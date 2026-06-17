---
name: purple-team
description: Purple team — red and blue in a feedback loop, every attack paired with a detection
version: 1.0.0
family: approaches
tools_allowed: [semgrep, trufflehog]
---

# Purple Team

## Methodology
Purple teaming puts red and blue in the same room in a feedback loop.
Every offensive technique immediately yields a detection improvement.
It is usually a function or exercise rather than a standing team.

The output of purple team is not just a finding list — it is a detection-engineering backlog:
for every attack technique demonstrated, a new or updated detection rule is the deliverable.

## Exercise structure
1. Red identifies a finding and demonstrates the attack (minimal PoC)
2. Blue observes the attack in their monitoring stack — what fired? what was missed?
3. Red and blue agree on the detection gap
4. Blue writes the detection rule; Red verifies the rule fires on the technique
5. Repeat — the coverage metric should improve each sprint

## For each finding, produce:
- **Attack card:** technique, ATT&CK ID, minimal PoC
- **Detection card:** log source, behavioral indicator, proposed SIEM rule description
- **Coverage assessment:** covered / gap / unknown

## ATT&CK detection opportunity mapping
| Technique | Log source | Behavioral indicator |
|---|---|---|
| T1190 Web exploit | Web server access log | High 500/error rate from single IP |
| T1059 Command exec | Process creation (auditd / Sysmon 4688) | Unusual parent process spawning shell |
| T1078 Valid accounts | Auth logs | Login outside normal hours / geolocation |
| T1083 File enumeration | File access audit | Rapid sequential file reads |
| T1041 Exfiltration | Network flow logs | Outbound data spike to new destination |

## Report framing
- Present as paired cards: attack + detection
- Highlight detection gaps as the highest-priority backlog items
- Track coverage percentage: (findings with detection rule) / (total open findings)
- A purple team exercise is only complete when every finding has a detection card
