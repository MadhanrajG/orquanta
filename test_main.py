"""
Test version of main.py for validation
Runs with minimal dependencies for testing
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Pydantic models
class GPURequest(BaseModel):
    """Request model for GPU allocation"""
    gpu_type: str = Field(..., description="GPU type (A100, H100, V100, T4)")
    gpu_count: int = Field(1, ge=1, le=16, description="Number of GPUs")
    duration_hours: Optional[int] = Field(None, description="Duration in hours")


class JobStatus(BaseModel):
    """Job status response"""
    job_id: str
    status: str
    gpu_type: str
    gpu_count: int
    created_at: datetime
    cost: float


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
    recommendations: list


# Create FastAPI app
app = FastAPI(
    title="AI GPU Cloud - Test Mode",
    description="Self-optimizing GPU cloud platform (Test Mode)",
    version="1.0.0-test"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0-test",
        "mode": "test"
    }


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "AI GPU Cloud - Autonomous Platform",
        "status": "running",
        "docs": "/docs",
        "health": "/health"
    }


@app.post("/api/v1/jobs", response_model=JobStatus)
async def create_job(request: GPURequest):
    """Create a new GPU job"""
    job_id = f"job-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    logger.info(f"Created job {job_id}: {request.gpu_count}x {request.gpu_type}")
    
    return JobStatus(
        job_id=job_id,
        status="pending",
        gpu_type=request.gpu_type,
        gpu_count=request.gpu_count,
        created_at=datetime.now(),
        cost=0.0
    )


@app.get("/api/v1/jobs/{job_id}", response_model=JobStatus)
async def get_job_status(job_id: str):
    """Get status of a specific job"""
    return JobStatus(
        job_id=job_id,
        status="running",
        gpu_type="A100",
        gpu_count=1,
        created_at=datetime.now(),
        cost=2.30
    )


@app.get("/api/v1/metrics/system", response_model=SystemMetrics)
async def get_system_metrics():
    """Get current system metrics"""
    return SystemMetrics(
        timestamp=datetime.now(),
        gpu_utilization=0.87,
        queue_depth=5,
        active_jobs=12,
        sla_compliance=0.9985,
        cost_per_hour=25.0,
        revenue_per_hour=40.0
    )


@app.get("/api/v1/benchmark", response_model=BenchmarkSummary)
async def get_benchmark():
    """Get latest competitive benchmark results"""
    return BenchmarkSummary(
        timestamp=datetime.now(),
        overall_score=92.0,
        cost_score=95.0,
        performance_score=88.0,
        recommendations=[
            "✅ PRICING: Excellent cost competitiveness maintained",
            "✅ PERFORMANCE: Leading performance metrics across the board",
            "🎯 OVERALL: Platform is highly competitive across all dimensions"
        ]
    )


@app.get("/api/v1/pricing")
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
            }
        },
        "updated_at": datetime.now().isoformat()
    }


@app.get("/api/v1/status")
async def get_platform_status():
    """Get overall platform status"""
    return {
        "platform": "AI GPU Cloud",
        "version": "1.0.0-test",
        "status": "operational",
        "mode": "test",
        "features": {
            "autonomous_optimization": "enabled",
            "self_healing": "enabled",
            "dynamic_pricing": "enabled",
            "competitive_benchmarking": "enabled"
        },
        "uptime": "99.95%",
        "active_gpus": 48,
        "available_gpus": 12,
        "timestamp": datetime.now().isoformat()
    }


if __name__ == "__main__":
    logger.info("Starting AI GPU Cloud Platform (Test Mode)...")
    logger.info("=" * 60)
    logger.info("🚀 AI GPU Cloud - Autonomous Platform")
    logger.info("=" * 60)
    logger.info("Mode: Test/Validation")
    logger.info("API will be available at: http://localhost:8000")
    logger.info("API Docs: http://localhost:8000/docs")
    logger.info("=" * 60)
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
