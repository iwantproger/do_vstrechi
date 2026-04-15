"""Handlers: просмотр, подтверждение, отмена бронирований."""
import logging

from aiogram import Router, F
from aiogram.enums import ParseMode
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from api import api
from keyboards import kb_booking_actions
from formatters import format_booking

log = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data.startswith("booking_"))
async def cb_booking_detail(cb: CallbackQuery):
    booking_id = cb.data.split("_", 1)[1]
    booking = await api("get", f"/api/bookings/{booking_id}?telegram_id={cb.from_user.id}")

    if not booking:
        await cb.answer("Встреча не найдена", show_alert=True)
        return

    text = format_booking(booking, show_role=True)

    if booking.get("my_role") == "organizer":
        kb = kb_booking_actions(booking_id, booking["status"])
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить", callback_data=f"cancel_{booking_id}")],
            [InlineKeyboardButton(text="« Назад",    callback_data="my_bookings")],
        ])

    await cb.message.edit_text(
        text, reply_markup=kb,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )
    await cb.answer()


@router.callback_query(F.data.startswith("confirm_"))
async def cb_confirm_booking(cb: CallbackQuery):
    booking_id = cb.data.split("_", 1)[1]
    result = await api("patch", f"/api/bookings/{booking_id}/confirm?telegram_id={cb.from_user.id}")
    if result:
        await cb.message.edit_text(
            cb.message.text + "\n\n✅ <b>Подтверждено</b>",
            parse_mode=ParseMode.HTML,
        )
        await cb.answer("Встреча подтверждена!")
    else:
        await cb.answer("Не удалось подтвердить", show_alert=True)


@router.callback_query(F.data.startswith("cancel_"))
async def cb_cancel_booking(cb: CallbackQuery):
    booking_id = cb.data.split("_", 1)[1]
    result = await api("patch", f"/api/bookings/{booking_id}/cancel?telegram_id={cb.from_user.id}")
    if result:
        await cb.message.edit_text(
            cb.message.text + "\n\n❌ <b>Отклонено</b>",
            parse_mode=ParseMode.HTML,
        )
        await cb.answer("Встреча отменена")
    else:
        await cb.answer("Не удалось отменить", show_alert=True)


@router.callback_query(F.data.startswith("guest_confirm_"))
async def cb_guest_confirm(cb: CallbackQuery):
    """Участник подтверждает что встреча в силе (ответ на утренний вопрос)."""
    booking_id = cb.data.replace("guest_confirm_", "", 1)
    result = await api("patch", f"/api/bookings/{booking_id}/guest-confirm?telegram_id={cb.from_user.id}")
    try:
        await cb.message.edit_text(
            cb.message.text + "\n\n✅ <b>Отлично, ждём вас!</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=None,
        )
    except Exception:
        pass
    if result:
        await cb.answer("Встреча подтверждена! 🎉")
    else:
        await cb.answer("Не удалось подтвердить", show_alert=True)
    log.info(f"Guest {cb.from_user.id} confirmed booking {booking_id}")


@router.callback_query(F.data.startswith("guest_cancel_"))
async def cb_guest_cancel(cb: CallbackQuery):
    """Участник отменяет встречу через утреннее сообщение."""
    booking_id = cb.data.replace("guest_cancel_", "", 1)
    result = await api("patch", f"/api/bookings/{booking_id}/cancel?telegram_id={cb.from_user.id}")
    try:
        await cb.message.edit_text(
            cb.message.text + "\n\n❌ <b>Встреча отменена</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=None,
        )
    except Exception:
        pass
    if result:
        await cb.answer("Встреча отменена")
    else:
        await cb.answer("Не удалось отменить", show_alert=True)
