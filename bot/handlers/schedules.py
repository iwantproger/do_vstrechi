"""Handlers: просмотр, шаринг, удаление расписаний."""
import logging

from aiogram import Router, F
from aiogram.enums import ParseMode
from aiogram.types import CallbackQuery

from api import api
from keyboards import kb_schedule_actions, kb_back_main
from formatters import DAYS_RU, direct_link, format_share_message_html

log = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data.startswith("schedule_"))
async def cb_schedule_detail(cb: CallbackQuery):
    schedule_id = cb.data.split("_", 1)[1]
    s = await api("get", f"/api/schedules/{schedule_id}")

    if not s:
        await cb.answer("Расписание не найдено", show_alert=True)
        return

    days = [DAYS_RU[d] for d in sorted(s.get("work_days", []))]
    text = (
        f"📅 <b>{s['title']}</b>\n\n"
        f"⏱ Длительность: {s['duration']} мин\n"
        f"⏸ Буфер: {s['buffer_time']} мин\n"
        f"📆 Дни: {', '.join(days)}\n"
        f"🕐 Время: {str(s['start_time'])[:5]} — {str(s['end_time'])[:5]}\n"
        f"🎥 Платформа: {s['platform']}\n"
    )
    if s.get("description"):
        text += f"\n📝 {s['description']}"

    await cb.message.edit_text(
        text,
        reply_markup=kb_schedule_actions(schedule_id),
        parse_mode=ParseMode.HTML,
    )
    await cb.answer()


@router.callback_query(F.data.startswith("share_"))
async def cb_share_schedule(cb: CallbackQuery):
    schedule_id = cb.data.split("_", 1)[1]
    link = direct_link(schedule_id)
    msg = format_share_message_html(schedule_id)

    await cb.message.answer(
        f"🔗 <b>Ссылка для записи:</b>\n\n"
        f"<code>{link}</code>\n\n"
        f"Перешли следующее сообщение клиентам 👇",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_back_main,
    )
    await cb.message.answer(msg, parse_mode=ParseMode.HTML)
    await cb.answer()


@router.callback_query(F.data.startswith("del_"))
async def cb_delete_schedule(cb: CallbackQuery):
    schedule_id = cb.data.split("_", 1)[1]
    result = await api("delete", f"/api/schedules/{schedule_id}?telegram_id={cb.from_user.id}")

    if result:
        await cb.message.edit_text("✅ Расписание удалено.", reply_markup=kb_back_main)
    else:
        await cb.answer("Не удалось удалить", show_alert=True)
