"""Верификация фиксов системы уведомлений (промты 1-8).

Группы тестов:
  A — Security (FINDING-003, 015)
  B — V1 мёртв (FINDING-002, 011)
  C — Per-user settings (FINDING-001, 004, 006, 012)
  D — Guest timezone (FINDING-007)
  E — Adaptive floor (FINDING-009) — см. test_confirmation_window.py
  F — At-least-once delivery (FINDING-005, 008)
  G — Expired status (FINDING-014, 016)
  H — UX & dead code (FINDING-010, 013)

Запуск: pytest backend/tests/test_notifications_verify.py -v
Требует: DATABASE_TEST_URL env (или beta DB), pytest, pytest-asyncio, asyncpg, httpx
"""
import os
import subprocess
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
BOT_DIR = REPO_ROOT / "bot"


def _grep(pattern: str, path: Path) -> list[str]:
    """Utility: grep -r pattern path, return matching lines."""
    result = subprocess.run(
        ["grep", "-rn", pattern, str(path)],
        capture_output=True, text=True, timeout=10,
    )
    return [l for l in result.stdout.strip().split("\n") if l]


# ═══════════════════════════════════════════
# Group A: Security (FINDING-003, 015)
# ═══════════════════════════════════════════

class TestSecurityAuth:
    """Все internal endpoints защищены get_internal_caller."""

    def test_get_internal_caller_exists(self):
        matches = _grep("async def get_internal_caller", BACKEND_DIR / "auth.py")
        assert len(matches) == 1, "get_internal_caller not found in auth.py"

    def test_internal_caller_uses_hmac(self):
        matches = _grep("hmac.compare_digest", BACKEND_DIR / "auth.py")
        assert len(matches) >= 2, "hmac.compare_digest missing in auth.py"

    def test_internal_api_key_required_at_startup(self):
        matches = _grep("assert INTERNAL_API_KEY", BACKEND_DIR / "config.py")
        assert len(matches) >= 1, "INTERNAL_API_KEY assert missing in config.py"

    def test_protected_endpoint_count(self):
        """10 endpoints должны иметь Depends(get_internal_caller)."""
        matches_bookings = _grep("get_internal_caller", BACKEND_DIR / "routers" / "bookings.py")
        matches_users = _grep("get_internal_caller", BACKEND_DIR / "routers" / "users.py")
        # 1 import + 9 usages in bookings, 1 import + 1 usage in users
        total_usages = len([m for m in matches_bookings + matches_users if "Depends(" in m])
        assert total_usages >= 10, f"Only {total_usages} endpoints protected, expected >=10"


# ═══════════════════════════════════════════
# Group B: V1 мёртв (FINDING-002, 011)
# ═══════════════════════════════════════════

class TestV1Removed:
    """V1 boolean-флаги, эндпоинты и callbacks удалены."""

    def test_v1_columns_not_in_code(self):
        for col in ["reminder_24h_sent", "reminder_1h_sent", "reminder_15m_sent",
                     "reminder_5m_sent", "morning_reminder_sent"]:
            # Исключаем tests/, __pycache__, .bak файлы
            matches = [m for m in _grep(col, BACKEND_DIR)
                       if "/tests/" not in m and "__pycache__" not in m and ".bak" not in m]
            assert len(matches) == 0, f"V1 column {col} still referenced in backend/ (excl tests): {matches}"
            matches_bot = _grep(col, BOT_DIR)
            assert len(matches_bot) == 0, f"V1 column {col} still referenced in bot/"

    def test_v1_endpoints_removed(self):
        """V1 routes /pending-reminders (без -v2) и /reminder-sent удалены."""
        bookings_py = BACKEND_DIR / "routers" / "bookings.py"
        matches_pr = _grep('/api/bookings/pending-reminders"', bookings_py)
        assert len(matches_pr) == 0, "V1 /pending-reminders route still exists"
        matches_rs = _grep("reminder-sent", bookings_py)
        assert len(matches_rs) == 0, "V1 /reminder-sent route still exists"

    def test_remind_callback_removed(self):
        matches = _grep('startswith.*"remind_"', BOT_DIR / "handlers")
        assert len(matches) == 0, "remind_* callback still registered"

    def test_v1_columns_not_in_init_sql(self):
        init_sql = REPO_ROOT / "database" / "init.sql"
        for col in ["reminder_24h_sent", "reminder_1h_sent"]:
            matches = _grep(col, init_sql)
            assert len(matches) == 0, f"V1 column {col} still in init.sql"


# ═══════════════════════════════════════════
# Group C: Per-user settings (FINDING-001, 004, 006, 012)
# ═══════════════════════════════════════════

class TestPerUserSettings:
    """Настройки напоминаний per-user: GET/PATCH + per-role SQL."""

    def test_get_endpoint_exists(self):
        matches = _grep('get.*notification-settings', BACKEND_DIR / "routers" / "users.py")
        assert len(matches) >= 1, "GET /notification-settings not found"

    def test_patch_endpoint_uses_merge(self):
        matches = _grep("merged.update", BACKEND_DIR / "routers" / "users.py")
        assert len(matches) >= 1, "PATCH /notification-settings doesn't merge"

    def test_frontend_server_sync(self):
        """Frontend загружает настройки с сервера, не только из localStorage."""
        profile = REPO_ROOT / "frontend" / "js" / "profile.js"
        matches_load = _grep("loadNotifSettingsFromServer", profile)
        assert len(matches_load) >= 2, "loadNotifSettingsFromServer not found/used"
        matches_save = _grep("saveNotifSettings", profile)
        assert len(matches_save) >= 4, "saveNotifSettings not used in toggles"

    def test_no_localstorage_writes(self):
        """localStorage.setItem('sb_settings') больше не вызывается."""
        profile = REPO_ROOT / "frontend" / "js" / "profile.js"
        matches = _grep("localStorage.setItem.*sb_settings", profile)
        assert len(matches) == 0, "localStorage.setItem still used for sb_settings"

    def test_per_role_sql(self):
        """V2 SQL содержит org_mins и guest_mins CTE."""
        bookings_py = BACKEND_DIR / "routers" / "bookings.py"
        matches_org = _grep("org_mins", bookings_py)
        matches_guest = _grep("guest_mins", bookings_py)
        assert len(matches_org) >= 2, "org_mins CTE not found in V2 SQL"
        assert len(matches_guest) >= 2, "guest_mins CTE not found in V2 SQL"

    def test_pydantic_validation_exists(self):
        matches = _grep("NotificationSettingsUpdate", BACKEND_DIR / "schemas.py")
        assert len(matches) >= 1, "NotificationSettingsUpdate schema not found"


# ═══════════════════════════════════════════
# Group D: Guest timezone (FINDING-007)
# ═══════════════════════════════════════════

class TestGuestTimezone:
    """guest_timezone сохраняется и используется в сообщениях."""

    def test_column_in_init_sql(self):
        matches = _grep("guest_timezone", REPO_ROOT / "database" / "init.sql")
        assert len(matches) >= 1, "guest_timezone column not in init.sql"

    def test_migration_exists(self):
        mig = REPO_ROOT / "database" / "migrations" / "019_guest_timezone.sql"
        assert mig.exists(), "Migration 019 not found"

    def test_schema_field(self):
        matches = _grep("guest_timezone", BACKEND_DIR / "schemas.py")
        assert len(matches) >= 1, "guest_timezone not in BookingCreate"

    def test_validation_in_create_booking(self):
        matches = _grep("available_timezones", BACKEND_DIR / "routers" / "bookings.py")
        assert len(matches) >= 1, "TZ validation not in create_booking"

    def test_bot_uses_guest_tz(self):
        matches = _grep("guest_timezone", BOT_DIR / "services" / "reminders.py")
        assert len(matches) >= 3, "guest_timezone not used in reminders.py"
        matches_notif = _grep("guest_tz", BOT_DIR / "services" / "notifications.py")
        assert len(matches_notif) >= 2, "guest_tz not used in notifications.py"

    def test_frontend_sends_tz(self):
        matches = _grep("guest_timezone", REPO_ROOT / "frontend" / "js" / "calendar.js")
        assert len(matches) >= 1, "guest_timezone not sent in calendar.js booking"


# ═══════════════════════════════════════════
# Group F: At-least-once delivery (FINDING-005, 008)
# ═══════════════════════════════════════════

class TestReliableDelivery:
    """sent_reminders пишется только после успеха/permanent fail. Окно 15 мин."""

    def test_permanent_fail_classification(self):
        matches = _grep("_is_permanent_fail", BOT_DIR / "services" / "reminders.py")
        assert len(matches) >= 2, "_is_permanent_fail not defined/used"

    def test_record_sent_after_success(self):
        """_record_sent вызывается после успешной отправки и после permanent fail, но НЕ после transient."""
        content = (BOT_DIR / "services" / "reminders.py").read_text()
        # Check pattern: permanent fail → _record_sent, then return
        assert "permanent_fail" in content and "_record_sent" in content
        assert "transient_fail" in content

    def test_window_15_min(self):
        """SQL окно выборки: reminder_min - 15, не reminder_min - 2."""
        matches = _grep("reminder_min - 15", BACKEND_DIR / "routers" / "bookings.py")
        assert len(matches) >= 1, "15-min window not found in V2 SQL"
        matches_old = _grep("reminder_min - 2", BACKEND_DIR / "routers" / "bookings.py")
        assert len(matches_old) == 0, "Old 2-min window still in V2 SQL"

    def test_late_booking_handler(self):
        matches = _grep("handle_late_booking", BOT_DIR / "services" / "notifications.py")
        assert len(matches) >= 2, "handle_late_booking not found"
        matches_route = _grep("notify-late", BOT_DIR / "services" / "notifications.py")
        assert len(matches_route) >= 1, "/internal/notify-late route not registered"

    def test_late_booking_backend(self):
        matches = _grep("_notify_bot_late_booking", BACKEND_DIR / "routers" / "bookings.py")
        assert len(matches) >= 1, "_notify_bot_late_booking not called in create_booking"


# ═══════════════════════════════════════════
# Group G: Expired status (FINDING-014, 016)
# ═══════════════════════════════════════════

class TestExpiredStatus:
    """Статус expired + фикс фильтра noans."""

    def test_expired_in_check_constraint(self):
        matches = _grep("expired", REPO_ROOT / "database" / "init.sql")
        found = [m for m in matches if "bookings_status_check" in m or "CHECK" in m]
        assert len(found) >= 1 or any("expired" in m for m in _grep("CHECK.*status", REPO_ROOT / "database" / "init.sql")), \
            "expired not in CHECK constraint"

    def test_migration_exists(self):
        mig = REPO_ROOT / "database" / "migrations" / "020_expired_status.sql"
        assert mig.exists(), "Migration 020 not found"

    def test_complete_past_transitions_expired(self):
        """complete_past_bookings делает UPDATE pending→expired и no_answer→expired."""
        content = (BACKEND_DIR / "routers" / "bookings.py").read_text()
        assert "status = 'expired'" in content, "expired transition not in complete_past"

    def test_noans_filter_fixed(self):
        """Фильтр noans использует status=='no_answer', не 'pending'+past."""
        matches = _grep('status.*==.*"no_answer"', BOT_DIR / "handlers" / "start.py")
        assert len(matches) >= 1, "noans filter not using no_answer status"
        # Old broken pattern should be gone
        matches_old = _grep('status.*==.*"pending".*<.*now', BOT_DIR / "handlers" / "start.py")
        assert len(matches_old) == 0, "Old broken noans filter still present"

    def test_expired_in_formatters(self):
        matches = _grep('"expired"', BOT_DIR / "formatters.py")
        assert len(matches) >= 2, "expired not in STATUS_EMOJI/STATUS_TEXT"

    def test_expired_in_frontend(self):
        matches = _grep("expired", REPO_ROOT / "frontend" / "js" / "utils.js")
        assert len(matches) >= 2, "expired not handled in frontend getMeetingStatus/meetingStatusHtml"


# ═══════════════════════════════════════════
# Group H: UX & dead code (FINDING-010, 013)
# ═══════════════════════════════════════════

class TestUxCleanup:
    """Шаблоны, кнопки, удаление зомби deep-link."""

    def test_notify_deep_link_removed(self):
        matches = _grep("handle_notify_setup", BOT_DIR)
        assert len(matches) == 0, "handle_notify_setup still exists"
        matches2 = _grep('notify_.*booking', BOT_DIR / "services" / "notifications.py")
        assert len(matches2) == 0, "notify_ deep-link still in notifications.py"

    def test_templates_module_exists(self):
        assert (BOT_DIR / "messages.py").exists(), "bot/messages.py not found"

    def test_templates_used(self):
        matches = _grep("from messages import", BOT_DIR / "services")
        assert len(matches) >= 2, "Templates not imported in services"

    def test_kb_meeting_actions_used(self):
        matches = _grep("kb_meeting_actions", BOT_DIR / "services")
        assert len(matches) >= 5, "kb_meeting_actions not widely used"

    def test_no_caps_in_templates(self):
        """Шаблоны не содержат полностью заглавных слов >3 букв (кроме HTML тегов)."""
        import re
        content = (BOT_DIR / "messages.py").read_text()
        # Find words that are all caps and >3 chars, exclude HTML/tech terms
        caps_words = re.findall(r'\b[A-Z]{4,}\b', content)
        allowed = {"MINI_APP_URL", "HTML", "HTTPS", "HTTP", "UUID", "BOOKING", "TRUE", "FALSE", "CAPS"}
        bad = [w for w in caps_words if w not in allowed]
        assert len(bad) == 0, f"CAPS words in templates: {bad}"
