# /deploy — Деплой проекта

Выполни полный цикл деплоя на Timeweb VPS:

1. Проверь, что нет незакоммиченных изменений (`git status`)
2. Если есть незакоммиченные изменения — предупреди и предложи /commit
3. Убедись, что текущая ветка — `main`
4. Запусти `git push origin main`
5. Подключись к серверу и выполни обновление:
   ```
   ssh root@109.73.192.69 "cd /opt/dovstrechi && git pull && docker compose up -d --build"
   ```
6. Проверь статус всех контейнеров:
   ```
   ssh root@109.73.192.69 "cd /opt/dovstrechi && docker compose ps"
   ```
7. Проверь последние логи на ошибки:
   ```
   ssh root@109.73.192.69 "cd /opt/dovstrechi && docker compose logs --tail=30"
   ```
8. Выведи итог: какие контейнеры запущены, есть ли ошибки в логах

Если что-то пошло не так — объясни проблему и предложи конкретное решение.

Сервисы: `dovstrechi_postgres`, `dovstrechi_backend`, `dovstrechi_bot`, `dovstrechi_nginx`.
Все четыре должны быть в статусе `Up`.
