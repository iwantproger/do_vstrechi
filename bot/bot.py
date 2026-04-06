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

from config import BOT_TOKEN, MINI_APP_URL
from handlers import start, navigation, schedules, bookings, create
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
    dp  = Dispatcher(storage=MemoryStorage())

    dp.include_router(start.router)
    dp.include_router(navigation.router)
    dp.include_router(schedules.router)
    dp.include_router(bookings.router)
    dp.include_router(create.router)

    await setup_bot_commands(bot)

    asyncio.create_task(reminder_loop(bot))
    runner = await start_internal_server(bot)

    log.info("Bot starting…")
    try:
        await dp.start_polling(bot, skip_updates=True)
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
