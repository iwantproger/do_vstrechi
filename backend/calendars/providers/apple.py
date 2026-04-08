"""Apple iCloud Calendar провайдер (CalDAV).

Особенности:
- CalDAV URL: https://caldav.icloud.com/ → редиректит на pXX-caldav.icloud.com
  (requests/caldav обрабатывают редирект автоматически; BasicAuth отправляется
  с каждым запросом, включая прямые запросы к pXX-хосту)
- Аутентификация: Apple ID email + пароль приложения (appleid.apple.com → App Passwords)
- Нет OAuth, нет webhooks
- Только full PUT при обновлении (библиотека делает это по умолчанию)
"""

from calendars.providers.caldav_adapter import CalDAVCalendarProvider


class AppleCalendarProvider(CalDAVCalendarProvider):
    """Apple iCloud Calendar через CalDAV."""

    provider_name = "apple"
    default_url = "https://caldav.icloud.com/"
