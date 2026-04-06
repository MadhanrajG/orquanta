"""
OrQuanta — Live GPU Price Aggregator
======================================
Polls Lambda Labs, RunPod, and Vast.ai simultaneously every 60 seconds.
Returns unified, sorted price table across all providers.

Endpoint: GET /api/v1/pricing
  ?gpu_type=a100    — filter by GPU model (optional)
  ?max_price=2.50   — max $/hr  (optional)
  ?min_vram=40      — min VRAM in GB (optional)
  ?provider=lambda  — filter by provider (optional)

Response: { updated_at, providers_polled, listings: [ {...} ] }

Also exposes:
  GET /api/v1/pricing/summary    — cheapest per GPU class
  GET /api/v1/pricing/providers  — which providers are live vs degraded
  POST /api/v1/pricing/compare   — compare two specific instances
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

logger = logging.getLogger("orquanta.pricing")
router  = APIRouter(prefix="/api/v1/pricing", tags=["pricing"])

# ─── Cache ────────────────────────────────────────────────────────────────────
_CACHE_TTL   = 60    # seconds
_cache_ts    = 0.0
_cache_data: list[dict] = []
_provider_health: dict[str, str] = {}  # provider → "ok" | "degraded" | "offline"


# ─── GPU Listing ──────────────────────────────────────────────────────────────

@dataclass
class GpuListing:
    provider:       str         # "lambda", "runpod", "vastai", "coreweave"
    provider_label: str         # "Lambda Labs"
    instance_id:    str         # provider-specific reference
    gpu_model:      str         # "A100 80GB"
    gpu_count:      int         # 1, 2, 4, 8
    vram_gb:        int         # 80
    vcpus:          int
    ram_gb:         int
    price_per_hr:   float       # $/hr
    region:         str
    availability:   str         # "available" | "limited" | "unavailable"
    spot:           bool        # True = interruptible
    tags:           list[str]   # ["NVLink", "InfiniBand", "PCIe"]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["price_per_hr_fmt"]  = f"${self.price_per_hr:.3f}/hr"
        d["cost_8hr_fmt"]      = f"${self.price_per_hr * 8:.2f} / 8hr"
        d["cost_day_fmt"]      = f"${self.price_per_hr * 24:.2f}/day"
        d["value_score"] = round(self.gpu_count * self.vram_gb / max(self.price_per_hr, 0.01), 1)
        return d


# ─── Lambda Labs Fetcher ──────────────────────────────────────────────────────

async def _fetch_lambda(client: httpx.AsyncClient) -> list[GpuListing]:
    key = os.getenv("LAMBDA_LABS_API_KEY", "")
    if not key:
        logger.debug("[Pricing/Lambda] No API key — using public catalog fallback")
        return _lambda_fallback()

    try:
        r = await client.get(
            "https://cloud.lambdalabs.com/api/v1/instance-types",
            headers={"Authorization": f"Bearer {key}"},
            timeout=8.0,
        )
        if r.status_code != 200:
            logger.warning(f"[Pricing/Lambda] HTTP {r.status_code}")
            _provider_health["lambda"] = "degraded"
            return _lambda_fallback()

        data = r.json().get("data", {})
        listings = []
        for inst_type, info in data.items():
            specs  = info.get("instance_type", {})
            price  = info.get("regions_with_capacity_available", [])
            # price is $/hr in cents from specs
            price_cents = specs.get("price_cents_per_hour", 0)
            price_usd   = price_cents / 100.0 if price_cents else 0.0

            gpu_qty   = specs.get("gpu_count", 1) or 1
            # Extract GPU description
            gpu_desc  = specs.get("gpu", {})
            gpu_name  = gpu_desc.get("name", inst_type) if isinstance(gpu_desc, dict) else str(gpu_desc)
            vram      = gpu_desc.get("memory_gib", 0) if isinstance(gpu_desc, dict) else 0

            for region_info in price:
                region = region_info.get("name", "us-east-1")
                listings.append(GpuListing(
                    provider="lambda",
                    provider_label="Lambda Labs",
                    instance_id=inst_type,
                    gpu_model=gpu_name,
                    gpu_count=gpu_qty,
                    vram_gb=int(vram),
                    vcpus=specs.get("vcpus", 0),
                    ram_gb=specs.get("memory_gib", 0),
                    price_per_hr=price_usd,
                    region=region,
                    availability="available",
                    spot=False,
                    tags=["on-demand"],
                ))

        _provider_health["lambda"] = "ok"
        logger.info(f"[Pricing/Lambda] Fetched {len(listings)} listings")
        return listings if listings else _lambda_fallback()

    except Exception as exc:
        logger.error(f"[Pricing/Lambda] Error: {exc}")
        _provider_health["lambda"] = "offline"
        return _lambda_fallback()


def _lambda_fallback() -> list[GpuListing]:
    """Known Lambda Labs prices as of March 2026 — used when API key not set."""
    return [
        GpuListing("lambda","Lambda Labs","gpu_1x_a10","A10 24GB",1,24,30,200,0.75,"us-texas-1","available",False,["on-demand"]),
        GpuListing("lambda","Lambda Labs","gpu_1x_a100","A100 80GB",1,80,30,200,1.99,"us-texas-1","available",False,["on-demand"]),
        GpuListing("lambda","Lambda Labs","gpu_1x_h100_pcie","H100 PCIe 80GB",1,80,30,200,2.99,"us-east-1","available",False,["on-demand"]),
        GpuListing("lambda","Lambda Labs","gpu_1x_h100_sxm5","H100 SXM5 80GB",1,80,26,200,3.29,"us-midwest-1","limited",False,["SXM","NVLink"]),
        GpuListing("lambda","Lambda Labs","gpu_8x_a100","8× A100 80GB",8,80,124,1800,14.32,"us-texas-1","available",False,["NVLink","InfiniBand"]),
        GpuListing("lambda","Lambda Labs","gpu_8x_h100_sxm5","8× H100 SXM5",8,80,208,1800,24.80,"us-midwest-1","limited",False,["SXM","NVLink","InfiniBand"]),
    ]


# ─── RunPod Fetcher ───────────────────────────────────────────────────────────

async def _fetch_runpod(client: httpx.AsyncClient) -> list[GpuListing]:
    """RunPod pricing via GraphQL API (no auth required for public listings)."""
    query = """
    query GpuTypes {
      gpuTypes {
        id displayName memoryInGb secureCloud communityCloud
        lowestPrice(input: {gpuCount: 1}) { minimumBidPrice uninterruptablePrice }
      }
    }
    """
    try:
        r = await client.post(
            "https://api.runpod.io/graphql",
            json={"query": query},
            timeout=8.0,
        )
        if r.status_code != 200:
            _provider_health["runpod"] = "degraded"
            return _runpod_fallback()

        gpu_types = r.json().get("data", {}).get("gpuTypes", [])
        listings  = []

        for g in gpu_types:
            lp = g.get("lowestPrice") or {}
            spot_price   = lp.get("minimumBidPrice",     0) or 0
            demand_price = lp.get("uninterruptablePrice", 0) or 0

            if spot_price > 0:
                listings.append(GpuListing(
                    provider="runpod", provider_label="RunPod",
                    instance_id=g.get("id",""), gpu_model=g.get("displayName",""),
                    gpu_count=1, vram_gb=g.get("memoryInGb",0),
                    vcpus=8, ram_gb=32,
                    price_per_hr=round(spot_price, 4),
                    region="global", availability="available",
                    spot=True, tags=["spot", "community"],
                ))
            if demand_price > 0:
                listings.append(GpuListing(
                    provider="runpod", provider_label="RunPod",
                    instance_id=g.get("id","") + "_od",
                    gpu_model=g.get("displayName",""),
                    gpu_count=1, vram_gb=g.get("memoryInGb",0),
                    vcpus=8, ram_gb=32,
                    price_per_hr=round(demand_price, 4),
                    region="global", availability="available",
                    spot=False, tags=["on-demand", "secure"],
                ))

        _provider_health["runpod"] = "ok"
        logger.info(f"[Pricing/RunPod] Fetched {len(listings)} listings")
        return listings if listings else _runpod_fallback()

    except Exception as exc:
        logger.error(f"[Pricing/RunPod] Error: {exc}")
        _provider_health["runpod"] = "offline"
        return _runpod_fallback()


def _runpod_fallback() -> list[GpuListing]:
    return [
        GpuListing("runpod","RunPod","RTX_3090","RTX 3090 24GB",1,24,16,62,0.29,"global","available",True,["spot","community"]),
        GpuListing("runpod","RunPod","RTX_4090","RTX 4090 24GB",1,24,16,62,0.44,"global","available",True,["spot","community"]),
        GpuListing("runpod","RunPod","A100_80GB_PCIe","A100 80GB PCIe",1,80,12,188,1.64,"global","available",True,["spot"]),
        GpuListing("runpod","RunPod","A100_80GB_SXM","A100 80GB SXM",1,80,12,188,2.19,"global","available",False,["on-demand","secure"]),
        GpuListing("runpod","RunPod","H100_80GB_SXM","H100 SXM 80GB",1,80,16,251,2.59,"global","available",False,["on-demand","secure"]),
    ]


# ─── Vast.ai Fetcher ──────────────────────────────────────────────────────────

async def _fetch_vastai(client: httpx.AsyncClient) -> list[GpuListing]:
    """Vast.ai public offers API — no auth for read."""
    try:
        r = await client.get(
            "https://console.vast.ai/api/v0/bundles/"
            "?q={"
            "\"num_gpus\":{\"gte\":1},"
            "\"gpu_ram\":{\"gte\":10},"
            "\"dph_total\":{\"lte\":5.0},"
            "\"order\":[[\"dph_total\",\"asc\"]],"
            "\"limit\":40,"
            "\"type\":\"on-demand\""
            "}",
            timeout=8.0,
        )
        if r.status_code != 200:
            _provider_health["vastai"] = "degraded"
            return _vastai_fallback()

        offers   = r.json().get("offers", [])
        listings = []
        for o in offers[:30]:
            listings.append(GpuListing(
                provider="vastai", provider_label="Vast.ai",
                instance_id=str(o.get("id", "")),
                gpu_model=o.get("gpu_name", "Unknown GPU"),
                gpu_count=o.get("num_gpus", 1),
                vram_gb=int(o.get("gpu_ram", 0) / 1024) if o.get("gpu_ram", 0) > 100 else int(o.get("gpu_ram", 0)),
                vcpus=o.get("cpu_cores_effective", 8),
                ram_gb=int(o.get("cpu_ram", 32) / 1024) if o.get("cpu_ram", 0) > 1000 else o.get("cpu_ram", 32),
                price_per_hr=round(o.get("dph_total", 0), 4),
                region=o.get("geolocation", "global"),
                availability="available",
                spot=False,
                tags=["on-demand", "interruptible" if o.get("is_bid") else "reserved"],
            ))

        _provider_health["vastai"] = "ok"
        logger.info(f"[Pricing/Vast.ai] Fetched {len(listings)} listings")
        return listings if listings else _vastai_fallback()

    except Exception as exc:
        logger.error(f"[Pricing/Vast.ai] Error: {exc}")
        _provider_health["vastai"] = "offline"
        return _vastai_fallback()


def _vastai_fallback() -> list[GpuListing]:
    return [
        GpuListing("vastai","Vast.ai","v_4090_1","RTX 4090 24GB",1,24,8,32,0.38,"US","available",False,["on-demand"]),
        GpuListing("vastai","Vast.ai","v_a100_1","A100 80GB",1,80,16,128,1.45,"EU","available",False,["on-demand"]),
        GpuListing("vastai","Vast.ai","v_h100_1","H100 80GB",1,80,20,256,2.35,"US","available",False,["on-demand"]),
    ]


# ─── AWS spot pricing stub ────────────────────────────────────────────────────

def _aws_spot_fallback() -> list[GpuListing]:
    """AWS on-demand prices for reference / comparison."""
    return [
        GpuListing("aws","AWS (on-demand)","p3.2xlarge","V100 16GB",1,16,8,61,3.06,"us-east-1","available",False,["on-demand","reference"]),
        GpuListing("aws","AWS (on-demand)","p4d.24xlarge","8× A100 40GB",8,40,96,1152,32.77,"us-east-1","available",False,["on-demand","reference"]),
        GpuListing("aws","AWS (on-demand)","p5.48xlarge","8× H100 80GB",8,80,192,2048,98.32,"us-east-1","limited",False,["on-demand","reference"]),
    ]


# ─── Aggregator ───────────────────────────────────────────────────────────────

async def _refresh_cache() -> None:
    global _cache_ts, _cache_data
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(
            _fetch_lambda(client),
            _fetch_runpod(client),
            _fetch_vastai(client),
            return_exceptions=True,
        )

    all_listings: list[GpuListing] = []
    for result in results:
        if isinstance(result, list):
            all_listings.extend(result)
        else:
            logger.warning(f"[Pricing] Provider fetch failed: {result}")

    # Always add AWS for reference (benchmark)
    all_listings.extend(_aws_spot_fallback())

    _cache_data = [l.to_dict() for l in all_listings if l.price_per_hr > 0]
    _cache_data.sort(key=lambda x: x["price_per_hr"])
    _cache_ts   = time.time()
    logger.info(f"[Pricing] Cache refreshed: {len(_cache_data)} listings")


async def _get_listings() -> list[dict]:
    global _cache_ts
    if time.time() - _cache_ts > _CACHE_TTL:
        await _refresh_cache()
    return _cache_data


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.get("")
@router.get("/")
async def get_pricing(
    gpu_type:  str | None = Query(None, description="Filter by GPU model keyword, e.g. 'a100', 'h100', '4090'"),
    max_price: float | None = Query(None, description="Max $/hr"),
    min_vram:  int | None   = Query(None, description="Min VRAM in GB"),
    provider:  str | None   = Query(None, description="Filter by provider: lambda, runpod, vastai, aws"),
    limit:     int           = Query(50, le=200),
):
    """
    Live GPU prices across Lambda Labs, RunPod, Vast.ai, and AWS.
    Updated every 60 seconds. Sorted cheapest first.
    """
    listings = await _get_listings()

    # Apply filters
    if gpu_type:
        kw = gpu_type.lower()
        listings = [l for l in listings if kw in l["gpu_model"].lower()]
    if max_price is not None:
        listings = [l for l in listings if l["price_per_hr"] <= max_price]
    if min_vram is not None:
        listings = [l for l in listings if l["vram_gb"] >= min_vram]
    if provider:
        listings = [l for l in listings if l["provider"] == provider.lower()]

    return JSONResponse({
        "updated_at":        datetime.fromtimestamp(_cache_ts, tz=timezone.utc).isoformat() if _cache_ts else None,
        "cache_age_sec":     round(time.time() - _cache_ts, 1),
        "providers_polled":  list({l["provider"] for l in listings}),
        "total_listings":    len(listings),
        "listings":          listings[:limit],
        "orquanta_tip":      "Submit a goal at /api/v1/goals — OrQuanta picks the cheapest available GPU automatically.",
    })


@router.get("/summary")
async def get_pricing_summary():
    """Cheapest available option per GPU class, across all providers."""
    listings = await _get_listings()

    # GPU classes
    classes = {
        "A10 / A10G (24GB)":    lambda l: "a10" in l["gpu_model"].lower() and l["gpu_count"] == 1,
        "RTX 3090 / 4090 (24GB)": lambda l: any(x in l["gpu_model"].lower() for x in ["3090","4090"]),
        "A100 40GB":             lambda l: "a100" in l["gpu_model"].lower() and l["vram_gb"] <= 40 and l["gpu_count"] == 1,
        "A100 80GB":             lambda l: "a100" in l["gpu_model"].lower() and l["vram_gb"] >= 80 and l["gpu_count"] == 1,
        "H100 80GB":             lambda l: "h100" in l["gpu_model"].lower() and l["gpu_count"] == 1,
        "8× H100 (cluster)":    lambda l: "h100" in l["gpu_model"].lower() and l["gpu_count"] >= 8,
    }

    summary = {}
    for class_name, predicate in classes.items():
        matches = sorted([l for l in listings if predicate(l)], key=lambda x: x["price_per_hr"])
        if matches:
            best = matches[0]
            aws  = next((l for l in listings if l["provider"] == "aws" and predicate(l)), None)
            savings_pct = 0
            if aws and best["price_per_hr"] > 0:
                savings_pct = round((1 - best["price_per_hr"] / aws["price_per_hr"]) * 100, 1)
            summary[class_name] = {
                "cheapest":        best,
                "options_count":   len(matches),
                "aws_ref_price":   aws["price_per_hr"] if aws else None,
                "savings_vs_aws_pct": savings_pct,
            }

    return JSONResponse({
        "summary":    summary,
        "updated_at": datetime.fromtimestamp(_cache_ts, tz=timezone.utc).isoformat() if _cache_ts else None,
        "tagline":    "OrQuanta routes your jobs to the cheapest available GPU automatically.",
    })


@router.get("/providers")
async def get_provider_health():
    """Which providers are live, degraded, or using cached fallback data."""
    return JSONResponse({
        "providers": {
            "lambda":  {"name": "Lambda Labs",  "status": _provider_health.get("lambda",  "fallback"), "api_key_set": bool(os.getenv("LAMBDA_LABS_API_KEY"))},
            "runpod":  {"name": "RunPod",        "status": _provider_health.get("runpod",  "unknown"), "api_key_set": True,  "note": "Public GraphQL, no key needed"},
            "vastai":  {"name": "Vast.ai",       "status": _provider_health.get("vastai",  "unknown"), "api_key_set": True,  "note": "Public API, no key needed"},
            "aws":     {"name": "AWS (reference)","status": "fallback",                                 "api_key_set": False, "note": "On-demand prices for comparison only"},
        },
        "cache_ttl_sec": _CACHE_TTL,
        "last_refresh":  datetime.fromtimestamp(_cache_ts, tz=timezone.utc).isoformat() if _cache_ts else None,
    })


@router.get("/live")
@router.get("/live/")
async def get_pricing_live(
    gpu_type:  str | None = Query(None),
    max_price: float | None = Query(None),
    min_vram:  int | None   = Query(None),
    provider:  str | None   = Query(None),
    limit:     int           = Query(50, le=200),
):
    """Alias for GET /api/v1/pricing — ensures /pricing/live always returns data."""
    return await get_pricing(
        gpu_type=gpu_type, max_price=max_price,
        min_vram=min_vram, provider=provider, limit=limit,
    )


@router.get("/status")
async def get_pricing_status():
    """Quick health check — how many listings are cached right now."""
    listings = await _get_listings()
    return {
        "cached_listings": len(listings),
        "cache_age_sec": round(time.time() - _cache_ts, 1),
        "status": "ok" if listings else "empty",
        "providers": list({l["provider"] for l in listings}),
    }
