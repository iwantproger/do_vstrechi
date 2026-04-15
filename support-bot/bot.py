"""
Support Bot для «До встречи»
Feedback bot — пересылка сообщений между пользователями и админами.
"""
import asyncio
import logging
from datetime import datetime

from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.filters import CommandStart, Command
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN, ADMIN_CHAT_ID, ADMIN_IDS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

router = Router()
user_sessions: dict[int, dict] = {}


def get_user_info(user: types.User) -> str:
    name = user.full_name or "Unknown"
    username = f"@{user.username}" if user.username else "нет username"
    session = user_sessions.get(user.id, {})
    msg_count = session.get("messages_count", 0)
    return (
        f"👤 <b>{name}</b>\n"
        f"🆔 <code>{user.id}</code> · {username}\n"
        f"📨 Сообщение #{msg_count}"
    )


def update_session(user: types.User):
    now = datetime.now().isoformat()
    if user.id not in user_sessions:
        user_sessions[user.id] = {
            "first_name": user.full_name,
            "username": user.username,
            "messages_count": 0,
            "first_contact": now,
        }
    user_sessions[user.id]["messages_count"] += 1
    user_sessions[user.id]["last_contact"] = now
    user_sessions[user.id]["first_name"] = user.full_name
    user_sessions[user.id]["username"] = user.username


@router.message(CommandStart())
async def cmd_start(message: types.Message):
    if message.from_user.id in ADMIN_IDS:
        count = len(user_sessions)
        await message.answer(
            f"🛠 <b>Панель поддержки</b>\n\n"
            f"Активных диалогов: {count}\n\n"
            f"Чтобы ответить — reply на пересланное сообщение.\n\n"
            f"/stats — статистика",
            parse_mode=ParseMode.HTML,
        )
    else:
        await message.answer(
            "👋 Привет! Это поддержка <b>До встречи</b>.\n\n"
            "Напишите ваш вопрос — мы ответим как можно скорее.\n"
            "Можно отправить текст, фото, скриншот или голосовое.",
            parse_mode=ParseMode.HTML,
        )


@router.message(Command("stats"))
async def cmd_stats(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    total = len(user_sessions)
    total_msgs = sum(s.get("messages_count", 0) for s in user_sessions.values())
    text = f"📊 <b>Статистика</b>\n\nОбращений: {total}\nСообщений: {total_msgs}\n"
    if user_sessions:
        text += "\n<b>Последние:</b>\n"
        recent = sorted(user_sessions.items(), key=lambda x: x[1].get("last_contact", ""), reverse=True)[:10]
        for uid, s in recent:
            name = s.get("first_name", "?")
            uname = f"@{s['username']}" if s.get("username") else ""
            text += f"  • {name} {uname} — {s.get('messages_count', 0)} сообщ.\n"
    await message.answer(text, parse_mode=ParseMode.HTML)


@router.message(~F.chat.id.in_(ADMIN_IDS))
async def user_message(message: types.Message):
    """Сообщение от пользователя → пересылаем админу."""
    user = message.from_user
    update_session(user)
    info = get_user_info(user)
    try:
        await message.bot.send_message(ADMIN_CHAT_ID, f"📩 <b>Новое сообщение</b>\n\n{info}", parse_mode=ParseMode.HTML)
        await message.forward(ADMIN_CHAT_ID)
        if user_sessions[user.id]["messages_count"] == 1:
            await message.answer("✅ Сообщение отправлено! Мы ответим в ближайшее время.")
    except Exception as e:
        log.error(f"Forward failed from {user.id}: {e}")
        await message.answer("❌ Ошибка отправки. Попробуйте позже.")


@router.message(F.chat.id.in_(ADMIN_IDS), F.reply_to_message)
async def admin_reply(message: types.Message):
    """Админ отвечает на forward → ответ уходит пользователю."""
    replied = message.reply_to_message
    target_user_id = None
    if replied.forward_from:
        target_user_id = replied.forward_from.id
    elif replied.forward_sender_name:
        for uid, session in user_sessions.items():
            if session.get("first_name") == replied.forward_sender_name:
                target_user_id = uid
                break
    if not target_user_id:
        await message.answer("⚠️ Не удалось определить пользователя. Ответьте reply на пересланное сообщение.")
        return
    try:
        await message.copy_to(target_user_id)
        await message.answer(f"✅ Отправлено пользователю {target_user_id}")
    except Exception as e:
        log.error(f"Reply failed to {target_user_id}: {e}")
        await message.answer(f"❌ Ошибка: {e}")


@router.message(Command("broadcast"), F.chat.id.in_(ADMIN_IDS))
async def cmd_broadcast(message: types.Message):
    text = message.text.replace("/broadcast", "", 1).strip()
    if not text:
        await message.answer("Использование: /broadcast <текст>")
        return
    sent, failed = 0, 0
    for uid in user_sessions:
        try:
            await message.bot.send_message(uid, f"📢 {text}")
            sent += 1
            await asyncio.sleep(0.1)
        except Exception:
            failed += 1
    await message.answer(f"📢 Отправлено: {sent}, ошибок: {failed}")


async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    log.info(f"Support bot starting, admin(s): {ADMIN_IDS}")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
