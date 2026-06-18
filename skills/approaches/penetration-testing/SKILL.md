---
name: penetration-testing
description: Penetration testing methodology — breadth-first vulnerability discovery and exploitation
version: 1.0.0
family: approaches
tools_allowed: [semgrep, trufflehog, nuclei, zap]
---

# Penetration Testing

## Methodology
Penetration testing is breadth-first: find and demonstrate exploitation of as many
vulnerabilities as possible within a defined scope and time box. It answers "what can
be broken" rather than "would we catch a real intruder."

It is noisier and less concerned with detection evasion than red teaming.
A pentest produces a report of exploitable findings with proof-of-concept.

## Scope definition
- Define in-scope targets explicitly before scanning
- Out-of-scope systems must not be touched
- Production systems require explicit authorization; prefer staging/dev

## Reporting framing
- Lead with business impact, not technical severity
- Include proof-of-concept for every exploitable finding
- Group findings by attack surface (web, API, infra, code)
- Prioritize by exploitability × impact, not CVSS alone

## Tools in scope for this approach
Static: semgrep (SAST), trufflehog (secrets)
Dynamic: nuclei (known vulns), zap (web app scanning) — Phase 6
