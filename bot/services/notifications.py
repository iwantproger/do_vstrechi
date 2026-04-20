"""Внутренний HTTP-сервер для приёма уведомлений от backend."""
import asyncio
import hmac
import logging
from datetime import datetime, timezone

from aiohttp import web
from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import (
    TelegramForbiddenError,
    TelegramRetryAfter,
    TelegramAPIError,
)
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

from config import INTERNAL_API_KEY, MINI_APP_URL
from formatters import format_dt

log = logging.getLogger(__name__)


async def _safe_send(bot: Bot, chat_id: int, text: str, **kwargs) -> bool:
    """Send message with graceful handling of 403/429/timeout. Returns True on success."""
    try:
        await asyncio.wait_for(
            bot.send_message(chat_id=chat_id, text=text, **kwargs),
            timeout=10,
        )
        return True
    except asyncio.TimeoutError:
        log.error(f"send_message timeout for chat {chat_id}")
        return False
    except TelegramForbiddenError:
        log.warning(f"Bot blocked by user {chat_id}, skipping")
        return False
    except TelegramRetryAfter as e:
        wait = getattr(e, "retry_after", 5)
        log.warning(f"Rate limited on chat {chat_id}, sleeping {wait}s and retrying once")
        try:
            await asyncio.sleep(wait)
            await asyncio.wait_for(
                bot.send_message(chat_id=chat_id, text=text, **kwargs),
                timeout=10,
            )
            return True
        except Exception as e2:
            log.error(f"Retry after rate-limit failed for {chat_id}: {e2}")
            return False
    except TelegramAPIError as e:
        log.error(f"Telegram API error for {chat_id}: {e}")
        return False
    except Exception as e:
        log.error(f"Unexpected send error for {chat_id}: {e}")
        return False


async def handle_new_booking(request: web.Request) -> web.Response:
    """Receive booking notification from backend and message the organizer."""
    key = request.headers.get("X-Internal-Key", "")
    if not INTERNAL_API_KEY or not hmac.compare_digest(key, INTERNAL_API_KEY):
        return web.json_response({"error": "unauthorized"}, status=401)

    try:
        payload = await request.json()
    except Exception:
        return web.json_response({"error": "invalid json"}, status=400)

    bot: Bot = request.app["bot"]
    organizer_tid = payload.get("organizer_telegram_id")
    if not organizer_tid:
        return web.json_response({"error": "missing data"}, status=400)

    try:
        from messages import TPL_NEW_BOOKING_ORG, TPL_NEW_BOOKING_GUEST, maybe_link_html
        from keyboards import kb_meeting_actions

        org_tz         = payload.get("organizer_timezone") or "UTC"
        guest_tz       = payload.get("guest_timezone") or org_tz
        dt_org         = format_dt(payload.get("scheduled_time", ""), tz=org_tz)
        dt_guest       = format_dt(payload.get("scheduled_time", ""), tz=guest_tz) if guest_tz != org_tz else dt_org
        schedule_title = payload.get("schedule_title", "Встреча")
        guest_name     = payload.get("guest_name", "—")
        guest_contact  = payload.get("guest_contact", "—")
        meeting_link   = payload.get("meeting_link", "")
        booking_id     = payload.get("booking_id", "")
        platform       = payload.get("platform", "")

        ml = maybe_link_html(meeting_link, platform)
        org_text = TPL_NEW_BOOKING_ORG.format(
            guest_name=guest_name, dt=dt_org, schedule_title=schedule_title,
            guest_contact=guest_contact, maybe_link=ml,
        )

        requires_confirm = payload.get("requires_confirmation", True)
        if requires_confirm:
            org_kb = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm_{booking_id}"),
                    InlineKeyboardButton(text="❌ Отклонить",  callback_data=f"cancel_{booking_id}"),
                ],
                [InlineKeyboardButton(text="📱 Открыть в приложении", web_app=WebAppInfo(url=MINI_APP_URL))],
            ])
        else:
            org_text += "\n\n✅ <i>Автоматически подтверждено</i>"
            org_kb = kb_meeting_actions(meeting_link, platform)

        org_booking_notif = payload.get("org_booking_notif", True)
        if org_booking_notif:
            await _safe_send(
                bot, organizer_tid, org_text,
                parse_mode=ParseMode.HTML,
                reply_markup=org_kb,
                disable_web_page_preview=True,
            )

        guest_tid = payload.get("guest_telegram_id")
        guest_booking_notif = payload.get("guest_booking_notif", True)
        if guest_tid and guest_booking_notif:
            conf_note = "\n⏳ Ожидайте подтверждения от организатора." if requires_confirm else ""
            guest_text = TPL_NEW_BOOKING_GUEST.format(
                schedule_title=schedule_title, dt=dt_guest,
                maybe_link=ml, confirmation_note=conf_note,
            )
            guest_kb = kb_meeting_actions(meeting_link, platform, include_connect=False)

            await _safe_send(
                bot, guest_tid, guest_text,
                parse_mode=ParseMode.HTML,
                reply_markup=guest_kb,
                disable_web_page_preview=True,
            )

        return web.json_response({"ok": True})

    except Exception as e:
        log.error(f"Failed to send notification: {e}")
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_status_change(request: web.Request) -> web.Response:
    """Receive booking status-change notification from backend."""
    key = request.headers.get("X-Internal-Key", "")
    if not INTERNAL_API_KEY or not hmac.compare_digest(key, INTERNAL_API_KEY):
        return web.json_response({"error": "unauthorized"}, status=401)

    try:
        payload = await request.json()
    except Exception:
        return web.json_response({"error": "invalid json"}, status=400)

    from messages import (
        TPL_CONFIRMED, TPL_CANCELLED_BY_ORG, TPL_CANCELLED_BY_GUEST,
        TPL_GUEST_CONFIRMED, TPL_NO_ANSWER, maybe_link_html,
    )
    from keyboards import kb_meeting_actions

    bot: Bot = request.app["bot"]
    new_status     = payload.get("new_status", "")
    initiator_tid  = payload.get("initiator_telegram_id")
    organizer_tid  = payload.get("organizer_telegram_id")
    guest_tid      = payload.get("guest_telegram_id")
    guest_name     = payload.get("guest_name", "—")
    schedule_title = payload.get("schedule_title", "Встреча")
    org_tz         = payload.get("organizer_timezone") or "UTC"
    guest_tz       = payload.get("guest_timezone") or org_tz
    dt_org         = format_dt(payload.get("scheduled_time", ""), tz=org_tz)
    dt_guest       = format_dt(payload.get("scheduled_time", ""), tz=guest_tz) if guest_tz != org_tz else dt_org
    meeting_link   = payload.get("meeting_link", "")
    platform       = payload.get("platform", "")
    ml = maybe_link_html(meeting_link, platform)

    try:
        if new_status == "confirmed":
            if guest_tid:
                text = TPL_CONFIRMED.format(schedule_title=schedule_title, dt=dt_guest, maybe_link=ml)
                kb = kb_meeting_actions(meeting_link, platform)
                await _safe_send(bot, guest_tid, text, parse_mode=ParseMode.HTML,
                                 reply_markup=kb, disable_web_page_preview=True)

        elif new_status == "cancelled":
            if initiator_tid == organizer_tid:
                if guest_tid:
                    text = TPL_CANCELLED_BY_ORG.format(schedule_title=schedule_title, dt=dt_guest)
                    kb = kb_meeting_actions(include_connect=False)
                    await _safe_send(bot, guest_tid, text, parse_mode=ParseMode.HTML, reply_markup=kb)
            else:
                if organizer_tid:
                    text = TPL_CANCELLED_BY_GUEST.format(guest_name=guest_name, schedule_title=schedule_title, dt=dt_org)
                    kb = kb_meeting_actions(include_connect=False)
                    await _safe_send(bot, organizer_tid, text, parse_mode=ParseMode.HTML, reply_markup=kb)

        elif new_status == "guest_confirmed":
            if organizer_tid:
                text = TPL_GUEST_CONFIRMED.format(guest_name=guest_name, schedule_title=schedule_title, dt=dt_org)
                kb = kb_meeting_actions(meeting_link, platform)
                await _safe_send(bot, organizer_tid, text, parse_mode=ParseMode.HTML, reply_markup=kb)

        elif new_status == "no_answer":
            if organizer_tid:
                text = TPL_NO_ANSWER.format(guest_name=guest_name, schedule_title=schedule_title, dt=dt_org)
                kb = kb_meeting_actions(include_connect=False)
                await _safe_send(bot, organizer_tid, text, parse_mode=ParseMode.HTML, reply_markup=kb)

        return web.json_response({"ok": True})

    except Exception as e:
        log.error(f"Status-change notification failed: {e}")
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_late_booking(request: web.Request) -> web.Response:
    """Instant-напоминание при бронировании близкой встречи (late booking)."""
    key = request.headers.get("X-Internal-Key", "")
    if not INTERNAL_API_KEY or not hmac.compare_digest(key, INTERNAL_API_KEY):
        return web.json_response({"error": "unauthorized"}, status=401)

    try:
        payload = await request.json()
    except Exception:
        return web.json_response({"error": "invalid json"}, status=400)

    from messages import TPL_LATE_BOOKING, maybe_link_html
    from keyboards import kb_meeting_actions

    bot: Bot = request.app["bot"]
    recipient_tid = payload.get("recipient_telegram_id")
    if not recipient_tid:
        return web.json_response({"error": "missing recipient"}, status=400)

    try:
        tz = payload.get("recipient_tz") or "UTC"
        dt = format_dt(payload.get("scheduled_time", ""), tz=tz)
        title = payload.get("schedule_title", "Встреча")
        time_left = payload.get("time_until_min", 0)
        meeting_link = payload.get("meeting_link", "")
        platform = payload.get("platform", "")
        duration = payload.get("duration", 60)

        if time_left >= 60:
            time_label = f"{time_left // 60} ч {time_left % 60} мин" if time_left % 60 else f"{time_left // 60} ч"
        else:
            time_label = f"{time_left} мин"

        ml = maybe_link_html(meeting_link, platform)
        text = TPL_LATE_BOOKING.format(
            schedule_title=title, dt=dt, duration=duration,
            time_label=time_label, maybe_link=ml,
        )
        kb = kb_meeting_actions(meeting_link, platform)

        await _safe_send(bot, recipient_tid, text, parse_mode=ParseMode.HTML,
                         reply_markup=kb, disable_web_page_preview=True)
        log.info(f"Late booking notification sent to {recipient_tid}")
        return web.json_response({"ok": True})

    except Exception as e:
        log.error(f"Late booking notification failed: {e}")
        return web.json_response({"ok": False, "error": str(e)}, status=500)


def register_internal_routes(webapp: web.Application, bot: Bot) -> None:
    """Register internal notification routes on an existing aiohttp app."""
    webapp["bot"] = bot
    webapp.router.add_post("/internal/notify",        handle_new_booking)
    webapp.router.add_post("/internal/status-change", handle_status_change)
    webapp.router.add_post("/internal/notify-late",   handle_late_booking)


async def start_internal_server(bot: Bot, port: int = 8080):
    """Start standalone aiohttp server for internal notifications (polling mode)."""
    webapp = web.Application()
    register_internal_routes(webapp, bot)
    runner = web.AppRunner(webapp)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    log.info(f"Internal notification server started on port {port}")
    return runner
