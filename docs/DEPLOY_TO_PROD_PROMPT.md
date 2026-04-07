# Deploy to Production — Процедура

> Этот файл читается Claude Code при запросе деплоя в production.
> Полная процедура будет описана в `docs/deploy-to-prod-ceremony.md`.

## Быстрый старт

Claude Code: прочитай файл `docs/deploy-to-prod-ceremony.md` и выполни его.

Если файл не существует — выполни минимальную процедуру:

1. `git diff main..dev --stat` — покажи пользователю что изменилось
2. `curl -sf https://beta.dovstrechiapp.ru/health` — проверь что beta healthy
3. Спроси подтверждение: "Это задеплоит в PRODUCTION. Подтверди: да/нет"
4. После "да" — спроси ещё раз: "Реальные пользователи будут затронуты. Точно? да/нет"
5. Только после двух "да":
   - `git checkout main && git merge dev --no-edit && git push origin main`
   - Дождись завершения `deploy-prod.yml` workflow
   - `curl -sf https://dovstrechiapp.ru/health` — health-check prod
6. Сообщи результат
