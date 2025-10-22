# bot.py
import asyncio
from dataclasses import dataclass, field
from typing import Optional, Set

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup,
    InlineKeyboardButton, ContentType
)

import os
TOKEN = os.getenv("TOKEN")

# === Ваши ПВЗ ===
PVZ_LIST = [
    "Яхромская 3",
    "Учинская 3 к1",
    "Лобненская 4",
    "Яхромская 2",
    "Дмитровское шоссе 103",
    "Дмитровское шоссе 107 к2",
    "Дмитровское шоссе 127 к1",
    "Софьи Ковалевской 8",
]

@dataclass
class SelectSession:
    chat_id: int
    origin_msg_id: int
    file_id: str
    sender_id: int
    selected: Set[int] = field(default_factory=set)
    keyboard_msg_id: Optional[int] = None

sessions: dict[int, SelectSession] = {}  # key = origin_msg_id

def build_keyboard(s: SelectSession) -> InlineKeyboardMarkup:
    rows = []
    row = []
    for i, name in enumerate(PVZ_LIST):
        checked = "☑" if i in s.selected else "☐"
        text = f"{checked} {name}"
        row.append(InlineKeyboardButton(text=text, callback_data=f"sel:{i}:{s.origin_msg_id}"))
        if len(row) == 2:
            rows.append(row); row = []
    if row:
        rows.append(row)
    rows.append([
        InlineKeyboardButton(text="✅ Готово", callback_data=f"done:{s.origin_msg_id}"),
        InlineKeyboardButton(text="✖ Отмена", callback_data=f"cancel:{s.origin_msg_id}")
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def caption_for(s: SelectSession) -> str:
    if not s.selected:
        return "Относится к ПВЗ: (не выбрано)"
    items = [PVZ_LIST[i] for i in sorted(s.selected)]
    return "Относится к ПВЗ:\n• " + "\n• ".join(items)

dp = Dispatcher()

@dp.message(Command("start"))
async def start(m: Message):
    await m.reply(
        "Кидайте фото/QR — выберите один или несколько ПВЗ и нажмите «Готово».\n"
        "Бот опубликует ту же картинку с подписью адресов."
    )

@dp.message(F.content_type.in_({ContentType.PHOTO, ContentType.DOCUMENT}))
async def on_image(m: Message):
    file_id = None
    if m.photo:
        file_id = m.photo[-1].file_id
    elif m.document and (m.document.mime_type or "").startswith("image/"):
        file_id = m.document.file_id

    if not file_id:
        await m.reply("Это не похоже на изображение. Пришлите фото или картинку.")
        return

    s = SelectSession(
        chat_id=m.chat.id,
        origin_msg_id=m.message_id,
        file_id=file_id,
        sender_id=m.from_user.id if m.from_user else 0,
    )
    sessions[m.message_id] = s
    sent = await m.reply(
        "Выберите один или несколько ПВЗ, затем нажмите «Готово».",
        reply_markup=build_keyboard(s)
    )
    s.keyboard_msg_id = sent.message_id

@dp.callback_query(F.data.startswith(("sel:", "done:", "cancel:")))
async def on_callbacks(cq: CallbackQuery):
    try:
        action, rest = cq.data.split(":", 1)
        if action == "sel":
            idx_str, origin_id_str = rest.split(":")
        else:
            origin_id_str = rest
        origin_id = int(origin_id_str)
    except Exception:
        await cq.answer("Некорректные данные.", show_alert=True)
        return

    s = sessions.get(origin_id)
    if not s:
        await cq.answer("Сессия не найдена (время истекло или завершена).", show_alert=True)
        return

    if cq.from_user.id != s.sender_id:
        await cq.answer("Только отправитель может выбирать адреса.", show_alert=True)
        return

    if action == "sel":
        idx = int(idx_str)
        if idx < 0 or idx >= len(PVZ_LIST):
            await cq.answer("Такого ПВЗ нет.", show_alert=True)
            return
        if idx in s.selected:
            s.selected.remove(idx)
        else:
            s.selected.add(idx)
        await cq.message.edit_reply_markup(reply_markup=build_keyboard(s))
        await cq.answer()
        return

    if action == "cancel":
        try:
            await cq.message.edit_text("Выбор отменён.")
        except Exception:
            pass
        sessions.pop(origin_id, None)
        await cq.answer("Отменено.")
        return

    if action == "done":
        await cq.bot.send_photo(chat_id=s.chat_id, photo=s.file_id, caption=caption_for(s))
        try:
            await cq.message.edit_text("Готово. Публикация отправлена.")
        except Exception:
            pass
        sessions.pop(origin_id, None)
        await cq.answer("Опубликовано.")
        return

async def main():
    bot = Bot(TOKEN)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

