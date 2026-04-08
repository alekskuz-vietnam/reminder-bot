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

MONTHS_RU = {
    'января':1,'февраля':2,'марта':3,'апреля':4,'мая':5,'июня':6,
    'июля':7,'августа':8,'сентября':9,'октября':10,'ноября':11,'декабря':12
}
WEEKDAYS_RU = {
    'понедельник':0,'вторник':1,'среда':2,'среды':2,'среду':2,
    'четверг':3,'пятница':4,'пятницу':4,'пятници':4,
    'суббота':5,'субботу':5,'воскресенье':6,'воскресенья':6
}

def now():
    return datetime.now(TIMEZONE)

def next_weekday(weekday):
    """Ближайший указанный день недели (не сегодня)"""
    n = now()
    days_ahead = weekday - n.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    return n + timedelta(days=days_ahead)

def parse_time_str(s):
    """Парсит строку времени: 10:00, 10, возвращает (hour, minute) или None"""
    s = s.strip().rstrip('/')
    m = re.match(r'^(\d{1,2}):(\d{2})$', s)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.match(r'^(\d{1,2})$', s)
    if m:
        h = int(m.group(1))
        if 0 <= h <= 23:
            return h, 0
    return None

def apply_time(dt, hour, minute):
    return dt.replace(hour=hour, minute=minute, second=0, microsecond=0)

def parse_datetime(text):
    """
    Возвращает (fire_dt, reminder_text, repeat_monthly, error)
    """
    text = text.strip()
    t = now()

    # === Ежемесячное: "каждое 1 число месяца 10:00 текст" ===
    m = re.match(r'^каждо[ей]\s+(\d{1,2})\s+числ[ао]\s+месяца\s+(\S+)(.*)', text, re.IGNORECASE)
    if m:
        day = int(m.group(1))
        time_parts = parse_time_str(m.group(2))
        reminder = m.group(3).strip()
        if time_parts:
            h, mn = time_parts
            target = t.replace(day=day, hour=h, minute=mn, second=0, microsecond=0)
            if target <= t:
                # следующий месяц
                if t.month == 12:
                    target = target.replace(year=t.year+1, month=1)
                else:
                    target = target.replace(month=t.month+1)
            return target, reminder or "Ежемесячное напоминание", True, None

    # === Формат "число.месяц.год" или "число.месяц" ===
    m = re.match(r'^(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?\s*(\S*)?(.*)', text)
    if m:
        day, month = int(m.group(1)), int(m.group(2))
        year = int(m.group(3)) if m.group(3) else t.year
        time_str = m.group(4) or ''
        reminder = m.group(5).strip() if m.group(5) else ''
        time_parts = parse_time_str(time_str)
        h, mn = time_parts if time_parts else (10, 0)
        try:
            target = TIMEZONE.localize(datetime(year, month, day, h, mn, 0))
            if target <= t:
                target = target.replace(year=year+1)
            return target, reminder or text, False, None
        except ValueError:
            pass

    # === "число месяц_рус (год)? время? текст" ===
    pattern_date = r'^(\d{1,2})\s+(' + '|'.join(MONTHS_RU.keys()) + r')(?:\s+(\d{4}))?\s*(\S*)?(.*)'
    m = re.match(pattern_date, text, re.IGNORECASE)
    if m:
        day = int(m.group(1))
        month = MONTHS_RU[m.group(2).lower()]
        year = int(m.group(3)) if m.group(3) else t.year
        time_str = m.group(4) or ''
        reminder = m.group(5).strip() if m.group(5) else ''
        time_parts = parse_time_str(time_str)
        h, mn = time_parts if time_parts else (10, 0)
        try:
            target = TIMEZONE.localize(datetime(year, month, day, h, mn, 0))
            if target <= t:
                target = target.replace(year=year+1)
            return target, reminder or text, False, None
        except ValueError:
            pass

    # === День недели ===
    pattern_wd = r'^(' + '|'.join(WEEKDAYS_RU.keys()) + r')\s*(\S*)?(.*)'
    m = re.match(pattern_wd, text, re.IGNORECASE)
    if m:
        wd = WEEKDAYS_RU[m.group(1).lower()]
        time_str = m.group(2) or ''
        reminder = m.group(3).strip() if m.group(3) else ''
        time_parts = parse_time_str(time_str)
        h, mn = time_parts if time_parts else (10, 0)
        target = apply_time(next_weekday(wd), h, mn)
        return target, reminder or text, False, None

    # === Завтра ===
    m = re.match(r'^завтра\s*(\S*)?(.*)', text, re.IGNORECASE)
    if m:
        time_str = m.group(1) or ''
        reminder = m.group(2).strip() if m.group(2) else ''
        time_parts = parse_time_str(time_str)
        h, mn = time_parts if time_parts else (10, 0)
        target = apply_time(t + timedelta(days=1), h, mn)
        return target, reminder or "Напоминание", False, None

    # === Относительное: 30m / 2h ===
    m = re.match(r'^(\d+)(m|h|ч|мин)\s*(.*)', text, re.IGNORECASE)
    if m:
        val = int(m.group(1))
        unit = m.group(2).lower()
        reminder = m.group(3).strip()
        delta = timedelta(hours=val) if unit in ('h','ч') else timedelta(minutes=val)
        return t + delta, reminder or "Напоминание", False, None

    # === Просто время: 16:00 текст или 16 текст ===
    m = re.match(r'^(\d{1,2}(?::\d{2})?)\s+(.*)', text)
    if m:
        time_parts = parse_time_str(m.group(1))
        reminder = m.group(2).strip()
        if time_parts:
            h, mn = time_parts
            target = apply_time(t, h, mn)
            if target <= t:
                target += timedelta(days=1)
            return target, reminder, False, None

    return None, None, False, "Не понял формат. Примеры:\n16:00 Текст\n30m Текст\nзавтра 10:00 Текст\nпонедельник 10:00 Текст\n4 апреля 10:00 Текст\n23.10 10:00 Текст"

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    chat_id = update.effective_chat.id

    fire_dt, reminder_text, repeat_monthly, err = parse_datetime(text)
    if err:
        await update.message.reply_text(err)
        return

    delay = (fire_dt - now()).total_seconds()
    if delay < 0:
        delay = 0

    job_name = f"{chat_id}_{int(fire_dt.timestamp())}"
    fire_str = fire_dt.strftime("%-d %B %Y г. (в %A) в %H:%M")

    job_data = {
        "text": reminder_text,
        "repeat": True,
        "repeat_monthly": repeat_monthly,
        "chat_id": chat_id,
        "original_day": fire_dt.day if repeat_monthly else None,
        "original_hour": fire_dt.hour,
        "original_minute": fire_dt.minute,
    }

    context.job_queue.run_once(
        send_reminder,
        when=delay,
        chat_id=chat_id,
        name=job_name,
        data=job_data
    )

    keyboard = [[InlineKeyboardButton("✅ Готово", callback_data=f"done_{job_name}")]]
    await update.message.reply_text(
        f"☑️ Напоминание запланировано.\n\n"
        f"⌚️ <b>{fire_str}</b>\n"
        f"〰️ {reminder_text}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    chat_id = data["chat_id"]
    text = data["text"]
    job_name = context.job.name

    keyboard = [[InlineKeyboardButton("✅ Выполнено", callback_data=f"done_{job_name}")]]
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"❕ {text}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    if data.get("repeat_monthly"):
        # Следующий месяц
        n = now()
        month = n.month + 1 if n.month < 12 else 1
        year = n.year + 1 if n.month == 12 else n.year
        try:
            next_dt = TIMEZONE.localize(datetime(year, month, data["original_day"],
                                                  data["original_hour"], data["original_minute"]))
            delay = (next_dt - now()).total_seconds()
            context.job_queue.run_once(send_reminder, when=delay,
                                       chat_id=chat_id, name=job_name, data=data)
        except Exception:
            pass
    elif data.get("repeat"):
        # Повтор через 15 минут
        context.job_queue.run_once(send_reminder, when=15*60,
                                   chat_id=chat_id, name=job_name, data=data)

async def done_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    job_name = query.data.replace("done_", "")
    jobs = context.job_queue.get_jobs_by_name(job_name)
    for job in jobs:
        job.schedule_removal()
    await query.answer("Отмечено как выполнено!")
    try:
        new_text = query.message.text.replace("❕", "✔️")
        await query.edit_message_text(text=new_text)
    except Exception:
        await query.edit_message_reply_markup(reply_markup=None)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Просто напиши напоминание:\n\n"
        "<b>16:00 Позвонить маме</b>\n"
        "<b>30m Проверить почту</b>\n"
        "<b>завтра 10:00 Зубной врач</b>\n"
        "<b>понедельник 10:00 Встреча</b>\n"
        "<b>4 апреля 10:00 Продлить страховку</b>\n"
        "<b>23.10 10:00 Оплатить аренду</b>\n"
        "<b>каждое 1 число месяца 10:00 Отчёт</b>\n\n"
        "Буду напоминать каждые 15 минут пока не нажмёшь ✅",
        parse_mode="HTML"
    )

async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    all_jobs = context.job_queue.jobs()
    my_jobs = [j for j in all_jobs if j.chat_id == chat_id and j.data]
    if not my_jobs:
        await update.message.reply_text("Нет активных напоминаний.")
        return
    lines = []
    n = now()
    for j in my_jobs:
        try:
            secs = int(j.next_t.timestamp() - n.timestamp())
            mins = max(0, secs // 60)
            lines.append(f"❕ {j.data['text']} — через {mins} мин.")
        except Exception:
            pass
    await update.message.reply_text("\n".join(lines) if lines else "Нет активных напоминаний.")

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
