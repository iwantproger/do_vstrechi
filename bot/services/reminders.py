"""Фоновый цикл напоминаний."""
import asyncio
import logging

from aiogram import Bot
from aiogram.enums import ParseMode

from api import api
from formatters import format_dt

log = logging.getLogger(__name__)


async def send_reminder(bot: Bot, booking: dict, reminder_type: str):
    """Send reminder to guest and organizer."""
    org_tz   = booking.get("organizer_timezone") or "UTC"
    time_str = format_dt(booking["scheduled_time"], tz=org_tz)
    prefix   = "⏰ Напоминание!" if reminder_type == "1h" else "📅 Завтра встреча!"

    text = (
        f"{prefix}\n\n"
        f"📋 {booking['schedule_title']}\n"
        f"📅 {time_str}\n"
        f"⏱ {booking.get('duration', 60)} мин\n"
    )
    if booking.get("meeting_link"):
        text += f"🔗 <a href=\"{booking['meeting_link']}\">Подключиться</a>\n"

    guest_tid = booking.get("guest_telegram_id")
    if guest_tid:
        try:
            await bot.send_message(
                guest_tid,
                text + f"\n👤 Организатор: {booking.get('organizer_name', 'N/A')}",
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        except Exception as e:
            log.warning(f"Failed to send reminder to guest {guest_tid}: {e}")

    org_tid = booking.get("organizer_telegram_id")
    if org_tid:
        try:
            await bot.send_message(
                org_tid,
                text + f"\n👤 Гость: {booking['guest_name']} ({booking.get('guest_contact', '')})",
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        except Exception as e:
            log.warning(f"Failed to send reminder to organizer {org_tid}: {e}")

    await api("patch", f"/api/bookings/{booking['id']}/reminder-sent?reminder_type={reminder_type}")


async def reminder_loop(bot: Bot):
    """Check for pending reminders every 5 minutes and send them."""
    await asyncio.sleep(10)
    log.info("Reminder loop started")
    while True:
        try:
            for rtype in ("24h", "1h"):
                response = await api(
                    "get",
                    f"/api/bookings/pending-reminders?reminder_type={rtype}",
                )
                if response and response.get("bookings"):
                    for b in response["bookings"]:
                        await send_reminder(bot, b, rtype)
                        await asyncio.sleep(0.5)
        except Exception as e:
            log.error(f"Reminder loop error: {e}")

        await asyncio.sleep(300)
