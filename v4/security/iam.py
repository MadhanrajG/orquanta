# Copyright 2026 OrQuanta — Apache License 2.0
"""
OrQuanta Phase 4B — AI Identity and Access Management.

Manages identities for: human users, AI agents, models, API keys,
service accounts, MCP servers/tools.

Implements:
- RBAC with fine-grained permissions
- Least privilege defaults
- Short-lived credentials (agent tokens)
- Credential rotation
- Delegated access with scope constraints
- Tenant isolation (enforced at identity layer)
- Session and token revocation

An agent NEVER inherits unrestricted permissions from its creator.
Agent permissions are explicitly scoped at delegation time.
"""
from __future__ import annotations

import datetime
import hashlib
import secrets
import threading
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, FrozenSet, List, Optional, Set

import logging

logger = logging.getLogger("orquanta.security.iam")


# ---------------------------------------------------------------------------
# Permission catalogue
# ---------------------------------------------------------------------------

class Permission(str, Enum):
    # Model permissions
    MODEL_READ          = "model:read"
    MODEL_DEPLOY        = "model:deploy"
    MODEL_DELETE        = "model:delete"
    MODEL_INFER         = "model:infer"
    MODEL_BENCHMARK     = "model:benchmark"
    # Agent permissions
    AGENT_CREATE        = "agent:create"
    AGENT_EXECUTE       = "agent:execute"
    AGENT_READ          = "agent:read"
    AGENT_DELETE        = "agent:delete"
    # Tool permissions
    TOOL_READ           = "tool:read"
    TOOL_EXECUTE        = "tool:execute"
    TOOL_REGISTER       = "tool:register"
    # Data permissions
    DATA_READ           = "data:read"
    DATA_READ_SENSITIVE = "data:read:sensitive"
    DATA_WRITE          = "data:write"
    # GPU permissions
    GPU_PROVISION       = "gpu:provision"
    GPU_READ            = "gpu:read"
    # Admin
    ADMIN_POLICY        = "admin:policy"
    ADMIN_USERS         = "admin:users"
    ADMIN_AUDIT         = "admin:audit"
    # Security
    SECURITY_READ       = "security:read"
    SECURITY_APPROVE    = "security:approve"
    SECURITY_REVOKE     = "security:revoke"
    # Billing
    BILLING_READ        = "billing:read"
    BILLING_MANAGE      = "billing:manage"


# ---------------------------------------------------------------------------
# Roles (RBAC)
# ---------------------------------------------------------------------------

ROLE_PERMISSIONS: Dict[str, Set[str]] = {
    "admin": {p.value for p in Permission},  # all permissions

    "security-admin": {
        Permission.SECURITY_READ.value,
        Permission.SECURITY_APPROVE.value,
        Permission.SECURITY_REVOKE.value,
        Permission.ADMIN_POLICY.value,
        Permission.ADMIN_AUDIT.value,
        Permission.MODEL_READ.value,
        Permission.AGENT_READ.value,
        Permission.TOOL_READ.value,
    },

    "operator": {
        Permission.MODEL_READ.value,
        Permission.MODEL_DEPLOY.value,
        Permission.MODEL_INFER.value,
        Permission.MODEL_BENCHMARK.value,
        Permission.AGENT_CREATE.value,
        Permission.AGENT_EXECUTE.value,
        Permission.AGENT_READ.value,
        Permission.GPU_PROVISION.value,
        Permission.GPU_READ.value,
        Permission.TOOL_READ.value,
        Permission.TOOL_EXECUTE.value,
        Permission.DATA_READ.value,
        Permission.BILLING_READ.value,
    },

    "developer": {
        Permission.MODEL_READ.value,
        Permission.MODEL_INFER.value,
        Permission.MODEL_BENCHMARK.value,
        Permission.AGENT_CREATE.value,
        Permission.AGENT_EXECUTE.value,
        Permission.AGENT_READ.value,
        Permission.TOOL_READ.value,
        Permission.TOOL_EXECUTE.value,
        Permission.DATA_READ.value,
        Permission.GPU_READ.value,
    },

    "viewer": {
        Permission.MODEL_READ.value,
        Permission.AGENT_READ.value,
        Permission.TOOL_READ.value,
        Permission.DATA_READ.value,
        Permission.GPU_READ.value,
        Permission.SECURITY_READ.value,
        Permission.BILLING_READ.value,
    },

    # Agents get minimal permissions — never admin, never sensitive data by default
    "agent": {
        Permission.MODEL_INFER.value,
        Permission.TOOL_READ.value,
        Permission.DATA_READ.value,
    },

    # MCP servers: can only execute pre-approved tools
    "mcp-server": {
        Permission.TOOL_EXECUTE.value,
        Permission.TOOL_READ.value,
    },
}


def get_role_permissions(role: str) -> Set[str]:
    return ROLE_PERMISSIONS.get(role, set())


# ---------------------------------------------------------------------------
# Identity types
# ---------------------------------------------------------------------------

class IdentityType(str, Enum):
    HUMAN         = "human"
    AGENT         = "agent"
    MODEL         = "model"
    API_KEY       = "api_key"
    SERVICE_ACCT  = "service_account"
    MCP_SERVER    = "mcp_server"


@dataclass
class Identity:
    identity_id: str
    identity_type: IdentityType
    name: str
    tenant_id: str
    roles: List[str] = field(default_factory=list)
    explicit_permissions: Set[str] = field(default_factory=set)
    denied_permissions: Set[str] = field(default_factory=set)
    created_at: str = field(default_factory=lambda: _now())
    created_by: str = "system"
    is_active: bool = True
    is_revoked: bool = False
    revoked_at: Optional[str] = None
    revoked_reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    # Short-lived credential support
    expires_at: Optional[str] = None

    def effective_permissions(self) -> Set[str]:
        """Union of role permissions + explicit grants, minus explicit denials."""
        perms: Set[str] = set()
        for role in self.roles:
            perms |= get_role_permissions(role)
        perms |= self.explicit_permissions
        perms -= self.denied_permissions
        return perms

    def has_permission(self, permission: str) -> bool:
        if self.is_revoked or not self.is_active:
            return False
        if self.expires_at:
            try:
                exp = datetime.datetime.fromisoformat(self.expires_at.rstrip("Z"))
                if datetime.datetime.utcnow() > exp:
                    return False
            except Exception:
                pass
        return permission in self.effective_permissions()

    def is_expired(self) -> bool:
        if not self.expires_at:
            return False
        try:
            exp = datetime.datetime.fromisoformat(self.expires_at.rstrip("Z"))
            return datetime.datetime.utcnow() > exp
        except Exception:
            return False

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["explicit_permissions"] = list(self.explicit_permissions)
        d["denied_permissions"] = list(self.denied_permissions)
        d["effective_permissions"] = list(self.effective_permissions())
        return d


# ---------------------------------------------------------------------------
# Delegated credential (agent tokens)
# ---------------------------------------------------------------------------

@dataclass
class DelegatedCredential:
    """
    Short-lived credential issued to an agent on behalf of a human user.
    Permissions are always a strict subset of the delegating user's permissions.
    An agent NEVER inherits unrestricted permissions.
    """
    credential_id: str
    agent_identity_id: str
    delegating_user_id: str
    tenant_id: str
    scoped_permissions: Set[str]        # explicit subset — never wildcard
    purpose: str
    created_at: str = field(default_factory=lambda: _now())
    expires_at: str = field(default_factory=lambda: (
        datetime.datetime.utcnow() + datetime.timedelta(hours=1)
    ).isoformat() + "Z")
    is_revoked: bool = False
    revoked_at: Optional[str] = None

    def is_valid(self) -> bool:
        if self.is_revoked:
            return False
        try:
            exp = datetime.datetime.fromisoformat(self.expires_at.rstrip("Z"))
            return datetime.datetime.utcnow() <= exp
        except Exception:
            return False

    def has_permission(self, permission: str) -> bool:
        return self.is_valid() and permission in self.scoped_permissions

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["scoped_permissions"] = list(self.scoped_permissions)
        return d


# ---------------------------------------------------------------------------
# IAM Store
# ---------------------------------------------------------------------------

class IAMStore:

    def __init__(self):
        self._lock = threading.Lock()
        self._identities: Dict[str, Identity] = {}
        self._credentials: Dict[str, DelegatedCredential] = {}
        self._by_name: Dict[str, str] = {}     # name → identity_id (within tenant)

    # -- Identity management -------------------------------------------------

    def create_identity(
        self,
        name: str,
        identity_type: IdentityType,
        tenant_id: str,
        roles: Optional[List[str]] = None,
        created_by: str = "system",
        expires_at: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> Identity:
        iid = str(uuid.uuid4())
        identity = Identity(
            identity_id=iid,
            identity_type=identity_type,
            name=name,
            tenant_id=tenant_id,
            roles=roles or self._default_roles(identity_type),
            created_by=created_by,
            expires_at=expires_at,
            metadata=metadata or {},
        )
        with self._lock:
            self._identities[iid] = identity
            self._by_name[f"{tenant_id}:{name}"] = iid
        logger.info("[iam] Created identity %s type=%s tenant=%s", iid, identity_type, tenant_id)
        return identity

    def _default_roles(self, itype: IdentityType) -> List[str]:
        defaults = {
            IdentityType.HUMAN:        ["developer"],
            IdentityType.AGENT:        ["agent"],
            IdentityType.MODEL:        [],
            IdentityType.API_KEY:      ["developer"],
            IdentityType.SERVICE_ACCT: ["viewer"],
            IdentityType.MCP_SERVER:   ["mcp-server"],
        }
        return defaults.get(itype, [])

    def get(self, identity_id: str) -> Optional[Identity]:
        return self._identities.get(identity_id)

    def get_by_name(self, name: str, tenant_id: str) -> Optional[Identity]:
        iid = self._by_name.get(f"{tenant_id}:{name}")
        return self._identities.get(iid) if iid else None

    def grant_permission(self, identity_id: str, permission: str) -> bool:
        identity = self._identities.get(identity_id)
        if not identity:
            return False
        with self._lock:
            identity.explicit_permissions.add(permission)
        return True

    def deny_permission(self, identity_id: str, permission: str) -> bool:
        identity = self._identities.get(identity_id)
        if not identity:
            return False
        with self._lock:
            identity.denied_permissions.add(permission)
        return True

    def revoke_identity(self, identity_id: str, reason: str = "") -> bool:
        identity = self._identities.get(identity_id)
        if not identity:
            return False
        with self._lock:
            identity.is_revoked = True
            identity.is_active = False
            identity.revoked_at = _now()
            identity.revoked_reason = reason
        logger.warning("[iam] Revoked identity %s reason=%s", identity_id, reason[:100])
        return True

    def list_identities(self, tenant_id: str, identity_type: Optional[IdentityType] = None) -> List[Identity]:
        with self._lock:
            identities = [i for i in self._identities.values() if i.tenant_id == tenant_id]
        if identity_type:
            identities = [i for i in identities if i.identity_type == identity_type]
        return identities

    # -- Delegated credentials -----------------------------------------------

    def delegate(
        self,
        agent_identity_id: str,
        delegating_user_id: str,
        tenant_id: str,
        requested_permissions: Set[str],
        purpose: str,
        ttl_hours: int = 1,
    ) -> DelegatedCredential:
        """
        Issue a delegated credential to an agent.
        Permissions are intersected with the delegating user's effective permissions.
        An agent NEVER gets permissions the delegating user doesn't have.
        """
        agent = self._identities.get(agent_identity_id)
        delegator = self._identities.get(delegating_user_id)

        if not agent:
            raise ValueError(f"Agent identity {agent_identity_id} not found")
        if not delegator:
            raise ValueError(f"Delegating user {delegating_user_id} not found")
        if delegator.tenant_id != tenant_id:
            raise PermissionError("Tenant isolation: delegating user must be in same tenant")
        if agent.tenant_id != tenant_id:
            raise PermissionError("Tenant isolation: agent must be in same tenant")

        # Strict intersection — agent cannot exceed delegator's permissions
        allowed = requested_permissions & delegator.effective_permissions()
        if not allowed:
            raise PermissionError(
                "Delegation denied: no overlap between requested permissions "
                "and delegating user's effective permissions."
            )

        expires_at = (
            datetime.datetime.utcnow() + datetime.timedelta(hours=ttl_hours)
        ).isoformat() + "Z"

        cred = DelegatedCredential(
            credential_id=str(uuid.uuid4()),
            agent_identity_id=agent_identity_id,
            delegating_user_id=delegating_user_id,
            tenant_id=tenant_id,
            scoped_permissions=allowed,
            purpose=purpose,
            expires_at=expires_at,
        )
        with self._lock:
            self._credentials[cred.credential_id] = cred
        logger.info(
            "[iam] Delegated credential %s to agent %s permissions=%s ttl=%dh",
            cred.credential_id, agent_identity_id, list(allowed), ttl_hours,
        )
        return cred

    def get_credential(self, credential_id: str) -> Optional[DelegatedCredential]:
        return self._credentials.get(credential_id)

    def revoke_credential(self, credential_id: str) -> bool:
        cred = self._credentials.get(credential_id)
        if not cred:
            return False
        cred.is_revoked = True
        cred.revoked_at = _now()
        return True


def _now() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"


_IAM_STORE = IAMStore()


def get_iam_store() -> IAMStore:
    return _IAM_STORE
