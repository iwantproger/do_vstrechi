"""Шаблоны сообщений для всех уведомлений бота.

Принципы:
- Заголовок в <b>, без точки в конце
- Emoji один раз в заголовке, максимум один в теле
- Деловой тон, без CAPS
"""

# ── Новое бронирование ──

TPL_NEW_BOOKING_ORG = (
    "🔔 <b>Новая запись</b>\n\n"
    "👤 {guest_name}\n"
    "📅 {dt}\n"
    "📋 {schedule_title}\n"
    "📞 {guest_contact}"
    "{maybe_link}"
)

TPL_NEW_BOOKING_GUEST = (
    "✅ <b>Вы записались</b>\n\n"
    "📋 {schedule_title}\n"
    "📅 {dt}"
    "{maybe_link}"
    "{confirmation_note}"
)

# ── Напоминание ──

TPL_REMINDER = (
    "{label}\n\n"
    "📋 {schedule_title}\n"
    "📅 {dt}\n"
    "⏱ {duration} мин"
    "{maybe_link}"
    "{counterparty}"
)

# ── Утренний запрос подтверждения ──

TPL_MORNING_CONFIRM = (
    "👋 <b>Напоминание о встрече сегодня</b>\n\n"
    "📋 {schedule_title}\n"
    "📅 {dt}\n"
    "⏱ {duration} мин\n\n"
    "Встреча в силе?"
)

# ── Pending-уведомление гостю ──

TPL_PENDING_GUEST = (
    "⏳ <b>Встреча сегодня ещё не подтверждена</b>\n\n"
    "📋 {schedule_title}\n"
    "📅 {dt}\n"
    "⏱ {duration} мин\n\n"
    "Мы уведомим вас, как только организатор подтвердит."
)

# ── Статусные уведомления ──

TPL_CONFIRMED = (
    "✅ <b>Встреча подтверждена</b>\n\n"
    "📋 {schedule_title}\n"
    "📅 {dt}"
    "{maybe_link}"
)

TPL_CANCELLED_BY_ORG = (
    "🚫 <b>Встреча отменена организатором</b>\n\n"
    "📋 {schedule_title}\n"
    "📅 {dt}"
)

TPL_CANCELLED_BY_GUEST = (
    "🚫 <b>Встреча отменена гостем</b>\n\n"
    "👤 {guest_name}\n"
    "📋 {schedule_title}\n"
    "📅 {dt}"
)

TPL_GUEST_CONFIRMED = (
    "✅ <b>{guest_name} подтвердил(а) встречу</b>\n\n"
    "📋 {schedule_title}\n"
    "📅 {dt}"
)

TPL_NO_ANSWER = (
    "⚠️ <b>Гость не подтвердил встречу</b>\n\n"
    "👤 {guest_name}\n"
    "📋 {schedule_title}\n"
    "📅 {dt}\n\n"
    "Возможно стоит написать напрямую."
)

# ── Late booking ──

TPL_LATE_BOOKING = (
    "⚡ <b>Встреча скоро</b>\n\n"
    "📋 {schedule_title}\n"
    "📅 {dt}\n"
    "⏱ {duration} мин\n\n"
    "⏰ До встречи: {time_label}"
    "{maybe_link}"
)

# ── Утренняя сводка организатору ──

TPL_MORNING_SUMMARY_HEADER = "📋 <b>Ожидают подтверждения сегодня</b>\n"
TPL_MORNING_SUMMARY_ITEM = "👤 {guest_name} — {dt}, {schedule_title} ({duration} мин)"


def maybe_link_html(meeting_link: str, platform: str = "") -> str:
    """Блок со ссылкой на встречу для вставки в шаблон."""
    if meeting_link and platform in ("jitsi", "zoom", "google_meet"):
        return f"\n🔗 <a href='{meeting_link}'>Подключиться</a>"
    return ""
