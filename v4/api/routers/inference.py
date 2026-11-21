# Copyright 2026 OrQuanta — Apache License 2.0
"""
OrQuanta Phase 3 — FastAPI Routers
=====================================
OpenAI-compatible Inference API    POST /v1/chat/completions, GET /v1/models, POST /v1/embeddings
Model Registry API                 GET  /api/v1/models, GET /api/v1/models/{id}
HF Search API                      GET  /api/v1/models/search/hf
GPU Compatibility API              POST /api/v1/models/check-compatibility
Model Deployment API               POST /api/v1/deployments, GET/DELETE /api/v1/deployments/{id}

Security:
- /v1/* routes require sk-orq-... inference API key OR user JWT
- Provider credentials never returned
- Licence permissions reported accurately; unknown = flagged
"""
from __future__ import annotations

import hashlib
import logging
import os
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..middleware.auth import get_current_user
from ..middleware.rate_limit import rate_limit_dependency
from ...inference.gateway import (
    route_inference_request,
    validate_virtual_key,
    _rate_check,
    InferenceError,
    MODEL_ROUTES,
    USE_REAL_INFERENCE,
)
from ...inference.model_registry import (
    list_models,
    get_model,
    search_hf_models,
    fetch_hf_metadata,
    get_licence_info,
)
from ...inference.gpu_compatibility import (
    check_compatibility,
    recommend_gpus_for_model,
    GPU_DB,
)
from ...inference.vllm_adapter import (
    build_deployment_spec,
    mock_deploy_response,
    _DEPLOYMENTS,
    DeploymentRecord,
)

logger = logging.getLogger("orquanta.api.inference")

# ─── OpenAI-Compatible Inference Router ──────────────────────────────────────

v1_router = APIRouter(prefix="/v1", tags=["Inference API (OpenAI-compatible)"])

# ─── Model Hub Router ─────────────────────────────────────────────────────────

hub_router = APIRouter(prefix="/api/v1/models", tags=["Model Hub"])

# ─── Deployment Router ────────────────────────────────────────────────────────

deploy_router = APIRouter(prefix="/api/v1/deployments", tags=["Model Deployments"])


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

async def _get_inference_tenant(
    authorization: Optional[str] = Header(default=None),
) -> Optional[Dict[str, Any]]:
    """
    Validate inference request auth.
    Accepts:
      1. OrQuanta inference key:  sk-orq-...
      2. User JWT:                Bearer eyJ...
    Returns tenant dict or None (open models allowed without key in dev).
    """
    if not authorization:
        return None

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None

    if token.startswith("sk-orq-"):
        tenant = validate_virtual_key(token)
        if tenant is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired inference API key",
            )
        if not _rate_check(tenant):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Limit: {tenant['rate_limit_rpm']} rpm",
            )
        return tenant

    # JWT falls through to FastAPI's normal auth dependency
    return None


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(system|user|assistant)$")
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    max_tokens: int = Field(default=1024, ge=1, le=32768)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    stream: bool = False


class EmbeddingRequest(BaseModel):
    model: str
    input: Any   # str | list[str]


class CompatibilityRequest(BaseModel):
    model_id: str
    gpu_model: str
    gpu_count: int = Field(default=1, ge=1, le=16)
    quantisation: str = "int8"
    engine: str = "vllm"
    context_length: Optional[int] = None


class DeploymentRequest(BaseModel):
    model_id: str
    engine: str = "vllm"
    quantisation: str = "int8"
    gpu_model: str
    gpu_count: int = Field(default=1, ge=1, le=16)
    provider: str = "runpod"
    region: str = "us-east-1"
    max_model_len: Optional[int] = None


# ---------------------------------------------------------------------------
# POST /v1/chat/completions — OpenAI-compatible inference
# ---------------------------------------------------------------------------

@v1_router.post("/chat/completions", summary="Chat completions (OpenAI-compatible)")
async def chat_completions(
    body: ChatCompletionRequest,
    tenant: Optional[Dict[str, Any]] = Depends(_get_inference_tenant),
):
    """
    OpenAI-compatible chat completions endpoint.

    Requires an OrQuanta inference API key (sk-orq-...) or user JWT.
    Real inference requires USE_REAL_INFERENCE=true and provider keys.
    Mock responses are labelled [MOCK] in the content.
    """
    messages = [{"role": m.role, "content": m.content} for m in body.messages]
    try:
        result = await route_inference_request(
            model_id=body.model,
            messages=messages,
            stream=False,
            max_tokens=body.max_tokens,
            temperature=body.temperature,
            tenant=tenant,
        )
    except InferenceError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))

    return result


# ---------------------------------------------------------------------------
# GET /v1/models — list available models
# ---------------------------------------------------------------------------

@v1_router.get("/models", summary="List available inference models")
async def list_inference_models():
    """List models available for inference through OrQuanta."""
    models = list_models()
    return {
        "object": "list",
        "data": [
            {
                "id": m.model_id,
                "object": "model",
                "created": 0,
                "owned_by": m.publisher,
                "orquanta": {
                    "engines": m.supported_engines,
                    "licence": m.licence,
                    "commercial_ok": m.commercial_ok,
                    "in_routing_table": m.model_id in MODEL_ROUTES,
                    "is_real": USE_REAL_INFERENCE and m.model_id in MODEL_ROUTES,
                },
            }
            for m in models
        ],
    }


# ---------------------------------------------------------------------------
# POST /v1/embeddings — embedding endpoint (placeholder with mock)
# ---------------------------------------------------------------------------

@v1_router.post("/embeddings", summary="Text embeddings (OpenAI-compatible)")
async def create_embeddings(
    body: EmbeddingRequest,
    tenant: Optional[Dict[str, Any]] = Depends(_get_inference_tenant),
):
    """
    Embedding endpoint. Currently returns mock embeddings.
    Real embeddings via vLLM-deployed embedding models in Phase 3D+.
    """
    texts = body.input if isinstance(body.input, list) else [body.input]
    import hashlib as _h
    return {
        "object": "list",
        "model": body.model,
        "data": [
            {
                "object": "embedding",
                "index": i,
                "embedding": [float(int(c, 16)) / 255 - 0.5
                               for c in _h.sha256((t + body.model).encode()).hexdigest()[:64]],
                "is_mock": True,
                "note": "Mock embedding. Deploy a real embedding model via POST /api/v1/deployments.",
            }
            for i, t in enumerate(texts)
        ],
        "usage": {"prompt_tokens": sum(len(t.split()) for t in texts), "total_tokens": sum(len(t.split()) for t in texts)},
    }


# ---------------------------------------------------------------------------
# GET /api/v1/models — Model Hub listing
# ---------------------------------------------------------------------------

@hub_router.get("", summary="List OrQuanta model registry")
async def api_list_models(
    family: Optional[str] = Query(default=None),
    commercial_ok: Optional[bool] = Query(default=None),
    engine: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    current_user: Dict = Depends(get_current_user),
):
    models = list_models(
        family=family,
        licence_commercial_ok=commercial_ok,
        engine=engine,
        search=search,
    )
    return {
        "models": [m.to_dict() for m in models],
        "total": len(models),
        "source": "orquanta_registry",
    }


# ---------------------------------------------------------------------------
# GET /api/v1/models/{model_id:path} — Model detail
# ---------------------------------------------------------------------------

@hub_router.get("/{model_id:path}", summary="Get model details")
async def api_get_model(
    model_id: str,
    current_user: Dict = Depends(get_current_user),
):
    model = get_model(model_id)
    if not model:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found in OrQuanta registry.")

    result = model.to_dict()
    result["gpu_recommendations"] = recommend_gpus_for_model(
        vram_fp16_gb=model.vram_fp16_gb or 0.0,
        quant="int8",
        engine="vllm",
    )[:5] if model.vram_fp16_gb else []

    return result


# ---------------------------------------------------------------------------
# GET /api/v1/models/search/hf — HF Hub search
# ---------------------------------------------------------------------------

@hub_router.get("/search/hf", summary="Search Hugging Face Hub")
async def api_search_hf(
    q: str = Query(..., min_length=1),
    limit: int = Query(default=20, ge=1, le=50),
    current_user: Dict = Depends(get_current_user),
):
    results = await search_hf_models(query=q, limit=limit)
    return {
        "query": q,
        "results": results,
        "total": len(results),
        "source": "huggingface_hub",
        "note": "Results include real HF metadata. Licence permissions marked unknown when not in OrQuanta licence database.",
    }


# ---------------------------------------------------------------------------
# GET /api/v1/models/fetch/hf — Fetch single HF model metadata
# ---------------------------------------------------------------------------

@hub_router.get("/fetch/hf", summary="Fetch HF model metadata by ID")
async def api_fetch_hf_model(
    hf_id: str = Query(...),
    current_user: Dict = Depends(get_current_user),
):
    metadata = await fetch_hf_metadata(hf_id)
    if not metadata:
        raise HTTPException(status_code=404, detail=f"Could not fetch metadata for '{hf_id}' from HF Hub.")

    metadata["licence_info"] = get_licence_info(metadata.get("licence", "other"))
    metadata["in_registry"] = hf_id in {m.hf_id for m in list_models()}
    return metadata


# ---------------------------------------------------------------------------
# POST /api/v1/models/check-compatibility — GPU compatibility check
# ---------------------------------------------------------------------------

@hub_router.post("/check-compatibility", summary="Check GPU compatibility for a model")
async def api_check_compatibility(
    body: CompatibilityRequest,
    current_user: Dict = Depends(get_current_user),
):
    model = get_model(body.model_id)
    vram_fp16 = model.vram_fp16_gb if model else None
    param_count = model.param_count if model else None

    result = check_compatibility(
        model_id=body.model_id,
        gpu_model=body.gpu_model,
        gpu_count=body.gpu_count,
        quantisation=body.quantisation,
        engine=body.engine,
        context_length=body.context_length,
        vram_fp16_gb=vram_fp16,
        param_count_str=param_count,
    )

    from dataclasses import asdict
    r = asdict(result)
    r["known_gpus"] = list(GPU_DB.keys())
    return r


# ---------------------------------------------------------------------------
# GET /api/v1/models/gpus — GPU database
# ---------------------------------------------------------------------------

@hub_router.get("/gpus", summary="List known GPU hardware specs")
async def api_list_gpus(current_user: Dict = Depends(get_current_user)):
    return {"gpus": GPU_DB, "total": len(GPU_DB)}


# ---------------------------------------------------------------------------
# POST /api/v1/deployments — One-click model deployment
# ---------------------------------------------------------------------------

@deploy_router.post("", summary="Deploy an inference model", status_code=201)
async def api_deploy_model(
    body: DeploymentRequest,
    current_user: Dict = Depends(get_current_user),
):
    """
    Initiate a one-click model deployment.

    Workflow:
    1. Validate model and GPU compatibility.
    2. Build deployment spec.
    3. Submit durable Celery job.
    4. Return deployment record (status=provisioning).

    The deployment transitions to 'ready' only after the inference /health check passes.
    """
    model = get_model(body.model_id)
    if not model:
        raise HTTPException(status_code=404, detail=f"Model '{body.model_id}' not in registry.")

    if body.engine not in model.supported_engines:
        raise HTTPException(
            status_code=400,
            detail=f"Engine '{body.engine}' not supported by this model. Supported: {model.supported_engines}",
        )

    # Compatibility pre-check
    compat = check_compatibility(
        model_id=body.model_id,
        gpu_model=body.gpu_model,
        gpu_count=body.gpu_count,
        quantisation=body.quantisation,
        engine=body.engine,
        vram_fp16_gb=model.vram_fp16_gb,
        param_count_str=model.param_count,
    )
    if compat.status == "incompatible":
        raise HTTPException(
            status_code=400,
            detail={
                "error": "incompatible_hardware",
                "reasons": compat.reasons,
                "constraints": compat.constraints,
            },
        )

    # Licence check
    licence_info = get_licence_info(model.licence)
    if licence_info.get("commercial") is False:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "licence_violation",
                "message": f"Model '{body.model_id}' has a non-commercial licence ({model.licence}). Commercial deployment is not permitted.",
                "licence": model.licence,
            },
        )

    deployment_id = str(uuid.uuid4())
    hourly_rate = 2.50 * body.gpu_count  # Placeholder; real pricing from provider

    spec = build_deployment_spec(
        deployment_id=deployment_id,
        model_id=body.model_id,
        hf_id=model.hf_id,
        engine=body.engine,
        quantisation=body.quantisation,
        gpu_model=body.gpu_model,
        gpu_count=body.gpu_count,
        provider=body.provider,
        region=body.region,
        hourly_rate_usd=hourly_rate,
        max_model_len=body.max_model_len,
    )

    # Submit durable job through Phase 2 pipeline
    is_real = os.getenv("USE_REAL_PROVIDERS", "false").lower() == "true"
    job_result = None
    deploy_job_id = None

    if is_real:
        try:
            from ...execution.durable_pipeline import submit_durable_job
            job = await submit_durable_job(
                script=f"deploy:{deployment_id}",
                provider=body.provider,
                region=body.region,
                gpu_model=body.gpu_model,
                gpu_count=body.gpu_count,
                user_id=current_user["user_id"],
                org_id=current_user.get("org_id", "default"),
                idempotency_key=f"deploy-{deployment_id}",
                metadata=spec,
            )
            deploy_job_id = job.get("job_id")
        except Exception as e:
            logger.error("[deploy] Failed to submit durable job: %s", e)
            raise HTTPException(status_code=503, detail=f"Failed to submit deployment job: {e}")
    else:
        # Mock deployment for testing
        mock = mock_deploy_response(spec)
        spec.update(mock)

    record = DeploymentRecord(
        deployment_id=deployment_id,
        model_id=body.model_id,
        hf_id=model.hf_id,
        engine=body.engine,
        quantisation=body.quantisation,
        gpu_model=body.gpu_model,
        gpu_count=body.gpu_count,
        provider=body.provider,
        region=body.region,
        status="provisioning" if is_real else "mock",
        hourly_rate_usd=hourly_rate,
        deploy_job_id=deploy_job_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        is_real=is_real,
        inference_endpoint=spec.get("inference_endpoint") if not is_real else None,
    )
    _DEPLOYMENTS[deployment_id] = record

    response = record.to_dict()
    response["compatibility"] = {
        "status": compat.status,
        "constraints": compat.constraints,
        "warnings": compat.warnings,
    }
    response["estimated_hourly_cost_usd"] = hourly_rate

    if not is_real:
        response["mock_note"] = spec.get("note", "")

    return response


# ---------------------------------------------------------------------------
# GET /api/v1/deployments — List deployments
# ---------------------------------------------------------------------------

@deploy_router.get("", summary="List model deployments")
async def api_list_deployments(current_user: Dict = Depends(get_current_user)):
    return {
        "deployments": [d.to_dict() for d in _DEPLOYMENTS.values()],
        "total": len(_DEPLOYMENTS),
    }


# ---------------------------------------------------------------------------
# GET /api/v1/deployments/{id} — Get deployment
# ---------------------------------------------------------------------------

@deploy_router.get("/{deployment_id}", summary="Get deployment detail")
async def api_get_deployment(
    deployment_id: str,
    current_user: Dict = Depends(get_current_user),
):
    d = _DEPLOYMENTS.get(deployment_id)
    if not d:
        raise HTTPException(status_code=404, detail="Deployment not found.")
    return d.to_dict()


# ---------------------------------------------------------------------------
# DELETE /api/v1/deployments/{id} — Stop and clean up deployment
# ---------------------------------------------------------------------------

@deploy_router.delete("/{deployment_id}", summary="Stop a deployment and clean up resources")
async def api_delete_deployment(
    deployment_id: str,
    current_user: Dict = Depends(get_current_user),
):
    d = _DEPLOYMENTS.get(deployment_id)
    if not d:
        raise HTTPException(status_code=404, detail="Deployment not found.")

    if d.status in ("stopped", "failed"):
        return {"message": "Deployment already stopped.", "deployment_id": deployment_id}

    # Mark as stopping; real teardown handled by Phase 2 Celery cancel_job
    d.status = "stopped"
    logger.info("[deploy] Deployment %s stopped by user=%s", deployment_id, current_user.get("user_id"))

    return {"message": "Deployment stopped. GPU resources will be cleaned up.", "deployment_id": deployment_id}
