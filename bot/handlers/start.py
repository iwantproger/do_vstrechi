"""Handlers: /start, /help, reply-keyboard buttons, notify deep link."""
import logging

from aiogram import Router, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.filters.command import CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo,
)

from api import api
from config import MINI_APP_URL
from keyboards import get_main_keyboard, kb_back_main
from formatters import STATUS_EMOJI, format_dt
from states import CreateSchedule

log = logging.getLogger(__name__)
router = Router()


@router.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext, command: CommandObject):
    await state.clear()
    user = msg.from_user
    args = command.args or ""
    log.info(f"User {user.id} started bot, args={args}")

    # Deep link: notify_BOOKING_ID — настройка уведомлений после бронирования
    if args.startswith("notify_"):
        booking_id = args[len("notify_"):]
        await handle_notify_setup(msg, booking_id)
        return

    try:
        from aiogram.types import MenuButtonWebApp
        await msg.bot.set_chat_menu_button(
            chat_id=msg.chat.id,
            menu_button=MenuButtonWebApp(
                text="Открыть",
                web_app=WebAppInfo(url=MINI_APP_URL),
            )
        )
        log.info(f"Menu button updated for user {user.id}")
    except Exception as e:
        log.warning(f"Could not set menu button for user {user.id}: {e}")

    await api("post", f"/api/users/auth?telegram_id={user.id}", json={
        "username":   user.username,
        "first_name": user.first_name,
        "last_name":  user.last_name,
    })

    await msg.answer(
        f"👋 Привет, <b>{user.first_name}</b>!\n\n"
        "Я помогу тебе управлять встречами:\n"
        "• создавать расписания\n"
        "• принимать бронирования\n"
        "• отправлять ссылки клиентам\n\n"
        "Выбери действие:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard(),
    )

    inline_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="🌐 Открыть приложение",
            web_app=WebAppInfo(url=MINI_APP_URL),
        )
    ]])
    await msg.answer("👇 Или открой приложение:", reply_markup=inline_kb)


@router.message(Command("help"))
async def cmd_help(msg: Message):
    await msg.answer(
        "📖 <b>Как пользоваться ботом</b>\n\n"
        "1. Создай расписание — укажи название, длительность и рабочие часы\n"
        "2. Отправь ссылку клиентам — они выберут удобное время\n"
        "3. Получи уведомление о бронировании\n"
        "4. Подтверди или отмени встречу\n\n"
        "<b>Команды:</b>\n"
        "/start — главное меню\n"
        "/help — эта справка\n",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_back_main(),
    )


# ── Reply-кнопки нижней панели ────────────────────────────

@router.message(F.text == "📅 Создать расписание")
async def reply_create_schedule(msg: Message, state: FSMContext):
    await state.clear()
    await state.set_state(CreateSchedule.title)
    await msg.answer(
        "➕ <b>Создание нового расписания</b>\n\n"
        "Шаг 1/5: Введи название расписания.\n"
        "Например: <i>Консультация по маркетингу</i>",
        parse_mode=ParseMode.HTML,
    )


@router.message(F.text == "📋 Мои расписания")
async def reply_my_schedules(msg: Message):
    schedules = await api("get", f"/api/schedules?telegram_id={msg.from_user.id}")

    if not schedules:
        await msg.answer(
            "У тебя пока нет расписаний.\n\nСоздай первое!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Создать", callback_data="create_schedule")],
            ])
        )
        return

    buttons = [
        [InlineKeyboardButton(
            text=f"📅 {s['title']} ({s['duration']} мин)",
            callback_data=f"schedule_{s['id']}",
        )]
        for s in schedules
    ]
    buttons.append([InlineKeyboardButton(text="➕ Создать новое", callback_data="create_schedule")])
    await msg.answer(
        f"📋 Твои расписания ({len(schedules)}):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.message(F.text == "👥 Мои встречи")
async def reply_my_bookings(msg: Message):
    bookings = await api("get", f"/api/bookings?telegram_id={msg.from_user.id}")

    if not bookings:
        await msg.answer("У тебя пока нет встреч.")
        return

    buttons = []
    for b in bookings[:10]:
        emoji = STATUS_EMOJI.get(b["status"], "?")
        dt    = format_dt(b["scheduled_time"], tz=b.get("organizer_timezone") or "UTC")
        role  = "📌" if b.get("my_role") == "organizer" else "👤"
        buttons.append([InlineKeyboardButton(
            text=f"{role}{emoji} {b.get('schedule_title','?')} · {dt}",
            callback_data=f"booking_{b['id']}",
        )])

    await msg.answer(
        f"📋 <b>Твои встречи ({len(bookings)})</b>\n"
        f"📌 = организатор, 👤 = гость",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode=ParseMode.HTML,
    )


@router.message(F.text == "❓ Помощь")
async def reply_help(msg: Message):
    await cmd_help(msg)


# ── Deep link: notify setup ────────────────────────────

async def handle_notify_setup(msg: Message, booking_id: str):
    """Настройка уведомлений после бронирования гостем."""
    booking = await api("get", f"/api/bookings/{booking_id}")

    if booking and isinstance(booking, dict):
        title = booking.get("schedule_title", "встречу")
        scheduled = booking.get("scheduled_time", "")
        date_str = scheduled[:10] if scheduled else "—"
        text = (
            f"🔔 <b>Уведомления включены!</b>\n\n"
            f"Встреча: <b>{title}</b>\n"
            f"Дата: {date_str}\n\n"
            f"Напомним вам:\n"
            f"• За 24 часа до встречи\n"
            f"• За 1 час до встречи\n\n"
            f"Хотите настроить напоминания подробнее?"
        )
    else:
        text = (
            "🔔 <b>Уведомления включены!</b>\n\n"
            "Напомним вам:\n"
            "• За 24 часа до встречи\n"
            "• За 1 час до встречи\n\n"
            "Хотите настроить напоминания подробнее?"
        )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="⏰ Добавить за 30 минут",
            callback_data=f"remind_30m_{booking_id}",
        )],
        [InlineKeyboardButton(
            text="⏰ Добавить за 15 минут",
            callback_data=f"remind_15m_{booking_id}",
        )],
        [InlineKeyboardButton(
            text="📱 Настроить в приложении",
            web_app=WebAppInfo(url=MINI_APP_URL),
        )],
    ])

    await msg.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


@router.callback_query(F.data.startswith("remind_"))
async def cb_remind_setup(callback: CallbackQuery):
    """Заглушка: настройка дополнительных напоминаний."""
    parts = callback.data.split("_")  # remind_30m_BOOKING_ID
    interval = parts[1] if len(parts) > 1 else ""

    interval_text = {
        "30m": "30 минут",
        "15m": "15 минут",
        "5m": "5 минут",
    }.get(interval, interval)

    await callback.answer(f"✅ Напоминание за {interval_text} добавлено!")
    # TODO: сохранить в БД через API
