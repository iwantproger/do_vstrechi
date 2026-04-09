"""Фоновый цикл напоминаний v2."""
import asyncio
import logging

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from api import api
from formatters import format_dt

log = logging.getLogger(__name__)

_REMINDER_LABEL = {
    "1440": "📅 Встреча завтра!",
    "60":   "⏰ Через 1 час встреча!",
    "30":   "🔔 Через 30 минут встреча!",
    "15":   "🔔 Через 15 минут встреча!",
    "5":    "⚡ Встреча через 5 минут!",
}


def _reminder_label(reminder_min: str) -> str:
    if reminder_min in _REMINDER_LABEL:
        return _REMINDER_LABEL[reminder_min]
    return f"⏰ Напоминание за {reminder_min} мин!"


async def send_reminder(bot: Bot, booking: dict, reminder_min: str):
    """Отправить напоминание организатору И участнику, записать в sent_reminders."""
    org_tz   = booking.get("organizer_timezone") or "UTC"
    time_str = format_dt(str(booking["scheduled_time"]), tz=org_tz)
    label    = _reminder_label(str(reminder_min))

    base = (
        f"{label}\n\n"
        f"📋 {booking['schedule_title']}\n"
        f"📅 {time_str}\n"
        f"⏱ {booking.get('duration', 60)} мин\n"
    )
    if booking.get("meeting_link") and booking.get("platform") in ("jitsi", "zoom", "google_meet"):
        base += f"🔗 <a href=\"{booking['meeting_link']}\">Подключиться</a>\n"

    guest_tid = booking.get("guest_telegram_id")
    if guest_tid:
        try:
            await bot.send_message(
                guest_tid,
                base + f"\n👤 Организатор: {booking.get('organizer_name', 'N/A')}",
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        except Exception as e:
            log.warning(f"Reminder to guest {guest_tid} failed: {e}")

    org_tid = booking.get("organizer_telegram_id")
    if org_tid:
        try:
            await bot.send_message(
                org_tid,
                base + f"\n👤 Гость: {booking['guest_name']} ({booking.get('guest_contact', '')})",
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        except Exception as e:
            log.warning(f"Reminder to organizer {org_tid} failed: {e}")

    await api("post", "/api/sent-reminders", json={
        "booking_id":    str(booking.get("booking_id") or booking.get("id")),
        "reminder_type": str(reminder_min),
    })


async def send_confirmation_request(bot: Bot, booking: dict):
    """Отправить участнику запрос 'Встреча в силе?' утром в день встречи."""
    guest_tid = booking.get("guest_telegram_id")
    if not guest_tid:
        return

    org_tz   = booking.get("organizer_timezone") or "UTC"
    time_str = format_dt(str(booking["scheduled_time"]), tz=org_tz)
    bid      = str(booking.get("id") or booking.get("booking_id"))

    text = (
        f"👋 <b>Напоминание о встрече сегодня!</b>\n\n"
        f"📋 {booking['schedule_title']}\n"
        f"📅 {time_str}\n"
        f"⏱ {booking.get('duration', 60)} мин\n\n"
        f"Встреча в силе?"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Да, всё в силе", callback_data=f"guest_confirm_{bid}"),
        InlineKeyboardButton(text="❌ Отменить",        callback_data=f"guest_cancel_{bid}"),
    ]])

    try:
        await bot.send_message(guest_tid, text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
        await api("post", "/api/sent-reminders", json={
            "booking_id":    bid,
            "reminder_type": "confirmation_request",
        })
    except Exception as e:
        log.warning(f"Confirmation request to {guest_tid} failed: {e}")


async def reminder_loop(bot: Bot):
    """Проверять напоминания каждые 60 секунд (v2: по настройкам пользователя)."""
    await asyncio.sleep(10)
    log.info("Reminder loop v2 started (1-min cycle)")
    _conf_tick = 0
    while True:
        try:
            # 1. Пользовательские напоминания по настройкам
            resp = await api("get", "/api/bookings/pending-reminders-v2")
            if resp and resp.get("reminders"):
                for r in resp["reminders"]:
                    await send_reminder(bot, r, str(r.get("reminder_min", "")))
                    await asyncio.sleep(0.3)

            # 2. Утренние запросы подтверждения — каждые 5 мин
            _conf_tick += 1
            if _conf_tick >= 5:
                _conf_tick = 0
                resp2 = await api("get", "/api/bookings/confirmation-requests")
                if resp2 and resp2.get("bookings"):
                    for b in resp2["bookings"]:
                        await send_confirmation_request(bot, b)
                        await asyncio.sleep(0.3)

        except Exception as e:
            log.error(f"Reminder loop error: {e}")

        await asyncio.sleep(60)
