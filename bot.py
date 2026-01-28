import os
import asyncio
from dataclasses import dataclass, field
from typing import Dict, Set
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ContentType,
)
from aiogram.filters import Command

import gspread
from google.oauth2.service_account import Credentials

# ================== НАСТРОЙКИ ==================

TOKEN = os.getenv("TOKEN")
RETURNS_CHAT_ID = int(os.getenv("RETURNS_CHAT_ID"))

if not TOKEN or not RETURNS_CHAT_ID:
    raise RuntimeError("TOKEN или RETURNS_CHAT_ID не заданы")

PVZ_LIST = [
    "Яхромская 3",
    "Учинская 3 к1",
    "Лобненская 4",
    "Яхромская 2",
    "Дмитровское шоссе 103",
    "Дмитровское шоссе 107 к2",
    "Дмитровское шоссе 127 к1",
    "Софьи Ковалевской 8",
    "Дмитровское шоссе 100 с2",
]

# ================== GOOGLE SHEETS ==================

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")

import json
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

google_creds_json = os.getenv("GOOGLE_CREDS_JSON")
if not google_creds_json:
    raise RuntimeError("GOOGLE_CREDS_JSON not set in environment")

creds = Credentials.from_service_account_info(
    json.loads(google_creds_json),
    scopes=SCOPES
)

gs = gspread.authorize(creds)
sheet = gs.open_by_key(GOOGLE_SHEET_ID).sheet1

# ================== СОСТОЯНИЕ ==================

@dataclass
class SupplierState:
    company: str | None = None
    photo_file_id: str | None = None
    selected_pvz: Set[str] = field(default_factory=set)

users: Dict[int, SupplierState] = {}

# ================== INIT ==================

bot = Bot(TOKEN)
dp = Dispatcher()

# ================== START ==================

@dp.message(Command("start"))
async def start(message: Message):
    if message.chat.type != "private":
        return

    users[message.from_user.id] = SupplierState()
    await message.answer(
        "Привет 👋\n\n"
        "Я бот *Brendwall Logistic* 📦\n\n"
        "Сюда можно отправлять *фото штрихкодов возвратов*, как только они появятся.\n"
        "Я передам всю информацию нашей команде.\n\n"
       "Для начала, пожалуйста, напиши *название своего ИП/ООО* одним сообщением.\n\n"
        "_Пример: ИП Иванов И.И._",
        parse_mode="Markdown",
    )

# ================== ИМЯ ПОСТАВЩИКА ==================

@dp.message(F.text & ~F.text.startswith("/"))
async def set_company(message: Message):
    if message.chat.type != "private":
        return

    state = users.get(message.from_user.id)
    if not state or state.company:
        return

    state.company = message.text.strip()
    await message.answer(
        f"Отлично ✅\n"
        f"ИП: *{state.company}*\n\n"
        "Теперь отправь *фото* штрихкода возврата.",
        parse_mode="Markdown",
    )

# ================== ФОТО ==================

@dp.message(F.content_type == ContentType.PHOTO)
async def handle_photo(message: Message):
    if message.chat.type != "private":
        return

    state = users.get(message.from_user.id)
    if not state or not state.company:
        await message.answer("Сначала напиши название ИП/ООО через /start")
        return

    state.photo_file_id = message.photo[-1].file_id
    state.selected_pvz.clear()

    await message.answer(
        "Выбери один или несколько ПВЗ, затем нажми «ОК»",
        reply_markup=build_pvz_keyboard(state),
    )

# ================== КНОПКИ ==================

def build_pvz_keyboard(state: SupplierState) -> InlineKeyboardMarkup:
    keyboard = []

    for pvz in PVZ_LIST:
        mark = "☑️" if pvz in state.selected_pvz else "⬜️"
        keyboard.append([
            InlineKeyboardButton(
                text=f"{mark} {pvz}",
                callback_data=f"pvz:{pvz}",
            )
        ])

    keyboard.append([
        InlineKeyboardButton(text="✅ ОК", callback_data="confirm")
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# ================== ВЫБОР ПВЗ ==================

@dp.callback_query(F.data.startswith("pvz:"))
async def toggle_pvz(callback: CallbackQuery):
    state = users.get(callback.from_user.id)
    if not state:
        return

    pvz = callback.data.replace("pvz:", "")
    if pvz in state.selected_pvz:
        state.selected_pvz.remove(pvz)
    else:
        state.selected_pvz.add(pvz)

    await callback.message.edit_reply_markup(
        reply_markup=build_pvz_keyboard(state)
    )
    await callback.answer()

# ================== ПОДТВЕРЖДЕНИЕ ==================

@dp.callback_query(F.data == "confirm")
async def confirm(callback: CallbackQuery):
    state = users.get(callback.from_user.id)
    if not state or not state.selected_pvz:
        await callback.answer("Выберите хотя бы один ПВЗ", show_alert=True)
        return

    pvz_text = "\n".join(f"• {p}" for p in state.selected_pvz)

    caption = (
        f"📦 *Возврат*\n\n"
        f"🏷 Клиент: *{state.company}*\n"
        f"📍 ПВЗ:\n{pvz_text}"
    )

    await bot.send_photo(
        RETURNS_CHAT_ID,
        photo=state.photo_file_id,
        caption=caption,
        parse_mode="Markdown",
    )

    # ===== логирование =====
    sheet.append_row([
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        state.company,
        callback.from_user.full_name,
        ", ".join(state.selected_pvz),
        state.photo_file_id,
    ])

    await callback.message.answer(
        "✅ Штрихкод возврата доставлен.\n"
        "Спасибо!"
    )

    await callback.message.delete()

    state.photo_file_id = None
    state.selected_pvz.clear()

    await callback.answer()

# ================== RUN ==================

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())


