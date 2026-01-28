# bot.py
import os
import asyncio
from dataclasses import dataclass
from typing import Dict

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ContentType
)

# ===== НАСТРОЙКИ =====

TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise RuntimeError("Переменная окружения TOKEN не задана")

# 👉 сюда потом вставишь chat_id группы Возвраты
RETURNS_CHAT_ID = int(os.getenv("RETURNS_CHAT_ID"))  # например: -1001234567890

DELETE_ORIGINAL_PHOTO = True
DELETE_KEYBOARD_MESSAGE = True

PVZ_LIST = [
    "Яхромская 3",
    "Яхромская 2",
    "Учинская 3 к1",
    "Лобненская 4",
    "Дмит ш 107 к3",
    "Дмит ш 103",
    "Дмит ш 107 к2",
    "Дмит ш 127 к1",
    "Норд Хаус",
    "С Ковалевской 8",
]

# ===== ХРАНИЛИЩЕ СОСТОЯНИЯ (ПРОСТО И НАДЁЖНО) =====

@dataclass
class SupplierState:
    name: str | None = None
    last_photo_id: str | None = None

suppliers: Dict[int, SupplierState] = {}

# ===== ИНИЦИАЛИЗАЦИЯ =====

bot = Bot(token=TOKEN)
dp = Dispatcher()

# ===== КОМАНДЫ =====

@dp.message(F.text.startswith("/getid"))
async def get_chat_id(message: Message):
    await message.reply(f"Chat ID: {message.chat.id}")

@dp.message(Command("start"))
async def start(message: Message):
    suppliers[message.from_user.id] = SupplierState()
    await message.answer(
        "Привет 👋\n\n"
        "Напиши, пожалуйста, *название твоего ИП* одним сообщением.",
        parse_mode="Markdown"
    )

# ===== ПОЛУЧЕНИЕ ИМЕНИ ПОСТАВЩИКА =====

@dp.message(F.text & ~F.text.startswith("/"))
async def set_supplier_name(message: Message):
    state = suppliers.get(message.from_user.id)
    if not state:
        return

    if state.name is None:
        state.name = message.text.strip()
        await message.answer(
            f"Отлично, *{state.name}* ✅\n\n"
            "Теперь отправь фото ШК возврата.",
            parse_mode="Markdown"
        )

# ===== ПОЛУЧЕНИЕ ФОТО =====

@dp.message(F.content_type == ContentType.PHOTO)
async def handle_photo(message: Message):
    user_id = message.from_user.id
    state = suppliers.get(user_id)

    if not state or not state.name:
        await message.answer("Сначала напиши название ИП через /start")
        return

    state.last_photo_id = message.photo[-1].file_id

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=pvz, callback_data=f"pvz:{pvz}")]
            for pvz in PVZ_LIST
        ]
    )

    await message.answer("Выбери адрес ПВЗ:", reply_markup=keyboard)

    if DELETE_ORIGINAL_PHOTO:
        await message.delete()

# ===== ОБРАБОТКА ВЫБОРА ПВЗ =====

@dp.callback_query(F.data.startswith("pvz:"))
async def pvz_selected(callback: CallbackQuery):
    user_id = callback.from_user.id
    state = suppliers.get(user_id)

    if not state or not state.last_photo_id:
        await callback.answer("Ошибка состояния", show_alert=True)
        return

    pvz = callback.data.split(":", 1)[1]

    if RETURNS_CHAT_ID is None:
        await callback.answer("RETURNS_CHAT_ID не задан", show_alert=True)
        return

    caption = (
        f"📦 *Возврат*\n\n"
        f"👤 Поставщик: *{state.name}*\n"
        f"📍 Адрес: *{pvz}*"
    )

    await bot.send_photo(
        chat_id=RETURNS_CHAT_ID,
        photo=state.last_photo_id,
        caption=caption,
        parse_mode="Markdown"
    )

    if DELETE_KEYBOARD_MESSAGE:
        await callback.message.delete()

    state.last_photo_id = None
    await callback.answer("Отправлено ✅")

# ===== ЗАПУСК =====

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

