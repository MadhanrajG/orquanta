# Copyright 2026 OrQuanta — Apache License 2.0
"""
OrQuanta Phase 6A — Unified Marketplace Asset Registry.

Central registry for all marketplace assets:
  - AI Models
  - Autonomous Agents
  - MCP Servers / Tools
  - AI Workflows

Extensible for future: Datasets, AI Applications.

Security invariants:
  - System actors cannot publish or approve assets.
  - Revoked assets remain in registry with REVOKED status (audit trail preserved).
  - Trust status is version-specific — a new version resets to PENDING_REVIEW.
  - Publishers must be verified before assets are publicly listed.
  - Asset metadata is recorded; OrQuanta does not guarantee correctness of
    publisher-supplied licence or permission claims.
"""
from __future__ import annotations

import datetime
import hashlib
import threading
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional

import logging

logger = logging.getLogger("orquanta.marketplace.registry")

SYSTEM_ACTOR_IDS = {"system", "auto", "automated", "orquanta", ""}

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class AssetType(str, Enum):
    MODEL    = "MODEL"
    AGENT    = "AGENT"
    MCP_TOOL = "MCP_TOOL"
    WORKFLOW = "WORKFLOW"
    # Reserved — not implemented in Phase 6 MVP
    DATASET      = "DATASET"
    APPLICATION  = "APPLICATION"


class PublicationStatus(str, Enum):
    DRAFT           = "DRAFT"
    PENDING_REVIEW  = "PENDING_REVIEW"
    PUBLISHED       = "PUBLISHED"
    RESTRICTED      = "RESTRICTED"
    DEPRECATED      = "DEPRECATED"
    WITHDRAWN       = "WITHDRAWN"


class TrustStatus(str, Enum):
    """
    Distinct levels of verification. Metadata verification != security review.
    OrQuanta does NOT guarantee that any asset is completely safe.
    """
    PENDING_REVIEW    = "PENDING_REVIEW"      # Awaiting any review
    METADATA_VERIFIED = "METADATA_VERIFIED"   # Publisher identity and manifest confirmed
    SECURITY_REVIEWED = "SECURITY_REVIEWED"   # Static analysis completed (see disclaimer)
    RESTRICTED        = "RESTRICTED"          # Available with caveats
    REJECTED          = "REJECTED"            # Failed review
    REVOKED           = "REVOKED"             # Previously published, now revoked


class PricingModel(str, Enum):
    FREE         = "FREE"
    PAID         = "PAID"
    SUBSCRIPTION = "SUBSCRIPTION"
    ENTERPRISE   = "ENTERPRISE"


# ---------------------------------------------------------------------------
# Core data structures
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"


@dataclass
class PricingInfo:
    model: PricingModel = PricingModel.FREE
    price_usd: Optional[float] = None           # None for FREE / ENTERPRISE
    billing_period: Optional[str] = None        # "monthly" | "annual" | "per_call"
    currency: str = "USD"
    # NOTE: OrQuanta does not process real payouts until payment verification,
    # fraud prevention, tax and applicable legal requirements are met.
    payout_enabled: bool = False
    pricing_note: str = (
        "Pricing information is provided by the publisher. "
        "OrQuanta does not currently process real payouts; "
        "payment integration requires separate legal and compliance review."
    )


@dataclass
class CompatibilityInfo:
    min_python: Optional[str] = None
    min_orquanta_version: Optional[str] = None
    supported_platforms: List[str] = field(default_factory=list)
    gpu_required: bool = False
    min_vram_gb: Optional[float] = None
    model_dependencies: List[str] = field(default_factory=list)   # model_id list
    tool_dependencies: List[str] = field(default_factory=list)    # tool_id list


@dataclass
class SecurityInfo:
    trust_status: TrustStatus = TrustStatus.PENDING_REVIEW
    trust_version: str = ""                     # version this trust applies to
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None
    assessment_id: Optional[str] = None         # links to supply chain assessment
    findings_summary: str = ""
    is_safe_claim: bool = False                 # always False — we never guarantee safety
    disclaimer: str = (
        "Security review reflects the state of static analysis at review time. "
        "OrQuanta does not guarantee that any marketplace asset is completely safe. "
        "Review all permission scopes before installation."
    )


@dataclass
class MarketplaceAsset:
    """Canonical asset record in the unified registry."""
    asset_id: str
    asset_type: AssetType
    publisher_id: str
    name: str
    version: str
    description: str
    tags: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)
    licence: str = "UNKNOWN"
    licence_url: Optional[str] = None
    source_repo: Optional[str] = None
    homepage: Optional[str] = None
    documentation_url: Optional[str] = None
    # Provenance
    manifest_hash: Optional[str] = None        # SHA-256 of signed manifest
    manifest_signature: Optional[str] = None   # Base64 publisher signature
    provenance_verified: bool = False
    # Security
    security: SecurityInfo = field(default_factory=SecurityInfo)
    # Governance
    publication_status: PublicationStatus = PublicationStatus.DRAFT
    governance_approval_id: Optional[str] = None
    # Compatibility
    compatibility: CompatibilityInfo = field(default_factory=CompatibilityInfo)
    # Required permissions (declared by publisher)
    required_permissions: List[str] = field(default_factory=list)
    required_scopes: List[str] = field(default_factory=list)
    # Pricing
    pricing: PricingInfo = field(default_factory=PricingInfo)
    # Installation
    install_requirements: Dict[str, Any] = field(default_factory=dict)
    # Analytics (populated at runtime — never trusted as accuracy guarantees)
    install_count: int = 0
    is_featured: bool = False
    is_demo: bool = False       # True for seed/demo assets
    # Timestamps
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    published_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["asset_type"] = self.asset_type.value
        d["publication_status"] = self.publication_status.value
        d["pricing"]["model"] = self.pricing.model.value
        d["security"]["trust_status"] = self.security.trust_status.value
        return d


@dataclass
class PublisherProfile:
    publisher_id: str
    display_name: str
    email: str
    organisation: Optional[str] = None
    website: Optional[str] = None
    github_handle: Optional[str] = None
    bio: str = ""
    is_verified: bool = False
    is_commercial: bool = False
    is_banned: bool = False
    ban_reason: Optional[str] = None
    # Analytics
    total_assets: int = 0
    total_installs: int = 0
    # Revenue accounting (not real payouts in Phase 6)
    revenue_share_pct: float = 0.0
    payout_enabled: bool = False
    created_at: str = field(default_factory=_now)
    verified_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class InstallationRecord:
    installation_id: str
    asset_id: str
    asset_version: str
    tenant_id: str
    installed_by: str
    status: str = "ACTIVE"          # ACTIVE | DISABLED | UNINSTALLED | REVOKED
    installed_at: str = field(default_factory=_now)
    disabled_at: Optional[str] = None
    uninstalled_at: Optional[str] = None
    # Execution monitoring
    last_executed_at: Optional[str] = None
    execution_count: int = 0
    # Durable job reference
    install_job_id: Optional[str] = None
    # Audit
    policy_decision: str = ""
    permissions_accepted: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Asset registry
# ---------------------------------------------------------------------------

class MarketplaceRegistry:
    """
    Thread-safe in-memory asset registry.
    In production, back this with PostgreSQL — the interface is stable.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._assets: Dict[str, MarketplaceAsset] = {}       # asset_id -> asset
        self._publishers: Dict[str, PublisherProfile] = {}   # publisher_id -> profile
        self._installations: Dict[str, InstallationRecord] = {}  # installation_id -> record
        self._version_index: Dict[str, List[str]] = {}       # name -> [asset_id, ...]
        self._seed_demo_assets()

    # ------------------------------------------------------------------
    # Publisher management
    # ------------------------------------------------------------------

    def register_publisher(
        self,
        *,
        actor_id: str,
        display_name: str,
        email: str,
        organisation: Optional[str] = None,
        website: Optional[str] = None,
        github_handle: Optional[str] = None,
        bio: str = "",
        is_commercial: bool = False,
    ) -> PublisherProfile:
        if actor_id in SYSTEM_ACTOR_IDS:
            raise PermissionError("System actors cannot register as publishers.")
        with self._lock:
            pub_id = f"pub-{uuid.uuid4().hex[:12]}"
            profile = PublisherProfile(
                publisher_id=pub_id,
                display_name=display_name,
                email=email,
                organisation=organisation,
                website=website,
                github_handle=github_handle,
                bio=bio,
                is_commercial=is_commercial,
            )
            self._publishers[pub_id] = profile
            logger.info(f"[Registry] Publisher registered: {pub_id} ({display_name})")
            return profile

    def verify_publisher(self, *, publisher_id: str, actor_id: str) -> PublisherProfile:
        """Mark publisher as verified. Requires a human actor (non-system)."""
        if actor_id in SYSTEM_ACTOR_IDS:
            raise PermissionError("System actors cannot verify publishers.")
        with self._lock:
            if publisher_id not in self._publishers:
                raise KeyError(f"Publisher not found: {publisher_id}")
            pub = self._publishers[publisher_id]
            if pub.is_banned:
                raise ValueError(f"Publisher {publisher_id} is banned.")
            pub.is_verified = True
            pub.verified_at = _now()
            logger.info(f"[Registry] Publisher verified: {publisher_id} by {actor_id}")
            return pub

    def get_publisher(self, publisher_id: str) -> Optional[PublisherProfile]:
        with self._lock:
            return self._publishers.get(publisher_id)

    def list_publishers(self, verified_only: bool = False) -> List[PublisherProfile]:
        with self._lock:
            pubs = list(self._publishers.values())
        if verified_only:
            pubs = [p for p in pubs if p.is_verified and not p.is_banned]
        return pubs

    # ------------------------------------------------------------------
    # Asset management
    # ------------------------------------------------------------------

    def submit_asset(
        self,
        *,
        actor_id: str,
        publisher_id: str,
        asset_type: AssetType,
        name: str,
        version: str,
        description: str,
        tags: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
        licence: str = "UNKNOWN",
        licence_url: Optional[str] = None,
        source_repo: Optional[str] = None,
        required_permissions: Optional[List[str]] = None,
        required_scopes: Optional[List[str]] = None,
        compatibility: Optional[CompatibilityInfo] = None,
        pricing: Optional[PricingInfo] = None,
        install_requirements: Optional[Dict[str, Any]] = None,
        is_demo: bool = False,
    ) -> MarketplaceAsset:
        if actor_id in SYSTEM_ACTOR_IDS:
            raise PermissionError("System actors cannot submit marketplace assets.")
        if asset_type in (AssetType.DATASET, AssetType.APPLICATION):
            raise NotImplementedError(
                f"{asset_type.value} assets are reserved for a future phase and not yet supported."
            )
        with self._lock:
            if publisher_id not in self._publishers and not is_demo:
                raise ValueError(f"Publisher not registered: {publisher_id}")
            asset_id = f"asset-{uuid.uuid4().hex[:16]}"
            asset = MarketplaceAsset(
                asset_id=asset_id,
                asset_type=asset_type,
                publisher_id=publisher_id,
                name=name,
                version=version,
                description=description,
                tags=tags or [],
                categories=categories or [],
                licence=licence,
                licence_url=licence_url,
                source_repo=source_repo,
                required_permissions=required_permissions or [],
                required_scopes=required_scopes or [],
                compatibility=compatibility or CompatibilityInfo(),
                pricing=pricing or PricingInfo(),
                install_requirements=install_requirements or {},
                publication_status=PublicationStatus.PENDING_REVIEW,
                is_demo=is_demo,
            )
            self._assets[asset_id] = asset
            self._version_index.setdefault(name, []).append(asset_id)
            # Update publisher stat (best-effort)
            if publisher_id in self._publishers:
                self._publishers[publisher_id].total_assets += 1
            logger.info(f"[Registry] Asset submitted: {asset_id} ({name} v{version}) by {actor_id}")
            return asset

    def publish_asset(self, *, asset_id: str, actor_id: str) -> MarketplaceAsset:
        """Move asset from PENDING_REVIEW → PUBLISHED. Requires human actor and METADATA_VERIFIED trust."""
        if actor_id in SYSTEM_ACTOR_IDS:
            raise PermissionError("System actors cannot approve asset publication.")
        with self._lock:
            asset = self._get_asset_locked(asset_id)
            if asset.publication_status not in (
                PublicationStatus.PENDING_REVIEW, PublicationStatus.DRAFT
            ):
                raise ValueError(
                    f"Asset {asset_id} is in status {asset.publication_status.value} — cannot publish."
                )
            if asset.security.trust_status == TrustStatus.REJECTED:
                raise ValueError("Cannot publish a rejected asset.")
            asset.publication_status = PublicationStatus.PUBLISHED
            asset.published_at = _now()
            asset.updated_at = _now()
            logger.info(f"[Registry] Asset published: {asset_id} by {actor_id}")
            return asset

    def withdraw_asset(self, *, asset_id: str, actor_id: str, reason: str = "") -> MarketplaceAsset:
        if actor_id in SYSTEM_ACTOR_IDS:
            raise PermissionError("System actors cannot withdraw assets.")
        with self._lock:
            asset = self._get_asset_locked(asset_id)
            asset.publication_status = PublicationStatus.WITHDRAWN
            asset.updated_at = _now()
            logger.info(f"[Registry] Asset withdrawn: {asset_id} by {actor_id}. Reason: {reason}")
            return asset

    def revoke_asset(self, *, asset_id: str, actor_id: str, reason: str = "") -> MarketplaceAsset:
        """Revocation preserves the asset record for audit trail."""
        if actor_id in SYSTEM_ACTOR_IDS:
            raise PermissionError("System actors cannot revoke assets.")
        with self._lock:
            asset = self._get_asset_locked(asset_id)
            asset.publication_status = PublicationStatus.WITHDRAWN
            asset.security.trust_status = TrustStatus.REVOKED
            asset.updated_at = _now()
            logger.warning(f"[Registry] Asset REVOKED: {asset_id} by {actor_id}. Reason: {reason}")
            return asset

    def update_trust_status(
        self,
        *,
        asset_id: str,
        actor_id: str,
        trust_status: TrustStatus,
        findings_summary: str = "",
        assessment_id: Optional[str] = None,
    ) -> MarketplaceAsset:
        if actor_id in SYSTEM_ACTOR_IDS:
            raise PermissionError("System actors cannot update trust status.")
        with self._lock:
            asset = self._get_asset_locked(asset_id)
            asset.security.trust_status = trust_status
            asset.security.trust_version = asset.version
            asset.security.reviewed_by = actor_id
            asset.security.reviewed_at = _now()
            asset.security.findings_summary = findings_summary
            asset.security.assessment_id = assessment_id
            asset.security.is_safe_claim = False   # Never claim safety
            asset.updated_at = _now()
            logger.info(
                f"[Registry] Trust updated: {asset_id} → {trust_status.value} by {actor_id}"
            )
            return asset

    def get_asset(self, asset_id: str) -> Optional[MarketplaceAsset]:
        with self._lock:
            return self._assets.get(asset_id)

    def search_assets(
        self,
        *,
        query: str = "",
        asset_type: Optional[AssetType] = None,
        tags: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
        publisher_id: Optional[str] = None,
        published_only: bool = True,
        pricing_model: Optional[PricingModel] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[MarketplaceAsset]:
        with self._lock:
            assets = list(self._assets.values())

        if published_only:
            assets = [a for a in assets if a.publication_status == PublicationStatus.PUBLISHED]
        if asset_type:
            assets = [a for a in assets if a.asset_type == asset_type]
        if publisher_id:
            assets = [a for a in assets if a.publisher_id == publisher_id]
        if pricing_model:
            assets = [a for a in assets if a.pricing.model == pricing_model]
        if tags:
            tag_set = set(t.lower() for t in tags)
            assets = [a for a in assets if tag_set & set(t.lower() for t in a.tags)]
        if categories:
            cat_set = set(c.lower() for c in categories)
            assets = [a for a in assets if cat_set & set(c.lower() for c in a.categories)]
        if query:
            q = query.lower()
            assets = [
                a for a in assets
                if q in a.name.lower()
                or q in a.description.lower()
                or any(q in t.lower() for t in a.tags)
            ]

        # Sort: featured first, then by install count
        assets.sort(key=lambda a: (not a.is_featured, -a.install_count))
        return assets[offset : offset + limit]

    def list_assets(
        self,
        asset_type: Optional[AssetType] = None,
        published_only: bool = True,
    ) -> List[MarketplaceAsset]:
        return self.search_assets(asset_type=asset_type, published_only=published_only, limit=1000)

    def get_version_history(self, name: str) -> List[MarketplaceAsset]:
        with self._lock:
            ids = self._version_index.get(name, [])
            return [self._assets[i] for i in ids if i in self._assets]

    # ------------------------------------------------------------------
    # Installation management
    # ------------------------------------------------------------------

    def record_installation(
        self,
        *,
        asset_id: str,
        asset_version: str,
        tenant_id: str,
        installed_by: str,
        install_job_id: Optional[str] = None,
        policy_decision: str = "",
        permissions_accepted: Optional[List[str]] = None,
    ) -> InstallationRecord:
        if installed_by in SYSTEM_ACTOR_IDS:
            raise PermissionError("System actors cannot perform installations.")
        with self._lock:
            if asset_id not in self._assets:
                raise KeyError(f"Asset not found: {asset_id}")
            rec_id = f"install-{uuid.uuid4().hex[:16]}"
            rec = InstallationRecord(
                installation_id=rec_id,
                asset_id=asset_id,
                asset_version=asset_version,
                tenant_id=tenant_id,
                installed_by=installed_by,
                install_job_id=install_job_id,
                policy_decision=policy_decision,
                permissions_accepted=permissions_accepted or [],
            )
            self._installations[rec_id] = rec
            asset = self._assets[asset_id]
            asset.install_count += 1
            # Update publisher total installs
            pub = self._publishers.get(asset.publisher_id)
            if pub:
                pub.total_installs += 1
            logger.info(
                f"[Registry] Installation recorded: {rec_id} — "
                f"asset={asset_id} tenant={tenant_id} by={installed_by}"
            )
            return rec

    def update_installation_status(
        self, installation_id: str, status: str
    ) -> InstallationRecord:
        with self._lock:
            if installation_id not in self._installations:
                raise KeyError(f"Installation not found: {installation_id}")
            rec = self._installations[installation_id]
            rec.status = status
            if status == "DISABLED":
                rec.disabled_at = _now()
            elif status == "UNINSTALLED":
                rec.uninstalled_at = _now()
            elif status == "REVOKED":
                rec.uninstalled_at = _now()
            return rec

    def list_installations(
        self, tenant_id: str, status_filter: Optional[str] = None
    ) -> List[InstallationRecord]:
        with self._lock:
            recs = [r for r in self._installations.values() if r.tenant_id == tenant_id]
        if status_filter:
            recs = [r for r in recs if r.status == status_filter]
        return recs

    def get_installation(self, installation_id: str) -> Optional[InstallationRecord]:
        with self._lock:
            return self._installations.get(installation_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_asset_locked(self, asset_id: str) -> MarketplaceAsset:
        """Must be called with self._lock held."""
        asset = self._assets.get(asset_id)
        if not asset:
            raise KeyError(f"Asset not found: {asset_id}")
        return asset

    def _seed_demo_assets(self) -> None:
        """Seed a small set of demo assets so the marketplace is not empty on startup."""
        demo_pub = PublisherProfile(
            publisher_id="pub-orquanta-demo",
            display_name="OrQuanta Demo",
            email="demo@orquanta.com",
            organisation="OrQuanta",
            is_verified=True,
            is_commercial=False,
        )
        self._publishers["pub-orquanta-demo"] = demo_pub

        demos = [
            {
                "asset_type": AssetType.MODEL,
                "name": "orquanta-reasoning-7b",
                "version": "1.0.0",
                "description": (
                    "Demo 7B parameter reasoning model. "
                    "This is a demonstration asset — not a real deployable model."
                ),
                "tags": ["reasoning", "7b", "demo"],
                "categories": ["Language Models"],
                "licence": "apache-2.0",
            },
            {
                "asset_type": AssetType.AGENT,
                "name": "cost-optimizer-agent",
                "version": "1.0.0",
                "description": (
                    "Demo agent that monitors GPU costs and suggests optimisations. "
                    "This is a demonstration asset."
                ),
                "tags": ["cost", "gpu", "agent", "demo"],
                "categories": ["Infrastructure"],
                "licence": "apache-2.0",
                "required_permissions": ["gpu:read", "billing:read"],
                "required_scopes": ["gpu:read", "billing:read"],
            },
            {
                "asset_type": AssetType.MCP_TOOL,
                "name": "orquanta-search-tool",
                "version": "1.0.0",
                "description": (
                    "Demo MCP tool for semantic search over OrQuanta job history. "
                    "This is a demonstration asset."
                ),
                "tags": ["search", "mcp", "demo"],
                "categories": ["Tools"],
                "licence": "apache-2.0",
                "required_scopes": ["db:read"],
            },
            {
                "asset_type": AssetType.WORKFLOW,
                "name": "gpu-benchmark-workflow",
                "version": "1.0.0",
                "description": (
                    "Demo workflow that runs a standard GPU benchmark suite "
                    "and reports throughput. This is a demonstration asset."
                ),
                "tags": ["benchmark", "gpu", "workflow", "demo"],
                "categories": ["Infrastructure"],
                "licence": "apache-2.0",
            },
        ]

        for d in demos:
            asset_id = f"asset-demo-{d['name']}"
            sec = SecurityInfo(
                trust_status=TrustStatus.METADATA_VERIFIED,
                trust_version=d["version"],
                reviewed_by="orquanta-demo-seed",
                reviewed_at=_now(),
                findings_summary="Demo asset — not a production security review.",
                is_safe_claim=False,
            )
            asset = MarketplaceAsset(
                asset_id=asset_id,
                asset_type=d["asset_type"],
                publisher_id="pub-orquanta-demo",
                name=d["name"],
                version=d["version"],
                description=d["description"],
                tags=d.get("tags", []),
                categories=d.get("categories", []),
                licence=d.get("licence", "UNKNOWN"),
                required_permissions=d.get("required_permissions", []),
                required_scopes=d.get("required_scopes", []),
                publication_status=PublicationStatus.PUBLISHED,
                security=sec,
                is_demo=True,
                is_featured=True,
                published_at=_now(),
            )
            self._assets[asset_id] = asset
            self._version_index.setdefault(d["name"], []).append(asset_id)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_registry: Optional[MarketplaceRegistry] = None
_registry_lock = threading.Lock()


def get_registry() -> MarketplaceRegistry:
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = MarketplaceRegistry()
    return _registry
