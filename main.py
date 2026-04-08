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
WEEKDAYS_NAMES = ['понедельник','вторник','среда','четверг','пятница','суббота','воскресенье']

def now():
    return datetime.now(TIMEZONE)

def next_weekday(weekday):
    n = now()
    days_ahead = weekday - n.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    return n + timedelta(days=days_ahead)

def parse_time_str(s):
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
    text = text.strip()
    t = now()

    m = re.match(r'^каждо[ей]\s+(\d{1,2})\s+числ[ао]\s+месяца\s+(\S+)(.*)', text, re.IGNORECASE)
    if m:
        day = int(m.group(1))
        time_parts = parse_time_str(m.group(2))
        reminder = m.group(3).strip()
        if time_parts:
            h, mn = time_parts
            target = t.replace(day=day, hour=h, minute=mn, second=0, microsecond=0)
            if target <= t:
                month = t.month + 1 if t.month < 12 else 1
                year = t.year + 1 if t.month == 12 else t.year
                target = target.replace(year=year, month=month)
            return target, reminder or "Ежемесячное напоминание", True, None

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

    m = re.match(r'^завтра\s*(\S*)?(.*)', text, re.IGNORECASE)
    if m:
        time_str = m.group(1) or ''
        reminder = m.group(2).strip() if m.group(2) else ''
        time_parts = parse_time_str(time_str)
        h, mn = time_parts if time_parts else (10, 0)
        target = apply_time(t + timedelta(days=1), h, mn)
        return target, reminder or "Напоминание", False, None

    m = re.match(r'^(\d+)(m|h|ч|мин)\s*(.*)', text, re.IGNORECASE)
    if m:
        val = int(m.group(1))
        unit = m.group(2).lower()
        reminder = m.group(3).strip()
        delta = timedelta(hours=val) if unit in ('h','ч') else timedelta(minutes=val)
        return t + delta, reminder or "Напоминание", False, None

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

    return None, None, False, (
        "Не понял формат. Примеры:\n"
        "<b>16:00 Текст\n30m Текст\nзавтра 10:00 Текст\n"
        "понедельник 10:00 Текст\n4 апреля 10:00 Текст\n"
        "23.10 10:00 Текст\nкаждое 1 число месяца 10:00 Текст</b>"
    )

def get_user_jobs(context, chat_id):
    return sorted(
        [j for j in context.job_queue.jobs() if j.chat_id == chat_id and j.data],
        key=lambda j: j.next_t
    )

def format_job(j, idx):
    data = j.data
    fire_dt = j.next_t.astimezone(TIMEZONE)
    wd = WEEKDAYS_NAMES[fire_dt.weekday()]
    date_str = fire_dt.strftime(f"%-d %B %Y г. (в {wd}) в %H:%M")
    lines = [f"{idx}) ⌚ {date_str}"]
    if data.get("repeat_monthly"):
        day = data.get("original_day", "?")
        h = data.get("original_hour", 10)
        mn = data.get("original_minute", 0)
        lines.append(f"∞ каждое {day}-е число месяца в {h:02d}:{mn:02d}")
    lines.append(f"〰️ {data['text']}")
    return "\n".join(lines)

def list_keyboard(page, total_pages, show_delete=False, jobs_on_page=0):
    rows = []
    if not show_delete:
        nav = []
        if total_pages > 1:
            nav.append(InlineKeyboardButton(">", callback_data=f"list_next_{page}"))
            nav.append(InlineKeyboardButton(">>", callback_data=f"list_last_{total_pages-1}"))
        if nav:
            rows.append(nav)
        rows.append([InlineKeyboardButton("✖️ Удалить по номеру", callback_data=f"list_delete_mode_{page}")])
    else:
        # Сетка номеров
        nums = list(range(1, jobs_on_page + 1))
        row = []
        for n in nums:
            row.append(InlineKeyboardButton(str(n), callback_data=f"list_del_{page}_{n-1}"))
            if len(row) == 5:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        rows.append([InlineKeyboardButton("« Назад", callback_data=f"list_page_{page}")])
    return InlineKeyboardMarkup(rows)

def build_list_text(jobs, page):
    per_page = 10
    start = page * per_page
    chunk = jobs[start:start+per_page]
    if not chunk:
        return "Нет активных напоминаний.", []
    lines = ["⚡ <b>Активные напоминания</b>\n"]
    for i, j in enumerate(chunk):
        lines.append(format_job(j, start + i + 1))
    return "\n".join(lines), chunk

async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    jobs = get_user_jobs(context, chat_id)
    if not jobs:
        await update.message.reply_text("Нет активных напоминаний.")
        return
    per_page = 10
    total_pages = max(1, (len(jobs) + per_page - 1) // per_page)
    text, chunk = build_list_text(jobs, 0)
    kb = list_keyboard(0, total_pages, show_delete=False, jobs_on_page=len(chunk))
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb)

async def list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    data = query.data
    jobs = get_user_jobs(context, chat_id)
    per_page = 10
    total_pages = max(1, (len(jobs) + per_page - 1) // per_page)

    if data.startswith("list_page_"):
        page = int(data.split("_")[-1])
        text, chunk = build_list_text(jobs, page)
        kb = list_keyboard(page, total_pages, show_delete=False, jobs_on_page=len(chunk))
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)

    elif data.startswith("list_next_"):
        page = int(data.split("_")[-1])
        next_page = min(page + 1, total_pages - 1)
        text, chunk = build_list_text(jobs, next_page)
        kb = list_keyboard(next_page, total_pages, show_delete=False, jobs_on_page=len(chunk))
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)

    elif data.startswith("list_last_"):
        page = int(data.split("_")[-1])
        text, chunk = build_list_text(jobs, page)
        kb = list_keyboard(page, total_pages, show_delete=False, jobs_on_page=len(chunk))
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)

    elif data.startswith("list_delete_mode_"):
        page = int(data.split("_")[-1])
        text, chunk = build_list_text(jobs, page)
        kb = list_keyboard(page, total_pages, show_delete=True, jobs_on_page=len(chunk))
        await query.edit_message_reply_markup(reply_markup=kb)

    elif data.startswith("list_del_"):
        parts = data.split("_")
        page = int(parts[2])
        idx_on_page = int(parts[3])
        start = page * per_page
        target_idx = start + idx_on_page
        if target_idx < len(jobs):
            jobs[target_idx].schedule_removal()
        jobs = get_user_jobs(context, chat_id)
        total_pages = max(1, (len(jobs) + per_page - 1) // per_page)
        page = min(page, total_pages - 1)
        if not jobs:
            await query.edit_message_text("Нет активных напоминаний.")
            return
        text, chunk = build_list_text(jobs, page)
        kb = list_keyboard(page, total_pages, show_delete=False, jobs_on_page=len(chunk))
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)

def creation_keyboard(job_name):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🕐 Изменить", callback_data=f"edit_{job_name}"),
        InlineKeyboardButton("✖️ Отменить", callback_data=f"cancel_{job_name}"),
    ]])

def reminder_keyboard(job_name):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("1 час", callback_data=f"snooze_1h_{job_name}"),
            InlineKeyboardButton("3 часа", callback_data=f"snooze_3h_{job_name}"),
            InlineKeyboardButton("1 день", callback_data=f"snooze_1d_{job_name}"),
        ],
        [
            InlineKeyboardButton("...", callback_data=f"snooze_custom_{job_name}"),
            InlineKeyboardButton("✅ Готово", callback_data=f"done_{job_name}"),
        ]
    ])

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    chat_id = update.effective_chat.id

    if context.user_data.get("waiting_reschedule"):
        await handle_reschedule_input(update, context)
        return

    fire_dt, reminder_text, repeat_monthly, err = parse_datetime(text)
    if err:
        await update.message.reply_text(err, parse_mode="HTML")
        return

    delay = max(0, (fire_dt - now()).total_seconds())
    job_name = f"{chat_id}_{int(fire_dt.timestamp())}"
    wd = WEEKDAYS_NAMES[fire_dt.weekday()]
    fire_str = fire_dt.strftime(f"%-d %B %Y г. (в {wd}) в %H:%M")

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
        send_reminder, when=delay,
        chat_id=chat_id, name=job_name, data=job_data
    )

    await update.message.reply_text(
        f"☑️ Напоминание запланировано.\n\n⌚️ <b>{fire_str}</b>\n〰️ {reminder_text}",
        parse_mode="HTML",
        reply_markup=creation_keyboard(job_name)
    )

async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    chat_id = data["chat_id"]
    job_name = context.job.name

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"❕ {data['text']}",
        reply_markup=reminder_keyboard(job_name)
    )

    if data.get("repeat_monthly"):
        n = now()
        month = n.month + 1 if n.month < 12 else 1
        year = n.year + 1 if n.month == 12 else n.year
        try:
            next_dt = TIMEZONE.localize(datetime(year, month, data["original_day"],
                                                  data["original_hour"], data["original_minute"]))
            context.job_queue.run_once(send_reminder, when=(next_dt - now()).total_seconds(),
                                       chat_id=chat_id, name=job_name, data=data)
        except Exception:
            pass
    elif data.get("repeat"):
        context.job_queue.run_once(send_reminder, when=15*60,
                                   chat_id=chat_id, name=job_name, data=data)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    raw = query.data

    if raw.startswith("list_"):
        await list_callback(update, context)
        return

    if raw.startswith("cancel_"):
        job_name = raw[len("cancel_"):]
        for job in context.job_queue.get_jobs_by_name(job_name):
            job.schedule_removal()
        await query.edit_message_text("✖️ Напоминание отменено.")
        return

    if raw.startswith("edit_"):
        job_name = raw[len("edit_"):]
        context.user_data["waiting_reschedule"] = job_name
        context.user_data["reschedule_text"] = query.message.text.split("〰️")[-1].strip() if "〰️" in query.message.text else "Напоминание"
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("⌚️ Напиши новое время (например: <b>18:00</b> или <b>завтра 10:00</b>)", parse_mode="HTML")
        return

    if raw.startswith("done_"):
        job_name = raw[len("done_"):]
        for job in context.job_queue.get_jobs_by_name(job_name):
            job.schedule_removal()
        try:
            await query.edit_message_text(query.message.text.replace("❕", "✔️"))
        except Exception:
            await query.edit_message_reply_markup(reply_markup=None)
        return

    for prefix, delta in [("snooze_1h_", timedelta(hours=1)),
                           ("snooze_3h_", timedelta(hours=3)),
                           ("snooze_1d_", timedelta(days=1))]:
        if raw.startswith(prefix):
            job_name = raw[len(prefix):]
            for job in context.job_queue.get_jobs_by_name(job_name):
                job.schedule_removal()
            reminder_text = query.message.text.replace("❕ ", "").strip()
            fire_dt = now() + delta
            new_job_name = f"{query.message.chat_id}_{int(fire_dt.timestamp())}"
            wd = WEEKDAYS_NAMES[fire_dt.weekday()]
            fire_str = fire_dt.strftime(f"%-d %B %Y г. (в {wd}) в %H:%M")
            job_data = {"text": reminder_text, "repeat": True, "repeat_monthly": False, "chat_id": query.message.chat_id}
            context.job_queue.run_once(send_reminder, when=delta.total_seconds(),
                                       chat_id=query.message.chat_id, name=new_job_name, data=job_data)
            await query.edit_message_text(f"⏰ Перенесено на <b>{fire_str}</b>\n〰️ {reminder_text}", parse_mode="HTML")
            return

    if raw.startswith("snooze_custom_"):
        job_name = raw[len("snooze_custom_"):]
        reminder_text = query.message.text.replace("❕ ", "").strip()
        context.user_data["waiting_reschedule"] = job_name
        context.user_data["reschedule_text"] = reminder_text
        for job in context.job_queue.get_jobs_by_name(job_name):
            job.schedule_removal()
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("⌚️ Напиши новое время (например: <b>18:00</b> или <b>завтра 10:00</b>)", parse_mode="HTML")
        return

async def handle_reschedule_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    job_name = context.user_data.get("waiting_reschedule")
    reminder_text = context.user_data.get("reschedule_text", "Напоминание")
    chat_id = update.effective_chat.id

    for job in context.job_queue.get_jobs_by_name(job_name):
        job.schedule_removal()

    tp = parse_time_str(text)
    if tp:
        h, mn = tp
        fire_dt = apply_time(now(), h, mn)
        if fire_dt <= now():
            fire_dt += timedelta(days=1)
    else:
        fire_dt, _, _, err = parse_datetime(text + " x")
        if err or not fire_dt:
            await update.message.reply_text("Не понял время. Напиши например: <b>18:00</b> или <b>завтра 10:00</b>", parse_mode="HTML")
            return

    context.user_data.pop("waiting_reschedule", None)
    context.user_data.pop("reschedule_text", None)

    delay = max(0, (fire_dt - now()).total_seconds())
    new_job_name = f"{chat_id}_{int(fire_dt.timestamp())}"
    wd = WEEKDAYS_NAMES[fire_dt.weekday()]
    fire_str = fire_dt.strftime(f"%-d %B %Y г. (в {wd}) в %H:%M")

    context.job_queue.run_once(send_reminder, when=delay, chat_id=chat_id,
                               name=new_job_name, data={
                                   "text": reminder_text, "repeat": True,
                                   "repeat_monthly": False, "chat_id": chat_id
                               })
    await update.message.reply_text(
        f"☑️ Перенесено.\n\n⌚️ <b>{fire_str}</b>\n〰️ {reminder_text}",
        parse_mode="HTML", reply_markup=creation_keyboard(new_job_name)
    )

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
        "Буду напоминать каждые 15 минут пока не нажмёшь ✅\n\n"
        "/list — список напоминаний",
        parse_mode="HTML"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Форматы напоминаний:\n\n"
        "<b>16:00 Текст</b> — сегодня в 16:00\n"
        "<b>30m Текст</b> — через 30 минут\n"
        "<b>2h Текст</b> — через 2 часа\n"
        "<b>завтра 10:00 Текст</b>\n"
        "<b>понедельник 10:00 Текст</b>\n"
        "<b>4 апреля 10:00 Текст</b>\n"
        "<b>23.10 10:00 Текст</b>\n"
        "<b>каждое 1 число месяца 10:00 Текст</b>\n\n"
        "Команды:\n"
        "/list — список активных напоминаний\n"
        "/help — эта справка",
        parse_mode="HTML"
    )

async def getid_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Ваш chat ID: <code>{update.effective_chat.id}</code>", parse_mode="HTML")

def main():
    token = os.environ["BOT_TOKEN"]
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("getid", getid_cmd))
    app.add_handler(CommandHandler("list", list_cmd))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()
