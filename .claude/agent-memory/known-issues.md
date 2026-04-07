# Известные проблемы и решения

## INC-001: Серый экран nginx (Docker nested bind mounts)
- **Симптом:** nginx не запускается, приложение недоступно (9 часов даунтайма)
- **Причина:** `./admin:/usr/share/nginx/html/admin:ro` вложен внутрь `./frontend:/usr/share/nginx/html:ro`. Docker не может создать mountpoint внутри read-only overlayfs
- **Решение:** убрать `:ro` с родительского маунта frontend. Дочерний admin остаётся `:ro`
- **Правило:** никогда не ставить `:ro` на родительский bind mount если внутрь него вложен другой
- **Документация:** `docs/incidents/INC_001_NGINX_GRAY_SCREEN.md`

## aiogram DefaultBotProperties (parse_mode deprecation)
- **Симптом:** DeprecationWarning при запуске бота: `parse_mode` в конструкторе Bot устарел
- **Причина:** aiogram 3.x перенёс default parse_mode в `DefaultBotProperties`
- **Решение:** `Bot(token=..., default=DefaultBotProperties(parse_mode=ParseMode.HTML))`
- **Коммит:** 47686e5

## HTTP 500 на /api/users/auth при первом деплое
- **Симптом:** 500 при попытке авторизоваться в Mini App после обновления схемы
- **Причина:** отсутствие столбцов timezone и reminder_24h_sent/reminder_1h_sent при UPDATE запросе
- **Решение:** применить миграции 002_add_timezone.sql и 003_add_reminder_flags.sql
- **Коммит:** 7497f40

## Telegram Login Widget HMAC mismatch
- **Симптом:** admin login с Telegram Widget возвращает 403 HMAC mismatch
- **Причина:** CSP блокировал connect-src для oauth.telegram.org; также неверный порядок полей при верификации
- **Решение:** добавить `https://oauth.telegram.org` в CSP connect-src; исправить алгоритм HMAC
- **Коммит:** b9d50e7

## CSP unsafe-eval + Chart.js
- **Симптом:** Chart.js не рендерит графики в admin (CSP ошибка в консоли)
- **Причина:** Chart.js 4.x требует `unsafe-eval` в script-src для некоторых операций
- **Решение:** добавить `'unsafe-eval'` в CSP script-src только для `/admin/` location в nginx.conf; также добавить cdnjs.cloudflare.com в sources
- **Коммит:** c34fc7c

## Гостевое бронирование — UI баги
- **Симптом:** дублирующийся заголовок расписания, спиннер не по центру, успех-экран без текста
- **Решение:** убрать дублирование в шапке, flex justify-content:center для спиннера, добавить subtitle «До встречи!» + кнопку уведомлений
- **Коммит:** 43afb1f

## Дропдаун группировки встреч уходил за экран
- **Симптом:** dropdown «По дате / По расписаниям» частично уходил за правый край
- **Причина:** позиционирование по left вместо right
- **Решение:** `right: window.innerWidth - r.right` для правостороннего выравнивания
- **Коммит:** 4fa0355

## Mask header в fullscreen-режиме
- **Симптом:** шапка не перекрывала контент при скролле
- **Решение:** backdrop-filter blur + корректный z-index для `.inner-header`
- **Коммит:** 6f0043a
