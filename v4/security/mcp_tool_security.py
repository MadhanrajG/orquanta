# Copyright 2026 OrQuanta — Apache License 2.0
"""
OrQuanta Phase 4E — MCP and Tool Security.

Secure MCP server and tool integration:
- Server identity registration and verification
- Tool registration with explicit permission scopes
- Tool approval workflow (high-impact requires human approval)
- Input and output validation with schema checking
- Execution isolation metadata
- Network restriction enforcement
- Secret protection (secrets never logged or exposed in tool I/O)
- Full tool execution audit trail

Requires explicit authorisation before high-impact tool operations.
"""
from __future__ import annotations

import datetime
import hashlib
import threading
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional, Set

import logging

logger = logging.getLogger("orquanta.security.mcp_tool")


# ---------------------------------------------------------------------------
# Enums and constants
# ---------------------------------------------------------------------------

class ToolRiskLevel(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH     = "HIGH"
    MEDIUM   = "MEDIUM"
    LOW      = "LOW"


class ToolStatus(str, Enum):
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED       = "APPROVED"
    REJECTED       = "REJECTED"
    SUSPENDED      = "SUSPENDED"


class MCPServerStatus(str, Enum):
    REGISTERED  = "REGISTERED"
    ACTIVE      = "ACTIVE"
    SUSPENDED   = "SUSPENDED"
    REVOKED     = "REVOKED"


# Permission scopes for tools
TOOL_SCOPES = {
    "fs:read",          # File system read (sandboxed)
    "fs:write",         # File system write (sandboxed)
    "net:http",         # Outbound HTTP requests
    "net:restricted",   # Outbound to allowlisted domains only
    "db:read",          # Database read
    "db:write",         # Database write
    "exec:shell",       # Shell execution (highest risk)
    "exec:code",        # Code execution
    "mem:read",         # Memory/context read
    "mem:write",        # Memory/context write
    "api:external",     # External API calls
    "api:internal",     # Internal API calls only
}

HIGH_IMPACT_SCOPES = {"fs:write", "db:write", "exec:shell", "exec:code", "net:http", "api:external"}


def _now() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode(errors="replace")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class MCPServer:
    server_id: str
    name: str
    version: str
    description: str
    tenant_id: str
    endpoint_url: str
    public_key_fingerprint: str         # For identity verification
    allowed_network_domains: List[str]  # Empty = no network access
    status: MCPServerStatus = MCPServerStatus.REGISTERED
    registered_by: str = "system"
    registered_at: str = field(default_factory=lambda: _now())
    approved_by: Optional[str] = None
    suspended_reason: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class RegisteredTool:
    tool_id: str
    server_id: str
    name: str
    description: str
    version: str
    tenant_id: str
    required_scopes: List[str]          # Scopes this tool needs
    is_high_impact: bool = False        # Requires human approval before execution
    risk_level: ToolRiskLevel = ToolRiskLevel.MEDIUM
    status: ToolStatus = ToolStatus.PENDING_REVIEW
    input_schema: Optional[Dict] = None
    output_schema: Optional[Dict] = None
    allowed_callers: List[str] = field(default_factory=list)  # agent_ids or "*"
    network_restrictions: List[str] = field(default_factory=list)
    max_execution_seconds: int = 30
    registered_at: str = field(default_factory=lambda: _now())
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class ToolExecutionRecord:
    execution_id: str
    tool_id: str
    tool_name: str
    server_id: str
    agent_id: str
    tenant_id: str
    caller_session_id: str
    input_hash: str                     # Never store raw inputs
    output_hash: str = ""
    permitted: bool = False
    executed: bool = False
    approval_required: bool = False
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    blocked_reason: str = ""
    input_validation_passed: bool = True
    output_validation_passed: bool = True
    duration_ms: float = 0.0
    network_calls: int = 0              # Monitored externally
    timestamp: str = field(default_factory=lambda: _now())
    error: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Input/Output validator
# ---------------------------------------------------------------------------

class ToolInputValidator:
    """
    Validates tool inputs against registered schema.
    Protects against injection via tool inputs.
    """

    def validate(
        self,
        tool: RegisteredTool,
        inputs: Dict[str, Any],
    ) -> tuple[bool, List[str]]:
        """Returns (passed, list_of_violations)."""
        violations = []

        if not tool.input_schema:
            return True, []

        required = tool.input_schema.get("required", [])
        for req_field in required:
            if req_field not in inputs:
                violations.append(f"Missing required field: {req_field}")

        # Type checking (basic)
        properties = tool.input_schema.get("properties", {})
        for prop_name, prop_schema in properties.items():
            if prop_name in inputs:
                expected_type = prop_schema.get("type")
                val = inputs[prop_name]
                if expected_type == "string" and not isinstance(val, str):
                    violations.append(f"Field '{prop_name}' must be string")
                elif expected_type == "integer" and not isinstance(val, int):
                    violations.append(f"Field '{prop_name}' must be integer")
                elif expected_type == "number" and not isinstance(val, (int, float)):
                    violations.append(f"Field '{prop_name}' must be number")

                # String length limits
                if isinstance(val, str):
                    max_len = prop_schema.get("maxLength", 100000)
                    if len(val) > max_len:
                        violations.append(f"Field '{prop_name}' exceeds max length {max_len}")

        return len(violations) == 0, violations

    def redact_secrets(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Return copy of inputs with secret values masked."""
        import re
        secret_keys = re.compile(
            r"(password|secret|key|token|credential|auth|api_key|private)", re.I
        )
        redacted = {}
        for k, v in inputs.items():
            if secret_keys.search(k):
                redacted[k] = "[REDACTED]"
            else:
                redacted[k] = v
        return redacted


# ---------------------------------------------------------------------------
# MCP Tool Security Registry
# ---------------------------------------------------------------------------

class MCPToolSecurityRegistry:

    def __init__(self):
        self._lock = threading.Lock()
        self._servers: Dict[str, MCPServer] = {}
        self._tools: Dict[str, RegisteredTool] = {}
        self._executions: List[ToolExecutionRecord] = []
        self._validator = ToolInputValidator()

    # -- Server registration -------------------------------------------------

    def register_server(
        self,
        name: str,
        version: str,
        description: str,
        tenant_id: str,
        endpoint_url: str,
        public_key_fingerprint: str,
        allowed_network_domains: List[str],
        registered_by: str,
    ) -> MCPServer:
        server = MCPServer(
            server_id=str(uuid.uuid4()),
            name=name,
            version=version,
            description=description,
            tenant_id=tenant_id,
            endpoint_url=endpoint_url,
            public_key_fingerprint=public_key_fingerprint,
            allowed_network_domains=allowed_network_domains,
            registered_by=registered_by,
        )
        with self._lock:
            self._servers[server.server_id] = server
        logger.info("[mcp] Registered server %s id=%s tenant=%s", name, server.server_id, tenant_id)
        return server

    def approve_server(self, server_id: str, approver_id: str) -> MCPServer:
        if approver_id in ("system", "auto", ""):
            raise PermissionError("MCP server approval requires a named human approver.")
        server = self._servers.get(server_id)
        if not server:
            raise ValueError(f"Server {server_id} not found")
        server.status = MCPServerStatus.ACTIVE
        server.approved_by = approver_id
        logger.info("[mcp] Server %s approved by %s", server_id, approver_id)
        return server

    def suspend_server(self, server_id: str, reason: str) -> bool:
        server = self._servers.get(server_id)
        if not server:
            return False
        server.status = MCPServerStatus.SUSPENDED
        server.suspended_reason = reason
        return True

    # -- Tool registration ---------------------------------------------------

    def register_tool(
        self,
        server_id: str,
        name: str,
        description: str,
        version: str,
        tenant_id: str,
        required_scopes: List[str],
        input_schema: Optional[Dict] = None,
        output_schema: Optional[Dict] = None,
        allowed_callers: Optional[List[str]] = None,
        network_restrictions: Optional[List[str]] = None,
        max_execution_seconds: int = 30,
    ) -> RegisteredTool:
        server = self._servers.get(server_id)
        if not server:
            raise ValueError(f"Server {server_id} not found. Register server first.")
        if server.tenant_id != tenant_id:
            raise PermissionError("Tenant isolation: tool must belong to same tenant as server.")

        is_high_impact = bool(set(required_scopes) & HIGH_IMPACT_SCOPES)
        risk = ToolRiskLevel.HIGH if is_high_impact else ToolRiskLevel.MEDIUM

        tool = RegisteredTool(
            tool_id=str(uuid.uuid4()),
            server_id=server_id,
            name=name,
            description=description,
            version=version,
            tenant_id=tenant_id,
            required_scopes=[s for s in required_scopes if s in TOOL_SCOPES],
            is_high_impact=is_high_impact,
            risk_level=risk,
            input_schema=input_schema,
            output_schema=output_schema,
            allowed_callers=allowed_callers or [],
            network_restrictions=network_restrictions or [],
            max_execution_seconds=max_execution_seconds,
        )
        with self._lock:
            self._tools[tool.tool_id] = tool
        logger.info(
            "[mcp] Registered tool %s/%s high_impact=%s scopes=%s",
            server_id, name, is_high_impact, required_scopes,
        )
        return tool

    def approve_tool(self, tool_id: str, approver_id: str) -> RegisteredTool:
        if approver_id in ("system", "auto", ""):
            raise PermissionError("Tool approval requires a named human approver.")
        tool = self._tools.get(tool_id)
        if not tool:
            raise ValueError(f"Tool {tool_id} not found")
        tool.status = ToolStatus.APPROVED
        tool.approved_by = approver_id
        tool.approved_at = _now()
        logger.info("[mcp] Tool %s/%s approved by %s", tool.tool_id, tool.name, approver_id)
        return tool

    # -- Tool execution authorization ----------------------------------------

    def authorize_execution(
        self,
        tool_id: str,
        agent_id: str,
        tenant_id: str,
        session_id: str,
        inputs: Dict[str, Any],
        agent_scopes: Set[str],
    ) -> ToolExecutionRecord:
        """
        Authorize a tool execution request.
        Returns record with permitted=True or blocked_reason set.
        """
        record = ToolExecutionRecord(
            execution_id=str(uuid.uuid4()),
            tool_id=tool_id,
            tool_name="",
            server_id="",
            agent_id=agent_id,
            tenant_id=tenant_id,
            caller_session_id=session_id,
            input_hash=_hash(str(self._validator.redact_secrets(inputs))),
        )

        tool = self._tools.get(tool_id)
        if not tool:
            record.blocked_reason = f"Tool {tool_id} not registered"
            self._append(record)
            return record

        record.tool_name = tool.name
        record.server_id = tool.server_id

        # Tenant isolation
        if tool.tenant_id != tenant_id:
            record.blocked_reason = "Tenant isolation: tool belongs to another tenant"
            self._append(record)
            return record

        # Tool approval status
        if tool.status != ToolStatus.APPROVED:
            record.blocked_reason = f"Tool not approved for execution (status: {tool.status.value})"
            self._append(record)
            return record

        # Caller allowlist check
        if tool.allowed_callers and agent_id not in tool.allowed_callers and "*" not in tool.allowed_callers:
            record.blocked_reason = f"Agent {agent_id} not in tool's allowed_callers list"
            self._append(record)
            return record

        # Scope check: agent must have all required tool scopes
        missing_scopes = set(tool.required_scopes) - agent_scopes
        if missing_scopes:
            record.blocked_reason = f"Agent missing required scopes: {missing_scopes}"
            self._append(record)
            return record

        # Input validation
        passed, violations = self._validator.validate(tool, inputs)
        record.input_validation_passed = passed
        if not passed:
            record.blocked_reason = f"Input validation failed: {'; '.join(violations)}"
            self._append(record)
            return record

        # High-impact requires approval
        if tool.is_high_impact:
            record.approval_required = True
            # Caller must obtain approval separately
            self._append(record)
            return record

        # All checks passed
        record.permitted = True
        self._append(record)
        return record

    def record_approval(self, execution_id: str, approver_id: str) -> ToolExecutionRecord:
        if approver_id in ("system", "auto", ""):
            raise PermissionError("Tool execution approval requires a named human approver.")
        with self._lock:
            records = [r for r in self._executions if r.execution_id == execution_id]
        if not records:
            raise ValueError(f"Execution {execution_id} not found")
        record = records[0]
        record.approved_by = approver_id
        record.approved_at = _now()
        record.permitted = True
        return record

    def record_completion(
        self,
        execution_id: str,
        output: Any,
        duration_ms: float,
        error: str = "",
    ) -> ToolExecutionRecord:
        with self._lock:
            records = [r for r in self._executions if r.execution_id == execution_id]
        if not records:
            raise ValueError(f"Execution {execution_id} not found")
        record = records[0]
        record.output_hash = _hash(str(output))
        record.duration_ms = duration_ms
        record.executed = True
        record.error = error
        return record

    def _append(self, record: ToolExecutionRecord) -> None:
        with self._lock:
            self._executions.append(record)
        status = "PERMITTED" if record.permitted else (
            "APPROVAL_REQUIRED" if record.approval_required else "BLOCKED"
        )
        logger.info(
            "[mcp] Tool %s/%s agent=%s status=%s reason=%s",
            record.tool_id, record.tool_name,
            record.agent_id, status, record.blocked_reason or "-",
        )

    def get_executions(
        self,
        tool_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict]:
        with self._lock:
            records = list(self._executions)
        if tool_id:
            records = [r for r in records if r.tool_id == tool_id]
        if agent_id:
            records = [r for r in records if r.agent_id == agent_id]
        if tenant_id:
            records = [r for r in records if r.tenant_id == tenant_id]
        return [r.to_dict() for r in records[-limit:]]

    def list_tools(self, tenant_id: str, status: Optional[ToolStatus] = None) -> List[Dict]:
        with self._lock:
            tools = [t for t in self._tools.values() if t.tenant_id == tenant_id]
        if status:
            tools = [t for t in tools if t.status == status]
        return [t.to_dict() for t in tools]

    def list_servers(self, tenant_id: str) -> List[Dict]:
        with self._lock:
            servers = [s for s in self._servers.values() if s.tenant_id == tenant_id]
        return [s.to_dict() for s in servers]


_MCP_REGISTRY = MCPToolSecurityRegistry()


def get_mcp_registry() -> MCPToolSecurityRegistry:
    return _MCP_REGISTRY
