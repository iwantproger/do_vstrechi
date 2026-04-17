"""Роут статистики."""
import asyncpg
from fastapi import APIRouter, Depends

from database import db
from auth import get_current_user
from utils import row_to_dict

router = APIRouter()


@router.get("/api/stats")
async def get_stats(
    auth_user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(db),
):
    telegram_id = auth_user["id"]
    # Rewritten with independent subqueries: avoids the schedules×bookings
    # cartesian fan-out that COUNT(DISTINCT s.id) + LEFT JOIN bookings produces
    # for organizers with many bookings per schedule.
    stats = await conn.fetchrow(
        """
        WITH u AS (
            SELECT id FROM users WHERE telegram_id = $1
        )
        SELECT
            (SELECT COUNT(*) FROM schedules s
              WHERE s.user_id = (SELECT id FROM u) AND s.is_active AND s.is_default = FALSE) AS active_schedules,
            (SELECT COUNT(*) FROM bookings b
              JOIN schedules s ON s.id = b.schedule_id
              WHERE s.user_id = (SELECT id FROM u)) AS total_bookings,
            (SELECT COUNT(*) FROM bookings b
              JOIN schedules s ON s.id = b.schedule_id
              WHERE s.user_id = (SELECT id FROM u) AND b.status = 'pending') AS pending_bookings,
            (SELECT COUNT(*) FROM bookings b
              JOIN schedules s ON s.id = b.schedule_id
              WHERE s.user_id = (SELECT id FROM u) AND b.status = 'confirmed') AS confirmed_bookings,
            (SELECT COUNT(*) FROM bookings b
              JOIN schedules s ON s.id = b.schedule_id
              WHERE s.user_id = (SELECT id FROM u) AND b.scheduled_time > NOW()) AS upcoming_bookings
        """,
        telegram_id
    )
    return row_to_dict(stats)
