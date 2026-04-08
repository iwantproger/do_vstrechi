"""Фоновый цикл напоминаний."""
import asyncio
import logging

from aiogram import Bot
from aiogram.enums import ParseMode

from api import api
from formatters import format_dt

log = logging.getLogger(__name__)

# Типы напоминаний в порядке убывания временного интервала
_REMINDER_TYPES = ["morning", "24h", "1h", "15m", "5m"]

_PREFIX = {
    "morning": "🌅 Сегодня встреча!",
    "24h":     "📅 Встреча завтра!",
    "1h":      "⏰ Через 1 час встреча!",
    "15m":     "🔔 Встреча через 15 минут!",
    "5m":      "⚡ Встреча через 5 минут!",
}


async def send_reminder(bot: Bot, booking: dict, reminder_type: str):
    """Отправить отдельное напоминание организатору И участнику."""
    org_tz   = booking.get("organizer_timezone") or "UTC"
    time_str = format_dt(str(booking["scheduled_time"]), tz=org_tz)
    prefix   = _PREFIX.get(reminder_type, "⏰ Напоминание!")

    base_text = (
        f"{prefix}\n\n"
        f"📋 {booking['schedule_title']}\n"
        f"📅 {time_str}\n"
        f"⏱ {booking.get('duration', 60)} мин\n"
    )
    if booking.get("meeting_link"):
        base_text += f"🔗 <a href=\"{booking['meeting_link']}\">Подключиться</a>\n"

    guest_tid = booking.get("guest_telegram_id")
    if guest_tid:
        try:
            await bot.send_message(
                guest_tid,
                base_text + f"\n👤 Организатор: {booking.get('organizer_name', 'N/A')}",
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
                base_text + f"\n👤 Гость: {booking['guest_name']} ({booking.get('guest_contact', '')})",
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        except Exception as e:
            log.warning(f"Reminder to organizer {org_tid} failed: {e}")

    await api("patch", f"/api/bookings/{booking['id']}/reminder-sent?reminder_type={reminder_type}")


async def reminder_loop(bot: Bot):
    """Проверять напоминания каждые 60 секунд и отправлять."""
    await asyncio.sleep(10)
    log.info("Reminder loop started (60s interval)")
    while True:
        try:
            for rtype in _REMINDER_TYPES:
                response = await api(
                    "get",
                    f"/api/bookings/pending-reminders?reminder_type={rtype}",
                )
                if response and response.get("bookings"):
                    for b in response["bookings"]:
                        await send_reminder(bot, b, rtype)
                        await asyncio.sleep(0.3)
        except Exception as e:
            log.error(f"Reminder loop error: {e}")

        await asyncio.sleep(60)
