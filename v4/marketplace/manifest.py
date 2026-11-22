# Copyright 2026 OrQuanta — Apache License 2.0
"""
OrQuanta Phase 6A — Signed Asset Manifest.

Standardised, versioned manifest for marketplace assets.

Security:
- SHA-256 integrity hash over canonical manifest JSON.
- Ed25519-compatible signature verification (requires publisher public key on record).
- Manifest schema is versioned — breaking changes require a new schema_version.
- Silent changes to published versions are prevented: re-publishing bumps version.
- OrQuanta does NOT auto-trust any manifest solely because it carries a signature;
  signatures prove manifest integrity, not asset safety.
"""
from __future__ import annotations

import hashlib
import json
import datetime
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

import logging

logger = logging.getLogger("orquanta.marketplace.manifest")

MANIFEST_SCHEMA_VERSION = "1.0"


def _now() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"


# ---------------------------------------------------------------------------
# Manifest schema
# ---------------------------------------------------------------------------

@dataclass
class ManifestDependency:
    name: str
    version_spec: str                           # e.g. ">=1.0,<2.0"
    asset_type: str                             # MODEL | AGENT | MCP_TOOL | WORKFLOW | PYTHON_PACKAGE
    optional: bool = False
    resolved_asset_id: Optional[str] = None    # filled after registry lookup


@dataclass
class ManifestResourceRequirements:
    min_cpu_cores: Optional[int] = None
    min_ram_gb: Optional[float] = None
    gpu_required: bool = False
    min_vram_gb: Optional[float] = None
    gpu_count: Optional[int] = None
    disk_gb: Optional[float] = None
    network_egress: bool = False


@dataclass
class AssetManifest:
    # Identity
    manifest_id: str
    schema_version: str = MANIFEST_SCHEMA_VERSION
    asset_name: str = ""
    asset_version: str = ""
    asset_type: str = ""
    publisher_id: str = ""
    publisher_display_name: str = ""
    # Source
    source_repo: Optional[str] = None
    source_ref: Optional[str] = None           # git tag / commit SHA
    homepage: Optional[str] = None
    # Licence
    licence: str = "UNKNOWN"
    licence_url: Optional[str] = None
    licence_note: str = ""
    # Dependencies
    dependencies: List[ManifestDependency] = field(default_factory=list)
    # Permissions
    required_permissions: List[str] = field(default_factory=list)
    required_scopes: List[str] = field(default_factory=list)
    # Resources
    resource_requirements: ManifestResourceRequirements = field(
        default_factory=ManifestResourceRequirements
    )
    # Model dependencies (for agents/workflows)
    model_dependencies: List[str] = field(default_factory=list)
    # Integrity
    content_hash: Optional[str] = None         # SHA-256 of asset payload
    manifest_hash: Optional[str] = None        # SHA-256 of this manifest (computed)
    # Signature
    signature: Optional[str] = None            # Publisher signature (Base64)
    signature_algorithm: str = "Ed25519"
    public_key_fingerprint: Optional[str] = None
    # Security assessment
    security_assessment_ref: Optional[str] = None
    # Timestamps
    created_at: str = field(default_factory=_now)
    signed_at: Optional[str] = None

    def to_canonical_dict(self) -> Dict[str, Any]:
        """
        Returns a deterministic dict for hashing.
        Excludes signature, manifest_hash, and created_at (non-deterministic fields).
        """
        d = asdict(self)
        for key in ("signature", "manifest_hash", "created_at", "signed_at"):
            d.pop(key, None)
        return d

    def compute_hash(self) -> str:
        """Compute SHA-256 over canonical JSON (sorted keys, no whitespace)."""
        canonical = json.dumps(self.to_canonical_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Manifest builder
# ---------------------------------------------------------------------------

def build_manifest(
    *,
    asset_name: str,
    asset_version: str,
    asset_type: str,
    publisher_id: str,
    publisher_display_name: str,
    licence: str,
    dependencies: Optional[List[ManifestDependency]] = None,
    required_permissions: Optional[List[str]] = None,
    required_scopes: Optional[List[str]] = None,
    resource_requirements: Optional[ManifestResourceRequirements] = None,
    model_dependencies: Optional[List[str]] = None,
    source_repo: Optional[str] = None,
    source_ref: Optional[str] = None,
    content_hash: Optional[str] = None,
    licence_url: Optional[str] = None,
    licence_note: str = "",
) -> AssetManifest:
    """Create a manifest and compute its hash. Caller must add signature separately."""
    manifest = AssetManifest(
        manifest_id=f"manifest-{uuid.uuid4().hex[:16]}",
        asset_name=asset_name,
        asset_version=asset_version,
        asset_type=asset_type,
        publisher_id=publisher_id,
        publisher_display_name=publisher_display_name,
        licence=licence,
        licence_url=licence_url,
        licence_note=licence_note,
        dependencies=dependencies or [],
        required_permissions=required_permissions or [],
        required_scopes=required_scopes or [],
        resource_requirements=resource_requirements or ManifestResourceRequirements(),
        model_dependencies=model_dependencies or [],
        source_repo=source_repo,
        source_ref=source_ref,
        content_hash=content_hash,
    )
    manifest.manifest_hash = manifest.compute_hash()
    return manifest


# ---------------------------------------------------------------------------
# Manifest verification
# ---------------------------------------------------------------------------

@dataclass
class ManifestVerificationResult:
    is_valid: bool
    hash_match: bool
    signature_verified: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    disclaimer: str = (
        "Manifest verification confirms integrity of the manifest document only. "
        "It does not certify that the asset is safe or free of vulnerabilities."
    )


def verify_manifest(
    manifest: AssetManifest,
    *,
    expected_hash: Optional[str] = None,
    public_key: Optional[bytes] = None,
) -> ManifestVerificationResult:
    """
    Verify manifest integrity and optionally its signature.

    Hash verification: always performed when expected_hash is provided.
    Signature verification: performed only when public_key is provided.
    Without a public key, signature_verified=False is returned — not an error,
    but callers should treat unverified signatures as lower trust.
    """
    errors: List[str] = []
    warnings: List[str] = []

    # 1. Recompute hash
    recomputed = manifest.compute_hash()
    hash_match = True

    if manifest.manifest_hash and manifest.manifest_hash != recomputed:
        errors.append(
            f"Manifest hash mismatch: stored={manifest.manifest_hash[:16]}... "
            f"computed={recomputed[:16]}..."
        )
        hash_match = False

    if expected_hash and expected_hash != recomputed:
        errors.append(
            f"Manifest does not match expected hash: expected={expected_hash[:16]}... "
            f"computed={recomputed[:16]}..."
        )
        hash_match = False

    # 2. Signature verification
    signature_verified = False
    if public_key and manifest.signature:
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            from cryptography.exceptions import InvalidSignature
            import base64
            key = Ed25519PublicKey.from_public_bytes(public_key)
            sig_bytes = base64.b64decode(manifest.signature)
            canonical = json.dumps(
                manifest.to_canonical_dict(), sort_keys=True, separators=(",", ":")
            ).encode()
            key.verify(sig_bytes, canonical)
            signature_verified = True
        except Exception as exc:
            errors.append(f"Signature verification failed: {exc}")
    elif manifest.signature and not public_key:
        warnings.append(
            "Manifest carries a signature but no public key was provided — "
            "signature not verified."
        )
    elif not manifest.signature:
        warnings.append("Manifest is unsigned — provenance cannot be cryptographically confirmed.")

    # 3. Schema version check
    if manifest.schema_version != MANIFEST_SCHEMA_VERSION:
        warnings.append(
            f"Manifest schema version {manifest.schema_version!r} differs from "
            f"current {MANIFEST_SCHEMA_VERSION!r}."
        )

    is_valid = hash_match and len(errors) == 0
    return ManifestVerificationResult(
        is_valid=is_valid,
        hash_match=hash_match,
        signature_verified=signature_verified,
        errors=errors,
        warnings=warnings,
    )
