---
name: breach-and-attack-simulation
description: BAS — continuous automated control validation against current threat landscape
version: 1.0.0
family: approaches
tools_allowed: [semgrep, trufflehog]
---

# Breach and Attack Simulation (BAS)

## Methodology
BAS is the automated, continuous version of adversary emulation. Platforms such as
SafeBreach, AttackIQ, and Cymulate run attack scenarios on a schedule to validate
that security controls still work — rather than a one-time engagement.

In Argus, BAS framing means: for each vulnerability found, evaluate whether the
existing control stack would detect or block exploitation.

## Control layers to evaluate
1. **WAF (Web Application Firewall):** Does the WAF rule set cover this attack pattern?
2. **SIEM / SOAR:** Would the attack generate a detectable log event and alert?
3. **EDR:** Would the endpoint agent block payload execution?
4. **Network controls:** Would IDS/IPS signatures fire? Would firewall rules block C2?
5. **Application controls:** Input validation, auth checks, rate limiting.

## Control status classification
- **effective:** All relevant controls cover this attack; exploitation would be detected/blocked
- **partial:** Some controls cover it but gaps exist; exploitation might succeed or go undetected
- **missing:** No controls in place; exploitation would succeed silently

## Report framing
- Lead with control gap analysis, not vulnerability list
- Highlight `missing` and `partial` findings as the BAS remediation backlog
- Track control coverage trends over time — the goal is to move `missing` → `partial` → `effective`
- Schedule re-scans after control deployments to validate improvement
