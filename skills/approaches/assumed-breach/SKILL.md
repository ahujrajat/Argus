---
name: assumed-breach
description: Assumed breach — post-compromise lateral movement, privilege escalation, and persistence testing
version: 1.0.0
family: approaches
tools_allowed: [semgrep, trufflehog]
---

# Assumed Breach

## Methodology
Assumed breach starts from the premise that the attacker is already inside with
standard user credentials. It skips the initial access phase and focuses entirely
on what an insider or compromised account can do.

It answers: "if an attacker already has a foothold, how far can they go?"

## In-scope objectives
- **Privilege escalation:** finding → admin, root, or service account
- **Lateral movement:** from one service/host to another using credentials or trust relationships
- **Credential harvesting:** hardcoded secrets, session tokens, connection strings accessible to a user
- **Persistence:** mechanisms that survive logout, password reset, or container restart
- **Data exfiltration:** bulk data accessible to a standard user

## Out of scope (in this approach)
- Initial access vulnerabilities (XSS on login page, public endpoint injection) unless
  they also enable post-compromise escalation
- Vulnerabilities only exploitable by unauthenticated attackers

## Report framing
- Group findings by post-compromise objective (escalation / lateral / persistence / exfiltration)
- Score each finding by value to an attacker already inside
- Show the escalation path: user → service account → admin
- Identify crown jewels: what data or systems does the path lead to?
