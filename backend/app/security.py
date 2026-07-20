"""Abuse protection: access-code gate, per-IP rate limiting, spend guard.

The API key is a server-side secret and is never sent to the browser, so it
cannot be stolen — the threat is abuse of the endpoints that *spend* it. These
layers bound the worst case; the true backstop is a credit-capped OpenRouter
key (provider-enforced, outside this code).
"""

import hmac
from datetime import datetime, timezone

from fastapi import Header, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from .config import settings


def _client_ip(request: Request) -> str:
    """Real client IP behind HF Spaces' / Vercel's proxy."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(key_func=_client_ip)

# Rate strings shared by the query endpoints' decorators
RATE_LIMITS = f"{settings.rate_limit_per_min}/minute;{settings.rate_limit_per_day}/day"


async def require_access(x_access_code: str = Header(default="")) -> None:
    """Dependency: gate every /api/* route behind the shared access code.

    Empty ACCESS_CODE disables the gate (local dev). Constant-time compare so
    the check can't be timing-probed.
    """
    expected = settings.access_code
    if not expected:
        return
    if not hmac.compare_digest(x_access_code, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing access code")


class SpendGuard:
    """In-memory daily spend ceiling (UTC day). Resets on restart, which is
    fine: the credit-capped OpenRouter key is the real backstop, this is just
    the graceful early stop."""

    def __init__(self) -> None:
        self._day = ""
        self._spent = 0.0

    def _roll(self) -> None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if today != self._day:
            self._day, self._spent = today, 0.0

    def check(self) -> None:
        """Raise 503 if today's spend is already over the limit."""
        self._roll()
        if self._spent >= settings.daily_spend_limit_usd:
            raise HTTPException(
                status_code=503,
                detail="Daily budget reached — try again tomorrow.",
            )

    def add(self, cost_usd: float) -> None:
        self._roll()
        self._spent += max(cost_usd, 0.0)

    @property
    def spent_today(self) -> float:
        self._roll()
        return self._spent


spend_guard = SpendGuard()
