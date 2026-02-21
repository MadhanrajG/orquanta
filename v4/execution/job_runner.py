"""
OrQuanta Agentic v1.0 — SSH Job Runner

Submits ML jobs to GPU instances via SSH:
- Executes arbitrary shell commands over Paramiko
- Streams stdout/stderr in real-time via WebSocket
- Monitors GPU metrics during execution
- Supports SCP artifact upload/download
- Handles connection failures with retry

Requires: pip install paramiko
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import stat
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Callable

logger = logging.getLogger("orquanta.execution.job_runner")

SSH_KEY_PATH = os.getenv("SSH_PRIVATE_KEY_PATH", os.path.expanduser("~/.ssh/orquanta_key"))
SSH_USER = os.getenv("SSH_DEFAULT_USER", "ubuntu")
SSH_CONNECT_TIMEOUT = int(os.getenv("SSH_CONNECT_TIMEOUT", "120"))  # seconds
SSH_PORT = int(os.getenv("SSH_PORT", "22"))


@dataclass
class JobResult:
    """Final result of a job execution."""
    job_id: str
    instance_id: str
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    artifacts: list[str] = field(default_factory=list)
    gpu_peak_utilization_pct: float = 0.0
    gpu_peak_memory_gb: float = 0.0
    total_cost_usd: float = 0.0
    completed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def success(self) -> bool:
        return self.exit_code == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "instance_id": self.instance_id,
            "exit_code": self.exit_code,
            "success": self.success,
            "duration_seconds": round(self.duration_seconds, 2),
            "gpu_peak_utilization_pct": self.gpu_peak_utilization_pct,
            "gpu_peak_memory_gb": self.gpu_peak_memory_gb,
            "total_cost_usd": round(self.total_cost_usd, 4),
            "artifacts": self.artifacts,
            "completed_at": self.completed_at,
        }


class SSHClient:
    """Async SSH client wrapping Paramiko for GPU instance interactions."""

    def __init__(self, host: str, user: str = SSH_USER, key_path: str = SSH_KEY_PATH, port: int = SSH_PORT):
        self.host = host
        self.user = user
        self.key_path = key_path
        self.port = port
        self._client = None

    async def connect(self, timeout: int = SSH_CONNECT_TIMEOUT) -> None:
        """Establish SSH connection with retry logic."""
        import paramiko
        deadline = time.time() + timeout
        last_exc = None

        while time.time() < deadline:
            try:
                loop = asyncio.get_event_loop()
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

                private_key = paramiko.RSAKey.from_private_key_file(self.key_path)

                await loop.run_in_executor(None, lambda: client.connect(
                    hostname=self.host,
                    username=self.user,
                    pkey=private_key,
                    port=self.port,
                    timeout=10,
                    banner_timeout=60,
                ))
                self._client = client
                logger.info(f"[SSH] Connected to {self.user}@{self.host}")
                return
            except Exception as exc:
                last_exc = exc
                logger.debug(f"[SSH] Connect attempt failed: {exc}. Retrying…")
                await asyncio.sleep(10)

        raise ConnectionError(f"Could not SSH to {self.host} within {timeout}s: {last_exc}")

    async def run(
        self,
        command: str,
        log_callback: Callable[[str, str], None] | None = None,
        timeout: int = 86400,  # 24 hours
    ) -> tuple[int, str, str]:
        """Execute a shell command and stream stdout/stderr.
        
        log_callback(stream, line) is called for each line of output.
        Returns (exit_code, full_stdout, full_stderr).
        """
        if not self._client:
            raise RuntimeError("Not connected. Call connect() first.")

        import paramiko
        loop = asyncio.get_event_loop()

        stdin, stdout, stderr = await loop.run_in_executor(
            None, lambda: self._client.exec_command(command, timeout=timeout)
        )
        stdout_lines: list[str] = []
        stderr_lines: list[str] = []

        # Stream output
        async def _read_stream(channel_stream, lines_list: list, stream_name: str):
            while True:
                line = await loop.run_in_executor(None, channel_stream.readline)
                if not line:
                    break
                decoded = line.decode("utf-8", errors="replace").rstrip()
                lines_list.append(decoded)
                if log_callback:
                    log_callback(stream_name, decoded)

        await asyncio.gather(
            _read_stream(stdout, stdout_lines, "stdout"),
            _read_stream(stderr, stderr_lines, "stderr"),
        )

        exit_code = await loop.run_in_executor(None, lambda: stdout.channel.recv_exit_status())
        return exit_code, "\n".join(stdout_lines), "\n".join(stderr_lines)

    async def upload_file(self, local_path: str, remote_path: str) -> None:
        """Upload a file via SFTP."""
        loop = asyncio.get_event_loop()
        sftp = await loop.run_in_executor(None, self._client.open_sftp)
        try:
            await loop.run_in_executor(None, lambda: sftp.put(local_path, remote_path))
            logger.info(f"[SSH] Uploaded {local_path} → {self.host}:{remote_path}")
        finally:
            sftp.close()

    async def download_file(self, remote_path: str, local_path: str) -> None:
        """Download a file via SFTP."""
        loop = asyncio.get_event_loop()
        sftp = await loop.run_in_executor(None, self._client.open_sftp)
        try:
            await loop.run_in_executor(None, lambda: sftp.get(remote_path, local_path))
            logger.info(f"[SSH] Downloaded {self.host}:{remote_path} → {local_path}")
        finally:
            sftp.close()

    async def upload_script(self, content: str, remote_path: str = "/tmp/orquanta_job.sh") -> str:
        """Upload an inline script string to the instance."""
        script_bytes = content.encode("utf-8")
        loop = asyncio.get_event_loop()
        sftp = await loop.run_in_executor(None, self._client.open_sftp)
        try:
            with sftp.open(remote_path, "wb") as f:
                await loop.run_in_executor(None, lambda: f.write(script_bytes))
            await loop.run_in_executor(None, lambda: sftp.chmod(remote_path, stat.S_IRWXU))
        finally:
            sftp.close()
        return remote_path

    def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None


class JobRunner:
    """High-level job runner that submits ML jobs to GPU instances via SSH.

    Features:
    - Waits for instance SSH readiness
    - Uploads job script
    - Streams logs back via callback (→ WebSocket)  
    - Polls GPU metrics during execution
    - downloads artifacts on completion
    - Calculates total cost
    """

    def __init__(self) -> None:
        self._active_jobs: dict[str, dict[str, Any]] = {}

    async def run_job(
        self,
        job_id: str,
        instance_id: str,
        host_ip: str,
        gpu_count: int,
        job_script: str,
        hours_billed_rate: float = 1.0,
        artifact_paths: list[str] | None = None,
        local_artifact_dir: str = "/tmp/orquanta-artifacts",
        log_callback: Callable[[str, str, str], None] | None = None,  # (job_id, stream, line)
        key_path: str = SSH_KEY_PATH,
    ) -> JobResult:
        """Execute a job on a GPU instance.

        Args:
            job_id: Unique job identifier.
            instance_id: Cloud instance/pod identifier.
            host_ip: Public IP of the instance.
            gpu_count: Number of GPUs (used for script environment).
            job_script: Shell script content to execute.
            hours_billed_rate: $/hr for cost estimation.
            artifact_paths: Remote paths to download after completion.
            local_artifact_dir: Local dir to save downloaded artifacts.
            log_callback: Called with (job_id, stream, line) for each output line.
            key_path: Path to SSH private key.
        """
        t0 = time.time()
        self._active_jobs[job_id] = {
            "instance_id": instance_id, "host": host_ip,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "status": "connecting",
        }

        ssh = SSHClient(host=host_ip, key_path=key_path)

        try:
            # --- 1. Connect (wait for instance to boot) ---
            logger.info(f"[JobRunner] Connecting to {host_ip} for job {job_id}…")
            await ssh.connect(timeout=SSH_CONNECT_TIMEOUT)
            self._active_jobs[job_id]["status"] = "uploading"

            # --- 2. Upload job script ---
            remote_script = await ssh.upload_script(job_script, "/tmp/orquanta_job.sh")
            logger.info(f"[JobRunner] Script uploaded for job {job_id}")

            # --- 3. Set up environment & run ---
            self._active_jobs[job_id]["status"] = "running"
            env_prefix = f"ORQUANTA_JOB_ID={job_id} ORQUANTA_GPU_COUNT={gpu_count} CUDA_VISIBLE_DEVICES=all"
            full_command = f"{env_prefix} bash {remote_script} 2>&1"

            peak_util = 0.0
            peak_mem = 0.0
            gpu_samples: list[tuple[float, float]] = []

            # GPU monitoring task (parallel to job execution)
            async def monitor_gpu():
                while job_id in self._active_jobs and self._active_jobs[job_id].get("status") == "running":
                    try:
                        exit_code, out, _ = await ssh.run("nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader,nounits")
                        for line in out.strip().split("\n"):
                            parts = line.split(",")
                            if len(parts) == 2:
                                util = float(parts[0].strip())
                                mem_mib = float(parts[1].strip())
                                gpu_samples.append((util, mem_mib / 1024))
                    except Exception:
                        pass
                    await asyncio.sleep(15)

            gpu_task = asyncio.create_task(monitor_gpu())

            def _cb(stream: str, line: str):
                if log_callback:
                    log_callback(job_id, stream, line)
                logger.debug(f"[{job_id}][{stream}] {line}")

            exit_code, stdout, stderr = await ssh.run(full_command, log_callback=_cb)

            gpu_task.cancel()
            if gpu_samples:
                peak_util = max(s[0] for s in gpu_samples)
                peak_mem = max(s[1] for s in gpu_samples)

            # --- 4. Download artifacts ---
            local_artifacts: list[str] = []
            os.makedirs(local_artifact_dir, exist_ok=True)
            for remote_path in (artifact_paths or []):
                local_name = os.path.basename(remote_path)
                local_path = os.path.join(local_artifact_dir, job_id, local_name)
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                try:
                    await ssh.download_file(remote_path, local_path)
                    local_artifacts.append(local_path)
                except Exception as exc:
                    logger.warning(f"[JobRunner] Artifact download failed: {remote_path}: {exc}")

            duration = time.time() - t0
            total_cost = (duration / 3600) * hours_billed_rate

            result = JobResult(
                job_id=job_id,
                instance_id=instance_id,
                exit_code=exit_code,
                stdout=stdout[-50000:],  # Truncate to 50K chars
                stderr=stderr[-10000:],
                duration_seconds=duration,
                artifacts=local_artifacts,
                gpu_peak_utilization_pct=peak_util,
                gpu_peak_memory_gb=peak_mem,
                total_cost_usd=total_cost,
            )

            status = "completed" if exit_code == 0 else "failed"
            self._active_jobs[job_id]["status"] = status
            logger.info(f"[JobRunner] Job {job_id} {status} — exit={exit_code}, cost=${total_cost:.4f}")
            return result

        except Exception as exc:
            duration = time.time() - t0
            logger.error(f"[JobRunner] Job {job_id} crashed: {exc}")
            self._active_jobs.pop(job_id, None)
            return JobResult(
                job_id=job_id, instance_id=instance_id,
                exit_code=1, stdout="", stderr=str(exc),
                duration_seconds=duration,
                total_cost_usd=(duration / 3600) * hours_billed_rate,
            )
        finally:
            ssh.close()
            self._active_jobs.pop(job_id, None)

    def get_active_jobs(self) -> dict[str, dict]:
        return dict(self._active_jobs)

    async def stream_logs(
        self,
        host_ip: str,
        log_file: str,
        key_path: str = SSH_KEY_PATH,
    ) -> AsyncIterator[str]:
        """Tail a remote log file and yield lines (for WebSocket streaming)."""
        ssh = SSHClient(host=host_ip, key_path=key_path)
        await ssh.connect(timeout=30)
        try:
            loop = asyncio.get_event_loop()
            _, stdout, _ = await loop.run_in_executor(
                None, lambda: ssh._client.exec_command(f"tail -f {log_file}")
            )
            while True:
                line = await loop.run_in_executor(None, stdout.readline)
                if not line:
                    break
                yield line.decode("utf-8", errors="replace").rstrip()
        finally:
            ssh.close()
