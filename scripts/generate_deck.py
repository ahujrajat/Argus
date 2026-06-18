"""
Generate Argus platform deck in Accenture Light theme.
Run: python scripts/generate_deck.py
Output: Argus_Platform_Deck.pptx
"""
from __future__ import annotations
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt
import copy

# ── Accenture Light palette ────────────────────────────────────────────────────
AC_PURPLE    = RGBColor(0xA1, 0x00, 0xFF)   # #A100FF  Accenture signature
AC_DARK      = RGBColor(0x1A, 0x1A, 0x1A)   # #1A1A1A  near-black text
AC_WHITE     = RGBColor(0xFF, 0xFF, 0xFF)   # #FFFFFF
AC_LIGHT_BG  = RGBColor(0xF7, 0xF7, 0xF7)  # #F7F7F7  slide background
AC_MID_GRAY  = RGBColor(0xCC, 0xCC, 0xCC)  # #CCCCCC  dividers
AC_DEEP      = RGBColor(0x46, 0x00, 0x73)   # #460073  dark purple accent
AC_GREEN     = RGBColor(0x00, 0xAB, 0x4D)   # #00AB4D  success / positive stat
AC_ORANGE    = RGBColor(0xFF, 0x6B, 0x00)   # #FF6B00  warning / highlight

SLIDE_W = Inches(13.33)
SLIDE_H = Inches(7.5)


def new_prs() -> Presentation:
    prs = Presentation()
    prs.slide_width  = SLIDE_W
    prs.slide_height = SLIDE_H
    return prs


def blank_layout(prs: Presentation):
    return prs.slide_layouts[6]  # completely blank


def add_rect(slide, left, top, width, height, fill_color, line_color=None, line_width=None):
    shape = slide.shapes.add_shape(1, left, top, width, height)  # MSO_SHAPE_TYPE.RECTANGLE=1
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill_color
    if line_color:
        shape.line.color.rgb = line_color
        if line_width:
            shape.line.width = line_width
    else:
        shape.line.fill.background()
    return shape


def add_textbox(slide, left, top, width, height, text, font_size=18,
                bold=False, color=AC_DARK, align=PP_ALIGN.LEFT,
                font_name="Arial", italic=False, wrap=True):
    txBox = slide.shapes.add_textbox(left, top, width, height)
    txBox.word_wrap = wrap
    tf = txBox.text_frame
    tf.word_wrap = wrap
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.size = Pt(font_size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color
    run.font.name = font_name
    return txBox


def add_multiline_textbox(slide, left, top, width, height, lines,
                          font_size=14, color=AC_DARK, bold=False,
                          line_spacing=1.2, font_name="Arial"):
    """Each item in lines is either a str or (str, dict) with overrides."""
    from pptx.util import Pt as _Pt
    from pptx.oxml.ns import qn
    from lxml import etree

    txBox = slide.shapes.add_textbox(left, top, width, height)
    txBox.word_wrap = True
    tf = txBox.text_frame
    tf.word_wrap = True

    for i, line in enumerate(lines):
        if isinstance(line, tuple):
            text, opts = line
        else:
            text, opts = line, {}

        p = tf.add_paragraph() if i > 0 else tf.paragraphs[0]
        p.alignment = opts.get("align", PP_ALIGN.LEFT)
        run = p.add_run()
        run.text = text
        run.font.size = _Pt(opts.get("size", font_size))
        run.font.bold = opts.get("bold", bold)
        run.font.color.rgb = opts.get("color", color)
        run.font.name = font_name
    return txBox


def purple_bar(slide, height=Inches(0.08)):
    """Thin purple bottom bar."""
    add_rect(slide, 0, SLIDE_H - height, SLIDE_W, height, AC_PURPLE)


def purple_left_bar(slide, width=Inches(0.06)):
    add_rect(slide, 0, 0, width, SLIDE_H, AC_PURPLE)


def slide_number(slide, num, total, color=AC_MID_GRAY):
    add_textbox(slide, SLIDE_W - Inches(1.0), SLIDE_H - Inches(0.35),
                Inches(0.8), Inches(0.3), f"{num} / {total}",
                font_size=9, color=color, align=PP_ALIGN.RIGHT)


# ══════════════════════════════════════════════════════════════════════════════
#  SLIDE BUILDERS
# ══════════════════════════════════════════════════════════════════════════════

def slide_cover(prs, num, total):
    """Full-bleed cover: purple left panel + white right panel."""
    slide = prs.slides.add_slide(blank_layout(prs))

    # Purple left panel (40%)
    panel_w = Inches(5.3)
    add_rect(slide, 0, 0, panel_w, SLIDE_H, AC_PURPLE)

    # White background right
    add_rect(slide, panel_w, 0, SLIDE_W - panel_w, SLIDE_H, AC_WHITE)

    # Product name on purple
    add_textbox(slide, Inches(0.4), Inches(1.5), Inches(4.5), Inches(1.2),
                "ARGUS", font_size=64, bold=True, color=AC_WHITE,
                align=PP_ALIGN.LEFT)
    add_textbox(slide, Inches(0.4), Inches(2.8), Inches(4.5), Inches(0.7),
                "Adaptive AI Security Platform", font_size=18, bold=False,
                color=AC_WHITE, align=PP_ALIGN.LEFT)
    add_textbox(slide, Inches(0.4), Inches(3.6), Inches(4.5), Inches(0.5),
                "Powered by Accenture", font_size=13, color=RGBColor(0xDD, 0xAA, 0xFF),
                align=PP_ALIGN.LEFT)

    # Tagline on white
    add_textbox(slide, Inches(5.7), Inches(1.8), Inches(7.0), Inches(1.5),
                "Find vulnerabilities faster.\nFix them smarter.\nSpend less.",
                font_size=26, bold=True, color=AC_DARK, align=PP_ALIGN.LEFT)
    add_textbox(slide, Inches(5.7), Inches(3.5), Inches(7.0), Inches(1.2),
                "Provider-agnostic · Cost-aware · Enterprise-ready\nSAST · SCA · DAST · IaC · Secrets · AI-assisted remediation",
                font_size=14, color=RGBColor(0x55, 0x55, 0x55), align=PP_ALIGN.LEFT)

    # Purple bottom bar
    purple_bar(slide)
    # Accenture > on white side
    add_textbox(slide, Inches(12.4), Inches(7.0), Inches(0.8), Inches(0.35),
                ">", font_size=22, bold=True, color=AC_PURPLE)
    slide_number(slide, num, total, color=AC_MID_GRAY)


def slide_problem(prs, num, total):
    slide = prs.slides.add_slide(blank_layout(prs))
    add_rect(slide, 0, 0, SLIDE_W, SLIDE_H, AC_LIGHT_BG)
    purple_left_bar(slide)

    add_textbox(slide, Inches(0.5), Inches(0.3), Inches(12), Inches(0.7),
                "The Problem", font_size=32, bold=True, color=AC_DARK)
    add_rect(slide, Inches(0.5), Inches(1.05), Inches(4.0), Inches(0.04), AC_PURPLE)

    problems = [
        ("Security teams are drowning in alerts", "Scanners produce thousands of noisy findings. Teams spend more time triaging than fixing."),
        ("AI tools are expensive and unpredictable", "LLM calls are unmetered, untested, and impossible to audit. Costs balloon overnight."),
        ("Toolchains are fragmented", "Semgrep, Grype, Checkov, ZAP — each with its own UI, format, and workflow. No unified view."),
        ("No governance or traceability", "Who approved that suppression? When was this policy last evaluated? Nobody knows."),
    ]

    for i, (title, body) in enumerate(problems):
        col = i % 2
        row = i // 2
        x = Inches(0.5) + col * Inches(6.3)
        y = Inches(1.4) + row * Inches(2.6)
        w = Inches(5.9)
        h = Inches(2.3)
        add_rect(slide, x, y, w, h, AC_WHITE)
        # accent top border
        add_rect(slide, x, y, w, Inches(0.06), AC_PURPLE)
        add_textbox(slide, x + Inches(0.2), y + Inches(0.15), w - Inches(0.4), Inches(0.45),
                    title, font_size=14, bold=True, color=AC_DARK)
        add_textbox(slide, x + Inches(0.2), y + Inches(0.65), w - Inches(0.4), Inches(1.5),
                    body, font_size=12, color=RGBColor(0x44, 0x44, 0x44))

    purple_bar(slide)
    slide_number(slide, num, total)


def slide_solution(prs, num, total):
    slide = prs.slides.add_slide(blank_layout(prs))
    add_rect(slide, 0, 0, SLIDE_W, SLIDE_H, AC_WHITE)
    purple_left_bar(slide)

    add_textbox(slide, Inches(0.5), Inches(0.3), Inches(12), Inches(0.7),
                "Introducing Argus", font_size=32, bold=True, color=AC_DARK)
    add_rect(slide, Inches(0.5), Inches(1.05), Inches(3.5), Inches(0.04), AC_PURPLE)

    add_textbox(slide, Inches(0.5), Inches(1.2), Inches(12.5), Inches(0.55),
                "A unified, AI-augmented security platform that orchestrates your existing tools, "
                "enforces cost discipline, and delivers actionable fixes — not more noise.",
                font_size=14, color=RGBColor(0x33, 0x33, 0x33))

    pillars = [
        (AC_PURPLE,  "Unified",      "One API, one dashboard, one audit log for all scanners."),
        (AC_DEEP,    "Cost-Aware",   "Every LLM call is budgeted, metered, and logged. No surprises."),
        (AC_GREEN,   "Actionable",   "AI generates diff-ready fixes, not just findings."),
        (AC_ORANGE,  "Governed",     "Policies, RBAC, suppression rules, and full audit trail."),
    ]

    for i, (color, title, body) in enumerate(pillars):
        x = Inches(0.4) + i * Inches(3.2)
        y = Inches(2.0)
        w = Inches(2.9)
        h = Inches(3.8)
        add_rect(slide, x, y, w, h, color)
        add_textbox(slide, x + Inches(0.15), y + Inches(0.2), w - Inches(0.3), Inches(0.6),
                    title, font_size=18, bold=True, color=AC_WHITE)
        add_textbox(slide, x + Inches(0.15), y + Inches(0.9), w - Inches(0.3), Inches(2.7),
                    body, font_size=13, color=AC_WHITE)

    purple_bar(slide)
    slide_number(slide, num, total)


def slide_key_metrics(prs, num, total):
    slide = prs.slides.add_slide(blank_layout(prs))
    add_rect(slide, 0, 0, SLIDE_W, SLIDE_H, AC_LIGHT_BG)
    purple_left_bar(slide)

    add_textbox(slide, Inches(0.5), Inches(0.3), Inches(12), Inches(0.7),
                "Platform at a Glance", font_size=32, bold=True, color=AC_DARK)
    add_rect(slide, Inches(0.5), Inches(1.05), Inches(3.0), Inches(0.04), AC_PURPLE)

    stats = [
        ("15", "Delivery Phases"),
        ("433", "Automated Tests"),
        ("6", "Scanner Adapters"),
        ("50+", "REST Endpoints"),
        ("0", "LLM Calls Without Budget Gate"),
        ("100%", "Findings with CWE / OWASP"),
    ]

    for i, (val, label) in enumerate(stats):
        col = i % 3
        row = i // 3
        x = Inches(0.5) + col * Inches(4.25)
        y = Inches(1.5) + row * Inches(2.5)
        w = Inches(3.9)
        h = Inches(2.1)
        add_rect(slide, x, y, w, h, AC_WHITE)
        add_rect(slide, x, y, w, Inches(0.06), AC_PURPLE)
        add_textbox(slide, x + Inches(0.15), y + Inches(0.18), w - Inches(0.3), Inches(1.0),
                    val, font_size=44, bold=True, color=AC_PURPLE, align=PP_ALIGN.CENTER)
        add_textbox(slide, x + Inches(0.15), y + Inches(1.25), w - Inches(0.3), Inches(0.6),
                    label, font_size=12, color=AC_DARK, align=PP_ALIGN.CENTER)

    purple_bar(slide)
    slide_number(slide, num, total)


def slide_architecture(prs, num, total):
    slide = prs.slides.add_slide(blank_layout(prs))
    add_rect(slide, 0, 0, SLIDE_W, SLIDE_H, AC_WHITE)
    purple_left_bar(slide)

    add_textbox(slide, Inches(0.5), Inches(0.25), Inches(12), Inches(0.65),
                "Architecture", font_size=32, bold=True, color=AC_DARK)
    add_rect(slide, Inches(0.5), Inches(0.95), Inches(3.0), Inches(0.04), AC_PURPLE)

    layers = [
        (AC_PURPLE, "SURFACES",  "Dashboard (React) · VS Code Extension · CI/CD Step · CLI Gate"),
        (AC_DEEP,   "API LAYER", "FastAPI · OpenAPI 3.1 · Rate Limiting · API Key Auth · SSE Streams"),
        (RGBColor(0x20,0x50,0xA0), "ORCHESTRATOR", "GovernanceGate · Budget Ledger · Agents Pipeline · Skills System"),
        (RGBColor(0x10,0x80,0x60), "SCANNERS (0 LLM tokens)", "Semgrep · TruffleHog · Grype · Checkov · Nuclei · OWASP ZAP"),
        (RGBColor(0x70,0x70,0x70), "PERSISTENCE", "PostgreSQL · SQLAlchemy 2 Async · Alembic Migrations · JSONB"),
    ]

    arrow_x = Inches(6.8)
    for i, (color, title, body) in enumerate(layers):
        y = Inches(1.1) + i * Inches(1.12)
        box_w = Inches(5.8)
        box_h = Inches(1.0)
        x = Inches(0.5)
        add_rect(slide, x, y, box_w, box_h, color)
        add_textbox(slide, x + Inches(0.15), y + Inches(0.06), Inches(1.8), Inches(0.45),
                    title, font_size=11, bold=True, color=AC_WHITE)
        add_textbox(slide, x + Inches(0.15), y + Inches(0.52), box_w - Inches(0.3), Inches(0.4),
                    body, font_size=10, color=RGBColor(0xEE,0xEE,0xEE))
        if i < len(layers) - 1:
            add_textbox(slide, x + Inches(2.4), y + box_h - Inches(0.05),
                        Inches(1.0), Inches(0.2), "▼", font_size=9, color=AC_MID_GRAY,
                        align=PP_ALIGN.CENTER)

    # Right panel: key integrations
    rx = Inches(6.8)
    add_textbox(slide, rx, Inches(1.1), Inches(6.0), Inches(0.4),
                "Integrations & Outputs", font_size=13, bold=True, color=AC_DARK)
    integrations = [
        ("Jira", "Auto-create tickets from findings"),
        ("PagerDuty", "Trigger incidents for critical scans"),
        ("Slack", "Rich Block Kit finding cards"),
        ("GitHub/GitLab", "Webhook triggers + PR fix creation"),
        ("Prometheus", "Metrics scrape endpoint"),
        ("OpenTelemetry", "Distributed tracing (OTLP)"),
        ("CycloneDX", "SBOM generation per scan"),
    ]
    for i, (name, desc) in enumerate(integrations):
        y = Inches(1.6) + i * Inches(0.73)
        add_rect(slide, rx, y, Inches(5.9), Inches(0.64), AC_LIGHT_BG)
        add_textbox(slide, rx + Inches(0.12), y + Inches(0.05), Inches(1.5), Inches(0.28),
                    name, font_size=11, bold=True, color=AC_DEEP)
        add_textbox(slide, rx + Inches(0.12), y + Inches(0.32), Inches(5.5), Inches(0.28),
                    desc, font_size=10, color=AC_DARK)

    purple_bar(slide)
    slide_number(slide, num, total)


def slide_tech_stack(prs, num, total):
    slide = prs.slides.add_slide(blank_layout(prs))
    add_rect(slide, 0, 0, SLIDE_W, SLIDE_H, AC_LIGHT_BG)
    purple_left_bar(slide)

    add_textbox(slide, Inches(0.5), Inches(0.25), Inches(12), Inches(0.65),
                "Technology Stack", font_size=32, bold=True, color=AC_DARK)
    add_rect(slide, Inches(0.5), Inches(0.95), Inches(3.0), Inches(0.04), AC_PURPLE)

    categories = [
        ("Backend", [
            "Python 3.12 + FastAPI 0.111",
            "Pydantic v2 (strict validation)",
            "SQLAlchemy 2 async + asyncpg",
            "Alembic (migrations)",
            "structlog (structured logging)",
        ]),
        ("AI / LLM", [
            "Anthropic Claude (multi-tier)",
            "Provider-agnostic routing",
            "GovernanceGate budget enforcement",
            "Token ledger per scan + monthly",
            "Batch mode for cost reduction",
        ]),
        ("Scanners", [
            "Semgrep (SAST, 1000+ rules)",
            "TruffleHog v3 (secrets)",
            "Grype (SCA, CVE matching)",
            "Checkov (IaC — Terraform/K8s)",
            "Nuclei + OWASP ZAP (DAST)",
        ]),
        ("Observability", [
            "Prometheus metrics (Counter/Histogram)",
            "OpenTelemetry SDK + OTLP export",
            "structlog JSON logging",
            "Full audit log (actor/action/before/after)",
            "SSE real-time scan trace stream",
        ]),
        ("Infrastructure", [
            "PostgreSQL 16 (JSONB for findings)",
            "slowapi rate limiting",
            "croniter scheduled scans",
            "python-pptx / httpx / croniter",
            "Docker Compose dev environment",
        ]),
        ("Security", [
            "API Key Auth (SHA-256 stored hash)",
            "RBAC: viewer / analyst / admin",
            "HMAC-SHA256 webhook verification",
            "DAST authorization gate",
            "Suppression rules + .argusignore",
        ]),
    ]

    for i, (cat, items) in enumerate(categories):
        col = i % 3
        row = i // 2
        x = Inches(0.5) + col * Inches(4.25)
        y = Inches(1.2) + row * Inches(2.85)
        w = Inches(3.95)
        h = Inches(2.6)
        add_rect(slide, x, y, w, h, AC_WHITE)
        add_rect(slide, x, y, w, Inches(0.06), AC_PURPLE)
        add_textbox(slide, x + Inches(0.15), y + Inches(0.12), w - Inches(0.3), Inches(0.38),
                    cat, font_size=13, bold=True, color=AC_DEEP)
        for j, item in enumerate(items):
            add_textbox(slide, x + Inches(0.25), y + Inches(0.6) + j * Inches(0.38),
                        w - Inches(0.4), Inches(0.36),
                        f"• {item}", font_size=10.5, color=AC_DARK)

    purple_bar(slide)
    slide_number(slide, num, total)


def slide_scanner_pipeline(prs, num, total):
    slide = prs.slides.add_slide(blank_layout(prs))
    add_rect(slide, 0, 0, SLIDE_W, SLIDE_H, AC_WHITE)
    purple_left_bar(slide)

    add_textbox(slide, Inches(0.5), Inches(0.25), Inches(12), Inches(0.65),
                "Scan Pipeline", font_size=32, bold=True, color=AC_DARK)
    add_rect(slide, Inches(0.5), Inches(0.95), Inches(2.5), Inches(0.04), AC_PURPLE)

    add_textbox(slide, Inches(0.5), Inches(1.05), Inches(12.5), Inches(0.4),
                "Every scan follows a configurable pipeline of agents. Deterministic scanners run first "
                "(zero LLM cost) — AI agents are invoked only when necessary.",
                font_size=12, color=RGBColor(0x44,0x44,0x44))

    steps = [
        (AC_PURPLE,               "1  Ingest",     "Clone repo / index files\nExtract language + framework signals"),
        (RGBColor(0x20,0x60,0xB0),"2  Scan",       "Run Semgrep, TruffleHog,\nGrype, Checkov, Nuclei, ZAP"),
        (RGBColor(0x10,0x80,0x60),"3  Triage",     "Deduplicate + fingerprint\nApply suppression rules"),
        (AC_DEEP,                 "4  Explain",    "AI: CWE/OWASP mapping\nBusiness-context explanation"),
        (AC_ORANGE,               "5  Fix",        "AI: diff-ready patch\nTest generation + validation"),
        (RGBColor(0x70,0x70,0x70),"6  Report",     "SBOM · Compliance report\nPolicy evaluation · Notify"),
    ]

    step_w = Inches(1.9)
    step_h = Inches(3.5)
    start_x = Inches(0.5)
    y = Inches(1.65)

    for i, (color, title, body) in enumerate(steps):
        x = start_x + i * (step_w + Inches(0.3))
        add_rect(slide, x, y, step_w, step_h, color)
        add_textbox(slide, x + Inches(0.1), y + Inches(0.15), step_w - Inches(0.2), Inches(0.55),
                    title, font_size=13, bold=True, color=AC_WHITE)
        add_textbox(slide, x + Inches(0.1), y + Inches(0.8), step_w - Inches(0.2), Inches(2.5),
                    body, font_size=11, color=AC_WHITE)
        if i < len(steps) - 1:
            add_textbox(slide, x + step_w + Inches(0.02), y + Inches(1.5),
                        Inches(0.28), Inches(0.5), "▶", font_size=14,
                        color=AC_MID_GRAY, align=PP_ALIGN.CENTER)

    # GovernanceGate callout
    gx = Inches(0.5)
    gy = Inches(5.5)
    add_rect(slide, gx, gy, Inches(12.5), Inches(0.85), RGBColor(0xF0,0xE8,0xFF))
    add_rect(slide, gx, gy, Inches(0.08), Inches(0.85), AC_PURPLE)
    add_textbox(slide, gx + Inches(0.25), gy + Inches(0.08), Inches(12.0), Inches(0.35),
                "GovernanceGate  —  enforces per-scan and monthly USD budgets before every LLM call. "
                "Blocks execution if limits are exceeded. All spend is logged to the cost ledger.",
                font_size=11, color=AC_DEEP)

    purple_bar(slide)
    slide_number(slide, num, total)


def slide_ai_cost(prs, num, total):
    slide = prs.slides.add_slide(blank_layout(prs))
    add_rect(slide, 0, 0, SLIDE_W, SLIDE_H, AC_LIGHT_BG)
    purple_left_bar(slide)

    add_textbox(slide, Inches(0.5), Inches(0.25), Inches(12), Inches(0.65),
                "Cost Discipline & AI Governance", font_size=32, bold=True, color=AC_DARK)
    add_rect(slide, Inches(0.5), Inches(0.95), Inches(4.5), Inches(0.04), AC_PURPLE)

    left_items = [
        ("Model Tiers", "flash (cheap, fast)\nstandard (balanced)\npremium (best quality)"),
        ("Budget Gates", "Per-scan USD limit\nMonthly aggregate limit\nHard-stop before overspend"),
        ("Token Ledger", "Every call logged with\ntokens_in, tokens_out, cost_usd\nQueryable via /cost/summary"),
        ("Batch Mode", "Up to 50% cost reduction\nfor non-latency-critical scans"),
    ]
    for i, (title, body) in enumerate(left_items):
        y = Inches(1.2) + i * Inches(1.45)
        add_rect(slide, Inches(0.5), y, Inches(5.8), Inches(1.3), AC_WHITE)
        add_rect(slide, Inches(0.5), y, Inches(0.07), Inches(1.3), AC_PURPLE)
        add_textbox(slide, Inches(0.7), y + Inches(0.08), Inches(5.4), Inches(0.4),
                    title, font_size=13, bold=True, color=AC_DARK)
        add_textbox(slide, Inches(0.7), y + Inches(0.48), Inches(5.4), Inches(0.75),
                    body, font_size=11, color=RGBColor(0x44,0x44,0x44))

    # Right: cost flow diagram (text-based)
    rx = Inches(7.0)
    add_textbox(slide, rx, Inches(1.1), Inches(5.9), Inches(0.4),
                "AI Call Flow", font_size=13, bold=True, color=AC_DARK)
    flow = [
        (AC_PURPLE, "Agent requests LLM call"),
        (AC_DEEP,   "GovernanceGate checks budget"),
        (AC_GREEN,  "✓ Within budget → call proceeds"),
        (AC_ORANGE, "✗ Over budget → blocked, logged"),
        (RGBColor(0x20,0x60,0xB0), "Response → token count recorded"),
        (RGBColor(0x10,0x80,0x60), "Cost ledger entry created"),
        (RGBColor(0x70,0x70,0x70), "Prometheus counter incremented"),
    ]
    for i, (color, text) in enumerate(flow):
        fy = Inches(1.65) + i * Inches(0.74)
        add_rect(slide, rx, fy, Inches(5.9), Inches(0.62), color)
        add_textbox(slide, rx + Inches(0.2), fy + Inches(0.12), Inches(5.5), Inches(0.38),
                    text, font_size=12, color=AC_WHITE)
        if i < len(flow) - 1:
            add_textbox(slide, rx + Inches(2.7), fy + Inches(0.62), Inches(0.5), Inches(0.15),
                        "▼", font_size=8, color=AC_MID_GRAY, align=PP_ALIGN.CENTER)

    purple_bar(slide)
    slide_number(slide, num, total)


def slide_security_features(prs, num, total):
    slide = prs.slides.add_slide(blank_layout(prs))
    add_rect(slide, 0, 0, SLIDE_W, SLIDE_H, AC_WHITE)
    purple_left_bar(slide)

    add_textbox(slide, Inches(0.5), Inches(0.25), Inches(12), Inches(0.65),
                "Enterprise Security Features", font_size=32, bold=True, color=AC_DARK)
    add_rect(slide, Inches(0.5), Inches(0.95), Inches(4.0), Inches(0.04), AC_PURPLE)

    features = [
        ("API Key Authentication", "SHA-256 hashed keys, expiry, revocation.\nARGUS_MASTER_KEY env var for bootstrap.", AC_PURPLE),
        ("RBAC", "viewer · analyst · admin roles.\nX-Argus-Role header enforcement.\n403 on insufficient role.", AC_DEEP),
        ("Rate Limiting", "60 req/min per IP via slowapi.\nConfigurable per-endpoint overrides.", RGBColor(0x20,0x60,0xB0)),
        ("Audit Log", "Every write action logged:\nactor, action, target, before, after.\nImmutable, queryable.", AC_GREEN),
        ("Suppression Rules", "Fingerprint · path_glob · rule_id.\nExpirable rules. .argusignore file.\nBulk suppress up to 500 at once.", AC_ORANGE),
        ("Policy Engine", "max_critical/high/medium/low thresholds.\nBlocked OWASP/CWE lists.\nCI gate exit-code enforcement.", RGBColor(0x70,0x10,0x70)),
        ("DAST Authorization Gate", "No DAST scan without explicit\ntarget_authorization record.\nEnvironment + expiry scoping.", RGBColor(0x80,0x40,0x00)),
        ("Webhook Verification", "HMAC-SHA256 for GitHub.\nToken-based for GitLab.\nReplayed payloads rejected.", RGBColor(0x00,0x60,0x80)),
    ]

    for i, (title, body, color) in enumerate(features):
        col = i % 4
        row = i // 4
        x = Inches(0.4) + col * Inches(3.2)
        y = Inches(1.2) + row * Inches(2.8)
        w = Inches(3.0)
        h = Inches(2.5)
        add_rect(slide, x, y, w, h, AC_LIGHT_BG)
        add_rect(slide, x, y, w, Inches(0.07), color)
        add_textbox(slide, x + Inches(0.12), y + Inches(0.15), w - Inches(0.24), Inches(0.42),
                    title, font_size=12, bold=True, color=color)
        add_textbox(slide, x + Inches(0.12), y + Inches(0.65), w - Inches(0.24), Inches(1.7),
                    body, font_size=10.5, color=AC_DARK)

    purple_bar(slide)
    slide_number(slide, num, total)


def slide_individual_use(prs, num, total):
    slide = prs.slides.add_slide(blank_layout(prs))
    add_rect(slide, 0, 0, SLIDE_W, SLIDE_H, AC_LIGHT_BG)
    purple_left_bar(slide)

    add_textbox(slide, Inches(0.5), Inches(0.25), Inches(12), Inches(0.65),
                "Individual Developer Workflow", font_size=32, bold=True, color=AC_DARK)
    add_rect(slide, Inches(0.5), Inches(0.95), Inches(4.5), Inches(0.04), AC_PURPLE)

    # Left: steps
    steps = [
        ("1  Install & Start",
         "docker compose up -d\nuv pip install -e '.[dev]'\nuvicorn core.api.app:app --reload"),
        ("2  Trigger a Scan",
         "POST /api/v1/scans\n{\"target_ref\": \"./my-project\",\n \"pipeline_config_name\": \"full-scan\"}"),
        ("3  Review Findings",
         "GET /api/v1/scans/{id}/findings?q=injection\nFilter by severity, OWASP, rule ID.\nCursor-paginated — 50 per page."),
        ("4  Apply AI Fix",
         "POST /api/v1/fixes/{id}/apply\nArgus opens a PR with the diff.\nReview, merge, done."),
        ("5  Export & Gate",
         "./scripts/ci-gate.sh --scan-id {id}\nExits 0 = clean. Non-zero = blocked.\nCSV export: /scans/export/csv"),
    ]

    for i, (title, code) in enumerate(steps):
        y = Inches(1.15) + i * Inches(1.15)
        add_rect(slide, Inches(0.5), y, Inches(6.2), Inches(1.05), AC_WHITE)
        add_rect(slide, Inches(0.5), y, Inches(0.07), Inches(1.05), AC_PURPLE)
        add_textbox(slide, Inches(0.7), y + Inches(0.05), Inches(2.0), Inches(0.38),
                    title, font_size=12, bold=True, color=AC_DEEP)
        add_textbox(slide, Inches(0.7), y + Inches(0.42), Inches(5.9), Inches(0.55),
                    code, font_size=10, color=AC_DARK,
                    font_name="Courier New")

    # Right: VS Code extension callout
    rx = Inches(7.1)
    add_rect(slide, rx, Inches(1.15), Inches(5.8), Inches(5.6), AC_PURPLE)
    add_textbox(slide, rx + Inches(0.25), Inches(1.35), Inches(5.3), Inches(0.6),
                "VS Code Extension", font_size=20, bold=True, color=AC_WHITE)
    vscode_items = [
        "Inline finding highlights as you type",
        "One-click AI fix application",
        "Real-time scan diff mode",
        "Cost budget visible in status bar",
        "No context switch — stay in editor",
    ]
    for i, item in enumerate(vscode_items):
        add_textbox(slide, rx + Inches(0.3), Inches(2.1) + i * Inches(0.72),
                    Inches(5.2), Inches(0.6),
                    f"✓  {item}", font_size=13, color=AC_WHITE)

    purple_bar(slide)
    slide_number(slide, num, total)


def slide_enterprise_use(prs, num, total):
    slide = prs.slides.add_slide(blank_layout(prs))
    add_rect(slide, 0, 0, SLIDE_W, SLIDE_H, AC_WHITE)
    purple_left_bar(slide)

    add_textbox(slide, Inches(0.5), Inches(0.25), Inches(12), Inches(0.65),
                "Enterprise Deployment", font_size=32, bold=True, color=AC_DARK)
    add_rect(slide, Inches(0.5), Inches(0.95), Inches(4.5), Inches(0.04), AC_PURPLE)

    scenarios = [
        ("CI/CD Integration", AC_PURPLE,
         "• Webhook triggers scan on every PR\n"
         "• ci-gate.sh blocks merge if policy fails\n"
         "• GitHub Actions + GitLab CI native support\n"
         "• Batch mode for nightly full-repo scans"),
        ("Security Team Operations", AC_DEEP,
         "• Organizations + workspaces per team/BU\n"
         "• RBAC: analysts triage, admins configure\n"
         "• Bulk suppress / assign findings to owners\n"
         "• Scheduled scans with cron expressions"),
        ("Compliance & Reporting", AC_GREEN,
         "• OWASP Top 10 + CWE compliance reports\n"
         "• CycloneDX 1.5 SBOM per scan\n"
         "• CSV export for audit evidence\n"
         "• Policy evaluations persisted + auditable"),
        ("Observability & SRE", AC_ORANGE,
         "• Prometheus metrics: scans, findings, cost\n"
         "• OpenTelemetry OTLP tracing (Jaeger/Tempo)\n"
         "• PagerDuty incidents for critical scans\n"
         "• Jira tickets auto-created from findings"),
    ]

    for i, (title, color, body) in enumerate(scenarios):
        col = i % 2
        row = i // 2
        x = Inches(0.5) + col * Inches(6.3)
        y = Inches(1.2) + row * Inches(2.8)
        w = Inches(5.9)
        h = Inches(2.55)
        add_rect(slide, x, y, w, h, AC_LIGHT_BG)
        add_rect(slide, x, y, w, Inches(0.07), color)
        add_textbox(slide, x + Inches(0.18), y + Inches(0.15), w - Inches(0.36), Inches(0.42),
                    title, font_size=14, bold=True, color=color)
        add_textbox(slide, x + Inches(0.18), y + Inches(0.65), w - Inches(0.36), Inches(1.8),
                    body, font_size=11, color=AC_DARK)

    purple_bar(slide)
    slide_number(slide, num, total)


def slide_api_reference(prs, num, total):
    slide = prs.slides.add_slide(blank_layout(prs))
    add_rect(slide, 0, 0, SLIDE_W, SLIDE_H, AC_LIGHT_BG)
    purple_left_bar(slide)

    add_textbox(slide, Inches(0.5), Inches(0.25), Inches(12), Inches(0.65),
                "API Surface (50+ Endpoints)", font_size=32, bold=True, color=AC_DARK)
    add_rect(slide, Inches(0.5), Inches(0.95), Inches(4.5), Inches(0.04), AC_PURPLE)

    groups = [
        ("Scans", "POST /scans  GET /scans  GET /scans/{id}\nGET /scans/{id}/findings  GET /scans/{id}/report\nGET /scans/{id}/sbom  POST /scans/batch\nGET /scans/export/csv"),
        ("Findings", "PATCH /findings/{id}  POST /findings/bulk-suppress\nPOST /findings/bulk-dismiss  POST /findings/bulk-assign"),
        ("Policies", "POST /policies  GET /policies  DELETE /policies/{id}\nPOST /policies/{id}/evaluate/{scan_id}"),
        ("Schedules", "POST /schedules  GET /schedules\nPATCH /schedules/{id}/enable|disable"),
        ("Suppressions", "POST /suppressions  GET /suppressions  DELETE /suppressions/{id}"),
        ("Analytics", "GET /analytics/trends  GET /analytics/mttr\nGET /analytics/top-rules  GET /analytics/summary"),
        ("Integrations", "POST /integrations/jira/issue\nPOST /integrations/pagerduty/trigger\nPOST /integrations/slack/finding"),
        ("Auth & Orgs", "POST /auth/keys  GET /auth/keys\nPOST /orgs  GET /orgs/{id}/members"),
        ("Observability", "GET /metrics (Prometheus)\nGET /api/v1/scans/{id}/events (SSE)"),
    ]

    for i, (title, endpoints) in enumerate(groups):
        col = i % 3
        row = i // 3
        x = Inches(0.5) + col * Inches(4.25)
        y = Inches(1.15) + row * Inches(1.9)
        w = Inches(3.95)
        h = Inches(1.72)
        add_rect(slide, x, y, w, h, AC_WHITE)
        add_rect(slide, x, y, w, Inches(0.06), AC_PURPLE)
        add_textbox(slide, x + Inches(0.12), y + Inches(0.1), w - Inches(0.24), Inches(0.35),
                    title, font_size=12, bold=True, color=AC_DEEP)
        add_textbox(slide, x + Inches(0.12), y + Inches(0.5), w - Inches(0.24), Inches(1.15),
                    endpoints, font_size=9, color=AC_DARK, font_name="Courier New")

    purple_bar(slide)
    slide_number(slide, num, total)


def slide_data_model(prs, num, total):
    slide = prs.slides.add_slide(blank_layout(prs))
    add_rect(slide, 0, 0, SLIDE_W, SLIDE_H, AC_WHITE)
    purple_left_bar(slide)

    add_textbox(slide, Inches(0.5), Inches(0.25), Inches(12), Inches(0.65),
                "Data Model — Key Tables", font_size=32, bold=True, color=AC_DARK)
    add_rect(slide, Inches(0.5), Inches(0.95), Inches(3.5), Inches(0.04), AC_PURPLE)

    tables = [
        ("scans", "id · target_ref · mode · status · cost_usd · model_usage (JSONB)"),
        ("findings", "id · scan_id · rule_id · severity · cwe · owasp_category · dedup_key · status · location (JSONB)"),
        ("fixes", "id · finding_id · diff · test · validation_result (JSONB) · status"),
        ("suppression_rules", "id · pattern_type · pattern · reason · expires_at"),
        ("scheduled_scans", "id · cron_expr · pipeline_config_name · enabled · next_run_at"),
        ("policies", "id · name · definition (JSONB) · active"),
        ("policy_evaluations", "id · scan_id · policy_id · passed · violations (JSONB)"),
        ("api_keys", "id · name · key_hash (SHA-256) · expires_at · revoked"),
        ("orgs / workspaces / org_members", "multi-tenancy + RBAC role assignment"),
        ("audit_log_entries", "actor · action · target · before/after (JSONB) · timestamp"),
        ("cost_ledger_entries", "scope_id · model_id · tier · tokens_in/out · cost_usd"),
        ("pipeline_configs", "id · name · version · definition (JSONB) · is_factory"),
    ]

    col_w = Inches(5.9)
    for i, (name, cols) in enumerate(tables):
        col = i % 2
        row = i // 2
        x = Inches(0.5) + col * Inches(6.35)
        y = Inches(1.15) + row * Inches(0.88)
        add_rect(slide, x, y, col_w, Inches(0.82), AC_LIGHT_BG)
        add_rect(slide, x, y, Inches(0.06), Inches(0.82), AC_PURPLE)
        add_textbox(slide, x + Inches(0.15), y + Inches(0.04), Inches(2.0), Inches(0.34),
                    name, font_size=11, bold=True, color=AC_DEEP)
        add_textbox(slide, x + Inches(0.15), y + Inches(0.42), col_w - Inches(0.25), Inches(0.34),
                    cols, font_size=9, color=AC_DARK, font_name="Courier New")

    purple_bar(slide)
    slide_number(slide, num, total)


def slide_phase_roadmap(prs, num, total):
    slide = prs.slides.add_slide(blank_layout(prs))
    add_rect(slide, 0, 0, SLIDE_W, SLIDE_H, AC_LIGHT_BG)
    purple_left_bar(slide)

    add_textbox(slide, Inches(0.5), Inches(0.25), Inches(12), Inches(0.65),
                "15-Phase Delivery Roadmap", font_size=32, bold=True, color=AC_DARK)
    add_rect(slide, Inches(0.5), Inches(0.95), Inches(4.5), Inches(0.04), AC_PURPLE)

    phases = [
        ("1–3",  "Foundation",    "SAST, secrets, triage, explainer, cost ledger, SSE, fix gen, VCS integration, VS Code extension"),
        ("4–5",  "Coverage",      "SCA (Grype), IaC (Checkov), batch API, skills system, PatternAgent, SkillCreatorAgent"),
        ("6–7",  "DAST & Audit",  "Nuclei + ZAP with authorization gate, audit log API, config API, eval harness"),
        ("8–9",  "Integration",   "CycloneDX SBOM, scan diff, GitHub/GitLab webhooks, API key auth, Prometheus metrics"),
        ("10–11","Governance",    "Suppression rules (.argusignore), cron scheduler, compliance report, policy engine, CI gate"),
        ("12–13","Enterprise",    "Multi-tenancy (orgs/workspaces), RBAC roles, Jira + PagerDuty + Slack integrations"),
        ("14–15","Production",    "Trend analytics, MTTR, CSV export, cursor pagination, full-text search, OpenTelemetry"),
    ]

    for i, (phase_num, title, desc) in enumerate(phases):
        y = Inches(1.15) + i * Inches(0.87)
        # Phase badge
        add_rect(slide, Inches(0.5), y, Inches(0.9), Inches(0.75), AC_PURPLE)
        add_textbox(slide, Inches(0.5), y + Inches(0.15), Inches(0.9), Inches(0.45),
                    phase_num, font_size=14, bold=True, color=AC_WHITE, align=PP_ALIGN.CENTER)
        # Title
        add_rect(slide, Inches(1.5), y, Inches(2.0), Inches(0.75), AC_DEEP)
        add_textbox(slide, Inches(1.55), y + Inches(0.15), Inches(1.9), Inches(0.45),
                    title, font_size=13, bold=True, color=AC_WHITE)
        # Description
        add_rect(slide, Inches(3.6), y, Inches(9.2), Inches(0.75), AC_WHITE)
        add_textbox(slide, Inches(3.7), y + Inches(0.12), Inches(9.0), Inches(0.52),
                    desc, font_size=11, color=AC_DARK)
        # Done badge
        add_rect(slide, Inches(12.9), y, Inches(0.3), Inches(0.75), AC_GREEN)

    add_textbox(slide, Inches(12.6), Inches(7.0), Inches(0.7), Inches(0.32),
                "■ Done", font_size=9, color=AC_GREEN)

    purple_bar(slide)
    slide_number(slide, num, total)


def slide_best_practices(prs, num, total):
    slide = prs.slides.add_slide(blank_layout(prs))
    add_rect(slide, 0, 0, SLIDE_W, SLIDE_H, AC_WHITE)
    purple_left_bar(slide)

    add_textbox(slide, Inches(0.5), Inches(0.25), Inches(12), Inches(0.65),
                "Best Practices & Tips", font_size=32, bold=True, color=AC_DARK)
    add_rect(slide, Inches(0.5), Inches(0.95), Inches(3.5), Inches(0.04), AC_PURPLE)

    left = [
        ("Start deterministic, add AI gradually",
         "Run full-scan pipeline first. Use pr-check (no AI) for fast PR feedback. Enable Explainer + Fix agents only when SAST findings stabilize."),
        ("Set budgets before enabling AI",
         "Configure ARGUS_BUDGET_PER_SCAN_USD and ARGUS_BUDGET_MONTHLY_USD. Start conservatively (e.g. $0.50/scan) and raise as you understand usage."),
        ("Use .argusignore for vendor code",
         "Suppress entire directories (vendor/**, node_modules/**) with path_glob rules before your first scan to avoid thousands of irrelevant findings."),
        ("Schedule nightly full scans",
         "Use POST /schedules with cron '0 2 * * *'. Reserve real-time mode for developer loop; batch mode for cost-sensitive overnight runs."),
    ]
    right = [
        ("Wire ci-gate.sh into merge gates",
         "Set max_critical=0 and block_on_any_critical=true in your production policy. Allow max_high=5 for PRs to avoid blocking developers on medium-risk findings."),
        ("Use bulk-assign for triage sprint planning",
         "POST /findings/bulk-assign to route security findings to the right team member. Filter by owasp_category first, then assign by domain expertise."),
        ("Monitor cost with Prometheus",
         "Scrape GET /metrics. Alert on argus_llm_cost_usd_total rate. Dashboard argus_scan_duration_seconds to catch regressions from new AI models."),
        ("Rotate API keys monthly",
         "POST /auth/keys creates a new key (key shown once). DELETE /auth/keys/{id} revokes the old one. Use ARGUS_MASTER_KEY only for initial bootstrap."),
    ]

    for i, (title, body) in enumerate(left):
        y = Inches(1.15) + i * Inches(1.48)
        add_rect(slide, Inches(0.5), y, Inches(6.1), Inches(1.35), AC_LIGHT_BG)
        add_rect(slide, Inches(0.5), y, Inches(0.07), Inches(1.35), AC_PURPLE)
        add_textbox(slide, Inches(0.7), y + Inches(0.08), Inches(5.8), Inches(0.38),
                    title, font_size=12, bold=True, color=AC_DARK)
        add_textbox(slide, Inches(0.7), y + Inches(0.5), Inches(5.8), Inches(0.8),
                    body, font_size=10.5, color=RGBColor(0x44,0x44,0x44))

    for i, (title, body) in enumerate(right):
        y = Inches(1.15) + i * Inches(1.48)
        add_rect(slide, Inches(7.0), y, Inches(6.1), Inches(1.35), AC_LIGHT_BG)
        add_rect(slide, Inches(7.0), y, Inches(0.07), Inches(1.35), AC_DEEP)
        add_textbox(slide, Inches(7.2), y + Inches(0.08), Inches(5.8), Inches(0.38),
                    title, font_size=12, bold=True, color=AC_DARK)
        add_textbox(slide, Inches(7.2), y + Inches(0.5), Inches(5.8), Inches(0.8),
                    body, font_size=10.5, color=RGBColor(0x44,0x44,0x44))

    purple_bar(slide)
    slide_number(slide, num, total)


def slide_roi(prs, num, total):
    slide = prs.slides.add_slide(blank_layout(prs))
    add_rect(slide, 0, 0, SLIDE_W, SLIDE_H, AC_LIGHT_BG)
    purple_left_bar(slide)

    add_textbox(slide, Inches(0.5), Inches(0.25), Inches(12), Inches(0.65),
                "Value & ROI", font_size=32, bold=True, color=AC_DARK)
    add_rect(slide, Inches(0.5), Inches(0.95), Inches(1.8), Inches(0.04), AC_PURPLE)

    # Big numbers
    metrics = [
        ("~70%", "Reduction in manual triage time\nthrough deduplication + AI explanation"),
        ("$0.50", "Average AI cost per full scan\nwith GovernanceGate budget enforcement"),
        ("<5 min", "Mean time to get a diff-ready fix\nfor a high-severity SAST finding"),
        ("100%", "Traceability — every suppression,\npolicy, and fix is auditable"),
    ]

    for i, (val, label) in enumerate(metrics):
        x = Inches(0.5) + i * Inches(3.2)
        y = Inches(1.2)
        w = Inches(2.9)
        h = Inches(2.2)
        add_rect(slide, x, y, w, h, AC_WHITE)
        add_rect(slide, x, y, w, Inches(0.08), AC_PURPLE)
        add_textbox(slide, x + Inches(0.1), y + Inches(0.18), w - Inches(0.2), Inches(0.85),
                    val, font_size=40, bold=True, color=AC_PURPLE, align=PP_ALIGN.CENTER)
        add_textbox(slide, x + Inches(0.1), y + Inches(1.1), w - Inches(0.2), Inches(1.0),
                    label, font_size=11, color=AC_DARK, align=PP_ALIGN.CENTER)

    # Comparison table
    headers = ["Capability", "Traditional SAST", "Argus"]
    rows_data = [
        ("Multi-scanner unified",    "No — separate tools",    "Yes — 6 adapters, one API"),
        ("AI-assisted remediation",  "No",                     "Yes — diff-ready patches"),
        ("Cost governance",          "N/A",                    "Hard budget gates per scan"),
        ("Policy as code",           "Manual review",          "Automated CI gate exit codes"),
        ("Compliance reporting",     "Manual export",          "OWASP/CWE/SBOM on demand"),
        ("Scheduling + webhooks",    "CI-only",                "Cron + GitHub/GitLab webhooks"),
    ]

    col_widths = [Inches(3.0), Inches(3.8), Inches(3.8)]
    col_x = [Inches(0.5), Inches(3.6), Inches(7.5)]
    header_y = Inches(3.75)

    for c, (header, cw, cx) in enumerate(zip(headers, col_widths, col_x)):
        bg = AC_PURPLE if c == 0 else (AC_DEEP if c == 1 else AC_GREEN)
        add_rect(slide, cx, header_y, cw, Inches(0.45), bg)
        add_textbox(slide, cx + Inches(0.1), header_y + Inches(0.05), cw - Inches(0.2), Inches(0.35),
                    header, font_size=12, bold=True, color=AC_WHITE)

    for r, row_vals in enumerate(rows_data):
        ry = header_y + Inches(0.45) + r * Inches(0.52)
        for c, (val, cw, cx) in enumerate(zip(row_vals, col_widths, col_x)):
            bg = AC_LIGHT_BG if r % 2 == 0 else AC_WHITE
            add_rect(slide, cx, ry, cw, Inches(0.5), bg)
            color = AC_GREEN if (c == 2 and val.startswith("Yes")) else (AC_DARK if c != 1 else RGBColor(0x88,0x00,0x00))
            add_textbox(slide, cx + Inches(0.1), ry + Inches(0.06), cw - Inches(0.2), Inches(0.38),
                        val, font_size=10, color=color)

    purple_bar(slide)
    slide_number(slide, num, total)


def slide_getting_started(prs, num, total):
    slide = prs.slides.add_slide(blank_layout(prs))
    add_rect(slide, 0, 0, SLIDE_W, SLIDE_H, AC_WHITE)
    purple_left_bar(slide)

    add_textbox(slide, Inches(0.5), Inches(0.25), Inches(12), Inches(0.65),
                "Getting Started in 5 Minutes", font_size=32, bold=True, color=AC_DARK)
    add_rect(slide, Inches(0.5), Inches(0.95), Inches(4.5), Inches(0.04), AC_PURPLE)

    steps = [
        ("Prerequisites",
         "• Python 3.12+  •  Docker & Docker Compose\n• uv (pip install uv)  •  PostgreSQL 16 (via Docker)\n• git  •  ANTHROPIC_API_KEY"),
        ("Clone & Install",
         "git clone https://github.com/ahujrajat/Argus.git\ncd Argus\nuv pip install -e '.[dev]'"),
        ("Start Infrastructure",
         "docker compose up -d          # starts PostgreSQL\nalembic upgrade head          # run DB migrations\nuvicorn core.api.app:app --reload"),
        ("Run First Scan",
         "curl -X POST http://localhost:8000/api/v1/scans \\\n  -H 'Content-Type: application/json' \\\n  -d '{\"target_ref\": \".\", \"pipeline_config_name\": \"full-scan\"}'"),
        ("View Results",
         "Open http://localhost:8000/docs   # Swagger UI\ncurl http://localhost:8000/api/v1/scans  # list scans\ncurl 'http://localhost:8000/api/v1/scans/{id}/findings?q=sql'"),
    ]

    for i, (title, code) in enumerate(steps):
        y = Inches(1.15) + i * Inches(1.2)
        # step number circle
        add_rect(slide, Inches(0.5), y + Inches(0.1), Inches(0.55), Inches(0.55), AC_PURPLE)
        add_textbox(slide, Inches(0.5), y + Inches(0.1), Inches(0.55), Inches(0.55),
                    str(i + 1), font_size=16, bold=True, color=AC_WHITE, align=PP_ALIGN.CENTER)
        add_textbox(slide, Inches(1.2), y + Inches(0.05), Inches(2.2), Inches(0.38),
                    title, font_size=13, bold=True, color=AC_DARK)
        add_rect(slide, Inches(1.2), y + Inches(0.48), Inches(11.6), Inches(0.65), AC_LIGHT_BG)
        add_textbox(slide, Inches(1.35), y + Inches(0.51), Inches(11.3), Inches(0.58),
                    code, font_size=10, color=AC_DARK, font_name="Courier New")

    purple_bar(slide)
    slide_number(slide, num, total)


def slide_closing(prs, num, total):
    slide = prs.slides.add_slide(blank_layout(prs))

    # Full purple background
    add_rect(slide, 0, 0, SLIDE_W, SLIDE_H, AC_PURPLE)

    add_textbox(slide, Inches(1.5), Inches(1.8), Inches(10.5), Inches(1.2),
                "ARGUS", font_size=72, bold=True, color=AC_WHITE, align=PP_ALIGN.CENTER)
    add_textbox(slide, Inches(1.5), Inches(3.1), Inches(10.5), Inches(0.65),
                "Adaptive AI Security Platform", font_size=24, color=RGBColor(0xDD,0xAA,0xFF),
                align=PP_ALIGN.CENTER)

    add_rect(slide, Inches(4.0), Inches(3.9), Inches(5.3), Inches(0.04), AC_WHITE)

    add_textbox(slide, Inches(1.5), Inches(4.1), Inches(10.5), Inches(0.6),
                "github.com/ahujrajat/Argus", font_size=16,
                color=RGBColor(0xDD,0xAA,0xFF), align=PP_ALIGN.CENTER)

    add_textbox(slide, Inches(1.5), Inches(5.0), Inches(10.5), Inches(0.55),
                "Built with ♥ by Rajat Ahuja · Accenture", font_size=14,
                color=RGBColor(0xCC,0xCC,0xFF), align=PP_ALIGN.CENTER)

    add_textbox(slide, Inches(11.5), Inches(6.9), Inches(1.7), Inches(0.45),
                ">", font_size=28, bold=True, color=AC_WHITE)
    slide_number(slide, num, total, color=RGBColor(0xCC,0xAA,0xFF))


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def build_deck(output_path: str = "Argus_Platform_Deck.pptx") -> None:
    prs = new_prs()

    builders = [
        slide_cover,
        slide_problem,
        slide_solution,
        slide_key_metrics,
        slide_architecture,
        slide_tech_stack,
        slide_scanner_pipeline,
        slide_ai_cost,
        slide_security_features,
        slide_individual_use,
        slide_enterprise_use,
        slide_api_reference,
        slide_data_model,
        slide_phase_roadmap,
        slide_best_practices,
        slide_roi,
        slide_getting_started,
        slide_closing,
    ]

    total = len(builders)
    for i, builder in enumerate(builders):
        builder(prs, i + 1, total)

    prs.save(output_path)
    print(f"Saved: {output_path}  ({total} slides)")


if __name__ == "__main__":
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else "Argus_Platform_Deck.pptx"
    build_deck(out)
