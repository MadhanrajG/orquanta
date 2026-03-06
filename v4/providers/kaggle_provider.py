"""
OrQuanta — Kaggle Kernels Provider
====================================
Gives OrQuanta users FREE GPU compute via Kaggle (30 hrs/week T4/P100).

Setup (per user):
  1. User signs up at kaggle.com
  2. Account → API → Create New API Token → downloads kaggle.json
  3. User pastes username + key into OrQuanta profile settings
  4. OrQuanta submits, monitors, and retrieves outputs automatically

Kaggle free tier:
  - GPU: NVIDIA T4 (16GB VRAM) or P100 (16GB)
  - RAM: 30GB
  - Storage: 20GB
  - Session: up to 9 hours
  - Weekly limit: ~30 GPU hours per account
  - Internet: On (can pip install anything)

This module handles:
  - Kernel creation / update via Kaggle REST API
  - Job status polling (queued → running → complete)
  - Output download (generated files, logs)
  - Cost tracking ($0.00 always)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger("orquanta.providers.kaggle")

KAGGLE_API_BASE = "https://www.kaggle.com/api/v1"
DEFAULT_POLL_INTERVAL = 30   # seconds between status checks
MAX_POLL_ATTEMPTS = 108      # ~54 minutes total (9h / 30s)


class KaggleJobStatus:
    QUEUED    = "queued"
    RUNNING   = "running"
    COMPLETE  = "complete"
    ERROR     = "error"
    CANCELLED = "cancelled"


class KaggleProvider:
    """
    Submits OrQuanta goals to Kaggle Kernels as free GPU jobs.
    Each job becomes a Kaggle notebook kernel that runs on T4/P100.
    """

    def __init__(self, username: str, api_key: str) -> None:
        self.username = username
        self.api_key  = api_key
        self._auth    = (username, api_key)

    # ─── Public interface ──────────────────────────────────────────────────────

    async def submit_job(
        self,
        goal: str,
        notebook_ipynb: dict,
        kernel_slug: str | None = None,
        dataset_sources: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Push a notebook to Kaggle and start it on a free GPU.
        Returns: { kernel_ref, status, dashboard_url, submitted_at }
        """
        slug = kernel_slug or f"orquanta-{secrets.token_hex(4)}"
        kernel_ref = f"{self.username}/{slug}"

        # Build Kaggle kernel metadata
        metadata = {
            "id": kernel_ref,
            "title": f"OrQuanta: {goal[:60]}",
            "code_file": "notebook.ipynb",
            "language": "python",
            "kernel_type": "notebook",
            "is_private": True,
            "enable_gpu": True,
            "enable_internet": True,
            "dataset_sources": dataset_sources or [],
            "kernel_sources": [],
            "competition_sources": [],
        }

        # Write temp files and push
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            nb_path   = Path(tmp) / "notebook.ipynb"
            meta_path = Path(tmp) / "kernel-metadata.json"
            nb_path.write_text(json.dumps(notebook_ipynb))
            meta_path.write_text(json.dumps(metadata))

            result = await self._push_kernel(tmp, slug)

        dashboard_url = f"https://www.kaggle.com/code/{self.username}/{slug}"
        logger.info(f"[Kaggle] Submitted kernel {kernel_ref} → {dashboard_url}")

        return {
            "kernel_ref":    kernel_ref,
            "kernel_slug":   slug,
            "status":        KaggleJobStatus.QUEUED,
            "dashboard_url": dashboard_url,
            "submitted_at":  datetime.now(timezone.utc).isoformat(),
            "gpu_type":      "T4 16GB (Kaggle free)",
            "cost_usd":      0.0,
            "provider":      "Kaggle",
        }

    async def get_status(self, kernel_ref: str) -> dict[str, Any]:
        """Poll a kernel's current run status."""
        username, slug = kernel_ref.split("/", 1)
        url = f"{KAGGLE_API_BASE}/kernels/{username}/{slug}"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.get(url, auth=self._auth)
                if r.status_code == 200:
                    data = r.json()
                    run_info = data.get("currentRunningVersion", {})
                    status_str = run_info.get("status", "unknown").lower()
                    kaggle_to_orquanta = {
                        "queued":    KaggleJobStatus.QUEUED,
                        "running":   KaggleJobStatus.RUNNING,
                        "complete":  KaggleJobStatus.COMPLETE,
                        "error":     KaggleJobStatus.ERROR,
                        "cancelled": KaggleJobStatus.CANCELLED,
                    }
                    return {
                        "status":        kaggle_to_orquanta.get(status_str, status_str),
                        "kernel_ref":    kernel_ref,
                        "total_votes":   data.get("totalVotes", 0),
                        "run_info":      run_info,
                        "dashboard_url": f"https://www.kaggle.com/code/{kernel_ref}",
                    }
        except Exception as exc:
            logger.error(f"[Kaggle] Status check failed for {kernel_ref}: {exc}")
        return {"status": "unknown", "kernel_ref": kernel_ref}

    async def wait_for_completion(
        self,
        kernel_ref: str,
        on_status_change: Any = None,
        poll_interval: int = DEFAULT_POLL_INTERVAL,
    ) -> dict[str, Any]:
        """
        Poll until the kernel finishes (complete/error/cancelled).
        Calls on_status_change(status_dict) on each poll if provided.
        """
        for attempt in range(MAX_POLL_ATTEMPTS):
            status = await self.get_status(kernel_ref)
            s = status.get("status")
            logger.info(f"[Kaggle] {kernel_ref} → {s} (poll {attempt+1})")

            if on_status_change:
                try:
                    await on_status_change(status)
                except Exception:
                    pass

            if s in (KaggleJobStatus.COMPLETE, KaggleJobStatus.ERROR, KaggleJobStatus.CANCELLED):
                if s == KaggleJobStatus.COMPLETE:
                    # Try to get output
                    outputs = await self.download_outputs(kernel_ref)
                    status["outputs"] = outputs
                return status

            await asyncio.sleep(poll_interval)

        return {"status": "timeout", "kernel_ref": kernel_ref, "message": "Polling timeout after 54 minutes"}

    async def download_outputs(self, kernel_ref: str) -> list[str]:
        """Download the kernel output files."""
        username, slug = kernel_ref.split("/", 1)
        url = f"{KAGGLE_API_BASE}/kernels/{username}/{slug}/output"
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                r = await client.get(url, auth=self._auth)
                if r.status_code == 200:
                    data = r.json()
                    files = data.get("files", [])
                    return [f.get("name", "") for f in files]
        except Exception as exc:
            logger.warning(f"[Kaggle] Output download failed: {exc}")
        return []

    async def list_kernels(self) -> list[dict]:
        """List all OrQuanta-created kernels for this user."""
        url = f"{KAGGLE_API_BASE}/kernels/list?user={self.username}&search=orquanta"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(url, auth=self._auth)
                if r.status_code == 200:
                    return r.json()
        except Exception as exc:
            logger.warning(f"[Kaggle] List kernels failed: {exc}")
        return []

    # ─── Internal ──────────────────────────────────────────────────────────────

    async def _push_kernel(self, kernel_dir: str, slug: str) -> dict:
        """Push kernel files via Kaggle API v1 (multipart or CLI equivalent)."""
        # Kaggle API: POST /kernels/push with JSON body containing base64 blob
        import base64

        nb_path = Path(kernel_dir) / "notebook.ipynb"
        nb_b64  = base64.b64encode(nb_path.read_bytes()).decode()

        payload = {
            "source":             nb_b64,
            "language":           "python",
            "kernel_type":        "notebook",
            "is_private":         True,
            "enable_gpu":         True,
            "enable_internet":    True,
            "dataset_data_sources": [],
            "kernel_data_sources":  [],
        }

        url = f"{KAGGLE_API_BASE}/kernels/push"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(url, auth=self._auth, json=payload)
                logger.info(f"[Kaggle] Push response: {r.status_code}")
                return r.json() if r.status_code in (200, 201) else {}
        except Exception as exc:
            logger.error(f"[Kaggle] Push failed: {exc}")
            return {}

    # ─── Capability check ──────────────────────────────────────────────────────

    async def check_credentials(self) -> bool:
        """Verify the Kaggle credentials are valid."""
        url = f"{KAGGLE_API_BASE}/kernels/list?user={self.username}&pageSize=1"
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                r = await client.get(url, auth=self._auth)
                return r.status_code == 200
        except Exception:
            return False

    @staticmethod
    def get_free_tier_info() -> dict:
        return {
            "provider":       "Kaggle",
            "gpu":            "NVIDIA T4 16GB or P100 16GB",
            "weekly_hours":   30,
            "session_max_h":  9,
            "ram_gb":         30,
            "storage_gb":     20,
            "cost":           "$0.00",
            "internet":       True,
            "signup_url":     "https://www.kaggle.com/account/login",
            "api_token_url":  "https://www.kaggle.com/settings/account",
            "setup_minutes":  5,
        }


# ─── Singleton factory ────────────────────────────────────────────────────────

def get_kaggle_provider(username: str, api_key: str) -> KaggleProvider:
    return KaggleProvider(username, api_key)
