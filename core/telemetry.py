"""
Telemetry Collection System

Collects metrics from GPU nodes, jobs, users, and market data
for the autonomous decision engine.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import aiohttp
import psutil
import GPUtil
from dataclasses import asdict

from .autonomous_engine import SystemState

logger = logging.getLogger(__name__)


class GPUMetricsCollector:
    """Collect GPU-specific metrics"""
    
    async def collect(self) -> Dict[str, any]:
        """Collect GPU metrics from all nodes"""
        try:
            gpus = GPUtil.getGPUs()
            
            total_gpus = len(gpus)
            available_gpus = sum(1 for gpu in gpus if gpu.memoryUtil < 0.8)
            
            gpu_utilization = sum(gpu.load for gpu in gpus) / max(total_gpus, 1)
            gpu_memory_usage = sum(gpu.memoryUtil for gpu in gpus) / max(total_gpus, 1)
            
            gpu_temperature = {
                f"gpu_{i}": gpu.temperature for i, gpu in enumerate(gpus)
            }
            
            return {
                'total_gpus': total_gpus,
                'available_gpus': available_gpus,
                'gpu_utilization': gpu_utilization,
                'gpu_memory_usage': gpu_memory_usage,
                'gpu_temperature': gpu_temperature,
            }
        except Exception as e:
            logger.warning(f"Failed to collect GPU metrics: {e}")
            return {
                'total_gpus': 0,
                'available_gpus': 0,
                'gpu_utilization': 0.0,
                'gpu_memory_usage': 0.0,
                'gpu_temperature': {},
            }


class JobMetricsCollector:
    """Collect job queue and execution metrics"""
    
    def __init__(self, db_connection):
        self.db = db_connection
    
    async def collect(self) -> Dict[str, any]:
        """Collect job-related metrics"""
        try:
            # Query job database
            queue_depth = await self._get_queue_depth()
            active_jobs = await self._get_active_jobs_count()
            completed_jobs_1h = await self._get_completed_jobs_count(hours=1)
            failed_jobs_1h = await self._get_failed_jobs_count(hours=1)
            avg_job_duration = await self._get_avg_job_duration()
            p95_job_latency = await self._get_p95_latency()
            
            return {
                'queue_depth': queue_depth,
                'active_jobs': active_jobs,
                'completed_jobs_1h': completed_jobs_1h,
                'failed_jobs_1h': failed_jobs_1h,
                'avg_job_duration': avg_job_duration,
                'p95_job_latency': p95_job_latency,
            }
        except Exception as e:
            logger.warning(f"Failed to collect job metrics: {e}")
            return {
                'queue_depth': 0,
                'active_jobs': 0,
                'completed_jobs_1h': 0,
                'failed_jobs_1h': 0,
                'avg_job_duration': 0.0,
                'p95_job_latency': 0.0,
            }
    
    async def _get_queue_depth(self) -> int:
        """Get number of jobs waiting in queue"""
        # Placeholder - would query actual job queue
        return 5
    
    async def _get_active_jobs_count(self) -> int:
        """Get number of currently running jobs"""
        return 10
    
    async def _get_completed_jobs_count(self, hours: int) -> int:
        """Get number of completed jobs in last N hours"""
        return 50
    
    async def _get_failed_jobs_count(self, hours: int) -> int:
        """Get number of failed jobs in last N hours"""
        return 2
    
    async def _get_avg_job_duration(self) -> float:
        """Get average job duration in seconds"""
        return 300.0
    
    async def _get_p95_latency(self) -> float:
        """Get 95th percentile job latency"""
        return 5.0


class CostMetricsCollector:
    """Collect cost and revenue metrics"""
    
    def __init__(self, billing_system):
        self.billing = billing_system
    
    async def collect(self) -> Dict[str, float]:
        """Collect cost and revenue metrics"""
        try:
            current_cost_per_hour = await self._get_current_cost_rate()
            revenue_per_hour = await self._get_current_revenue_rate()
            profit_margin = (revenue_per_hour - current_cost_per_hour) / max(revenue_per_hour, 1.0)
            
            return {
                'current_cost_per_hour': current_cost_per_hour,
                'revenue_per_hour': revenue_per_hour,
                'profit_margin': profit_margin,
            }
        except Exception as e:
            logger.warning(f"Failed to collect cost metrics: {e}")
            return {
                'current_cost_per_hour': 0.0,
                'revenue_per_hour': 0.0,
                'profit_margin': 0.0,
            }
    
    async def _get_current_cost_rate(self) -> float:
        """Get current cost per hour"""
        # Placeholder - would query cloud provider APIs
        return 25.0
    
    async def _get_current_revenue_rate(self) -> float:
        """Get current revenue per hour"""
        # Placeholder - would query billing system
        return 40.0


class MarketIntelligenceCollector:
    """Collect competitor pricing and market data"""
    
    async def collect(self) -> Dict[str, any]:
        """Collect market intelligence"""
        try:
            competitor_pricing = await self._scrape_competitor_pricing()
            demand_forecast_1h = await self._forecast_demand(hours=1)
            demand_forecast_24h = await self._forecast_demand(hours=24)
            
            return {
                'competitor_pricing': competitor_pricing,
                'demand_forecast_1h': demand_forecast_1h,
                'demand_forecast_24h': demand_forecast_24h,
            }
        except Exception as e:
            logger.warning(f"Failed to collect market intelligence: {e}")
            return {
                'competitor_pricing': {},
                'demand_forecast_1h': 0.0,
                'demand_forecast_24h': 0.0,
            }
    
    async def _scrape_competitor_pricing(self) -> Dict[str, float]:
        """Scrape competitor pricing"""
        # Placeholder - would scrape RunPod, Lambda Labs, Vast.ai
        return {
            'runpod_a100': 2.89,
            'lambda_a100': 3.09,
            'vast_a100': 2.50,
        }
    
    async def _forecast_demand(self, hours: int) -> float:
        """Forecast demand for next N hours"""
        # Placeholder - would use ML model
        return 15.0


class HealthMetricsCollector:
    """Collect node health and reliability metrics"""
    
    async def collect(self) -> Dict[str, any]:
        """Collect health metrics"""
        try:
            node_health_scores = await self._get_node_health_scores()
            error_rate = await self._get_error_rate()
            sla_compliance = await self._get_sla_compliance()
            
            return {
                'node_health_scores': node_health_scores,
                'error_rate': error_rate,
                'sla_compliance': sla_compliance,
            }
        except Exception as e:
            logger.warning(f"Failed to collect health metrics: {e}")
            return {
                'node_health_scores': {},
                'error_rate': 0.0,
                'sla_compliance': 1.0,
            }
    
    async def _get_node_health_scores(self) -> Dict[str, float]:
        """Get health score for each node (0.0 to 1.0)"""
        # Placeholder - would query monitoring system
        return {
            'node-1': 0.95,
            'node-2': 0.98,
            'node-3': 0.75,  # Unhealthy
            'node-4': 0.92,
        }
    
    async def _get_error_rate(self) -> float:
        """Get current error rate"""
        return 0.005  # 0.5%
    
    async def _get_sla_compliance(self) -> float:
        """Get SLA compliance rate"""
        return 0.9985  # 99.85%


class UserMetricsCollector:
    """Collect user behavior and satisfaction metrics"""
    
    def __init__(self, user_db):
        self.user_db = user_db
    
    async def collect(self) -> Dict[str, any]:
        """Collect user metrics"""
        try:
            active_users = await self._get_active_users_count()
            new_user_signups_1h = await self._get_new_signups(hours=1)
            user_satisfaction_score = await self._get_satisfaction_score()
            
            return {
                'active_users': active_users,
                'new_user_signups_1h': new_user_signups_1h,
                'user_satisfaction_score': user_satisfaction_score,
            }
        except Exception as e:
            logger.warning(f"Failed to collect user metrics: {e}")
            return {
                'active_users': 0,
                'new_user_signups_1h': 0,
                'user_satisfaction_score': 0.8,
            }
    
    async def _get_active_users_count(self) -> int:
        """Get number of active users"""
        return 25
    
    async def _get_new_signups(self, hours: int) -> int:
        """Get new user signups in last N hours"""
        return 3
    
    async def _get_satisfaction_score(self) -> float:
        """Get user satisfaction score (0.0 to 1.0)"""
        # Would be calculated from NPS, support tickets, etc.
        return 0.85


class TelemetryCollector:
    """
    Main telemetry collector that aggregates all metrics
    into a SystemState object.
    """
    
    def __init__(self):
        self.gpu_collector = GPUMetricsCollector()
        # These would be initialized with actual connections
        self.job_collector = JobMetricsCollector(db_connection=None)
        self.cost_collector = CostMetricsCollector(billing_system=None)
        self.market_collector = MarketIntelligenceCollector()
        self.health_collector = HealthMetricsCollector()
        self.user_collector = UserMetricsCollector(user_db=None)
    
    async def collect_system_state(self) -> SystemState:
        """Collect all metrics and create SystemState"""
        
        # Collect all metrics in parallel
        results = await asyncio.gather(
            self.gpu_collector.collect(),
            self.job_collector.collect(),
            self.cost_collector.collect(),
            self.market_collector.collect(),
            self.health_collector.collect(),
            self.user_collector.collect(),
            return_exceptions=True
        )
        
        # Unpack results
        gpu_metrics = results[0] if not isinstance(results[0], Exception) else {}
        job_metrics = results[1] if not isinstance(results[1], Exception) else {}
        cost_metrics = results[2] if not isinstance(results[2], Exception) else {}
        market_metrics = results[3] if not isinstance(results[3], Exception) else {}
        health_metrics = results[4] if not isinstance(results[4], Exception) else {}
        user_metrics = results[5] if not isinstance(results[5], Exception) else {}
        
        # Create SystemState
        state = SystemState(
            timestamp=datetime.now(),
            **gpu_metrics,
            **job_metrics,
            **cost_metrics,
            **market_metrics,
            **health_metrics,
            **user_metrics,
        )
        
        logger.debug(f"Collected system state: {asdict(state)}")
        
        return state


class PrometheusExporter:
    """Export metrics to Prometheus for monitoring"""
    
    def __init__(self, port: int = 9090):
        self.port = port
        from prometheus_client import start_http_server, Gauge
        
        # Define Prometheus metrics
        self.gpu_utilization = Gauge('gpu_utilization', 'GPU utilization percentage')
        self.queue_depth = Gauge('queue_depth', 'Number of jobs in queue')
        self.active_jobs = Gauge('active_jobs', 'Number of active jobs')
        self.error_rate = Gauge('error_rate', 'Current error rate')
        self.sla_compliance = Gauge('sla_compliance', 'SLA compliance rate')
        self.cost_per_hour = Gauge('cost_per_hour', 'Current cost per hour')
        self.revenue_per_hour = Gauge('revenue_per_hour', 'Current revenue per hour')
        
        start_http_server(port)
        logger.info(f"Prometheus exporter started on port {port}")
    
    def update_metrics(self, state: SystemState):
        """Update Prometheus metrics from SystemState"""
        self.gpu_utilization.set(state.gpu_utilization)
        self.queue_depth.set(state.queue_depth)
        self.active_jobs.set(state.active_jobs)
        self.error_rate.set(state.error_rate)
        self.sla_compliance.set(state.sla_compliance)
        self.cost_per_hour.set(state.current_cost_per_hour)
        self.revenue_per_hour.set(state.revenue_per_hour)


class TelemetryAggregator:
    """
    Aggregates telemetry data over time for historical analysis
    and trend detection.
    """
    
    def __init__(self, retention_hours: int = 168):  # 7 days
        self.retention_hours = retention_hours
        self.history: List[SystemState] = []
    
    def add_state(self, state: SystemState):
        """Add a state to history"""
        self.history.append(state)
        
        # Remove old data
        cutoff_time = datetime.now() - timedelta(hours=self.retention_hours)
        self.history = [s for s in self.history if s.timestamp > cutoff_time]
    
    def get_trend(self, metric_name: str, hours: int = 24) -> List[float]:
        """Get trend for a specific metric"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        recent_states = [s for s in self.history if s.timestamp > cutoff_time]
        
        return [getattr(s, metric_name) for s in recent_states]
    
    def detect_anomalies(self, metric_name: str, threshold_std: float = 3.0) -> List[datetime]:
        """Detect anomalies using standard deviation"""
        import numpy as np
        
        values = [getattr(s, metric_name) for s in self.history]
        timestamps = [s.timestamp for s in self.history]
        
        if len(values) < 10:
            return []
        
        mean = np.mean(values)
        std = np.std(values)
        
        anomalies = []
        for i, value in enumerate(values):
            if abs(value - mean) > threshold_std * std:
                anomalies.append(timestamps[i])
        
        return anomalies
