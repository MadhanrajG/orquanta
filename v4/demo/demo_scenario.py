"""
OrQuanta Agentic v1.0 — Pre-Built Demo Scenarios
=================================================

Three compelling scenarios that run automatically in demo mode,
each designed to showcase a key OrQuanta capability.

Scenario 1: "Cost Optimizer saves $200"
  → Submits 5 training jobs, switches from AWS to Lambda Labs mid-run,
    shows cumulative $200+ savings in dashboard

Scenario 2: "Self-Healing recovery"
  → Job fails with OOM, HealingAgent detects + recovers in 8.3s,
    full reasoning visible in agent monitor

Scenario 3: "Natural language to running GPU"
  → User types goal in plain English, 5 agents activate,
    GPU job running in <30s
"""
from __future__ import annotations

import asyncio
import logging

from v4.demo.demo_mode import DemoEngine, DemoEvent, get_demo_engine

logger = logging.getLogger("orquanta.demo.scenarios")


# ─── Scenario 1: Cost Optimizer ───────────────────────────────────────────────

async def scenario_cost_optimizer(engine: DemoEngine) -> dict:
    """
    Submits 5 jobs with provider comparison, showing cumulative savings.
    Designed to fill the 'Spend & Savings' Grafana panel with real data.
    """
    logger.info("[Demo] Running Scenario 1: Cost Optimizer")
    await engine._emit(DemoEvent("scenario_start", {
        "scenario": "cost_optimizer",
        "title": "Scenario 1: Cost Optimizer saves $200",
        "description": "Watch OrQuanta automatically select the cheapest GPU across 4 providers.",
    }))

    jobs = [
        ("Fine-tune LLaMA 3 8B on customer support dataset",      "gpu_1x_a100", "lambda", 20),
        ("Train ResNet-50 on ImageNet subset, 50 epochs",          "gpu_1x_a10",  "lambda", 15),
        ("Generate embeddings for 1M product descriptions",        "gpu_1x_a100", "lambda", 25),
        ("Run inference benchmark on Mistral 7B Instruct",         "gpu_1x_a10",  "lambda", 10),
        ("Fine-tune Whisper Large v3 on custom audio dataset",     "gpu_1x_a100", "lambda", 30),
    ]

    total_saved = 0.0
    submitted_jobs = []

    for i, (goal, gpu, provider, duration) in enumerate(jobs, 1):
        await engine._emit(DemoEvent("agent_thought", {
            "agent": "cost_optimizer",
            "icon": "💸",
            "message": f"Job {i}/5: Comparing prices... Lambda Labs wins at ${0.75 if 'a10' in gpu else 1.99:.2f}/hr",
            "confidence": 0.94,
        }))
        job = await engine.submit_demo_job(goal, gpu, provider, duration)
        submitted_jobs.append(job)
        await asyncio.sleep(3)  # stagger starts

    # Wait for all jobs
    timeout = 120
    elapsed = 0
    while elapsed < timeout:
        all_done = all(
            j.phase.value in ("complete", "failed")
            for j in submitted_jobs
        )
        if all_done:
            break
        await asyncio.sleep(2)
        elapsed += 2

    total_saved = sum(j.saved_vs_aws for j in submitted_jobs)
    total_cost  = sum(j.cost_so_far  for j in submitted_jobs)

    await engine._emit(DemoEvent("scenario_complete", {
        "scenario": "cost_optimizer",
        "summary": f"5 jobs complete. Total saved: ${total_saved:.2f} vs AWS on-demand. Total cost: ${total_cost:.2f}.",
        "jobs_completed": len(submitted_jobs),
        "total_saved_usd": round(total_saved, 2),
        "total_cost_usd": round(total_cost, 2),
        "savings_pct": round(total_saved / (total_saved + total_cost) * 100, 1) if total_cost else 0,
    }))
    logger.info(f"[Demo] Scenario 1 complete — saved ${total_saved:.2f}")
    return {"scenario": "cost_optimizer", "saved": total_saved, "cost": total_cost}


# ─── Scenario 2: Self-Healing ─────────────────────────────────────────────────

async def scenario_self_healing(engine: DemoEngine) -> dict:
    """
    Submits one job with a forced OOM failure, shows healing in 8.3s.
    Showcases the most dramatic OrQuanta capability.
    """
    logger.info("[Demo] Running Scenario 2: Self-Healing")
    await engine._emit(DemoEvent("scenario_start", {
        "scenario": "self_healing",
        "title": "Scenario 2: HealingAgent rescues a failing job",
        "description": "Watch OrQuanta detect VRAM overflow and recover — automatically.",
    }))

    await engine._emit(DemoEvent("agent_thought", {
        "agent": "orquanta_orchestrator",
        "icon": "🧠",
        "message": "Submitting LLaMA 7B fine-tune job. Confidence: 0.89.",
    }))
    await asyncio.sleep(1)

    await engine._emit(DemoEvent("agent_thought", {
        "agent": "healing_agent",
        "icon": "🔧",
        "message": "1Hz telemetry monitor armed on gpu_1x_a100 | Threshold: VRAM > 95%",
    }))

    job = await engine.submit_demo_job(
        goal="Fine-tune LLaMA 3 7B with 4096 context window, batch_size=32",
        gpu_type="gpu_1x_a100",
        provider="lambda",
        duration_min=25,
        inject_failure=True,   # ← forces OOM at ~40% progress
    )

    # Wait for job completion
    for _ in range(90):
        if job.phase.value in ("complete", "failed"):
            break
        await asyncio.sleep(1)

    result = {
        "scenario": "self_healing",
        "job_id": job.job_id,
        "healed": job.healed,
        "heal_count": job.heal_count,
        "completed": job.phase.value == "complete",
        "cost": job.cost_so_far,
    }
    await engine._emit(DemoEvent("scenario_complete", {
        **result,
        "summary": "OOM detected at 97.3% VRAM. HealingAgent intervened in 8.3s. "
                   "Job recovered and completed. Zero data loss. Zero human intervention.",
        "mttr_seconds": 8.3,
        "human_intervention": 0,
    }))
    logger.info(f"[Demo] Scenario 2 complete — healed: {job.healed}")
    return result


# ─── Scenario 3: Natural Language Goal ───────────────────────────────────────

async def scenario_natural_language(engine: DemoEngine) -> dict:
    """
    Shows the full agentic pipeline from NL goal → running GPU job.
    Maximizes the 'OrMind Orchestrator' showcase.
    """
    logger.info("[Demo] Running Scenario 3: Natural Language Goal")

    goal_text = "Fine-tune Mistral 7B Instruct on my customer support tickets. Keep it under $50."

    await engine._emit(DemoEvent("scenario_start", {
        "scenario": "natural_language",
        "title": "Scenario 3: Natural Language → Running GPU Job",
        "description": f'User typed: "{goal_text}"',
    }))

    # Orchestrator thinking steps
    thinking_steps = [
        ("orquanta_orchestrator", "🧠", "Parsing natural language goal...", 0.91),
        ("orquanta_orchestrator", "🧠", "Intent: fine_tune | Model: Mistral 7B | Budget: $50 | Constraint: cost_limit", 0.93),
        ("orquanta_orchestrator", "🧠", "DAG: 5 tasks | Dependencies resolved | Dispatching agents", 0.91),
        ("cost_optimizer",        "💸", "Budget $50 → max 25 GPU-hours at $2/hr | Searching cheapest A100...", 0.95),
        ("cost_optimizer",        "💸", "Lambda Labs gpu_1x_a100 @ $1.99/hr | Estimated: $39.80 for 20hrs | Under budget ✓", 0.97),
        ("scheduler",             "📅", "No queue backlog | Provisioning now | ETA: 18 seconds", 0.99),
    ]

    for agent, icon, message, conf in thinking_steps:
        await engine._emit(DemoEvent("agent_thought", {
            "agent": agent, "icon": icon, "message": message, "confidence": conf,
        }))
        await asyncio.sleep(0.9)

    job = await engine.submit_demo_job(
        goal=goal_text,
        gpu_type="gpu_1x_a100",
        provider="lambda",
        duration_min=20,
    )

    await asyncio.sleep(2)
    await engine._emit(DemoEvent("agent_thought", {
        "agent": "audit_agent",
        "icon": "🔒",
        "message": f"Job {job.job_id} logged. Goal hash: {hash(goal_text)&0xFFFFFF:06X}. HMAC signing batch #1.",
    }))

    # Wait for at least 30% progress before returning scenario result
    for _ in range(60):
        if job.progress_pct >= 30 or job.phase.value == "complete":
            break
        await asyncio.sleep(1)

    await engine._emit(DemoEvent("scenario_complete", {
        "scenario": "natural_language",
        "job_id": job.job_id,
        "goal": goal_text,
        "time_to_running_s": 18,
        "provider": "lambda",
        "gpu_type": "gpu_1x_a100",
        "cost_per_hr": job.cost_per_hr,
        "estimated_total": round(job.cost_per_hr * (job.duration_min / 60), 2),
        "under_budget": True,
        "summary": (
            f"Natural language goal → running GPU job in 18 seconds. "
            f"4 agents coordinated. Lambda Labs selected at $1.99/hr. "
            f"Estimated cost: ${job.cost_per_hr * (job.duration_min / 60):.2f} — under $50 budget."
        ),
    }))
    logger.info(f"[Demo] Scenario 3 complete — {job.job_id} running")
    return {"scenario": "natural_language", "job_id": job.job_id}


# ─── Scenario Runner ──────────────────────────────────────────────────────────

SCENARIOS = {
    "cost_optimizer":   scenario_cost_optimizer,
    "self_healing":     scenario_self_healing,
    "natural_language": scenario_natural_language,
}


async def run_scenario(name: str, engine: DemoEngine | None = None) -> dict:
    """Run a named demo scenario. Returns result dict."""
    if engine is None:
        engine = get_demo_engine()
    if not engine.is_active():
        await engine.start()

    fn = SCENARIOS.get(name)
    if not fn:
        raise ValueError(f"Unknown scenario '{name}'. Available: {list(SCENARIOS.keys())}")

    return await fn(engine)


async def run_all_scenarios(engine: DemoEngine | None = None) -> list[dict]:
    """Run all three scenarios in sequence."""
    if engine is None:
        engine = get_demo_engine()
    if not engine.is_active():
        await engine.start()

    results = []
    for name, fn in SCENARIOS.items():
        try:
            result = await fn(engine)
            results.append(result)
            await asyncio.sleep(3)  # pause between scenarios
        except Exception as exc:
            logger.error(f"[Demo] Scenario '{name}' failed: {exc}")
            results.append({"scenario": name, "error": str(exc)})
    return results
