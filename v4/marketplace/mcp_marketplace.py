# Copyright 2026 OrQuanta — Apache License 2.0
"""
OrQuanta Phase 6D — MCP and Tool Marketplace.

Trusted MCP server and tool discovery platform.

Security:
- Never automatically execute an unverified MCP server.
- Every server remains PENDING_REVIEW until a human approves it.
- Integrates with existing Phase 4E MCPToolSecurityRegistry for execution-time enforcement.
- Scope declarations are displayed before installation.
- Revocation is immediate and preserved in the audit trail.
"""
from __future__ import annotations

import threading
import uuid
import logging
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from .registry import (
    AssetType, MarketplaceRegistry, CompatibilityInfo,
    SecurityInfo, TrustStatus, _now,
)

logger = logging.getLogger("orquanta.marketplace.mcp")

SYSTEM_ACTOR_IDS = {"system", "auto", "automated", "orquanta", ""}


# ---------------------------------------------------------------------------
# MCP-specific metadata
# ---------------------------------------------------------------------------

@dataclass
class MCPServerSpec:
    endpoint_url: Optional[str] = None             # Only revealed post-install
    transport: str = "stdio"                        # stdio | http | sse
    auth_required: bool = True
    auth_method: Optional[str] = None              # bearer | oauth2 | api_key
    tls_required: bool = True
    network_access: bool = False
    allowed_domains: List[str] = field(default_factory=list)


@dataclass
class MCPToolEntry:
    asset_id: str
    server_spec: Optional[MCPServerSpec] = None
    tools: List[Dict[str, Any]] = field(default_factory=list)   # [{name, description, scopes}]
    required_scopes: List[str] = field(default_factory=list)
    public_key_fingerprint: Optional[str] = None
    # Safety
    is_sandboxed: bool = False
    sandbox_type: Optional[str] = None             # docker | wasm | process

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class MCPMarketplace:

    def __init__(self, registry: MarketplaceRegistry) -> None:
        self._registry = registry
        self._entries: Dict[str, MCPToolEntry] = {}

    def register_mcp_server(
        self,
        *,
        actor_id: str,
        publisher_id: str,
        name: str,
        version: str,
        description: str,
        licence: str,
        required_scopes: List[str],
        tools: Optional[List[Dict[str, Any]]] = None,
        server_spec: Optional[MCPServerSpec] = None,
        public_key_fingerprint: Optional[str] = None,
        tags: Optional[List[str]] = None,
        is_sandboxed: bool = False,
        sandbox_type: Optional[str] = None,
        is_demo: bool = False,
    ) -> Dict[str, Any]:
        if actor_id in SYSTEM_ACTOR_IDS:
            raise PermissionError("System actors cannot register MCP servers.")
        asset = self._registry.submit_asset(
            actor_id=actor_id,
            publisher_id=publisher_id,
            asset_type=AssetType.MCP_TOOL,
            name=name,
            version=version,
            description=description,
            tags=(tags or []) + ["mcp", "tool"],
            categories=["MCP Tools"],
            licence=licence,
            required_scopes=required_scopes,
            is_demo=is_demo,
        )
        entry = MCPToolEntry(
            asset_id=asset.asset_id,
            server_spec=server_spec,
            tools=tools or [],
            required_scopes=required_scopes,
            public_key_fingerprint=public_key_fingerprint,
            is_sandboxed=is_sandboxed,
            sandbox_type=sandbox_type,
        )
        self._entries[asset.asset_id] = entry
        logger.info(f"[MCPMarketplace] Server registered: {asset.asset_id} ({name} v{version})")
        return {"asset": asset.to_dict(), "mcp_entry": entry.to_dict()}

    def get_mcp_detail(self, asset_id: str) -> Optional[Dict[str, Any]]:
        asset = self._registry.get_asset(asset_id)
        if not asset or asset.asset_type != AssetType.MCP_TOOL:
            return None
        entry = self._entries.get(asset_id, MCPToolEntry(asset_id=asset_id))
        return {
            "asset": asset.to_dict(),
            "mcp_entry": entry.to_dict(),
            "execution_warning": (
                "This MCP server will NOT be executed until it passes trust review "
                "and you explicitly approve installation."
            ),
        }

    def list_mcp_servers(
        self, *, query: str = "", published_only: bool = True, limit: int = 50
    ) -> List[Dict[str, Any]]:
        assets = self._registry.search_assets(
            query=query,
            asset_type=AssetType.MCP_TOOL,
            published_only=published_only,
            limit=limit,
        )
        return [
            {
                "asset": a.to_dict(),
                "mcp_entry": self._entries.get(
                    a.asset_id, MCPToolEntry(asset_id=a.asset_id)
                ).to_dict(),
            }
            for a in assets
        ]

    def get_integration_config(
        self, asset_id: str, tenant_id: str, requesting_user: str
    ) -> Dict[str, Any]:
        """
        Returns integration config for an installed MCP server.
        Endpoint URL is only revealed post-install and only to the installing tenant.
        """
        if requesting_user in SYSTEM_ACTOR_IDS:
            raise PermissionError("System actors cannot retrieve MCP integration config.")
        entry = self._entries.get(asset_id)
        if not entry or not entry.server_spec:
            raise KeyError(f"MCP entry not found: {asset_id}")
        return {
            "asset_id": asset_id,
            "transport": entry.server_spec.transport,
            "auth_required": entry.server_spec.auth_required,
            "tls_required": entry.server_spec.tls_required,
            "tools": entry.tools,
            "required_scopes": entry.required_scopes,
            "is_sandboxed": entry.is_sandboxed,
            "note": "Endpoint URL is provisioned at runtime by OrQuanta — not stored in the marketplace.",
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_mcp_marketplace: Optional[MCPMarketplace] = None
_mcp_lock = threading.Lock()


def get_mcp_marketplace() -> MCPMarketplace:
    global _mcp_marketplace
    if _mcp_marketplace is None:
        with _mcp_lock:
            if _mcp_marketplace is None:
                from .registry import get_registry
                _mcp_marketplace = MCPMarketplace(get_registry())
    return _mcp_marketplace
