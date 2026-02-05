import asyncio
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher
from aiogram.types import ChatMemberUpdated
from aiogram.filters.chat_member_updated import ChatMemberUpdatedFilter, JOIN_TRANSITION

# --- SOZLAMALAR ---
TOKEN = "8451159147:AAGM58p2h3Nr0kIzB0n9IrCivlCXfrNCTPk"
bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- BAZA BILAN ISHLASH ---
def init_db():
    conn = sqlite3.connect("kanal_a'zolari.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS members (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            joined_date TEXT,
            channel_id INTEGER
        )
    ''')
    conn.commit()
    conn.close()

def save_user(user_id, username, full_name, channel_id):
    conn = sqlite3.connect("kanal_a'zolari.db")
    cursor = conn.cursor()
    now = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    # INSERT OR IGNORE - agar foydalanuvchi oldin bor bo'lsa, qayta yozmaydi
    cursor.execute('''
        INSERT OR IGNORE INTO members (user_id, username, full_name, joined_date, channel_id)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, username, full_name, now, channel_id))
    conn.commit()
    conn.close()

# --- KANALGA QO'SHILGANLARNI TUTUVCHI HANDLER ---
@dp.chat_member(ChatMemberUpdatedFilter(JOIN_TRANSITION))
async def on_user_joined_channel(event: ChatMemberUpdated):
    # Faqat kanallarni tekshirish (ixtiyoriy)
    if event.chat.type == 'channel':
        user = event.new_chat_member.user
        
        user_id = user.id
        username = f"@{user.username}" if user.username else "Mavjud emas"
        full_name = user.full_name
        channel_id = event.chat.id
        
        save_user(user_id, username, full_name, channel_id)
        print(f"Kanalga yangi odam qo'shildi: {full_name} | ID: {user_id}")

# --- ISHGA TUSHIRISH ---
async def main():
    init_db()
    print("Bot kanallarni kuzatishni boshladi...")
    # Barcha update'larni (shu jumladan chat_member) olishni yoqish
    await dp.start_polling(bot, allowed_updates=["chat_member", "message"])

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot to'xtatildi")