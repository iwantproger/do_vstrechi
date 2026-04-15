"""HTTP-клиент к backend API (persistent session + retry on 5xx)."""
import asyncio
import logging
import aiohttp

from config import BACKEND_URL, INTERNAL_API_KEY

log = logging.getLogger(__name__)

_session: aiohttp.ClientSession | None = None
_lock = asyncio.Lock()


async def get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        async with _lock:
            if _session is None or _session.closed:
                headers = {}
                if INTERNAL_API_KEY:
                    headers["X-Internal-Key"] = INTERNAL_API_KEY
                _session = aiohttp.ClientSession(
                    base_url=BACKEND_URL,
                    timeout=aiohttp.ClientTimeout(total=15, connect=5),
                    headers=headers,
                )
    return _session


async def close_session() -> None:
    global _session
    if _session is not None and not _session.closed:
        try:
            await _session.close()
        except Exception as e:
            log.warning(f"Error closing session: {e}")
    _session = None


async def api(method: str, path: str, **kwargs) -> dict | list | None:
    session = await get_session()
    extra_headers = kwargs.pop("headers", None)
    for attempt in range(2):
        try:
            req_headers = extra_headers or None
            async with session.request(method.upper(), path, headers=req_headers, **kwargs) as r:
                if r.status in (200, 201):
                    return await r.json()
                if 500 <= r.status < 600 and attempt == 0:
                    log.warning(f"API {method.upper()} {path} → {r.status}, retrying in 2s")
                    await asyncio.sleep(2)
                    continue
                text = await r.text()
                log.error(f"API {method.upper()} {path} → {r.status}: {text[:300]}")
                return None
        except asyncio.CancelledError:
            raise
        except Exception as e:
            if attempt == 0:
                log.warning(f"API {method.upper()} {path} transport error: {e}, retrying")
                await asyncio.sleep(2)
                continue
            log.error(f"API error {path}: {e}")
            return None
    return None
