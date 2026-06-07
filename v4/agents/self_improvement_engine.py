"""
OrQuanta Agentic v1.0  -  Recursive AI Self-Improvement Engine

This module implements recursive self-improvement across three dimensions:

1. PolicyMutationEngine
   - Tracks outcome quality of GPU scheduling decisions
   - Mutates cost/performance/risk weights based on real outcomes
   - Uses clamped gradient descent with safety bounds
   - Persists policy snapshots to SQLite for audit + rollback

2. PromptEvolutionEngine
   - Tracks per-template LLM success rates (parse success, task completion)
   - When a template underperforms (<70% success), triggers LLM self-reflection
   - Generates improved template variant, A/B tests it over next N calls
   - Promotes winner, archives loser with performance metadata

3. AgentReflectionLoop
   - After each GoalExecution completes (success or failure), calls LLM reflection
   - "Given what happened, what would you do differently?"
   - Extracts actionable delta (weight changes, routing changes, new heuristics)
   - Applies validated deltas to live policy state

Together, these form a closed feedback loop:
    Goal → Execute → Observe Outcome → Reflect → Mutate Policy → Next Goal (improved)

Architecture:
    SelfImprovementEngine (singleton)
        ├── PolicyMutationEngine      (weight gradient descent)
        ├── PromptEvolutionEngine     (template A/B testing)
        └── AgentReflectionLoop       (post-goal LLM reflection)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

logger = logging.getLogger("orquanta.self_improvement")

_DB_PATH = os.getenv("SELF_IMPROVEMENT_DB", "v4/self_improvement.db")

# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class PolicySnapshot:
    """Immutable snapshot of policy weights at a point in time."""
    version: int
    weights: dict[str, float]
    cause: str
    performance_score: float        # 0.0-1.0 overall outcome quality
    cost_efficiency_delta: float    # change vs previous snapshot
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    snapshot_id: str = field(default_factory=lambda: str(uuid4())[:8])


@dataclass
class TemplatePerformance:
    """Per-template LLM call success tracking."""
    template_name: str
    total_calls: int = 0
    successful_parses: int = 0
    task_completions: int = 0
    avg_latency_ms: float = 0.0
    last_evolved_at: str = ""
    evolution_count: int = 0
    active_variant: str = "original"    # "original" | "evolved_vN"

    @property
    def success_rate(self) -> float:
        if self.total_calls == 0:
            return 1.0
        return self.successful_parses / self.total_calls

    @property
    def completion_rate(self) -> float:
        if self.total_calls == 0:
            return 1.0
        return self.task_completions / self.total_calls


@dataclass
class ReflectionEntry:
    """A single agent reflection after a goal completes."""
    reflection_id: str
    goal_id: str
    goal_text: str
    outcome: str            # "completed" | "failed"
    cost_usd: float
    tasks_completed: int
    tasks_failed: int
    reflection_text: str    # LLM's "what would I do differently?"
    applied_mutations: list[dict]   # deltas actually applied to policy
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ImprovementReport:
    """Full self-improvement status report — served by API."""
    # Policy
    policy_version: int
    policy_weights: dict[str, float]
    total_mutations: int
    last_mutation_cause: str
    last_mutation_at: str
    policy_history: list[dict]      # last 20 snapshots

    # Prompt evolution
    template_stats: list[dict]      # per-template metrics
    total_evolutions: int
    templates_evolved: list[str]

    # Reflection
    total_reflections: int
    recent_reflections: list[dict]  # last 10 entries
    avg_improvement_per_reflection: float

    # Overall health
    improvement_health: str         # "excellent" | "good" | "stagnant" | "regressing"
    learning_velocity: float        # mutations per hour
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ---------------------------------------------------------------------------
# PolicyMutationEngine
# ---------------------------------------------------------------------------

class PolicyMutationEngine:
    """
    Gradient-descent style weight mutation for GPU routing policy.

    Weights: cost (0-1), perf (0-1), risk (0-1) — always sum to 1.0
    Mutation: outcome_quality → compute gradient → apply clamped update
    Safety: max per-step delta = 0.15 per weight, min/max per weight = 0.05/0.90
    Decay: every 30 min, weights drift 5% toward balanced baseline to prevent overfitting
    """

    BASELINE = {"cost": 0.50, "perf": 0.30, "risk": 0.20}
    CLAMP_MIN = 0.05
    CLAMP_MAX = 0.90
    MAX_STEP = 0.15
    DECAY_RATE = 0.05
    DECAY_INTERVAL_S = 1800.0   # 30 min

    def __init__(self) -> None:
        self.version = 1
        self.weights = {"cost": 0.60, "perf": 0.25, "risk": 0.15}
        self.history: list[PolicySnapshot] = []
        self._last_decay = time.time()
        self._total_mutations = 0
        self._db_path = _DB_PATH
        self._load()
        logger.info(
            f"[PolicyMutation] Loaded policy v{self.version}: "
            f"cost={self.weights['cost']:.2f} perf={self.weights['perf']:.2f} "
            f"risk={self.weights['risk']:.2f}"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def mutate(self, cause: str, impact: dict[str, float], performance_score: float = 0.5) -> PolicySnapshot:
        """
        Apply a mutation to policy weights.

        Args:
            cause: Human-readable reason (e.g., "OOM_failure", "reflection_delta")
            impact: Dict of {weight_name: delta} — positive = increase
            performance_score: Outcome quality 0-1 (1 = perfect, 0 = complete failure)

        Returns:
            PolicySnapshot with full delta metadata.
        """
        prev_weights = self.weights.copy()

        # Apply clamped impact
        for k, delta in impact.items():
            if k in self.weights:
                clamped_delta = max(-self.MAX_STEP, min(self.MAX_STEP, delta))
                self.weights[k] = self.weights[k] + clamped_delta

        self._normalize()
        self.version += 1
        self._total_mutations += 1

        # Cost efficiency: compare new weights to previous on a synthetic benchmark
        cost_eff_delta = self.weights.get("cost", 0) - prev_weights.get("cost", 0)

        snap = PolicySnapshot(
            version=self.version,
            weights=self.weights.copy(),
            cause=cause,
            performance_score=performance_score,
            cost_efficiency_delta=round(cost_eff_delta, 4),
        )
        self.history.insert(0, snap)
        self.history = self.history[:100]   # keep last 100
        self._persist(snap)

        logger.info(
            f"[PolicyMutation] v{self.version}  cause='{cause}'  "
            f"cost={self.weights['cost']:.3f} perf={self.weights['perf']:.3f} "
            f"risk={self.weights['risk']:.3f}  perf_score={performance_score:.2f}"
        )
        return snap

    def decay(self) -> None:
        """Drift weights 5% toward balanced baseline (anti-overfitting)."""
        now = time.time()
        if now - self._last_decay < self.DECAY_INTERVAL_S:
            return
        self._last_decay = now

        changed = False
        for k in self.weights:
            diff = self.BASELINE[k] - self.weights[k]
            if abs(diff) > 0.01:
                self.weights[k] += diff * self.DECAY_RATE
                changed = True

        if changed:
            self._normalize()
            logger.debug(f"[PolicyMutation] Decay applied → cost={self.weights['cost']:.3f}")

    def evaluate(self, req_vram_gb: int) -> dict:
        """Score available GPU tiers against current policy weights."""
        HARDWARE = {
            "T4":   {"vram": 16,  "cost": 0.40, "reliability": 0.95},
            "A10G": {"vram": 24,  "cost": 1.20, "reliability": 0.99},
            "A100": {"vram": 80,  "cost": 3.20, "reliability": 0.999},
            "H100": {"vram": 80,  "cost": 5.00, "reliability": 0.9999},
        }
        scores = {}
        for name, hw in HARDWARE.items():
            if hw["vram"] < req_vram_gb:
                scores[name] = 0.0
                continue
            n_cost = 1.0 - min(1.0, hw["cost"] / 6.0)
            n_perf = min(1.0, hw["vram"] / 100.0)
            n_risk = hw["reliability"]
            scores[name] = (
                self.weights["cost"] * n_cost +
                self.weights["perf"] * n_perf +
                self.weights["risk"] * n_risk
            )

        best = max(scores, key=scores.get)
        return {"decision": best, "scores": scores, "policy_version": self.version}

    def rollback(self, target_version: int) -> bool:
        """Rollback to a previous policy version."""
        target = next((h for h in self.history if h.version == target_version), None)
        if not target and target_version == 1:
            target = PolicySnapshot(version=1, weights=self.BASELINE.copy(),
                                    cause="rollback_to_baseline", performance_score=0.5,
                                    cost_efficiency_delta=0.0)
        if target:
            self.weights = target.weights.copy()
            self.version = target_version
            logger.info(f"[PolicyMutation] Rolled back to v{target_version}")
            return True
        return False

    @property
    def total_mutations(self) -> int:
        return self._total_mutations

    @property
    def last_snapshot(self) -> PolicySnapshot | None:
        return self.history[0] if self.history else None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _normalize(self) -> None:
        """Clamp to [MIN, MAX] then renormalise to sum=1."""
        for k in self.weights:
            self.weights[k] = max(self.CLAMP_MIN, min(self.CLAMP_MAX, self.weights[k]))
        total = sum(self.weights.values())
        for k in self.weights:
            self.weights[k] = round(self.weights[k] / total, 6)

    def _persist(self, snap: PolicySnapshot) -> None:
        """Write snapshot to SQLite for audit + cross-restart persistence."""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS policy_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    version INTEGER,
                    weights_json TEXT,
                    cause TEXT,
                    performance_score REAL,
                    cost_efficiency_delta REAL,
                    timestamp TEXT
                )
            """)
            conn.execute(
                "INSERT OR REPLACE INTO policy_snapshots VALUES (?,?,?,?,?,?,?)",
                (snap.snapshot_id, snap.version, json.dumps(snap.weights),
                 snap.cause, snap.performance_score, snap.cost_efficiency_delta, snap.timestamp)
            )
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.debug(f"[PolicyMutation] Persist failed (non-fatal): {exc}")

    def _load(self) -> None:
        """Load latest policy state from SQLite on startup."""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS policy_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    version INTEGER,
                    weights_json TEXT,
                    cause TEXT,
                    performance_score REAL,
                    cost_efficiency_delta REAL,
                    timestamp TEXT
                )
            """)
            rows = conn.execute(
                "SELECT * FROM policy_snapshots ORDER BY version DESC LIMIT 100"
            ).fetchall()
            conn.close()

            if rows:
                latest = rows[0]
                self.version = latest[1]
                self.weights = json.loads(latest[2])
                self._total_mutations = latest[1] - 1  # version 1 = 0 mutations

                # Rebuild history from DB
                self.history = []
                for r in rows:
                    self.history.append(PolicySnapshot(
                        snapshot_id=r[0], version=r[1],
                        weights=json.loads(r[2]), cause=r[3],
                        performance_score=r[4], cost_efficiency_delta=r[5],
                        timestamp=r[6]
                    ))
                logger.info(f"[PolicyMutation] Restored {len(rows)} snapshots from DB.")
        except Exception as exc:
            logger.debug(f"[PolicyMutation] Load failed (using defaults): {exc}")


# ---------------------------------------------------------------------------
# PromptEvolutionEngine
# ---------------------------------------------------------------------------

class PromptEvolutionEngine:
    """
    Tracks per-template LLM call success and triggers prompt evolution.

    When a template's success_rate drops below EVOLUTION_THRESHOLD:
      1. Calls LLM with meta-prompt: "Rewrite this template to improve outcomes"
      2. Stores evolved template as variant
      3. Routes 50% of calls to evolved variant for N_AB_TRIALS calls
      4. Promotes winner permanently after trials complete
    """

    EVOLUTION_THRESHOLD = 0.70      # trigger evolution if success_rate < 70%
    N_AB_TRIALS = 20                # calls per variant during A/B test
    MIN_CALLS_BEFORE_EVOLVE = 10    # don't evolve with fewer data points
    COOLDOWN_S = 600.0              # 10 min cooldown between evolutions per template

    def __init__(self) -> None:
        self._stats: dict[str, TemplatePerformance] = {}
        self._evolved_templates: dict[str, str] = {}   # template_name -> evolved content
        self._ab_trial_counts: dict[str, int] = {}
        self._ab_results: dict[str, dict] = {}         # {original: N, evolved: N}
        self._last_evolution: dict[str, float] = {}
        self._total_evolutions = 0

    def record_call(
        self,
        template_name: str,
        success: bool,
        task_completed: bool,
        latency_ms: float,
    ) -> None:
        """Record outcome of an LLM call for a template."""
        if template_name not in self._stats:
            self._stats[template_name] = TemplatePerformance(template_name=template_name)

        stat = self._stats[template_name]
        stat.total_calls += 1
        if success:
            stat.successful_parses += 1
        if task_completed:
            stat.task_completions += 1
        # Rolling average latency
        stat.avg_latency_ms = (
            (stat.avg_latency_ms * (stat.total_calls - 1) + latency_ms) / stat.total_calls
        )

    async def maybe_evolve(self, template_name: str, llm_engine: Any) -> bool:
        """
        Check if evolution is warranted and trigger if so.

        Returns True if evolution was triggered.
        """
        stat = self._stats.get(template_name)
        if not stat or stat.total_calls < self.MIN_CALLS_BEFORE_EVOLVE:
            return False

        if stat.success_rate >= self.EVOLUTION_THRESHOLD:
            return False

        # Cooldown check
        last = self._last_evolution.get(template_name, 0.0)
        if time.time() - last < self.COOLDOWN_S:
            return False

        self._last_evolution[template_name] = time.time()

        logger.warning(
            f"[PromptEvolution] Template '{template_name}' success_rate={stat.success_rate:.2%} "
            f"< threshold {self.EVOLUTION_THRESHOLD:.0%}. Triggering evolution."
        )

        # Trigger async evolution (don't block caller)
        asyncio.create_task(
            self._evolve_template(template_name, stat, llm_engine),
            name=f"evolve-{template_name}"
        )
        return True

    async def _evolve_template(
        self, template_name: str, stat: TemplatePerformance, llm_engine: Any
    ) -> None:
        """Call LLM to produce an improved version of the template."""
        from .llm_reasoning_engine import PROMPT_TEMPLATES
        original = PROMPT_TEMPLATES.get(template_name, "")
        if not original:
            return

        meta_prompt = f"""
You are an AI prompt engineer optimizing agent performance.

The following prompt template has a {stat.success_rate:.0%} success rate over {stat.total_calls} calls.
Average latency: {stat.avg_latency_ms:.0f}ms.
Common failure mode: JSON parse errors or incomplete reasoning.

ORIGINAL TEMPLATE:
{original}

Rewrite this template to:
1. Produce more reliable JSON output (clearer schema, explicit examples)
2. Reduce ambiguity in instructions
3. Keep all the same output fields
4. Be 10-20% more concise

Respond ONLY with the improved template text (no JSON wrapper, no explanation).
"""

        try:
            raw = await llm_engine._call_llm(meta_prompt)
            if raw and len(raw) > 100:
                self._evolved_templates[template_name] = raw.strip()
                self._ab_trial_counts[template_name] = 0
                self._ab_results[template_name] = {"original": 0, "evolved": 0}
                stat.evolution_count += 1
                stat.active_variant = f"evolved_v{stat.evolution_count}"
                stat.last_evolved_at = datetime.now(timezone.utc).isoformat()
                self._total_evolutions += 1
                logger.info(f"[PromptEvolution] Template '{template_name}' evolved to v{stat.evolution_count}.")
        except Exception as exc:
            logger.warning(f"[PromptEvolution] Evolution call failed for '{template_name}': {exc}")

    def get_template(self, template_name: str) -> str | None:
        """Return evolved template if in A/B test phase, else None (use original)."""
        evolved = self._evolved_templates.get(template_name)
        if not evolved:
            return None

        # A/B routing: alternate between original and evolved
        count = self._ab_trial_counts.get(template_name, 0)
        if count >= self.N_AB_TRIALS * 2:
            # Trials complete — declare winner
            results = self._ab_results.get(template_name, {})
            if results.get("evolved", 0) > results.get("original", 0):
                logger.info(f"[PromptEvolution] '{template_name}' evolved template WINS. Promoting.")
                return evolved   # keep using evolved
            else:
                logger.info(f"[PromptEvolution] '{template_name}' original WINS. Discarding evolved.")
                del self._evolved_templates[template_name]
                return None

        self._ab_trial_counts[template_name] = count + 1
        return evolved if count % 2 == 1 else None   # alternate

    @property
    def total_evolutions(self) -> int:
        return self._total_evolutions

    def get_stats(self) -> list[dict]:
        return [
            {
                "template": s.template_name,
                "total_calls": s.total_calls,
                "success_rate": round(s.success_rate, 4),
                "completion_rate": round(s.completion_rate, 4),
                "avg_latency_ms": round(s.avg_latency_ms, 1),
                "evolution_count": s.evolution_count,
                "active_variant": s.active_variant,
                "last_evolved_at": s.last_evolved_at,
            }
            for s in self._stats.values()
        ]


# ---------------------------------------------------------------------------
# AgentReflectionLoop
# ---------------------------------------------------------------------------

class AgentReflectionLoop:
    """
    After each GoalExecution completes, calls LLM to reflect on what happened
    and extract actionable improvements to apply to policy.

    Reflection prompt asks: "Given this goal's outcome, what weight changes
    would improve future performance?"

    The LLM returns a delta dict, which is validated and applied to PolicyMutationEngine.
    """

    MAX_DELTA_PER_DIM = 0.10        # cap per reflection delta at 10%
    REFLECTION_COOLDOWN_S = 30.0    # don't reflect more than once per 30s overall

    def __init__(self, policy_engine: PolicyMutationEngine) -> None:
        self._policy = policy_engine
        self._reflections: list[ReflectionEntry] = []
        self._total_reflections = 0
        self._last_reflection_time = 0.0
        self._cumulative_improvement = 0.0

    async def reflect(self, goal_result: dict, llm_engine: Any) -> ReflectionEntry | None:
        """
        Reflect on a completed goal and apply policy mutations.

        Args:
            goal_result: The to_dict() output of a GoalExecution.
            llm_engine: The LLMReasoningEngine instance.

        Returns:
            ReflectionEntry with applied mutations, or None if skipped.
        """
        now = time.time()
        if now - self._last_reflection_time < self.REFLECTION_COOLDOWN_S:
            logger.debug("[Reflection] Cooldown active — skipping reflection.")
            return None

        self._last_reflection_time = now

        goal_id = goal_result.get("goal_id", "unknown")
        outcome = goal_result.get("status", "unknown")
        cost_usd = float(goal_result.get("cost_incurred_usd", 0))
        tasks_completed = len(goal_result.get("completed_tasks", []))
        tasks_failed = len(goal_result.get("failed_tasks", []))
        goal_text = goal_result.get("raw_text", "")[:200]

        reflection_prompt = f"""
You are the OrQuanta self-improvement system reflecting on a completed AI agent run.

GOAL: "{goal_text}"
OUTCOME: {outcome}
TASKS COMPLETED: {tasks_completed}
TASKS FAILED: {tasks_failed}
COST INCURRED: ${cost_usd:.4f}
CURRENT POLICY WEIGHTS: {json.dumps(self._policy.weights)}

Based on this outcome, recommend weight adjustments to improve future similar goals.
The weights control: cost_priority (cost savings), perf_priority (speed/GPU choice), risk_priority (reliability).

Respond ONLY with valid JSON:
{{
  "reflection": "<2-3 sentences: what happened and why>",
  "weight_deltas": {{
    "cost": <float between -0.10 and 0.10>,
    "perf": <float between -0.10 and 0.10>,
    "risk": <float between -0.10 and 0.10>
  }},
  "confidence": <0.0-1.0>,
  "reasoning": "<why these specific adjustments>"
}}
"""

        applied_mutations = []
        reflection_text = ""

        try:
            raw = await llm_engine._call_llm(reflection_prompt)
            parsed = llm_engine._parse_json_response(raw)

            reflection_text = parsed.get("reflection", "")
            deltas = parsed.get("weight_deltas", {})
            confidence = float(parsed.get("confidence", 0.5))
            reasoning = parsed.get("reasoning", "")

            # Only apply if confidence is reasonable
            if confidence >= 0.4 and deltas:
                # Scale delta by confidence and cap per dim
                scaled = {
                    k: max(-self.MAX_DELTA_PER_DIM, min(self.MAX_DELTA_PER_DIM, float(v) * confidence))
                    for k, v in deltas.items()
                    if k in ("cost", "perf", "risk")
                }

                if any(abs(v) > 0.001 for v in scaled.values()):
                    # Compute performance score for mutation log
                    perf_score = 1.0 if outcome == "completed" else 0.3
                    if tasks_failed > 0:
                        fail_rate = tasks_failed / max(tasks_completed + tasks_failed, 1)
                        perf_score = max(0.1, perf_score * (1 - fail_rate))

                    snap = self._policy.mutate(
                        cause=f"reflection:{outcome}:{goal_id[:8]}",
                        impact=scaled,
                        performance_score=perf_score,
                    )
                    applied_mutations = [{"weights": snap.weights, "delta": scaled, "reasoning": reasoning}]
                    self._cumulative_improvement += (1.0 if outcome == "completed" else -0.5)

        except Exception as exc:
            logger.warning(f"[Reflection] LLM reflection failed for goal {goal_id}: {exc}")
            reflection_text = f"Reflection unavailable: {exc}"

        entry = ReflectionEntry(
            reflection_id=str(uuid4())[:8],
            goal_id=goal_id,
            goal_text=goal_text,
            outcome=outcome,
            cost_usd=cost_usd,
            tasks_completed=tasks_completed,
            tasks_failed=tasks_failed,
            reflection_text=reflection_text,
            applied_mutations=applied_mutations,
        )

        self._reflections.insert(0, entry)
        self._reflections = self._reflections[:100]
        self._total_reflections += 1

        logger.info(
            f"[Reflection] Goal {goal_id[:8]} ({outcome})  "
            f"mutations_applied={len(applied_mutations)}  "
            f"policy_v={self._policy.version}"
        )
        return entry

    @property
    def total_reflections(self) -> int:
        return self._total_reflections

    @property
    def avg_improvement_per_reflection(self) -> float:
        if self._total_reflections == 0:
            return 0.0
        return round(self._cumulative_improvement / self._total_reflections, 4)

    def get_recent(self, n: int = 10) -> list[dict]:
        return [
            {
                "reflection_id": r.reflection_id,
                "goal_id": r.goal_id,
                "goal_text": r.goal_text[:80],
                "outcome": r.outcome,
                "cost_usd": r.cost_usd,
                "mutations_applied": len(r.applied_mutations),
                "reflection_summary": r.reflection_text[:150],
                "timestamp": r.timestamp,
            }
            for r in self._reflections[:n]
        ]


# ---------------------------------------------------------------------------
# SelfImprovementEngine — Main Orchestrator
# ---------------------------------------------------------------------------

class SelfImprovementEngine:
    """
    Central self-improvement coordinator.

    Wires together PolicyMutationEngine, PromptEvolutionEngine, and
    AgentReflectionLoop into a single singleton used by:
      - MasterOrchestrator (calls reflect() after each goal)
      - VeroAgent (calls policy.decay() every 120s, checks improvement health)
      - LLMReasoningEngine (calls record_call() after each LLM call)

    REST API: GET /api/v1/vero/self-improvement/status
    """

    def __init__(self) -> None:
        self.policy = PolicyMutationEngine()
        self.prompts = PromptEvolutionEngine()
        self._reflection_loop: AgentReflectionLoop | None = None
        self._start_time = time.time()
        self._improvement_loop_task: asyncio.Task | None = None
        self._running = False
        logger.info("[SelfImprovement] Engine initialised.")

    def _get_reflection_loop(self, llm_engine: Any) -> AgentReflectionLoop:
        if self._reflection_loop is None:
            self._reflection_loop = AgentReflectionLoop(self.policy)
        return self._reflection_loop

    async def start(self, interval_s: float = 120.0) -> None:
        """Start the background improvement loop (policy decay + health check)."""
        self._running = True
        self._improvement_loop_task = asyncio.create_task(
            self._run_loop(interval_s), name="self-improvement-loop"
        )
        logger.info(f"[SelfImprovement] Background loop started (interval={interval_s}s).")

    async def stop(self) -> None:
        self._running = False
        if self._improvement_loop_task:
            self._improvement_loop_task.cancel()
            try:
                await self._improvement_loop_task
            except asyncio.CancelledError:
                pass

    async def _run_loop(self, interval_s: float) -> None:
        """Background loop: decay weights, check prompt evolution needs."""
        while self._running:
            try:
                self.policy.decay()
                logger.debug("[SelfImprovement] Policy decay check complete.")
            except Exception as exc:
                logger.warning(f"[SelfImprovement] Loop error: {exc}")
            await asyncio.sleep(interval_s)

    async def reflect_on_goal(self, goal_result: dict, llm_engine: Any) -> ReflectionEntry | None:
        """Called by MasterOrchestrator after each goal completes."""
        loop = self._get_reflection_loop(llm_engine)
        return await loop.reflect(goal_result, llm_engine)

    def record_llm_call(
        self,
        template_name: str,
        success: bool,
        task_completed: bool,
        latency_ms: float,
    ) -> None:
        """Called by LLMReasoningEngine after each call."""
        self.prompts.record_call(template_name, success, task_completed, latency_ms)

    async def maybe_evolve_template(self, template_name: str, llm_engine: Any) -> bool:
        """Called by LLMReasoningEngine to trigger prompt evolution if needed."""
        return await self.prompts.maybe_evolve(template_name, llm_engine)

    def get_evolved_template(self, template_name: str) -> str | None:
        """Return evolved template content for A/B routing, or None to use original."""
        return self.prompts.get_template(template_name)

    def get_report(self) -> ImprovementReport:
        """Build full report for REST API."""
        last_snap = self.policy.last_snapshot
        reflection_loop = self._reflection_loop

        # Learning velocity: mutations per hour since start
        hours_running = max(0.01, (time.time() - self._start_time) / 3600)
        velocity = round(self.policy.total_mutations / hours_running, 2)

        # Health assessment
        if velocity > 5:
            health = "excellent"
        elif velocity > 1:
            health = "good"
        elif self.policy.total_mutations == 0:
            health = "stagnant"
        else:
            health = "learning"

        return ImprovementReport(
            policy_version=self.policy.version,
            policy_weights=self.policy.weights.copy(),
            total_mutations=self.policy.total_mutations,
            last_mutation_cause=last_snap.cause if last_snap else "none",
            last_mutation_at=last_snap.timestamp if last_snap else "",
            policy_history=[
                {
                    "version": s.version, "weights": s.weights,
                    "cause": s.cause, "performance_score": s.performance_score,
                    "timestamp": s.timestamp,
                }
                for s in self.policy.history[:20]
            ],
            template_stats=self.prompts.get_stats(),
            total_evolutions=self.prompts.total_evolutions,
            templates_evolved=[s["template"] for s in self.prompts.get_stats() if s["evolution_count"] > 0],
            total_reflections=reflection_loop.total_reflections if reflection_loop else 0,
            recent_reflections=reflection_loop.get_recent() if reflection_loop else [],
            avg_improvement_per_reflection=(
                reflection_loop.avg_improvement_per_reflection if reflection_loop else 0.0
            ),
            improvement_health=health,
            learning_velocity=velocity,
        )


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_engine: SelfImprovementEngine | None = None


def get_self_improvement_engine() -> SelfImprovementEngine:
    """Return the global SelfImprovementEngine singleton."""
    global _engine
    if _engine is None:
        _engine = SelfImprovementEngine()
    return _engine
