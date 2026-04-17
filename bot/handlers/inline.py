"""Inline-режим: поиск и шаринг расписаний через @bot в любом чате."""
import logging
from uuid import uuid4

from aiogram import Router
from aiogram.types import (
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    LinkPreviewOptions,
)

from api import api
from config import BOT_USERNAME
from formatters import direct_link, format_share_message_html

log = logging.getLogger(__name__)
router = Router()

_app_url = f"https://t.me/{BOT_USERNAME}/app"


@router.inline_query()
async def handle_inline_query(query: InlineQuery):
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
                        InlineKeyboardButton(text="Открыть приложение", url=_app_url)
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
        dur = s.get("duration", 60)
        plat = s.get("platform", "jitsi")
        link = direct_link(sid)
        msg = format_share_message_html(sid)

        subtitle = f"{dur} мин · {plat}"
        if s.get("description"):
            subtitle += f" · {s['description'][:40]}"

        results.append(
            InlineQueryResultArticle(
                id=str(uuid4()),
                title=f"📅 {title}",
                description=subtitle,
                input_message_content=InputTextMessageContent(
                    message_text=msg,
                    parse_mode="HTML",
                    link_preview_options=LinkPreviewOptions(
                        url=link,
                    ),
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
                InlineKeyboardButton(text="Открыть приложение", url=_app_url)
            ]]),
        )
    )

    await query.answer(results=results, cache_time=30, is_personal=True)
