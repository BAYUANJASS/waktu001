from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters
from datetime import datetime
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")

user_timers = {}
user_activities = {}
user_izin_counts = {}
daily_limit = {'kamar_mandi': 100, 'merokok': 100, 'makan': 100, 'bab': 100}
admin_ids = [7452519221]

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
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
        await safe_send_message(context, chat_id, f"⚠️ Kamu sudah mencapai batas izin untuk {izin_type} hari ini.", message_id)
        return

    if user_id in user_timers:
        await safe_send_message(context, chat_id, "⏳ Kamu masih punya izin aktif.
Gunakan /done untuk menyelesaikannya.", message_id)
        return

    reason = f"Izin {izin_type}"
    info = f"🕒 {reason} dimulai."
    if duration:
        info += f"
⏳ Waktu: {duration} menit."

    await safe_send_message(context, chat_id, info, message_id)

    task = asyncio.create_task(timer_task(duration, chat_id, user_id, context, reason, message_id)) if duration else asyncio.create_task(wait_indefinitely(user_id))

    user_timers[user_id] = {
        'task': task,
        'start_time': datetime.now(),
        'reason': reason,
        'message_id': message_id,
        'duration': duration
    }

    if user_id not in user_activities:
        user_activities[user_id] = {}
    user_activities[user_id][izin_type] = user_activities[user_id].get(izin_type, 0) + 1

    if user_id not in user_izin_counts:
        user_izin_counts[user_id] = {izin_type: 1}
    else:
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

        text = f"✅ {reason} selesai.
⏱️ Durasi: {minutes} menit {seconds} detik."
        if duration_limit and elapsed.total_seconds() > duration_limit * 60:
            text += "
⚠️ Estimasi waktu telah terlewati."

        user_timers[user_id]['task'].cancel()
        del user_timers[user_id]
    else:
        text = "⚠️ Tidak ada izin aktif.
Ketik `/izin` atau 'izin ambil makan' untuk mulai."

    await safe_send_message(context, chat_id, text, message_id)

async def rekap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    report = "📊 Ringkasan Harian:
"
    if not user_activities:
        await safe_send_message(context, update.message.chat.id, "⚠️ Belum ada aktivitas yang tercatat.", update.message.message_id)
        return

    for user_id, activities in user_activities.items():
        try:
            user = await context.bot.get_chat(user_id)
            username = user.username if user.username else f"@{user_id}"
        except Exception:
            username = f"@{user_id}"

        activity_report = "
".join([f"{activity}: {count} kali" for activity, count in activities.items()])
        report += f"🏷️ {username}:
{activity_report}
"

    await safe_send_message(context, update.message.chat.id, report, update.message.message_id)

async def siapa_izin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    active_users = []
    for user_id in user_timers:
        try:
            user = await context.bot.get_chat(user_id)
            username = user.username if user.username else f"@{user_id}"
            active_users.append(username)
        except Exception:
            active_users.append(f"@{user_id}")

    text = f"✅ Orang yang masih izin:
" + "
".join(active_users) if active_users else "⚠️ Tidak ada yang sedang izin saat ini."
    await safe_send_message(context, update.message.chat.id, text, update.message.message_id)

async def reset_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in admin_ids:
        return await safe_send_message(context, update.message.chat.id, "⚠️ Hanya admin yang bisa menggunakan perintah ini.", update.message.message_id)

    user_timers.clear()
    user_activities.clear()
    user_izin_counts.clear()
    await safe_send_message(context, update.message.chat.id, "✅ Semua data telah direset.")

async def set_batas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in admin_ids:
        return await safe_send_message(context, update.message.chat.id, "⚠️ Hanya admin yang bisa menggunakan perintah ini.", update.message.message_id)

    if context.args:
        izin_type = context.args[0]
        try:
            limit = int(context.args[1])
            daily_limit[izin_type] = limit
            await safe_send_message(context, update.message.chat.id, f"✅ Batas izin {izin_type} diubah menjadi {limit} per hari.")
        except (ValueError, IndexError):
            await safe_send_message(context, update.message.chat.id, "⚠️ Format salah. Gunakan: /set_batas <izin_type> <limit>")
    else:
        await safe_send_message(context, update.message.chat.id, "⚠️ Mohon masukkan tipe izin dan batasnya.")

async def timer_task(duration, chat_id, user_id, context, reason, message_id):
    try:
        await asyncio.sleep(duration * 60)
        await safe_send_message(context, chat_id, f"⏰ {reason} selesai otomatis setelah {duration} menit.", message_id)
    except asyncio.CancelledError:
        return
    finally:
        if user_id in user_timers:
            del user_timers[user_id]

async def wait_indefinitely(user_id):
    try:
        while True:
            await asyncio.sleep(60)
    except asyncio.CancelledError:
        return

async def safe_send_message(context, chat_id, text, message_id):
    try:
        await context.bot.send_message(chat_id=chat_id, text=text, reply_to_message_id=message_id)
    except Exception as e:
        print(f"Error sending message: {e}")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.add_handler(CommandHandler("done", done))
    app.add_handler(CommandHandler("rekap", rekap))
    app.add_handler(CommandHandler("siapa_izin", siapa_izin))
    app.add_handler(CommandHandler("reset_data", reset_data))
    app.add_handler(CommandHandler("set_batas", set_batas))
    print("Bot aktif... Menunggu pesan...")
    app.run_polling()
