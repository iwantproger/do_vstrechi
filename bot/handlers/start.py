"""Handlers: /start, /help, reply-keyboard buttons, notify deep link."""
import logging
from datetime import timezone, datetime
from urllib.parse import quote

from aiogram import Router, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.filters.command import CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo,
)

from api import api
from config import MINI_APP_URL, BOT_USERNAME
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

    # Fetch stats + schedules to determine user type
    stats = await api("get", f"/api/stats?telegram_id={user.id}")
    active_schedules = 0
    upcoming_bookings = 0
    if stats and isinstance(stats, dict):
        active_schedules = stats.get("active_schedules", 0) or 0
        upcoming_bookings = stats.get("upcoming_bookings", 0) or 0

    if active_schedules == 0:
        # ── New user — onboarding ──
        await api("post", f"/api/schedules/default?telegram_id={user.id}")

        await msg.answer(
            "📅 <b>До встречи!</b> — это поиск свободного времени "
            "между тобой и другим человеком\n\n"
            "1. Создай расписание — укажи название, время и дни\n"
            "2. Отправь ссылку другому человеку\n"
            "3. Он выбирает слот и записывается\n"
            "4. Ты получаешь уведомление и подтверждаешь\n\n"
            "Без сайтов, без регистрации — всё внутри Telegram.\n\n"
            "У тебя уже есть готовое расписание — посмотри его по кнопке ниже.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📋 Готовое расписание", callback_data="show_default_schedule")],
                [InlineKeyboardButton(text="➕ Создать своё расписание", web_app=WebAppInfo(url=f"{MINI_APP_URL}?action=create"))],
                [InlineKeyboardButton(text="💬 Создать в чате", callback_data="create_schedule_chat")],
            ]),
        )

    else:
        # ── Returning user ──
        resp = await api("get", f"/api/schedules?telegram_id={user.id}")
        schedules_list = resp.get("schedules", []) if isinstance(resp, dict) else (resp or [])
        schedule_count = len(schedules_list)
        has_custom = schedule_count > 1 or (
            schedule_count == 1
            and not (schedules_list[0].get("title") or "").startswith("Свободное время")
        )

        if upcoming_bookings > 0:
            text = (
                f"👋 {user.first_name}, с возвращением!\n\n"
                f"У тебя {upcoming_bookings} предстоящих встреч."
            )
            buttons = []
            if schedule_count > 1:
                buttons.append([InlineKeyboardButton(text="📅 Мои расписания", callback_data="my_schedules")])
            elif schedule_count == 1:
                buttons.append([InlineKeyboardButton(text="📅 Моё расписание", callback_data="show_default_schedule")])
            buttons.append([InlineKeyboardButton(text="📋 Мои встречи", callback_data="my_bookings")])
            buttons.append([InlineKeyboardButton(text="🌐 Открыть приложение", web_app=WebAppInfo(url=MINI_APP_URL))])

        elif has_custom:
            text = (
                f"👋 {user.first_name}, с возвращением!\n\n"
                "Пока нет предстоящих встреч. Поделись ссылкой на расписание — и записи появятся."
            )
            buttons = []
            if schedule_count > 1:
                buttons.append([InlineKeyboardButton(text="📅 Мои расписания", callback_data="my_schedules")])
            elif schedule_count == 1:
                buttons.append([InlineKeyboardButton(text="📅 Моё расписание", callback_data="show_default_schedule")])
            buttons.append([InlineKeyboardButton(text="➕ Создать расписание", web_app=WebAppInfo(url=f"{MINI_APP_URL}?action=create"))])
            buttons.append([InlineKeyboardButton(text="🌐 Открыть приложение", web_app=WebAppInfo(url=MINI_APP_URL))])

        else:
            text = (
                f"👋 {user.first_name}, с возвращением!\n\n"
                "Пока нет предстоящих встреч. Поделись ссылкой на расписание — и записи появятся."
            )
            buttons = [
                [InlineKeyboardButton(text="📋 Готовое расписание", callback_data="show_default_schedule")],
                [InlineKeyboardButton(text="➕ Создать своё расписание", web_app=WebAppInfo(url=f"{MINI_APP_URL}?action=create"))],
            ]

        await msg.answer(text, parse_mode=ParseMode.HTML,
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

    # Delete user's /start message
    try:
        await msg.delete()
    except Exception:
        pass


@router.callback_query(F.data == "how_it_works")
async def cb_how_it_works(cb: CallbackQuery):
    text = (
        "📖 <b>Как это работает:</b>\n\n"
        "Шаг 1 — Создаёшь расписание в боте или приложении\n"
        "Шаг 2 — Делишься ссылкой (в чат, в stories, куда угодно)\n"
        "Шаг 3 — Человек открывает, выбирает дату и время\n"
        "Шаг 4 — Тебе приходит уведомление, подтверждаешь в один клик\n\n"
        "Готов попробовать?"
    )
    inline_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать расписание", web_app=WebAppInfo(url=f"{MINI_APP_URL}?action=create"))],
    ])
    await cb.message.answer(text, parse_mode=ParseMode.HTML, reply_markup=inline_kb)
    await cb.answer()


@router.callback_query(F.data == "show_default_schedule")
async def cb_show_default_schedule(cb: CallbackQuery):
    """Show default schedule details by button press."""
    resp = await api("get", f"/api/schedules?telegram_id={cb.from_user.id}")
    schedules = resp.get("schedules", []) if isinstance(resp, dict) else (resp or [])

    if not schedules:
        await cb.answer("Расписание не найдено", show_alert=True)
        return

    s = schedules[0]
    sid = str(s["id"])
    title = s.get("title", "Расписание")
    duration = s.get("duration", 60)
    buffer = s.get("buffer_time", 0)
    description = s.get("description", "")

    booking_link = f"https://t.me/{BOT_USERNAME}/app?startapp={sid}"
    browser_link = f"{MINI_APP_URL}?schedule_id={sid}"

    text = (
        f"📅 <b>{title}</b>\n"
        f"⏱ {duration} мин · {buffer} мин перерыв\n"
        "📆 Пн–Пт, 09:00–18:00\n"
        "⏰ Запись не менее чем за 1 час\n"
        "✅ Требуется подтверждение\n"
    )
    if description:
        text += f"\n📝 {description}\n"
    text += (
        f"\n🔗 <b>Ссылка для бронирования:</b>\n"
        f"<code>{booking_link}</code>\n"
        f"\n💡 Inline-режим: в любом чате введите @{BOT_USERNAME}"
    )

    share_text = (
        "Вот мои свободные слоты — выбирайте удобное время!\n"
        "До встречи! 🙌\n\n"
        f"Или откройте в браузере:\n{browser_link}"
    )
    tg_share = f"https://t.me/share/url?url={quote(booking_link)}&text={quote(share_text)}"

    buttons = [
        [InlineKeyboardButton(text="📤 Поделиться в Telegram", url=tg_share)],
        [InlineKeyboardButton(text="✏️ Редактировать", web_app=WebAppInfo(url=f"{MINI_APP_URL}?action=edit&schedule_id={sid}"))],
        [InlineKeyboardButton(text="➕ Создать своё расписание", web_app=WebAppInfo(url=f"{MINI_APP_URL}?action=create"))],
    ]

    await cb.message.answer(
        text, parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        disable_web_page_preview=True,
    )
    await cb.answer()


@router.callback_query(F.data.startswith("copy_link_"))
async def cb_copy_link(cb: CallbackQuery):
    schedule_id = cb.data.replace("copy_link_", "", 1)
    link = f"https://t.me/{BOT_USERNAME}/app?startapp={schedule_id}"
    await cb.message.answer(
        f"🔗 Нажмите на ссылку чтобы скопировать:\n\n<code>{link}</code>",
        parse_mode=ParseMode.HTML,
    )
    await cb.answer("👆 Нажмите на ссылку выше")


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
        reply_markup=kb_back_main,
    )


# ── Reply-кнопки нижней панели ────────────────────────────

@router.message(F.text == "🏠 Главная")
async def reply_home(msg: Message):
    tid = msg.from_user.id
    now = datetime.now(timezone.utc)

    stats    = await api("get", f"/api/stats?telegram_id={tid}")
    resp     = await api("get", f"/api/bookings?telegram_id={tid}&role=organizer")
    bookings = resp.get("bookings", []) if isinstance(resp, dict) else (resp or [])

    upcoming = []
    today_list = []
    if bookings:
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
        [
            InlineKeyboardButton(text="🕑 Просрочено",  callback_data="meetings_expired"),
        ],
    ])
    await msg.answer("📋 <b>Встречи</b>\nВыберите фильтр:", parse_mode=ParseMode.HTML, reply_markup=kb)


@router.callback_query(F.data.startswith("meetings_"))
async def cb_meetings_filter(cb: CallbackQuery):
    filter_type = cb.data.replace("meetings_", "")
    tid = cb.from_user.id
    now = datetime.now(timezone.utc)

    resp     = await api("get", f"/api/bookings?telegram_id={tid}&role=organizer")
    bookings = resp.get("bookings", []) if isinstance(resp, dict) else (resp or [])
    if not bookings:
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
        filtered = [b for b in bookings if b["status"] == "no_answer"]
    elif filter_type == "expired":
        filtered = [b for b in bookings if b["status"] == "expired"]
    else:
        filtered = [b for b in bookings if b.get("status") not in ("cancelled", "completed", "expired")]

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
    resp = await api("get", f"/api/schedules?telegram_id={msg.from_user.id}")
    schedules = resp.get("schedules", []) if isinstance(resp, dict) else (resp or [])

    if not schedules:
        await msg.answer(
            "📅 <b>Расписания</b>\n\nУ вас пока нет расписаний.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="➕ Создать расписание", web_app=WebAppInfo(url=f"{MINI_APP_URL}?action=create")),
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
    kb_rows.append([InlineKeyboardButton(text="➕ Создать расписание", web_app=WebAppInfo(url=f"{MINI_APP_URL}?action=create"))])

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
