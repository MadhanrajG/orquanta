"""OrQuanta Agentic v1.0 — API Rate Limiting Middleware."""

from __future__ import annotations

import logging
import os
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

logger = logging.getLogger("orquanta.ratelimit")

RATE_LIMIT_REQUESTS = int(os.getenv("API_RATE_LIMIT_REQUESTS", "60"))
RATE_LIMIT_WINDOW_S = int(os.getenv("API_RATE_LIMIT_WINDOW_S", "60"))


class RateLimiter:
    """Sliding-window rate limiter (per IP address).
    
    Default: 60 requests per 60 seconds per client IP.
    Configure via API_RATE_LIMIT_REQUESTS and API_RATE_LIMIT_WINDOW_S env vars.
    """

    def __init__(self) -> None:
        self._windows: dict[str, deque] = defaultdict(deque)
        self.limit = RATE_LIMIT_REQUESTS
        self.window = RATE_LIMIT_WINDOW_S

    def check(self, identifier: str) -> None:
        """Check if the identifier (IP) is within rate limits.
        
        Args:
            identifier: Client IP or user ID.
            
        Raises:
            HTTPException 429: If rate limit exceeded.
        """
        now = time.monotonic()
        window = self._windows[identifier]

        # Remove expired timestamps
        while window and window[0] < now - self.window:
            window.popleft()

        if len(window) >= self.limit:
            retry_after = int(self.window - (now - window[0]))
            logger.warning(f"[RateLimit] {identifier} exceeded {self.limit} req/{self.window}s")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Rate limit exceeded: {self.limit} requests per {self.window} seconds. "
                    f"Retry after {retry_after} seconds."
                ),
                headers={"Retry-After": str(retry_after)},
            )

        window.append(now)

    def get_stats(self) -> dict[str, int]:
        """Return rate limiter statistics."""
        return {
            "tracked_clients": len(self._windows),
            "limit": self.limit,
            "window_seconds": self.window,
        }


# Module-level singleton
_limiter = RateLimiter()


async def rate_limit_dependency(request: Request) -> None:
    """FastAPI dependency: apply rate limiting per client IP."""
    client_ip = request.client.host if request.client else "unknown"
    # Exemptions: health check endpoint
    if request.url.path in ["/health", "/", "/docs", "/openapi.json"]:
        return
    _limiter.check(client_ip)
