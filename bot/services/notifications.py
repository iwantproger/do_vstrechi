"""Внутренний HTTP-сервер для приёма уведомлений от backend."""
import hmac
import logging
from datetime import datetime, timezone

from aiohttp import web
from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

from config import INTERNAL_API_KEY, MINI_APP_URL
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
            org_text += "\n\n✅ <i>Автоматически подтверждено</i>"
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="📱 Открыть приложение", web_app=WebAppInfo(url=MINI_APP_URL)),
            ]])

        await bot.send_message(
            chat_id=organizer_tid,
            text=org_text,
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
            disable_web_page_preview=True,
        )

        guest_tid = payload.get("guest_telegram_id")
        if guest_tid:
            # Calculate hours until meeting for reminder text
            try:
                scheduled_dt = datetime.fromisoformat(
                    payload.get("scheduled_time", "").replace("Z", "+00:00")
                )
                hours_until = (scheduled_dt - datetime.now(timezone.utc)).total_seconds() / 3600
            except Exception:
                hours_until = 999

            guest_text = (
                "✅ <b>Вы записались!</b>\n\n"
                f"📋 {schedule_title}\n"
                f"📅 {dt}\n"
            )
            if meeting_link:
                guest_text += f"🔗 <a href='{meeting_link}'>Ссылка на встречу</a>\n"
            guest_text += "\n⏳ Ожидайте подтверждения от организатора.\n"

            if hours_until > 24:
                guest_text += "\n🔔 Мы напомним вам о встрече за 24 часа и за 1 час.\n"
            elif hours_until > 1:
                guest_text += "\n🔔 Мы напомним вам о встрече за 1 час.\n"

            guest_text += "\n💡 Здесь вы будете получать напоминания и обновления по этой встрече."

            # Inline buttons for guest
            guest_buttons = []
            if booking_id:
                notify_url = f"https://t.me/do_vstrechi_bot?start=notify_{booking_id}"
                guest_buttons.append([
                    InlineKeyboardButton(text="🔔 Настроить уведомления", url=notify_url)
                ])
            guest_buttons.append([
                InlineKeyboardButton(text="📅 Принимать записи самому →", callback_data="how_it_works")
            ])
            guest_kb = InlineKeyboardMarkup(inline_keyboard=guest_buttons)

            await bot.send_message(
                chat_id=guest_tid,
                text=guest_text,
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

        elif new_status == "guest_confirmed":
            # Guest pressed "Да, буду!" → notify organizer
            if organizer_tid:
                text = (
                    f"✅ <b>{guest_name} подтвердил(а) встречу!</b>\n\n"
                    f"📋 {schedule_title}\n"
                    f"📅 {dt}"
                )
                await bot.send_message(organizer_tid, text, parse_mode=ParseMode.HTML)

        elif new_status == "no_answer":
            # Guest didn't respond to morning confirmation → notify organizer
            if organizer_tid:
                text = (
                    f"⚠️ <b>{guest_name} не подтвердил(а) встречу</b>\n\n"
                    f"📋 {schedule_title}\n"
                    f"📅 {dt}\n\n"
                    "Участник не ответил на утреннее подтверждение."
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
