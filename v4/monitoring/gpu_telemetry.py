"""
OrQuanta Agentic v1.0 — GPU Telemetry Collector

Collects real NVIDIA GPU metrics from running instances:
- SSH → nvidia-smi for all GPU metrics
- Pushes to Prometheus Pushgateway every 30 seconds
- Fires alerts when: temp > 85°C, memory > 95%, util < 5% for 10min

Metrics collected:
  - GPU utilization %
  - Memory used / total / utilization %
  - Temperature (°C)
  - Power draw (W) / power limit
  - Fan speed %
  - PCIe throughput
  - ECC error counts
  - SM clock frequency
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

logger = logging.getLogger("orquanta.monitoring.gpu_telemetry")

# Alert thresholds
TEMP_CRITICAL_C = float(85)
MEM_CRITICAL_PCT = float(95)
UTIL_IDLE_PCT = float(5)
UTIL_IDLE_MIN = int(10)  # Minutes of low utilization before alerting

# nvidia-smi query format
NVIDIA_SMI_QUERY = ",".join([
    "index", "gpu_name", "utilization.gpu", "memory.used", "memory.free",
    "memory.total", "temperature.gpu", "power.draw", "power.limit",
    "fan.speed", "clocks.sm", "ecc.errors.uncorrected.volatile.total",
])
NVIDIA_SMI_CMD = (
    f"nvidia-smi --query-gpu={NVIDIA_SMI_QUERY} "
    f"--format=csv,noheader,nounits"
)


@dataclass
class GPUMetricPoint:
    """A single GPU metric snapshot."""
    instance_id: str
    provider: str
    gpu_index: int
    gpu_name: str
    utilization_pct: float
    memory_used_mb: float
    memory_free_mb: float
    memory_total_mb: float
    memory_utilization_pct: float
    temp_celsius: float
    power_draw_w: float
    power_limit_w: float
    fan_speed_pct: float
    sm_clock_mhz: float
    ecc_errors: int
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def memory_used_gb(self) -> float:
        return round(self.memory_used_mb / 1024, 2)

    def is_critical(self) -> list[str]:
        """Return list of active alerts for this metric snapshot."""
        alerts = []
        if self.temp_celsius >= TEMP_CRITICAL_C:
            alerts.append(f"THERMAL_CRITICAL: {self.temp_celsius:.0f}°C (≥{TEMP_CRITICAL_C}°C)")
        if self.memory_utilization_pct >= MEM_CRITICAL_PCT:
            alerts.append(f"OOM_RISK: {self.memory_utilization_pct:.1f}% memory (≥{MEM_CRITICAL_PCT}%)")
        if self.ecc_errors > 0:
            alerts.append(f"ECC_ERRORS: {self.ecc_errors} uncorrected errors")
        if self.power_draw_w > self.power_limit_w * 0.98:
            alerts.append(f"POWER_LIMIT: {self.power_draw_w:.0f}W near limit {self.power_limit_w:.0f}W")
        return alerts

    def to_dict(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "gpu_index": self.gpu_index,
            "gpu_name": self.gpu_name,
            "utilization_pct": self.utilization_pct,
            "memory_used_gb": self.memory_used_gb(),
            "memory_total_gb": round(self.memory_total_mb / 1024, 2),
            "memory_utilization_pct": self.memory_utilization_pct,
            "temp_celsius": self.temp_celsius,
            "power_draw_w": self.power_draw_w,
            "fan_speed_pct": self.fan_speed_pct,
            "sm_clock_mhz": self.sm_clock_mhz,
            "ecc_errors": self.ecc_errors,
            "alerts": self.is_critical(),
            "timestamp": self.timestamp,
        }


class GPUTelemetryCollector:
    """Continuously collects GPU metrics from running instances via SSH.
    
    Usage:
        collector = GPUTelemetryCollector(ssh_runner)
        await collector.start_monitoring("instance-001", "1.2.3.4")
        await asyncio.sleep(60)
        metrics = collector.get_latest("instance-001")
    """

    def __init__(
        self,
        alert_callback: Callable[[str, str, GPUMetricPoint], None] | None = None,
        push_gateway_url: str | None = None,
        poll_interval_s: float = 30.0,
    ) -> None:
        """
        Args:
            alert_callback: Called (instance_id, alert_message, metric_point) when threshold crossed.
            push_gateway_url: Prometheus Pushgateway URL for metric export.
            poll_interval_s: How often to poll each instance (default 30s).
        """
        self._alert_callback = alert_callback
        self._push_gateway_url = push_gateway_url
        self._poll_interval = poll_interval_s
        self._monitored: dict[str, dict[str, Any]] = {}   # instance_id → {host, task, metrics}
        self._latest: dict[str, list[GPUMetricPoint]] = {}
        self._idle_tracker: dict[str, list[float]] = {}   # instance_id → [utilization readings]
        self._alert_history: list[dict[str, Any]] = []

    async def start_monitoring(
        self,
        instance_id: str,
        host_ip: str,
        provider: str = "aws",
        key_path: str | None = None,
    ) -> None:
        """Begin polling an instance for GPU metrics."""
        if instance_id in self._monitored:
            return

        logger.info(f"[Telemetry] Starting GPU monitoring for {instance_id} ({host_ip})")
        task = asyncio.create_task(
            self._poll_loop(instance_id, host_ip, provider, key_path),
            name=f"telemetry-{instance_id}",
        )
        self._monitored[instance_id] = {
            "host": host_ip, "provider": provider, "task": task,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }

    def stop_monitoring(self, instance_id: str) -> None:
        """Stop monitoring an instance."""
        info = self._monitored.pop(instance_id, None)
        if info:
            info["task"].cancel()
            logger.info(f"[Telemetry] Stopped monitoring {instance_id}")

    def get_latest(self, instance_id: str) -> list[GPUMetricPoint]:
        """Get the most recent metric snapshot for all GPUs on an instance."""
        return self._latest.get(instance_id, [])

    def get_all_latest(self) -> dict[str, list[dict[str, Any]]]:
        """Get latest metrics for all monitored instances."""
        return {
            iid: [m.to_dict() for m in metrics]
            for iid, metrics in self._latest.items()
        }

    def get_alert_history(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._alert_history[-limit:]

    async def _poll_loop(
        self, instance_id: str, host_ip: str, provider: str, key_path: str | None
    ) -> None:
        """Background loop that polls nvidia-smi on the instance."""
        from ..execution.job_runner import SSHClient
        ssh = SSHClient(host=host_ip, key_path=key_path or "~/.ssh/orquanta_key")

        # Wait for SSH to be ready
        try:
            await ssh.connect(timeout=120)
        except Exception as exc:
            logger.error(f"[Telemetry] SSH connect failed for {instance_id}: {exc}")
            return

        logger.info(f"[Telemetry] Connected for monitoring {instance_id}")
        consecutive_failures = 0

        try:
            while instance_id in self._monitored:
                try:
                    exit_code, stdout, _ = await ssh.run(NVIDIA_SMI_CMD)
                    if exit_code == 0 and stdout.strip():
                        metrics = self._parse_nvidia_smi(stdout, instance_id, provider)
                        self._latest[instance_id] = metrics
                        self._check_alerts(instance_id, metrics)
                        if self._push_gateway_url:
                            await self._push_to_prometheus(instance_id, metrics)
                        consecutive_failures = 0
                    else:
                        consecutive_failures += 1
                except Exception as exc:
                    consecutive_failures += 1
                    logger.warning(f"[Telemetry] Poll error for {instance_id}: {exc}")

                if consecutive_failures >= 5:
                    logger.error(f"[Telemetry] Too many failures for {instance_id}, stopping.")
                    break

                await asyncio.sleep(self._poll_interval)
        finally:
            ssh.close()
            self._monitored.pop(instance_id, None)

    def _parse_nvidia_smi(
        self, output: str, instance_id: str, provider: str
    ) -> list[GPUMetricPoint]:
        """Parse nvidia-smi CSV output into GPUMetricPoint objects."""
        metrics: list[GPUMetricPoint] = []
        for line in output.strip().split("\n"):
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 12:
                continue
            try:
                def _float(v: str) -> float:
                    # Clean up "[N/A]" and other non-numeric nvidia-smi outputs
                    cleaned = re.sub(r"[^\d.]", "", v)
                    return float(cleaned) if cleaned else 0.0

                mem_used = _float(parts[3])
                mem_total = _float(parts[5])
                mem_util = (mem_used / mem_total * 100) if mem_total else 0.0

                metrics.append(GPUMetricPoint(
                    instance_id=instance_id,
                    provider=provider,
                    gpu_index=int(_float(parts[0])),
                    gpu_name=parts[1].strip(),
                    utilization_pct=_float(parts[2]),
                    memory_used_mb=mem_used,
                    memory_free_mb=_float(parts[4]),
                    memory_total_mb=mem_total,
                    memory_utilization_pct=round(mem_util, 1),
                    temp_celsius=_float(parts[6]),
                    power_draw_w=_float(parts[7]),
                    power_limit_w=_float(parts[8]),
                    fan_speed_pct=_float(parts[9]),
                    sm_clock_mhz=_float(parts[10]),
                    ecc_errors=int(_float(parts[11])),
                ))
            except (ValueError, IndexError) as exc:
                logger.debug(f"[Telemetry] Parse error: {exc} — line: {line}")

        return metrics

    def _check_alerts(self, instance_id: str, metrics: list[GPUMetricPoint]) -> None:
        """Check metric thresholds and fire callbacks."""
        for m in metrics:
            alerts = m.is_critical()
            for alert_msg in alerts:
                logger.warning(f"[Telemetry] ALERT {instance_id}/GPU{m.gpu_index}: {alert_msg}")
                record = {
                    "instance_id": instance_id,
                    "gpu_index": m.gpu_index,
                    "alert": alert_msg,
                    "metric": m.to_dict(),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                self._alert_history.append(record)
                if self._alert_callback:
                    self._alert_callback(instance_id, alert_msg, m)

        # Idle detection: track utilization over time
        if metrics:
            avg_util = sum(m.utilization_pct for m in metrics) / len(metrics)
            readings = self._idle_tracker.setdefault(instance_id, [])
            readings.append(avg_util)
            readings_window = int(UTIL_IDLE_MIN * 60 / self._poll_interval)
            if len(readings) > readings_window:
                readings.pop(0)
                if all(u < UTIL_IDLE_PCT for u in readings):
                    idle_msg = f"GPU_IDLE: Utilization < {UTIL_IDLE_PCT}% for {UTIL_IDLE_MIN} minutes"
                    logger.warning(f"[Telemetry] ALERT {instance_id}: {idle_msg}")
                    if self._alert_callback:
                        self._alert_callback(instance_id, idle_msg, metrics[0])
                    self._idle_tracker[instance_id] = []  # Reset to avoid spam

    async def _push_to_prometheus(
        self, instance_id: str, metrics: list[GPUMetricPoint]
    ) -> None:
        """Push metrics to Prometheus Pushgateway."""
        lines: list[str] = []
        for m in metrics:
            label = f'instance_id="{instance_id}",gpu_index="{m.gpu_index}",provider="{m.provider}"'
            lines += [
                f'orquanta_gpu_utilization_pct{{{label}}} {m.utilization_pct}',
                f'orquanta_gpu_memory_used_gb{{{label}}} {m.memory_used_gb()}',
                f'orquanta_gpu_memory_total_gb{{{label}}} {round(m.memory_total_mb/1024, 2)}',
                f'orquanta_gpu_memory_utilization_pct{{{label}}} {m.memory_utilization_pct}',
                f'orquanta_gpu_temperature_celsius{{{label}}} {m.temp_celsius}',
                f'orquanta_gpu_power_draw_watts{{{label}}} {m.power_draw_w}',
                f'orquanta_gpu_fan_speed_pct{{{label}}} {m.fan_speed_pct}',
                f'orquanta_gpu_ecc_errors_total{{{label}}} {m.ecc_errors}',
            ]

        try:
            import httpx
            payload = "\n".join(lines) + "\n"
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    f"{self._push_gateway_url}/metrics/job/orquanta/instance/{instance_id}",
                    content=payload,
                    headers={"Content-Type": "text/plain"},
                )
        except Exception as exc:
            logger.debug(f"[Telemetry] Prometheus push failed: {exc}")
