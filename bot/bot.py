"""
До встречи — Telegram Bot
aiogram 3.x + FastAPI backend
Supports webhook mode (WEBHOOK_ENABLED=true) with polling fallback.
"""
import asyncio
import logging

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, MenuButtonWebApp, WebAppInfo

from api import close_session
from config import (
    BOT_TOKEN, MINI_APP_URL, REDIS_URL,
    WEBHOOK_ENABLED, WEBHOOK_HOST, WEBHOOK_PATH, WEBHOOK_SECRET, BOT_PORT,
)
from handlers import start, navigation, schedules, bookings, create, inline, admin
from services.reminders import reminder_loop
from services.notifications import register_internal_routes, start_internal_server
from services.heartbeat import heartbeat_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


async def setup_bot_commands(bot: Bot):
    """Регистрирует команды и устанавливает Menu Button глобально."""
    commands = [
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="help",  description="Справка по боту"),
    ]
    await bot.set_my_commands(commands)
    try:
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="Открыть",
                web_app=WebAppInfo(url=MINI_APP_URL),
            )
        )
        log.info(f"Global menu button set: 'Открыть' → {MINI_APP_URL}")
    except Exception as e:
        log.warning(f"Could not set global menu button: {e}")
    log.info("Bot commands configured")


async def main():
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    # Redis storage если доступен, иначе memory
    if REDIS_URL:
        try:
            from aiogram.fsm.storage.redis import RedisStorage
            storage = RedisStorage.from_url(REDIS_URL)
            log.info(f"Using Redis FSM storage: {REDIS_URL}")
        except Exception as e:
            log.warning(f"Redis unavailable, falling back to memory: {e}")
            storage = MemoryStorage()
    else:
        storage = MemoryStorage()

    dp = Dispatcher(storage=storage)

    dp.include_router(admin.router)
    dp.include_router(start.router)
    dp.include_router(navigation.router)
    dp.include_router(schedules.router)
    dp.include_router(bookings.router)
    dp.include_router(create.router)
    dp.include_router(inline.router)

    me = await bot.get_me()
    log.info("Bot username: @%s", me.username)

    await setup_bot_commands(bot)

    reminder_task = asyncio.create_task(reminder_loop(bot))
    heartbeat_task = asyncio.create_task(heartbeat_loop())

    if WEBHOOK_ENABLED and WEBHOOK_HOST:
        # ═══════════════════════════════════════════
        #  WEBHOOK MODE
        # ═══════════════════════════════════════════
        log.info(f"Starting in WEBHOOK mode: {WEBHOOK_HOST}{WEBHOOK_PATH}")

        from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

        webapp = web.Application()
        register_internal_routes(webapp, bot)

        webhook_url = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

        await bot.delete_webhook(drop_pending_updates=True)
        await bot.set_webhook(
            url=webhook_url,
            secret_token=WEBHOOK_SECRET or None,
            drop_pending_updates=True,
        )
        log.info(f"Webhook set: {webhook_url}")

        handler = SimpleRequestHandler(
            dispatcher=dp,
            bot=bot,
            secret_token=WEBHOOK_SECRET or None,
        )
        handler.register(webapp, path=WEBHOOK_PATH)
        setup_application(webapp, dp, bot=bot)

        runner = web.AppRunner(webapp)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", BOT_PORT)
        await site.start()
        log.info(f"Bot webhook+internal server on port {BOT_PORT}")

        try:
            await asyncio.Event().wait()
        finally:
            reminder_task.cancel()
            try:
                await reminder_task
            except (asyncio.CancelledError, Exception):
                pass
            await bot.delete_webhook()
            await runner.cleanup()
            await close_session()
            log.info("Webhook bot stopped")

    else:
        # ═══════════════════════════════════════════
        #  POLLING MODE (fallback)
        # ═══════════════════════════════════════════
        log.info("Starting in POLLING mode")

        runner = await start_internal_server(bot, port=BOT_PORT)

        try:
            updates = await bot.get_updates(offset=-1, limit=1)
            if updates:
                log.info(f"Skipping ~{updates[-1].update_id} pending updates")
        except Exception:
            pass

        log.info("Bot starting…")
        try:
            await bot.delete_webhook(drop_pending_updates=True)
            await dp.start_polling(bot, skip_updates=True)
        finally:
            reminder_task.cancel()
            try:
                await reminder_task
            except (asyncio.CancelledError, Exception):
                pass
            await runner.cleanup()
            await close_session()
            log.info("Polling bot stopped")


if __name__ == "__main__":
    asyncio.run(main())
