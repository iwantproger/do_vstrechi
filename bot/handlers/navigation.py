"""Handlers: main_menu, my_schedules, my_bookings, stats."""
import logging

from aiogram import Router, F
from aiogram.enums import ParseMode
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from api import api
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
    schedules = resp.get("schedules", []) if isinstance(resp, dict) else (resp or [])

    if not schedules:
        await cb.message.edit_text(
            "У тебя пока нет расписаний.\n\nСоздай первое!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Создать", callback_data="create_schedule")],
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
    buttons.append([InlineKeyboardButton(text="➕ Создать новое", callback_data="create_schedule")])
    buttons.append([InlineKeyboardButton(text="« Назад",         callback_data="main_menu")])

    await cb.message.edit_text(
        f"📋 Твои расписания ({len(schedules)}):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await cb.answer()


@router.callback_query(F.data == "my_bookings")
async def cb_my_bookings(cb: CallbackQuery):
    resp = await api("get", f"/api/bookings?telegram_id={cb.from_user.id}")
    bookings = resp.get("bookings", []) if isinstance(resp, dict) else (resp or [])

    if not bookings:
        await cb.message.edit_text("У тебя пока нет встреч.", reply_markup=kb_back_main)
        await cb.answer()
        return

    buttons = []
    for b in bookings[:10]:
        emoji = STATUS_EMOJI.get(b["status"], "?")
        dt    = format_dt(b["scheduled_time"], tz=b.get("organizer_timezone") or "UTC")
        role  = "📌" if b.get("my_role") == "organizer" else "👤"
        buttons.append([InlineKeyboardButton(
            text=f"{role}{emoji} {b.get('schedule_title','?')} · {dt}",
            callback_data=f"booking_{b['id']}",
        )])
    buttons.append([InlineKeyboardButton(text="« Назад", callback_data="main_menu")])

    await cb.message.edit_text(
        f"📋 <b>Твои встречи ({len(bookings)})</b>\n"
        f"📌 = организатор, 👤 = гость",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode=ParseMode.HTML,
    )
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
