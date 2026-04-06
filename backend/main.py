"""
До встречи — Backend API
FastAPI + asyncpg (PostgreSQL)
"""
import sys
import logging
import time as _time
from contextlib import asynccontextmanager

import structlog
import asyncpg
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

import uuid

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)
log = structlog.get_logger()

from config import CORS_ORIGINS, APP_VERSION
from database import init_pool, close_pool, run_migrations, get_pool, db
from utils import _track_event, anonymize_id

from routers import users, schedules, bookings, meetings, stats, admin as admin_router


# ─────────────────────────────────────────────────────────
# Lifespan
# ─────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    await run_migrations()
    yield
    await close_pool()


# ─────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────

app = FastAPI(title="До встречи API", version=APP_VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-Init-Data"],
)


class StructlogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = uuid.uuid4().hex[:8]
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )
        start = _time.monotonic()
        response = await call_next(request)
        duration_ms = round((_time.monotonic() - start) * 1000, 1)
        if request.url.path not in ("/", "/health"):
            log.info(
                "request_handled",
                status_code=response.status_code,
                duration_ms=duration_ms,
            )
        response.headers["X-Request-ID"] = request_id
        return response


app.add_middleware(StructlogMiddleware)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log.error("unhandled_exception", exc_type=type(exc).__name__, detail=str(exc)[:500])
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await _track_event(conn, "error", 0, {
                "exc_type": type(exc).__name__,
                "detail": str(exc)[:500],
                "path": request.url.path,
                "method": request.method,
            }, severity="error")
    except Exception:
        pass
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# ─────────────────────────────────────────────────────────
# Routers
# ─────────────────────────────────────────────────────────

app.include_router(users.router)
app.include_router(schedules.router)
app.include_router(bookings.router)
app.include_router(meetings.router)
app.include_router(stats.router)
app.include_router(admin_router.router)


# ─────────────────────────────────────────────────────────
# Health
# ─────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"message": "До встречи API", "version": APP_VERSION, "status": "running"}


@app.get("/health")
async def health(conn: asyncpg.Connection = Depends(db)):
    try:
        await conn.fetchval("SELECT 1")
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        log.error("health_check_failed", error=str(e))
        raise HTTPException(status_code=503, detail="Database unavailable")
