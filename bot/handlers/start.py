"""Handlers: /start, /help, reply-keyboard buttons, notify deep link."""
import logging
from datetime import timezone, datetime

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
from formatters import STATUS_EMOJI, STATUS_TEXT, format_dt
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

    # Deep link: calendar_connected — Google Calendar успешно подключён
    if args == "calendar_connected":
        await msg.answer(
            "✅ <b>Google Calendar подключён!</b>\n\n"
            "Ваши события из Google Calendar теперь автоматически блокируют слоты в расписаниях.\n\n"
            "Откройте приложение, чтобы настроить какие календари использовать.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text="📅 Открыть приложение",
                    web_app=WebAppInfo(url=MINI_APP_URL),
                )
            ]]),
        )
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

@router.message(F.text == "🏠 Главная")
async def reply_home(msg: Message):
    tid = msg.from_user.id
    now = datetime.now(timezone.utc)

    stats    = await api("get", f"/api/stats?telegram_id={tid}")
    bookings = await api("get", f"/api/bookings?telegram_id={tid}&role=organizer")

    upcoming = []
    today_list = []
    if isinstance(bookings, list):
        for b in bookings:
            try:
                dt = datetime.fromisoformat(b["scheduled_time"].replace("Z", "+00:00"))
            except Exception:
                continue
            if dt > now and b.get("status") not in ("cancelled", "completed"):
                upcoming.append((dt, b))
                if dt.date() == now.date():
                    today_list.append((dt, b))
        upcoming.sort(key=lambda x: x[0])
        today_list.sort(key=lambda x: x[0])

    text = f"🏠 <b>Главная</b>\n\n"

    if upcoming:
        _, b = upcoming[0]
        tz = b.get("organizer_timezone") or "UTC"
        text += (
            f"📌 <b>Ближайшая встреча</b>\n"
            f"👤 {b['guest_name']}\n"
            f"📅 {format_dt(b['scheduled_time'], tz=tz)}\n"
            f"📋 {b.get('schedule_title', '')}\n"
            f"Статус: {STATUS_EMOJI.get(b['status'], '❓')} {STATUS_TEXT.get(b['status'], b['status'])}\n\n"
        )

    if today_list:
        text += f"📅 <b>Сегодня — {len(today_list)} встреч:</b>\n"
        for _, b in today_list[:5]:
            tz = b.get("organizer_timezone") or "UTC"
            emoji = STATUS_EMOJI.get(b["status"], "❓")
            t = format_dt(b["scheduled_time"], tz=tz)
            text += f"  {emoji} {t} — {b['guest_name']}\n"
    else:
        text += "📅 Сегодня встреч нет\n"

    if stats and isinstance(stats, dict):
        text += (
            f"\n📊 Расписаний: <b>{stats.get('active_schedules', 0)}</b>"
            f" · Встреч: <b>{stats.get('total_bookings', 0)}</b>"
        )

    kb_rows = []
    if upcoming:
        _, b0 = upcoming[0]
        kb_rows.append([InlineKeyboardButton(
            text="📋 Подробнее о ближайшей",
            callback_data=f"booking_{b0['id']}",
        )])
        if b0.get("meeting_link") and b0.get("schedule_platform") in ("jitsi", "zoom", "google_meet"):
            kb_rows.append([InlineKeyboardButton(
                text="🔗 Подключиться",
                url=b0["meeting_link"],
            )])

    await msg.answer(text, parse_mode=ParseMode.HTML,
                     reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows) if kb_rows else None)


@router.message(F.text == "📋 Встречи")
async def reply_meetings(msg: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⏳ Нужно подтвердить", callback_data="meetings_pending"),
            InlineKeyboardButton(text="📋 Все",               callback_data="meetings_all"),
        ],
        [
            InlineKeyboardButton(text="✅ Всё в силе",  callback_data="meetings_confirmed"),
            InlineKeyboardButton(text="❓ Нет ответа",  callback_data="meetings_noans"),
        ],
    ])
    await msg.answer("📋 <b>Встречи</b>\nВыберите фильтр:", parse_mode=ParseMode.HTML, reply_markup=kb)


@router.callback_query(F.data.startswith("meetings_"))
async def cb_meetings_filter(cb: CallbackQuery):
    filter_type = cb.data.replace("meetings_", "")
    tid = cb.from_user.id
    now = datetime.now(timezone.utc)

    bookings = await api("get", f"/api/bookings?telegram_id={tid}&role=organizer")
    if not isinstance(bookings, list) or not bookings:
        await cb.message.edit_text("📭 Встреч пока нет")
        await cb.answer()
        return

    def _dt(b):
        try:
            return datetime.fromisoformat(b["scheduled_time"].replace("Z", "+00:00"))
        except Exception:
            return None

    if filter_type == "pending":
        filtered = [b for b in bookings if b["status"] == "pending" and (_dt(b) or now) > now]
    elif filter_type == "confirmed":
        filtered = [b for b in bookings if b["status"] == "confirmed" and (_dt(b) or now) > now]
    elif filter_type == "noans":
        filtered = [b for b in bookings if b["status"] == "pending" and (_dt(b) or now) < now]
    else:
        filtered = [b for b in bookings if b.get("status") not in ("cancelled", "completed")]

    if not filtered:
        await cb.message.edit_text("📭 Нет встреч по этому фильтру")
        await cb.answer()
        return

    text = f"📋 <b>Встречи ({len(filtered)})</b>\n\n"
    kb_rows = []
    for b in filtered[:10]:
        emoji = STATUS_EMOJI.get(b["status"], "❓")
        tz    = b.get("organizer_timezone") or "UTC"
        text += f"{emoji} <b>{b['guest_name']}</b>\n   {format_dt(b['scheduled_time'], tz=tz)} · {b.get('schedule_title', '')}\n\n"
        kb_rows.append([InlineKeyboardButton(
            text=f"📋 {b['guest_name']}",
            callback_data=f"booking_{b['id']}",
        )])

    # Trim text to Telegram limit
    if len(text) > 4000:
        text = text[:4000] + "…"

    await cb.message.edit_text(text, parse_mode=ParseMode.HTML,
                                reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))
    await cb.answer()


@router.message(F.text == "📅 Расписания")
async def reply_schedules(msg: Message):
    schedules = await api("get", f"/api/schedules?telegram_id={msg.from_user.id}")

    if not isinstance(schedules, list) or not schedules:
        await msg.answer(
            "📅 <b>Расписания</b>\n\nУ вас пока нет расписаний.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="➕ Создать расписание", callback_data="create_schedule"),
            ]]),
        )
        return

    text = "📅 <b>Расписания</b>\n\n"
    kb_rows = []
    for s in schedules:
        status = "🟢" if s.get("is_active", True) else "⏸"
        text += f"{status} <b>{s['title']}</b>\n   ⏱ {s['duration']} мин · {s.get('platform', 'jitsi')}\n\n"
        kb_rows.append([InlineKeyboardButton(
            text=f"⚙️ {s['title']}",
            callback_data=f"schedule_{s['id']}",
        )])
    kb_rows.append([InlineKeyboardButton(text="➕ Создать расписание", callback_data="create_schedule")])

    await msg.answer(text, parse_mode=ParseMode.HTML,
                     reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))


@router.message(F.text == "👤 Профиль")
async def reply_profile(msg: Message):
    u = msg.from_user
    text = (
        f"👤 <b>Профиль</b>\n\n"
        f"Имя: {u.first_name} {u.last_name or ''}\n"
        f"Username: @{u.username or '—'}\n"
        f"ID: {u.id}\n"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔔 Настройки уведомлений", callback_data="profile_notifications")],
        [InlineKeyboardButton(text="💬 Написать в поддержку",  url="https://t.me/iwantproger")],
        [InlineKeyboardButton(text="❓ Помощь",                callback_data="profile_help")],
    ])
    await msg.answer(text, parse_mode=ParseMode.HTML, reply_markup=kb)


@router.callback_query(F.data == "profile_help")
async def cb_profile_help(cb: CallbackQuery):
    await cb.message.answer(
        "📖 <b>Как пользоваться ботом</b>\n\n"
        "1. Создай расписание через «📅 Расписания» → «➕ Создать»\n"
        "2. Поделись ссылкой с клиентами\n"
        "3. Клиент бронирует → ты получаешь уведомление\n"
        "4. Подтверди или отмени встречу\n\n"
        "<b>Команды:</b>\n/start — главное меню\n/help — эта справка",
        parse_mode=ParseMode.HTML,
    )
    await cb.answer()


@router.callback_query(F.data == "profile_notifications")
async def cb_profile_notifications(cb: CallbackQuery):
    await cb.message.answer(
        "🔔 <b>Настройки уведомлений</b>\n\n"
        "Управляй напоминаниями в приложении:\n"
        "• Выбери когда напоминать (за 24ч, 1ч, 30мин и т.д.)\n"
        "• Добавь свои тайминги",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="📱 Открыть настройки",
                web_app=WebAppInfo(url=MINI_APP_URL),
            )
        ]]),
    )
    await cb.answer()


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
