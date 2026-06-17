---
name: blue-team
description: Blue team defensive review — detection engineering, hardening, and control gap analysis
version: 1.0.0
family: approaches
tools_allowed: [semgrep, trufflehog]
---

# Blue Team

## Methodology
Blue teaming is the defenders' discipline: monitoring, detection engineering,
incident response, and hardening. In Argus, blue team framing means using the
same vulnerability findings to drive defensive improvements rather than exploitation.

## For each finding, the blue team asks:
1. **Detection:** What log event would indicate exploitation? Which SIEM rule fires?
2. **Prevention:** What control (input validation, auth gate, WAF rule) prevents it?
3. **Hardening:** What configuration change closes the gap permanently?
4. **Response:** If exploited, what is the IR playbook? What artifacts remain?

## Log sources for common vulnerability classes
- SQL injection: database query logs, WAF logs (SQLi pattern matches), app error logs
- XSS: CSP violation reports, browser console errors in monitoring
- Command injection: process creation events (Windows Event 4688, Linux auditd), EDR alerts
- Hardcoded secrets: secret scanning in CI/CD pipeline, vault access logs
- Path traversal: file access audit logs, web server 403/404 patterns

## Hardening checklist
- [ ] All user inputs validated at entry (allow-list preferred over deny-list)
- [ ] CSP header configured: `default-src 'self'`
- [ ] HSTS, X-Frame-Options, X-Content-Type-Options set
- [ ] Least-privilege service accounts — no admin credentials in application config
- [ ] Secrets in vault, not in code or environment files
- [ ] Parameterized queries or ORM for all DB access

## Report framing
- Lead with detection gaps: what would we miss if exploited?
- Organize by control domain (input handling, auth, secrets, network)
- Include SIEM rule recommendations alongside vulnerability descriptions
- Metric: detection coverage percentage — how many findings have a detection rule?
