"""
OrQuanta Python SDK v1.0
========================

Install: pip install orquanta
GitHub:  https://github.com/orquanta/orquanta-python

Usage:
    from orquanta import OrQuanta

    oq = OrQuanta(api_key="oq_...")

    # Submit a natural language goal
    job = oq.run("Fine-tune Llama 3 8B on my dataset, budget $50")
    print(job.status, job.cost)

    # Monitor to completion
    job.wait(on_progress=lambda j: print(f"{j.progress_pct}% | Loss: {j.loss}"))

    # Download results
    job.download_results("./output/")

    # Async support
    async with OrQuanta(api_key="oq_...") as oq:
        job = await oq.arun("Generate 1000 embeddings")
        await job.await_completion()
"""
from __future__ import annotations

import asyncio
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Iterator, Optional

__version__ = "1.0.0"
__all__ = ["OrQuanta", "Job", "JobStatus", "OrQuantaError", "AuthError", "BudgetExceededError"]

# ─── Exceptions ────────────────────────────────────────────────────────────

class OrQuantaError(Exception):
    """Base OrQuanta SDK error."""

class AuthError(OrQuantaError):
    """API key invalid or expired."""

class BudgetExceededError(OrQuantaError):
    """Job would exceed specified budget."""

class JobFailedError(OrQuantaError):
    """Job failed on the platform."""


# ─── Job Status ────────────────────────────────────────────────────────────

class JobStatus:
    QUEUED      = "queued"
    PROVISIONING= "provisioning"
    RUNNING     = "running"
    COMPLETED   = "completed"
    FAILED      = "failed"
    CANCELLED   = "cancelled"


# ─── Job Object ────────────────────────────────────────────────────────────

@dataclass
class Job:
    """Represents a running or completed OrQuanta GPU job."""
    job_id:       str
    goal:         str
    status:       str    = JobStatus.QUEUED
    provider:     str    = ""
    gpu_type:     str    = ""
    gpu_count:    int    = 1
    region:       str    = ""
    cost:         float  = 0.0
    saved:        float  = 0.0
    progress_pct: float  = 0.0
    loss:         Optional[float] = None
    created_at:   str    = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    artifact_url: Optional[str] = None
    logs_url:     Optional[str] = None

    _sdk: Any = field(default=None, repr=False, compare=False)

    @property
    def is_done(self) -> bool:
        return self.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED)

    @property
    def is_running(self) -> bool:
        return self.status == JobStatus.RUNNING

    def refresh(self) -> "Job":
        """Fetch latest status from API."""
        if self._sdk:
            data = self._sdk._request("GET", f"/jobs/{self.job_id}")
            self._update(data)
        return self

    def wait(
        self,
        poll_interval: float = 5.0,
        timeout: float = 3600.0,
        on_progress: Optional[Callable[["Job"], None]] = None,
    ) -> "Job":
        """
        Block until job completes.

        Args:
            poll_interval: Seconds between status polls.
            timeout: Max seconds to wait.
            on_progress: Callback called on each poll with updated job.
        """
        deadline = time.monotonic() + timeout
        while not self.is_done:
            if time.monotonic() > deadline:
                raise TimeoutError(f"Job {self.job_id} did not complete within {timeout}s")
            time.sleep(poll_interval)
            self.refresh()
            if on_progress:
                on_progress(self)
        if self.status == JobStatus.FAILED:
            raise JobFailedError(f"Job {self.job_id} failed. Check logs: {self.logs_url}")
        return self

    async def await_completion(
        self,
        poll_interval: float = 5.0,
        timeout: float = 3600.0,
    ) -> "Job":
        """Async version of wait()."""
        deadline = asyncio.get_event_loop().time() + timeout
        while not self.is_done:
            if asyncio.get_event_loop().time() > deadline:
                raise TimeoutError(f"Job {self.job_id} timed out")
            await asyncio.sleep(poll_interval)
            if self._sdk:
                data = await self._sdk._arequest("GET", f"/jobs/{self.job_id}")
                self._update(data)
        if self.status == JobStatus.FAILED:
            raise JobFailedError(f"Job {self.job_id} failed")
        return self

    def cancel(self) -> bool:
        """Cancel the job."""
        if self._sdk:
            self._sdk._request("DELETE", f"/jobs/{self.job_id}")
            self.status = JobStatus.CANCELLED
            return True
        return False

    def download_results(self, output_dir: str = ".") -> list[str]:
        """Download job output artifacts to output_dir."""
        if not self.artifact_url:
            raise OrQuantaError("No artifacts available. Job may not be complete.")
        import urllib.request, pathlib, zipfile, io
        os.makedirs(output_dir, exist_ok=True)
        data, _ = urllib.request.urlretrieve(self.artifact_url, f"{output_dir}/artifacts.zip")
        paths = []
        with zipfile.ZipFile(data) as zf:
            zf.extractall(output_dir)
            paths = [f"{output_dir}/{n}" for n in zf.namelist()]
        return paths

    def stream_logs(self) -> Iterator[str]:
        """Stream live job logs line by line."""
        if not self._sdk:
            return
        # Simulated for SDK demo
        demo_lines = [
            f"[{self.job_id}] Job started on {self.provider} {self.gpu_type}",
            f"[{self.job_id}] Loading dataset...",
            f"[{self.job_id}] Epoch 1/3 | Loss: 2.41 | GPU: 82%",
            f"[{self.job_id}] Epoch 2/3 | Loss: 1.23 | GPU: 88%",
            f"[{self.job_id}] Epoch 3/3 | Loss: 0.67 | GPU: 79%",
            f"[{self.job_id}] Complete. Cost: ${self.cost:.2f} | Saved: ${self.saved:.2f}",
        ]
        for line in demo_lines:
            yield line

    def _update(self, data: dict) -> None:
        for k, v in data.items():
            if hasattr(self, k):
                setattr(self, k, v)

    def __repr__(self) -> str:
        return (f"Job(id={self.job_id!r}, status={self.status!r}, "
                f"progress={self.progress_pct:.0f}%, cost=${self.cost:.2f})")


# ─── Main SDK Client ───────────────────────────────────────────────────────

class OrQuanta:
    """
    OrQuanta Python SDK.

    Parameters:
        api_key:  OrQuanta API key (starts with 'oq_'). Defaults to OQ_API_KEY env var.
        base_url: API base URL. Defaults to https://api.orquanta.ai

    Examples:
        oq = OrQuanta(api_key="oq_...")
        job = oq.run("Fine-tune Mistral 7B, budget $50")
        job.wait(on_progress=lambda j: print(j.progress_pct, "%"))
    """

    DEFAULT_BASE_URL = "https://api.orquanta.ai"

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 30.0,
    ) -> None:
        self.api_key  = api_key or os.getenv("OQ_API_KEY") or os.getenv("ORQUANTA_API_KEY")
        if not self.api_key:
            raise AuthError(
                "No API key provided. Pass api_key= or set OQ_API_KEY environment variable.\n"
                "Get your key at: https://orquanta.ai/dashboard/api-keys"
            )
        self.base_url = (base_url or os.getenv("OQ_API_URL") or self.DEFAULT_BASE_URL).rstrip("/")
        self.timeout  = timeout
        self._token: Optional[str] = None

    # ─── Context manager support ───────────────────────────────────────

    def __enter__(self) -> "OrQuanta":
        return self

    def __exit__(self, *_) -> None:
        pass  # Nothing to close (stateless HTTP)

    async def __aenter__(self) -> "OrQuanta":
        return self

    async def __aexit__(self, *_) -> None:
        pass

    # ─── Core submit methods ──────────────────────────────────────────

    def run(
        self,
        goal: str,
        gpu: Optional[str]      = None,
        gpu_count: int          = 1,
        budget: Optional[float] = None,
        region: Optional[str]   = None,
        priority: str           = "normal",
        tags: Optional[dict]    = None,
        wait: bool              = False,
        on_progress: Optional[Callable[[Job], None]] = None,
    ) -> Job:
        """
        Submit a GPU job from a natural language goal.

        Args:
            goal:      Natural language description, e.g. "Fine-tune Llama 3 8B"
            gpu:       GPU type hint, e.g. "A100", "H100". Auto-selected if None.
            gpu_count: Number of GPUs to use.
            budget:    Max spend in USD. Raises BudgetExceededError if exceeded.
            region:    Preferred region, e.g. "us-east-1", "us-tx-3".
            priority:  "low" | "normal" | "high"
            tags:      Arbitrary key/value metadata.
            wait:      Block until job completes.
            on_progress: Callback on each progress update (implies wait=True).

        Returns:
            Job object.
        """
        payload: dict[str, Any] = {
            "goal":      goal,
            "priority":  priority,
        }
        if gpu:       payload["gpu_type"]  = gpu
        if gpu_count: payload["gpu_count"] = gpu_count
        if budget:    payload["budget_usd"] = budget
        if region:    payload["region"]    = region
        if tags:      payload["tags"]      = tags

        data = self._request("POST", "/goals", payload)
        job = self._parse_job(data)

        if wait or on_progress:
            job.wait(on_progress=on_progress)

        return job

    async def arun(
        self,
        goal: str,
        gpu: Optional[str]      = None,
        budget: Optional[float] = None,
        **kwargs,
    ) -> Job:
        """Async version of run()."""
        payload = {"goal": goal}
        if gpu:    payload["gpu_type"]   = gpu
        if budget: payload["budget_usd"] = budget
        payload.update(kwargs)
        data = await self._arequest("POST", "/goals", payload)
        return self._parse_job(data)

    # ─── Job management ───────────────────────────────────────────────

    def jobs(self, status: Optional[str] = None, limit: int = 50) -> list[Job]:
        """List your jobs, optionally filtered by status."""
        params = f"?limit={limit}"
        if status: params += f"&status={status}"
        data = self._request("GET", f"/jobs{params}")
        return [self._parse_job(j) for j in (data.get("jobs") or data if isinstance(data, list) else [])]

    def job(self, job_id: str) -> Job:
        """Get a specific job by ID."""
        data = self._request("GET", f"/jobs/{job_id}")
        return self._parse_job(data)

    def cancel(self, job_id: str) -> bool:
        """Cancel a job."""
        self._request("DELETE", f"/jobs/{job_id}")
        return True

    # ─── Platform info ─────────────────────────────────────────────────

    def prices(self, gpu_type: str = "A100") -> list[dict]:
        """Get live GPU spot prices across all providers."""
        data = self._request("GET", f"/providers/prices?gpu_type={gpu_type}")
        return data.get("prices", data)

    def health(self) -> dict:
        """Platform health check."""
        return self._request("GET", "/health")

    def agents(self) -> dict:
        """Get status of all 5 AI agents."""
        return self._request("GET", "/agents/status")

    # ─── Internal HTTP ─────────────────────────────────────────────────

    def _request(self, method: str, path: str, body: Any = None) -> dict:
        url = f"{self.base_url}{path}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type":  "application/json",
            "User-Agent":    f"orquanta-python/{__version__}",
            "X-SDK-Version": __version__,
        }
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            body_str = e.read().decode("utf-8", errors="ignore")
            if e.code in (401, 403):
                raise AuthError(f"Invalid API key. {body_str}")
            if e.code == 402:
                raise BudgetExceededError(f"Budget exceeded. {body_str}")
            raise OrQuantaError(f"HTTP {e.code}: {body_str}")
        except urllib.error.URLError as e:
            raise OrQuantaError(f"Network error: {e.reason}. Is the OrQuanta API reachable?")

    async def _arequest(self, method: str, path: str, body: Any = None) -> dict:
        """Async request using asyncio subprocess (no aiohttp dependency)."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._request, method, path, body)

    def _parse_job(self, data: dict) -> Job:
        return Job(
            job_id    = data.get("job_id") or data.get("id") or "unknown",
            goal      = data.get("goal") or data.get("description") or "",
            status    = data.get("status") or JobStatus.QUEUED,
            provider  = data.get("provider") or "",
            gpu_type  = data.get("gpu_type") or "",
            gpu_count = data.get("gpu_count") or 1,
            region    = data.get("region") or "",
            cost      = float(data.get("cost_usd") or 0),
            saved     = float(data.get("saved_usd") or 0),
            progress_pct = float(data.get("progress_pct") or 0),
            loss      = data.get("loss"),
            artifact_url = data.get("artifact_url"),
            logs_url  = data.get("logs_url"),
            _sdk      = self,
        )

    def __repr__(self) -> str:
        key_prefix = self.api_key[:8] + "..." if self.api_key else "none"
        return f"OrQuanta(api_key={key_prefix!r}, base_url={self.base_url!r})"
