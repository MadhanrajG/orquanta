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
OrQuanta Phase 3G — Benchmark API Router.

POST   /api/v1/benchmarks                   — start a benchmark run
GET    /api/v1/benchmarks                   — list runs
GET    /api/v1/benchmarks/{id}              — get single result
GET    /api/v1/benchmarks/compare           — compare two runs (?a=id1&b=id2)
GET    /api/v1/benchmarks/leaderboard       — ranked results (?model_id=x)
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

bench_router = APIRouter(prefix="/api/v1/benchmarks", tags=["benchmarks"])


# ---------------------------------------------------------------------------
# Auth dependency stub
# ---------------------------------------------------------------------------

def _get_current_user() -> Dict[str, Any]:
    return {"user_id": "demo-user", "tenant_id": "default"}


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------

class BenchmarkRequest(BaseModel):
    model_id: str
    deployment_id: str
    num_requests: int = 50
    concurrency: int = 4
    context_length: int = 512
    prompt_tokens: int = 128
    seed: int = 42


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@bench_router.post("", status_code=202)
def start_benchmark(body: BenchmarkRequest, current_user: Dict = Depends(_get_current_user)):
    """
    Start a benchmark run against a deployment.
    If deployment is not real (is_real=False), result will carry is_mock=True.
    """
    from inference.benchmark_engine import BenchmarkConfig, BenchmarkRunner

    # Check deployment exists and is ready (best-effort; not all deployments tracked)
    endpoint_url = ""
    is_real = False
    try:
        from inference.engine_interface import _DEPLOYMENTS
        dep = _DEPLOYMENTS.get(body.deployment_id)
        if dep is None:
            # Allow benchmark to run in mock mode against unknown deployment IDs
            pass
        elif dep.get("status") != "ready":
            raise HTTPException(
                status_code=409,
                detail=f"Deployment '{body.deployment_id}' is not ready (status: {dep.get('status')}). Cannot benchmark."
            )
        else:
            endpoint_url = dep.get("endpoint_url", "")
            is_real = bool(endpoint_url)
    except ImportError:
        pass  # engine_interface not yet available

    config = BenchmarkConfig(
        model_id=body.model_id,
        engine="unknown",
        context_length=body.context_length,
        num_requests=body.num_requests,
        concurrency=body.concurrency,
        prompt_tokens=body.prompt_tokens,
    )

    runner = BenchmarkRunner(endpoint_url=endpoint_url, is_real=is_real)
    result = runner.run(config, seed=body.seed)

    return {
        **result.to_dict(),
        "note": (
            "Benchmark ran against a live endpoint."
            if result.is_measured
            else "Benchmark is SYNTHETIC MOCK DATA — no real GPU execution occurred."
        ),
    }


@bench_router.get("")
def list_benchmarks(
    model_id: Optional[str] = Query(None),
    current_user: Dict = Depends(_get_current_user),
):
    from inference.benchmark_engine import list_benchmarks as _list
    results = _list(model_id=model_id)
    return [r.to_dict() for r in results]


@bench_router.get("/compare")
def compare_benchmarks(
    a: str = Query(..., description="Benchmark ID A"),
    b: str = Query(..., description="Benchmark ID B"),
    current_user: Dict = Depends(_get_current_user),
):
    from inference.benchmark_engine import compare_benchmarks as _cmp
    from dataclasses import asdict
    result = _cmp(a, b)
    if result is None:
        raise HTTPException(status_code=404, detail="One or both benchmark IDs not found")
    return asdict(result)


@bench_router.get("/leaderboard")
def leaderboard(
    model_id: Optional[str] = Query(None),
    current_user: Dict = Depends(_get_current_user),
):
    from inference.benchmark_engine import get_leaderboard
    results = get_leaderboard(model_id=model_id)
    return [r.to_dict() for r in results]


@bench_router.get("/{benchmark_id}")
def get_benchmark(benchmark_id: str, current_user: Dict = Depends(_get_current_user)):
    from inference.benchmark_engine import get_benchmark as _get
    result = _get(benchmark_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Benchmark not found")
    return result.to_dict()
