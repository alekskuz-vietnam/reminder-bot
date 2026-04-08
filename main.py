import logging
import re
import os
import pytz
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters, CommandHandler
)

logging.basicConfig(level=logging.INFO)
TIMEZONE = pytz.timezone("Europe/Moscow")

def now():
    return datetime.now(TIMEZONE)

def parse_time(text):
    text = text.strip()
    # "16:00" или "9:30"
    m = re.match(r'^(\d{1,2}):(\d{2})$', text)
    if m:
        h, mn = int(m.group(1)), int(m.group(2))
        t = now().replace(hour=h, minute=mn, second=0, microsecond=0)
        if t <= now():
            t += timedelta(days=1)
        return t, None
    # "30m" или "2h"
    m = re.match(r'^(\d+)(m|h)$', text.lower())
    if m:
        val = int(m.group(1))
        unit = m.group(2)
        delta = timedelta(minutes=val) if unit == 'm' else timedelta(hours=val)
        return now() + delta, None
    # "завтра 10:00"
    m = re.match(r'^завтра\s+(\d{1,2}):(\d{2})$', text.lower())
    if m:
        h, mn = int(m.group(1)), int(m.group(2))
        t = (now() + timedelta(days=1)).replace(hour=h, minute=mn, second=0, microsecond=0)
        return t, None
    return None, "Не понял время. Примеры: 16:00 / 30m / 2h / завтра 10:00"

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    chat_id = update.effective_chat.id

    # Попробуем разобрать: "время текст"
    parts = text.split(None, 1)
    if len(parts) < 2:
        await update.message.reply_text(
            "Напиши напоминание в формате:\n"
            "<b>16:00 Позвонить маме</b>\n"
            "<b>30m Проверить почту</b>\n"
            "<b>2h Встреча</b>\n"
            "<b>завтра 9:00 Зубной врач</b>",
            parse_mode="HTML"
        )
        return

    time_str, err = parse_time(parts[0])
    if err:
        await update.message.reply_text(err)
        return

    reminder_text = parts[1]
    delay = (time_str - now()).total_seconds()
    fire_dt = time_str.strftime("%d %B %Y г. в %H:%M")

    job = context.job_queue.run_once(
        send_reminder,
        when=delay,
        chat_id=chat_id,
        name=f"{chat_id}_{id(time_str)}",
        data={"text": reminder_text, "repeat": True, "chat_id": chat_id}
    )

    keyboard = [[InlineKeyboardButton("✅ Готово", callback_data=f"done_{job.name}")]]
    await update.message.reply_text(
        f"☑️ Напоминание запланировано.\n\n"
        f"⌚️ <b>{fire_dt}</b>\n"
        f"〰️ {reminder_text}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    chat_id = data["chat_id"]
    text = data["text"]

    keyboard = [[InlineKeyboardButton("✅ Выполнено", callback_data=f"done_{context.job.name}")]]
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"❕ {text}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    # Повтор через 15 минут если не отмечено выполненным
    if data.get("repeat", False):
        context.job_queue.run_once(
            send_reminder,
            when=15 * 60,
            chat_id=chat_id,
            name=context.job.name,
            data=data
        )

async def done_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    job_name = query.data.replace("done_", "")

    # Убираем все повторы с этим именем
    jobs = context.job_queue.get_jobs_by_name(job_name)
    for job in jobs:
        job.schedule_removal()

    await query.answer("Отмечено как выполнено!")
    await query.edit_message_reply_markup(reply_markup=None)
    await query.edit_message_text(
        text=query.message.text.replace("❕", "✔️"),
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бот-напоминалка.\n\n"
        "Просто напиши:\n"
        "<b>16:00 Позвонить маме</b>\n"
        "<b>30m Проверить почту</b>\n"
        "<b>2h Встреча с командой</b>\n"
        "<b>завтра 9:00 Зубной врач</b>\n\n"
        "Буду напоминать каждые 15 минут пока не нажмёшь ✅",
        parse_mode="HTML"
    )

async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    all_jobs = context.job_queue.jobs()
    my_jobs = [j for j in all_jobs if j.chat_id == chat_id]
    if not my_jobs:
        await update.message.reply_text("Нет активных напоминаний.")
        return
    lines = []
    for j in my_jobs:
        secs = int(j.next_t.timestamp() - now().timestamp())
        mins = max(0, secs // 60)
        lines.append(f"❕ {j.data['text']} — через {mins} мин.")
    await update.message.reply_text("\n".join(lines))

def main():
    token = os.environ["BOT_TOKEN"]
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("list", list_cmd))
    app.add_handler(CallbackQueryHandler(done_callback, pattern="^done_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()
