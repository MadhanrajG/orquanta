"""
OrQuanta Vero — User Analytics Engine

Thread-safe, in-memory event store for tracking:
  - Login events (success/failure, OAuth provider)
  - Active sessions (JWT-based)
  - Daily Active Users (DAU) and Monthly Active Users (MAU)
  - Feature usage heatmap (which pages/actions users actually use)

Vero polls this engine every 60 seconds to build user intelligence reports.

Usage::

    from v4.intelligence.user_analytics import get_analytics

    analytics = get_analytics()

    # On each login (called from auth middleware)
    analytics.record_login(user_id="u-123", email="user@acme.com", provider="google")

    # On each page/feature access
    analytics.record_feature_use(user_id="u-123", feature="goal_submit")

    # Vero reads this:
    report = analytics.get_report()
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any

logger = logging.getLogger("orquanta.vero.analytics")


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class LoginEvent:
    user_id: str
    email: str
    provider: str      # "email" | "google" | "github"
    success: bool
    timestamp: float = field(default_factory=time.time)
    ip: str = ""


@dataclass
class SessionRecord:
    user_id: str
    email: str
    login_ts: float
    last_seen_ts: float
    feature_path: str = "/"


@dataclass
class UserAnalyticsReport:
    """Complete user intelligence snapshot for Vero."""
    # Login metrics
    total_logins_today: int
    total_logins_this_hour: int
    login_success_rate_pct: float
    logins_by_provider: dict[str, int]

    # Active sessions
    active_sessions: int
    peak_sessions_today: int

    # DAU / MAU
    dau: int
    mau: int
    dau_mau_ratio: float

    # Feature heatmap (top 10 most used)
    feature_usage: dict[str, int]
    top_feature: str

    # Trend signals for Vero
    login_trend: str          # "rising" | "stable" | "declining"
    session_trend: str
    generated_at: str


# ---------------------------------------------------------------------------
# Analytics Engine
# ---------------------------------------------------------------------------

class UserAnalyticsEngine:
    """
    Thread-safe in-memory user analytics collector.

    The engine stores rolling windows of events:
    - Login events: last 30 days
    - Sessions: active (last 30 min)
    - Feature events: last 24 hours

    In production, persist to TimescaleDB / ClickHouse.
    """

    _SESSION_TIMEOUT_SECS = 30 * 60   # 30 minutes
    _EVENT_WINDOW_DAYS = 30

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._login_events: deque[LoginEvent] = deque(maxlen=50_000)
        self._sessions: dict[str, SessionRecord] = {}
        self._feature_events: deque[tuple[str, str, float]] = deque(maxlen=100_000)
        # (user_id, feature, timestamp)
        self._peak_sessions = 0
        self._unique_daily: set[str] = set()       # user_ids seen today
        self._unique_monthly: set[str] = set()     # user_ids seen this month
        self._daily_reset_ts = self._start_of_day()
        self._monthly_reset_ts = self._start_of_month()
        logger.info("UserAnalyticsEngine initialised.")

    # ------------------------------------------------------------------
    # Event Recording API (called by auth middleware)
    # ------------------------------------------------------------------

    def record_login(
        self,
        user_id: str,
        email: str = "",
        provider: str = "email",
        success: bool = True,
        ip: str = "",
    ) -> None:
        """Record a login attempt. Call this from auth middleware on every login."""
        with self._lock:
            self._maybe_reset_daily()
            event = LoginEvent(
                user_id=user_id,
                email=email,
                provider=provider,
                success=success,
                ip=ip,
            )
            self._login_events.append(event)
            if success:
                self._unique_daily.add(user_id)
                self._unique_monthly.add(user_id)
                # Start a session
                self._sessions[user_id] = SessionRecord(
                    user_id=user_id,
                    email=email,
                    login_ts=time.time(),
                    last_seen_ts=time.time(),
                )
                active = len(self._get_active_sessions())
                if active > self._peak_sessions:
                    self._peak_sessions = active
            logger.debug(f"[Analytics] login user={user_id} provider={provider} ok={success}")

    def record_feature_use(self, user_id: str, feature: str) -> None:
        """Record a feature/page access. Call from API middleware or route handlers."""
        with self._lock:
            self._feature_events.append((user_id, feature, time.time()))
            # Refresh session
            if user_id in self._sessions:
                self._sessions[user_id].last_seen_ts = time.time()
                self._sessions[user_id].feature_path = feature

    def record_logout(self, user_id: str) -> None:
        """Remove session on explicit logout."""
        with self._lock:
            self._sessions.pop(user_id, None)

    # ------------------------------------------------------------------
    # Report Generation (called by Vero every 60s)
    # ------------------------------------------------------------------

    def get_report(self) -> UserAnalyticsReport:
        """Generate a comprehensive analytics report for Vero."""
        with self._lock:
            self._maybe_reset_daily()
            now = time.time()
            one_hour_ago = now - 3600
            today_start = self._start_of_day()

            # Login stats
            today_logins = [e for e in self._login_events if e.timestamp >= today_start]
            hour_logins = [e for e in self._login_events if e.timestamp >= one_hour_ago]
            total_today = len(today_logins)
            success_today = sum(1 for e in today_logins if e.success)
            success_rate = (success_today / total_today * 100) if total_today > 0 else 100.0

            # By provider
            by_provider: dict[str, int] = defaultdict(int)
            for e in today_logins:
                if e.success:
                    by_provider[e.provider] += 1

            # Active sessions
            active = self._get_active_sessions()

            # Feature heatmap (last 24h)
            day_ago = now - 86400
            feature_counts: dict[str, int] = defaultdict(int)
            for uid, feat, ts in self._feature_events:
                if ts >= day_ago:
                    feature_counts[feat] += 1
            top_feature = max(feature_counts, key=feature_counts.get) if feature_counts else "dashboard"

            # Trend signals (compare last hour vs previous hour)
            prev_hour_logins = [e for e in self._login_events if e.timestamp < one_hour_ago and e.timestamp >= one_hour_ago - 3600]
            login_trend = self._trend(len(hour_logins), len(prev_hour_logins))
            session_trend = self._trend(len(active), self._peak_sessions // 2)

            dau = len(self._unique_daily)
            mau = len(self._unique_monthly)

            return UserAnalyticsReport(
                total_logins_today=total_today,
                total_logins_this_hour=len(hour_logins),
                login_success_rate_pct=round(success_rate, 1),
                logins_by_provider=dict(by_provider),
                active_sessions=len(active),
                peak_sessions_today=self._peak_sessions,
                dau=dau,
                mau=max(mau, dau),  # MAU >= DAU always
                dau_mau_ratio=round(dau / max(mau, 1), 3),
                feature_usage=dict(feature_counts),
                top_feature=top_feature,
                login_trend=login_trend,
                session_trend=session_trend,
                generated_at=datetime.now(timezone.utc).isoformat(),
            )

    def get_live_session_count(self) -> int:
        """Fast path for live session count (no lock acquisition overhead)."""
        return len(self._get_active_sessions())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_active_sessions(self) -> list[SessionRecord]:
        """Return sessions active within the last SESSION_TIMEOUT_SECS."""
        cutoff = time.time() - self._SESSION_TIMEOUT_SECS
        expired = [uid for uid, s in self._sessions.items() if s.last_seen_ts < cutoff]
        for uid in expired:
            del self._sessions[uid]
        return list(self._sessions.values())

    def _trend(self, current: int, previous: int) -> str:
        if previous == 0:
            return "stable"
        delta_pct = (current - previous) / previous * 100
        if delta_pct > 10:
            return "rising"
        elif delta_pct < -10:
            return "declining"
        return "stable"

    def _maybe_reset_daily(self) -> None:
        """Reset daily counters at UTC midnight."""
        today = self._start_of_day()
        if today > self._daily_reset_ts:
            self._unique_daily.clear()
            self._peak_sessions = 0
            self._daily_reset_ts = today
        month_start = self._start_of_month()
        if month_start > self._monthly_reset_ts:
            self._unique_monthly.clear()
            self._monthly_reset_ts = month_start

    @staticmethod
    def _start_of_day() -> float:
        now = datetime.now(timezone.utc)
        return now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()

    @staticmethod
    def _start_of_month() -> float:
        now = datetime.now(timezone.utc)
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp()


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_analytics: UserAnalyticsEngine | None = None


def get_analytics() -> UserAnalyticsEngine:
    """Return the global UserAnalyticsEngine singleton."""
    global _analytics
    if _analytics is None:
        _analytics = UserAnalyticsEngine()
    return _analytics
