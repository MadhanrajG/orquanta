"""
OrQuanta Agentic v1.0 — Docker Container Job Runner

Submits ML jobs as Docker containers on GPU instances:
- Pulls images from DockerHub / ECR / GCR
- GPU passthrough via --gpus all (NVIDIA container runtime)
- Container health monitoring with restart policies
- Volume mounts for dataset / model storage
- Port forwarding for TensorBoard / Jupyter
- Auto cleanup on completion
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("orquanta.execution.docker_runner")


@dataclass
class DockerJobSpec:
    """Specification for a containerized ML job."""
    job_id: str
    image: str                          # e.g. "nvcr.io/nvidia/pytorch:24.01-py3"
    command: list[str]                  # Entrypoint override
    gpu_count: int = 1
    gpu_device_ids: str = "all"         # "all" or "0,1,2,3"
    env: dict[str, str] = field(default_factory=dict)
    volumes: dict[str, str] = field(default_factory=dict)   # host_path → container_path
    ports: dict[int, int] = field(default_factory=dict)     # host_port → container_port
    shm_size: str = "16g"               # /dev/shm for multi-GPU comm
    restart_policy: str = "no"          # no / on-failure / always
    memory_limit: str | None = None     # e.g. "64g"
    labels: dict[str, str] = field(default_factory=dict)
    extra_docker_args: list[str] = field(default_factory=list)


@dataclass
class DockerJobResult:
    """Result of a containerized job."""
    job_id: str
    container_id: str
    exit_code: int
    logs: str
    duration_seconds: float
    total_cost_usd: float
    completed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def success(self) -> bool:
        return self.exit_code == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "container_id": self.container_id[:12],
            "exit_code": self.exit_code,
            "success": self.success,
            "duration_seconds": round(self.duration_seconds, 2),
            "total_cost_usd": round(self.total_cost_usd, 4),
            "completed_at": self.completed_at,
        }


class DockerRunner:
    """Runs GPU jobs as Docker containers.

    Can target:
    1. Local Docker daemon (docker.sock)
    2. Remote Docker daemon over TCP (host:2376) — for cloud instances
    3. Docker-in-Kubernetes (DinD) sidecar

    Requires: pip install docker
    """

    def __init__(self, docker_host: str | None = None) -> None:
        """
        Args:
            docker_host: Docker host URL. None = local daemon.
                         e.g. "tcp://1.2.3.4:2376"   (remote)
                              "unix:///var/run/docker.sock"  (local)
        """
        self._docker_host = docker_host
        self._client = None
        self._active: dict[str, str] = {}  # job_id → container_id

    def _get_client(self):
        if self._client is None:
            try:
                import docker
                if self._docker_host:
                    # TLS for remote daemons — expects SSL certs in ~/.docker/
                    self._client = docker.DockerClient(
                        base_url=self._docker_host,
                        tls=self._docker_host.startswith("tcp://"),
                    )
                else:
                    self._client = docker.from_env()
            except ImportError:
                raise RuntimeError("docker SDK not installed. Run: pip install docker")
        return self._client

    async def run_job(
        self,
        spec: DockerJobSpec,
        hourly_rate_usd: float = 1.0,
        log_callback=None,
        auto_remove: bool = True,
    ) -> DockerJobResult:
        """Pull image and run a GPU container to completion.

        Args:
            spec: Job specification.
            hourly_rate_usd: GPU instance cost/hr for billing.
            log_callback: Callable(job_id, stream, line) for log streaming.
            auto_remove: Delete container after completion.
        """
        loop = asyncio.get_event_loop()
        client = self._get_client()
        t0 = time.time()

        logger.info(f"[Docker] Pulling image {spec.image} for job {spec.job_id}…")
        try:
            await loop.run_in_executor(None, lambda: client.images.pull(spec.image))
        except Exception as exc:
            logger.warning(f"[Docker] Image pull failed (may already exist): {exc}")

        # Build docker run arguments
        device_requests = [{
            "Driver": "nvidia",
            "Count": spec.gpu_count if spec.gpu_device_ids == "all" else -1,
            "DeviceIDs": None if spec.gpu_device_ids == "all" else spec.gpu_device_ids.split(","),
            "Capabilities": [["gpu"]],
        }]

        volumes_list = [
            f"{host_path}:{container_path}"
            for host_path, container_path in spec.volumes.items()
        ]
        ports_dict = {
            f"{cont_port}/tcp": host_port
            for host_port, cont_port in spec.ports.items()
        }
        env_list = [f"{k}={v}" for k, v in spec.env.items()]
        all_labels = {"orquanta.job_id": spec.job_id, "orquanta.managed": "true", **spec.labels}

        logger.info(f"[Docker] Starting container for job {spec.job_id} ({spec.image})")
        container = await loop.run_in_executor(None, lambda: client.containers.run(
            image=spec.image,
            command=spec.command,
            environment=env_list,
            volumes=volumes_list,
            ports=ports_dict,
            device_requests=device_requests,
            shm_size=spec.shm_size,
            labels=all_labels,
            detach=True,
            remove=False,  # Remove manually after log collection
            **({"mem_limit": spec.memory_limit} if spec.memory_limit else {}),
        ))

        container_id = container.id
        self._active[spec.job_id] = container_id
        logger.info(f"[Docker] Container {container_id[:12]} started for job {spec.job_id}")

        # Stream logs
        all_logs: list[str] = []
        try:
            log_gen = await loop.run_in_executor(
                None, lambda: container.logs(stream=True, follow=True)
            )
            async def _drain_logs():
                for chunk in log_gen:
                    line = chunk.decode("utf-8", errors="replace").rstrip()
                    all_logs.append(line)
                    if log_callback:
                        log_callback(spec.job_id, "stdout", line)

            await asyncio.wait_for(
                loop.run_in_executor(None, lambda: [
                    all_logs.append(chunk.decode("utf-8", errors="replace").rstrip())
                    for chunk in log_gen
                ]),
                timeout=86400,
            )
        except Exception as exc:
            logger.warning(f"[Docker] Log streaming error: {exc}")

        # Wait for container to finish and get exit code
        result = await loop.run_in_executor(None, container.wait)
        exit_code = result.get("StatusCode", 1)

        # Cleanup
        if auto_remove:
            try:
                await loop.run_in_executor(None, container.remove)
            except Exception:
                pass

        duration = time.time() - t0
        total_cost = (duration / 3600) * hourly_rate_usd
        self._active.pop(spec.job_id, None)

        status = "completed" if exit_code == 0 else "failed"
        logger.info(f"[Docker] Job {spec.job_id} {status} — exit={exit_code}, cost=${total_cost:.4f}")

        return DockerJobResult(
            job_id=spec.job_id,
            container_id=container_id,
            exit_code=exit_code,
            logs="\n".join(all_logs[-5000:]),  # Last 5000 lines
            duration_seconds=duration,
            total_cost_usd=total_cost,
        )

    async def stop_job(self, job_id: str, timeout: int = 30) -> bool:
        """Stop a running container."""
        container_id = self._active.get(job_id)
        if not container_id:
            return False
        loop = asyncio.get_event_loop()
        client = self._get_client()
        try:
            container = await loop.run_in_executor(None, lambda: client.containers.get(container_id))
            await loop.run_in_executor(None, lambda: container.stop(timeout=timeout))
            logger.info(f"[Docker] Stopped container {container_id[:12]} for job {job_id}")
            return True
        except Exception as exc:
            logger.error(f"[Docker] Stop failed for {container_id[:12]}: {exc}")
            return False

    async def get_container_stats(self, job_id: str) -> dict[str, Any] | None:
        """Get live resource stats for a running container."""
        container_id = self._active.get(job_id)
        if not container_id:
            return None
        loop = asyncio.get_event_loop()
        client = self._get_client()
        try:
            container = await loop.run_in_executor(None, lambda: client.containers.get(container_id))
            stats = await loop.run_in_executor(None, lambda: container.stats(stream=False))
            cpu_delta = stats["cpu_stats"]["cpu_usage"]["total_usage"] - stats["precpu_stats"]["cpu_usage"]["total_usage"]
            system_delta = stats["cpu_stats"]["system_cpu_usage"] - stats["precpu_stats"]["system_cpu_usage"]
            cpu_pct = (cpu_delta / system_delta) * 100 if system_delta else 0.0
            mem_used = stats["memory_stats"].get("usage", 0) / (1024**3)
            mem_limit = stats["memory_stats"].get("limit", 1) / (1024**3)
            return {
                "container_id": container_id[:12],
                "cpu_utilization_pct": round(cpu_pct, 1),
                "memory_used_gb": round(mem_used, 2),
                "memory_limit_gb": round(mem_limit, 2),
                "memory_utilization_pct": round(mem_used / mem_limit * 100, 1) if mem_limit else 0.0,
                "network_rx_mb": stats.get("networks", {}).get("eth0", {}).get("rx_bytes", 0) / 1024**2,
                "network_tx_mb": stats.get("networks", {}).get("eth0", {}).get("tx_bytes", 0) / 1024**2,
            }
        except Exception as exc:
            logger.warning(f"[Docker] Stats error for {container_id[:12]}: {exc}")
            return None

    def list_active(self) -> dict[str, str]:
        return dict(self._active)
