import logging
import re
from datetime import datetime, timedelta
import pytz
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes, JobQueue
)

logging.basicConfig(level=logging.INFO)
TIMEZONE = pytz.timezone("Europe/Moscow")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бот-напоминалка.\n\n"
        "/remind 30m Текст — через 30 минут\n"
        "/remind 2h Текст — через 2 часа\n"
        "/remind 18:00 Текст — в конкретное время\n"
        "/list — список напоминаний\n"
        "/cancel — отменить напоминание"
    )

async def remind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("Использование: /remind 30m Текст или /remind 18:00 Текст")
        return

    time_arg = context.args[0]
    text = " ".join(context.args[1:])
    chat_id = update.effective_chat.id
    now = datetime.now(TIMEZONE)

    delay = None

    match = re.match(r"^(\d+)(m|h)$", time_arg)
    if match:
        value = int(match.group(1))
        unit = match.group(2)
        delay = timedelta(minutes=value) if unit == "m" else timedelta(hours=value)
    else:
        match2 = re.match(r"^(\d{1,2}):(\d{2})$", time_arg)
        if match2:
            hour, minute = int(match2.group(1)), int(match2.group(2))
            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            delay = target - now

    if delay is None:
        await update.message.reply_text("Не понял время. Используй: 30m, 2h или 18:00")
        return

    fire_time = now + delay
    job = context.job_queue.run_once(
        send_reminder,
        when=delay.total_seconds(),
        chat_id=chat_id,
        name=str(chat_id),
        data=text
    )

    await update.message.reply_text(
        f"Напомню в {fire_time.strftime('%H:%M')} — {text}"
    )

async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(
        chat_id=context.job.chat_id,
        text=f"Напоминание: {context.job.data}"
    )

async def list_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    jobs = context.job_queue.get_jobs_by_name(str(chat_id))
    if not jobs:
        await update.message.reply_text("Нет активных напоминаний.")
        return
    lines = []
    now = datetime.now(TIMEZONE)
    for i, job in enumerate(jobs, 1):
        fire_in = int(job.next_t.timestamp() - now.timestamp())
        minutes = fire_in // 60
        lines.append(f"{i}. {job.data} — через {minutes} мин.")
    await update.message.reply_text("\n".join(lines))

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    jobs = context.job_queue.get_jobs_by_name(str(chat_id))
    if not jobs:
        await update.message.reply_text("Нет активных напоминаний.")
        return
    for job in jobs:
        job.schedule_removal()
    await update.message.reply_text(f"Отменено напоминаний: {len(jobs)}")

import os

def main():
    token = os.environ["BOT_TOKEN"]
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("remind", remind))
    app.add_handler(CommandHandler("list", list_reminders))
    app.add_handler(CommandHandler("cancel", cancel))
    app.run_polling()

if __name__ == "__main__":
    main()
