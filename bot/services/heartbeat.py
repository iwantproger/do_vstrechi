"""Bot heartbeat — sends periodic alive signal to backend."""
import asyncio
import time
import logging

from api import api

log = logging.getLogger(__name__)

_start_time = time.time()


async def heartbeat_loop():
    """Send heartbeat every 60 seconds. Never raises — logs errors internally."""
    await asyncio.sleep(15)  # wait for backend to be ready
    log.info("Heartbeat loop started")

    while True:
        try:
            uptime = int(time.time() - _start_time)
            await api("post", "/api/internal/bot-heartbeat", json={
                "status": "alive",
                "uptime_sec": uptime,
            })
        except Exception as e:
            log.warning(f"Heartbeat failed: {e}")
        await asyncio.sleep(60)
