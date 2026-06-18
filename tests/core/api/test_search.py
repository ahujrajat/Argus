from __future__ import annotations
import pytest
from core.api.search import matches_query


def _finding(**kwargs) -> dict:
    base = {
        "rule_id": "",
        "source_tool": "",
        "cwe": "",
        "owasp_category": "",
        "explanation": "",
        "dedup_key": "",
        "location": {},
    }
    base.update(kwargs)
    return base


def test_matches_rule_id():
    f = _finding(rule_id="sql-injection")
    assert matches_query(f, "sql") is True


def test_matches_source_tool():
    f = _finding(source_tool="semgrep")
    assert matches_query(f, "semgrep") is True


def test_matches_cwe():
    f = _finding(cwe="CWE-89")
    assert matches_query(f, "CWE-89") is True


def test_matches_owasp_category():
    f = _finding(owasp_category="A01:2021")
    assert matches_query(f, "A01") is True


def test_matches_explanation():
    f = _finding(explanation="This is a SQL injection vulnerability")
    assert matches_query(f, "injection") is True


def test_matches_dedup_key():
    f = _finding(dedup_key="abc123")
    assert matches_query(f, "abc123") is True


def test_matches_location_file():
    f = _finding(location={"file": "src/api/db.py"})
    assert matches_query(f, "db.py") is True


def test_case_insensitive_match():
    f = _finding(rule_id="SQL-INJECTION")
    assert matches_query(f, "sql-injection") is True


def test_case_insensitive_query_upper():
    f = _finding(source_tool="semgrep")
    assert matches_query(f, "SEMGREP") is True


def test_no_match_returns_false():
    f = _finding(rule_id="xss", source_tool="bandit")
    assert matches_query(f, "nonexistent-term-xyz") is False


def test_empty_query_matches_everything():
    # "" is a substring of any string, so empty query always matches
    f = _finding(rule_id="anything")
    assert matches_query(f, "") is True


def test_location_not_dict_does_not_crash():
    f = _finding(location=None)
    # Should not raise; location.file lookup is skipped
    assert matches_query(f, "something") is False


def test_location_string_does_not_crash():
    f = _finding(location="some/path.py")
    # location is not a dict, so file lookup is skipped
    assert matches_query(f, "path.py") is False


def test_missing_fields_do_not_crash():
    f = {}  # completely empty finding
    assert matches_query(f, "anything") is False


def test_partial_match_in_file_path():
    f = _finding(location={"file": "/home/user/projects/app/utils.py"})
    assert matches_query(f, "utils") is True
