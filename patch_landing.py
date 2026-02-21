"""
OrQuanta Landing Page + Remaining Files Patcher
Patches CSS vars, hero content, features, pricing, footer, 
and cleans out all remaining orquanta references.
"""
from pathlib import Path

ROOT = Path(r"c:\ai-gpu-cloud")
LP   = ROOT / "v4" / "landing" / "index.html"

# ─── CSS variable patch ───────────────────────────────────────────────────────
CSS_OLD = """        :root {
            --bg: #080910;
            --surface: #0f1117;
            --surface2: #161822;
            --border: rgba(255, 255, 255, 0.06);
            --primary: #6366f1;
            --primary-glow: rgba(99, 102, 241, 0.3);
            --accent: #06b6d4;
            --accent-glow: rgba(6, 182, 212, 0.25);
            --green: #10b981;
            --amber: #f59e0b;
            --red: #ef4444;
            --text-primary: #f1f5f9;
            --text-secondary: #94a3b8;
            --text-muted: #475569;
            --radius: 12px;
            --radius-lg: 20px;
        }"""

CSS_NEW = """        :root {
            /* ── OrQuanta Design Tokens ── */
            --bg: #0A0B14;
            --surface: #0F1624;
            --surface2: #131D2E;
            --border: rgba(0, 212, 255, 0.08);
            --primary: #00D4FF;
            --primary-glow: rgba(0, 212, 255, 0.25);
            --secondary: #7B2FFF;
            --secondary-glow: rgba(123, 47, 255, 0.25);
            --accent: #00D4FF;
            --accent-glow: rgba(0, 212, 255, 0.20);
            --green: #00FF88;
            --amber: #FFB800;
            --red: #FF4444;
            --text-primary: #E8EAF6;
            --text-secondary: #8892A4;
            --text-muted: #4A5568;
            --radius: 12px;
            --radius-lg: 20px;
            --gradient: linear-gradient(135deg, #00D4FF, #7B2FFF);
        }"""

# ─── Grid background color ─────────────────────────────────────────────────────
GRID_OLD = """            background-image:
                linear-gradient(rgba(99, 102, 241, 0.03) 1px, transparent 1px),
                linear-gradient(90deg, rgba(99, 102, 241, 0.03) 1px, transparent 1px);"""
GRID_NEW = """            background-image:
                linear-gradient(rgba(0, 212, 255, 0.03) 1px, transparent 1px),
                linear-gradient(90deg, rgba(0, 212, 255, 0.03) 1px, transparent 1px);"""

# ─── Glow orbs ────────────────────────────────────────────────────────────────
ORB_OLD1 = "        .glow-orb-1 {\n            width: 600px;\n            height: 600px;\n            background: rgba(99, 102, 241, 0.15);\n            top: -200px;\n            left: -100px;\n        }"
ORB_NEW1 = "        .glow-orb-1 {\n            width: 600px;\n            height: 600px;\n            background: rgba(0, 212, 255, 0.12);\n            top: -200px;\n            left: -100px;\n        }"

ORB_OLD2 = "        .glow-orb-2 {\n            width: 500px;\n            height: 500px;\n            background: rgba(6, 182, 212, 0.10);\n            top: 200px;\n            right: -100px;\n        }"
ORB_NEW2 = "        .glow-orb-2 {\n            width: 500px;\n            height: 500px;\n            background: rgba(123, 47, 255, 0.10);\n            top: 200px;\n            right: -100px;\n        }"

# ─── Hero badge border ─────────────────────────────────────────────────────────
BADGE_OLD = "            border: 1px solid rgba(99, 102, 241, 0.4);\n            background: rgba(99, 102, 241, 0.1);"
BADGE_NEW = "            border: 1px solid rgba(0, 212, 255, 0.4);\n            background: rgba(0, 212, 255, 0.08);"

# ─── gradient-text ────────────────────────────────────────────────────────────
GRAD_TEXT_OLD = "            background: linear-gradient(135deg, #fff 30%, var(--primary), var(--accent));"
GRAD_TEXT_NEW = "            background: linear-gradient(135deg, #ffffff 0%, #00D4FF 55%, #7B2FFF 100%);"

# ─── Primary buttons (old indigo → OrQuanta blue/purple) ──────────────────────
BTN_P_OLD  = "            background: linear-gradient(135deg, var(--primary), #4f46e5);"
BTN_P_NEW  = "            background: linear-gradient(135deg, var(--primary), var(--secondary));"

# ─── btn-hero outline hover ───────────────────────────────────────────────────
BTN_HO_OLD = "            background: rgba(99, 102, 241, 0.08);"
BTN_HO_NEW = "            background: rgba(0, 212, 255, 0.06);"

# ─── feature card hover ───────────────────────────────────────────────────────
FC_HOVER_OLD = "            border-color: rgba(99, 102, 241, 0.3);"
FC_HOVER_NEW = "            border-color: rgba(0, 212, 255, 0.3);"

# ─── section-label background ─────────────────────────────────────────────────
SL_OLD = "            background: rgba(99, 102, 241, 0.1);"
SL_NEW = "            background: rgba(0, 212, 255, 0.08);"

# ─── steps grid gradient ──────────────────────────────────────────────────────
STEPS_OLD = "            background: linear-gradient(90deg, transparent, var(--primary), var(--accent), transparent);"
STEPS_NEW = "            background: linear-gradient(90deg, transparent, var(--primary), var(--secondary), transparent);"

# ─── step-num background ──────────────────────────────────────────────────────
SN_OLD = "            background: linear-gradient(135deg, var(--primary), var(--accent));"
SN_NEW = "            background: linear-gradient(135deg, var(--primary), var(--secondary));"

# ─── popular card ─────────────────────────────────────────────────────────────
POP_OLD = "            background: linear-gradient(180deg, rgba(99, 102, 241, 0.12) 0%, var(--surface2) 100%);"
POP_NEW = "            background: linear-gradient(180deg, rgba(0, 212, 255, 0.08) 0%, var(--surface2) 100%);"

# ─── btn pricing ──────────────────────────────────────────────────────────────
BTN_PR_OLD = "            background: linear-gradient(135deg, var(--primary), #4f46e5);"
BTN_PR_NEW = "            background: linear-gradient(135deg, var(--primary), var(--secondary));"

# ─── metric gradient ──────────────────────────────────────────────────────────
MET_OLD = "            background: linear-gradient(135deg, var(--primary), var(--accent));"
MET_NEW = "            background: linear-gradient(135deg, var(--primary), var(--secondary));"


def apply_all(html: str) -> str:
    patches = [
        (CSS_OLD,       CSS_NEW,       "CSS vars"),
        (GRID_OLD,      GRID_NEW,      "grid bg"),
        (ORB_OLD1,      ORB_NEW1,      "orb1"),
        (ORB_OLD2,      ORB_NEW2,      "orb2"),
        (BADGE_OLD,     BADGE_NEW,     "badge"),
        (GRAD_TEXT_OLD, GRAD_TEXT_NEW, "gradient-text"),
        (FC_HOVER_OLD,  FC_HOVER_NEW,  "feature card hover"),
        (SL_OLD,        SL_NEW,        "section-label bg"),
        (STEPS_OLD,     STEPS_NEW,     "steps gradient"),
        (POP_OLD,       POP_NEW,       "popular card"),
        (MET_OLD,       MET_NEW,       "metric gradient"),
    ]
    btn_old = "            background: linear-gradient(135deg, var(--primary), #4f46e5);"
    btn_new = "            background: linear-gradient(135deg, var(--primary), var(--secondary));"

    # Replace all occurrences of old indigo buttons
    html = html.replace(btn_old, btn_new)
    html = html.replace(BTN_HO_OLD, BTN_HO_NEW)
    html = html.replace(SN_OLD, SN_NEW)

    for old, new, label in patches:
        if old in html:
            html = html.replace(old, new)
            print(f"  [OK] {label}")
        else:
            print(f"  [--] {label} (not found, may already be patched)")
    return html


def patch_meta(html: str) -> str:
    """Update title, meta description, og tags."""
    old_title = "<title>OrQuanta Agentic v1.0 — AI-Native GPU Cloud Management</title>"
    new_title = "<title>OrQuanta — Orchestrate. Optimize. Evolve.</title>"
    if old_title in html:
        html = html.replace(old_title, new_title)
        print("  [OK] title")

    old_desc = 'content="OrQuanta Agentic v1.0 — The AI Operating System for GPU Cloud. Automatically schedule, optimize, and monitor GPU workloads across AWS, GCP, Azure, and CoreWeave. Start free for 14 days." />'
    new_desc = 'content="OrQuanta is the first Agentic AI Cloud GPU platform that autonomously orchestrates, optimizes and heals your GPU workloads across AWS, GCP, Azure and CoreWeave. 14-day free trial, no credit card required." />'
    if old_desc in html:
        html = html.replace(old_desc, new_desc)
        print("  [OK] meta description")

    old_og_title = 'content="OrQuanta Agentic — AI That Manages Your GPU Cloud" />'
    new_og_title = 'content="OrQuanta — Orchestrate. Optimize. Evolve." />'
    if old_og_title in html:
        html = html.replace(old_og_title, new_og_title)
        print("  [OK] og:title")

    old_og_desc = 'content="One natural language goal. Five AI agents. Real GPU instances spinning up in seconds." />'
    new_og_desc = 'content="The first Agentic AI platform for autonomous GPU cloud management. Save 47% on GPU costs. Deploy in minutes." />'
    if old_og_desc in html:
        html = html.replace(old_og_desc, new_og_desc)
        print("  [OK] og:description")

    # Add twitter/og extras if not present
    if 'twitter:card' not in html:
        html = html.replace(
            '<meta name="theme-color"',
            '<meta name="twitter:card" content="summary_large_image" />\n    <meta name="twitter:site" content="@OrQuantaAI" />\n    <meta property="og:type" content="website" />\n    <meta property="og:url" content="https://orquanta.ai" />\n    <meta name="theme-color"'
        )
        print("  [OK] twitter/og extras")
    return html


def patch_hero_content(html: str) -> str:
    """Update hero badge text."""
    old_badge = ">⚡ OrQuanta Agentic v1.0 — Now Live</span>"
    new_badge = ">⚡ OrQuanta Agentic v1.0 — Orchestrate. Optimize. Evolve.</span>"
    if old_badge in html:
        html = html.replace(old_badge, new_badge)
        print("  [OK] hero badge text")

    # Ensure nav logo text
    html = html.replace(">OrQuanta<", ">OrQuanta<")

    return html


def patch_nav_logo(html: str) -> str:
    """Replace plain nav logo icon with OQ monogram SVG."""
    OLD_ICON = '<div class="nav-logo-icon">⚡</div>'
    NEW_ICON = '''<div class="nav-logo-icon" style="background:linear-gradient(135deg,#00D4FF,#7B2FFF);border-radius:10px;width:38px;height:38px;display:flex;align-items:center;justify-content:center;">
                <svg width="22" height="22" viewBox="0 0 80 80" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <defs>
                        <linearGradient id="nav-oq-g" x1="0%" y1="0%" x2="100%" y2="100%">
                            <stop offset="0%" stop-color="#fff" stop-opacity="0.95"/>
                            <stop offset="100%" stop-color="#E8EAF6" stop-opacity="0.7"/>
                        </linearGradient>
                    </defs>
                    <circle cx="30" cy="40" r="12" stroke="url(#nav-oq-g)" stroke-width="6" fill="none"/>
                    <line x1="39" y1="49" x2="44" y2="54" stroke="url(#nav-oq-g)" stroke-width="5.5" stroke-linecap="round"/>
                    <path d="M50 27 L50 47 Q50 53 56 53 Q62 53 62 47 L62 34 Q62 27 56 27 Z" fill="none" stroke="url(#nav-oq-g)" stroke-width="5" stroke-linejoin="round"/>
                    <line x1="59" y1="50" x2="65" y2="56" stroke="url(#nav-oq-g)" stroke-width="5" stroke-linecap="round"/>
                </svg>
            </div>'''
    if OLD_ICON in html:
        html = html.replace(OLD_ICON, NEW_ICON)
        print("  [OK] nav logo SVG")
    return html


def patch_footer(html: str) -> str:
    """Update footer copyright and tagline."""
    OLD_COPY = ">© 2025 OrQuanta. All rights reserved.<"
    NEW_COPY = ">© 2026 OrQuanta AI, Inc. All rights reserved.<"
    if OLD_COPY in html:
        html = html.replace(OLD_COPY, NEW_COPY)
        print("  [OK] footer copyright year")

    old_p = ">© 2024 OrQuanta. All rights reserved.<"
    if old_p in html:
        html = html.replace(old_p, ">© 2026 OrQuanta AI, Inc. All rights reserved.<")
    return html


def clean_remaining_orquanta(html: str) -> tuple[str, int]:
    """Final pass — remove any remaining orquanta references."""
    pairs = [
        ("OrQuanta Agentic v4.0", "OrQuanta Agentic v1.0"),
        ("OrQuanta Agentic",      "OrQuanta Agentic"),
        ("OrQuanta",              "OrQuanta"),
        ("ORQUANTA",              "ORQUANTA"),
        ("orquanta",              "orquanta"),
        ("Meta-Brain",         "OrMind"),
    ]
    count = 0
    for old, new in pairs:
        n = html.count(old)
        if n:
            html = html.replace(old, new)
            count += n
    return html, count


def main():
    print(f"\n{'='*55}")
    print("OrQuanta Landing Page Brand Patcher")
    print(f"{'='*55}")

    html = LP.read_text(encoding="utf-8", errors="replace")
    print(f"Loaded: {len(html)//1024}KB, {html.count(chr(10))} lines")

    print("\n[Meta tags]")
    html = patch_meta(html)

    print("\n[CSS Variables & Colors]")
    html = apply_all(html)

    print("\n[Hero Content]")
    html = patch_hero_content(html)

    print("\n[Nav Logo]")
    html = patch_nav_logo(html)

    print("\n[Footer]")
    html = patch_footer(html)

    print("\n[Final orquanta cleanup]")
    html, cleaned = clean_remaining_orquanta(html)
    print(f"  Cleaned {cleaned} remaining orquanta references")

    LP.write_text(html, encoding="utf-8")
    print(f"\n[DONE] Saved {len(html)//1024}KB to {LP.relative_to(LP.parent.parent.parent)}")

    # Verify
    remaining = html.lower().count("orquanta")
    print(f"Remaining 'orquanta': {remaining}")
    if remaining == 0:
        print("LANDING PAGE: CLEAN - Zero OrQuanta references!")
    else:
        import re
        for m in re.finditer("orquanta", html, re.IGNORECASE):
            start = max(0, m.start()-30)
            print(f"  Found: ...{html[start:m.end()+30]}...")


if __name__ == "__main__":
    main()
