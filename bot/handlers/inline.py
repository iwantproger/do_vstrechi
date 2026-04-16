"""Inline-режим: поиск и шаринг расписаний через @bot в любом чате."""
import logging
from uuid import uuid4

from aiogram import Bot, Router
from aiogram.types import (
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from api import api
from config import MINI_APP_URL
from formatters import DAYS_RU

log = logging.getLogger(__name__)
router = Router()

PLATFORM_NAMES = {
    "jitsi": "Jitsi Meet",
    "zoom": "Zoom",
    "google_meet": "Google Meet",
    "other": "Другое",
}


def _bot_app_url(bot: Bot, startapp: str = "") -> str:
    base = f"https://t.me/{bot.me.username}/app"
    return f"{base}?startapp={startapp}" if startapp else base


@router.inline_query()
async def handle_inline_query(query: InlineQuery, bot: Bot):
    """Показать расписания пользователя для шаринга."""
    user_id = query.from_user.id
    search = (query.query or "").strip().lower()

    resp = await api("get", f"/api/schedules?telegram_id={user_id}")
    schedules = resp.get("schedules", []) if isinstance(resp, dict) else (resp or [])

    if not schedules:
        await query.answer(
            results=[
                InlineQueryResultArticle(
                    id=str(uuid4()),
                    title="У вас пока нет расписаний",
                    description="Откройте приложение, чтобы создать",
                    input_message_content=InputTextMessageContent(
                        message_text="📅 Создайте расписание в «До встречи»!",
                    ),
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(
                            text="Открыть приложение",
                            url=_bot_app_url(bot),
                        )
                    ]]),
                )
            ],
            cache_time=10,
            is_personal=True,
        )
        return

    active = [s for s in schedules if s.get("is_active", True) and not s.get("is_default")]

    if search:
        active = [s for s in active if search in s.get("title", "").lower()]

    results = []
    for s in active[:10]:
        sid = s["id"]
        title = s.get("title", "Без названия")
        desc = s.get("description", "")
        dur = s.get("duration", 60)
        plat = PLATFORM_NAMES.get(s.get("platform", ""), s.get("platform", ""))
        days = ", ".join(DAYS_RU[d] for d in sorted(s.get("work_days", [])) if d < 7)
        start = str(s.get("start_time", "09:00"))[:5]
        end = str(s.get("end_time", "18:00"))[:5]

        link = _bot_app_url(bot, sid)

        msg = (
            f"📅 <b>{title}</b>\n\n"
            f"⏱ {dur} мин · {plat}\n"
            f"📆 {days}, {start}–{end}\n"
        )
        if desc:
            msg += f"📝 {desc}\n"
        msg += f"\n👉 <a href=\"{link}\">Записаться на встречу</a>"

        subtitle = f"{dur} мин · {plat} · {days}"
        if desc:
            subtitle += f" · {desc[:40]}"

        results.append(
            InlineQueryResultArticle(
                id=str(uuid4()),
                title=f"📅 {title}",
                description=subtitle,
                input_message_content=InputTextMessageContent(
                    message_text=msg,
                    parse_mode="HTML",
                ),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="📅 Записаться", url=link)
                ]]),
            )
        )

    results.append(
        InlineQueryResultArticle(
            id=str(uuid4()),
            title="➕ Создать новое расписание",
            description="Откройте приложение для настройки",
            input_message_content=InputTextMessageContent(
                message_text="📅 Настройте расписание в «До встречи»!",
            ),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text="Открыть приложение",
                    url=_bot_app_url(bot),
                )
            ]]),
        )
    )

    await query.answer(results=results, cache_time=30, is_personal=True)
