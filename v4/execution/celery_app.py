"""
OrQuanta — Celery Application Configuration
==========================================
Configures the Celery app with Redis as broker and result backend.
All task modules are auto-discovered from the execution package.

Usage:
    # Start worker:
    celery -A v4.execution.celery_app worker --loglevel=info --concurrency=4 -Q orquanta.jobs

    # Start beat (periodic tasks — reconciler, health checks):
    celery -A v4.execution.celery_app beat --loglevel=info

    # Flower monitoring:
    celery -A v4.execution.celery_app flower
"""
from __future__ import annotations

import os
from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Separate DB for Celery results to avoid polluting app cache
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", REDIS_URL.replace("/0", "/1"))

celery_app = Celery(
    "orquanta",
    broker=REDIS_URL,
    backend=CELERY_RESULT_BACKEND,
    include=[
        "v4.execution.tasks",           # GPU job tasks
        "v4.execution.reconciler",      # Periodic reconciliation
        "v4.execution.provider_health", # Provider health checks
    ],
)

celery_app.conf.update(
    # Serialisation — always JSON, never pickle (security)
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    # Timezone
    timezone="UTC",
    enable_utc=True,
    # Reliability
    task_acks_late=True,                     # Ack AFTER task completes (not before)
    task_reject_on_worker_lost=True,         # Requeue if worker dies mid-execution
    task_track_started=True,                 # Emit STARTED state for observability
    worker_prefetch_multiplier=1,            # Fair dispatch — one task per worker slot
    # Result expiry — keep for 7 days
    result_expires=604800,
    # Soft/hard time limits (overridden per-task for GPU workloads)
    task_soft_time_limit=7200,               # 2h soft limit → SoftTimeLimitExceeded
    task_time_limit=7500,                    # 2h5m hard kill
    # Retry policy defaults
    task_max_retries=3,
    # Queue routing
    task_default_queue="orquanta.jobs",
    task_routes={
        "v4.execution.tasks.execute_gpu_job": {"queue": "orquanta.jobs"},
        "v4.execution.reconciler.*": {"queue": "orquanta.ops"},
        "v4.execution.provider_health.*": {"queue": "orquanta.ops"},
    },
    # Beat schedule (periodic tasks)
    beat_schedule={
        "reconcile-stuck-jobs": {
            "task": "v4.execution.reconciler.reconcile_stuck_jobs",
            "schedule": 60.0,  # every 60s
        },
        "check-provider-health": {
            "task": "v4.execution.provider_health.check_all_providers",
            "schedule": 120.0,  # every 2m
        },
        "cleanup-outbox": {
            "task": "v4.execution.reconciler.flush_outbox",
            "schedule": 10.0,  # every 10s
        },
    },
    # Broker connection resilience
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=10,
    broker_transport_options={
        "visibility_timeout": 7800,  # > hard time limit to prevent premature requeue
        "max_retries": 5,
    },
)
