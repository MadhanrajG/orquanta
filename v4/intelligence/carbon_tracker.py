"""
OrQuanta Intelligence — Carbon Tracker
=======================================

Tracks CO2 emissions per GPU job and provides carbon intelligence:
- Per-job and cumulative CO2 (gCO2eq)
- Region-level renewable energy percentage
- Carbon-optimal provider routing
- Monthly carbon report
- "Carbon Neutral" badge when user purchases offsets

Data sources:
  - electricityMap regional carbon intensity (gCO2eq/kWh)
  - GPU TDP profiles for accurate power estimation
  - NREL renewable energy data (US regions)
"""
from __future__ import annotations

import asyncio
import logging
import math
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("orquanta.intelligence.carbon")

# ─── Regional carbon intensity (gCO2eq / kWh) ─────────────────────────────
# Source: electricityMap 2024 averages
REGION_CARBON_INTENSITY: dict[str, float] = {
    # AWS regions
    "us-east-1":      386,   # N. Virginia — grid mixed
    "us-east-2":      493,   # Ohio
    "us-west-1":      238,   # N. California
    "us-west-2":       96,   # Oregon (hydro-heavy — excellent)
    "eu-west-1":      316,   # Ireland
    "eu-west-3":       61,   # Paris (nuclear-heavy — excellent)
    "eu-central-1":  329,   # Frankfurt
    "ap-northeast-1": 462,   # Tokyo
    "ap-southeast-1": 431,   # Singapore

    # GCP regions
    "us-central1":    467,   # Iowa
    "us-west1":        79,   # Oregon (97% renewable)
    "europe-west1":   117,   # Belgium (wind)
    "europe-west4":   353,   # Netherlands
    "europe-north1":   11,   # Finland (98% renewable — best)
    "asia-east1":     540,   # Taiwan (high)

    # Lambda Labs regions
    "us-tx-3":        392,   # Texas
    "us-az-2":        512,   # Arizona
    "us-ca-1":        228,   # California (solar mix)

    # CoreWeave
    "ORD1":           568,   # Chicago (grid)
    "LAS1":           339,   # Las Vegas (solar)
}

# ─── GPU Power profiles (TDP in Watts) ────────────────────────────────────
GPU_TDP: dict[str, int] = {
    "H100":     700,   # H100 SXM5
    "A100":     400,   # A100 SXM4
    "A100-80G": 400,
    "A10G":     150,
    "A10":      150,
    "L4":       72,
    "T4":       70,
    "V100":     300,
    "L40S":     350,
    "RTX4090":  450,
}

# ─── Renewable energy percentage by region ───────────────────────────────
RENEWABLE_PCT: dict[str, float] = {
    "europe-north1":  98.0,  # Finland
    "eu-west-3":      90.5,  # France (nuclear)
    "us-west-2":      87.3,  # Oregon
    "us-west1":       96.9,  # GCP Oregon
    "us-ca-1":        55.2,  # California
    "eu-west-1":      42.3,  # Ireland
    "us-east-1":      22.8,  # Virginia
    "us-tx-3":        28.1,  # Texas
    "ORD1":           14.2,  # Chicago
    "us-east-2":      12.5,  # Ohio
}

# ─── Carbon offset cost (USD per tonne CO2) ──────────────────────────────
OFFSET_COST_PER_TONNE = 15.0   # Gold Standard credits


@dataclass
class CarbonEstimate:
    """Carbon footprint estimate for a GPU job."""
    job_id:            str
    gpu_type:          str
    gpu_count:         int
    region:            str
    provider:          str
    duration_hours:    float

    # Computed fields
    energy_kwh:        float = 0.0
    carbon_g_co2eq:    float = 0.0   # grams CO2eq
    carbon_kg_co2eq:   float = 0.0   # kg CO2eq
    carbon_intensity:  float = 0.0   # gCO2eq / kWh
    renewable_pct:     float = 0.0
    offset_cost_usd:   float = 0.0
    vs_worst_region_pct: float = 0.0  # % better than worst region

    def __post_init__(self) -> None:
        tdp_w       = GPU_TDP.get(self.gpu_type, 300)
        # GPU doesn't always run at 100% TDP — use 85% average
        power_kw    = tdp_w * self.gpu_count * 0.85 / 1000
        self.energy_kwh = round(power_kw * self.duration_hours, 4)

        intensity   = REGION_CARBON_INTENSITY.get(self.region, 400)
        self.carbon_intensity = intensity
        self.carbon_g_co2eq  = round(self.energy_kwh * intensity, 1)
        self.carbon_kg_co2eq = round(self.carbon_g_co2eq / 1000, 4)
        self.renewable_pct   = RENEWABLE_PCT.get(self.region, 20.0)

        # Offset cost (convert g → tonnes)
        tonnes = self.carbon_kg_co2eq / 1000
        self.offset_cost_usd = round(tonnes * OFFSET_COST_PER_TONNE, 4)

        # How much better vs worst region (ORD1 at 568)
        worst = 568
        if self.carbon_intensity < worst:
            self.vs_worst_region_pct = round((worst - self.carbon_intensity) / worst * 100, 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id":                self.job_id,
            "gpu_type":              self.gpu_type,
            "gpu_count":             self.gpu_count,
            "region":                self.region,
            "provider":              self.provider,
            "duration_hours":        self.duration_hours,
            "energy_kwh":            self.energy_kwh,
            "carbon_g_co2eq":        self.carbon_g_co2eq,
            "carbon_kg_co2eq":       self.carbon_kg_co2eq,
            "carbon_intensity_g_kwh": self.carbon_intensity,
            "renewable_pct":         self.renewable_pct,
            "offset_cost_usd":       self.offset_cost_usd,
            "vs_worst_region_pct":   self.vs_worst_region_pct,
        }


class CarbonTracker:
    """
    Global carbon tracker — aggregates per-job footprint,
    provides routing recommendations, and generates monthly reports.
    """

    def __init__(self) -> None:
        self._jobs: list[CarbonEstimate] = []
        self._total_offset_usd: float = 0.0
        self._carbon_neutral: bool = False

    def track_job(
        self,
        job_id: str,
        gpu_type: str,
        gpu_count: int,
        region: str,
        provider: str,
        duration_hours: float,
    ) -> CarbonEstimate:
        """Record carbon for a completed job."""
        estimate = CarbonEstimate(
            job_id=job_id,
            gpu_type=gpu_type,
            gpu_count=gpu_count,
            region=region,
            provider=provider,
            duration_hours=duration_hours,
        )
        self._jobs.append(estimate)
        logger.info(
            f"[Carbon] Job {job_id}: {estimate.carbon_kg_co2eq}kg CO2eq "
            f"({estimate.energy_kwh}kWh × {estimate.carbon_intensity}gCO2/kWh, "
            f"{estimate.renewable_pct:.0f}% renewable)"
        )
        return estimate

    def recommend_green_region(
        self,
        gpu_type: str,
        providers: list[str] | None = None,
    ) -> list[dict]:
        """
        Return regions sorted by carbon intensity (greenest first).
        Optionally filtered by available providers.
        """
        results = []
        regions_checked = REGION_CARBON_INTENSITY.copy()

        for region, intensity in regions_checked.items():
            results.append({
                "region":            region,
                "carbon_intensity":  intensity,
                "renewable_pct":     RENEWABLE_PCT.get(region, 15.0),
                "rating":            self._green_rating(intensity),
                "vs_average_pct":    round((400 - intensity) / 400 * 100, 1),
            })

        return sorted(results, key=lambda r: r["carbon_intensity"])[:10]

    def get_stats(self) -> dict[str, Any]:
        """Aggregated carbon stats across all tracked jobs."""
        if not self._jobs:
            return {
                "total_jobs":           0,
                "total_energy_kwh":     0,
                "total_co2_kg":         0,
                "total_offset_usd":     0,
                "carbon_neutral":       False,
                "avg_intensity":        0,
                "greenest_region":      "europe-north1",
            }

        total_kwh  = sum(j.energy_kwh for j in self._jobs)
        total_co2  = sum(j.carbon_kg_co2eq for j in self._jobs)
        total_off  = sum(j.offset_cost_usd for j in self._jobs)
        avg_intens = sum(j.carbon_intensity for j in self._jobs) / len(self._jobs)

        return {
            "total_jobs":       len(self._jobs),
            "total_energy_kwh": round(total_kwh, 2),
            "total_co2_kg":     round(total_co2, 4),
            "total_co2_tonnes": round(total_co2 / 1000, 6),
            "total_offset_usd": round(total_off, 4),
            "carbon_neutral":   self._carbon_neutral,
            "avg_intensity_g_kwh": round(avg_intens, 1),
            "jobs_detail":      [j.to_dict() for j in self._jobs[-10:]],
            "greenest_region":  "europe-north1 (11 gCO2/kWh, 98% renewable)",
        }

    def purchase_offsets(self, amount_usd: float) -> dict:
        """Record a carbon offset purchase."""
        tonnes_offset = amount_usd / OFFSET_COST_PER_TONNE
        total_co2_tonnes = sum(j.carbon_kg_co2eq for j in self._jobs) / 1000
        self._total_offset_usd += amount_usd
        total_purchased_tonnes = self._total_offset_usd / OFFSET_COST_PER_TONNE
        self._carbon_neutral = total_purchased_tonnes >= total_co2_tonnes
        logger.info(f"[Carbon] Offset purchase: ${amount_usd} = {tonnes_offset:.4f}t CO2. "
                    f"Neutral: {self._carbon_neutral}")
        return {
            "purchased_usd":     amount_usd,
            "tonnes_offset":     round(tonnes_offset, 4),
            "total_co2_tonnes":  round(total_co2_tonnes, 4),
            "carbon_neutral":    self._carbon_neutral,
            "badge":             "🌿 Carbon Neutral" if self._carbon_neutral else None,
        }

    def monthly_report(self) -> dict:
        """Generate a monthly carbon report."""
        stats = self.get_stats()
        greenest = min(REGION_CARBON_INTENSITY.items(), key=lambda x: x[1])
        highest  = max(REGION_CARBON_INTENSITY.items(), key=lambda x: x[1])

        # Equivalent trees planted
        trees_equiv = stats["total_co2_kg"] / 21  # avg tree absorbs 21kg/yr

        return {
            **stats,
            "month":              datetime.now(timezone.utc).strftime("%B %Y"),
            "trees_equivalent":   round(trees_equiv, 1),
            "km_driven_equiv":    round(stats["total_co2_kg"] * 4, 1),  # ~250gCO2/km car
            "recommended_action": (
                f"Switch jobs from {highest[0]} ({highest[1]}gCO2/kWh) "
                f"to {greenest[0]} ({greenest[1]}gCO2/kWh) for 97% reduction"
            ),
            "offset_to_neutral_usd": round(
                max(0, stats["total_co2_tonnes"] * OFFSET_COST_PER_TONNE - self._total_offset_usd), 2
            ),
        }

    @staticmethod
    def _green_rating(intensity: float) -> str:
        if intensity < 50:   return "A+ 🌿"
        if intensity < 150:  return "A  ♻️"
        if intensity < 300:  return "B  ⚡"
        if intensity < 450:  return "C  ⚠️"
        return "D  ❌"


# ─── Singleton ────────────────────────────────────────────────────────────
_tracker: CarbonTracker | None = None

def get_carbon_tracker() -> CarbonTracker:
    global _tracker
    if _tracker is None:
        _tracker = CarbonTracker()
    return _tracker
