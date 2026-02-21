"""
OrQuanta Agentic v1.0 — Input Validator & Security Filter

Protects all API entry points from:
  - Prompt injection attacks (LLM manipulation)
  - SQL injection (belt-and-suspenders on top of ORM)
  - Path traversal / directory traversal
  - Script injection (XSS)
  - Oversized payloads (DoS)
  - Malicious file names
  - SSRF attempts in URLs

Every user-supplied string MUST pass through sanitize() before
being processed by any agent or stored in the database.
"""

from __future__ import annotations

import html
import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("orquanta.security.input_validator")

# ─── Limits ─────────────────────────────────────────────────────────────────
MAX_GOAL_TEXT_LEN = 2000
MAX_FIELD_LEN = 500
MAX_EMAIL_LEN = 320
MAX_URL_LEN = 2048
MAX_FILENAME_LEN = 255
MAX_JSON_DEPTH = 10
MAX_ARRAY_LEN = 1000


# ─── Threat patterns ────────────────────────────────────────────────────────

# Prompt injection: attempts to override system instructions
PROMPT_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions?", re.I),
    re.compile(r"you\s+are\s+now\s+(a\s+)?(?:jailbreak|dan|evil|unrestricted)", re.I),
    re.compile(r"forget\s+your\s+(system\s+)?prompt", re.I),
    re.compile(r"act\s+as\s+(if\s+you\s+are\s+)?(?:an?\s+)?(?:ai|robot|bot)\s+without", re.I),
    re.compile(r"\[system\]|\[user\]|\[assistant\]", re.I),
    re.compile(r"<\|im_start\|>|<\|im_end\|>|<\|endoftext\|>", re.I),
    re.compile(r"###\s*(system|instruction)", re.I),
    re.compile(r"prompt\s*injection", re.I),
    re.compile(r"jailbreak", re.I),
    re.compile(r"dan\s+mode", re.I),
]

# SQL injection keywords in suspicious contexts
SQL_INJECTION_PATTERNS = [
    re.compile(r"(--|#|/\*|\*/)", re.I),
    re.compile(r"\b(union\s+select|insert\s+into|drop\s+table|delete\s+from|truncate\s+table|alter\s+table|exec\s*\(|execute\s*\()\b", re.I),
    re.compile(r"\b(xp_cmdshell|sp_executesql|into\s+outfile|load_file)\b", re.I),
    re.compile(r"'\s*(or|and)\s*'?\d*\s*'?\s*=\s*'?\d", re.I),
]

# Path traversal
PATH_TRAVERSAL_PATTERNS = [
    re.compile(r"\.\.[/\\]"),
    re.compile(r"[/\\]etc[/\\]passwd"),
    re.compile(r"[/\\]proc[/\\]"),
    re.compile(r"[/\\]windows[/\\]system32", re.I),
    re.compile(r"%2e%2e", re.I),    # URL-encoded ../
    re.compile(r"%252e", re.I),     # Double-encoded
]

# XSS / script injection
SCRIPT_INJECTION_PATTERNS = [
    re.compile(r"<\s*script", re.I),
    re.compile(r"javascript\s*:", re.I),
    re.compile(r"on\w+\s*=", re.I),       # onload=, onerror=, etc.
    re.compile(r"<\s*iframe", re.I),
    re.compile(r"<\s*object", re.I),
    re.compile(r"data:\s*text/html", re.I),
    re.compile(r"vbscript\s*:", re.I),
]

# SSRF-dangerous URLs
SSRF_PATTERNS = [
    re.compile(r"https?://(?:169\.254\.169\.254|metadata\.google\.internal|100\.100\.100\.200)", re.I),
    re.compile(r"https?://(?:localhost|127\.\d+\.\d+\.\d+|0\.0\.0\.0|::1)", re.I),
    re.compile(r"https?://(?:10\.|172\.(?:1[6-9]|2\d|3[01])\.|192\.168\.)", re.I),
    re.compile(r"file://", re.I),
    re.compile(r"ftp://", re.I),
    re.compile(r"gopher://", re.I),
]

# Dangerous shell metacharacters in filenames / commands
SHELL_METACHAR_PATTERN = re.compile(r"[;&|`$(){}\[\]<>!#*?~^]")


@dataclass
class ValidationResult:
    """Result of input validation."""
    clean: str
    is_safe: bool
    threats_detected: list[str]
    was_modified: bool

    @property
    def is_dangerous(self) -> bool:
        return bool(self.threats_detected)


class InputValidator:
    """
    Central input validation and sanitization.

    All methods return ValidationResult — the caller decides whether to
    reject (raise 400) or use the sanitized value.

    For user-facing goals/intents: reject on any threat.
    For internal strings: use sanitized value with warning.
    """

    # ─── Main entry points ────────────────────────────────────────────

    @classmethod
    def validate_goal_text(cls, text: str) -> ValidationResult:
        """Validate a natural language goal submission (highest security)."""
        result = cls._base_validate(text, max_len=MAX_GOAL_TEXT_LEN)

        # Additional: detect prompt injection
        for pattern in PROMPT_INJECTION_PATTERNS:
            if pattern.search(result.clean):
                result.threats_detected.append(f"PROMPT_INJECTION: {pattern.pattern[:40]}")

        if result.threats_detected:
            logger.warning(f"[InputValidator] GOAL REJECTED — threats: {result.threats_detected}")

        return result

    @classmethod
    def validate_field(cls, value: str, field_name: str = "field", max_len: int = MAX_FIELD_LEN) -> ValidationResult:
        """Validate a generic text field."""
        return cls._base_validate(value, max_len=max_len)

    @classmethod
    def validate_email(cls, email: str) -> ValidationResult:
        """Validate and normalize an email address."""
        clean = email.strip().lower()[:MAX_EMAIL_LEN]
        threats = []
        if not re.match(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$", clean):
            threats.append("INVALID_EMAIL_FORMAT")
        for pattern in SCRIPT_INJECTION_PATTERNS + SQL_INJECTION_PATTERNS:
            if pattern.search(clean):
                threats.append(f"INJECTION_IN_EMAIL")
                break
        return ValidationResult(
            clean=clean,
            is_safe=not bool(threats),
            threats_detected=threats,
            was_modified=(clean != email),
        )

    @classmethod
    def validate_filename(cls, name: str) -> ValidationResult:
        """Validate a filename — strip path traversal and dangerous chars."""
        original = name
        # Strip any directory component
        clean = re.sub(r"[/\\]", "_", name)
        # Remove null bytes
        clean = clean.replace("\x00", "")
        # Strip path traversal
        threats = []
        for pattern in PATH_TRAVERSAL_PATTERNS:
            if pattern.search(clean):
                threats.append("PATH_TRAVERSAL")
                clean = clean.replace("..", "__")
                break
        # Remove shell metacharacters
        if SHELL_METACHAR_PATTERN.search(clean):
            threats.append("SHELL_METACHAR")
            clean = SHELL_METACHAR_PATTERN.sub("_", clean)
        # Limit length
        if len(clean) > MAX_FILENAME_LEN:
            clean = clean[:MAX_FILENAME_LEN]
            threats.append("TRUNCATED")
        # Only allow safe characters
        clean = re.sub(r"[^\w\-.]", "_", clean)
        return ValidationResult(
            clean=clean, is_safe=not bool(threats),
            threats_detected=threats, was_modified=(clean != original),
        )

    @classmethod
    def validate_url(cls, url: str) -> ValidationResult:
        """Validate a URL — block SSRF targets."""
        threats = []
        clean = url.strip()[:MAX_URL_LEN]
        for pattern in SSRF_PATTERNS:
            if pattern.search(clean):
                threats.append(f"SSRF_RISK: {pattern.pattern[:40]}")
        if not re.match(r"^https?://", clean):
            threats.append("INVALID_URL_SCHEME")
        if threats:
            logger.warning(f"[InputValidator] URL BLOCKED — {threats}: {clean[:80]}")
            clean = ""
        return ValidationResult(
            clean=clean, is_safe=not bool(threats),
            threats_detected=threats, was_modified=(clean != url),
        )

    @classmethod
    def validate_json_payload(cls, data: Any, depth: int = 0) -> ValidationResult:
        """Recursively validate a JSON payload for injections."""
        threats: list[str] = []
        if depth > MAX_JSON_DEPTH:
            return ValidationResult("", False, ["JSON_TOO_DEEP"], True)

        if isinstance(data, str):
            r = cls._base_validate(data, max_len=MAX_FIELD_LEN)
            return r
        elif isinstance(data, dict):
            for k, v in list(data.items()):
                r = cls.validate_json_payload(v, depth + 1)
                if r.threats_detected:
                    threats.extend([f"{k}.{t}" for t in r.threats_detected])
        elif isinstance(data, list):
            if len(data) > MAX_ARRAY_LEN:
                threats.append(f"ARRAY_TOO_LARGE: {len(data)}")
            for item in data[:MAX_ARRAY_LEN]:
                r = cls.validate_json_payload(item, depth + 1)
                threats.extend(r.threats_detected)

        return ValidationResult(
            clean=str(data), is_safe=not bool(threats),
            threats_detected=threats, was_modified=False,
        )

    # ─── Sanitizers (clean without rejection) ─────────────────────────

    @staticmethod
    def sanitize_for_llm(text: str) -> str:
        """Strip injection patterns before sending text to any LLM."""
        # Remove special tokens
        clean = re.sub(r"<\|[^|>]+\|>", "", text)
        clean = re.sub(r"\[/?(?:system|user|assistant|inst)\]", "", clean, flags=re.I)
        # Strip HTML/script tags
        clean = re.sub(r"<[^>]+>", "", clean)
        # Normalize unicode control chars
        clean = "".join(c for c in clean if unicodedata.category(c) not in ("Cc", "Cf") or c in "\n\t ")
        return clean.strip()

    @staticmethod
    def sanitize_for_shell(text: str) -> str:
        """Escape a string for safe inclusion in a shell command."""
        # Single-quote wrapping: safest approach
        return "'" + text.replace("'", "'\\''") + "'"

    @staticmethod
    def strip_pii(text: str) -> str:
        """Remove common PII patterns before logging."""
        # Email addresses
        text = re.sub(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b", "[EMAIL]", text)
        # Phone numbers
        text = re.sub(r"\b\+?[\d\s\-().]{10,15}\b", "[PHONE]", text)
        # Credit card-like
        text = re.sub(r"\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b", "[CARD]", text)
        # SSN
        text = re.sub(r"\b\d{3}-\d{2}-\d{4}\b", "[SSN]", text)
        # AWS-key-like
        text = re.sub(r"\bAKIA[A-Z0-9]{16}\b", "[AWS_KEY]", text)
        # JWT-like tokens
        text = re.sub(r"\beyJ[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\b", "[JWT]", text)
        return text

    # ─── Internal ─────────────────────────────────────────────────────

    @classmethod
    def _base_validate(cls, text: str, max_len: int = MAX_FIELD_LEN) -> ValidationResult:
        original = text
        threats: list[str] = []

        # 1. Type check
        if not isinstance(text, str):
            text = str(text)

        # 2. Null byte removal
        clean = text.replace("\x00", "")
        if "\x00" in text:
            threats.append("NULL_BYTE")

        # 3. Length enforcement
        if len(clean) > max_len:
            threats.append(f"TOO_LONG: {len(clean)} > {max_len}")
            clean = clean[:max_len]

        # 4. Normalize unicode (detect homoglyphs etc.)
        try:
            clean = unicodedata.normalize("NFKC", clean)
        except Exception:
            pass

        # 5. HTML escape (XSS prevention)
        escaped = html.escape(clean, quote=True)

        # 6. Pattern checks on original (before escaping)
        for pattern in SQL_INJECTION_PATTERNS:
            if pattern.search(clean):
                threats.append(f"SQL_INJECTION: {pattern.pattern[:40]}")
                break

        for pattern in SCRIPT_INJECTION_PATTERNS:
            if pattern.search(clean):
                threats.append(f"XSS: {pattern.pattern[:40]}")
                break

        for pattern in PATH_TRAVERSAL_PATTERNS:
            if pattern.search(clean):
                threats.append("PATH_TRAVERSAL")
                break

        return ValidationResult(
            clean=escaped,
            is_safe=not bool(threats),
            threats_detected=threats,
            was_modified=(escaped != original),
        )


def require_safe_input(result: ValidationResult, field: str = "input") -> str:
    """Raise HTTPException if input is unsafe. Return clean value otherwise."""
    from fastapi import HTTPException
    if not result.is_safe:
        logger.warning(f"[InputValidator] Blocked unsafe {field}: {result.threats_detected}")
        raise HTTPException(
            status_code=400,
            detail=f"Invalid input: {result.threats_detected[0] if result.threats_detected else 'unsafe content detected'}",
        )
    return result.clean
