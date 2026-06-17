---
name: owasp-top-10
description: OWASP Top 10 2021 category codes, CWE mappings, and detection signals
version: 1.0.0
family: standards
tools_allowed: []
---

# OWASP Top 10 (2021) Reference

| Code | Category | Key CWEs | Argus finding types |
|------|----------|----------|---------------------|
| A01:2021 | Broken Access Control | CWE-22, CWE-284, CWE-285, CWE-639 | path traversal, missing authz checks, IDOR |
| A02:2021 | Cryptographic Failures | CWE-311, CWE-326, CWE-327 | weak crypto, unencrypted sensitive data |
| A03:2021 | Injection | CWE-89, CWE-78, CWE-79 | SQL injection, command injection, XSS |
| A04:2021 | Insecure Design | CWE-73, CWE-183 | missing rate limiting, weak password policy |
| A05:2021 | Security Misconfiguration | CWE-16, CWE-611 | debug mode on, permissive CORS, XXE |
| A06:2021 | Vulnerable Components | CWE-1035, CWE-937 | SCA findings, outdated dependencies |
| A07:2021 | Auth & Session Failures | CWE-287, CWE-798 | hardcoded creds, broken session management |
| A08:2021 | Software & Data Integrity | CWE-502, CWE-829 | deserialization, unsigned updates |
| A09:2021 | Logging & Monitoring Failures | CWE-778, CWE-117 | missing audit logs, log injection |
| A10:2021 | SSRF | CWE-918 | unvalidated URL fetch with user input |

## Mapping rule
When a finding has a CWE but no OWASP category, use this table to derive one.
Multiple CWEs may map to the same OWASP category — use the most specific.
