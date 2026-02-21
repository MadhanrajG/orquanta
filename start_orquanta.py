#!/usr/bin/env python3
"""
OrQuanta Agentic v1.0 — Startup Script
=======================================

Usage:
    python start_orquanta.py              # Production mode
    python start_orquanta.py --demo       # Demo mode (simulated cloud)
    python start_orquanta.py --demo --scenario cost_optimizer
    python start_orquanta.py --check      # Health check only

Flags:
    --demo          Enable demo mode (DEMO_MODE=true)
    --scenario STR  Auto-run scenario: cost_optimizer | self_healing | natural_language | all
    --no-browser    Don't open browser automatically
    --port INT      API port (default: 8000)
    --workers INT   Uvicorn workers (default: 1 in demo, 4 in prod)
    --check         Run health check and exit
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import webbrowser
import asyncio
from pathlib import Path

ROOT = Path(__file__).parent
V4   = ROOT / "v4"

# ─── ANSI Colors ──────────────────────────────────────────────────────────────
RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
CYAN   = "\033[36m"
BLUE   = "\033[34m"
PURPLE = "\033[35m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
RED    = "\033[31m"
WHITE  = "\033[97m"


def c(color: str, text: str) -> str:
    return f"{color}{text}{RESET}"


def print_separator(char="─", width=62) -> None:
    print(c(DIM, char * width))


def print_header(demo: bool) -> None:
    print()
    print_separator("═")
    print()
    print(c(BOLD + CYAN,   "        ██████  ██████  "))
    print(c(BOLD + CYAN,   "       ██    ██ ██    ██"))
    print(c(BOLD + PURPLE, "       ██    ██ ██    ██"))
    print(c(BOLD + PURPLE, "        ██████  ██████  "))
    print()
    print(c(BOLD + WHITE,  "        OrQuanta Agentic v1.0"))
    print(c(DIM,           "    Orchestrate. Optimize. Evolve."))
    print()
    if demo:
        print(c(YELLOW,    "  ⚡ DEMO MODE — All clouds simulated"))
    else:
        print(c(GREEN,     "  🚀 PRODUCTION MODE"))
    print()
    print_separator("═")
    print()


def print_step(icon: str, text: str, status: str | None = None) -> None:
    status_str = ""
    if status == "ok":
        status_str = c(GREEN, " ✓")
    elif status == "skip":
        status_str = c(DIM, " --")
    elif status == "warn":
        status_str = c(YELLOW, " ⚠")
    elif status == "fail":
        status_str = c(RED, " ✗")
    print(f"  {icon}  {text}{status_str}")


# ─── Argument parsing ─────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="OrQuanta Agentic v1.0 — Startup Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--demo",        action="store_true", help="Run in demo mode")
    p.add_argument("--production",  action="store_true", help="Run in production mode")
    p.add_argument("--scenario",    default="cost_optimizer",
                   choices=["cost_optimizer", "self_healing", "natural_language", "all"],
                   help="Demo scenario to auto-run")
    p.add_argument("--no-browser",  action="store_true", help="Don't open browser")
    p.add_argument("--port",        type=int, default=8000, help="API port")
    p.add_argument("--workers",     type=int, default=0,    help="Uvicorn workers (0=auto)")
    p.add_argument("--check",       action="store_true",    help="Health check and exit")
    return p.parse_args()


# ─── Environment setup ────────────────────────────────────────────────────────

def setup_env(demo: bool) -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    if demo:
        env["DEMO_MODE"]   = "true"
        env["LOG_LEVEL"]   = "INFO"
    else:
        env["DEMO_MODE"]   = "false"
        env.setdefault("LOG_LEVEL", "INFO")
    return env


# ─── Health check ────────────────────────────────────────────────────────────

def health_check(port: int, retries: int = 10, delay: float = 2.0) -> bool:
    """Poll /health until API is up."""
    try:
        import urllib.request
        url = f"http://localhost:{port}/health"
        for attempt in range(retries):
            try:
                with urllib.request.urlopen(url, timeout=3) as resp:
                    if resp.status == 200:
                        return True
            except Exception:
                pass
            if attempt < retries - 1:
                time.sleep(delay)
        return False
    except Exception:
        return False


# ─── Preflight checks ────────────────────────────────────────────────────────

def run_preflight(demo: bool) -> bool:
    print(c(BOLD, "  Pre-flight checks"))
    print_separator()

    # Python version
    major, minor = sys.version_info[:2]
    if major >= 3 and minor >= 11:
        print_step("🐍", f"Python {major}.{minor}", "ok")
    else:
        print_step("🐍", f"Python {major}.{minor} (need 3.11+)", "warn")

    # Key dependencies
    deps = ["fastapi", "uvicorn", "httpx", "pydantic"]
    missing = []
    for dep in deps:
        try:
            __import__(dep)
            print_step("📦", dep, "ok")
        except ImportError:
            print_step("📦", dep + " — NOT INSTALLED", "fail")
            missing.append(dep)

    if missing:
        print()
        print(c(RED, f"  Missing: {', '.join(missing)}"))
        print(c(DIM, "  Run: pip install -r requirements.txt"))
        return False

    # .env file
    env_file = ROOT / ".env"
    if env_file.exists():
        print_step("🔑", ".env found", "ok")
    elif demo:
        print_step("🔑", ".env not found (OK in demo mode)", "skip")
    else:
        print_step("🔑", ".env not found — create from .env.example", "warn")

    print()
    return True


# ─── Start API server ─────────────────────────────────────────────────────────

def start_api(port: int, workers: int, env: dict) -> subprocess.Popen:
    """Launch uvicorn API server."""
    n_workers = workers if workers > 0 else (1 if env.get("DEMO_MODE") == "true" else 4)
    cmd = [
        sys.executable, "-m", "uvicorn",
        "v4.api.main:app",
        "--host", "0.0.0.0",
        "--port", str(port),
        "--workers", str(n_workers),
        "--log-level", "warning",
    ]
    proc = subprocess.Popen(cmd, cwd=ROOT, env=env)
    return proc


# ─── Post-startup actions ─────────────────────────────────────────────────────

async def post_start_demo_actions(port: int, scenario: str) -> None:
    """After API is up, kick off the demo scenario."""
    try:
        from v4.demo.demo_mode import get_demo_engine
        from v4.demo.demo_scenario import run_scenario, run_all_scenarios

        engine = get_demo_engine()
        await engine.start()

        print()
        print(c(BOLD, "  Running demo scenario:"), c(CYAN, scenario))
        print_separator()

        if scenario == "all":
            results = await run_all_scenarios(engine)
        else:
            result = await run_scenario(scenario, engine)
            results = [result]

        for r in results:
            scen = r.get("scenario", "?")
            if "error" in r:
                print_step("❌", f"{scen}: {r['error']}", "fail")
            else:
                print_step("✅", f"{scen}: complete", "ok")

    except Exception as exc:
        print(c(YELLOW, f"  Demo scenario error (non-fatal): {exc}"))


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    args   = parse_args()
    demo   = args.demo or (not args.production)
    port   = args.port

    print_header(demo)

    # ── Preflight ────────────────────────────────────────────────────────────
    if not run_preflight(demo):
        sys.exit(1)

    # ── Health-check-only mode ────────────────────────────────────────────────
    if args.check:
        print(c(BOLD, "  Health check"))
        print_separator()
        ok = health_check(port, retries=1, delay=0)
        if ok:
            print_step("💚", f"API on port {port} is healthy", "ok")
        else:
            print_step("💔", f"API on port {port} not responding", "fail")
        print()
        sys.exit(0 if ok else 1)

    # ── API startup ───────────────────────────────────────────────────────────
    print(c(BOLD, "  Starting services"))
    print_separator()
    env = setup_env(demo)
    proc = start_api(port, args.workers, env)

    print_step("🚀", f"API server starting on port {port}...", None)

    # Wait for API to come up
    ready = health_check(port, retries=15, delay=1.5)
    if not ready:
        print_step("💔", "API failed to start", "fail")
        print(c(DIM, "  Check logs above for errors."))
        proc.terminate()
        sys.exit(1)

    print_step("🌐", f"OrQuanta API live at http://localhost:{port}", "ok")
    print_step("📖", f"API docs:          http://localhost:{port}/docs", "ok")
    print_step("💻", f"Dashboard:         http://localhost:{port}/dashboard", "ok")
    if demo:
        print_step("🎭", f"Demo dashboard:    http://localhost:{port}/demo", "ok")
        print_step("📊", "Metrics stream:    ws://localhost:{port}/ws/agent-stream", "skip")
    print()

    # ── Open browser ─────────────────────────────────────────────────────────
    if not args.no_browser:
        url = f"http://localhost:{port}/demo" if demo else f"http://localhost:{port}/dashboard"
        print_step("🌍", f"Opening {url}...", "ok")
        time.sleep(0.5)
        webbrowser.open(url)
        print()

    # ── Demo scenarios ────────────────────────────────────────────────────────
    if demo:
        print(c(BOLD, "  Demo scenarios"))
        print_separator()
        print(c(DIM, "  Starting background scenario..."))
        asyncio.run(post_start_demo_actions(port, args.scenario))

    # ── Running banner ────────────────────────────────────────────────────────
    print()
    print_separator("═")
    print()
    print(c(BOLD + GREEN,  "  OrQuanta is running!"))
    print()
    if demo:
        print(c(CYAN,  f"  🎭 Demo live:      http://localhost:{port}/demo"))
    print(c(WHITE,  f"  📡 API:            http://localhost:{port}"))
    print(c(WHITE,  f"  📖 Docs:           http://localhost:{port}/docs"))
    print(c(WHITE,  f"  🏥 Health:         http://localhost:{port}/health"))
    print()
    print(c(DIM, "  Press Ctrl+C to stop"))
    print()
    print_separator("═")
    print()

    # ── Keep alive ────────────────────────────────────────────────────────────
    try:
        proc.wait()
    except KeyboardInterrupt:
        print()
        print(c(YELLOW, "  Shutting down OrQuanta..."))
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        print(c(DIM, "  Goodbye. Orchestrate. Optimize. Evolve."))
        print()


if __name__ == "__main__":
    main()
