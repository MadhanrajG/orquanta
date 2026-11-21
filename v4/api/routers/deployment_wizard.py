# Copyright 2026 OrQuanta — Apache License 2.0
# Copyright 2024 OrQuanta Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
OrQuanta Phase 3F — Deployment Wizard Backend API.

5-step wizard: model → engine → provider → review → deploy.
Session is tenant-isolated: only the creating user may advance steps.
"""

from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

wizard_router = APIRouter(prefix="/api/v1/wizard", tags=["deployment-wizard"])

# ---------------------------------------------------------------------------
# Session state machine
# ---------------------------------------------------------------------------

WIZARD_STEPS = ["model", "engine", "provider", "review", "deploy"]


@dataclass
class WizardSession:
    session_id: str
    user_id: str
    step: int = 1               # 1-based; 5 = deploy
    status: str = "active"      # active | completed | cancelled | expired
    # Step data
    model_id: Optional[str] = None
    engine: Optional[str] = None
    quantisation: Optional[str] = None
    gpu_model: Optional[str] = None
    gpu_count: int = 1
    provider: Optional[str] = None
    region: Optional[str] = None
    compatibility_result: Optional[Dict] = None
    cost_estimate_usd: Optional[float] = None
    governance_decision: Optional[Dict] = None
    deployment_id: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.datetime.utcnow().isoformat() + "Z")
    expires_at: str = field(default_factory=lambda: (
        datetime.datetime.utcnow() + datetime.timedelta(hours=2)
    ).isoformat() + "Z")
    updated_at: str = field(default_factory=lambda: datetime.datetime.utcnow().isoformat() + "Z")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def touch(self):
        self.updated_at = datetime.datetime.utcnow().isoformat() + "Z"

    def is_expired(self) -> bool:
        try:
            exp = datetime.datetime.fromisoformat(self.expires_at.rstrip("Z"))
            return datetime.datetime.utcnow() > exp
        except Exception:
            return False


# In-memory session store (Phase 4 migrates to DB)
_SESSIONS: Dict[str, WizardSession] = {}


# ---------------------------------------------------------------------------
# Auth dependency (compatible with existing auth pattern)
# ---------------------------------------------------------------------------

def _get_current_user(request: Any = None) -> Dict[str, Any]:
    """
    Lightweight auth stub compatible with existing JWT middleware.
    In production the existing verify_token dependency populates this.
    """
    return {"user_id": "demo-user", "tenant_id": "default", "role": "user"}


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class StepModelRequest(BaseModel):
    model_id: str


class StepEngineRequest(BaseModel):
    engine: str
    quantisation: str = "none"
    gpu_model: str = "unknown"
    gpu_count: int = 1


class StepProviderRequest(BaseModel):
    provider: str
    region: str = "us-east-1"


class StepReviewRequest(BaseModel):
    confirm: bool = True


class StepDeployRequest(BaseModel):
    confirmed: bool  # Must be explicitly True — no auto-deploy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_session(session_id: str, current_user: Dict) -> WizardSession:
    sess = _SESSIONS.get(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Wizard session not found")
    if sess.user_id != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="Access denied: session belongs to another user")
    if sess.is_expired():
        sess.status = "expired"
        raise HTTPException(status_code=410, detail="Wizard session has expired")
    if sess.status == "cancelled":
        raise HTTPException(status_code=409, detail="Session was cancelled")
    return sess


def _require_step(sess: WizardSession, required_step: int):
    """Ensure wizard steps are taken in order."""
    if sess.step < required_step:
        raise HTTPException(
            status_code=409,
            detail=f"Step {required_step} requires step {required_step - 1} to be completed first (current step: {sess.step})"
        )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@wizard_router.post("/sessions", status_code=201)
def create_session(current_user: Dict = Depends(_get_current_user)):
    sid = str(uuid.uuid4())
    sess = WizardSession(session_id=sid, user_id=current_user["user_id"])
    _SESSIONS[sid] = sess
    return sess.to_dict()


@wizard_router.get("/sessions/{session_id}")
def get_session(session_id: str, current_user: Dict = Depends(_get_current_user)):
    sess = _get_session(session_id, current_user)
    return sess.to_dict()


@wizard_router.post("/sessions/{session_id}/step/model")
def step_model(session_id: str, body: StepModelRequest, current_user: Dict = Depends(_get_current_user)):
    sess = _get_session(session_id, current_user)
    # Validate model exists in registry
    try:
        from inference.model_registry import _REGISTRY
        if body.model_id not in _REGISTRY:
            raise HTTPException(status_code=422, detail=f"Model '{body.model_id}' not found in registry")
    except ImportError:
        pass  # Registry not available; allow model_id pass-through

    sess.model_id = body.model_id
    sess.step = max(sess.step, 2)
    sess.touch()
    return sess.to_dict()


@wizard_router.post("/sessions/{session_id}/step/engine")
def step_engine(session_id: str, body: StepEngineRequest, current_user: Dict = Depends(_get_current_user)):
    sess = _get_session(session_id, current_user)
    _require_step(sess, 2)

    # Run compatibility check
    compat_result: Dict[str, Any] = {"compatible": True, "notes": [], "is_mock": True}
    try:
        from inference.gpu_compatibility import GPUCompatibilityEngine
        engine = GPUCompatibilityEngine()
        if sess.model_id:
            result = engine.check_compatibility(sess.model_id, body.gpu_model, body.quantisation)
            compat_result = {
                "compatible": result.get("compatible", True),
                "notes": result.get("notes", []),
                "vram_required_gb": result.get("vram_required_gb"),
                "vram_available_gb": result.get("vram_available_gb"),
                "is_mock": False,
            }
    except Exception as exc:
        compat_result["notes"].append(f"Compatibility check unavailable: {exc}")

    sess.engine = body.engine
    sess.quantisation = body.quantisation
    sess.gpu_model = body.gpu_model
    sess.gpu_count = body.gpu_count
    sess.compatibility_result = compat_result
    sess.step = max(sess.step, 3)
    sess.touch()
    return sess.to_dict()


@wizard_router.post("/sessions/{session_id}/step/provider")
def step_provider(session_id: str, body: StepProviderRequest, current_user: Dict = Depends(_get_current_user)):
    sess = _get_session(session_id, current_user)
    _require_step(sess, 3)

    # Compute cost estimate
    gpu_hour_rates = {
        "runpod": 0.69, "lambda": 1.10, "aws": 2.50,
        "gcp": 2.20, "azure": 2.35, "coreweave": 1.75,
    }
    rate = gpu_hour_rates.get(body.provider.lower(), 1.50)
    cost_estimate = round(rate * sess.gpu_count, 4)  # per GPU-hour

    sess.provider = body.provider
    sess.region = body.region
    sess.cost_estimate_usd = cost_estimate
    sess.step = max(sess.step, 4)
    sess.touch()
    return {**sess.to_dict(), "cost_estimate_per_gpu_hour_usd": cost_estimate}


@wizard_router.post("/sessions/{session_id}/step/review")
def step_review(session_id: str, body: StepReviewRequest, current_user: Dict = Depends(_get_current_user)):
    sess = _get_session(session_id, current_user)
    _require_step(sess, 4)

    # Run governance evaluation
    governance_result: Dict[str, Any] = {
        "decision": "APPROVED",
        "reasons": ["No governance engine available; default allow."],
        "approver_required": False,
        "is_mock": True,
    }
    try:
        from inference.governance import GovernanceEngine, DeploymentRequest as GovReq
        gov = GovernanceEngine()
        req = GovReq(
            model_id=sess.model_id or "",
            engine=sess.engine or "",
            quantisation=sess.quantisation or "none",
            gpu_model=sess.gpu_model or "unknown",
            gpu_count=sess.gpu_count,
            provider=sess.provider or "unknown",
            region=sess.region or "unknown",
            requester_user_id=current_user["user_id"],
            tenant_id=current_user.get("tenant_id", "default"),
        )
        evaluation = gov.evaluate_deployment(req)
        governance_result = {
            "decision": evaluation.decision,
            "reasons": evaluation.reasons,
            "approver_required": evaluation.decision == "REQUIRES_REVIEW",
            "policy_id": evaluation.policy_id,
            "is_mock": False,
        }
    except Exception as exc:
        governance_result["reasons"].append(f"Governance check error: {exc}")

    sess.governance_decision = governance_result
    sess.step = max(sess.step, 5)
    sess.touch()
    return sess.to_dict()


@wizard_router.post("/sessions/{session_id}/step/deploy")
def step_deploy(session_id: str, body: StepDeployRequest, current_user: Dict = Depends(_get_current_user)):
    sess = _get_session(session_id, current_user)
    _require_step(sess, 5)

    # Explicit user confirmation required — never auto-deploy
    if not body.confirmed:
        raise HTTPException(status_code=409, detail="Deploy step requires confirmed=true")

    # Governance gate
    if sess.governance_decision:
        decision = sess.governance_decision.get("decision", "APPROVED")
        if decision == "BLOCKED":
            raise HTTPException(status_code=403, detail="Deployment blocked by governance policy")

    # Tenant isolation: only the session owner may deploy
    if sess.user_id != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="Tenant isolation: deploy denied")

    # Submit deployment (integrate with existing durable job engine if available)
    deployment_id = str(uuid.uuid4())
    is_mock = True
    try:
        from api.routers.inference import _start_deployment_internal
        result = _start_deployment_internal(
            model_id=sess.model_id,
            engine=sess.engine,
            gpu_model=sess.gpu_model,
            gpu_count=sess.gpu_count,
            provider=sess.provider,
        )
        deployment_id = result.get("deployment_id", deployment_id)
        is_mock = result.get("is_mock", True)
    except Exception:
        pass  # Deployment engine not yet wired; use mock ID

    sess.deployment_id = deployment_id
    sess.status = "completed"
    sess.touch()

    return {
        **sess.to_dict(),
        "deployment_id": deployment_id,
        "is_mock": is_mock,
        "message": "Deployment submitted. Monitor status via /api/v1/deployments/{deployment_id}"
        if not is_mock else "Mock deployment created (no live GPU allocated).",
    }


@wizard_router.delete("/sessions/{session_id}", status_code=204)
def cancel_session(session_id: str, current_user: Dict = Depends(_get_current_user)):
    sess = _get_session(session_id, current_user)
    sess.status = "cancelled"
    sess.touch()
    return None
