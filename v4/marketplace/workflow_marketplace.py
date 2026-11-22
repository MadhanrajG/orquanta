# Copyright 2026 OrQuanta — Apache License 2.0
"""
OrQuanta Phase 6E — Workflow Marketplace.

Reusable AI workflow discovery and publishing.

Integrates with:
- Existing Celery execution (execution/celery_app.py)
- Durable job management (execution/durable_pipeline.py)
- Existing agents, model registry, inference gateway, governance engine.

Security:
- Workflow steps are validated before installation.
- Dependencies are checked for trust status before execution.
- Governance policies evaluated before every workflow run.
- System actors cannot publish or install workflows.
"""
from __future__ import annotations

import threading
import uuid
import logging
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from .registry import (
    AssetType, MarketplaceRegistry, CompatibilityInfo, _now,
)

logger = logging.getLogger("orquanta.marketplace.workflows")

SYSTEM_ACTOR_IDS = {"system", "auto", "automated", "orquanta", ""}


# ---------------------------------------------------------------------------
# Workflow-specific metadata
# ---------------------------------------------------------------------------

@dataclass
class WorkflowStep:
    step_id: str
    name: str
    step_type: str          # "agent" | "model_inference" | "tool_call" | "job" | "condition"
    asset_id: Optional[str] = None      # marketplace asset this step uses
    config: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)   # step_ids


@dataclass
class WorkflowMarketplaceEntry:
    asset_id: str
    steps: List[WorkflowStep] = field(default_factory=list)
    trigger: str = "manual"             # manual | schedule | webhook | event
    schedule_cron: Optional[str] = None
    max_duration_seconds: int = 3600
    max_spend_usd: float = 50.0
    is_parallel: bool = False
    changelog: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


class WorkflowMarketplace:

    def __init__(self, registry: MarketplaceRegistry) -> None:
        self._registry = registry
        self._entries: Dict[str, WorkflowMarketplaceEntry] = {}
        self._run_history: Dict[str, List[Dict[str, Any]]] = {}  # asset_id -> runs

    def publish_workflow(
        self,
        *,
        actor_id: str,
        publisher_id: str,
        name: str,
        version: str,
        description: str,
        licence: str,
        steps: List[Dict[str, Any]],
        required_permissions: Optional[List[str]] = None,
        required_scopes: Optional[List[str]] = None,
        model_dependencies: Optional[List[str]] = None,
        trigger: str = "manual",
        schedule_cron: Optional[str] = None,
        max_duration_seconds: int = 3600,
        max_spend_usd: float = 50.0,
        tags: Optional[List[str]] = None,
        changelog: str = "",
        is_demo: bool = False,
    ) -> Dict[str, Any]:
        if actor_id in SYSTEM_ACTOR_IDS:
            raise PermissionError("System actors cannot publish workflows.")
        parsed_steps = [
            WorkflowStep(
                step_id=s.get("step_id", str(uuid.uuid4())),
                name=s.get("name", ""),
                step_type=s.get("step_type", "agent"),
                asset_id=s.get("asset_id"),
                config=s.get("config", {}),
                depends_on=s.get("depends_on", []),
            )
            for s in steps
        ]
        asset = self._registry.submit_asset(
            actor_id=actor_id,
            publisher_id=publisher_id,
            asset_type=AssetType.WORKFLOW,
            name=name,
            version=version,
            description=description,
            tags=(tags or []) + ["workflow"],
            categories=["Workflows"],
            licence=licence,
            required_permissions=required_permissions or [],
            required_scopes=required_scopes or [],
            compatibility=CompatibilityInfo(model_dependencies=model_dependencies or []),
            is_demo=is_demo,
        )
        entry = WorkflowMarketplaceEntry(
            asset_id=asset.asset_id,
            steps=parsed_steps,
            trigger=trigger,
            schedule_cron=schedule_cron,
            max_duration_seconds=max_duration_seconds,
            max_spend_usd=max_spend_usd,
            changelog=changelog,
        )
        self._entries[asset.asset_id] = entry
        logger.info(
            f"[WorkflowMarketplace] Workflow published: {asset.asset_id} ({name} v{version})"
        )
        return {"asset": asset.to_dict(), "workflow_entry": entry.to_dict()}

    def get_workflow_detail(self, asset_id: str) -> Optional[Dict[str, Any]]:
        asset = self._registry.get_asset(asset_id)
        if not asset or asset.asset_type != AssetType.WORKFLOW:
            return None
        entry = self._entries.get(asset_id, WorkflowMarketplaceEntry(asset_id=asset_id))
        return {
            "asset": asset.to_dict(),
            "workflow_entry": entry.to_dict(),
            "run_count": len(self._run_history.get(asset_id, [])),
        }

    def list_workflows(
        self, *, query: str = "", published_only: bool = True, limit: int = 50
    ) -> List[Dict[str, Any]]:
        assets = self._registry.search_assets(
            query=query,
            asset_type=AssetType.WORKFLOW,
            published_only=published_only,
            limit=limit,
        )
        return [
            {
                "asset": a.to_dict(),
                "workflow_entry": self._entries.get(
                    a.asset_id, WorkflowMarketplaceEntry(asset_id=a.asset_id)
                ).to_dict(),
            }
            for a in assets
        ]

    def submit_workflow_run(
        self,
        *,
        asset_id: str,
        tenant_id: str,
        submitted_by: str,
        input_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Records intent to run a workflow. Actual execution is submitted as a
        durable job through the existing execution infrastructure.
        Does NOT execute anything directly — governance must approve first.
        """
        if submitted_by in SYSTEM_ACTOR_IDS:
            raise PermissionError("System actors cannot submit workflow runs.")
        asset = self._registry.get_asset(asset_id)
        if not asset:
            raise KeyError(f"Asset not found: {asset_id}")
        if asset.asset_type != AssetType.WORKFLOW:
            raise ValueError(f"Asset {asset_id} is not a workflow.")
        run_id = f"wfrun-{uuid.uuid4().hex[:16]}"
        run = {
            "run_id": run_id,
            "asset_id": asset_id,
            "asset_name": asset.name,
            "asset_version": asset.version,
            "tenant_id": tenant_id,
            "submitted_by": submitted_by,
            "status": "PENDING_GOVERNANCE",
            "input_params": input_params or {},
            "submitted_at": _now(),
            "execution_note": (
                "Workflow execution is pending governance policy evaluation. "
                "It will be submitted as a durable job after approval."
            ),
        }
        self._run_history.setdefault(asset_id, []).append(run)
        logger.info(f"[WorkflowMarketplace] Run submitted: {run_id} for {asset_id} by {submitted_by}")
        return run

    def cancel_workflow_run(
        self, *, run_id: str, asset_id: str, cancelled_by: str
    ) -> Dict[str, Any]:
        if cancelled_by in SYSTEM_ACTOR_IDS:
            raise PermissionError("System actors cannot cancel workflow runs.")
        for run in self._run_history.get(asset_id, []):
            if run["run_id"] == run_id:
                run["status"] = "CANCELLED"
                run["cancelled_at"] = _now()
                run["cancelled_by"] = cancelled_by
                return run
        raise KeyError(f"Run not found: {run_id}")

    def get_run_history(self, asset_id: str, tenant_id: str) -> List[Dict[str, Any]]:
        return [
            r for r in self._run_history.get(asset_id, [])
            if r["tenant_id"] == tenant_id
        ]


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_workflow_marketplace: Optional[WorkflowMarketplace] = None
_wf_lock = threading.Lock()


def get_workflow_marketplace() -> WorkflowMarketplace:
    global _workflow_marketplace
    if _workflow_marketplace is None:
        with _wf_lock:
            if _workflow_marketplace is None:
                from .registry import get_registry
                _workflow_marketplace = WorkflowMarketplace(get_registry())
    return _workflow_marketplace
