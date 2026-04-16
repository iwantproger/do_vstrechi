"""Форматтеры: статусы, даты, бронирования, share-сообщения."""
from datetime import datetime
from zoneinfo import ZoneInfo

from config import BOT_USERNAME

STATUS_EMOJI = {
    "pending":   "⏳",
    "confirmed": "✅",
    "cancelled": "❌",
    "completed": "✓",
    "no_answer": "⚠️",
}
STATUS_TEXT = {
    "pending":    "Ожидает",
    "confirmed":  "Подтверждена",
    "cancelled":  "Отменена",
    "completed":  "Завершена",
    "no_answer":  "Нет ответа",
}
DAYS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def format_dt(dt_str: str, tz: str = "UTC") -> str:
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        local_dt = dt.astimezone(ZoneInfo(tz))
        return local_dt.strftime("%d.%m.%Y %H:%M")
    except Exception:
        return dt_str


def direct_link(schedule_id: str) -> str:
    return f"https://t.me/{BOT_USERNAME}/app?startapp={schedule_id}"


def format_share_message_html(schedule_id: str) -> str:
    """Единый HTML-текст приглашения на бронирование (все точки шаринга)."""
    link = direct_link(schedule_id)
    return (
        f"Вот мои свободные слоты — выбирайте удобное время:\n"
        f'👉 <a href="{link}">Записаться на встречу</a>\n\n'
        f"До встречи! 🙌\n\n"
        f"Если ссылка не открывается, скопируй:\n"
        f"<code>{link}</code>"
    )


def format_booking(b: dict, show_role: bool = False) -> str:
    emoji  = STATUS_EMOJI.get(b["status"], "?")
    status = STATUS_TEXT.get(b["status"], b["status"])
    dt     = format_dt(b["scheduled_time"], tz=b.get("organizer_timezone") or "UTC")
    lines  = [
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
