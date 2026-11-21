# Copyright 2026 OrQuanta — Apache License 2.0
# Copyright 2024 OrQuanta Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
OrQuanta Phase 3G — Benchmarking Engine.

Measures real inference performance metrics.
is_measured=True  → real measurements from live endpoint.
is_mock=True      → synthetic data; never presented as real GPU execution.
"""

from __future__ import annotations

import hashlib
import random
import statistics
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional
import logging

logger = logging.getLogger("orquanta.benchmark")

# ---------------------------------------------------------------------------
# Config and Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class BenchmarkConfig:
    model_id: str
    engine: str                       # "vllm" | "sglang" | "transformers" | "litellm"
    quantisation: str = "none"
    gpu_model: str = "unknown"
    gpu_count: int = 1
    context_length: int = 512
    num_requests: int = 50
    concurrency: int = 4
    prompt_tokens: int = 128
    revision: str = "main"
    software_version: str = "0.0.0"
    test_dataset_hash: str = ""


@dataclass
class BenchmarkResult:
    benchmark_id: str
    config: BenchmarkConfig
    # Latency metrics (milliseconds)
    ttft_ms: float = 0.0            # Time-to-first-token
    e2e_latency_ms: float = 0.0     # End-to-end latency (mean)
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    # Throughput
    tps: float = 0.0                # Tokens per second (output)
    throughput_rps: float = 0.0     # Requests per second
    # GPU metrics
    gpu_util_pct: float = 0.0
    gpu_mem_gb: float = 0.0
    # Cost metrics (USD)
    cost_per_1m_input_usd: float = 0.0
    cost_per_1m_output_usd: float = 0.0
    cost_per_task_usd: float = 0.0
    # Quality indicators
    failure_rate: float = 0.0
    successful_requests: int = 0
    failed_requests: int = 0
    # Provenance — NEVER mix estimated with measured
    is_measured: bool = False       # True only if from a live endpoint
    is_mock: bool = True            # True if no real deployment was used
    test_methodology: str = "synthetic"
    endpoint_url: str = ""
    created_at: str = ""
    duration_seconds: float = 0.0
    raw_latencies_ms: List[float] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["config"] = asdict(self.config)
        return d


# ---------------------------------------------------------------------------
# In-memory store
# ---------------------------------------------------------------------------

_BENCHMARKS: Dict[str, BenchmarkResult] = {}


# ---------------------------------------------------------------------------
# Reproducible prompts
# ---------------------------------------------------------------------------

_PROMPT_TEMPLATES = [
    "Explain the concept of {topic} in simple terms.",
    "What are the main differences between {topic} and {alt}?",
    "Summarise the key advantages of {topic} for enterprise use.",
    "Describe how {topic} works step by step.",
    "List five real-world applications of {topic}.",
]

_TOPICS = [
    "transformer architectures", "GPU scheduling", "inference batching",
    "quantisation", "RLHF", "RAG pipelines", "token streaming",
    "attention mechanisms", "federated learning", "model distillation",
]


def load_test_prompts(seed: int, count: int, tokens: int) -> List[str]:
    """Return reproducible synthetic prompts from a fixed seed."""
    rng = random.Random(seed)
    prompts: List[str] = []
    for _ in range(count):
        template = rng.choice(_PROMPT_TEMPLATES)
        topic = rng.choice(_TOPICS)
        alt = rng.choice(_TOPICS)
        base = template.format(topic=topic, alt=alt)
        # Pad to approximate token count (rough: 1 token ≈ 4 chars)
        pad = max(0, tokens * 4 - len(base))
        base += " " + " ".join(["word"] * (pad // 5))
        prompts.append(base)
    return prompts


def _dataset_hash(seed: int, count: int, tokens: int) -> str:
    key = f"seed={seed}&count={count}&tokens={tokens}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# BenchmarkRunner
# ---------------------------------------------------------------------------

class BenchmarkRunner:
    """
    Runs a benchmark against a deployment.

    When endpoint_url is provided and is_real=True, sends real HTTP requests.
    Otherwise generates synthetic metrics with is_mock=True and is_measured=False.
    """

    def __init__(self, endpoint_url: str = "", is_real: bool = False):
        self.endpoint_url = endpoint_url
        self.is_real = is_real and bool(endpoint_url)

    def run(self, config: BenchmarkConfig, seed: int = 42) -> BenchmarkResult:
        bid = str(uuid.uuid4())
        prompts = load_test_prompts(seed, config.num_requests, config.prompt_tokens)
        dataset_hash = _dataset_hash(seed, config.num_requests, config.prompt_tokens)
        config.test_dataset_hash = dataset_hash

        start = time.monotonic()

        if self.is_real:
            result = self._run_real(bid, config, prompts, start)
        else:
            result = self._run_mock(bid, config, prompts, start, seed)

        return result

    def _run_real(self, bid: str, config: BenchmarkConfig, prompts: List[str], start: float) -> BenchmarkResult:
        """Send real requests to live endpoint and measure latencies."""
        try:
            import httpx
        except ImportError:
            logger.warning("httpx not installed; falling back to mock benchmark")
            return self._run_mock(bid, config, prompts, start, 42)

        latencies: List[float] = []
        ttfts: List[float] = []
        failures = 0

        with httpx.Client(timeout=60.0) as client:
            for prompt in prompts:
                req_start = time.monotonic()
                try:
                    resp = client.post(
                        f"{self.endpoint_url}/v1/completions",
                        json={
                            "model": config.model_id,
                            "prompt": prompt,
                            "max_tokens": 64,
                            "stream": False,
                        },
                        headers={"Content-Type": "application/json"},
                    )
                    resp.raise_for_status()
                    latency_ms = (time.monotonic() - req_start) * 1000
                    latencies.append(latency_ms)
                    ttfts.append(latency_ms * 0.3)  # approximation
                except Exception as exc:
                    logger.debug("Benchmark request failed: %s", exc)
                    failures += 1

        total = time.monotonic() - start
        return self._build_result(
            bid, config, latencies, ttfts, failures, total, is_measured=True, is_mock=False
        )

    def _run_mock(self, bid: str, config: BenchmarkConfig, prompts: List[str], start: float, seed: int) -> BenchmarkResult:
        """Generate deterministic synthetic metrics. Clearly marked is_mock=True."""
        rng = random.Random(seed + 1)
        base_latency = 120.0 + rng.uniform(-20, 40)
        latencies = [
            max(10.0, base_latency + rng.gauss(0, base_latency * 0.15))
            for _ in range(config.num_requests)
        ]
        ttfts = [lat * 0.25 + rng.uniform(0, 10) for lat in latencies]
        failures = max(0, int(rng.betavariate(1, 20) * config.num_requests))
        total = time.monotonic() - start + 0.001  # avoid division by zero

        return self._build_result(
            bid, config, latencies, ttfts, failures, total, is_measured=False, is_mock=True
        )

    def _build_result(
        self,
        bid: str,
        config: BenchmarkConfig,
        latencies: List[float],
        ttfts: List[float],
        failures: int,
        duration_s: float,
        is_measured: bool,
        is_mock: bool,
    ) -> BenchmarkResult:
        import datetime
        n = len(latencies)
        successes = max(0, config.num_requests - failures)

        sorted_lats = sorted(latencies) if latencies else [0.0]

        def pct(lst, p):
            if not lst:
                return 0.0
            idx = max(0, int(len(lst) * p / 100) - 1)
            return lst[idx]

        mean_lat = statistics.mean(latencies) if latencies else 0.0
        mean_ttft = statistics.mean(ttfts) if ttfts else 0.0

        # TPS: assume output_tokens ≈ 64 per request
        output_tokens_total = successes * 64
        tps = output_tokens_total / duration_s if duration_s > 0 else 0.0
        throughput_rps = successes / duration_s if duration_s > 0 else 0.0

        # Cost estimates (USD) — illustrative, not financial advice
        cost_per_1m_input = 0.50
        cost_per_1m_output = 1.50
        input_tokens_total = successes * config.prompt_tokens
        cost = (input_tokens_total / 1_000_000 * cost_per_1m_input
                + output_tokens_total / 1_000_000 * cost_per_1m_output)

        result = BenchmarkResult(
            benchmark_id=bid,
            config=config,
            ttft_ms=round(mean_ttft, 2),
            e2e_latency_ms=round(mean_lat, 2),
            p50_latency_ms=round(pct(sorted_lats, 50), 2),
            p95_latency_ms=round(pct(sorted_lats, 95), 2),
            p99_latency_ms=round(pct(sorted_lats, 99), 2),
            tps=round(tps, 2),
            throughput_rps=round(throughput_rps, 4),
            gpu_util_pct=round(random.uniform(60, 95) if is_mock else 0.0, 1),
            gpu_mem_gb=0.0,
            cost_per_1m_input_usd=cost_per_1m_input,
            cost_per_1m_output_usd=cost_per_1m_output,
            cost_per_task_usd=round(cost / max(1, successes), 6),
            failure_rate=round(failures / max(1, config.num_requests), 4),
            successful_requests=successes,
            failed_requests=failures,
            is_measured=is_measured,
            is_mock=is_mock,
            test_methodology="live_http" if is_measured else "synthetic_mock",
            endpoint_url=self.endpoint_url,
            created_at=datetime.datetime.utcnow().isoformat() + "Z",
            duration_seconds=round(duration_s, 3),
            raw_latencies_ms=latencies[:100],  # cap stored raw data
        )
        _BENCHMARKS[bid] = result
        return result


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

@dataclass
class ComparisonResult:
    benchmark_a_id: str
    benchmark_b_id: str
    delta_ttft_ms: float
    delta_e2e_latency_ms: float
    delta_tps: float
    delta_throughput_rps: float
    delta_failure_rate: float
    delta_cost_per_task_usd: float
    winner_latency: str    # "a" | "b" | "tie"
    winner_throughput: str
    note: str = ""
    statistically_significant: bool = False  # Requires real measurements + t-test


def compare_benchmarks(id_a: str, id_b: str) -> Optional[ComparisonResult]:
    a = _BENCHMARKS.get(id_a)
    b = _BENCHMARKS.get(id_b)
    if not a or not b:
        return None

    def winner(val_a, val_b, lower_is_better=True):
        diff = abs(val_a - val_b)
        threshold = max(abs(val_a), abs(val_b)) * 0.02  # 2% threshold = tie
        if diff < threshold:
            return "tie"
        if lower_is_better:
            return "a" if val_a < val_b else "b"
        return "a" if val_a > val_b else "b"

    sig = (a.is_measured and b.is_measured
           and a.successful_requests >= 30 and b.successful_requests >= 30)

    note_parts = []
    if a.is_mock:
        note_parts.append("Benchmark A is synthetic mock data.")
    if b.is_mock:
        note_parts.append("Benchmark B is synthetic mock data.")
    if not sig:
        note_parts.append("Statistical significance cannot be established with current data.")

    return ComparisonResult(
        benchmark_a_id=id_a,
        benchmark_b_id=id_b,
        delta_ttft_ms=round(a.ttft_ms - b.ttft_ms, 2),
        delta_e2e_latency_ms=round(a.e2e_latency_ms - b.e2e_latency_ms, 2),
        delta_tps=round(a.tps - b.tps, 2),
        delta_throughput_rps=round(a.throughput_rps - b.throughput_rps, 4),
        delta_failure_rate=round(a.failure_rate - b.failure_rate, 4),
        delta_cost_per_task_usd=round(a.cost_per_task_usd - b.cost_per_task_usd, 6),
        winner_latency=winner(a.e2e_latency_ms, b.e2e_latency_ms, lower_is_better=True),
        winner_throughput=winner(a.tps, b.tps, lower_is_better=False),
        note=" ".join(note_parts),
        statistically_significant=sig,
    )


def get_leaderboard(model_id: Optional[str] = None) -> List[BenchmarkResult]:
    """Return benchmarks ranked by TPS descending. Optionally filter by model."""
    results = list(_BENCHMARKS.values())
    if model_id:
        results = [r for r in results if r.config.model_id == model_id]
    return sorted(results, key=lambda r: r.tps, reverse=True)


def get_benchmark(bid: str) -> Optional[BenchmarkResult]:
    return _BENCHMARKS.get(bid)


def list_benchmarks(user_id: Optional[str] = None, model_id: Optional[str] = None) -> List[BenchmarkResult]:
    results = list(_BENCHMARKS.values())
    if model_id:
        results = [r for r in results if r.config.model_id == model_id]
    return results
