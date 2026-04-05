"""
До встречи — Telegram Bot
aiogram 3.x + FastAPI backend
"""

import os
import hmac
import logging
import asyncio
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, WebAppInfo,
    BotCommand, MenuButtonWebApp
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

BOT_TOKEN        = os.environ["BOT_TOKEN"]
BACKEND_URL      = os.environ.get("BACKEND_API_URL", "http://backend:8000")
MINI_APP_URL     = os.environ.get("MINI_APP_URL", "https://YOUR_DOMAIN.ru")
INTERNAL_API_KEY = os.environ.get("INTERNAL_API_KEY", "")

_bot: Bot | None = None

# ─────────────────────────────────────────────────────────
# FSM States
# ─────────────────────────────────────────────────────────

class CreateSchedule(StatesGroup):
    title        = State()
    duration     = State()
    buffer_time  = State()
    work_days    = State()
    start_time   = State()
    end_time     = State()
    platform     = State()

# ─────────────────────────────────────────────────────────
# API helper
# ─────────────────────────────────────────────────────────

async def api(method: str, path: str, **kwargs) -> dict | list | None:
    url = f"{BACKEND_URL}{path}"
    headers = kwargs.pop("headers", {})
    if INTERNAL_API_KEY:
        headers["X-Internal-Key"] = INTERNAL_API_KEY
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with getattr(session, method)(url, headers=headers, **kwargs) as r:
                if r.status in (200, 201):
                    return await r.json()
                text = await r.text()
                log.error(f"API {method.upper()} {path} → {r.status}: {text}")
                return None
    except Exception as e:
        log.error(f"API error {path}: {e}")
        return None

# ─────────────────────────────────────────────────────────
# Keyboards
# ─────────────────────────────────────────────────────────

def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Main reply keyboard (persistent bottom panel)"""
    keyboard = [
        [KeyboardButton(text="📅 Создать расписание")],
        [
            KeyboardButton(text="📋 Мои расписания"),
            KeyboardButton(text="👥 Мои встречи")
        ],
        [KeyboardButton(text="❓ Помощь")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def kb_main(mini_app_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Открыть приложение", web_app=WebAppInfo(url=mini_app_url))],
        [InlineKeyboardButton(text="📅 Мои расписания", callback_data="my_schedules")],
        [InlineKeyboardButton(text="➕ Создать расписание", callback_data="create_schedule")],
        [InlineKeyboardButton(text="📋 Мои встречи", callback_data="my_bookings")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="stats")],
    ])

def kb_back_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="« Главное меню", callback_data="main_menu")]
    ])

def kb_duration() -> InlineKeyboardMarkup:
    buttons = []
    for d in [15, 30, 45, 60, 90, 120]:
        buttons.append(InlineKeyboardButton(text=f"{d} мин", callback_data=f"dur_{d}"))
    rows = [buttons[i:i+3] for i in range(0, len(buttons), 3)]
    rows.append([InlineKeyboardButton(text="« Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_buffer() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Без буфера", callback_data="buf_0"),
         InlineKeyboardButton(text="10 мин", callback_data="buf_10")],
        [InlineKeyboardButton(text="15 мин", callback_data="buf_15"),
         InlineKeyboardButton(text="30 мин", callback_data="buf_30")],
    ])

def kb_platform() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎥 Jitsi Meet (бесплатно)", callback_data="plat_jitsi")],
        [InlineKeyboardButton(text="🔗 Zoom", callback_data="plat_zoom")],
        [InlineKeyboardButton(text="📍 Офлайн / другое", callback_data="plat_other")],
    ])

def kb_schedule_actions(schedule_id: str, mini_app_url: str) -> InlineKeyboardMarkup:
    booking_url = f"{mini_app_url}?schedule_id={schedule_id}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Открыть страницу записи", web_app=WebAppInfo(url=booking_url))],
        [InlineKeyboardButton(text="🔗 Поделиться ссылкой", callback_data=f"share_{schedule_id}")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"del_{schedule_id}")],
        [InlineKeyboardButton(text="« Назад", callback_data="my_schedules")],
    ])

def kb_booking_actions(booking_id: str, status: str) -> InlineKeyboardMarkup:
    buttons = []
    if status == "pending":
        buttons.append([
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm_{booking_id}"),
            InlineKeyboardButton(text="❌ Отменить", callback_data=f"cancel_{booking_id}"),
        ])
    elif status == "confirmed":
        buttons.append([InlineKeyboardButton(text="❌ Отменить", callback_data=f"cancel_{booking_id}")])
    buttons.append([InlineKeyboardButton(text="« Назад", callback_data="my_bookings")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ─────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────

STATUS_EMOJI = {"pending": "⏳", "confirmed": "✅", "cancelled": "❌", "completed": "✓"}
STATUS_TEXT  = {"pending": "Ожидает", "confirmed": "Подтверждена", "cancelled": "Отменена", "completed": "Завершена"}
DAYS_RU      = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

def format_dt(dt_str: str, tz: str = "UTC") -> str:
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        local_dt = dt.astimezone(ZoneInfo(tz))
        return local_dt.strftime("%d.%m.%Y %H:%M")
    except Exception:
        return dt_str

def format_booking(b: dict, show_role: bool = False) -> str:
    emoji = STATUS_EMOJI.get(b["status"], "?")
    status = STATUS_TEXT.get(b["status"], b["status"])
    dt = format_dt(b["scheduled_time"])
    lines = [
        f"{emoji} <b>{b.get('schedule_title', 'Встреча')}</b>",
        f"🕐 {dt}",
        f"👤 {b['guest_name']} ({b['guest_contact']})",
        f"Статус: {status}",
    ]
    if show_role and b.get("my_role"):
        role = "Организатор" if b["my_role"] == "organizer" else "Гость"
        lines.append(f"Роль: {role}")
    if b.get("meeting_link"):
        lines.append(f"🎥 <a href='{b['meeting_link']}'>Ссылка на встречу</a>")
    return "\n".join(lines)

# ─────────────────────────────────────────────────────────
# Router
# ─────────────────────────────────────────────────────────

router = Router()

# ── /start ──────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext):
    await state.clear()
    user = msg.from_user
    log.info(f"User {user.id} started bot")

    # Принудительно обновляем Menu Button для этого пользователя
    try:
        await msg.bot.set_chat_menu_button(
            chat_id=msg.chat.id,
            menu_button=MenuButtonWebApp(
                text="Открыть",
                web_app=WebAppInfo(url=MINI_APP_URL)
            )
        )
        log.info(f"Menu button updated for user {user.id}")
    except Exception as e:
        log.warning(f"Could not set menu button for user {user.id}: {e}")

    await api("post", f"/api/users/auth?telegram_id={user.id}", json={
        "username":    user.username,
        "first_name":  user.first_name,
        "last_name":   user.last_name,
    })

    await msg.answer(
        f"👋 Привет, <b>{user.first_name}</b>!\n\n"
        "Я помогу тебе управлять встречами:\n"
        "• создавать расписания\n"
        "• принимать бронирования\n"
        "• отправлять ссылки клиентам\n\n"
        "Выбери действие:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard()
    )

    # Одна inline-кнопка для открытия Mini App
    inline_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="🌐 Открыть приложение",
            web_app=WebAppInfo(url=MINI_APP_URL)
        )
    ]])

    await msg.answer(
        "👇 Или открой приложение:",
        reply_markup=inline_kb
    )

# ── Главное меню ──────────────────────────────────────────

@router.callback_query(F.data == "main_menu")
async def cb_main_menu(cb: CallbackQuery):
    await cb.message.edit_text(
        "Выбери действие:",
        reply_markup=kb_main(MINI_APP_URL)
    )
    await cb.answer()

# ── Мои расписания ────────────────────────────────────────

@router.callback_query(F.data == "my_schedules")
async def cb_my_schedules(cb: CallbackQuery):
    schedules = await api("get", f"/api/schedules?telegram_id={cb.from_user.id}")
    
    if not schedules:
        await cb.message.edit_text(
            "У тебя пока нет расписаний.\n\nСоздай первое!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Создать", callback_data="create_schedule")],
                [InlineKeyboardButton(text="« Назад", callback_data="main_menu")],
            ])
        )
        await cb.answer()
        return

    buttons = []
    for s in schedules:
        dur = s["duration"]
        buttons.append([
            InlineKeyboardButton(
                text=f"📅 {s['title']} ({dur} мин)",
                callback_data=f"schedule_{s['id']}"
            )
        ])
    buttons.append([InlineKeyboardButton(text="➕ Создать новое", callback_data="create_schedule")])
    buttons.append([InlineKeyboardButton(text="« Назад", callback_data="main_menu")])

    await cb.message.edit_text(
        f"📋 Твои расписания ({len(schedules)}):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await cb.answer()

@router.callback_query(F.data.startswith("schedule_"))
async def cb_schedule_detail(cb: CallbackQuery):
    schedule_id = cb.data.split("_", 1)[1]
    s = await api("get", f"/api/schedules/{schedule_id}")
    
    if not s:
        await cb.answer("Расписание не найдено", show_alert=True)
        return

    days = [DAYS_RU[d] for d in sorted(s.get("work_days", []))]
    text = (
        f"📅 <b>{s['title']}</b>\n\n"
        f"⏱ Длительность: {s['duration']} мин\n"
        f"⏸ Буфер: {s['buffer_time']} мин\n"
        f"📆 Дни: {', '.join(days)}\n"
        f"🕐 Время: {str(s['start_time'])[:5]} — {str(s['end_time'])[:5]}\n"
        f"🎥 Платформа: {s['platform']}\n"
    )
    if s.get("description"):
        text += f"\n📝 {s['description']}"

    await cb.message.edit_text(
        text,
        reply_markup=kb_schedule_actions(schedule_id, MINI_APP_URL),
        parse_mode=ParseMode.HTML
    )
    await cb.answer()

@router.callback_query(F.data.startswith("share_"))
async def cb_share_schedule(cb: CallbackQuery):
    schedule_id = cb.data.split("_", 1)[1]
    booking_url = f"{MINI_APP_URL}?schedule_id={schedule_id}"
    
    await cb.message.answer(
        f"🔗 <b>Ссылка для записи:</b>\n\n"
        f"<code>{booking_url}</code>\n\n"
        f"Отправь эту ссылку клиентам — они смогут выбрать время и записаться.",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_back_main()
    )
    await cb.answer()

@router.callback_query(F.data.startswith("del_"))
async def cb_delete_schedule(cb: CallbackQuery):
    schedule_id = cb.data.split("_", 1)[1]
    result = await api("delete", f"/api/schedules/{schedule_id}?telegram_id={cb.from_user.id}")
    
    if result:
        await cb.message.edit_text(
            "✅ Расписание удалено.",
            reply_markup=kb_back_main()
        )
    else:
        await cb.answer("Не удалось удалить", show_alert=True)

# ── Создание расписания (FSM) ─────────────────────────────

@router.callback_query(F.data == "create_schedule")
async def cb_create_schedule(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(CreateSchedule.title)
    await cb.message.edit_text(
        "➕ <b>Создание нового расписания</b>\n\n"
        "Шаг 1/5: Введи название расписания.\n"
        "Например: <i>Консультация по маркетингу</i>",
        parse_mode=ParseMode.HTML
    )
    await cb.answer()

@router.message(CreateSchedule.title)
async def fsm_title(msg: Message, state: FSMContext):
    await state.update_data(title=msg.text.strip())
    await state.set_state(CreateSchedule.duration)
    await msg.answer(
        "Шаг 2/5: Выбери длительность встречи:",
        reply_markup=kb_duration()
    )

@router.callback_query(CreateSchedule.duration, F.data.startswith("dur_"))
async def fsm_duration(cb: CallbackQuery, state: FSMContext):
    duration = int(cb.data.split("_")[1])
    await state.update_data(duration=duration)
    await state.set_state(CreateSchedule.buffer_time)
    await cb.message.edit_text(
        f"✓ Длительность: {duration} мин\n\n"
        "Шаг 3/5: Буфер между встречами\n"
        "(время на отдых/подготовку):",
        reply_markup=kb_buffer()
    )
    await cb.answer()

@router.callback_query(CreateSchedule.buffer_time, F.data.startswith("buf_"))
async def fsm_buffer(cb: CallbackQuery, state: FSMContext):
    buf = int(cb.data.split("_")[1])
    await state.update_data(buffer_time=buf)
    await state.set_state(CreateSchedule.work_days)
    await cb.message.edit_text(
        f"✓ Буфер: {buf} мин\n\n"
        "Шаг 4/5: Рабочие дни\n\n"
        "Введи числами через пробел:\n"
        "<code>0=Пн, 1=Вт, 2=Ср, 3=Чт, 4=Пт, 5=Сб, 6=Вс</code>\n\n"
        "Например: <code>0 1 2 3 4</code> — будни",
        parse_mode=ParseMode.HTML
    )
    await cb.answer()

@router.message(CreateSchedule.work_days)
async def fsm_work_days(msg: Message, state: FSMContext):
    try:
        days = [int(d) for d in msg.text.strip().split() if d.isdigit() and 0 <= int(d) <= 6]
        if not days:
            raise ValueError
    except:
        await msg.answer("Неверный формат. Введи числа от 0 до 6 через пробел. Например: 0 1 2 3 4")
        return
    
    await state.update_data(work_days=days)
    await state.set_state(CreateSchedule.start_time)
    days_str = ", ".join(DAYS_RU[d] for d in sorted(days))
    await msg.answer(
        f"✓ Дни: {days_str}\n\n"
        "Шаг 4б: Начало рабочего дня\n"
        "Введи время в формате <code>ЧЧ:ММ</code>, например: <code>09:00</code>",
        parse_mode=ParseMode.HTML
    )

@router.message(CreateSchedule.start_time)
async def fsm_start_time(msg: Message, state: FSMContext):
    t = msg.text.strip()
    try:
        datetime.strptime(t, "%H:%M")
    except:
        await msg.answer("Неверный формат. Введи время как 09:00")
        return
    await state.update_data(start_time=t)
    await state.set_state(CreateSchedule.end_time)
    await msg.answer(
        f"✓ Начало: {t}\n\n"
        "Конец рабочего дня (например: <code>18:00</code>):",
        parse_mode=ParseMode.HTML
    )

@router.message(CreateSchedule.end_time)
async def fsm_end_time(msg: Message, state: FSMContext):
    t = msg.text.strip()
    try:
        datetime.strptime(t, "%H:%M")
    except:
        await msg.answer("Неверный формат. Введи время как 18:00")
        return
    await state.update_data(end_time=t)
    await state.set_state(CreateSchedule.platform)
    await msg.answer(
        f"✓ Конец: {t}\n\n"
        "Шаг 5/5: Платформа для встреч:",
        reply_markup=kb_platform()
    )

@router.callback_query(CreateSchedule.platform, F.data.startswith("plat_"))
async def fsm_platform(cb: CallbackQuery, state: FSMContext):
    platform = cb.data.split("_")[1]
    data = await state.get_data()
    data["platform"] = platform
    telegram_id = cb.from_user.id

    await state.clear()

    result = await api("post", f"/api/schedules?telegram_id={telegram_id}", json=data)
    
    if result:
        days_str = ", ".join(DAYS_RU[d] for d in sorted(data.get("work_days", [])))
        booking_url = f"{MINI_APP_URL}?schedule_id={result['id']}"
        await cb.message.edit_text(
            f"🎉 <b>Расписание создано!</b>\n\n"
            f"📅 {data['title']}\n"
            f"⏱ {data['duration']} мин\n"
            f"📆 {days_str}\n"
            f"🕐 {data['start_time']} — {data['end_time']}\n\n"
            f"🔗 <b>Ссылка для клиентов:</b>\n"
            f"<code>{booking_url}</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="« Главное меню", callback_data="main_menu")]
            ])
        )
    else:
        await cb.message.edit_text(
            "❌ Ошибка создания расписания. Попробуй ещё раз.",
            reply_markup=kb_back_main()
        )
    await cb.answer()

# ── Мои встречи ───────────────────────────────────────────

@router.callback_query(F.data == "my_bookings")
async def cb_my_bookings(cb: CallbackQuery):
    bookings = await api("get", f"/api/bookings?telegram_id={cb.from_user.id}")
    
    if not bookings:
        await cb.message.edit_text(
            "У тебя пока нет встреч.",
            reply_markup=kb_back_main()
        )
        await cb.answer()
        return

    buttons = []
    for b in bookings[:10]:  # лимит 10 в меню
        emoji = STATUS_EMOJI.get(b["status"], "?")
        dt = format_dt(b["scheduled_time"])
        role = "📌" if b.get("my_role") == "organizer" else "👤"
        buttons.append([
            InlineKeyboardButton(
                text=f"{role}{emoji} {b.get('schedule_title','?')} · {dt}",
                callback_data=f"booking_{b['id']}"
            )
        ])
    buttons.append([InlineKeyboardButton(text="« Назад", callback_data="main_menu")])

    await cb.message.edit_text(
        f"📋 <b>Твои встречи ({len(bookings)})</b>\n"
        f"📌 = организатор, 👤 = гость",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode=ParseMode.HTML
    )
    await cb.answer()

@router.callback_query(F.data.startswith("booking_"))
async def cb_booking_detail(cb: CallbackQuery):
    booking_id = cb.data.split("_", 1)[1]
    bookings = await api("get", f"/api/bookings?telegram_id={cb.from_user.id}")
    
    booking = next((b for b in (bookings or []) if b["id"] == booking_id), None)
    if not booking:
        await cb.answer("Встреча не найдена", show_alert=True)
        return

    text = format_booking(booking, show_role=True)
    
    # Управление показываем только организатору
    if booking.get("my_role") == "organizer":
        kb = kb_booking_actions(booking_id, booking["status"])
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить", callback_data=f"cancel_{booking_id}")],
            [InlineKeyboardButton(text="« Назад", callback_data="my_bookings")],
        ])

    await cb.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML,
                                disable_web_page_preview=True)
    await cb.answer()

@router.callback_query(F.data.startswith("confirm_"))
async def cb_confirm_booking(cb: CallbackQuery):
    booking_id = cb.data.split("_", 1)[1]
    result = await api("patch", f"/api/bookings/{booking_id}/confirm?telegram_id={cb.from_user.id}")
    if result:
        await cb.message.edit_text(
            cb.message.text + "\n\n✅ <b>Подтверждено</b>",
            parse_mode=ParseMode.HTML,
        )
        await cb.answer("Встреча подтверждена!")
    else:
        await cb.answer("Не удалось подтвердить", show_alert=True)

@router.callback_query(F.data.startswith("cancel_"))
async def cb_cancel_booking(cb: CallbackQuery):
    booking_id = cb.data.split("_", 1)[1]
    result = await api("patch", f"/api/bookings/{booking_id}/cancel?telegram_id={cb.from_user.id}")
    if result:
        await cb.message.edit_text(
            cb.message.text + "\n\n❌ <b>Отклонено</b>",
            parse_mode=ParseMode.HTML,
        )
        await cb.answer("Встреча отменена")
    else:
        await cb.answer("Не удалось отменить", show_alert=True)

# ── Статистика ────────────────────────────────────────────

@router.callback_query(F.data == "stats")
async def cb_stats(cb: CallbackQuery):
    stats = await api("get", f"/api/stats?telegram_id={cb.from_user.id}")
    
    if not stats:
        await cb.answer("Не удалось загрузить статистику", show_alert=True)
        return

    text = (
        "📊 <b>Твоя статистика</b>\n\n"
        f"📅 Активных расписаний: <b>{stats.get('active_schedules', 0)}</b>\n"
        f"📋 Всего встреч: <b>{stats.get('total_bookings', 0)}</b>\n"
        f"⏳ Ожидают подтверждения: <b>{stats.get('pending_bookings', 0)}</b>\n"
        f"✅ Подтверждено: <b>{stats.get('confirmed_bookings', 0)}</b>\n"
        f"🚀 Предстоящих: <b>{stats.get('upcoming_bookings', 0)}</b>\n"
    )
    await cb.message.edit_text(text, reply_markup=kb_back_main(), parse_mode=ParseMode.HTML)
    await cb.answer()

# ── /help ─────────────────────────────────────────────────

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
        reply_markup=kb_back_main()
    )

# ── Reply-кнопки (нижняя панель) ────────────────────────

@router.message(F.text == "📅 Создать расписание")
async def reply_create_schedule(msg: Message, state: FSMContext):
    await state.clear()
    await state.set_state(CreateSchedule.title)
    await msg.answer(
        "➕ <b>Создание нового расписания</b>\n\n"
        "Шаг 1/5: Введи название расписания.\n"
        "Например: <i>Консультация по маркетингу</i>",
        parse_mode=ParseMode.HTML
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

    buttons = []
    for s in schedules:
        dur = s["duration"]
        buttons.append([
            InlineKeyboardButton(
                text=f"📅 {s['title']} ({dur} мин)",
                callback_data=f"schedule_{s['id']}"
            )
        ])
    buttons.append([InlineKeyboardButton(text="➕ Создать новое", callback_data="create_schedule")])

    await msg.answer(
        f"📋 Твои расписания ({len(schedules)}):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
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
        dt = format_dt(b["scheduled_time"])
        role = "📌" if b.get("my_role") == "organizer" else "👤"
        buttons.append([
            InlineKeyboardButton(
                text=f"{role}{emoji} {b.get('schedule_title','?')} · {dt}",
                callback_data=f"booking_{b['id']}"
            )
        ])

    await msg.answer(
        f"📋 <b>Твои встречи ({len(bookings)})</b>\n"
        f"📌 = организатор, 👤 = гость",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode=ParseMode.HTML
    )


@router.message(F.text == "❓ Помощь")
async def reply_help(msg: Message):
    await cmd_help(msg)

# ─────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────

async def setup_bot_commands(bot: Bot):
    """Регистрирует команды и устанавливает Menu Button глобально."""
    commands = [
        BotCommand(command="start",  description="Главное меню"),
        BotCommand(command="help",   description="Справка по боту"),
    ]
    await bot.set_my_commands(commands)

    # Принудительно устанавливаем правильную Menu Button глобально
    try:
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="Открыть",
                web_app=WebAppInfo(url=MINI_APP_URL)
            )
        )
        log.info(f"Global menu button set: 'Открыть' → {MINI_APP_URL}")
    except Exception as e:
        log.warning(f"Could not set global menu button: {e}")
    log.info("Bot commands configured")


# ─────────────────────────────────────────────────────────
# Internal notification webhook (aiohttp)
# ─────────────────────────────────────────────────────────

async def handle_new_booking(request: web.Request) -> web.Response:
    """Receive booking notification from backend and message the organizer."""
    key = request.headers.get("X-Internal-Key", "")
    if not INTERNAL_API_KEY or not hmac.compare_digest(key, INTERNAL_API_KEY):
        return web.json_response({"error": "unauthorized"}, status=401)

    try:
        payload = await request.json()
    except Exception:
        return web.json_response({"error": "invalid json"}, status=400)

    organizer_tid = payload.get("organizer_telegram_id")
    if not organizer_tid or not _bot:
        return web.json_response({"error": "missing data"}, status=400)

    try:
        dt = format_dt(payload.get("scheduled_time", ""))
        schedule_title = payload.get("schedule_title", "Встреча")
        guest_name = payload.get("guest_name", "—")
        guest_contact = payload.get("guest_contact", "—")
        meeting_link = payload.get("meeting_link", "")

        # Message to organizer
        org_text = (
            "🔔 <b>Новая запись!</b>\n\n"
            f"👤 {guest_name}\n"
            f"📅 {dt}\n"
            f"📋 {schedule_title}\n"
            f"📞 {guest_contact}"
        )
        if meeting_link:
            org_text += f"\n🔗 <a href='{meeting_link}'>Ссылка на встречу</a>"

        booking_id = payload.get("booking_id", "")
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm_{booking_id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"cancel_{booking_id}"),
            ],
        ])

        await _bot.send_message(
            chat_id=organizer_tid,
            text=org_text,
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
            disable_web_page_preview=True,
        )

        # Message to guest (if telegram_id available)
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

            await _bot.send_message(
                chat_id=guest_tid,
                text=guest_text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )

        return web.json_response({"ok": True})

    except Exception as e:
        log.error(f"Failed to send notification: {e}")
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def send_reminder(booking: dict, reminder_type: str):
    """Send reminder to guest and organizer."""
    scheduled_dt = booking["scheduled_time"]
    if isinstance(scheduled_dt, str):
        scheduled_dt = datetime.fromisoformat(scheduled_dt.replace("Z", "+00:00"))

    org_tz = booking.get("organizer_timezone") or "UTC"
    time_str = format_dt(booking["scheduled_time"], tz=org_tz)

    prefix = "⏰ Напоминание!" if reminder_type == "1h" else "📅 Завтра встреча!"

    text = (
        f"{prefix}\n\n"
        f"📋 {booking['schedule_title']}\n"
        f"📅 {time_str}\n"
        f"⏱ {booking.get('duration', 60)} мин\n"
    )
    if booking.get("meeting_link"):
        text += f"🔗 <a href=\"{booking['meeting_link']}\">Подключиться</a>\n"

    # Notify guest
    guest_tid = booking.get("guest_telegram_id")
    if guest_tid and _bot:
        try:
            await _bot.send_message(
                guest_tid,
                text + f"\n👤 Организатор: {booking.get('organizer_name', 'N/A')}",
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        except Exception as e:
            log.warning(f"Failed to send reminder to guest {guest_tid}: {e}")

    # Notify organizer
    org_tid = booking.get("organizer_telegram_id")
    if org_tid and _bot:
        try:
            await _bot.send_message(
                org_tid,
                text + f"\n👤 Гость: {booking['guest_name']} ({booking.get('guest_contact', '')})",
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        except Exception as e:
            log.warning(f"Failed to send reminder to organizer {org_tid}: {e}")

    # Mark as sent
    await api("patch", f"/api/bookings/{booking['id']}/reminder-sent?reminder_type={reminder_type}")


async def reminder_loop():
    """Check for pending reminders every 5 minutes and send them."""
    await asyncio.sleep(10)  # wait for bot startup
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
                        await send_reminder(b, rtype)
                        await asyncio.sleep(0.5)  # rate limit
        except Exception as e:
            log.error(f"Reminder loop error: {e}")

        await asyncio.sleep(300)  # 5 minutes


async def main():
    global _bot
    _bot = Bot(token=BOT_TOKEN)
    dp  = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    await setup_bot_commands(_bot)

    # Background reminder task
    asyncio.create_task(reminder_loop())

    # Internal notification server
    webapp = web.Application()
    webapp.router.add_post("/internal/notify", handle_new_booking)
    runner = web.AppRunner(webapp)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()
    log.info("Internal notification server started on port 8080")

    log.info("Bot starting…")
    try:
        await dp.start_polling(_bot, skip_updates=True)
    finally:
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
