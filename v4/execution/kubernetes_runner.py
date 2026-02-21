"""
OrQuanta Agentic v1.0 — Kubernetes Job Runner

Submits GPU workloads as Kubernetes Jobs with:
- nvidia.com/gpu resource requests
- ConfigMap for job scripts
- Log streaming via pod log API
- Auto cleanup of completed Jobs
- Support for multi-node distributed training (MPI Jobs)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger("orquanta.execution.kubernetes_runner")

KUBE_API = os.getenv("KUBE_API_SERVER", "https://kubernetes.default.svc")
KUBE_TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"
KUBE_CA_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
KUBE_NAMESPACE = os.getenv("KUBE_NAMESPACE", "orquanta-jobs")
KUBE_TOKEN = os.getenv("KUBE_TOKEN", "")  # External token if not running in-cluster


@dataclass
class KubernetesJobSpec:
    """Specification for a Kubernetes job."""
    job_id: str
    image: str
    command: list[str]
    gpu_count: int = 1
    cpu_request: str = "4"
    memory_request: str = "16Gi"
    gpu_type: str = "nvidia.com/gpu"  # or nvidia.com/H100_PCIE_80GB for CoreWeave
    env: dict[str, str] = field(default_factory=dict)
    volume_claims: list[dict[str, str]] = field(default_factory=list)  # PVC mounts
    node_selector: dict[str, str] = field(default_factory=dict)
    tolerations: list[dict[str, str]] = field(default_factory=list)
    backoff_limit: int = 0
    active_deadline_seconds: int = 86400  # 24h max


class KubernetesRunner:
    """Submits GPU jobs to Kubernetes via the API.
    
    Works with:
    - Standard Kubernetes + NVIDIA Device Plugin
    - CoreWeave (GPU-native Kubernetes)
    - GKE / EKS / AKS managed clusters
    """

    def __init__(self) -> None:
        self._token: str = self._load_token()
        self._api = KUBE_API
        self._active_jobs: dict[str, str] = {}  # job_id → k8s job name

    def _load_token(self) -> str:
        """Load service account token for in-cluster auth, or use env var."""
        if KUBE_TOKEN:
            return KUBE_TOKEN
        try:
            with open(KUBE_TOKEN_PATH) as f:
                return f.read().strip()
        except FileNotFoundError:
            return ""

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    def _client(self) -> httpx.AsyncClient:
        # Use CA cert if available (in-cluster), else skip TLS verify for dev
        verify = KUBE_CA_PATH if os.path.exists(KUBE_CA_PATH) else False
        return httpx.AsyncClient(base_url=self._api, verify=verify, timeout=30.0)

    # ------------------------------------------------------------------
    # Job management
    # ------------------------------------------------------------------

    async def submit_job(self, spec: KubernetesJobSpec) -> str:
        """Submit a Kubernetes Job and return the job name."""
        job_name = f"orquanta-{spec.job_id.replace('_', '-')[:40]}"
        env_list = [{"name": k, "value": v} for k, v in spec.env.items()]
        env_list.append({"name": "ORQUANTA_JOB_ID", "value": spec.job_id})

        volume_mounts = []
        volumes = []
        for pvc in spec.volume_claims:
            volumes.append({
                "name": pvc["name"],
                "persistentVolumeClaim": {"claimName": pvc["claim_name"]},
            })
            volume_mounts.append({
                "name": pvc["name"],
                "mountPath": pvc.get("mount_path", f"/data/{pvc['name']}"),
            })

        tolerations = spec.tolerations or [{
            "key": "nvidia.com/gpu",
            "operator": "Exists",
            "effect": "NoSchedule",
        }]

        job_manifest = {
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": {
                "name": job_name,
                "namespace": KUBE_NAMESPACE,
                "labels": {
                    "app": "orquanta", "job-id": spec.job_id,
                    "component": "gpu-job",
                },
            },
            "spec": {
                "backoffLimit": spec.backoff_limit,
                "activeDeadlineSeconds": spec.active_deadline_seconds,
                "template": {
                    "metadata": {"labels": {"app": "orquanta", "job-id": spec.job_id}},
                    "spec": {
                        "restartPolicy": "Never",
                        "nodeSelector": spec.node_selector or {},
                        "tolerations": tolerations,
                        "volumes": volumes,
                        "containers": [{
                            "name": "gpu-job",
                            "image": spec.image,
                            "command": spec.command,
                            "env": env_list,
                            "volumeMounts": volume_mounts,
                            "resources": {
                                "requests": {
                                    "cpu": spec.cpu_request,
                                    "memory": spec.memory_request,
                                    spec.gpu_type: str(spec.gpu_count),
                                },
                                "limits": {
                                    spec.gpu_type: str(spec.gpu_count),
                                },
                            },
                        }],
                    },
                },
            },
        }

        async with self._client() as client:
            resp = await client.post(
                f"/apis/batch/v1/namespaces/{KUBE_NAMESPACE}/jobs",
                headers=self._headers(),
                content=json.dumps(job_manifest),
            )
            if resp.status_code not in (200, 201):
                raise RuntimeError(f"Failed to create K8s Job: {resp.status_code} {resp.text}")

        self._active_jobs[spec.job_id] = job_name
        logger.info(f"[K8s] Job {job_name} submitted in namespace {KUBE_NAMESPACE}")
        return job_name

    async def wait_for_completion(
        self,
        job_id: str,
        timeout_seconds: int = 86400,
        poll_interval: int = 10,
    ) -> dict[str, Any]:
        """Poll job status until succeeded/failed or timeout."""
        job_name = self._active_jobs.get(job_id)
        if not job_name:
            raise ValueError(f"No K8s job found for job_id={job_id}")

        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            status = await self.get_job_status(job_name)
            if status.get("succeeded", 0) > 0:
                return {"status": "succeeded", "job_name": job_name}
            if status.get("failed", 0) > 0:
                return {"status": "failed", "job_name": job_name}
            await asyncio.sleep(poll_interval)

        return {"status": "timeout", "job_name": job_name}

    async def get_job_status(self, job_name: str) -> dict[str, Any]:
        """Get current Kubernetes Job status."""
        async with self._client() as client:
            resp = await client.get(
                f"/apis/batch/v1/namespaces/{KUBE_NAMESPACE}/jobs/{job_name}",
                headers=self._headers(),
            )
            if resp.status_code == 404:
                return {"error": "not_found"}
            resp.raise_for_status()
            data = resp.json()
            status = data.get("status", {})
            return {
                "active": status.get("active", 0),
                "succeeded": status.get("succeeded", 0),
                "failed": status.get("failed", 0),
                "start_time": status.get("startTime"),
                "completion_time": status.get("completionTime"),
                "conditions": status.get("conditions", []),
            }

    async def stream_pod_logs(self, job_id: str) -> list[str]:
        """Get logs from the pod(s) spawned by a job."""
        job_name = self._active_jobs.get(job_id)
        if not job_name:
            return []

        # Find pods for this job
        async with self._client() as client:
            pods_resp = await client.get(
                f"/api/v1/namespaces/{KUBE_NAMESPACE}/pods",
                headers=self._headers(),
                params={"labelSelector": f"job-name={job_name}"},
            )
            pods_resp.raise_for_status()
            pods = pods_resp.json().get("items", [])

        logs: list[str] = []
        for pod in pods:
            pod_name = pod["metadata"]["name"]
            async with self._client() as client:
                log_resp = await client.get(
                    f"/api/v1/namespaces/{KUBE_NAMESPACE}/pods/{pod_name}/log",
                    headers=self._headers(),
                    params={"tail": 1000},
                )
                if log_resp.status_code == 200:
                    logs.extend(log_resp.text.split("\n"))

        return logs

    async def delete_job(self, job_id: str, delete_pods: bool = True) -> bool:
        """Delete a K8s Job and optionally its pods."""
        job_name = self._active_jobs.get(job_id)
        if not job_name:
            return False

        async with self._client() as client:
            # Cascade deletion removes pods too
            params = {"propagationPolicy": "Foreground"} if delete_pods else {}
            resp = await client.delete(
                f"/apis/batch/v1/namespaces/{KUBE_NAMESPACE}/jobs/{job_name}",
                headers=self._headers(),
                params=params,
            )
            success = resp.status_code in (200, 202, 404)
            if success:
                self._active_jobs.pop(job_id, None)
                logger.info(f"[K8s] Deleted job {job_name}")
            return success

    async def list_gpu_nodes(self) -> list[dict[str, Any]]:
        """List all GPU nodes and their available capacity."""
        async with self._client() as client:
            resp = await client.get(
                "/api/v1/nodes",
                headers=self._headers(),
                params={"labelSelector": "nvidia.com/gpu.present=true"},
            )
            resp.raise_for_status()
            nodes = resp.json().get("items", [])

        result = []
        for node in nodes:
            meta = node.get("metadata", {})
            allocatable = node.get("status", {}).get("allocatable", {})
            labels = meta.get("labels", {})
            result.append({
                "name": meta.get("name"),
                "gpu_type": labels.get("gpu.nvidia.com/model", "unknown"),
                "region": labels.get("topology.kubernetes.io/region", "unknown"),
                "zone": labels.get("topology.kubernetes.io/zone", "unknown"),
                "allocatable_gpus": int(allocatable.get("nvidia.com/gpu", 0)),
                "allocatable_cpu": allocatable.get("cpu", "0"),
                "allocatable_memory": allocatable.get("memory", "0"),
            })
        return result

    def get_active_jobs(self) -> dict[str, str]:
        return dict(self._active_jobs)
