# Copyright 2026 OrQuanta — Apache License 2.0
"""
OrQuanta Phase 6C — Agent Marketplace.

Allows developers to publish reusable autonomous agents.

Security invariants:
- Agents must declare all required permissions explicitly.
- An installed agent NEVER inherits publisher privileges.
- Agents execute under the installing user's authorised identity.
- Required permissions are displayed to the user before installation.
- System actors cannot publish, install or approve agents.
- Agent code is never executed during marketplace browsing.
"""
from __future__ import annotations

import threading
import uuid
import logging
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from .registry import (
    AssetType, MarketplaceAsset, MarketplaceRegistry,
    CompatibilityInfo, PublicationStatus, _now,
)

logger = logging.getLogger("orquanta.marketplace.agents")

SYSTEM_ACTOR_IDS = {"system", "auto", "automated", "orquanta", ""}


# ---------------------------------------------------------------------------
# Agent-specific metadata
# ---------------------------------------------------------------------------

@dataclass
class AgentEntrypoint:
    """Describes how to load and run the agent."""
    module_path: str                            # e.g. "my_package.agent:MyAgent"
    config_schema: Dict[str, Any] = field(default_factory=dict)
    environment_vars: List[str] = field(default_factory=list)   # names only, not values
    max_execution_seconds: int = 300
    max_spend_usd: float = 10.0


@dataclass
class AgentMarketplaceEntry:
    asset_id: str
    entrypoint: Optional[AgentEntrypoint] = None
    # Declared at publish time — user sees these before installing
    required_permissions: List[str] = field(default_factory=list)
    required_scopes: List[str] = field(default_factory=list)
    model_dependencies: List[str] = field(default_factory=list)
    tool_dependencies: List[str] = field(default_factory=list)
    # Security
    max_spend_usd: float = 10.0
    max_execution_seconds: int = 300
    # Versioning
    changelog: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


class AgentMarketplace:

    def __init__(self, registry: MarketplaceRegistry) -> None:
        self._registry = registry
        self._entries: Dict[str, AgentMarketplaceEntry] = {}
        self._execution_history: Dict[str, List[Dict[str, Any]]] = {}  # asset_id -> records

    def publish_agent(
        self,
        *,
        actor_id: str,
        publisher_id: str,
        name: str,
        version: str,
        description: str,
        licence: str,
        required_permissions: List[str],
        required_scopes: List[str],
        model_dependencies: Optional[List[str]] = None,
        tool_dependencies: Optional[List[str]] = None,
        max_spend_usd: float = 10.0,
        max_execution_seconds: int = 300,
        tags: Optional[List[str]] = None,
        entrypoint: Optional[AgentEntrypoint] = None,
        changelog: str = "",
        is_demo: bool = False,
    ) -> Dict[str, Any]:
        if actor_id in SYSTEM_ACTOR_IDS:
            raise PermissionError("System actors cannot publish agents.")
        # Required permissions must be explicit — empty list is acceptable only for read-only agents
        asset = self._registry.submit_asset(
            actor_id=actor_id,
            publisher_id=publisher_id,
            asset_type=AssetType.AGENT,
            name=name,
            version=version,
            description=description,
            tags=(tags or []) + ["agent"],
            categories=["Agents"],
            licence=licence,
            required_permissions=required_permissions,
            required_scopes=required_scopes,
            compatibility=CompatibilityInfo(
                model_dependencies=model_dependencies or [],
                tool_dependencies=tool_dependencies or [],
            ),
            is_demo=is_demo,
        )
        entry = AgentMarketplaceEntry(
            asset_id=asset.asset_id,
            entrypoint=entrypoint,
            required_permissions=required_permissions,
            required_scopes=required_scopes,
            model_dependencies=model_dependencies or [],
            tool_dependencies=tool_dependencies or [],
            max_spend_usd=max_spend_usd,
            max_execution_seconds=max_execution_seconds,
            changelog=changelog,
        )
        self._entries[asset.asset_id] = entry
        logger.info(f"[AgentMarketplace] Agent published: {asset.asset_id} ({name} v{version})")
        return {"asset": asset.to_dict(), "agent_entry": entry.to_dict()}

    def get_agent_detail(self, asset_id: str) -> Optional[Dict[str, Any]]:
        asset = self._registry.get_asset(asset_id)
        if not asset or asset.asset_type != AssetType.AGENT:
            return None
        entry = self._entries.get(asset_id, AgentMarketplaceEntry(asset_id=asset_id))
        return {
            "asset": asset.to_dict(),
            "agent_entry": entry.to_dict(),
            "execution_count": len(self._execution_history.get(asset_id, [])),
            "permission_notice": (
                "Installing this agent will grant it the declared permissions "
                "under YOUR identity — it will never receive publisher privileges."
            ),
        }

    def list_agents(
        self, *, query: str = "", published_only: bool = True, limit: int = 50
    ) -> List[Dict[str, Any]]:
        assets = self._registry.search_assets(
            query=query,
            asset_type=AssetType.AGENT,
            published_only=published_only,
            limit=limit,
        )
        return [
            {
                "asset": a.to_dict(),
                "agent_entry": self._entries.get(
                    a.asset_id, AgentMarketplaceEntry(asset_id=a.asset_id)
                ).to_dict(),
            }
            for a in assets
        ]

    def record_execution(
        self,
        *,
        asset_id: str,
        tenant_id: str,
        executed_by: str,
        success: bool,
        duration_seconds: float,
        cost_usd: float,
        job_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if executed_by in SYSTEM_ACTOR_IDS:
            raise PermissionError("System actors cannot record agent executions.")
        record = {
            "execution_id": str(uuid.uuid4()),
            "asset_id": asset_id,
            "tenant_id": tenant_id,
            "executed_by": executed_by,
            "success": success,
            "duration_seconds": duration_seconds,
            "cost_usd": cost_usd,
            "is_estimated": True,
            "job_id": job_id,
            "recorded_at": _now(),
        }
        self._execution_history.setdefault(asset_id, []).append(record)
        return record

    def get_execution_history(
        self, asset_id: str, tenant_id: str
    ) -> List[Dict[str, Any]]:
        return [
            r for r in self._execution_history.get(asset_id, [])
            if r["tenant_id"] == tenant_id
        ]


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_agent_marketplace: Optional[AgentMarketplace] = None
_am_lock = threading.Lock()


def get_agent_marketplace() -> AgentMarketplace:
    global _agent_marketplace
    if _agent_marketplace is None:
        with _am_lock:
            if _agent_marketplace is None:
                from .registry import get_registry
                _agent_marketplace = AgentMarketplace(get_registry())
    return _agent_marketplace
