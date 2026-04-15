"""
До встречи — Telegram Bot
aiogram 3.x + FastAPI backend
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, MenuButtonWebApp, WebAppInfo

from api import close_session
from config import BOT_TOKEN, MINI_APP_URL, REDIS_URL
from handlers import start, navigation, schedules, bookings, create, inline
from services.reminders import reminder_loop
from services.notifications import start_internal_server

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

    dp.include_router(start.router)
    dp.include_router(navigation.router)
    dp.include_router(schedules.router)
    dp.include_router(bookings.router)
    dp.include_router(create.router)
    dp.include_router(inline.router)

    await setup_bot_commands(bot)

    reminder_task = asyncio.create_task(reminder_loop(bot))
    runner = await start_internal_server(bot)

    try:
        updates = await bot.get_updates(offset=-1, limit=1)
        if updates:
            log.info(f"Skipping ~{updates[-1].update_id} pending updates")
    except Exception:
        pass

    log.info("Bot starting…")
    try:
        await dp.start_polling(bot, skip_updates=True)
    finally:
        reminder_task.cancel()
        try:
            await reminder_task
        except (asyncio.CancelledError, Exception):
            pass
        await runner.cleanup()
        await close_session()
        log.info("session closed")


if __name__ == "__main__":
    asyncio.run(main())
