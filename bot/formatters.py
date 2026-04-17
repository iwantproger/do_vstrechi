"""Форматтеры: статусы, даты, бронирования, share-сообщения."""
from datetime import datetime
from zoneinfo import ZoneInfo

from config import BOT_USERNAME, MINI_APP_URL

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


def browser_link(schedule_id: str) -> str:
    return f"{MINI_APP_URL}?schedule_id={schedule_id}"


def format_share_message_html(schedule_id: str) -> str:
    """Единый HTML-текст приглашения на бронирование.

    НЕ используем <a href> для t.me ссылок — Telegram открывает их
    в in-app браузере вместо Mini App. Кнопка «Записаться» в
    reply_markup (inline keyboard) — основной путь запуска Mini App.
    """
    tg_link = direct_link(schedule_id)
    web_link = browser_link(schedule_id)
    return (
        f"Вот мои свободные слоты — выбирайте удобное время!\n\n"
        f"До встречи! 🙌\n\n"
        f'Или <a href="{web_link}">открыть в браузере</a>\n\n'
        f"Ссылка для копирования:\n"
        f"<code>{tg_link}</code>"
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
