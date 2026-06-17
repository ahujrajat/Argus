from __future__ import annotations
import re
import hashlib

_SECRET_PATTERNS = [
    re.compile(r"sk-ant-api\d{2}-[A-Za-z0-9_\-]{12,}"),
    re.compile(r"sk-proj-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"ghp_[A-Za-z0-9]{36}"),
    re.compile(r"gho_[A-Za-z0-9]{36}"),
    re.compile(r"AIza[0-9A-Za-z\-_]{35}"),
    re.compile(r"[A-Za-z0-9+/]{40,}={0,2}"),  # base64 blobs ≥40 chars
]

_SENSITIVE_KEYS = frozenset({
    "password", "passwd", "secret", "token", "api_key", "apikey",
    "access_key", "secret_key", "private_key", "auth", "credential",
    "credentials", "authorization", "bearer",
})


def redact(text: str) -> str:
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def redact_dict(d: dict) -> dict:
    result = {}
    for k, v in d.items():
        if isinstance(k, str) and k.lower() in _SENSITIVE_KEYS:
            result[k] = "[REDACTED]"
        elif isinstance(v, dict):
            result[k] = redact_dict(v)
        elif isinstance(v, str):
            result[k] = redact(v)
        else:
            result[k] = v
    return result


def fingerprint(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()
