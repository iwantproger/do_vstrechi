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
        InlineKeyboardButton(text="✅ Да, буду!", callback_data=f"guest_confirm_{bid}"),
        InlineKeyboardButton(text="❌ Отменить",  callback_data=f"guest_cancel_{bid}"),
    ]])

    try:
        await bot.send_message(guest_tid, text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
        # Mark confirmation as asked on backend (sets confirmation_asked + confirmation_asked_at)
        await api("patch", f"/api/bookings/{bid}/confirmation-asked")
    except Exception as e:
        log.warning(f"Confirmation request to {guest_tid} failed: {e}")


async def send_pending_guest_notice(bot: Bot, booking: dict):
    """Сообщить участнику утром, что встреча ещё ожидает подтверждения организатора."""
    guest_tid = booking.get("guest_telegram_id")
    if not guest_tid:
        return

    org_tz   = booking.get("organizer_timezone") or "UTC"
    time_str = format_dt(str(booking["scheduled_time"]), tz=org_tz)
    bid      = str(booking.get("id") or booking.get("booking_id"))

    text = (
        f"⏳ <b>Ваша встреча сегодня ещё не подтверждена.</b>\n\n"
        f"📋 {booking['schedule_title']}\n"
        f"📅 {time_str}\n"
        f"⏱ {booking.get('duration', 60)} мин\n\n"
        "Ожидайте — мы уведомим вас, как только организатор подтвердит встречу."
    )

    try:
        await bot.send_message(guest_tid, text, parse_mode=ParseMode.HTML)
        # Mark confirmation_asked=TRUE so this notice isn't re-sent,
        # and so confirmation-requests won't send "still coming?" until organizer confirms
        # (confirm_booking resets confirmation_asked=FALSE, then loop picks it up)
        await api("patch", f"/api/bookings/{bid}/confirmation-asked")
    except Exception as e:
        log.warning(f"Pending guest notice to {guest_tid} failed: {e}")


async def send_morning_organizer_summary(bot: Bot, organizer: dict):
    """Отправить организатору сводку о встречах, ожидающих подтверждения сегодня."""
    org_tid  = organizer.get("organizer_telegram_id")
    org_tz   = organizer.get("organizer_timezone") or "UTC"
    bookings = organizer.get("bookings", [])
    if not org_tid or not bookings:
        return

    text_lines = ["📋 <b>Ожидают вашего подтверждения сегодня:</b>\n"]
    buttons = []

    for b in bookings:
        time_str = format_dt(str(b["scheduled_time"]), tz=org_tz)
        dur      = b.get("duration", 60)
        text_lines.append(
            f"👤 {b['guest_name']} — {time_str}, {b['schedule_title']} ({dur} мин)"
        )
        bid = b["id"]
        buttons.append([
            InlineKeyboardButton(
                text=f"✅ {b['guest_name']} {time_str}",
                callback_data=f"confirm_{bid}",
            ),
            InlineKeyboardButton(text="❌", callback_data=f"cancel_{bid}"),
        ])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    try:
        await bot.send_message(
            org_tid,
            "\n".join(text_lines),
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )
        # Mark that summary was sent today (prevents re-sending in same day)
        await api("patch", f"/api/users/{org_tid}/morning-summary-sent")
    except Exception as e:
        log.warning(f"Morning organizer summary to {org_tid} failed: {e}")


async def _reminder_tick(bot: Bot, state: dict) -> None:
    """One iteration of the reminder loop. Raises on errors so outer loop can back off."""
    # 1. Пользовательские напоминания по настройкам
    resp = await api("get", "/api/bookings/pending-reminders-v2")
    if resp and resp.get("reminders"):
        for r in resp["reminders"]:
            await send_reminder(bot, r, str(r.get("reminder_min", "")))
            await asyncio.sleep(0.3)

    # 2. Утренние проверки — каждые 5 мин
    state["conf_tick"] += 1
    if state["conf_tick"] >= 5:
        state["conf_tick"] = 0

        resp2 = await api("get", "/api/bookings/confirmation-requests")
        if resp2 and resp2.get("bookings"):
            for b in resp2["bookings"]:
                await send_confirmation_request(bot, b)
                await asyncio.sleep(0.3)

        resp_pending = await api("get", "/api/bookings/morning-pending-guest-notice")
        if resp_pending and resp_pending.get("bookings"):
            for b in resp_pending["bookings"]:
                await send_pending_guest_notice(bot, b)
                await asyncio.sleep(0.3)

        resp_org = await api("get", "/api/bookings/morning-organizer-summary")
        if resp_org and resp_org.get("organizers"):
            for org in resp_org["organizers"]:
                await send_morning_organizer_summary(bot, org)
                await asyncio.sleep(0.3)

        resp3 = await api("get", "/api/bookings/no-answer-candidates")
        if resp3 and resp3.get("bookings"):
            for b in resp3["bookings"]:
                bid = str(b.get("id", ""))
                await api("patch", f"/api/bookings/{bid}/set-no-answer")
                await asyncio.sleep(0.3)

    # 3. Автозавершение прошедших встреч — каждые 15 мин
    state["complete_tick"] += 1
    if state["complete_tick"] >= 15:
        state["complete_tick"] = 0
        resp_c = await api("post", "/api/bookings/complete-past")
        if resp_c and resp_c.get("completed", 0) > 0:
            log.info(f"Auto-completed {resp_c['completed']} past bookings")


async def reminder_loop(bot: Bot):
    """Robust reminder loop: exponential backoff on errors, heartbeat log, clean cancel."""
    await asyncio.sleep(10)
    log.info("Reminder loop v2 started (1-min cycle)")

    state = {"conf_tick": 0, "complete_tick": 0}
    consecutive_errors = 0
    backoff = 60
    BACKOFF_MAX = 300
    heartbeat_counter = 0
    HEARTBEAT_EVERY = 30  # ~30 минут при нормальном 60-сек цикле

    try:
        while True:
            try:
                await _reminder_tick(bot, state)
                consecutive_errors = 0
                backoff = 60

                heartbeat_counter += 1
                if heartbeat_counter >= HEARTBEAT_EVERY:
                    heartbeat_counter = 0
                    log.info("reminder_loop alive")

                await asyncio.sleep(60)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                consecutive_errors += 1
                if consecutive_errors >= 5:
                    log.critical(
                        f"reminder_loop: {consecutive_errors} consecutive errors, "
                        f"latest: {e}"
                    )
                else:
                    log.error(f"reminder_loop error ({consecutive_errors}): {e}")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, BACKOFF_MAX)
    except asyncio.CancelledError:
        log.info("reminder_loop_cancelled")
        raise
