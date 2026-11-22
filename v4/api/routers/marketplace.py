# Copyright 2026 OrQuanta — Apache License 2.0
"""
OrQuanta Phase 6H — Marketplace REST API Router.

Endpoints at /api/v1/marketplace/*:

  Assets (unified)
    GET  /assets                    — search/list all assets
    GET  /assets/{id}               — get asset detail
    GET  /assets/{id}/versions      — version history

  Models
    GET  /models                    — list model assets
    GET  /models/{id}               — model detail + deployment info
    POST /models                    — register model asset (publisher)

  Agents
    GET  /agents                    — list agent assets
    GET  /agents/{id}               — agent detail
    POST /agents                    — publish agent (publisher)
    GET  /agents/{id}/executions    — execution history

  MCP Tools
    GET  /tools                     — list MCP server assets
    GET  /tools/{id}                — tool detail
    POST /tools                     — register MCP server (publisher)

  Workflows
    GET  /workflows                 — list workflow assets
    GET  /workflows/{id}            — workflow detail
    POST /workflows                 — publish workflow (publisher)
    POST /workflows/{id}/run        — submit workflow run
    POST /workflows/{id}/runs/{run}/cancel — cancel workflow run

  Publishers
    POST /publishers                — register publisher
    GET  /publishers/{id}           — publisher profile
    GET  /publishers/{id}/analytics — publisher analytics
    GET  /publishers/{id}/assets    — publisher's assets

  Trust
    POST /trust/assess/{id}         — run trust pipeline
    GET  /trust/assessments/{id}    — get assessment
    POST /trust/approve/{id}        — approve assessment
    GET  /trust/assessments         — list all assessments

  Installation
    POST /install/prepare           — prepare installation (steps 1-7)
    POST /install/confirm           — confirm installation (step 8+)
    GET  /install/session/{id}      — get session status
    GET  /installations             — list tenant installations
    POST /installations/{id}/disable
    POST /installations/{id}/uninstall
    POST /installations/{id}/revoke

  Manifests
    POST /manifests/verify          — verify a submitted manifest
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

logger = logging.getLogger("orquanta.api.marketplace")

router = APIRouter(prefix="/api/v1/marketplace", tags=["Marketplace"])

# Lazy imports from marketplace modules (avoid circular)
def _reg():
    from ...marketplace.registry import get_registry
    return get_registry()

def _mm():
    from ...marketplace.model_marketplace import get_model_marketplace
    return get_model_marketplace()

def _am():
    from ...marketplace.agent_marketplace import get_agent_marketplace
    return get_agent_marketplace()

def _mcpm():
    from ...marketplace.mcp_marketplace import get_mcp_marketplace
    return get_mcp_marketplace()

def _wfm():
    from ...marketplace.workflow_marketplace import get_workflow_marketplace
    return get_workflow_marketplace()

def _te():
    from ...marketplace.trust_engine import get_trust_engine
    return get_trust_engine()

def _ie():
    from ...marketplace.installation import get_installation_engine
    return get_installation_engine()

def _pp():
    from ...marketplace.publisher_portal import get_publisher_portal
    return get_publisher_portal()

# Auth dependency
try:
    from ..middleware.auth import get_current_user
except Exception:
    async def get_current_user():  # type: ignore
        return {"sub": "dev-user", "email": "dev@orquanta.com", "role": "user"}


# ---------------------------------------------------------------------------
# Pydantic request schemas
# ---------------------------------------------------------------------------

class PublisherRegisterRequest(BaseModel):
    display_name: str
    email: str
    organisation: Optional[str] = None
    website: Optional[str] = None
    github_handle: Optional[str] = None
    bio: str = ""
    is_commercial: bool = False


class ModelSubmitRequest(BaseModel):
    publisher_id: str
    name: str
    version: str
    description: str
    licence: str
    hf_repo_id: Optional[str] = None
    model_family: Optional[str] = None
    parameter_count: Optional[str] = None
    context_length: Optional[int] = None
    quantisation_options: List[str] = []
    supported_engines: List[str] = []
    min_vram_gb: Optional[float] = None
    tags: List[str] = []


class AgentSubmitRequest(BaseModel):
    publisher_id: str
    name: str
    version: str
    description: str
    licence: str
    required_permissions: List[str]
    required_scopes: List[str]
    model_dependencies: List[str] = []
    tool_dependencies: List[str] = []
    max_spend_usd: float = 10.0
    tags: List[str] = []


class MCPSubmitRequest(BaseModel):
    publisher_id: str
    name: str
    version: str
    description: str
    licence: str
    required_scopes: List[str]
    tools: List[Dict[str, Any]] = []
    is_sandboxed: bool = False
    tags: List[str] = []


class WorkflowSubmitRequest(BaseModel):
    publisher_id: str
    name: str
    version: str
    description: str
    licence: str
    steps: List[Dict[str, Any]]
    required_permissions: List[str] = []
    required_scopes: List[str] = []
    trigger: str = "manual"
    tags: List[str] = []


class WorkflowRunRequest(BaseModel):
    input_params: Dict[str, Any] = {}


class TrustAssessRequest(BaseModel):
    reviewer_id: str


class TrustApproveRequest(BaseModel):
    approver_id: str
    override_status: Optional[str] = None


class InstallPrepareRequest(BaseModel):
    asset_id: str
    tenant_id: str


class InstallConfirmRequest(BaseModel):
    session_id: str
    accepted_permissions: List[str] = []


class ManifestVerifyRequest(BaseModel):
    manifest: Dict[str, Any]
    expected_hash: Optional[str] = None


# ---------------------------------------------------------------------------
# Helper: safe error wrapper
# ---------------------------------------------------------------------------

def _safe(fn):
    try:
        return fn()
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except (ValueError, NotImplementedError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ===========================================================================
# Assets (unified)
# ===========================================================================

@router.get("/assets")
async def search_assets(
    q: str = Query(""),
    asset_type: Optional[str] = Query(None),
    tags: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    current_user: dict = Depends(get_current_user),
):
    from ...marketplace.registry import AssetType as AT
    atype = None
    if asset_type:
        try:
            atype = AT(asset_type.upper())
        except ValueError:
            raise HTTPException(400, f"Unknown asset_type: {asset_type}")
    tag_list = [t.strip() for t in tags.split(",")] if tags else None
    results = _reg().search_assets(
        query=q, asset_type=atype, tags=tag_list,
        published_only=True, limit=limit, offset=offset,
    )
    return {"assets": [a.to_dict() for a in results], "total": len(results)}


@router.get("/assets/{asset_id}")
async def get_asset(asset_id: str, current_user: dict = Depends(get_current_user)):
    asset = _reg().get_asset(asset_id)
    if not asset:
        raise HTTPException(404, f"Asset not found: {asset_id}")
    return asset.to_dict()


@router.get("/assets/{asset_id}/versions")
async def get_asset_versions(asset_id: str, current_user: dict = Depends(get_current_user)):
    asset = _reg().get_asset(asset_id)
    if not asset:
        raise HTTPException(404, f"Asset not found: {asset_id}")
    versions = _reg().get_version_history(asset.name)
    return {"versions": [a.to_dict() for a in versions]}


# ===========================================================================
# Models
# ===========================================================================

@router.get("/models")
async def list_models(
    q: str = Query(""),
    family: Optional[str] = Query(None),
    licence: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    current_user: dict = Depends(get_current_user),
):
    return {"models": _mm().list_models(query=q, family=family, licence=licence, limit=limit)}


@router.get("/models/{asset_id}")
async def get_model(asset_id: str, current_user: dict = Depends(get_current_user)):
    result = _mm().get_model_detail(asset_id)
    if not result:
        raise HTTPException(404, f"Model asset not found: {asset_id}")
    return result


@router.get("/models/{asset_id}/deployment")
async def get_model_deployment_info(asset_id: str, current_user: dict = Depends(get_current_user)):
    return _safe(lambda: _mm().get_deployment_info(asset_id))


@router.post("/models", status_code=201)
async def submit_model(req: ModelSubmitRequest, current_user: dict = Depends(get_current_user)):
    actor_id = current_user.get("sub", "")
    return _safe(lambda: _mm().register_model_asset(
        actor_id=actor_id,
        publisher_id=req.publisher_id,
        name=req.name,
        version=req.version,
        description=req.description,
        licence=req.licence,
        hf_repo_id=req.hf_repo_id,
        model_family=req.model_family,
        parameter_count=req.parameter_count,
        context_length=req.context_length,
        quantisation_options=req.quantisation_options,
        supported_engines=req.supported_engines,
        min_vram_gb=req.min_vram_gb,
        tags=req.tags,
    ))


# ===========================================================================
# Agents
# ===========================================================================

@router.get("/agents")
async def list_agents(
    q: str = Query(""),
    limit: int = Query(50, le=200),
    current_user: dict = Depends(get_current_user),
):
    return {"agents": _am().list_agents(query=q, limit=limit)}


@router.get("/agents/{asset_id}")
async def get_agent(asset_id: str, current_user: dict = Depends(get_current_user)):
    result = _am().get_agent_detail(asset_id)
    if not result:
        raise HTTPException(404, f"Agent asset not found: {asset_id}")
    return result


@router.post("/agents", status_code=201)
async def publish_agent(req: AgentSubmitRequest, current_user: dict = Depends(get_current_user)):
    actor_id = current_user.get("sub", "")
    return _safe(lambda: _am().publish_agent(
        actor_id=actor_id,
        publisher_id=req.publisher_id,
        name=req.name,
        version=req.version,
        description=req.description,
        licence=req.licence,
        required_permissions=req.required_permissions,
        required_scopes=req.required_scopes,
        model_dependencies=req.model_dependencies,
        tool_dependencies=req.tool_dependencies,
        max_spend_usd=req.max_spend_usd,
        tags=req.tags,
    ))


@router.get("/agents/{asset_id}/executions")
async def get_agent_executions(asset_id: str, current_user: dict = Depends(get_current_user)):
    tenant_id = current_user.get("org", current_user.get("sub", ""))
    return {"executions": _am().get_execution_history(asset_id, tenant_id)}


# ===========================================================================
# MCP Tools
# ===========================================================================

@router.get("/tools")
async def list_tools(
    q: str = Query(""),
    limit: int = Query(50, le=200),
    current_user: dict = Depends(get_current_user),
):
    return {"tools": _mcpm().list_mcp_servers(query=q, limit=limit)}


@router.get("/tools/{asset_id}")
async def get_tool(asset_id: str, current_user: dict = Depends(get_current_user)):
    result = _mcpm().get_mcp_detail(asset_id)
    if not result:
        raise HTTPException(404, f"MCP tool asset not found: {asset_id}")
    return result


@router.post("/tools", status_code=201)
async def register_mcp_server(req: MCPSubmitRequest, current_user: dict = Depends(get_current_user)):
    actor_id = current_user.get("sub", "")
    return _safe(lambda: _mcpm().register_mcp_server(
        actor_id=actor_id,
        publisher_id=req.publisher_id,
        name=req.name,
        version=req.version,
        description=req.description,
        licence=req.licence,
        required_scopes=req.required_scopes,
        tools=req.tools,
        is_sandboxed=req.is_sandboxed,
        tags=req.tags,
    ))


# ===========================================================================
# Workflows
# ===========================================================================

@router.get("/workflows")
async def list_workflows(
    q: str = Query(""),
    limit: int = Query(50, le=200),
    current_user: dict = Depends(get_current_user),
):
    return {"workflows": _wfm().list_workflows(query=q, limit=limit)}


@router.get("/workflows/{asset_id}")
async def get_workflow(asset_id: str, current_user: dict = Depends(get_current_user)):
    result = _wfm().get_workflow_detail(asset_id)
    if not result:
        raise HTTPException(404, f"Workflow asset not found: {asset_id}")
    return result


@router.post("/workflows", status_code=201)
async def publish_workflow(req: WorkflowSubmitRequest, current_user: dict = Depends(get_current_user)):
    actor_id = current_user.get("sub", "")
    return _safe(lambda: _wfm().publish_workflow(
        actor_id=actor_id,
        publisher_id=req.publisher_id,
        name=req.name,
        version=req.version,
        description=req.description,
        licence=req.licence,
        steps=req.steps,
        required_permissions=req.required_permissions,
        required_scopes=req.required_scopes,
        trigger=req.trigger,
        tags=req.tags,
    ))


@router.post("/workflows/{asset_id}/run")
async def run_workflow(
    asset_id: str, req: WorkflowRunRequest, current_user: dict = Depends(get_current_user)
):
    actor_id = current_user.get("sub", "")
    tenant_id = current_user.get("org", actor_id)
    return _safe(lambda: _wfm().submit_workflow_run(
        asset_id=asset_id,
        tenant_id=tenant_id,
        submitted_by=actor_id,
        input_params=req.input_params,
    ))


@router.post("/workflows/{asset_id}/runs/{run_id}/cancel")
async def cancel_workflow_run(
    asset_id: str, run_id: str, current_user: dict = Depends(get_current_user)
):
    actor_id = current_user.get("sub", "")
    return _safe(lambda: _wfm().cancel_workflow_run(
        run_id=run_id, asset_id=asset_id, cancelled_by=actor_id
    ))


# ===========================================================================
# Publishers
# ===========================================================================

@router.post("/publishers", status_code=201)
async def register_publisher(req: PublisherRegisterRequest, current_user: dict = Depends(get_current_user)):
    actor_id = current_user.get("sub", "")
    return _safe(lambda: _reg().register_publisher(
        actor_id=actor_id,
        display_name=req.display_name,
        email=req.email,
        organisation=req.organisation,
        website=req.website,
        github_handle=req.github_handle,
        bio=req.bio,
        is_commercial=req.is_commercial,
    ).to_dict())


@router.get("/publishers/{publisher_id}")
async def get_publisher(publisher_id: str, current_user: dict = Depends(get_current_user)):
    pub = _reg().get_publisher(publisher_id)
    if not pub:
        raise HTTPException(404, f"Publisher not found: {publisher_id}")
    return pub.to_dict()


@router.get("/publishers/{publisher_id}/analytics")
async def get_publisher_analytics(publisher_id: str, current_user: dict = Depends(get_current_user)):
    actor_id = current_user.get("sub", "")
    return _safe(lambda: _pp().get_publisher_analytics(publisher_id, actor_id).to_dict())


@router.get("/publishers/{publisher_id}/assets")
async def get_publisher_assets(publisher_id: str, current_user: dict = Depends(get_current_user)):
    return {"assets": _pp().get_submission_history(publisher_id)}


# ===========================================================================
# Trust Engine
# ===========================================================================

@router.post("/trust/assess/{asset_id}")
async def run_trust_assessment(
    asset_id: str, req: TrustAssessRequest, current_user: dict = Depends(get_current_user)
):
    return _safe(lambda: _te().run_trust_pipeline(
        asset_id=asset_id, reviewer_id=req.reviewer_id
    ).to_dict())


@router.get("/trust/assessments/{assessment_id}")
async def get_trust_assessment(assessment_id: str, current_user: dict = Depends(get_current_user)):
    result = _te().get_assessment(assessment_id)
    if not result:
        raise HTTPException(404, f"Assessment not found: {assessment_id}")
    return result.to_dict()


@router.get("/trust/assets/{asset_id}/latest")
async def get_latest_assessment(asset_id: str, current_user: dict = Depends(get_current_user)):
    result = _te().get_latest_assessment(asset_id)
    if not result:
        raise HTTPException(404, f"No assessment found for asset: {asset_id}")
    return result.to_dict()


@router.post("/trust/approve/{assessment_id}")
async def approve_trust_assessment(
    assessment_id: str, req: TrustApproveRequest, current_user: dict = Depends(get_current_user)
):
    from ...marketplace.registry import TrustStatus as TS
    override = None
    if req.override_status:
        try:
            override = TS(req.override_status)
        except ValueError:
            raise HTTPException(400, f"Invalid trust status: {req.override_status}")
    return _safe(lambda: _te().approve_assessment(
        assessment_id=assessment_id,
        approver_id=req.approver_id,
        override_status=override,
    ).to_dict())


@router.get("/trust/assessments")
async def list_trust_assessments(current_user: dict = Depends(get_current_user)):
    return {"assessments": [a.to_dict() for a in _te().list_assessments()]}


# ===========================================================================
# Installation
# ===========================================================================

@router.post("/install/prepare")
async def prepare_installation(req: InstallPrepareRequest, current_user: dict = Depends(get_current_user)):
    actor_id = current_user.get("sub", "")
    return _safe(lambda: _ie().prepare_installation(
        asset_id=req.asset_id,
        tenant_id=req.tenant_id,
        requesting_user=actor_id,
    ).to_dict())


@router.post("/install/confirm")
async def confirm_installation(req: InstallConfirmRequest, current_user: dict = Depends(get_current_user)):
    actor_id = current_user.get("sub", "")
    return _safe(lambda: _ie().confirm_installation(
        session_id=req.session_id,
        approving_user=actor_id,
        accepted_permissions=req.accepted_permissions,
    ).to_dict())


@router.get("/install/session/{session_id}")
async def get_install_session(session_id: str, current_user: dict = Depends(get_current_user)):
    session = _ie().get_session(session_id)
    if not session:
        raise HTTPException(404, f"Session not found: {session_id}")
    return session.to_dict()


@router.get("/installations")
async def list_installations(
    status_filter: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    tenant_id = current_user.get("org", current_user.get("sub", ""))
    recs = _reg().list_installations(tenant_id, status_filter=status_filter)
    return {"installations": [r.to_dict() for r in recs]}


@router.post("/installations/{installation_id}/disable")
async def disable_installation(installation_id: str, current_user: dict = Depends(get_current_user)):
    actor_id = current_user.get("sub", "")
    return _safe(lambda: _ie().disable_installation(installation_id, actor_id).to_dict())


@router.post("/installations/{installation_id}/uninstall")
async def uninstall(installation_id: str, current_user: dict = Depends(get_current_user)):
    actor_id = current_user.get("sub", "")
    return _safe(lambda: _ie().uninstall(installation_id, actor_id).to_dict())


@router.post("/installations/{installation_id}/revoke")
async def revoke_installation(installation_id: str, current_user: dict = Depends(get_current_user)):
    actor_id = current_user.get("sub", "")
    return _safe(lambda: _ie().revoke_installation(installation_id, actor_id).to_dict())


# ===========================================================================
# Manifests
# ===========================================================================

@router.post("/manifests/verify")
async def verify_manifest_endpoint(req: ManifestVerifyRequest, current_user: dict = Depends(get_current_user)):
    from ...marketplace.manifest import AssetManifest, verify_manifest, ManifestDependency
    from ...marketplace.manifest import ManifestResourceRequirements
    try:
        md = req.manifest
        manifest = AssetManifest(
            manifest_id=md.get("manifest_id", ""),
            schema_version=md.get("schema_version", "1.0"),
            asset_name=md.get("asset_name", ""),
            asset_version=md.get("asset_version", ""),
            asset_type=md.get("asset_type", ""),
            publisher_id=md.get("publisher_id", ""),
            publisher_display_name=md.get("publisher_display_name", ""),
            licence=md.get("licence", "UNKNOWN"),
            manifest_hash=md.get("manifest_hash"),
            signature=md.get("signature"),
            content_hash=md.get("content_hash"),
        )
        result = verify_manifest(manifest, expected_hash=req.expected_hash)
        return {
            "is_valid": result.is_valid,
            "hash_match": result.hash_match,
            "signature_verified": result.signature_verified,
            "errors": result.errors,
            "warnings": result.warnings,
            "disclaimer": result.disclaimer,
        }
    except Exception as exc:
        raise HTTPException(400, f"Manifest parsing error: {exc}")


# ===========================================================================
# Overview / home
# ===========================================================================

@router.get("/overview")
async def marketplace_overview(current_user: dict = Depends(get_current_user)):
    """Return summary stats for the marketplace home page."""
    from ...marketplace.registry import AssetType as AT, PublicationStatus as PS
    all_assets = _reg().list_assets(published_only=True)
    return {
        "total_assets": len(all_assets),
        "models": len([a for a in all_assets if a.asset_type == AT.MODEL]),
        "agents": len([a for a in all_assets if a.asset_type == AT.AGENT]),
        "tools": len([a for a in all_assets if a.asset_type == AT.MCP_TOOL]),
        "workflows": len([a for a in all_assets if a.asset_type == AT.WORKFLOW]),
        "featured": [a.to_dict() for a in all_assets if a.is_featured][:6],
        "demo_data_note": (
            "Featured assets include demo entries seeded at startup. "
            "Demo assets are clearly marked with is_demo=true."
        ),
    }
