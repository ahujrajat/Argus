from __future__ import annotations
from core.model.redaction import redact, redact_dict, fingerprint

def test_redact_api_key_in_string():
    text = 'Authorization: Bearer sk-ant-api03-abc123xyz789'
    result = redact(text)
    assert "sk-ant-api03-abc123xyz789" not in result
    assert "[REDACTED]" in result

def test_redact_openai_key():
    text = "key = 'sk-proj-ABCDEFGHIJKLMNOPQRSTUVWXYZ'"
    result = redact(text)
    assert "sk-proj-ABCDEFGHIJKLMNOPQRSTUVWXYZ" not in result

def test_redact_dict_nested():
    d = {"config": {"api_key": "sk-ant-api03-secret", "model": "claude"}}
    result = redact_dict(d)
    assert result["config"]["api_key"] == "[REDACTED]"
    assert result["config"]["model"] == "claude"

def test_redact_dict_key_names():
    d = {"password": "hunter2", "token": "ghp_abc123", "name": "alice"}
    result = redact_dict(d)
    assert result["password"] == "[REDACTED]"
    assert result["token"] == "[REDACTED]"
    assert result["name"] == "alice"

def test_fingerprint_is_deterministic():
    assert fingerprint("secret123") == fingerprint("secret123")

def test_fingerprint_is_not_reversible():
    fp = fingerprint("secret123")
    assert "secret123" not in fp
    assert len(fp) == 64  # sha256 hex
