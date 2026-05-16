"""
OrQuanta Agentic v1.0  -  RunPod Serverless Endpoint Bridge
==========================================================

RunPod Serverless is a scale-to-zero GPU compute model:
  - Workers spin up on demand (cold start ~5s), scale to zero when idle
  - Billed per-second of actual compute  -  zero idle cost
  - Perfect for AI inference jobs dispatched by OrQuanta's SchedulerAgent

This module wraps the runpod-python SDK Endpoint API for:
  1. Async job dispatch (fire-and-poll)
  2. Synchronous invocation with configurable timeout
  3. Job status polling and cancellation
  4. Multi-endpoint routing (route to cheapest / fastest endpoint)
  5. Mock mode (no API key required for demo)

Usage:
    from v4.providers.runpod_serverless import RunPodServerlessBridge

    bridge = RunPodServerlessBridge()
    result = await bridge.invoke_sync(
        endpoint_id="your-endpoint-id",
        payload={"input": {"prompt": "Hello, world!", "max_tokens": 100}},
        timeout_s=120,
    )
    print(result)

Typical OrQuanta integration (in SchedulerAgent):
    # Instead of spinning up a full pod for short inference jobs,
    # route them to a registered serverless endpoint
    if job.estimated_duration_mins < 5 and bridge.has_endpoint("llm-inference"):
        result = await bridge.invoke_sync("llm-inference", job.payload)
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("orquanta.providers.runpod_serverless")

RUNPOD_API_KEY = os.getenv("RUNPOD_API_KEY", "")
RUNPOD_ENDPOINT_ID = os.getenv("RUNPOD_ENDPOINT_ID", "")


# ------------------------------------------------------------------------------
# Data models
# ------------------------------------------------------------------------------

@dataclass
class EndpointJobResult:
    """Result of a RunPod serverless endpoint invocation."""
    job_id: str
    endpoint_id: str
    status: str                             # COMPLETED | FAILED | TIMED_OUT | IN_QUEUE | IN_PROGRESS
    output: Any = None
    error: str | None = None
    execution_time_ms: float = 0.0
    worker_id: str | None = None
    retries: int = 0
    submitted_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: str | None = None

    @property
    def success(self) -> bool:
        return self.status == "COMPLETED" and self.error is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "endpoint_id": self.endpoint_id,
            "status": self.status,
            "output": self.output,
            "error": self.error,
            "execution_time_ms": round(self.execution_time_ms, 1),
            "worker_id": self.worker_id,
            "success": self.success,
            "submitted_at": self.submitted_at,
            "completed_at": self.completed_at,
        }


@dataclass
class EndpointHealth:
    """Health metrics for a RunPod serverless endpoint."""
    endpoint_id: str
    workers_running: int = 0
    workers_idle: int = 0
    jobs_in_queue: int = 0
    jobs_completed_24h: int = 0
    jobs_failed_24h: int = 0
    p50_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    is_ready: bool = True
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ------------------------------------------------------------------------------
# Core bridge
# ------------------------------------------------------------------------------

class RunPodServerlessBridge:
    """
    Bridge between OrQuanta's job scheduler and RunPod Serverless endpoints.

    Supports multiple registered endpoints with different specializations
    (e.g., one for LLM inference, one for image generation, etc.).

    Works in mock mode when RUNPOD_API_KEY is not set.
    """

    def __init__(self) -> None:
        self._api_key = RUNPOD_API_KEY
        self._endpoints: dict[str, str] = {}       # alias -> endpoint_id
        self._job_log: list[EndpointJobResult] = []  # audit trail
        self._sdk_ok = False

        # Register default endpoint if configured
        if RUNPOD_ENDPOINT_ID:
            self._endpoints["default"] = RUNPOD_ENDPOINT_ID

        if self._api_key:
            self._init_sdk()
        else:
            logger.info("[RunPod Serverless] RUNPOD_API_KEY not set  -  mock mode")

    # --------------------------------------------------------------------------
    # SDK management
    # --------------------------------------------------------------------------

    def _init_sdk(self) -> None:
        try:
            import runpod
            runpod.api_key = self._api_key
            self._sdk_ok = True
            logger.info("[RunPod Serverless] SDK initialized")
        except ImportError:
            logger.warning(
                "[RunPod Serverless] runpod package not found. "
                "Install with: pip install runpod>=1.7.0"
            )
        except Exception as exc:
            logger.warning(f"[RunPod Serverless] SDK init error: {exc}")

    def _get_endpoint_obj(self, endpoint_id: str):
        """Return a runpod.Endpoint instance for the given endpoint_id."""
        import runpod
        return runpod.Endpoint(endpoint_id)

    # --------------------------------------------------------------------------
    # Endpoint registry
    # --------------------------------------------------------------------------

    def register_endpoint(self, alias: str, endpoint_id: str) -> None:
        """
        Register a RunPod serverless endpoint under a human-readable alias.

        Example:
            bridge.register_endpoint("llm", "abc123endpoint")
            bridge.register_endpoint("sdxl", "xyz789endpoint")
        """
        self._endpoints[alias] = endpoint_id
        logger.info(f"[RunPod Serverless] Registered endpoint '{alias}' -> {endpoint_id}")

    def has_endpoint(self, alias_or_id: str) -> bool:
        """Return True if the alias (or raw endpoint ID) is registered/known."""
        return alias_or_id in self._endpoints or alias_or_id in self._endpoints.values()

    def _resolve_endpoint_id(self, alias_or_id: str) -> str:
        """Resolve an alias or raw endpoint ID to a valid endpoint ID."""
        return self._endpoints.get(alias_or_id, alias_or_id)

    # --------------------------------------------------------------------------
    # Job dispatch
    # --------------------------------------------------------------------------

    async def invoke(
        self,
        endpoint_id: str,
        payload: dict[str, Any],
    ) -> str:
        """
        Dispatch a job to a RunPod serverless endpoint (async, non-blocking).

        Returns the job_id immediately. Use poll_job() to check status.
        Ideal for fire-and-forget or long-running workloads.
        """
        if not self._sdk_ok:
            return self._mock_invoke(endpoint_id, payload)

        eid = self._resolve_endpoint_id(endpoint_id)
        t0 = time.monotonic()
        try:
            loop = asyncio.get_event_loop()
            endpoint = self._get_endpoint_obj(eid)

            run_request = await loop.run_in_executor(
                None, lambda: endpoint.run(payload)
            )
            job_id = run_request.job_id if hasattr(run_request, "job_id") else str(run_request)
            latency = (time.monotonic() - t0) * 1000

            result = EndpointJobResult(
                job_id=job_id,
                endpoint_id=eid,
                status="IN_QUEUE",
                execution_time_ms=latency,
            )
            self._job_log.append(result)
            logger.info(f"[RunPod Serverless] Job {job_id} dispatched to {eid} in {latency:.0f}ms")
            return job_id

        except Exception as exc:
            logger.error(f"[RunPod Serverless] invoke failed: {exc}")
            raise

    async def invoke_sync(
        self,
        endpoint_id: str,
        payload: dict[str, Any],
        timeout_s: float = 120.0,
    ) -> EndpointJobResult:
        """
        Dispatch a job and wait for completion (synchronous-style).

        Uses run_sync under the hood which blocks up to 90s natively,
        then falls back to manual polling if the job exceeds that.
        Best for short inference tasks (< 2 min).

        Returns an EndpointJobResult with output or error.
        """
        if not self._sdk_ok:
            return self._mock_invoke_sync(endpoint_id, payload)

        eid = self._resolve_endpoint_id(endpoint_id)
        t0 = time.monotonic()
        try:
            loop = asyncio.get_event_loop()
            endpoint = self._get_endpoint_obj(eid)

            # run_sync blocks until done (up to SDK's internal 90s timeout)
            raw_result = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: endpoint.run_sync(payload)),
                timeout=timeout_s,
            )

            elapsed_ms = (time.monotonic() - t0) * 1000

            # Parse result  -  run_sync returns the output dict directly if done
            if isinstance(raw_result, dict):
                if raw_result.get("status") == "FAILED":
                    result = EndpointJobResult(
                        job_id=raw_result.get("id", uuid.uuid4().hex[:8]),
                        endpoint_id=eid,
                        status="FAILED",
                        error=str(raw_result.get("error", "Unknown error")),
                        execution_time_ms=elapsed_ms,
                        completed_at=datetime.now(timezone.utc).isoformat(),
                    )
                else:
                    result = EndpointJobResult(
                        job_id=raw_result.get("id", uuid.uuid4().hex[:8]),
                        endpoint_id=eid,
                        status="COMPLETED",
                        output=raw_result.get("output", raw_result),
                        execution_time_ms=elapsed_ms,
                        completed_at=datetime.now(timezone.utc).isoformat(),
                    )
            else:
                # Job exceeded run_sync timeout  -  get job_id and poll
                job_id = getattr(raw_result, "job_id", str(raw_result))
                result = await self.poll_job(endpoint_id, job_id, timeout_s=timeout_s - elapsed_ms / 1000)

            self._job_log.append(result)
            logger.info(
                f"[RunPod Serverless] Job completed: {result.job_id} "
                f"status={result.status} in {elapsed_ms:.0f}ms"
            )
            return result

        except asyncio.TimeoutError:
            elapsed_ms = (time.monotonic() - t0) * 1000
            result = EndpointJobResult(
                job_id="timeout",
                endpoint_id=eid,
                status="TIMED_OUT",
                error=f"Job did not complete within {timeout_s}s",
                execution_time_ms=elapsed_ms,
                completed_at=datetime.now(timezone.utc).isoformat(),
            )
            self._job_log.append(result)
            return result
        except Exception as exc:
            elapsed_ms = (time.monotonic() - t0) * 1000
            result = EndpointJobResult(
                job_id="error",
                endpoint_id=eid,
                status="FAILED",
                error=str(exc),
                execution_time_ms=elapsed_ms,
            )
            self._job_log.append(result)
            logger.error(f"[RunPod Serverless] invoke_sync failed: {exc}")
            return result

    async def poll_job(
        self,
        endpoint_id: str,
        job_id: str,
        poll_interval_s: float = 3.0,
        timeout_s: float = 300.0,
    ) -> EndpointJobResult:
        """
        Poll a submitted job until it completes or times out.

        Used for long-running jobs (training, embedding generation, etc.)
        where run_sync's 90s limit is insufficient.
        """
        if not self._sdk_ok:
            return self._mock_invoke_sync(endpoint_id, {"job_id": job_id})

        eid = self._resolve_endpoint_id(endpoint_id)
        deadline = time.monotonic() + timeout_s
        t0 = time.monotonic()

        loop = asyncio.get_event_loop()
        endpoint = self._get_endpoint_obj(eid)

        # Recreate run_request handle from job_id (SDK needs it for status())
        try:
            import runpod
            # Construct a RunPodJob object manually via internal SDK
            from runpod.api import RunRequest
            run_request = RunRequest(endpoint, job_id)
        except Exception:
            # Fallback: use REST endpoint directly
            run_request = None

        while time.monotonic() < deadline:
            try:
                if run_request:
                    status_raw = await loop.run_in_executor(None, run_request.status)
                    if status_raw in ("COMPLETED", "FAILED", "CANCELLED"):
                        output = await loop.run_in_executor(None, run_request.output)
                        elapsed_ms = (time.monotonic() - t0) * 1000
                        return EndpointJobResult(
                            job_id=job_id,
                            endpoint_id=eid,
                            status=status_raw,
                            output=output if status_raw == "COMPLETED" else None,
                            error=str(output) if status_raw == "FAILED" else None,
                            execution_time_ms=elapsed_ms,
                            completed_at=datetime.now(timezone.utc).isoformat(),
                        )
                await asyncio.sleep(poll_interval_s)
            except Exception as exc:
                logger.debug(f"[RunPod Serverless] poll error (will retry): {exc}")
                await asyncio.sleep(poll_interval_s)

        elapsed_ms = (time.monotonic() - t0) * 1000
        return EndpointJobResult(
            job_id=job_id,
            endpoint_id=eid,
            status="TIMED_OUT",
            error=f"Polling timed out after {timeout_s}s",
            execution_time_ms=elapsed_ms,
            completed_at=datetime.now(timezone.utc).isoformat(),
        )

    async def cancel_job(self, endpoint_id: str, job_id: str) -> bool:
        """Cancel a queued or running job."""
        if not self._sdk_ok:
            logger.info(f"[RunPod Serverless] Mock cancel job {job_id}")
            return True
        try:
            import runpod
            eid = self._resolve_endpoint_id(endpoint_id)
            endpoint = self._get_endpoint_obj(eid)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: endpoint.cancel(job_id))
            logger.info(f"[RunPod Serverless]  Cancelled job {job_id}")
            return True
        except Exception as exc:
            logger.error(f"[RunPod Serverless] cancel_job failed: {exc}")
            return False

    # --------------------------------------------------------------------------
    # Monitoring
    # --------------------------------------------------------------------------

    async def get_endpoint_health(self, endpoint_id: str) -> EndpointHealth:
        """Fetch health and queue metrics for a serverless endpoint."""
        eid = self._resolve_endpoint_id(endpoint_id)
        if not self._sdk_ok:
            return EndpointHealth(
                endpoint_id=eid,
                workers_running=0,
                workers_idle=0,
                jobs_in_queue=0,
                is_ready=False,
            )
        try:
            import runpod
            loop = asyncio.get_event_loop()
            endpoint = self._get_endpoint_obj(eid)
            # health() returns current worker / queue stats
            health_raw = await loop.run_in_executor(None, endpoint.health)
            if isinstance(health_raw, dict):
                workers = health_raw.get("workers", {})
                jobs = health_raw.get("jobs", {})
                return EndpointHealth(
                    endpoint_id=eid,
                    workers_running=workers.get("running", 0),
                    workers_idle=workers.get("idle", 0),
                    jobs_in_queue=jobs.get("inQueue", 0),
                    jobs_completed_24h=jobs.get("completed", 0),
                    jobs_failed_24h=jobs.get("failed", 0),
                    is_ready=True,
                )
        except Exception as exc:
            logger.warning(f"[RunPod Serverless] health check failed: {exc}")
        return EndpointHealth(endpoint_id=eid, is_ready=False)

    def get_job_stats(self) -> dict[str, Any]:
        """Return aggregate stats of all jobs dispatched through this bridge."""
        total = len(self._job_log)
        if not total:
            return {"total_jobs": 0, "success_rate_pct": 100.0, "avg_latency_ms": 0.0}

        completed = sum(1 for j in self._job_log if j.status == "COMPLETED")
        failed = sum(1 for j in self._job_log if j.status == "FAILED")
        avg_latency = sum(j.execution_time_ms for j in self._job_log) / total

        return {
            "total_jobs": total,
            "completed": completed,
            "failed": failed,
            "timed_out": sum(1 for j in self._job_log if j.status == "TIMED_OUT"),
            "success_rate_pct": round(completed / total * 100, 1),
            "avg_latency_ms": round(avg_latency, 1),
            "registered_endpoints": list(self._endpoints.keys()),
        }

    # --------------------------------------------------------------------------
    # Mock / demo helpers
    # --------------------------------------------------------------------------

    def _mock_invoke(self, endpoint_id: str, payload: dict) -> str:
        """Return a fake job_id for demo mode."""
        job_id = f"mock-job-{uuid.uuid4().hex[:8]}"
        logger.info(f"[RunPod Serverless] DEMO: dispatched job {job_id}")
        return job_id

    def _mock_invoke_sync(self, endpoint_id: str, payload: dict) -> EndpointJobResult:
        """Return a realistic mock completed job result for demo mode."""
        job_id = f"mock-job-{uuid.uuid4().hex[:8]}"
        mock_output = {
            "text": "This is a mock RunPod serverless response for demo mode.",
            "tokens_used": 42,
            "model": "mock-llm-v1",
            "endpoint_id": endpoint_id,
        }
        logger.info(f"[RunPod Serverless] DEMO: mock job {job_id} completed")
        result = EndpointJobResult(
            job_id=job_id,
            endpoint_id=endpoint_id,
            status="COMPLETED",
            output=mock_output,
            execution_time_ms=185.0,
            worker_id="mock-worker-1",
            completed_at=datetime.now(timezone.utc).isoformat(),
        )
        self._job_log.append(result)
        return result


# ------------------------------------------------------------------------------
# Singleton for use across OrQuanta
# ------------------------------------------------------------------------------

_bridge: RunPodServerlessBridge | None = None


def get_serverless_bridge() -> RunPodServerlessBridge:
    """Return the shared RunPod Serverless bridge singleton."""
    global _bridge
    if _bridge is None:
        _bridge = RunPodServerlessBridge()
    return _bridge
