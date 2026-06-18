# tests/core/remediation/test_validator.py
from __future__ import annotations
import subprocess
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from core.remediation.validator import PatchValidator, PatchValidationResult


VULNERABLE_CONTENT = '''\
import os

def run_cmd(user_input):
    os.system(f"ls {user_input}")
'''

UNIFIED_DIFF = '''\
--- a/vuln.py
+++ b/vuln.py
@@ -3,2 +3,4 @@
 def run_cmd(user_input):
-    os.system(f"ls {user_input}")
+    import shlex
+    safe = shlex.quote(user_input)
+    os.system(f"ls {safe}")
'''

SEMGREP_ORIGINAL_SARIF = {
    "runs": [{
        "results": [{
            "ruleId": "python.lang.security.audit.subprocess-shell-true.subprocess-shell-true",
            "locations": [{"physicalLocation": {"artifactLocation": {"uri": "vuln.py"}}}],
        }]
    }]
}

SEMGREP_CLEAN_SARIF = {
    "runs": [{"results": []}]
}


def test_patch_validation_result_defaults():
    r = PatchValidationResult(applied=False, finding_cleared=False, new_findings=[], error=None)
    assert r.applied is False
    assert r.new_findings == []
    assert r.error is None


def test_validate_returns_applied_true_when_patch_succeeds(tmp_path):
    target = tmp_path / "vuln.py"
    target.write_text(VULNERABLE_CONTENT)

    validator = PatchValidator()

    def fake_run(cmd, **kwargs):
        result = MagicMock()
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
        return result

    with patch("subprocess.run", side_effect=fake_run):
        with patch.object(validator, "_run_semgrep", side_effect=[
            SEMGREP_ORIGINAL_SARIF, SEMGREP_CLEAN_SARIF
        ]):
            result = validator.validate(
                diff=UNIFIED_DIFF,
                target_file=target,
                scan_root=tmp_path,
                original_rule_id="python.lang.security.audit.subprocess-shell-true.subprocess-shell-true",
            )

    assert result.applied is True
    assert result.finding_cleared is True
    assert result.new_findings == []
    assert result.error is None


def test_validate_returns_applied_false_when_patch_fails(tmp_path):
    target = tmp_path / "vuln.py"
    target.write_text(VULNERABLE_CONTENT)

    validator = PatchValidator()

    def fake_run_fail(cmd, **kwargs):
        result = MagicMock()
        result.returncode = 1
        result.stdout = ""
        result.stderr = "patch failed"
        return result

    with patch("subprocess.run", side_effect=fake_run_fail):
        result = validator.validate(
            diff=UNIFIED_DIFF,
            target_file=target,
            scan_root=tmp_path,
            original_rule_id="some.rule",
        )

    assert result.applied is False
    assert result.error == "patch failed"


def test_validate_detects_new_findings_introduced_by_patch(tmp_path):
    target = tmp_path / "vuln.py"
    target.write_text(VULNERABLE_CONTENT)

    validator = PatchValidator()

    NEW_FINDING_SARIF = {
        "runs": [{
            "results": [{
                "ruleId": "python.lang.security.new-rule",
                "locations": [{"physicalLocation": {"artifactLocation": {"uri": "vuln.py"}}}],
            }]
        }]
    }

    def fake_run(cmd, **kwargs):
        result = MagicMock()
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
        return result

    with patch("subprocess.run", side_effect=fake_run):
        with patch.object(validator, "_run_semgrep", side_effect=[
            SEMGREP_ORIGINAL_SARIF, NEW_FINDING_SARIF
        ]):
            result = validator.validate(
                diff=UNIFIED_DIFF,
                target_file=target,
                scan_root=tmp_path,
                original_rule_id="python.lang.security.audit.subprocess-shell-true.subprocess-shell-true",
            )

    assert result.finding_cleared is True
    assert "python.lang.security.new-rule" in result.new_findings


def test_validate_finding_not_cleared_if_rule_still_present(tmp_path):
    target = tmp_path / "vuln.py"
    target.write_text(VULNERABLE_CONTENT)

    validator = PatchValidator()
    original_rule = "python.lang.security.audit.subprocess-shell-true.subprocess-shell-true"

    def fake_run(cmd, **kwargs):
        result = MagicMock()
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
        return result

    with patch("subprocess.run", side_effect=fake_run):
        with patch.object(validator, "_run_semgrep", side_effect=[
            SEMGREP_ORIGINAL_SARIF, SEMGREP_ORIGINAL_SARIF
        ]):
            result = validator.validate(
                diff=UNIFIED_DIFF,
                target_file=target,
                scan_root=tmp_path,
                original_rule_id=original_rule,
            )

    assert result.applied is True
    assert result.finding_cleared is False
