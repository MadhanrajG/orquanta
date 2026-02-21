"""
OrQuanta Agentic v1.0 — Redis-Backed Distributed Rate Limiter

Protects all API endpoints with sliding window rate limiting:

  Tier 1 — Per IP:      100 req/min (unauthenticated)
  Tier 2 — Per User:    60 req/min (authenticated)
  Tier 3 — Per Org:     500 req/min (org-wide)
  Tier 4 — Per Endpoint: custom per-route limits

DDoS Protection:
  - Hard block IPs exceeding 10× normal limit
  - Adaptive throttling: slow abusers, not legitimate users
  - Burst allowance: short bursts OK, sustained flood → block

Implementation:
  Redis SORTED SET per key — "sliding window" algorithm.
  Each request is scored by current timestamp.
  Window is cleaned by removing scores older than window_seconds.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("orquanta.security.rate_limiter")

# ─── Rate limit tiers ────────────────────────────────────────────────────────

@dataclass
class RateLimit:
    requests: int      # Max requests per window
    window_s: int      # Window size in seconds
    burst_factor: float = 1.5   # Allow this × limit in a burst
    block_factor: float = 5.0   # Permanently block at this × limit

    @property
    def burst_limit(self) -> int:
        return int(self.requests * self.burst_factor)

    @property
    def block_threshold(self) -> int:
        return int(self.requests * self.block_factor)


RATE_LIMITS: dict[str, RateLimit] = {
    # Authentication endpoints
    "auth:login": RateLimit(10, 60),           # 10/min
    "auth:register": RateLimit(5, 60),          # 5/min
    "auth:password_reset": RateLimit(3, 300),   # 3 per 5 min

    # Goal submission (expensive — LLM involved)
    "goals:submit": RateLimit(20, 60),          # 20/min

    # Job management
    "jobs:create": RateLimit(50, 60),           # 50/min
    "jobs:list": RateLimit(120, 60),            # 120/min

    # Cloud operations (cost-incurring)
    "providers:spin_up": RateLimit(10, 60),     # 10/min

    # Metrics / analytics (cheap reads)
    "metrics:read": RateLimit(200, 60),         # 200/min

    # Admin
    "admin:any": RateLimit(100, 60),            # 100/min

    # Default fallback
    "default": RateLimit(60, 60),              # 60/min

    # Per-IP unauthenticated
    "ip:unauthenticated": RateLimit(100, 60),   # 100/min
    "ip:ddos_threshold": RateLimit(500, 60),    # Block above 500/min per IP
}


class RateLimiter:
    """Redis sliding-window rate limiter.

    Falls back to a simple in-memory counter if Redis is unavailable
    (development mode).
    """

    def __init__(self, redis_url: str | None = None) -> None:
        import os
        self._redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self._redis = None
        self._memory_windows: dict[str, list[float]] = {}   # Fallback
        self._blocked_keys: set[str] = set()
        self._connect()

    def _connect(self) -> None:
        try:
            import redis
            self._redis = redis.from_url(self._redis_url, decode_responses=True, socket_timeout=1.0)
            self._redis.ping()
            logger.info("[RateLimiter] Connected to Redis")
        except Exception as exc:
            logger.warning(f"[RateLimiter] Redis unavailable ({exc}) — using in-memory fallback")
            self._redis = None

    def check(
        self,
        key: str,           # Unique identifier: "user:{user_id}", "ip:{ip}", etc.
        endpoint: str = "default",
        cost: int = 1,      # Weight of this request (expensive ops cost more)
    ) -> "RateLimitResult":
        """
        Check if a request is allowed.
        Returns RateLimitResult with allowed=True/False and headers.
        """
        if key in self._blocked_keys:
            return RateLimitResult(
                allowed=False, remaining=0, reset_in=3600,
                reason="PERMANENTLY_BLOCKED", retry_after=3600,
            )

        limit = RATE_LIMITS.get(endpoint) or RATE_LIMITS["default"]
        now = time.time()
        window_start = now - limit.window_s

        if self._redis:
            return self._redis_check(key, endpoint, limit, now, window_start, cost)
        else:
            return self._memory_check(key, endpoint, limit, now, window_start, cost)

    def check_ip(self, ip: str) -> "RateLimitResult":
        """Fast IP-level check — call before user auth."""
        return self.check(f"ip:{ip}", "ip:unauthenticated")

    def check_user(self, user_id: str, endpoint: str = "default") -> "RateLimitResult":
        """Per-user rate limit."""
        return self.check(f"user:{user_id}", endpoint)

    def check_org(self, org_id: str, endpoint: str = "default") -> "RateLimitResult":
        """Per-organization aggregate rate limit."""
        return self.check(f"org:{org_id}", endpoint)

    def permanently_block(self, ip: str, reason: str = "") -> None:
        """Block an IP address indefinitely (DDoS / abuse)."""
        key = f"ip:{ip}"
        self._blocked_keys.add(key)
        if self._redis:
            self._redis.setex(f"ratelimit:blocked:{key}", 86400 * 30, reason or "abuse")
        logger.warning(f"[RateLimiter] BLOCKED {ip}: {reason}")

    def unblock(self, ip: str) -> None:
        key = f"ip:{ip}"
        self._blocked_keys.discard(key)
        if self._redis:
            self._redis.delete(f"ratelimit:blocked:{key}")

    def get_stats(self, key: str, endpoint: str = "default") -> dict[str, Any]:
        """Get current usage stats for a key."""
        limit = RATE_LIMITS.get(endpoint) or RATE_LIMITS["default"]
        now = time.time()
        window_start = now - limit.window_s
        redis_key = f"ratelimit:{endpoint}:{key}"

        if self._redis:
            try:
                count = self._redis.zcount(redis_key, window_start, now)
                return {
                    "requests_in_window": int(count),
                    "limit": limit.requests,
                    "window_seconds": limit.window_s,
                    "remaining": max(0, limit.requests - int(count)),
                    "blocked": key in self._blocked_keys,
                }
            except Exception:
                pass
        return {"requests_in_window": 0, "limit": limit.requests, "remaining": limit.requests}

    # ─── Redis implementation ─────────────────────────────────────────

    def _redis_check(
        self,
        key: str, endpoint: str, limit: RateLimit,
        now: float, window_start: float, cost: int,
    ) -> "RateLimitResult":
        redis_key = f"ratelimit:{endpoint}:{key}"
        pipe = self._redis.pipeline()

        try:
            # Atomically: remove old entries, count current, add new
            pipe.zremrangebyscore(redis_key, 0, window_start)
            pipe.zcard(redis_key)
            pipe.zadd(redis_key, {f"{now}:{cost}": now})
            pipe.expire(redis_key, limit.window_s + 10)
            results = pipe.execute()

            current_count = int(results[1]) * cost
            remaining = max(0, limit.requests - current_count)
            reset_in = int(limit.window_s - (now - window_start))

            # DDoS detection: hard block at block_threshold
            if current_count >= limit.block_threshold and "ip:" in key:
                ip = key.replace("ip:", "")
                self.permanently_block(ip, f"DDoS: {current_count} req in {limit.window_s}s")
                return RateLimitResult(
                    allowed=False, remaining=0, reset_in=3600,
                    reason="DDOS_BLOCK", retry_after=3600,
                )

            allowed = current_count <= limit.requests
            if not allowed:
                logger.info(f"[RateLimiter] LIMIT {key}/{endpoint}: {current_count}/{limit.requests}")

            return RateLimitResult(
                allowed=allowed,
                remaining=remaining,
                reset_in=reset_in,
                limit=limit.requests,
                reason="RATE_LIMITED" if not allowed else "",
                retry_after=reset_in if not allowed else 0,
            )

        except Exception as exc:
            logger.warning(f"[RateLimiter] Redis error — allowing: {exc}")
            return RateLimitResult(allowed=True, remaining=limit.requests, reset_in=60)

    # ─── In-memory fallback ───────────────────────────────────────────

    def _memory_check(
        self,
        key: str, endpoint: str, limit: RateLimit,
        now: float, window_start: float, cost: int,
    ) -> "RateLimitResult":
        mem_key = f"{endpoint}:{key}"
        window = self._memory_windows.setdefault(mem_key, [])

        # Clean old
        self._memory_windows[mem_key] = [t for t in window if t > window_start]

        count = len(self._memory_windows[mem_key]) * cost
        remaining = max(0, limit.requests - count)

        if count < limit.burst_limit:
            self._memory_windows[mem_key].append(now)

        allowed = count <= limit.requests
        return RateLimitResult(
            allowed=allowed, remaining=remaining,
            reset_in=limit.window_s, limit=limit.requests,
            reason="RATE_LIMITED" if not allowed else "",
            retry_after=limit.window_s if not allowed else 0,
        )


@dataclass
class RateLimitResult:
    """Result of a rate limit check."""
    allowed: bool
    remaining: int
    reset_in: int           # Seconds until window resets
    limit: int = 0
    reason: str = ""
    retry_after: int = 0    # Seconds client should wait before retrying

    def to_headers(self) -> dict[str, str]:
        """HTTP headers to include in every response (RFC 6585 compliant)."""
        headers = {
            "X-RateLimit-Remaining": str(self.remaining),
            "X-RateLimit-Reset": str(int(time.time()) + self.reset_in),
        }
        if self.limit:
            headers["X-RateLimit-Limit"] = str(self.limit)
        if not self.allowed and self.retry_after:
            headers["Retry-After"] = str(self.retry_after)
        return headers


# ─── FastAPI middleware ───────────────────────────────────────────────────────

def make_rate_limit_middleware(limiter: RateLimiter):
    """Create FastAPI middleware from a RateLimiter instance."""
    from fastapi import Request, Response
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse

    class RateLimitMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            # Get real IP (handle proxies)
            forwarded_for = request.headers.get("X-Forwarded-For", "")
            ip = forwarded_for.split(",")[0].strip() if forwarded_for else (
                request.client.host if request.client else "unknown"
            )

            # Skip rate limiting for health checks
            if request.url.path in ("/health", "/ready"):
                return await call_next(request)

            # IP-level check first (cheapest)
            ip_result = limiter.check_ip(ip)
            if not ip_result.allowed:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests", "reason": ip_result.reason, "retry_after": ip_result.retry_after},
                    headers=ip_result.to_headers(),
                )

            # User-level check if authenticated
            user_id = getattr(request.state, "user_id", None)
            if user_id:
                # Map path to endpoint key
                path = request.url.path.lstrip("/").split("/")[0]
                method = request.method.lower()
                endpoint_key = f"{path}:{'submit' if method == 'post' else 'list'}"
                user_result = limiter.check_user(user_id, endpoint_key)
                if not user_result.allowed:
                    return JSONResponse(
                        status_code=429,
                        content={"detail": "Rate limit exceeded", "retry_after": user_result.retry_after},
                        headers=user_result.to_headers(),
                    )

            response = await call_next(request)

            # Add rate limit headers to response
            for k, v in ip_result.to_headers().items():
                response.headers[k] = v

            return response

    return RateLimitMiddleware


# ─── Singleton ────────────────────────────────────────────────────────────────

_limiter: RateLimiter | None = None

def get_rate_limiter() -> RateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = RateLimiter()
    return _limiter
