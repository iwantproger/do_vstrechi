"""Calendar Abstraction Layer — единый интерфейс для внешних календарей."""

from calendars.base import CalendarProvider
from calendars.registry import get_provider, register_provider, get_all_providers

__all__ = [
    "CalendarProvider",
    "get_provider",
    "register_provider",
    "get_all_providers",
]
