"""Все клавиатуры бота."""
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    KeyboardButton, ReplyKeyboardMarkup, WebAppInfo,
)

from config import MINI_APP_URL


def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Постоянная нижняя панель 2×2."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏠 Главная"),    KeyboardButton(text="📋 Встречи")],
            [KeyboardButton(text="📅 Расписания"), KeyboardButton(text="👤 Профиль")],
        ],
        resize_keyboard=True,
    )


# Static inline keyboards (module-level, immutable).

kb_main = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🌐 Открыть приложение", web_app=WebAppInfo(url=MINI_APP_URL))],
    [InlineKeyboardButton(text="📅 Мои расписания",   callback_data="my_schedules")],
    [InlineKeyboardButton(text="➕ Создать расписание", url="https://t.me/do_vstrechi_bot/app?startapp=create")],
    [InlineKeyboardButton(text="📋 Мои встречи",      callback_data="my_bookings")],
    [InlineKeyboardButton(text="📊 Статистика",       callback_data="stats")],
])


kb_back_main = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="« Главное меню", callback_data="main_menu")]
])


_FSM_NAV_ROW = [
    InlineKeyboardButton(text="← Назад", callback_data="fsm_back"),
    InlineKeyboardButton(text="✕ Отмена", callback_data="fsm_cancel"),
]

kb_fsm_nav = InlineKeyboardMarkup(inline_keyboard=[_FSM_NAV_ROW])


def _build_duration_kb() -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(text=f"{d} мин", callback_data=f"dur_{d}")
        for d in [15, 30, 45, 60, 90, 120]
    ]
    rows = [buttons[i:i+3] for i in range(0, len(buttons), 3)]
    rows.append(_FSM_NAV_ROW)
    return InlineKeyboardMarkup(inline_keyboard=rows)


kb_duration = _build_duration_kb()


kb_buffer = InlineKeyboardMarkup(inline_keyboard=[
    [
        InlineKeyboardButton(text="Без буфера", callback_data="buf_0"),
        InlineKeyboardButton(text="10 мин",     callback_data="buf_10"),
    ],
    [
        InlineKeyboardButton(text="15 мин", callback_data="buf_15"),
        InlineKeyboardButton(text="30 мин", callback_data="buf_30"),
    ],
    _FSM_NAV_ROW,
])


kb_platform = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🎥 Jitsi Meet (бесплатно)", callback_data="plat_jitsi")],
    [InlineKeyboardButton(text="🔗 Zoom",                   callback_data="plat_zoom")],
    [InlineKeyboardButton(text="📍 Офлайн / другое",        callback_data="plat_other")],
    _FSM_NAV_ROW,
])


def kb_work_days(selected: list[int] | None = None) -> InlineKeyboardMarkup:
    """Клавиатура выбора рабочих дней с toggle-эффектом."""
    if selected is None:
        selected = []
    days = [(0, "Пн"), (1, "Вт"), (2, "Ср"), (3, "Чт"), (4, "Пт"), (5, "Сб"), (6, "Вс")]
    day_buttons = []
    for num, name in days:
        mark = f"✅ {name}" if num in selected else name
        day_buttons.append(InlineKeyboardButton(text=mark, callback_data=f"day_{num}"))

    rows = [day_buttons[:4], day_buttons[4:]]
    rows.append([
        InlineKeyboardButton(text="📅 Будни (Пн-Пт)", callback_data="days_weekdays"),
        InlineKeyboardButton(text="📅 Все дни", callback_data="days_all"),
    ])
    if selected:
        rows.append([InlineKeyboardButton(text="✓ Готово", callback_data="days_done")])
    rows.append(_FSM_NAV_ROW)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_schedule_actions(schedule_id: str) -> InlineKeyboardMarkup:
    booking_url = f"{MINI_APP_URL}?schedule_id={schedule_id}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Открыть страницу записи", web_app=WebAppInfo(url=booking_url))],
        [InlineKeyboardButton(text="🔗 Поделиться ссылкой", callback_data=f"share_{schedule_id}")],
        [InlineKeyboardButton(text="🗑 Удалить",             callback_data=f"del_{schedule_id}")],
        [InlineKeyboardButton(text="« Назад",               callback_data="my_schedules")],
    ])


def kb_booking_actions(booking_id: str, status: str) -> InlineKeyboardMarkup:
    buttons = []
    if status == "pending":
        buttons.append([
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm_{booking_id}"),
            InlineKeyboardButton(text="❌ Отменить",    callback_data=f"cancel_{booking_id}"),
        ])
    elif status == "confirmed":
        buttons.append([InlineKeyboardButton(text="❌ Отменить", callback_data=f"cancel_{booking_id}")])
    buttons.append([InlineKeyboardButton(text="« Назад", callback_data="my_bookings")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
