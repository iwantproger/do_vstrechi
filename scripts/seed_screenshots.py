#!/usr/bin/env python3
"""Seed beta DB with demo data for marketing screenshots.

Usage:
    python3 scripts/seed_screenshots.py              # seed data
    python3 scripts/seed_screenshots.py --dry-run    # show plan, no writes
    python3 scripts/seed_screenshots.py --reset      # remove seed data

Requires env vars:
    DATABASE_URL          — must contain 'beta' (safety check)
    OWNER_TELEGRAM_ID     — your Telegram ID
    OWNER_USERNAME        — your Telegram username (optional)
    OWNER_FIRST_NAME      — your first name (optional)
"""
import argparse
import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, time as dtime
from zoneinfo import ZoneInfo

import asyncpg

SEED_MARKER = "[SEED]"
TZ_MSK = ZoneInfo("Europe/Moscow")
TZ_UTC = ZoneInfo("UTC")


def generate_meeting_link() -> str:
    """Generate a Jitsi Meet link (standalone, no backend import needed)."""
    room = uuid.uuid4().hex[:12]
    return f"https://meet.jit.si/dovstrechi-{room}"


def check_environment(db_url: str) -> None:
    """Hard-check: only allow beta/dev databases."""
    lower = db_url.lower()
    if "prod" in lower and "beta" not in lower:
        print("❌ BLOCKED: DATABASE_URL contains 'prod'. This script runs only on beta/dev.")
        sys.exit(1)
    if "beta" not in lower and "localhost" not in lower and "127.0.0.1" not in lower:
        print(f"⚠️  WARNING: DATABASE_URL does not contain 'beta': {db_url[:60]}...")
        print("   Proceeding anyway (not blocked), but double-check your target.")


def get_owner_config() -> dict:
    """Read owner info from env vars."""
    tid = os.environ.get("OWNER_TELEGRAM_ID", "")
    if not tid or not tid.isdigit():
        print("❌ OWNER_TELEGRAM_ID env var is required (your numeric Telegram ID).")
        print("   Example: OWNER_TELEGRAM_ID=5109612976 python3 scripts/seed_screenshots.py")
        sys.exit(1)
    return {
        "telegram_id": int(tid),
        "username": os.environ.get("OWNER_USERNAME", ""),
        "first_name": os.environ.get("OWNER_FIRST_NAME", "User"),
    }


SCHEDULES = [
    {
        "title": "Консультация",
        "description": f"Разбираю запрос, даю рекомендации {SEED_MARKER}",
        "duration": 60,
        "buffer_time": 15,
        "work_days": [0, 1, 2, 3, 4],
        "start_time": dtime(10, 0),
        "end_time": dtime(18, 0),
        "platform": "jitsi",
        "requires_confirmation": True,
        "is_default": True,
    },
    {
        "title": "Знакомство",
        "description": f"Короткий созвон, чтобы познакомиться {SEED_MARKER}",
        "duration": 30,
        "buffer_time": 10,
        "work_days": [1, 3],
        "start_time": dtime(14, 0),
        "end_time": dtime(19, 0),
        "platform": "jitsi",
        "requires_confirmation": False,
        "is_default": False,
    },
    {
        "title": "Стратегическая сессия",
        "description": f"Глубокая сессия по продукту {SEED_MARKER}",
        "duration": 90,
        "buffer_time": 30,
        "work_days": [0, 2],
        "start_time": dtime(11, 0),
        "end_time": dtime(16, 0),
        "platform": "jitsi",
        "requires_confirmation": True,
        "is_default": False,
    },
]


def build_bookings(now_msk: datetime) -> list[dict]:
    """Build 8 bookings with times relative to now in Moscow TZ."""
    today = now_msk.date()
    tomorrow = today + timedelta(days=1)
    day_after = today + timedelta(days=2)
    three_days = today + timedelta(days=3)
    yesterday = today - timedelta(days=1)
    three_ago = today - timedelta(days=3)

    def msk_dt(d, h, m=0):
        """Create a datetime in Moscow TZ, convert to UTC. Clamps hour to 0-23."""
        h = max(0, min(23, h))
        return datetime(d.year, d.month, d.day, h, m, tzinfo=TZ_MSK).astimezone(TZ_UTC)

    # Round current hour up to next whole hour for "today" meetings
    next_hour = now_msk.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)

    return [
        {
            "schedule_title": "Консультация",
            "guest_name": "Мария Соколова",
            "scheduled_time": msk_dt(today, next_hour.hour + 2),
            "status": "confirmed",
            "has_link": True,
            "notes": f"{SEED_MARKER} Хочу обсудить переход с фриланса",
        },
        {
            "schedule_title": "Знакомство",
            "guest_name": "Алексей Петров",
            "scheduled_time": msk_dt(today, next_hour.hour + 5),
            "status": "confirmed",
            "has_link": True,
            "notes": SEED_MARKER,
        },
        {
            "schedule_title": "Консультация",
            "guest_name": "Ольга Иванова",
            "scheduled_time": msk_dt(tomorrow, 11),
            "status": "pending",
            "has_link": False,
            "notes": f"{SEED_MARKER} Помогите разобраться с продуктом",
        },
        {
            "schedule_title": "Стратегическая сессия",
            "guest_name": "Дмитрий Козлов",
            "scheduled_time": msk_dt(tomorrow, 15),
            "status": "confirmed",
            "has_link": True,
            "notes": f"{SEED_MARKER} Обсудить роадмап на Q3",
        },
        {
            "schedule_title": "Консультация",
            "guest_name": "Анна Смирнова",
            "scheduled_time": msk_dt(day_after, 12),
            "status": "pending",
            "has_link": False,
            "notes": SEED_MARKER,
        },
        {
            "schedule_title": "Знакомство",
            "guest_name": "Игорь Васильев",
            "scheduled_time": msk_dt(three_days, 16),
            "status": "confirmed",
            "has_link": True,
            "notes": SEED_MARKER,
        },
        {
            "schedule_title": "Консультация",
            "guest_name": "Елена Морозова",
            "scheduled_time": msk_dt(yesterday, 14),
            "status": "completed",
            "has_link": True,
            "notes": f"{SEED_MARKER} Спасибо, было полезно!",
        },
        {
            "schedule_title": "Консультация",
            "guest_name": "Сергей Лебедев",
            "scheduled_time": msk_dt(three_ago, 14),
            "status": "cancelled",
            "has_link": False,
            "notes": SEED_MARKER,
        },
    ]


async def seed(conn: asyncpg.Connection, owner: dict, dry_run: bool) -> None:
    """Insert demo data into the database."""
    now_msk = datetime.now(TZ_MSK)
    bookings_data = build_bookings(now_msk)

    if dry_run:
        print("\n📋 DRY RUN — план без записи в БД\n")
        print(f"  Owner: {owner['first_name']} (@{owner['username']}, tid={owner['telegram_id']})")
        print(f"  Timezone: Europe/Moscow, now = {now_msk.strftime('%Y-%m-%d %H:%M')}\n")
        print("  Schedules (3):")
        for s in SCHEDULES:
            _dn = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
            days = ",".join(_dn[d] if d < len(_dn) else "?" for d in s["work_days"])
            dflt = " (default)" if s["is_default"] else ""
            print(f"    - {s['title']} ({s['duration']} мин, {days} {s['start_time']}-{s['end_time']}){dflt}")
        print(f"\n  Bookings (8):")
        for b in bookings_data:
            t_msk = b["scheduled_time"].astimezone(TZ_MSK)
            t_utc = b["scheduled_time"]
            link = "✓" if b["has_link"] else "—"
            print(f"    - {b['guest_name']:20s} | {b['status']:10s} | {t_msk:%d.%m %H:%M} МСК ({t_utc:%H:%M} UTC) | link={link}")
        print("\n  ✅ Dry run complete — no changes made.")
        return

    # 1. UPSERT owner user
    user_row = await conn.fetchrow("""
        INSERT INTO users (telegram_id, username, first_name, timezone)
        VALUES ($1, $2, $3, 'Europe/Moscow')
        ON CONFLICT (telegram_id) DO UPDATE
            SET username = EXCLUDED.username,
                first_name = EXCLUDED.first_name,
                timezone = 'Europe/Moscow',
                updated_at = NOW()
        RETURNING id, first_name
    """, owner["telegram_id"], owner["username"], owner["first_name"])
    user_id = user_row["id"]
    print(f"  👤 User: {user_row['first_name']} (id={user_id}, tid={owner['telegram_id']})")

    # 2. Clean old seed data (bookings first → then schedules, FK order)
    del_b = await conn.execute("""
        DELETE FROM bookings
        WHERE notes LIKE '[SEED]%'
          AND schedule_id IN (SELECT id FROM schedules WHERE user_id = $1)
    """, user_id)
    del_s = await conn.execute("""
        DELETE FROM schedules
        WHERE user_id = $1 AND description LIKE '%[SEED]%'
    """, user_id)
    print(f"  🧹 Cleaned old seed: {del_s}, {del_b}")

    # 3. Insert schedules
    schedule_ids = {}
    for s in SCHEDULES:
        row = await conn.fetchrow("""
            INSERT INTO schedules
                (user_id, title, description, duration, buffer_time,
                 work_days, start_time, end_time, platform,
                 requires_confirmation, is_active, is_default)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, TRUE, $11)
            RETURNING id
        """,
            user_id, s["title"], s["description"], s["duration"], s["buffer_time"],
            s["work_days"], s["start_time"], s["end_time"], s["platform"],
            s["requires_confirmation"], s["is_default"],
        )
        schedule_ids[s["title"]] = row["id"]
        dflt = " (default)" if s["is_default"] else ""
        print(f"  📅 Schedule: {s['title']} ({s['duration']} мин){dflt}")

    # 4. Insert bookings
    status_counts = {}
    for b in bookings_data:
        sid = schedule_ids[b["schedule_title"]]
        link = generate_meeting_link() if b["has_link"] else None
        await conn.execute("""
            INSERT INTO bookings
                (schedule_id, guest_name, guest_contact, scheduled_time,
                 status, meeting_link, notes)
            VALUES ($1, $2, '', $3, $4, $5, $6)
        """, sid, b["guest_name"], b["scheduled_time"], b["status"], link, b["notes"])
        status_counts[b["status"]] = status_counts.get(b["status"], 0) + 1

    print(f"\n✅ Seed complete")
    print(f"  Schedules: {len(SCHEDULES)}")
    print(f"  Bookings:  {len(bookings_data)}")
    for st, cnt in sorted(status_counts.items()):
        print(f"    {st}: {cnt}")

    # Count today's meetings
    today_start = datetime(now_msk.year, now_msk.month, now_msk.day, tzinfo=TZ_MSK).astimezone(TZ_UTC)
    today_end = today_start + timedelta(days=1)
    today_count = sum(
        1 for b in bookings_data
        if today_start <= b["scheduled_time"] < today_end
        and b["status"] in ("confirmed", "pending")
    )
    pending_count = status_counts.get("pending", 0)

    print(f"\n📱 Next steps:")
    print(f"  1. Открой @beta_do_vstrechi_bot и нажми /start")
    print(f"  2. Открой Mini App → главный экран")
    print(f"  3. Ожидаемо: {today_count} встреч сегодня, {pending_count} ожидают подтверждения")


async def reset(conn: asyncpg.Connection, owner: dict) -> None:
    """Remove all seed data, keep the user."""
    user_row = await conn.fetchrow(
        "SELECT id FROM users WHERE telegram_id = $1", owner["telegram_id"]
    )
    if not user_row:
        print("⚠️  User not found in DB, nothing to reset.")
        return
    user_id = user_row["id"]

    del_b = await conn.execute("""
        DELETE FROM bookings
        WHERE notes LIKE '[SEED]%'
          AND schedule_id IN (SELECT id FROM schedules WHERE user_id = $1)
    """, user_id)
    del_s = await conn.execute("""
        DELETE FROM schedules
        WHERE user_id = $1 AND description LIKE '%[SEED]%'
    """, user_id)

    b_count = int(del_b.split()[-1])
    s_count = int(del_s.split()[-1])

    print(f"\n🧹 Reset complete")
    print(f"  Deleted bookings:  {b_count}")
    print(f"  Deleted schedules: {s_count}")
    print(f"  User: сохранён (tid={owner['telegram_id']})")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Seed beta DB with demo data for screenshots")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without writing to DB")
    parser.add_argument("--reset", action="store_true", help="Remove all seed data and exit")
    parser.add_argument("--force-prod", action="store_true", help="Allow running on production DB")
    args = parser.parse_args()

    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        print("❌ DATABASE_URL env var is required.")
        sys.exit(1)

    if args.force_prod:
        print("⚠️  --force-prod: production safety check bypassed")
    else:
        check_environment(db_url)
    owner = get_owner_config()

    if args.dry_run:
        # Dry run doesn't need a DB connection
        conn_stub = None
        await seed(conn_stub, owner, dry_run=True)
        return

    conn = await asyncpg.connect(db_url)
    try:
        # Bypass RLS for direct DB access
        await conn.execute("SET app.is_internal = 'true'")

        if args.reset:
            await reset(conn, owner)
        else:
            await seed(conn, owner, dry_run=False)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
