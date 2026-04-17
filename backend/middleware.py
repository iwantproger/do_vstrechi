"""RLS context middleware — sets telegram_id and is_internal on every request."""
import hmac

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from auth import validate_init_data
from config import BOT_TOKEN, INTERNAL_API_KEY


class RLSMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        telegram_id = None
        is_internal = False

        internal_key = request.headers.get("X-Internal-Key")
        if internal_key and INTERNAL_API_KEY and hmac.compare_digest(internal_key, INTERNAL_API_KEY):
            is_internal = True
            tid = request.query_params.get("telegram_id")
            if tid:
                try:
                    telegram_id = int(tid)
                except ValueError:
                    pass

        if not telegram_id and not is_internal:
            init_data = request.headers.get("X-Init-Data")
            if init_data:
                user = validate_init_data(init_data, BOT_TOKEN)
                if user:
                    telegram_id = user.get("id")

        request.state.telegram_id = telegram_id
        request.state.is_internal = is_internal

        return await call_next(request)
