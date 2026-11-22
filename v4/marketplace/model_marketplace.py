# Copyright 2026 OrQuanta — Apache License 2.0
"""
OrQuanta Phase 6B — Model Marketplace.

Integrates with existing model registry (inference/model_registry.py) and
Hugging Face discovery. Does NOT duplicate existing model data — it bridges
MarketplaceAsset records to existing ModelRecord objects.

Security:
- Never automatically execute untrusted model code.
- Model code is never run during discovery or listing.
- Licence restrictions are surfaced; unknown licences flagged explicitly.
- Deployment connects to existing deployment wizard (Phase 3F) via durable jobs.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from .registry import (
    AssetType, MarketplaceAsset, MarketplaceRegistry,
    PricingInfo, PricingModel, PublicationStatus, TrustStatus,
    CompatibilityInfo, SecurityInfo, _now,
)

logger = logging.getLogger("orquanta.marketplace.models")


# ---------------------------------------------------------------------------
# Model-specific extension
# ---------------------------------------------------------------------------

@dataclass
class ModelMarketplaceEntry:
    """
    Thin overlay joining a MarketplaceAsset to model-specific metadata.
    The canonical model data lives in inference/model_registry.py.
    """
    asset_id: str
    model_registry_id: Optional[str] = None    # links to ModelRecord.model_id
    hf_repo_id: Optional[str] = None           # e.g. "meta-llama/Llama-3-8B"
    model_family: Optional[str] = None
    parameter_count: Optional[str] = None      # e.g. "7B", "70B"
    context_length: Optional[int] = None
    quantisation_options: List[str] = field(default_factory=list)
    supported_engines: List[str] = field(default_factory=list)  # vllm, sglang, llamacpp
    min_vram_gb: Optional[float] = None
    benchmark_summary: Dict[str, Any] = field(default_factory=dict)
    deployment_wizard_url: str = "/deploy"      # frontend route
    # Flags
    is_gated: bool = False          # requires HF agreement
    is_quantised: bool = False
    is_fine_tuned: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ModelMarketplace:
    """
    Model marketplace operations built on top of MarketplaceRegistry.
    Does not own model data — bridges to existing ModelRegistry.
    """

    def __init__(self, registry: MarketplaceRegistry) -> None:
        self._registry = registry
        self._entries: Dict[str, ModelMarketplaceEntry] = {}

    def register_model_asset(
        self,
        *,
        actor_id: str,
        publisher_id: str,
        name: str,
        version: str,
        description: str,
        licence: str,
        hf_repo_id: Optional[str] = None,
        model_registry_id: Optional[str] = None,
        model_family: Optional[str] = None,
        parameter_count: Optional[str] = None,
        context_length: Optional[int] = None,
        quantisation_options: Optional[List[str]] = None,
        supported_engines: Optional[List[str]] = None,
        min_vram_gb: Optional[float] = None,
        benchmark_summary: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        is_gated: bool = False,
        is_demo: bool = False,
    ) -> Dict[str, Any]:
        compat = CompatibilityInfo(
            gpu_required=min_vram_gb is not None,
            min_vram_gb=min_vram_gb,
        )
        asset = self._registry.submit_asset(
            actor_id=actor_id,
            publisher_id=publisher_id,
            asset_type=AssetType.MODEL,
            name=name,
            version=version,
            description=description,
            tags=(tags or []) + ["model"],
            categories=["Language Models"],
            licence=licence,
            source_repo=f"https://huggingface.co/{hf_repo_id}" if hf_repo_id else None,
            compatibility=compat,
            is_demo=is_demo,
        )
        entry = ModelMarketplaceEntry(
            asset_id=asset.asset_id,
            model_registry_id=model_registry_id,
            hf_repo_id=hf_repo_id,
            model_family=model_family,
            parameter_count=parameter_count,
            context_length=context_length,
            quantisation_options=quantisation_options or [],
            supported_engines=supported_engines or [],
            min_vram_gb=min_vram_gb,
            benchmark_summary=benchmark_summary or {},
            is_gated=is_gated,
        )
        self._entries[asset.asset_id] = entry
        return {"asset": asset.to_dict(), "model_entry": entry.to_dict()}

    def get_model_detail(self, asset_id: str) -> Optional[Dict[str, Any]]:
        asset = self._registry.get_asset(asset_id)
        if not asset or asset.asset_type != AssetType.MODEL:
            return None
        entry = self._entries.get(asset_id, ModelMarketplaceEntry(asset_id=asset_id))
        return {"asset": asset.to_dict(), "model_entry": entry.to_dict()}

    def list_models(
        self,
        *,
        query: str = "",
        family: Optional[str] = None,
        licence: Optional[str] = None,
        published_only: bool = True,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        assets = self._registry.search_assets(
            query=query,
            asset_type=AssetType.MODEL,
            published_only=published_only,
            limit=limit,
        )
        results = []
        for a in assets:
            entry = self._entries.get(a.asset_id, ModelMarketplaceEntry(asset_id=a.asset_id))
            if family and entry.model_family and entry.model_family.lower() != family.lower():
                continue
            if licence and a.licence.lower() != licence.lower():
                continue
            results.append({"asset": a.to_dict(), "model_entry": entry.to_dict()})
        return results

    def get_deployment_info(self, asset_id: str) -> Dict[str, Any]:
        """
        Returns deployment metadata to pass to the deployment wizard.
        Does NOT start a deployment — that requires explicit user approval.
        """
        asset = self._registry.get_asset(asset_id)
        if not asset or asset.asset_type != AssetType.MODEL:
            raise KeyError(f"Model asset not found: {asset_id}")
        entry = self._entries.get(asset_id, ModelMarketplaceEntry(asset_id=asset_id))
        return {
            "asset_id": asset_id,
            "name": asset.name,
            "version": asset.version,
            "hf_repo_id": entry.hf_repo_id,
            "model_registry_id": entry.model_registry_id,
            "supported_engines": entry.supported_engines,
            "min_vram_gb": entry.min_vram_gb,
            "deployment_wizard_url": entry.deployment_wizard_url,
            "trust_status": asset.security.trust_status.value,
            "disclaimer": (
                "Deployment requires user approval and passes through the "
                "OrQuanta policy engine and governance controls."
            ),
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

import threading

_model_marketplace: Optional[ModelMarketplace] = None
_mm_lock = threading.Lock()


def get_model_marketplace() -> ModelMarketplace:
    global _model_marketplace
    if _model_marketplace is None:
        with _mm_lock:
            if _model_marketplace is None:
                from .registry import get_registry
                _model_marketplace = ModelMarketplace(get_registry())
    return _model_marketplace
