# Argus Phase 1 — Security Approaches Addendum

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Apply after:** all tasks in the four base Phase 1 plans are complete.

**Goal:** Add `SecurityApproach` as a first-class scan configuration. Six approaches selectable from the UI: penetration testing, adversary emulation, BAS, assumed breach, blue team, purple team. Each approach changes agent prompt framing, report language, and the skill set loaded. Infrastructure (GovernanceGate, orchestrator, pipeline) is approach-agnostic.

**Architecture:** `SecurityApproach` is an enum on `Scan`. Triage and Explainer agents receive the active approach in their `AgentContext` and select the matching prompt variant. Six approach skill files in `skills/approaches/` carry methodology-specific guidance. The dashboard scan trigger exposes the approach selector. Findings display an approach badge and adapt their column labels.

**Tech Stack:** Same as base plans.

## Global Constraints

- All constraints from base plans apply
- The default approach is `penetration_testing` — existing agent behavior is unchanged when this is selected
- Approach prompt variants must never include raw secret values — redact before any prompt assembly

---

### Mapping: approach → framing

| Approach | Core question | Triage framing | Report language |
|---|---|---|---|
| `penetration_testing` | What can be broken? | Breadth-first attacker, find + exploit all in scope | Attack scenarios, exploit payloads |
| `adversary_emulation` | Would we catch a specific threat actor? | MITRE ATT&CK TTP replay, named group techniques | ATT&CK technique IDs, TTP chains |
| `breach_and_attack_simulation` | Do our controls still work? | Control validation — would WAF/SIEM/EDR catch this? | Control status: effective / partial / missing |
| `assumed_breach` | Can an attacker move laterally once inside? | Post-compromise only — priv esc, lateral movement, persistence | Lateral movement paths, escalation chains |
| `blue_team` | How do we harden and detect? | Defender framing — detection rules, log sources, controls | Detection opportunities, hardening steps |
| `purple_team` | Does detection catch the attack? | Dual offensive + defensive — ATT&CK + detection rule | Technique + detection pair per finding |

---

### Task A1: SecurityApproach in data model + DB

**Files:**
- Modify: `core/model/entities.py` — add `SecurityApproach` enum, add `approach` field to `Scan`
- Modify: `core/db/tables.py` — add `approach` column to `ScanRow`
- Create: `core/db/migrations/versions/002_add_scan_approach.py` (or generate via alembic)
- Modify: `tests/core/model/test_entities.py` — add approach test

**Interfaces:**
- Produces: `SecurityApproach` enum importable from `core.model.entities`; `Scan.approach: SecurityApproach`

- [ ] **Step 1: Write failing test**

```python
# Add to tests/core/model/test_entities.py
from core.model.entities import SecurityApproach

def test_scan_approach_defaults_to_pentest():
    from core.model.entities import Scan, ScanMode
    from uuid import uuid4
    s = Scan(
        target_ref="github.com/acme/api@main",
        pipeline_config_id=uuid4(),
        mode=ScanMode.at_rest,
    )
    assert s.approach == SecurityApproach.penetration_testing

def test_all_approaches_valid():
    approaches = list(SecurityApproach)
    assert len(approaches) == 6
    labels = [a.value for a in approaches]
    assert "penetration_testing" in labels
    assert "adversary_emulation" in labels
    assert "breach_and_attack_simulation" in labels
    assert "assumed_breach" in labels
    assert "blue_team" in labels
    assert "purple_team" in labels
```

- [ ] **Step 2: Run — expect failure**

```bash
pytest tests/core/model/test_entities.py::test_scan_approach_defaults_to_pentest -v
```

Expected: `ImportError` or `AttributeError`

- [ ] **Step 3: Add SecurityApproach to core/model/entities.py**

Add after the existing enums (after `SkillStatus`):

```python
class SecurityApproach(str, Enum):
    penetration_testing = "penetration_testing"
    adversary_emulation = "adversary_emulation"
    breach_and_attack_simulation = "breach_and_attack_simulation"
    assumed_breach = "assumed_breach"
    blue_team = "blue_team"
    purple_team = "purple_team"
```

Add `approach` field to `Scan`:

```python
class Scan(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    target_ref: str
    pipeline_config_id: UUID
    mode: ScanMode
    approach: SecurityApproach = SecurityApproach.penetration_testing  # add this line
    status: ScanStatus = ScanStatus.pending
    # ... rest unchanged
```

- [ ] **Step 4: Add `approach` column to core/db/tables.py**

In `ScanRow`, add after `mode`:

```python
approach = Column(String, nullable=False, default="penetration_testing")
```

- [ ] **Step 5: Generate and run migration**

```bash
alembic revision --autogenerate -m "add scan approach"
alembic upgrade head
```

Expected: migration applies cleanly, `scans` table now has an `approach` column.

- [ ] **Step 6: Run tests — expect pass**

```bash
pytest tests/core/model/test_entities.py -v
```

Expected: all pass including the two new tests.

- [ ] **Step 7: Commit**

```bash
git add core/model/entities.py core/db/tables.py core/db/migrations/versions/ \
        tests/core/model/test_entities.py
git commit -m "feat: SecurityApproach enum and scan.approach field"
```

---

### Task A2: Approach-parameterized agent prompts

**Files:**
- Create: `core/agents/prompts/approaches.py` — per-approach system prompt variants
- Modify: `core/agents/prompts/triage.py` — make TRIAGE_SYSTEM approach-aware
- Modify: `core/agents/prompts/explainer.py` — make EXPLAINER_SYSTEM approach-aware
- Modify: `core/agents/triage.py` — pass approach from ctx
- Modify: `core/agents/explainer.py` — pass approach from ctx
- Modify: `core/agents/base.py` — add `approach` to `AgentContext`
- Modify: `tests/core/agents/test_triage.py` — test approach propagation

**Interfaces:**
- Produces: `get_triage_system(approach: SecurityApproach) -> str`, `get_explainer_system(approach: SecurityApproach) -> str`

- [ ] **Step 1: Write failing test**

```python
# Add to tests/core/agents/test_triage.py
from core.model.entities import SecurityApproach
from core.agents.prompts.approaches import get_triage_system

def test_approach_changes_triage_prompt():
    pentest = get_triage_system(SecurityApproach.penetration_testing)
    blue = get_triage_system(SecurityApproach.blue_team)
    assert pentest != blue
    assert "attacker" in pentest.lower() or "exploit" in pentest.lower()
    assert "detect" in blue.lower() or "harden" in blue.lower()

def test_all_approaches_have_prompts():
    for approach in SecurityApproach:
        prompt = get_triage_system(approach)
        assert len(prompt) > 100, f"Prompt for {approach} is too short"
```

- [ ] **Step 2: Run — expect failure**

```bash
pytest tests/core/agents/test_triage.py::test_approach_changes_triage_prompt -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create core/agents/prompts/approaches.py**

```python
# core/agents/prompts/approaches.py
from __future__ import annotations
from core.model.entities import SecurityApproach

_TRIAGE_SYSTEMS: dict[SecurityApproach, str] = {

    SecurityApproach.penetration_testing: """\
You are an adversarial security analyst conducting a penetration test.
Your job is to evaluate each finding through the eyes of a skilled attacker:
assume the attacker has read access to the source code, knows the framework,
and will chain vulnerabilities to maximize impact.

For each finding answer:
1. Can an attacker reach and trigger this? (reachability)
2. What is the minimal attack — exact payload, method, required auth?
3. What is the realistic blast radius — data exfiltration, auth bypass, RCE, pivot?
4. Does this chain with any other finding to enable a worse attack?
5. Is this exploitable or a false positive? Dismiss only with a clear reason.

Return ONLY a JSON object with the structure shown. No commentary outside the JSON.
""",

    SecurityApproach.adversary_emulation: """\
You are emulating a sophisticated threat actor using known techniques.
Map each finding to MITRE ATT&CK tactics and techniques.
For each finding, identify which phase of the ATT&CK lifecycle it enables:
Initial Access, Execution, Persistence, Privilege Escalation, Defense Evasion,
Credential Access, Discovery, Lateral Movement, Collection, Exfiltration, or Impact.

Focus on: which ATT&CK technique ID applies (e.g. T1078, T1190), what a real
threat actor group (default: APT29 / Cozy Bear) would do with this finding,
how it fits into a kill chain, and whether the technique is commonly attributed
to nation-state, criminal, or hacktivist actors.

Return ONLY a JSON object with the structure shown. Include `attack_technique_id`
and `att_ck_tactic` in each finding. No commentary outside the JSON.
""",

    SecurityApproach.breach_and_attack_simulation: """\
You are a BAS (Breach and Attack Simulation) platform validating whether existing
security controls would detect and block exploitation of each finding.

For each finding assess:
1. Would a WAF (Web Application Firewall) catch this exploit attempt?
2. Would a SIEM alert fire on the attack pattern?
3. Would EDR (Endpoint Detection and Response) block the payload execution?
4. Is there a network-level control (IDS/IPS, firewall rule) that would stop it?
5. Overall control status: effective (all controls cover it), partial (some cover it),
   or missing (no controls would catch it).

Prioritize findings where controls are missing or partial — those are gaps that
continuous simulation should flag. Findings where all controls are effective are
still valid but lower priority for immediate remediation.

Return ONLY a JSON object with the structure shown. Include `control_status` and
`control_gaps` fields per finding. No commentary outside the JSON.
""",

    SecurityApproach.assumed_breach: """\
You are a red team operator who has already gained initial access with standard
user credentials. Your goal is post-compromise: privilege escalation, lateral
movement, credential harvesting, data exfiltration, and persistence.

IGNORE findings that only help with initial access (e.g. login-page XSS, public
endpoint injection) unless they also enable privilege escalation or pivoting.

Focus exclusively on:
- Privilege escalation paths (what gets you from user to admin/root?)
- Lateral movement opportunities (what allows moving to other systems?)
- Credential harvesting (what exposes passwords, tokens, keys, session cookies?)
- Persistence mechanisms (what allows surviving a reboot or password reset?)
- Data exfiltration routes (what allows bulk data extraction?)

Score each finding by its value to an attacker who is already inside.
Dismiss anything that does not advance a post-compromise objective.

Return ONLY a JSON object with the structure shown. Include `post_compromise_value`
and `kill_chain_phase` per finding. No commentary outside the JSON.
""",

    SecurityApproach.blue_team: """\
You are a defensive security engineer conducting a hardening review.
Your job is NOT to exploit these findings — it is to use them to improve detection,
hardening, and response capabilities.

For each finding provide:
1. What log source and log entry would indicate exploitation attempts?
2. What SIEM detection rule or behavioral signature would fire?
3. What control (WAF rule, CSP header, auth check, input validation) would prevent it?
4. What hardening step closes the gap permanently?
5. What is the recommended remediation priority for a defender?

Frame everything as actionable defender recommendations. Do not describe attack
payloads — describe what defenders see in logs and what they should build.

Return ONLY a JSON object with the structure shown. Include `detection_opportunity`,
`recommended_control`, and `hardening_step` per finding. No commentary outside the JSON.
""",

    SecurityApproach.purple_team: """\
You are running a purple team exercise — red and blue working together.
For each finding provide BOTH the offensive technique AND the defensive detection.

Offensive side:
- Exact attack technique (minimal payload, entry point, expected outcome)
- MITRE ATT&CK technique ID and tactic

Defensive side:
- Which log source captures the attack (e.g., web server access log, Windows Event ID 4688)
- What behavioral indicator distinguishes attack traffic from legitimate traffic
- What detection rule would fire (describe in plain English, not SIEM syntax)
- Current detection coverage: covered / gap / unknown

The output of a purple team exercise is detection improvement.
For each finding with a detection gap, the output should directly feed a detection-engineering backlog.

Return ONLY a JSON object with the structure shown. Include `att_ck_technique_id`,
`att_ck_tactic`, `detection_log_source`, `detection_indicator`, `detection_coverage`
per finding. No commentary outside the JSON.
""",
}

_EXPLAINER_SYSTEMS: dict[SecurityApproach, str] = {

    SecurityApproach.penetration_testing: """\
You are a security advisor writing for the developer who owns the vulnerable code.
Lead every explanation with the attack: what an adversary does, what they get, how.
Then explain why the code is vulnerable. Then give the exact minimal fix.
Be specific, brief, actionable. Return only JSON.
""",

    SecurityApproach.adversary_emulation: """\
You are a threat intelligence analyst explaining findings to a developer.
Lead with the threat actor TTP: which ATT&CK technique this enables and which
known threat groups use it. Then explain the vulnerability. Then give the fix
and note which detection would have caught the technique.
Return only JSON.
""",

    SecurityApproach.breach_and_attack_simulation: """\
You are explaining to a security operations team whether their controls cover each finding.
Lead with the control validation result: which controls are effective and which are missing.
Then explain the vulnerability briefly. Then give both the fix and the control that should be
added or tuned to cover this attack pattern.
Return only JSON.
""",

    SecurityApproach.assumed_breach: """\
You are a red team operator debriefing after an assumed-breach engagement.
Lead with the post-compromise value: what this finding enables for an attacker already inside.
Focus on lateral movement, escalation, persistence, and data access.
Skip initial-access framing. Give the fix and note the post-compromise detection opportunity.
Return only JSON.
""",

    SecurityApproach.blue_team: """\
You are a security engineer writing a hardening recommendation.
Lead with the detection opportunity: what log entry or alert would indicate exploitation.
Then describe the control that prevents it. Then give the developer fix.
Frame everything from the defender's perspective — no exploit payloads.
Return only JSON.
""",

    SecurityApproach.purple_team: """\
You are writing a purple team exercise card for this finding.
Provide both sides: (1) the attack technique with ATT&CK mapping, and
(2) the detection rule and log source that should catch it.
The developer fix closes the vulnerability; the detection rule closes the visibility gap.
Return only JSON.
""",
}


def get_triage_system(approach: SecurityApproach) -> str:
    return _TRIAGE_SYSTEMS[approach]


def get_explainer_system(approach: SecurityApproach) -> str:
    return _EXPLAINER_SYSTEMS[approach]
```

- [ ] **Step 4: Update core/agents/base.py — add approach to AgentContext**

```python
# core/agents/base.py  — replace the existing dataclass
from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from core.model.entities import Scan, SecurityApproach

if TYPE_CHECKING:
    from core.governance.gate import GovernanceGate


@dataclass
class AgentContext:
    scan: Scan
    skills: list[str]
    budget_slice_usd: float
    gate: "GovernanceGate"
    approach: SecurityApproach = SecurityApproach.penetration_testing
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentOutput:
    agent_id: str
    data: dict[str, Any]
    cost_usd: float = 0.0
    skipped: bool = False
    skip_reason: str = ""
```

- [ ] **Step 5: Update core/agents/prompts/triage.py — use approach**

Replace the hardcoded `TRIAGE_SYSTEM` constant with a function call. The file now exports only `TRIAGE_USER_TEMPLATE` (unchanged) and re-exports `get_triage_system` for convenience:

```python
# core/agents/prompts/triage.py
from __future__ import annotations
from core.agents.prompts.approaches import get_triage_system  # re-export

TRIAGE_USER_TEMPLATE = """\
Codebase context:
- Root: {root}
- Languages: {languages}
- Frameworks: {frameworks}
- Entry points: {entry_points}
- Repo map (first 100 files):
{repo_map}

Findings to triage ({count} total, deduplicated):
{findings_json}

Return a JSON object:
{{
  "findings": [
    {{
      "dedup_key": "<exact dedup_key from input>",
      "confidence": <0.0-1.0>,
      "exploit_likelihood": <0.0-1.0>,
      "reachability": "<one sentence>",
      "attack_scenario": "<2-3 sentences: exact attack an adversary would perform>",
      "priority_score": <0.0-10.0>,
      "status": "open" | "dismissed",
      "false_positive_reason": "<reason if dismissed, null otherwise>",
      "attack_chain": "<other finding dedup_key this chains with, or null>",
      "att_ck_technique_id": "<e.g. T1190, or null if not applicable>",
      "att_ck_tactic": "<e.g. Initial Access, or null>",
      "control_status": "effective" | "partial" | "missing" | null,
      "control_gaps": "<description of missing controls, or null>",
      "post_compromise_value": "<value to insider attacker, or null>",
      "detection_opportunity": "<log source + indicator, or null>",
      "detection_coverage": "covered" | "gap" | "unknown" | null
    }}
  ]
}}
"""
```

- [ ] **Step 6: Update core/agents/triage.py — pass approach**

Replace the hardcoded `TRIAGE_SYSTEM` reference with a dynamic lookup. In `TriageAgent.run()`, replace:

```python
# OLD (remove this import at top of file):
from core.agents.prompts.triage import TRIAGE_SYSTEM, TRIAGE_USER_TEMPLATE

# NEW (replace with):
from core.agents.prompts.triage import TRIAGE_USER_TEMPLATE, get_triage_system
```

And in the `messages` list inside `run()`, replace `TRIAGE_SYSTEM` with `get_triage_system(ctx.approach)`:

```python
        result = await ctx.gate.complete(
            task_type="triage",
            messages=[
                {"role": "system", "content": get_triage_system(ctx.approach)},
                {"role": "user", "content": user_msg},
            ],
            agent_id=self.agent_id,
            scan_id=ctx.scan.id,
        )
```

- [ ] **Step 7: Update core/agents/prompts/explainer.py — use approach**

Replace the hardcoded `EXPLAINER_SYSTEM` with a re-export:

```python
# core/agents/prompts/explainer.py
from __future__ import annotations
from core.agents.prompts.approaches import get_explainer_system  # re-export

EXPLAINER_USER_TEMPLATE = """\
Explain each open finding below. For each, return:
- The attack / technique description (approach-appropriate framing)
- Why this specific code is vulnerable (one sentence)
- The exact minimal fix (code or diff)

Findings ({count} open):
{findings_json}

Return:
{{
  "explanations": [
    {{
      "dedup_key": "<exact dedup_key>",
      "explanation": "<framing-appropriate description. vulnerability cause. exact fix.>"
    }}
  ]
}}
"""
```

- [ ] **Step 8: Update core/agents/explainer.py — pass approach**

Replace `EXPLAINER_SYSTEM` with `get_explainer_system(ctx.approach)`:

```python
from core.agents.prompts.explainer import EXPLAINER_USER_TEMPLATE, get_explainer_system

# In run():
        result = await ctx.gate.complete(
            task_type="explanation",
            messages=[
                {"role": "system", "content": get_explainer_system(ctx.approach)},
                {"role": "user", "content": user_msg},
            ],
            agent_id=self.agent_id,
            scan_id=ctx.scan.id,
        )
```

- [ ] **Step 9: Update core/agents/orchestrator.py — propagate approach**

In `Orchestrator.run()`, when building `AgentContext` inside the loop, pass the scan's approach:

```python
            ctx = AgentContext(
                scan=scan,
                skills=[],
                budget_slice_usd=0.0,
                gate=self._gate,
                approach=scan.approach,   # add this line
                extra=extra,
            )
```

- [ ] **Step 10: Run all agent tests — expect pass**

```bash
pytest tests/core/agents/ -v
```

Expected: all pass. The mock gate responses are approach-agnostic (they return fixed JSON), so existing tests still pass with the new approach parameter defaulting to `penetration_testing`.

- [ ] **Step 11: Commit**

```bash
git add core/agents/prompts/ core/agents/base.py core/agents/triage.py \
        core/agents/explainer.py core/agents/orchestrator.py \
        tests/core/agents/test_triage.py
git commit -m "feat: approach-parameterized agent prompts (6 security methodologies)"
```

---

### Task A3: Six approach skill files

**Files:**
- Create: `skills/approaches/penetration-testing/SKILL.md`
- Create: `skills/approaches/adversary-emulation/SKILL.md`
- Create: `skills/approaches/breach-and-attack-simulation/SKILL.md`
- Create: `skills/approaches/assumed-breach/SKILL.md`
- Create: `skills/approaches/blue-team/SKILL.md`
- Create: `skills/approaches/purple-team/SKILL.md`

No test cycle.

- [ ] **Step 1: Create skills/approaches/penetration-testing/SKILL.md**

```markdown
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
```

- [ ] **Step 2: Create skills/approaches/adversary-emulation/SKILL.md**

```markdown
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
```

- [ ] **Step 3: Create skills/approaches/breach-and-attack-simulation/SKILL.md**

```markdown
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
```

- [ ] **Step 4: Create skills/approaches/assumed-breach/SKILL.md**

```markdown
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
```

- [ ] **Step 5: Create skills/approaches/blue-team/SKILL.md**

```markdown
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
```

- [ ] **Step 6: Create skills/approaches/purple-team/SKILL.md**

```markdown
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
```

- [ ] **Step 7: Commit**

```bash
git add skills/approaches/
git commit -m "feat: 6 security approach skill files (pentest, adversary emulation, BAS, assumed breach, blue team, purple team)"
```

---

### Task A4: API approach field + dashboard approach selector

**Files:**
- Modify: `core/api/routers/scans.py` — add `approach` to `TriggerScanRequest` and `ScanRow` persistence
- Modify: `surfaces/dashboard/src/api/client.ts` — add `approach` to `TriggerScanRequest` and `ScanDTO`
- Create: `surfaces/dashboard/src/pages/scans/TriggerScanModal.tsx`
- Modify: `surfaces/dashboard/src/pages/findings/FindingsPage.tsx` — add approach badge, wire TriggerScanModal

- [ ] **Step 1: Update core/api/routers/scans.py**

In `TriggerScanRequest`, add the `approach` field:

```python
from core.model.entities import ScanMode, SecurityApproach

class TriggerScanRequest(BaseModel):
    target_ref: str
    mode: ScanMode = ScanMode.at_rest
    pipeline_config_name: str = "full-scan"
    approach: SecurityApproach = SecurityApproach.penetration_testing
```

In `trigger_scan()`, pass `approach` when constructing `Scan` and when writing `ScanRow`:

```python
    # In trigger_scan(), update ScanRow construction:
    row = SR(
        id=str(scan_id),
        target_ref=body.target_ref,
        pipeline_config_id=str(uuid4()),
        mode=body.mode.value,
        approach=body.approach.value,    # add this
        status="pending",
        started_at=datetime.now(timezone.utc),
    )

    # Update Scan construction:
    scan = Scan(
        id=scan_id,
        target_ref=body.target_ref,
        pipeline_config_id=scan_id,
        mode=body.mode,
        approach=body.approach,          # add this
    )
```

Also update `list_scans` and `get_scan` responses to include `"approach": row.approach`.

- [ ] **Step 2: Write API test**

```python
# Add to tests/core/api/test_scans.py
async def test_trigger_scan_with_approach(client):
    resp = await client.post("/api/v1/scans/", json={
        "target_ref": "/tmp/test",
        "approach": "blue_team",
    })
    assert resp.status_code == 202
    assert "scan_id" in resp.json()
```

```bash
pytest tests/core/api/test_scans.py -v
```

Expected: all pass.

- [ ] **Step 3: Update surfaces/dashboard/src/api/client.ts**

Add `SecurityApproach` type and update interfaces:

```typescript
// Add after the existing imports
export type SecurityApproach =
  | "penetration_testing"
  | "adversary_emulation"
  | "breach_and_attack_simulation"
  | "assumed_breach"
  | "blue_team"
  | "purple_team";

export const APPROACH_LABELS: Record<SecurityApproach, string> = {
  penetration_testing: "Penetration Testing",
  adversary_emulation: "Adversary Emulation",
  breach_and_attack_simulation: "Breach & Attack Simulation",
  assumed_breach: "Assumed Breach",
  blue_team: "Blue Team",
  purple_team: "Purple Team",
};

export const APPROACH_DESCRIPTIONS: Record<SecurityApproach, string> = {
  penetration_testing: "Breadth-first: find and exploit all vulnerabilities in scope",
  adversary_emulation: "Replay threat actor TTPs mapped to MITRE ATT&CK",
  breach_and_attack_simulation: "Validate controls: would WAF/SIEM/EDR catch this?",
  assumed_breach: "Post-compromise: lateral movement, privilege escalation, persistence",
  blue_team: "Defensive: detection engineering, hardening, control gap analysis",
  purple_team: "Red + blue feedback loop: every attack paired with a detection rule",
};
```

Update `ScanDTO`:
```typescript
export interface ScanDTO {
  id: string;
  target_ref: string;
  status: string;
  mode: string;
  approach: SecurityApproach;
  cost_usd: number;
  started_at: string | null;
}
```

Update `api.triggerScan`:
```typescript
  triggerScan: (body: { target_ref: string; mode?: string; approach?: SecurityApproach }) =>
    post<{ scan_id: string }>("/api/v1/scans/", body),
```

- [ ] **Step 4: Create TriggerScanModal.tsx**

```tsx
// surfaces/dashboard/src/pages/scans/TriggerScanModal.tsx
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, SecurityApproach, APPROACH_LABELS, APPROACH_DESCRIPTIONS } from "../../api/client";

interface Props { onClose: () => void; }

const APPROACHES: SecurityApproach[] = [
  "penetration_testing",
  "adversary_emulation",
  "breach_and_attack_simulation",
  "assumed_breach",
  "blue_team",
  "purple_team",
];

const APPROACH_ICON: Record<SecurityApproach, string> = {
  penetration_testing: "⚔️",
  adversary_emulation: "🎭",
  breach_and_attack_simulation: "🔁",
  assumed_breach: "🔓",
  blue_team: "🛡️",
  purple_team: "🟣",
};

export function TriggerScanModal({ onClose }: Props) {
  const [targetRef, setTargetRef] = useState("");
  const [approach, setApproach] = useState<SecurityApproach>("penetration_testing");
  const [mode, setMode] = useState<"at_rest" | "real_time">("at_rest");
  const qc = useQueryClient();

  const mutation = useMutation({
    mutationFn: () => api.triggerScan({ target_ref: targetRef, mode, approach }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["scans"] }); onClose(); },
  });

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl p-8 w-[600px] max-h-[90vh] overflow-y-auto">
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-xl font-bold">New Scan</h2>
          <button onClick={onClose} className="text-gray-500 hover:text-white text-2xl leading-none">×</button>
        </div>

        <div className="flex flex-col gap-5">
          <div>
            <label className="text-xs text-gray-400 uppercase tracking-wide font-semibold mb-1.5 block">
              Target (path or repo URL)
            </label>
            <input
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm font-mono focus:outline-none focus:border-indigo-500"
              placeholder="/path/to/repo or github.com/org/repo@main"
              value={targetRef}
              onChange={(e) => setTargetRef(e.target.value)}
            />
          </div>

          <div>
            <label className="text-xs text-gray-400 uppercase tracking-wide font-semibold mb-2 block">
              Security Approach
            </label>
            <div className="grid grid-cols-2 gap-2">
              {APPROACHES.map((a) => (
                <button
                  key={a}
                  onClick={() => setApproach(a)}
                  className={`text-left px-4 py-3 rounded-xl border transition-all ${
                    approach === a
                      ? "border-indigo-500 bg-indigo-950"
                      : "border-gray-700 bg-gray-800 hover:border-gray-500"
                  }`}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-base">{APPROACH_ICON[a]}</span>
                    <span className="text-sm font-semibold text-white">{APPROACH_LABELS[a]}</span>
                  </div>
                  <p className="text-xs text-gray-400 leading-snug">{APPROACH_DESCRIPTIONS[a]}</p>
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="text-xs text-gray-400 uppercase tracking-wide font-semibold mb-1.5 block">Mode</label>
            <select
              className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm"
              value={mode}
              onChange={(e) => setMode(e.target.value as typeof mode)}
            >
              <option value="at_rest">At Rest — full scan</option>
              <option value="real_time">Real Time — diff only</option>
            </select>
          </div>

          <button
            onClick={() => mutation.mutate()}
            disabled={!targetRef || mutation.isPending}
            className="mt-2 w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white font-semibold rounded-xl py-3 transition-colors"
          >
            {mutation.isPending ? "Starting…" : `Start ${APPROACH_LABELS[approach]} Scan`}
          </button>

          {mutation.isError && (
            <p className="text-sm text-red-400">{String(mutation.error)}</p>
          )}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Update FindingsPage.tsx to add approach badge and scan trigger button**

In `FindingsPage.tsx`, import and wire `TriggerScanModal`:

```tsx
import { useState } from "react";
import { TriggerScanModal } from "../scans/TriggerScanModal";
import { APPROACH_LABELS, APPROACH_ICON } from "../../api/client";

// Add state:
const [showTrigger, setShowTrigger] = useState(false);

// In the header row, replace the scan select with:
<div className="flex items-center gap-3">
  <select ...>{/* existing scan select */}</select>
  <button
    onClick={() => setShowTrigger(true)}
    className="px-4 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-semibold rounded-lg transition-colors"
  >
    + New Scan
  </button>
</div>

// Add approach badge next to scan selector label:
{scans?.find(s => s.id === selectedScanId)?.approach && (
  <span className="px-2 py-0.5 rounded-full bg-gray-800 border border-gray-700 text-xs text-gray-300">
    {APPROACH_LABELS[scans!.find(s => s.id === selectedScanId)!.approach]}
  </span>
)}

// At the end of the return, add:
{showTrigger && <TriggerScanModal onClose={() => setShowTrigger(false)} />}
```

- [ ] **Step 6: Build dashboard**

```bash
cd surfaces/dashboard && npm run build
```

Expected: no errors.

- [ ] **Step 7: Commit**

```bash
cd ../..
git add core/api/routers/scans.py surfaces/dashboard/src/ tests/core/api/
git commit -m "feat: SecurityApproach in API + dashboard scan trigger with approach selector"
```

---

### Task A5: Update spec and decisions

**Files:**
- Modify: `docs/superpowers/specs/2026-06-17-argus-design.md` — add SecurityApproach to data model section
- Modify: `docs/DECISIONS.md` — update D-005 status to active

- [ ] **Step 1: Update spec data model section**

In the spec, in section 7 (Data Model), update the `Scan` entity to include `approach`:

```
Scan
────────────────
id (uuid)
target_ref
pipeline_config_id
mode
approach                ← SecurityApproach enum (new)
status
...
```

Add a note: "SecurityApproach drives agent prompt framing and skill selection. It does not change the pipeline topology — the same orchestrator handles all approaches."

- [ ] **Step 2: Update DECISIONS.md D-005**

Change status from "Spec updated; Phase 1 scaffolds the approach enum" to:
"Implemented in Phase 1 addendum: enum in data model, approach-parameterized agent prompts, 6 approach skill files, approach selector in dashboard scan trigger."

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/ docs/DECISIONS.md
git commit -m "docs: SecurityApproach implemented in Phase 1 — update spec and decisions"
```

---

## Phase 1 addendum complete — final check

```bash
# All unit tests must pass
pytest tests/ --ignore=tests/e2e -v

# Dashboard build
cd surfaces/dashboard && npm run build && cd ../..

# Confirm 6 approach skills exist
ls skills/approaches/
# Expected: penetration-testing  adversary-emulation  breach-and-attack-simulation
#           assumed-breach  blue-team  purple-team
```
