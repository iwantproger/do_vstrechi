"""Реестр провайдеров календарей."""

from calendars.base import CalendarProvider

_providers: dict[str, CalendarProvider] = {}


def register_provider(name: str, provider: CalendarProvider) -> None:
    """Зарегистрировать провайдер (вызывается при импорте адаптера)."""
    _providers[name] = provider


def get_provider(name: str) -> CalendarProvider:
    """Получить провайдер по имени (google, yandex, apple, outlook)."""
    if name not in _providers:
        available = ", ".join(sorted(_providers)) or "(нет зарегистрированных)"
        raise KeyError(
            f"Calendar provider '{name}' not registered. "
            f"Available: {available}"
        )
    return _providers[name]


def get_all_providers() -> dict[str, CalendarProvider]:
    """Все зарегистрированные провайдеры."""
    return dict(_providers)
