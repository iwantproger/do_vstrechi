"""Внутренний HTTP-сервер для приёма уведомлений от backend."""
import hmac
import logging

from aiohttp import web
from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import INTERNAL_API_KEY
from formatters import format_dt

log = logging.getLogger(__name__)


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
        org_tz         = payload.get("organizer_timezone") or "UTC"
        dt             = format_dt(payload.get("scheduled_time", ""), tz=org_tz)
        schedule_title = payload.get("schedule_title", "Встреча")
        guest_name     = payload.get("guest_name", "—")
        guest_contact  = payload.get("guest_contact", "—")
        meeting_link   = payload.get("meeting_link", "")
        booking_id     = payload.get("booking_id", "")

        org_text = (
            "🔔 <b>Новая запись!</b>\n\n"
            f"👤 {guest_name}\n"
            f"📅 {dt}\n"
            f"📋 {schedule_title}\n"
            f"📞 {guest_contact}"
        )
        if meeting_link:
            org_text += f"\n🔗 <a href='{meeting_link}'>Ссылка на встречу</a>"

        requires_confirm = payload.get("requires_confirmation", True)
        if requires_confirm:
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm_{booking_id}"),
                InlineKeyboardButton(text="❌ Отклонить",  callback_data=f"cancel_{booking_id}"),
            ]])
        else:
            kb = None
            org_text += "\n\n✅ <i>Автоматически подтверждено</i>"

        await bot.send_message(
            chat_id=organizer_tid,
            text=org_text,
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
            disable_web_page_preview=True,
        )

        guest_tid = payload.get("guest_telegram_id")
        if guest_tid:
            guest_text = (
                "✅ <b>Вы записались!</b>\n\n"
                f"📋 {schedule_title}\n"
                f"📅 {dt}\n"
            )
            if meeting_link:
                guest_text += f"🔗 <a href='{meeting_link}'>Ссылка на встречу</a>\n"
            guest_text += "\nОжидайте подтверждения от организатора."

            await bot.send_message(
                chat_id=guest_tid,
                text=guest_text,
                parse_mode=ParseMode.HTML,
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

    bot: Bot = request.app["bot"]
    new_status     = payload.get("new_status", "")
    initiator_tid  = payload.get("initiator_telegram_id")
    organizer_tid  = payload.get("organizer_telegram_id")
    guest_tid      = payload.get("guest_telegram_id")
    guest_name     = payload.get("guest_name", "—")
    schedule_title = payload.get("schedule_title", "Встреча")
    org_tz         = payload.get("organizer_timezone") or "UTC"
    dt             = format_dt(payload.get("scheduled_time", ""), tz=org_tz)
    meeting_link   = payload.get("meeting_link", "")

    try:
        if new_status == "confirmed":
            if guest_tid:
                text = (
                    "✅ <b>Встреча подтверждена!</b>\n\n"
                    f"📋 {schedule_title}\n"
                    f"📅 {dt}\n"
                )
                if meeting_link:
                    text += f"🔗 <a href='{meeting_link}'>Ссылка на встречу</a>"
                await bot.send_message(
                    guest_tid, text,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )

        elif new_status == "cancelled":
            if initiator_tid == organizer_tid:
                # Organizer cancelled → notify guest
                if guest_tid:
                    text = (
                        "🚫 <b>Встреча отменена организатором.</b>\n\n"
                        f"📋 {schedule_title}\n"
                        f"📅 {dt}"
                    )
                    await bot.send_message(guest_tid, text, parse_mode=ParseMode.HTML)
            else:
                # Guest cancelled → notify organizer
                if organizer_tid:
                    text = (
                        "🚫 <b>Отмена встречи.</b>\n\n"
                        f"👤 {guest_name} отменил(а) запись.\n"
                        f"📋 {schedule_title}\n"
                        f"📅 {dt}"
                    )
                    await bot.send_message(organizer_tid, text, parse_mode=ParseMode.HTML)

        return web.json_response({"ok": True})

    except Exception as e:
        log.error(f"Status-change notification failed: {e}")
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def start_internal_server(bot: Bot):
    """Start aiohttp server on :8080 for internal notifications."""
    webapp = web.Application()
    webapp["bot"] = bot
    webapp.router.add_post("/internal/notify",        handle_new_booking)
    webapp.router.add_post("/internal/status-change", handle_status_change)
    runner = web.AppRunner(webapp)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()
    log.info("Internal notification server started on port 8080")
    return runner
