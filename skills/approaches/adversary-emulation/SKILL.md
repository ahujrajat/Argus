---
name: adversary-emulation
description: Threat-informed adversary emulation using MITRE ATT&CK framework
version: 1.0.0
family: approaches
tools_allowed: [semgrep, trufflehog]
---

# Adversary Emulation

## Methodology
Adversary emulation replays the specific techniques of a known threat actor, mapped
to the MITRE ATT&CK framework. It is more prescriptive than open-ended pentesting:
given a target adversary (e.g. APT29, Lazarus Group, FIN7), the question is whether
the techniques that group uses would succeed against this codebase.

Reference: https://attack.mitre.org/

## ATT&CK tactic mapping for code findings
- SQL injection → T1190 (Exploit Public-Facing Application) → Initial Access
- Command injection → T1059 (Command and Scripting Interpreter) → Execution
- Hardcoded credentials → T1078 (Valid Accounts) → Persistence / Priv Esc
- Path traversal → T1083 (File and Directory Discovery) → Discovery
- Deserialization → T1059 / T1055 → Execution / Defense Evasion
- SSRF → T1090 (Proxy) / T1041 (Exfiltration over C2) → Lateral Movement / Exfiltration
- Weak auth → T1110 (Brute Force) → Credential Access

## Report framing
- Group findings by ATT&CK tactic phase
- Show the kill chain: Initial Access → Execution → Persistence → Exfiltration
- For each finding, name which real-world threat actors have used this technique
- Highlight technique chains that match a specific group's known playbook

## Common threat actor profiles
- APT29 (Cozy Bear): spearphishing, valid accounts, web shell, SSRF, credential dumping
- FIN7 (Carbanak): web app exploitation, supply chain, persistence via scheduled tasks
- Lazarus Group: supply chain compromise, credential theft, destructive payloads
