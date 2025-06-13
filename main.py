from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters
from datetime import datetime
import asyncio
import logging

TOKEN = '7928886857:AAGS7Fe1u4KInYZe2SJ8qcZbXjcm18uljQI'
admin_ids = [7452519221]

daily_limit = {'kamar_mandi': 50, 'merokok': 50, 'makan': 50, 'bab': 50}
user_timers = {}
user_activities = {}
user_izin_counts = {}

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower().strip()
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    message_id = update.message.message_id

    if 'izin ambil makan' in text:
        await handle_izin(update, context, user_id, chat_id, message_id, 'makan', 20)
    elif 'izin kamar mandi bab' in text:
        await handle_izin(update, context, user_id, chat_id, message_id, 'bab', None)
    elif 'izin kamar mandi' in text:
        await handle_izin(update, context, user_id, chat_id, message_id, 'kamar_mandi', 5)
    elif 'izin merokok' in text:
        await handle_izin(update, context, user_id, chat_id, message_id, 'merokok', 10)

async def handle_izin(update, context, user_id, chat_id, message_id, izin_type, duration):
    if user_izin_counts.get(user_id, {}).get(izin_type, 0) >= daily_limit.get(izin_type, 0):
        await safe_send_message(context, chat_id, f"⚠️ Batas izin {izin_type} hari ini sudah habis.", message_id)
        return

    if user_id in user_timers:
     await safe_send_message(context, chat_id, "⏳ Kamu masih punya izin aktif.")
     return

    reason = f"Izin {izin_type}"
    info = f"🕒 {reason} dimulai."
    if duration:
        info += f"\n⏳ Waktu: {duration} menit."

    await safe_send_message(context, chat_id, info, message_id)

    task = asyncio.create_task(timer_task(duration, chat_id, user_id, context, reason, message_id)) if duration else asyncio.create_task(wait_indefinitely(user_id))

    user_timers[user_id] = {
        'task': task,
        'start_time': datetime.now(),
        'reason': reason,
        'message_id': message_id,
        'duration': duration
    }

    user_activities.setdefault(user_id, {})
    user_activities[user_id][izin_type] = user_activities[user_id].get(izin_type, 0) + 1

    user_izin_counts.setdefault(user_id, {})
    user_izin_counts[user_id][izin_type] = user_izin_counts[user_id].get(izin_type, 0) + 1

async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    message_id = update.message.message_id

    if user_id in user_timers:
        start_time = user_timers[user_id]['start_time']
        reason = user_timers[user_id]['reason']
        duration_limit = user_timers[user_id].get('duration')
        elapsed = datetime.now() - start_time
        minutes = elapsed.seconds // 60
        seconds = elapsed.seconds % 60

        text = f"✅ {reason} selesai.\n⏱️ Durasi: {minutes} menit {seconds} detik."
        if duration_limit and elapsed.total_seconds() > duration_limit * 60:
            text += "\n⚠️ Estimasi waktu terlewati."

        user_timers[user_id]['task'].cancel()
        del user_timers[user_id]
    else:
        text = "⚠️ Gak ada izin aktif.\nKetik 'izin ambil makan' atau lainnya."

    await safe_send_message(context, chat_id, text, message_id)

async def rekap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    report = "📊 Ringkasan Harian:\n"
    if not user_activities:
        return await safe_send_message(context, update.message.chat.id, "⚠️ Belum ada data aktivitas.", update.message.message_id)

    for user_id, activities in user_activities.items():
        try:
            user = await context.bot.get_chat(user_id)
            username = f"@{user.username}" if user.username else f"ID: {user_id}"
        except:
            username = f"ID: {user_id}"

        detail = "\n".join([f"{k}: {v} kali" for k, v in activities.items()])
        report += f"\n🏷️ {username}:\n{detail}\n"

    await safe_send_message(context, update.message.chat.id, report, update.message.message_id)

async def siapa_izin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    aktif = []
    for user_id in user_timers:
        try:
            user = await context.bot.get_chat(user_id)
            username = f"@{user.username}" if user.username else f"ID: {user_id}"
            aktif.append(username)
        except:
            aktif.append(f"ID: {user_id}")

    text = "✅ Orang yang masih izin:\n" + "\n".join(aktif) if aktif else "⚠️ Tidak ada yang sedang izin."
    await safe_send_message(context, update.message.chat.id, text, update.message.message_id)

async def reset_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in admin_ids:
        return await safe_send_message(context, update.message.chat.id, "❌ Hanya admin yang bisa reset.", update.message.message_id)

    user_timers.clear()
    user_activities.clear()
    user_izin_counts.clear()
    await safe_send_message(context, update.message.chat.id, "✅ Semua data berhasil direset.")

async def set_batas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in admin_ids:
        return await safe_send_message(context, update.message.chat.id, "❌ Hanya admin yang bisa atur batas.", update.message.message_id)

    try:
        izin_type = context.args[0]
        limit = int(context.args[1])
        daily_limit[izin_type] = limit
        await safe_send_message(context, update.message.chat.id, f"✅ Batas {izin_type} diubah jadi {limit}.")
    except:
        await safe_send_message(context, update.message.chat.id, "⚠️ Format: /set_batas <izin> <jumlah>")

async def timer_task(duration, chat_id, user_id, context, reason, message_id):
    try:
        await asyncio.sleep(duration * 60)
        await safe_send_message(context, chat_id, f"⏰ {reason} selesai otomatis setelah {duration} menit.", message_id)
    except asyncio.CancelledError:
        return
    finally:
        user_timers.pop(user_id, None)

async def wait_indefinitely(user_id):
    try:
        while True:
            await asyncio.sleep(60)
    except asyncio.CancelledError:
        return

async def safe_send_message(context, chat_id, text, reply_id=None):
    try:
        await context.bot.send_message(chat_id=chat_id, text=text, reply_to_message_id=reply_id)
        await asyncio.sleep(0.5)
    except Exception as e:
        logging.error(f"Error sending message: {e}")

# === RUN BOT DENGAN DROP SPAM ===
async def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.add_handler(CommandHandler("done", done))
    app.add_handler(CommandHandler("rekap", rekap))
    app.add_handler(CommandHandler("siapa_izin", siapa_izin))
    app.add_handler(CommandHandler("reset_data", reset_data))
    app.add_handler(CommandHandler("set_batas", set_batas))

    await app.bot.delete_webhook(drop_pending_updates=True)  # 🛡️ ANTI SPAM SAAT NYALA
    print("🤖 Bot aktif dan menunggu perintah...")
    await app.run_polling()

if __name__ == '__main__':
    asyncio.run(main())
