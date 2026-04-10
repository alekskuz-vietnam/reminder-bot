import asyncio
import os
import json
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters

API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]
BOT_TOKEN = os.environ["BOT_TOKEN"]
MY_CHAT_ID = int(os.environ["MY_CHAT_ID"])
SESSION_STRING = os.environ["SESSION_STRING"]

# Состояние — каналы и слова (можно менять через бота)
STATE = {
    "channels": [
        "vandroukiru",
        "piratesru",
        "samokatus",
        "cheaptrip",
        "travelradar_ru",
    ],
    "keywords": ["Вьетнам"],
    "active": True,
}

user_client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

# ===== TELEGRAM BOT (управление) =====

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != MY_CHAT_ID:
        return
    keyboard = [
        [InlineKeyboardButton("📡 Каналы", callback_data="menu_channels"),
         InlineKeyboardButton("🔍 Слова", callback_data="menu_keywords")],
        [InlineKeyboardButton("⏯ Вкл/Выкл мониторинг", callback_data="menu_toggle")],
        [InlineKeyboardButton("📊 Статус", callback_data="menu_status")],
    ]
    await update.message.reply_text(
        "⚙️ Управление мониторингом каналов:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def cmd_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_start(update, context)

def main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📡 Каналы", callback_data="menu_channels"),
         InlineKeyboardButton("🔍 Слова", callback_data="menu_keywords")],
        [InlineKeyboardButton("⏯ Вкл/Выкл мониторинг", callback_data="menu_toggle")],
        [InlineKeyboardButton("📊 Статус", callback_data="menu_status")],
    ])

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = query.message.chat_id

    if chat_id != MY_CHAT_ID:
        return

    if data == "menu_channels":
        channels_list = "\n".join(f"• @{c}" for c in STATE["channels"])
        keyboard = [
            [InlineKeyboardButton("➕ Добавить канал", callback_data="add_channel")],
            [InlineKeyboardButton("➖ Удалить канал", callback_data="del_channel_list")],
            [InlineKeyboardButton("« Назад", callback_data="back_main")],
        ]
        await query.edit_message_text(
            f"📡 Отслеживаемые каналы:\n\n{channels_list}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data == "menu_keywords":
        kw_list = "\n".join(f"• {k}" for k in STATE["keywords"])
        keyboard = [
            [InlineKeyboardButton("➕ Добавить слово", callback_data="add_keyword")],
            [InlineKeyboardButton("➖ Удалить слово", callback_data="del_keyword_list")],
            [InlineKeyboardButton("« Назад", callback_data="back_main")],
        ]
        await query.edit_message_text(
            f"🔍 Ключевые слова:\n\n{kw_list}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data == "menu_toggle":
        STATE["active"] = not STATE["active"]
        status = "✅ Включён" if STATE["active"] else "⏸ Выключен"
        await query.edit_message_text(
            f"Мониторинг: {status}",
            reply_markup=main_keyboard()
        )

    elif data == "menu_status":
        channels_list = "\n".join(f"• @{c}" for c in STATE["channels"])
        kw_list = ", ".join(STATE["keywords"])
        status = "✅ Включён" if STATE["active"] else "⏸ Выключен"
        await query.edit_message_text(
            f"📊 Статус мониторинга: {status}\n\n"
            f"📡 Каналы:\n{channels_list}\n\n"
            f"🔍 Слова: {kw_list}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("« Назад", callback_data="back_main")]
            ])
        )

    elif data == "back_main":
        await query.edit_message_text(
            "⚙️ Управление мониторингом каналов:",
            reply_markup=main_keyboard()
        )

    elif data == "add_channel":
        context.user_data["waiting"] = "add_channel"
        await query.edit_message_text(
            "Напиши username канала без @ (например: vandroukiru):",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("« Отмена", callback_data="menu_channels")]
            ])
        )

    elif data == "add_keyword":
        context.user_data["waiting"] = "add_keyword"
        await query.edit_message_text(
            "Напиши слово для поиска:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("« Отмена", callback_data="menu_keywords")]
            ])
        )

    elif data == "del_channel_list":
        if not STATE["channels"]:
            await query.edit_message_text("Нет каналов для удаления.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Назад", callback_data="menu_channels")]]))
            return
        buttons = [[InlineKeyboardButton(f"🗑 @{c}", callback_data=f"delch_{c}")] for c in STATE["channels"]]
        buttons.append([InlineKeyboardButton("« Назад", callback_data="menu_channels")])
        await query.edit_message_text("Выбери канал для удаления:",
            reply_markup=InlineKeyboardMarkup(buttons))

    elif data == "del_keyword_list":
        if not STATE["keywords"]:
            await query.edit_message_text("Нет слов для удаления.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Назад", callback_data="menu_keywords")]]))
            return
        buttons = [[InlineKeyboardButton(f"🗑 {k}", callback_data=f"delkw_{k}")] for k in STATE["keywords"]]
        buttons.append([InlineKeyboardButton("« Назад", callback_data="menu_keywords")])
        await query.edit_message_text("Выбери слово для удаления:",
            reply_markup=InlineKeyboardMarkup(buttons))

    elif data.startswith("delch_"):
        ch = data[6:]
        if ch in STATE["channels"]:
            STATE["channels"].remove(ch)
            await update_userbot_channels()
        channels_list = "\n".join(f"• @{c}" for c in STATE["channels"]) or "Нет каналов"
        await query.edit_message_text(
            f"✅ Канал @{ch} удалён.\n\n📡 Каналы:\n{channels_list}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Добавить канал", callback_data="add_channel")],
                [InlineKeyboardButton("➖ Удалить канал", callback_data="del_channel_list")],
                [InlineKeyboardButton("« Назад", callback_data="back_main")],
            ])
        )

    elif data.startswith("delkw_"):
        kw = data[6:]
        if kw in STATE["keywords"]:
            STATE["keywords"].remove(kw)
        kw_list = "\n".join(f"• {k}" for k in STATE["keywords"]) or "Нет слов"
        await query.edit_message_text(
            f"✅ Слово «{kw}» удалено.\n\n🔍 Слова:\n{kw_list}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Добавить слово", callback_data="add_keyword")],
                [InlineKeyboardButton("➖ Удалить слово", callback_data="del_keyword_list")],
                [InlineKeyboardButton("« Назад", callback_data="back_main")],
            ])
        )

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != MY_CHAT_ID:
        return
    waiting = context.user_data.get("waiting")
    if not waiting:
        return
    text = update.message.text.strip().lstrip("@")
    context.user_data.pop("waiting")

    if waiting == "add_channel":
        if text not in STATE["channels"]:
            STATE["channels"].append(text)
            await update_userbot_channels()
        channels_list = "\n".join(f"• @{c}" for c in STATE["channels"])
        await update.message.reply_text(
            f"✅ Канал @{text} добавлен.\n\n📡 Каналы:\n{channels_list}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Добавить канал", callback_data="add_channel")],
                [InlineKeyboardButton("➖ Удалить канал", callback_data="del_channel_list")],
                [InlineKeyboardButton("« Назад", callback_data="back_main")],
            ])
        )

    elif waiting == "add_keyword":
        if text not in STATE["keywords"]:
            STATE["keywords"].append(text)
        kw_list = "\n".join(f"• {k}" for k in STATE["keywords"])
        await update.message.reply_text(
            f"✅ Слово «{text}» добавлено.\n\n🔍 Слова:\n{kw_list}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Добавить слово", callback_data="add_keyword")],
                [InlineKeyboardButton("➖ Удалить слово", callback_data="del_keyword_list")],
                [InlineKeyboardButton("« Назад", callback_data="back_main")],
            ])
        )

# ===== USERBOT (мониторинг) =====

async def update_userbot_channels():
    """Перезапускает обработчик с новым списком каналов"""
    user_client.remove_event_handler(channel_handler)
    if STATE["channels"]:
        user_client.add_event_handler(
            channel_handler,
            events.NewMessage(chats=STATE["channels"])
        )

async def channel_handler(event):
    if not STATE["active"]:
        return
    text = event.message.text or ""
    text_lower = text.lower()
    found = [kw for kw in STATE["keywords"] if kw.lower() in text_lower]
    if not found:
        return
    keywords_str = ", ".join(found)
    forward_text = (
        f"🔍 Канал: {event.chat.title}\n"
        f"🏷 Слова: {keywords_str}\n\n"
        f"{text[:1000]}"
    )
    await user_client.send_message(MY_CHAT_ID, forward_text)

# ===== MAIN =====

async def main():
    await user_client.start()
    user_client.add_event_handler(
        channel_handler,
        events.NewMessage(chats=STATE["channels"])
    )
    print("Userbot запущен, слежу за каналами...")

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("setup", cmd_setup))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    await user_client.run_until_disconnected()

    await app.updater.stop()
    await app.stop()
    await app.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
