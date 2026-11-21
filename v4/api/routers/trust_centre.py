# Copyright 2026 OrQuanta — Apache License 2.0
"""
OrQuanta Phase 4 — AI Trust Centre API Router.

Provides all Phase 4 endpoints:

Policy Engine:
  GET  /api/v1/trust/policies              — list policies
  POST /api/v1/trust/policies              — create policy
  POST /api/v1/trust/policies/evaluate     — evaluate a policy decision
  DELETE /api/v1/trust/policies/{id}       — disable policy

IAM:
  POST /api/v1/trust/identities            — create identity
  GET  /api/v1/trust/identities            — list identities
  GET  /api/v1/trust/identities/{id}       — get identity
  DELETE /api/v1/trust/identities/{id}     — revoke identity
  POST /api/v1/trust/identities/{id}/delegate — issue delegated credential

Supply Chain:
  POST /api/v1/trust/models/assess         — run model security assessment
  GET  /api/v1/trust/models/assessments    — list assessments
  GET  /api/v1/trust/models/risks          — list risk records
  POST /api/v1/trust/models/assessments/{id}/clear — human clearance

MCP/Tools:
  POST /api/v1/trust/mcp/servers           — register MCP server
  POST /api/v1/trust/mcp/servers/{id}/approve — approve server
  POST /api/v1/trust/mcp/tools            — register tool
  POST /api/v1/trust/mcp/tools/{id}/approve  — approve tool
  POST /api/v1/trust/mcp/tools/{id}/execute  — authorize execution
  GET  /api/v1/trust/mcp/executions        — list tool executions

Governance:
  POST /api/v1/trust/governance/evaluate   — evaluate governance decision
  GET  /api/v1/trust/governance/queue      — approval queue
  POST /api/v1/trust/governance/queue/{id}/approve — approve request
  POST /api/v1/trust/governance/queue/{id}/reject  — reject request

Risk Register:
  GET  /api/v1/trust/risks                 — list risks
  POST /api/v1/trust/risks                 — add risk
  GET  /api/v1/trust/risks/report          — generate report
  POST /api/v1/trust/risks/{id}/evidence   — add evidence
  GET  /api/v1/trust/risks/evidence        — list evidence

Audit:
  GET  /api/v1/trust/audit                 — query audit log
  GET  /api/v1/trust/audit/stats           — audit statistics

Agent Runtime:
  POST /api/v1/trust/agents/sessions       — create agent session
  GET  /api/v1/trust/agents/sessions/{id}  — get session
  DELETE /api/v1/trust/agents/sessions/{id} — terminate session
  POST /api/v1/trust/agents/sessions/{id}/assess-injection — assess injection risk
  GET  /api/v1/trust/agents/tool-records   — list tool call records
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

trust_router = APIRouter(prefix="/api/v1/trust", tags=["trust-centre"])


# ---------------------------------------------------------------------------
# Auth stub (compatible with existing JWT middleware pattern)
# ---------------------------------------------------------------------------

def _get_current_user() -> Dict[str, Any]:
    return {"user_id": "demo-user", "tenant_id": "default", "role": "operator"}


# ---------------------------------------------------------------------------
# Request/Response models
# ---------------------------------------------------------------------------

class PolicyEvalRequest(BaseModel):
    actor_id: str
    actor_type: str = "human"
    resource_type: str
    resource_id: str
    action: str
    context: Dict[str, Any] = {}
    resource_tenant_id: Optional[str] = None


class IdentityCreateRequest(BaseModel):
    name: str
    identity_type: str              # "human" | "agent" | "mcp_server" | ...
    roles: Optional[List[str]] = None
    expires_in_hours: Optional[int] = None


class DelegateRequest(BaseModel):
    agent_identity_id: str
    requested_permissions: List[str]
    purpose: str
    ttl_hours: int = 1


class ModelAssessRequest(BaseModel):
    model_id: str
    publisher: str
    source_url: str
    revision: str
    expected_revision: Optional[str] = None
    file_extensions: List[str] = [".safetensors"]
    licence: str = "unknown"
    commercial_use: Optional[bool] = None
    config_files: Optional[List[str]] = None
    expected_checksum: Optional[str] = None
    actual_checksum: Optional[str] = None


class ClearanceRequest(BaseModel):
    reviewer_id: str
    notes: str = ""


class MCPServerRegisterRequest(BaseModel):
    name: str
    version: str
    description: str
    endpoint_url: str
    public_key_fingerprint: str = ""
    allowed_network_domains: List[str] = []


class MCPToolRegisterRequest(BaseModel):
    server_id: str
    name: str
    description: str
    version: str
    required_scopes: List[str]
    input_schema: Optional[Dict] = None
    allowed_callers: Optional[List[str]] = None
    network_restrictions: Optional[List[str]] = None
    max_execution_seconds: int = 30


class ToolExecuteRequest(BaseModel):
    agent_id: str
    session_id: str
    inputs: Dict[str, Any] = {}
    agent_scopes: List[str] = []


class ApproverRequest(BaseModel):
    approver_id: str
    notes: str = ""


class RejectRequest(BaseModel):
    rejector_id: str
    reason: str


class GovEvalRequest(BaseModel):
    actor_id: str
    operation_type: str
    resource_id: str
    resource_type: str = "unknown"
    context: Dict[str, Any] = {}


class RiskAddRequest(BaseModel):
    asset_type: str
    asset_id: str
    category: str
    title: str
    description: str
    severity: str
    likelihood: str
    potential_impact: str
    mitigation: str
    residual_risk: str
    risk_owner: str
    compliance_refs: List[str] = []


class EvidenceAddRequest(BaseModel):
    control_id: str
    evidence_type: str
    description: str
    implementation_status: str
    evidence_data: Dict[str, Any] = {}


class AgentSessionRequest(BaseModel):
    agent_id: str
    permitted_tools: List[str]
    permitted_permissions: List[str]
    max_execution_seconds: int = 300
    max_spend_usd: float = 10.0
    max_tool_calls: int = 50


class InjectionAssessRequest(BaseModel):
    content: str
    source: str = "user_direct"


# ---------------------------------------------------------------------------
# Policy Engine endpoints
# ---------------------------------------------------------------------------

@trust_router.get("/policies")
def list_policies(
    resource_type: Optional[str] = Query(None),
    current_user: Dict = Depends(_get_current_user),
):
    from security.policy_engine import get_policy_store
    store = get_policy_store()
    return [p.to_dict() for p in store.list_all(resource_type=resource_type)]


@trust_router.post("/policies/evaluate")
def evaluate_policy(body: PolicyEvalRequest, current_user: Dict = Depends(_get_current_user)):
    from security.policy_engine import get_policy_engine
    engine = get_policy_engine()
    result = engine.evaluate(
        actor_id=body.actor_id,
        actor_type=body.actor_type,
        tenant_id=current_user["tenant_id"],
        resource_type=body.resource_type,
        resource_id=body.resource_id,
        action=body.action,
        context=body.context,
        resource_tenant_id=body.resource_tenant_id,
    )
    return result.to_dict()


@trust_router.delete("/policies/{policy_id}", status_code=204)
def disable_policy(policy_id: str, current_user: Dict = Depends(_get_current_user)):
    from security.policy_engine import get_policy_store
    store = get_policy_store()
    if not store.disable(policy_id):
        raise HTTPException(status_code=404, detail="Policy not found")


# ---------------------------------------------------------------------------
# IAM endpoints
# ---------------------------------------------------------------------------

@trust_router.post("/identities", status_code=201)
def create_identity(body: IdentityCreateRequest, current_user: Dict = Depends(_get_current_user)):
    from security.iam import get_iam_store, IdentityType
    import datetime
    store = get_iam_store()
    try:
        itype = IdentityType(body.identity_type)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid identity_type: {body.identity_type}")

    expires_at = None
    if body.expires_in_hours:
        expires_at = (
            datetime.datetime.utcnow() + datetime.timedelta(hours=body.expires_in_hours)
        ).isoformat() + "Z"

    identity = store.create_identity(
        name=body.name,
        identity_type=itype,
        tenant_id=current_user["tenant_id"],
        roles=body.roles,
        created_by=current_user["user_id"],
        expires_at=expires_at,
    )
    return identity.to_dict()


@trust_router.get("/identities")
def list_identities(
    identity_type: Optional[str] = Query(None),
    current_user: Dict = Depends(_get_current_user),
):
    from security.iam import get_iam_store, IdentityType
    store = get_iam_store()
    itype = None
    if identity_type:
        try:
            itype = IdentityType(identity_type)
        except ValueError:
            pass
    identities = store.list_identities(current_user["tenant_id"], itype)
    return [i.to_dict() for i in identities]


@trust_router.get("/identities/{identity_id}")
def get_identity(identity_id: str, current_user: Dict = Depends(_get_current_user)):
    from security.iam import get_iam_store
    store = get_iam_store()
    identity = store.get(identity_id)
    if not identity or identity.tenant_id != current_user["tenant_id"]:
        raise HTTPException(status_code=404, detail="Identity not found")
    return identity.to_dict()


@trust_router.delete("/identities/{identity_id}", status_code=204)
def revoke_identity(identity_id: str, current_user: Dict = Depends(_get_current_user)):
    from security.iam import get_iam_store
    store = get_iam_store()
    identity = store.get(identity_id)
    if not identity or identity.tenant_id != current_user["tenant_id"]:
        raise HTTPException(status_code=404, detail="Identity not found")
    store.revoke_identity(identity_id, reason=f"Revoked by {current_user['user_id']}")


@trust_router.post("/identities/{identity_id}/delegate", status_code=201)
def delegate_credential(
    identity_id: str,
    body: DelegateRequest,
    current_user: Dict = Depends(_get_current_user),
):
    from security.iam import get_iam_store
    store = get_iam_store()
    try:
        cred = store.delegate(
            agent_identity_id=body.agent_identity_id,
            delegating_user_id=identity_id,
            tenant_id=current_user["tenant_id"],
            requested_permissions=set(body.requested_permissions),
            purpose=body.purpose,
            ttl_hours=body.ttl_hours,
        )
        return cred.to_dict()
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=403, detail=str(exc))


# ---------------------------------------------------------------------------
# Model supply chain endpoints
# ---------------------------------------------------------------------------

@trust_router.post("/models/assess", status_code=201)
def assess_model(body: ModelAssessRequest, current_user: Dict = Depends(_get_current_user)):
    from security.model_supply_chain import get_supply_chain_security
    scs = get_supply_chain_security()
    assessment = scs.assess_model(
        model_id=body.model_id,
        publisher=body.publisher,
        source_url=body.source_url,
        revision=body.revision,
        expected_revision=body.expected_revision,
        file_extensions=body.file_extensions,
        licence=body.licence,
        commercial_use=body.commercial_use,
        config_files=body.config_files,
        expected_checksum=body.expected_checksum,
        actual_checksum=body.actual_checksum,
    )
    return assessment.to_dict()


@trust_router.get("/models/assessments")
def list_assessments(
    model_id: Optional[str] = Query(None),
    current_user: Dict = Depends(_get_current_user),
):
    from security.model_supply_chain import get_supply_chain_security
    return get_supply_chain_security().list_assessments(model_id=model_id)


@trust_router.get("/models/risks")
def list_model_risks(current_user: Dict = Depends(_get_current_user)):
    from security.model_supply_chain import get_supply_chain_security
    return get_supply_chain_security().list_risk_records()


@trust_router.post("/models/assessments/{assessment_id}/clear")
def clear_model_for_deployment(
    assessment_id: str,
    body: ClearanceRequest,
    current_user: Dict = Depends(_get_current_user),
):
    from security.model_supply_chain import get_supply_chain_security
    try:
        assessment = get_supply_chain_security().clear_for_deployment(
            assessment_id=assessment_id,
            reviewer_id=body.reviewer_id,
            notes=body.notes,
        )
        return assessment.to_dict()
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=403, detail=str(exc))


# ---------------------------------------------------------------------------
# MCP / Tool Security endpoints
# ---------------------------------------------------------------------------

@trust_router.post("/mcp/servers", status_code=201)
def register_mcp_server(body: MCPServerRegisterRequest, current_user: Dict = Depends(_get_current_user)):
    from security.mcp_tool_security import get_mcp_registry
    reg = get_mcp_registry()
    server = reg.register_server(
        name=body.name,
        version=body.version,
        description=body.description,
        tenant_id=current_user["tenant_id"],
        endpoint_url=body.endpoint_url,
        public_key_fingerprint=body.public_key_fingerprint,
        allowed_network_domains=body.allowed_network_domains,
        registered_by=current_user["user_id"],
    )
    return server.to_dict()


@trust_router.post("/mcp/servers/{server_id}/approve")
def approve_mcp_server(
    server_id: str,
    body: ApproverRequest,
    current_user: Dict = Depends(_get_current_user),
):
    from security.mcp_tool_security import get_mcp_registry
    try:
        server = get_mcp_registry().approve_server(server_id, body.approver_id)
        return server.to_dict()
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@trust_router.get("/mcp/servers")
def list_mcp_servers(current_user: Dict = Depends(_get_current_user)):
    from security.mcp_tool_security import get_mcp_registry
    return get_mcp_registry().list_servers(current_user["tenant_id"])


@trust_router.post("/mcp/tools", status_code=201)
def register_tool(body: MCPToolRegisterRequest, current_user: Dict = Depends(_get_current_user)):
    from security.mcp_tool_security import get_mcp_registry
    try:
        tool = get_mcp_registry().register_tool(
            server_id=body.server_id,
            name=body.name,
            description=body.description,
            version=body.version,
            tenant_id=current_user["tenant_id"],
            required_scopes=body.required_scopes,
            input_schema=body.input_schema,
            allowed_callers=body.allowed_callers,
            network_restrictions=body.network_restrictions,
            max_execution_seconds=body.max_execution_seconds,
        )
        return tool.to_dict()
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@trust_router.post("/mcp/tools/{tool_id}/approve")
def approve_tool(
    tool_id: str,
    body: ApproverRequest,
    current_user: Dict = Depends(_get_current_user),
):
    from security.mcp_tool_security import get_mcp_registry
    try:
        tool = get_mcp_registry().approve_tool(tool_id, body.approver_id)
        return tool.to_dict()
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@trust_router.get("/mcp/tools")
def list_tools(
    status: Optional[str] = Query(None),
    current_user: Dict = Depends(_get_current_user),
):
    from security.mcp_tool_security import get_mcp_registry, ToolStatus
    s = None
    if status:
        try:
            s = ToolStatus(status)
        except ValueError:
            pass
    return get_mcp_registry().list_tools(current_user["tenant_id"], s)


@trust_router.post("/mcp/tools/{tool_id}/execute", status_code=201)
def authorize_tool_execution(
    tool_id: str,
    body: ToolExecuteRequest,
    current_user: Dict = Depends(_get_current_user),
):
    from security.mcp_tool_security import get_mcp_registry
    record = get_mcp_registry().authorize_execution(
        tool_id=tool_id,
        agent_id=body.agent_id,
        tenant_id=current_user["tenant_id"],
        session_id=body.session_id,
        inputs=body.inputs,
        agent_scopes=set(body.agent_scopes),
    )
    return record.to_dict()


@trust_router.get("/mcp/executions")
def list_tool_executions(
    tool_id: Optional[str] = Query(None),
    agent_id: Optional[str] = Query(None),
    current_user: Dict = Depends(_get_current_user),
):
    from security.mcp_tool_security import get_mcp_registry
    return get_mcp_registry().get_executions(
        tool_id=tool_id,
        agent_id=agent_id,
        tenant_id=current_user["tenant_id"],
    )


# ---------------------------------------------------------------------------
# Governance endpoints
# ---------------------------------------------------------------------------

@trust_router.post("/governance/evaluate")
def evaluate_governance(body: GovEvalRequest, current_user: Dict = Depends(_get_current_user)):
    from security.governance_approvals import get_governance_engine
    result = get_governance_engine().evaluate(
        actor_id=body.actor_id,
        tenant_id=current_user["tenant_id"],
        operation_type=body.operation_type,
        resource_id=body.resource_id,
        resource_type=body.resource_type,
        context=body.context,
    )
    return result.to_dict()


@trust_router.get("/governance/policies")
def list_gov_policies(
    operation_type: Optional[str] = Query(None),
    current_user: Dict = Depends(_get_current_user),
):
    from security.governance_approvals import get_governance_engine
    return get_governance_engine().list_policies(operation_type=operation_type)


@trust_router.get("/governance/queue")
def get_approval_queue(
    status: Optional[str] = Query(None),
    current_user: Dict = Depends(_get_current_user),
):
    from security.governance_approvals import get_governance_engine, ApprovalStatus
    s = None
    if status:
        try:
            s = ApprovalStatus(status)
        except ValueError:
            pass
    return get_governance_engine().get_approval_queue(current_user["tenant_id"], s)


@trust_router.post("/governance/queue/{request_id}/approve")
def approve_governance_request(
    request_id: str,
    body: ApproverRequest,
    current_user: Dict = Depends(_get_current_user),
):
    from security.governance_approvals import get_governance_engine
    try:
        req = get_governance_engine().approve_request(request_id, body.approver_id, body.notes)
        return req.to_dict()
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@trust_router.post("/governance/queue/{request_id}/reject")
def reject_governance_request(
    request_id: str,
    body: RejectRequest,
    current_user: Dict = Depends(_get_current_user),
):
    from security.governance_approvals import get_governance_engine
    try:
        req = get_governance_engine().reject_request(request_id, body.rejector_id, body.reason)
        return req.to_dict()
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ---------------------------------------------------------------------------
# Risk Register endpoints
# ---------------------------------------------------------------------------

@trust_router.get("/risks")
def list_risks(
    category: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    current_user: Dict = Depends(_get_current_user),
):
    from security.risk_register import get_risk_register, RiskCategory, Severity
    cat = None
    sev = None
    try:
        if category:
            cat = RiskCategory(category)
        if severity:
            sev = Severity(severity)
    except ValueError:
        pass
    return get_risk_register().list_risks(
        tenant_id=current_user["tenant_id"],
        category=cat,
        severity=sev,
    )


@trust_router.post("/risks", status_code=201)
def add_risk(body: RiskAddRequest, current_user: Dict = Depends(_get_current_user)):
    from security.risk_register import get_risk_register, RiskCategory, Severity, Likelihood
    try:
        entry = get_risk_register().add_risk(
            asset_type=body.asset_type,
            asset_id=body.asset_id,
            tenant_id=current_user["tenant_id"],
            category=RiskCategory(body.category),
            title=body.title,
            description=body.description,
            severity=Severity(body.severity),
            likelihood=Likelihood(body.likelihood),
            potential_impact=body.potential_impact,
            mitigation=body.mitigation,
            residual_risk=Severity(body.residual_risk),
            risk_owner=body.risk_owner,
            compliance_refs=body.compliance_refs,
        )
        return entry.to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@trust_router.get("/risks/report")
def get_risk_report(current_user: Dict = Depends(_get_current_user)):
    from security.risk_register import get_risk_register
    return get_risk_register().generate_risk_report(current_user["tenant_id"])


@trust_router.post("/risks/{risk_id}/evidence", status_code=201)
def add_evidence(
    risk_id: str,
    body: EvidenceAddRequest,
    current_user: Dict = Depends(_get_current_user),
):
    from security.risk_register import get_risk_register
    evidence = get_risk_register().add_evidence(
        risk_id=risk_id,
        control_id=body.control_id,
        evidence_type=body.evidence_type,
        description=body.description,
        implementation_status=body.implementation_status,
        evidence_data=body.evidence_data,
        collected_by=current_user["user_id"],
    )
    if not evidence:
        raise HTTPException(status_code=404, detail="Risk or control not found")
    return evidence.to_dict()


@trust_router.get("/risks/evidence")
def list_evidence(
    risk_id: Optional[str] = Query(None),
    framework: Optional[str] = Query(None),
    current_user: Dict = Depends(_get_current_user),
):
    from security.risk_register import get_risk_register, ComplianceFramework
    fw = None
    if framework:
        try:
            fw = ComplianceFramework(framework)
        except ValueError:
            pass
    return get_risk_register().list_evidence(risk_id=risk_id, framework=fw)


# ---------------------------------------------------------------------------
# Audit endpoints
# ---------------------------------------------------------------------------

@trust_router.get("/audit")
def query_audit(
    actor_id: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    decision: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
    current_user: Dict = Depends(_get_current_user),
):
    from security.policy_engine import get_audit_bus
    return get_audit_bus().query(
        tenant_id=current_user["tenant_id"],
        actor_id=actor_id,
        resource_type=resource_type,
        decision=decision,
        limit=limit,
    )


@trust_router.get("/audit/stats")
def audit_stats(current_user: Dict = Depends(_get_current_user)):
    from security.policy_engine import get_audit_bus
    bus = get_audit_bus()
    all_events = bus.query(tenant_id=current_user["tenant_id"], limit=10000)
    decision_counts: Dict[str, int] = {}
    resource_counts: Dict[str, int] = {}
    for e in all_events:
        d = e.get("decision", "UNKNOWN")
        r = e.get("resource_type", "UNKNOWN")
        decision_counts[d] = decision_counts.get(d, 0) + 1
        resource_counts[r] = resource_counts.get(r, 0) + 1
    return {
        "total_events": len(all_events),
        "decision_breakdown": decision_counts,
        "resource_type_breakdown": resource_counts,
    }


# ---------------------------------------------------------------------------
# Agent Runtime endpoints
# ---------------------------------------------------------------------------

@trust_router.post("/agents/sessions", status_code=201)
def create_agent_session(body: AgentSessionRequest, current_user: Dict = Depends(_get_current_user)):
    from security.agent_runtime import get_agent_runtime
    runtime = get_agent_runtime()
    sess = runtime.create_session(
        agent_id=body.agent_id,
        tenant_id=current_user["tenant_id"],
        permitted_tools=set(body.permitted_tools),
        permitted_permissions=set(body.permitted_permissions),
        max_execution_seconds=body.max_execution_seconds,
        max_spend_usd=body.max_spend_usd,
        max_tool_calls=body.max_tool_calls,
    )
    return sess.to_dict()


@trust_router.get("/agents/sessions/{session_id}")
def get_agent_session(session_id: str, current_user: Dict = Depends(_get_current_user)):
    from security.agent_runtime import get_agent_runtime
    sess = get_agent_runtime().get_session(session_id)
    if not sess or sess.tenant_id != current_user["tenant_id"]:
        raise HTTPException(status_code=404, detail="Session not found")
    return sess.to_dict()


@trust_router.delete("/agents/sessions/{session_id}", status_code=204)
def terminate_agent_session(session_id: str, current_user: Dict = Depends(_get_current_user)):
    from security.agent_runtime import get_agent_runtime
    sess = get_agent_runtime().get_session(session_id)
    if not sess or sess.tenant_id != current_user["tenant_id"]:
        raise HTTPException(status_code=404, detail="Session not found")
    get_agent_runtime().terminate_session(session_id, reason="terminated_by_operator")


@trust_router.post("/agents/sessions/{session_id}/assess-injection")
def assess_injection(
    session_id: str,
    body: InjectionAssessRequest,
    current_user: Dict = Depends(_get_current_user),
):
    from security.agent_runtime import get_agent_runtime, InputSource
    runtime = get_agent_runtime()
    try:
        source = InputSource(body.source)
    except ValueError:
        source = InputSource.USER_DIRECT
    result = runtime.assess_injection_risk(body.content, source)
    return result.to_dict()


@trust_router.get("/agents/tool-records")
def list_tool_records(
    agent_id: Optional[str] = Query(None),
    current_user: Dict = Depends(_get_current_user),
):
    from security.agent_runtime import get_agent_runtime
    return get_agent_runtime().get_tool_records(agent_id=agent_id)
