"""Handlers: main_menu, my_schedules, my_bookings, stats."""
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Router, F
from aiogram.enums import ParseMode
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

from api import api
from config import MINI_APP_URL
from keyboards import kb_main, kb_back_main
from formatters import STATUS_EMOJI, format_dt

log = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "main_menu")
async def cb_main_menu(cb: CallbackQuery):
    await cb.message.edit_text("Выбери действие:", reply_markup=kb_main)
    await cb.answer()


@router.callback_query(F.data == "my_schedules")
async def cb_my_schedules(cb: CallbackQuery):
    resp = await api("get", f"/api/schedules?telegram_id={cb.from_user.id}")
    all_schedules = resp.get("schedules", []) if isinstance(resp, dict) else (resp or [])

    # Показываем только активные, не-default расписания
    schedules = [s for s in all_schedules
                 if s.get("is_active", True) and not s.get("is_default")]

    if not schedules:
        await cb.message.edit_text(
            "У тебя пока нет активных расписаний.\n\nСоздай первое!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Создать", web_app=WebAppInfo(url=MINI_APP_URL))],
                [InlineKeyboardButton(text="« Назад",   callback_data="main_menu")],
            ])
        )
        await cb.answer()
        return

    buttons = [
        [InlineKeyboardButton(
            text=f"📅 {s['title']} ({s['duration']} мин)",
            callback_data=f"schedule_{s['id']}",
        )]
        for s in schedules
    ]
    buttons.append([InlineKeyboardButton(text="➕ Создать новое", web_app=WebAppInfo(url=MINI_APP_URL))])
    buttons.append([InlineKeyboardButton(text="« Назад",         callback_data="main_menu")])

    await cb.message.edit_text(
        f"📋 Твои расписания ({len(schedules)}):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await cb.answer()


def _parse_dt(dt_str: str) -> datetime:
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


def _render_bookings(bookings: list, title: str, filter_type: str) -> tuple[str, InlineKeyboardMarkup]:
    """Build message text and keyboard for a filtered booking list."""
    buttons = []
    for b in bookings[:10]:
        emoji = STATUS_EMOJI.get(b["status"], "?")
        dt = format_dt(b["scheduled_time"], tz=b.get("organizer_timezone") or "UTC")
        role = "📌" if b.get("my_role") == "organizer" else "👤"
        buttons.append([InlineKeyboardButton(
            text=f"{role}{emoji} {b.get('schedule_title', '?')} · {dt}",
            callback_data=f"booking_{b['id']}",
        )])
    if len(bookings) > 10:
        buttons.append([InlineKeyboardButton(
            text=f"… ещё {len(bookings) - 10}",
            callback_data="meetings_noop",
        )])

    # Filter nav row
    nav = []
    if filter_type != "upcoming":
        nav.append(InlineKeyboardButton(text="📋 Актуальные", callback_data="meetings_upcoming"))
    if filter_type != "archive":
        nav.append(InlineKeyboardButton(text="🗂 Архив", callback_data="meetings_archive"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton(text="« Назад", callback_data="main_menu")])

    text = (
        f"📋 <b>{title} ({len(bookings)})</b>\n"
        f"📌 = организатор, 👤 = гость"
    )
    return text, InlineKeyboardMarkup(inline_keyboard=buttons)


async def _fetch_and_show_bookings(cb: CallbackQuery, filter_type: str = "upcoming"):
    resp = await api("get", f"/api/bookings?telegram_id={cb.from_user.id}")
    bookings = resp.get("bookings", []) if isinstance(resp, dict) else (resp or [])

    if not bookings:
        await cb.message.edit_text("У тебя пока нет встреч.", reply_markup=kb_back_main)
        await cb.answer()
        return

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)

    if filter_type == "upcoming":
        filtered = [b for b in bookings
                    if _parse_dt(b["scheduled_time"]) > cutoff
                    and b["status"] not in ("cancelled", "completed")]
        title = "Актуальные встречи"
    else:  # archive
        filtered = [b for b in bookings
                    if _parse_dt(b["scheduled_time"]) <= cutoff
                    or b["status"] in ("cancelled", "completed")]
        title = "Архив встреч"

    if not filtered:
        nav = []
        if filter_type == "upcoming":
            nav.append([InlineKeyboardButton(text="🗂 Архив", callback_data="meetings_archive")])
        else:
            nav.append([InlineKeyboardButton(text="📋 Актуальные", callback_data="meetings_upcoming")])
        nav.append([InlineKeyboardButton(text="« Назад", callback_data="main_menu")])
        await cb.message.edit_text(
            f"📋 <b>{title}</b>\n\nПусто.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=nav),
            parse_mode=ParseMode.HTML,
        )
        await cb.answer()
        return

    # Sort: upcoming by date asc, archive by date desc
    filtered.sort(key=lambda b: _parse_dt(b["scheduled_time"]),
                  reverse=(filter_type == "archive"))

    text, kb = _render_bookings(filtered, title, filter_type)
    await cb.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    await cb.answer()


@router.callback_query(F.data == "my_bookings")
async def cb_my_bookings(cb: CallbackQuery):
    await _fetch_and_show_bookings(cb, "upcoming")


@router.callback_query(F.data == "meetings_upcoming")
async def cb_meetings_upcoming(cb: CallbackQuery):
    await _fetch_and_show_bookings(cb, "upcoming")


@router.callback_query(F.data == "meetings_archive")
async def cb_meetings_archive(cb: CallbackQuery):
    await _fetch_and_show_bookings(cb, "archive")


@router.callback_query(F.data == "meetings_noop")
async def cb_meetings_noop(cb: CallbackQuery):
    await cb.answer()


@router.callback_query(F.data == "stats")
async def cb_stats(cb: CallbackQuery):
    stats = await api("get", f"/api/stats?telegram_id={cb.from_user.id}")

    if not stats:
        await cb.answer("Не удалось загрузить статистику", show_alert=True)
        return

    text = (
        "📊 <b>Твоя статистика</b>\n\n"
        f"📅 Активных расписаний: <b>{stats.get('active_schedules', 0)}</b>\n"
        f"📋 Всего встреч: <b>{stats.get('total_bookings', 0)}</b>\n"
        f"⏳ Ожидают подтверждения: <b>{stats.get('pending_bookings', 0)}</b>\n"
        f"✅ Подтверждено: <b>{stats.get('confirmed_bookings', 0)}</b>\n"
        f"🚀 Предстоящих: <b>{stats.get('upcoming_bookings', 0)}</b>\n"
    )
    await cb.message.edit_text(text, reply_markup=kb_back_main, parse_mode=ParseMode.HTML)
    await cb.answer()
