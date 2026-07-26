import asyncio
import logging
import sqlite3
import os
from datetime import datetime, timedelta
from typing import Optional
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.storage.memory import MemoryStorage

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS", "8428048355").split(",") if id.strip()]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=storage)

# --- База данных ---
class Database:
    def __init__(self, db_file="database.db"):
        self.conn = sqlite3.connect(db_file, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.init_db()
    
    def init_db(self):
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS mutes (
                user_id INTEGER,
                chat_id INTEGER,
                muted_until INTEGER,
                PRIMARY KEY (user_id, chat_id)
            )
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS deleted_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                user_id INTEGER,
                username TEXT,
                first_name TEXT,
                text TEXT,
                deleted_at INTEGER
            )
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS edited_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                user_id INTEGER,
                username TEXT,
                first_name TEXT,
                old_text TEXT,
                new_text TEXT,
                edited_at INTEGER
            )
        """)
        self.conn.commit()
    
    def add_mute(self, user_id: int, chat_id: int, until: int):
        self.cursor.execute(
            "INSERT OR REPLACE INTO mutes (user_id, chat_id, muted_until) VALUES (?, ?, ?)",
            (user_id, chat_id, until)
        )
        self.conn.commit()
    
    def remove_mute(self, user_id: int, chat_id: int):
        self.cursor.execute(
            "DELETE FROM mutes WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id)
        )
        self.conn.commit()
    
    def is_muted(self, user_id: int, chat_id: int) -> bool:
        self.cursor.execute(
            "SELECT muted_until FROM mutes WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id)
        )
        result = self.cursor.fetchone()
        if result:
            return result[0] > int(datetime.now().timestamp()) or result[0] == -1
        return False
    
    def save_deleted_message(self, chat_id: int, user_id: int, username: str, first_name: str, text: str):
        self.cursor.execute(
            """INSERT INTO deleted_messages 
               (chat_id, user_id, username, first_name, text, deleted_at) 
               VALUES (?, ?, ?, ?, ?, ?)""",
            (chat_id, user_id, username or "", first_name or "", text or "", 
             int(datetime.now().timestamp()))
        )
        self.conn.commit()
    
    def save_edited_message(self, chat_id: int, user_id: int, username: str,
                          first_name: str, old_text: str, new_text: str):
        self.cursor.execute(
            """INSERT INTO edited_messages 
               (chat_id, user_id, username, first_name, old_text, new_text, edited_at) 
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (chat_id, user_id, username or "", first_name or "", 
             old_text or "", new_text or "", int(datetime.now().timestamp()))
        )
        self.conn.commit()

db = Database()

# --- Клавиатуры ---
def get_admin_keyboard():
    buttons = [
        [InlineKeyboardButton(text="📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton(text="📋 Мутлист", callback_data="mutelist")],
        [InlineKeyboardButton(text="🔍 Логи", callback_data="logs")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- Функции ---
async def check_mute(message: Message) -> bool:
    if message.from_user.id in ADMIN_IDS:
        return False
    return db.is_muted(message.from_user.id, message.chat.id)

async def process_mute(message: Message, duration: int = None):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        if member.status in ["administrator", "creator"]:
            await message.reply("❌ Нельзя замутить администратора!")
            return
    except:
        pass
    
    until = -1 if duration is None else int((datetime.now() + timedelta(minutes=duration)).timestamp())
    db.add_mute(user_id, chat_id, until)
    
    if duration:
        await message.reply(f"🔇 Пользователь замучен на {duration} минут!")
    else:
        await message.reply("🔇 Пользователь замучен навсегда!")
    
    try:
        async for msg in bot.get_chat_history(chat_id, limit=50):
            if msg.from_user.id == user_id and msg.date > datetime.now() - timedelta(minutes=5):
                await msg.delete()
    except:
        pass

async def process_unmute(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not db.is_muted(user_id, chat_id):
        await message.reply("❌ Пользователь не в муте!")
        return
    
    db.remove_mute(user_id, chat_id)
    await message.reply("✅ Мут снят!")

async def process_spam(message: Message, count: int, text: str):
    if count > 50:
        await message.reply("❌ Нельзя спамить больше 50 сообщений!")
        return
    
    await message.delete()
    for _ in range(min(count, 50)):
        await message.answer(text)
        await asyncio.sleep(0.3)

# --- Обработчики команд ---
@dp.message(Command("start"))
async def cmd_start(message: Message):
    if message.chat.type != "private":
        return
    
    await message.answer(
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        "Я бот-модератор с функциями:\n"
        "• .mute [@username] [минуты] - замутить пользователя\n"
        "• .unmute [@username] - снять мут\n"
        "• .spam [кол-во] [текст] - спамить сообщения\n"
        "• .admin - админ-панель\n\n"
        "Добавь меня в группу и назначь администратором!",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(text="➕ Добавить в группу", 
                                   url=f"https://t.me/{bot.username}?startgroup=true")
            ]]
        )
    )

@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ У вас нет прав!")
        return
    
    await message.answer("⚙️ Админ-панель", reply_markup=get_admin_keyboard())

@dp.message(F.text.startswith(".mute"))
async def cmd_mute(message: Message):
    if message.chat.type == "private":
        await message.reply("❌ Команда работает только в группах!")
        return
    
    member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    if not (member.status in ["administrator", "creator"] or message.from_user.id in ADMIN_IDS):
        await message.reply("❌ Нет прав на мут!")
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.reply("❌ Использование: .mute [@username или ID] [минуты]")
        return
    
    target = None
    duration = None
    
    if args[1].startswith("@"):
        try:
            target_user = await bot.get_chat_member(message.chat.id, args[1])
            target = target_user.user.id
        except:
            await message.reply("❌ Пользователь не найден!")
            return
    else:
        try:
            target = int(args[1])
        except:
            await message.reply("❌ Укажите ID пользователя или @username!")
            return
    
    if len(args) > 2:
        try:
            duration = int(args[2])
            if duration <= 0:
                await message.reply("❌ Время должно быть положительным числом!")
                return
        except:
            await message.reply("❌ Укажите время в минутах числом!")
            return
    
    fake_message = await message.reply("...")
    fake_message.from_user.id = target
    fake_message.chat = message.chat
    
    await process_mute(fake_message, duration)

@dp.message(F.text.startswith(".unmute"))
async def cmd_unmute(message: Message):
    if message.chat.type == "private":
        await message.reply("❌ Команда работает только в группах!")
        return
    
    member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    if not (member.status in ["administrator", "creator"] or message.from_user.id in ADMIN_IDS):
        await message.reply("❌ Нет прав на снятие мута!")
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.reply("❌ Использование: .unmute [@username или ID]")
        return
    
    target = None
    if args[1].startswith("@"):
        try:
            target_user = await bot.get_chat_member(message.chat.id, args[1])
            target = target_user.user.id
        except:
            await message.reply("❌ Пользователь не найден!")
            return
    else:
        try:
            target = int(args[1])
        except:
            await message.reply("❌ Укажите ID пользователя или @username!")
            return
    
    fake_message = await message.reply("...")
    fake_message.from_user.id = target
    fake_message.chat = message.chat
    
    await process_unmute(fake_message)

@dp.message(F.text.startswith(".spam"))
async def cmd_spam(message: Message):
    if message.chat.type == "private":
        await message.reply("❌ Команда работает только в группах!")
        return
    
    member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    if not (member.status in ["administrator", "creator"] or message.from_user.id in ADMIN_IDS):
        await message.reply("❌ Нет прав на спам!")
        return
    
    args = message.text.split()
    if len(args) < 3:
        await message.reply("❌ Использование: .spam [кол-во] [текст]")
        return
    
    try:
        count = int(args[1])
        text = " ".join(args[2:])
    except:
        await message.reply("❌ Укажите число сообщений!")
        return
    
    await process_spam(message, count, text)

# --- Авто-модерация (ПРАВИЛЬНАЯ ВЕРСИЯ) ---
@dp.message()
async def handle_messages(message: Message):
    # Пропускаем админов
    if message.from_user.id in ADMIN_IDS:
        return
    
    # Проверяем мут
    if await check_mute(message):
        await message.delete()

# --- Сохранение удаленных сообщений ---
@dp.message(F.left_chat_member | F.right_chat_member)
async def handle_member_updates(message: Message):
    if message.left_chat_member:
        user = message.left_chat_member
        db.save_deleted_message(
            message.chat.id,
            user.id,
            user.username,
            user.first_name,
            "Вышел из чата"
        )

# --- Сохранение редактированных сообщений ---
@dp.edited_message()
async def handle_edited_message(message: Message):
    if not message.text or not message.reply_to_message:
        return
    
    db.save_edited_message(
        message.chat.id,
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name,
        message.reply_to_message.text or "",
        message.text
    )

# --- Inline кнопки ---
@dp.callback_query(F.data == "stats")
async def show_stats(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "📊 Статистика:\nБот активен и работает!",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")
            ]]
        )
    )

@dp.callback_query(F.data == "mutelist")
async def show_mutelist(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "📋 Список замученных:\nПока пусто.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")
            ]]
        )
    )

@dp.callback_query(F.data == "logs")
async def show_logs(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "🔍 Последние логи:\nЛогирование активно.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")
            ]]
        )
    )

@dp.callback_query(F.data == "admin_back")
async def back_to_admin(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "⚙️ Админ-панель",
        reply_markup=get_admin_keyboard()
    )

# --- Запуск ---
async def main():
    logger.info("Бот @Smertnymod_bot запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
