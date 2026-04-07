# /test — Проверить корректность кода

1. Найди все тесты в проекте:
   ```
   find . -name "test_*.py" -o -name "*_test.py" | grep -v __pycache__
   ```

2. Если тесты найдены — запусти их:
   ```
   cd backend && python -m pytest -v
   ```

3. Проверь синтаксис всех Python-файлов:
   ```
   find . -name "*.py" -not -path "./.git/*" -not -path "*/__pycache__/*" \
   | xargs python -m py_compile && echo "✅ Синтаксис OK" || echo "❌ Синтаксические ошибки"
   ```

4. Проверь валидность docker-compose:
   ```
   docker compose config --quiet && echo "✅ docker-compose.yml валиден"
   ```

5. Проверь наличие незапущенных миграций:
   ```
   ls -lt database/migrations/
   ```

6. Выведи итог: что прошло, что упало, что нужно исправить.

Тон — конкретный. Только факты и ошибки, без воды.
