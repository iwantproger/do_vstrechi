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
    stats = await conn.fetchrow(
        """
        SELECT
            COUNT(DISTINCT s.id) FILTER (WHERE s.is_active)             AS active_schedules,
            COUNT(b.id)                                                  AS total_bookings,
            COUNT(b.id) FILTER (WHERE b.status = 'pending')             AS pending_bookings,
            COUNT(b.id) FILTER (WHERE b.status = 'confirmed')           AS confirmed_bookings,
            COUNT(b.id) FILTER (WHERE b.scheduled_time > NOW())         AS upcoming_bookings
        FROM schedules s
        LEFT JOIN bookings b ON b.schedule_id = s.id
        JOIN users u ON u.id = s.user_id
        WHERE u.telegram_id = $1
        """,
        telegram_id
    )
    return row_to_dict(stats)
