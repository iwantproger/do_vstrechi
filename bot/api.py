"""HTTP-клиент к backend API."""
import logging
import aiohttp

from config import BACKEND_URL, INTERNAL_API_KEY

log = logging.getLogger(__name__)


async def api(method: str, path: str, **kwargs) -> dict | list | None:
    url = f"{BACKEND_URL}{path}"
    headers = kwargs.pop("headers", {})
    if INTERNAL_API_KEY:
        headers["X-Internal-Key"] = INTERNAL_API_KEY
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with getattr(session, method)(url, headers=headers, **kwargs) as r:
                if r.status in (200, 201):
                    return await r.json()
                text = await r.text()
                log.error(f"API {method.upper()} {path} → {r.status}: {text}")
                return None
    except Exception as e:
        log.error(f"API error {path}: {e}")
        return None
