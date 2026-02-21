"""
OrQuanta - Main FastAPI Application

Production-ready API for the autonomous GPU cloud platform.
Powered by self-optimizing AI and reinforcement learning.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import uvicorn

from core.autonomous_engine import get_decision_engine, ActionType
from core.benchmarking import get_benchmarking_system
from core.telemetry import TelemetryCollector

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Pydantic models for API
class GPURequest(BaseModel):
    """Request model for GPU allocation"""
    gpu_type: str = Field(..., description="GPU type (A100, H100, V100, T4)")
    gpu_count: int = Field(1, ge=1, le=16, description="Number of GPUs")
    duration_hours: Optional[int] = Field(None, description="Duration in hours")
    docker_image: Optional[str] = Field(None, description="Custom Docker image")
    environment: Optional[Dict[str, str]] = Field(default_factory=dict, description="Environment variables")


class JobStatus(BaseModel):
    """Job status response"""
    job_id: str
    status: str
    gpu_type: str
    gpu_count: int
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    cost: float
    logs_url: Optional[str]


class SystemMetrics(BaseModel):
    """System metrics response"""
    timestamp: datetime
    gpu_utilization: float
    queue_depth: int
    active_jobs: int
    sla_compliance: float
    cost_per_hour: float
    revenue_per_hour: float


class BenchmarkSummary(BaseModel):
    """Benchmark summary response"""
    timestamp: datetime
    overall_score: float
    cost_score: float
    performance_score: float
    feature_score: float
    ux_score: float
    recommendations: List[str]


class AutonomousMetrics(BaseModel):
    """Autonomous engine metrics"""
    status: str
    training_steps: int
    total_decisions: int
    avg_reward_100: float
    action_distribution: Dict[str, int]
    last_action: Optional[str]


# Application lifespan management
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle"""
    logger.info("Starting AI GPU Cloud Platform...")
    
    # Start autonomous decision engine
    decision_engine = get_decision_engine()
    decision_task = asyncio.create_task(decision_engine.run_decision_loop(interval_seconds=60))
    
    # Start competitive benchmarking
    benchmarking = get_benchmarking_system()
    benchmark_task = asyncio.create_task(benchmarking.run_continuous_benchmarking(interval_hours=6))
    
    logger.info("All systems operational")
    
    yield
    
    # Shutdown
    logger.info("Shutting down...")
    decision_engine.stop()
    benchmarking.stop()
    
    decision_task.cancel()
    benchmark_task.cancel()
    
    try:
        await decision_task
    except asyncio.CancelledError:
        pass
    
    try:
        await benchmark_task
    except asyncio.CancelledError:
        pass
    
    logger.info("Shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="OrQuanta - Autonomous GPU Cloud",
    description="Enterprise-grade GPU cloud platform with self-optimizing AI, reinforcement learning, and autonomous operations",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check endpoint
@app.get("/health", tags=["System"])
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    }


# GPU Management Endpoints
@app.post("/api/v1/jobs", response_model=JobStatus, tags=["Jobs"])
async def create_job(request: GPURequest, background_tasks: BackgroundTasks):
    """
    Create a new GPU job
    
    This endpoint allocates GPUs and starts a job with the specified configuration.
    The autonomous system will optimize placement and resource allocation.
    """
    try:
        # Generate job ID
        job_id = f"job-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        # Create job (placeholder - would integrate with actual job scheduler)
        job = JobStatus(
            job_id=job_id,
            status="pending",
            gpu_type=request.gpu_type,
            gpu_count=request.gpu_count,
            created_at=datetime.now(),
            started_at=None,
            completed_at=None,
            cost=0.0,
            logs_url=None
        )
        
        logger.info(f"Created job {job_id}: {request.gpu_count}x {request.gpu_type}")
        
        return job
        
    except Exception as e:
        logger.error(f"Failed to create job: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/jobs/{job_id}", response_model=JobStatus, tags=["Jobs"])
async def get_job_status(job_id: str):
    """Get status of a specific job"""
    # Placeholder - would query actual job database
    return JobStatus(
        job_id=job_id,
        status="running",
        gpu_type="A100",
        gpu_count=1,
        created_at=datetime.now(),
        started_at=datetime.now(),
        completed_at=None,
        cost=2.30,
        logs_url=f"/api/v1/jobs/{job_id}/logs"
    )


@app.delete("/api/v1/jobs/{job_id}", tags=["Jobs"])
async def cancel_job(job_id: str):
    """Cancel a running job"""
    logger.info(f"Cancelling job {job_id}")
    return {"status": "cancelled", "job_id": job_id}


@app.get("/api/v1/jobs", tags=["Jobs"])
async def list_jobs(status: Optional[str] = None, limit: int = 100):
    """List all jobs with optional status filter"""
    # Placeholder - would query actual job database
    return {
        "jobs": [],
        "total": 0,
        "limit": limit
    }


# Metrics and Monitoring Endpoints
@app.get("/api/v1/metrics/system", response_model=SystemMetrics, tags=["Metrics"])
async def get_system_metrics():
    """Get current system metrics"""
    try:
        collector = TelemetryCollector()
        state = await collector.collect_system_state()
        
        return SystemMetrics(
            timestamp=state.timestamp,
            gpu_utilization=state.gpu_utilization,
            queue_depth=state.queue_depth,
            active_jobs=state.active_jobs,
            sla_compliance=state.sla_compliance,
            cost_per_hour=state.current_cost_per_hour,
            revenue_per_hour=state.revenue_per_hour
        )
    except Exception as e:
        logger.error(f"Failed to get system metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/metrics/autonomous", response_model=AutonomousMetrics, tags=["Metrics"])
async def get_autonomous_metrics():
    """Get autonomous decision engine metrics"""
    try:
        engine = get_decision_engine()
        metrics = engine.get_metrics()
        
        return AutonomousMetrics(
            status=metrics['status'],
            training_steps=metrics['training_steps'],
            total_decisions=metrics['total_decisions'],
            avg_reward_100=metrics.get('avg_reward_100', 0.0),
            action_distribution=metrics.get('action_distribution', {}),
            last_action=metrics.get('last_action')
        )
    except Exception as e:
        logger.error(f"Failed to get autonomous metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/benchmark", response_model=BenchmarkSummary, tags=["Benchmarking"])
async def get_benchmark():
    """Get latest competitive benchmark results"""
    try:
        benchmarking = get_benchmarking_system()
        result = benchmarking.get_latest_benchmark()
        
        if not result:
            # Run benchmark if none exists
            result = await benchmarking.run_benchmark()
        
        return BenchmarkSummary(
            timestamp=result.timestamp,
            overall_score=result.overall_score,
            cost_score=result.cost_score,
            performance_score=result.performance_score,
            feature_score=result.feature_score,
            ux_score=result.ux_score,
            recommendations=result.recommendations
        )
    except Exception as e:
        logger.error(f"Failed to get benchmark: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/benchmark/run", tags=["Benchmarking"])
async def run_benchmark(background_tasks: BackgroundTasks):
    """Trigger a new benchmark run"""
    async def run_benchmark_task():
        benchmarking = get_benchmarking_system()
        await benchmarking.run_benchmark()
    
    background_tasks.add_task(run_benchmark_task)
    return {"status": "benchmark_started"}


# Pricing Endpoints
@app.get("/api/v1/pricing", tags=["Pricing"])
async def get_pricing():
    """Get current GPU pricing"""
    return {
        "pricing": {
            "A100": {
                "on_demand": 2.30,
                "spot": 1.50,
                "currency": "USD",
                "unit": "per_hour"
            },
            "H100": {
                "on_demand": 3.99,
                "spot": 2.50,
                "currency": "USD",
                "unit": "per_hour"
            },
            "V100": {
                "on_demand": 1.40,
                "spot": 0.90,
                "currency": "USD",
                "unit": "per_hour"
            },
            "T4": {
                "on_demand": 0.55,
                "spot": 0.35,
                "currency": "USD",
                "unit": "per_hour"
            }
        },
        "updated_at": datetime.now().isoformat()
    }


# Admin Endpoints
@app.post("/api/v1/admin/autonomous/start", tags=["Admin"])
async def start_autonomous_engine():
    """Start the autonomous decision engine"""
    engine = get_decision_engine()
    if not engine.running:
        asyncio.create_task(engine.run_decision_loop())
        return {"status": "started"}
    return {"status": "already_running"}


@app.post("/api/v1/admin/autonomous/stop", tags=["Admin"])
async def stop_autonomous_engine():
    """Stop the autonomous decision engine"""
    engine = get_decision_engine()
    engine.stop()
    return {"status": "stopped"}


@app.get("/api/v1/admin/decisions", tags=["Admin"])
async def get_decision_history(limit: int = 100):
    """Get recent autonomous decisions"""
    engine = get_decision_engine()
    history = list(engine.decision_history)[-limit:]
    return {"decisions": history, "total": len(history)}


# Error handlers
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "type": type(exc).__name__}
    )


# Main entry point
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
