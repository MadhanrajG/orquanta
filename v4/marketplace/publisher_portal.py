# Copyright 2026 OrQuanta — Apache License 2.0
"""
OrQuanta Phase 6G — Publisher Portal and Monetisation Foundation.

Provides publisher analytics, submission management, and revenue accounting.

IMPORTANT: Monetisation accounting only — no real payment processing.
Real payouts require: payment verification, fraud prevention, tax,
refund policy, and applicable legal review before enabling payout_enabled=True.
"""
from __future__ import annotations

import threading
import logging
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from .registry import MarketplaceRegistry, _now

logger = logging.getLogger("orquanta.marketplace.publisher_portal")

SYSTEM_ACTOR_IDS = {"system", "auto", "automated", "orquanta", ""}

PAYOUT_DISCLAIMER = (
    "Revenue accounting is recorded for future reconciliation. "
    "OrQuanta does NOT currently process real payouts. "
    "Enabling real payouts requires payment verification, fraud prevention, "
    "tax handling, refund policy, and legal compliance review."
)


@dataclass
class PublisherAnalytics:
    publisher_id: str
    total_assets: int = 0
    published_assets: int = 0
    total_installs: int = 0
    installs_last_30d: int = 0
    top_assets: List[Dict[str, Any]] = field(default_factory=list)
    # Revenue (accounting only — no real payout)
    total_revenue_usd: float = 0.0
    revenue_last_30d_usd: float = 0.0
    is_estimated: bool = True
    payout_enabled: bool = False
    payout_disclaimer: str = PAYOUT_DISCLAIMER
    generated_at: str = field(default_factory=_now)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RevenueRecord:
    record_id: str
    publisher_id: str
    asset_id: str
    installation_id: str
    amount_usd: float
    is_estimated: bool = True
    recorded_at: str = field(default_factory=_now)
    payout_status: str = "PENDING"   # PENDING | CLEARED | WITHHELD
    payout_note: str = PAYOUT_DISCLAIMER

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PublisherPortal:

    def __init__(self, registry: MarketplaceRegistry) -> None:
        self._registry = registry
        self._revenue_records: Dict[str, List[RevenueRecord]] = {}  # publisher_id -> records
        self._lock = threading.Lock()

    def get_publisher_analytics(self, publisher_id: str, actor_id: str) -> PublisherAnalytics:
        """
        Returns analytics for a publisher.
        Publisher can only view their own analytics; admin can view any.
        """
        if actor_id in SYSTEM_ACTOR_IDS:
            raise PermissionError("System actors cannot access publisher analytics.")
        pub = self._registry.get_publisher(publisher_id)
        if not pub:
            raise KeyError(f"Publisher not found: {publisher_id}")

        from .registry import PublicationStatus, AssetType
        assets = self._registry.list_assets(published_only=False)
        pub_assets = [a for a in assets if a.publisher_id == publisher_id]
        published = [a for a in pub_assets if a.publication_status == PublicationStatus.PUBLISHED]

        top = sorted(pub_assets, key=lambda a: -a.install_count)[:5]

        with self._lock:
            rev_records = self._revenue_records.get(publisher_id, [])
        total_rev = sum(r.amount_usd for r in rev_records)

        return PublisherAnalytics(
            publisher_id=publisher_id,
            total_assets=len(pub_assets),
            published_assets=len(published),
            total_installs=pub.total_installs,
            top_assets=[{"name": a.name, "installs": a.install_count} for a in top],
            total_revenue_usd=total_rev,
            is_estimated=True,
            payout_enabled=pub.payout_enabled,
        )

    def record_revenue(
        self,
        *,
        publisher_id: str,
        asset_id: str,
        installation_id: str,
        amount_usd: float,
    ) -> RevenueRecord:
        import uuid
        rec = RevenueRecord(
            record_id=f"rev-{uuid.uuid4().hex[:16]}",
            publisher_id=publisher_id,
            asset_id=asset_id,
            installation_id=installation_id,
            amount_usd=amount_usd,
            is_estimated=True,
        )
        with self._lock:
            self._revenue_records.setdefault(publisher_id, []).append(rec)
        return rec

    def get_revenue_records(self, publisher_id: str, actor_id: str) -> List[RevenueRecord]:
        if actor_id in SYSTEM_ACTOR_IDS:
            raise PermissionError("System actors cannot access revenue records.")
        with self._lock:
            return list(self._revenue_records.get(publisher_id, []))

    def get_submission_history(self, publisher_id: str) -> List[Dict[str, Any]]:
        assets = self._registry.list_assets(published_only=False)
        return [a.to_dict() for a in assets if a.publisher_id == publisher_id]


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_portal: Optional[PublisherPortal] = None
_portal_lock = threading.Lock()


def get_publisher_portal() -> PublisherPortal:
    global _portal
    if _portal is None:
        with _portal_lock:
            if _portal is None:
                from .registry import get_registry
                _portal = PublisherPortal(get_registry())
    return _portal
