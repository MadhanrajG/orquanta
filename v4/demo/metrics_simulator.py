"""
OrQuanta Agentic v1.0 — Live Metrics Simulator
===============================================

Background process that continuously generates realistic GPU metrics
in demo mode and pushes them to all WebSocket subscribers.

Features:
  - GPU utilization: 60–95% (sine-wave with noise)
  - VRAM: climbs as job progresses, with occasional spikes
  - Temperature: 65–78°C realistic thermal curve
  - Power: 250–450W for A100 class GPUs
  - Cost: accumulates per-second at configured rate
  - PCIe bandwidth: 15–31 GB/s
"""
from __future__ import annotations

import asyncio
import logging
import math
import random
import time
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("orquanta.demo.metrics")


class MetricsSimulator:
    """
    Generates and streams realistic GPU telemetry on a 5-second heartbeat.
    Used to make the Grafana/dashboard look live during demos.
    """

    # GPU spec profiles for realistic metrics
    GPU_PROFILES = {
        "gpu_1x_a10": {
            "vram_gb": 24, "max_power_w": 150, "pcie_lanes": 16,
            "mem_bw_gbs": 600, "typical_util": 75,
        },
        "gpu_1x_a100": {
            "vram_gb": 80, "max_power_w": 400, "pcie_lanes": 16,
            "mem_bw_gbs": 2000, "typical_util": 82,
        },
        "gpu_1x_h100_pcie": {
            "vram_gb": 80, "max_power_w": 350, "pcie_lanes": 16,
            "mem_bw_gbs": 2000, "typical_util": 88,
        },
        "gpu_8x_a100": {
            "vram_gb": 640, "max_power_w": 3200, "pcie_lanes": 16,
            "mem_bw_gbs": 16000, "typical_util": 85,
        },
    }
    DEFAULT_PROFILE = GPU_PROFILES["gpu_1x_a100"]

    def __init__(
        self,
        gpu_type: str = "gpu_1x_a100",
        job_duration_min: int = 30,
        interval_s: float = 5.0,
    ) -> None:
        self._gpu_type      = gpu_type
        self._profile       = self.GPU_PROFILES.get(gpu_type, self.DEFAULT_PROFILE)
        self._duration_s    = job_duration_min * 60
        self._interval      = interval_s
        self._started_at    = time.monotonic()
        self._running       = False
        self._step          = 0
        self._callbacks: list[Any] = []

        # State variables for smooth metric evolution
        self._base_util     = float(self._profile["typical_util"])
        self._base_mem      = 40.0
        self._trend_util    = 0.0
        self._trend_mem     = 0.0

    # ─── Subscription ─────────────────────────────────────────────────────────

    def add_callback(self, fn) -> None:
        """Register an async callback for each metrics push."""
        self._callbacks.append(fn)

    def remove_callback(self, fn) -> None:
        self._callbacks = [c for c in self._callbacks if c != fn]

    # ─── Control ──────────────────────────────────────────────────────────────

    async def start(self) -> asyncio.Task:
        """Start the metrics pump. Returns the background task."""
        self._running = True
        task = asyncio.create_task(self._pump())
        logger.info(f"[MetricsSim] Started for {self._gpu_type} (interval={self._interval}s)")
        return task

    async def stop(self) -> None:
        self._running = False

    # ─── Metric generation ────────────────────────────────────────────────────

    def _generate_metrics(self) -> dict:
        """Generate one metrics snapshot."""
        t      = time.monotonic() - self._started_at
        pct    = min(1.0, t / self._duration_s)
        step   = self._step
        prof   = self._profile

        # ── GPU Utilization ───────────────────────────────────────────────────
        # Pattern: ramp up in first 20%, sustain at 80-95%, dip at end
        if pct < 0.15:
            target_util = 40 + 50 * (pct / 0.15)
        elif pct > 0.90:
            target_util = self._base_util * (1.0 - (pct - 0.90) / 0.1 * 0.3)
        else:
            target_util = prof["typical_util"]

        # Add wave + noise
        wave   = 8  * math.sin(step * 0.4) + 4 * math.sin(step * 1.1 + 0.5)
        noise  = random.gauss(0, 2.5)
        gpu_util = max(5, min(99, target_util + wave + noise))

        # ── VRAM Usage ───────────────────────────────────────────────────────
        # Climbs as job loads data, then stabilizes
        mem_base = 35 + 40 * min(1.0, pct / 0.3)
        mem_wave = 6 * math.sin(step * 0.25)
        mem_noise = random.gauss(0, 1.5)
        # Occasional spike simulation
        if random.random() < 0.03:
            mem_noise += random.uniform(5, 15)
        vram_pct = max(10, min(97, mem_base + mem_wave + mem_noise))
        vram_gb  = round(vram_pct / 100 * prof["vram_gb"], 2)

        # ── Temperature ──────────────────────────────────────────────────────
        temp_base = 62 + 14 * (gpu_util / 100)
        temp_wave = 3 * math.sin(step * 0.15)
        temp = max(45, min(84, temp_base + temp_wave + random.gauss(0, 1.0)))

        # ── Power ─────────────────────────────────────────────────────────────
        power = prof["max_power_w"] * (gpu_util / 100) * random.uniform(0.9, 1.05)
        power = max(50, min(prof["max_power_w"], power))

        # ── PCIe Bandwidth ────────────────────────────────────────────────────
        pcie_bw = prof["mem_bw_gbs"] * (gpu_util / 100) * random.uniform(0.6, 0.95)

        # ── Training metrics ──────────────────────────────────────────────────
        loss = max(0.40, 3.5 * math.exp(-pct * 4)) + random.gauss(0, 0.02)
        lr   = 2e-4 * (0.1 ** (pct * 2))

        self._step += 1

        return {
            "timestamp":          datetime.now(timezone.utc).isoformat(),
            "gpu_type":           self._gpu_type,
            "progress_pct":       round(pct * 100, 1),
            "elapsed_s":          round(t, 0),

            # GPU metrics
            "gpu_utilization":    round(gpu_util, 1),
            "memory_used_gb":     vram_gb,
            "memory_total_gb":    prof["vram_gb"],
            "memory_pct":         round(vram_pct, 1),
            "temperature_c":      round(temp, 1),
            "power_watts":        round(power, 1),
            "pcie_bandwidth_gbs": round(pcie_bw, 1),

            # Training metrics
            "loss":               round(loss, 4),
            "learning_rate":      round(lr, 8),
            "throughput_samples_s": round(gpu_util * 3.2 + random.uniform(-20, 20), 0),

            # System
            "cpu_pct":            round(random.uniform(15, 45), 1),
            "ram_pct":            round(random.uniform(30, 65), 1),
            "disk_read_mbs":      round(random.uniform(10, 180), 1),
            "disk_write_mbs":     round(random.uniform(2, 40), 1),
        }

    async def _pump(self) -> None:
        """Main metrics pump loop."""
        while self._running:
            try:
                metrics = self._generate_metrics()
                for cb in list(self._callbacks):
                    try:
                        if asyncio.iscoroutinefunction(cb):
                            await cb(metrics)
                        else:
                            cb(metrics)
                    except Exception as exc:
                        logger.debug(f"[MetricsSim] Callback error: {exc}")

                # Stop when job duration elapsed
                elapsed = time.monotonic() - self._started_at
                if elapsed >= self._duration_s + 10:
                    logger.info("[MetricsSim] Job duration elapsed — stopping")
                    break

            except Exception as exc:
                logger.error(f"[MetricsSim] Pump error: {exc}")

            await asyncio.sleep(self._interval)


# ─── Spot Price Simulator ─────────────────────────────────────────────────────

class SpotPriceSimulator:
    """
    Simulates real-time spot price fluctuations across 4 providers.
    Lambda Labs prices are fairly stable; AWS/GCP/Azure have more volatility.
    """

    BASE_PRICES = {
        # (provider, gpu_type): base_price_usd_hr
        ("aws",       "A100"): 4.10,
        ("gcp",       "A100"): 3.28,
        ("azure",     "A100"): 3.85,
        ("lambda",    "A100"): 1.99,
        ("aws",       "H100"): 6.50,
        ("gcp",       "H100"): 5.80,
        ("azure",     "H100"): 6.20,
        ("lambda",    "H100"): 2.99,
        ("aws",       "A10"):  1.10,
        ("gcp",       "A10"):  0.90,
        ("lambda",    "A10"):  0.75,
    }

    def __init__(self, interval_s: float = 60.0) -> None:
        self._interval = interval_s
        self._running  = False
        self._step     = 0
        self._callbacks: list = []

    def add_callback(self, fn) -> None:
        self._callbacks.append(fn)

    async def start(self) -> asyncio.Task:
        self._running = True
        return asyncio.create_task(self._pump())

    async def stop(self) -> None:
        self._running = False

    def _generate_prices(self) -> dict:
        prices = {}
        for (provider, gpu_type), base in self.BASE_PRICES.items():
            # AWS/GCP/Azure have ±20% spot volatility; Lambda is stable ±3%
            volatility = 0.03 if provider == "lambda" else 0.20
            wave = 0.08 * math.sin(self._step * 0.1 + hash(provider) % 10)
            noise = random.gauss(0, volatility * 0.4)
            price = max(base * 0.7, base * (1 + wave + noise))
            prices[f"{provider}:{gpu_type}"] = round(price, 3)
        self._step += 1
        return {"timestamp": datetime.now(timezone.utc).isoformat(), "prices": prices}

    async def _pump(self) -> None:
        while self._running:
            prices = self._generate_prices()
            for cb in list(self._callbacks):
                try:
                    if asyncio.iscoroutinefunction(cb):
                        await cb(prices)
                    else:
                        cb(prices)
                except Exception:
                    pass
            await asyncio.sleep(self._interval)
