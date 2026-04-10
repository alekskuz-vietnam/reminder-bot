import asyncio
import os
from telethon import TelegramClient, events
from telethon.sessions import StringSession

API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]
BOT_TOKEN = os.environ["BOT_TOKEN"]
MY_CHAT_ID = int(os.environ["MY_CHAT_ID"])
SESSION_STRING = os.environ["SESSION_STRING"]

CHANNELS = [
    "vandroukiru",
    "piratesru",
    "samokatus",
    "cheaptrip",
    "travelradar_ru",
]

KEYWORDS = [
    "Вьетнам",
]

client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
bot = TelegramClient("bot", API_ID, API_HASH)

@client.on(events.NewMessage(chats=CHANNELS))
async def handler(event):
    text = event.message.text or ""
    text_lower = text.lower()
    found = [kw for kw in KEYWORDS if kw.lower() in text_lower]
    if not found:
        return
    keywords_str = ", ".join(found)
    forward_text = (
        f"🔍 Найдено в канале: {event.chat.title}\n"
        f"🏷 Слова: {keywords_str}\n\n"
        f"{text[:1000]}"
    )
    await bot.send_message(MY_CHAT_ID, forward_text)

async def main():
    await client.start()
    await bot.start(bot_token=BOT_TOKEN)
    print("Userbot запущен, слежу за каналами...")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
