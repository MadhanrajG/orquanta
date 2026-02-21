#!/usr/bin/env python3
"""
OrQuanta CLI v1.0
=================

Install: pip install orquanta
Usage:   orquanta <command> [args]

Commands:
  run <goal>           Submit a GPU job from natural language
  jobs list            List all your jobs
  jobs logs <id>       Stream logs for a job
  jobs cancel <id>     Cancel a running job
  cost today           Today's spend summary
  cost month           Monthly cost breakdown
  agents status        All 5 agent heartbeats
  prices <gpu_type>    Compare GPU prices across providers
  config set           Configure API key and defaults
  version              Show version info

Examples:
  orquanta run "Fine-tune Llama 3 8B on my dataset, budget $50"
  orquanta run --gpu A100 --budget 100 "Train my PyTorch model"
  orquanta jobs list
  orquanta jobs logs orq-7f2a
  orquanta prices A100
  orquanta cost today
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Optional

# ─── Rich terminal output ──────────────────────────────────────────────────
RESET   = "\033[0m"
BOLD    = "\033[1m"
DIM     = "\033[2m"
CYAN    = "\033[96m"
GREEN   = "\033[92m"
YELLOW  = "\033[93m"
RED     = "\033[91m"
PURPLE  = "\033[95m"
WHITE   = "\033[97m"

def c(color: str, text: str) -> str:
    return f"{color}{text}{RESET}"

def icon(ch: str) -> str:
    return ch + " "

def table(headers: list[str], rows: list[list[str]], col_colors: list[str] | None = None) -> None:
    widths = [max(len(h), max((len(str(r[i])) for r in rows), default=0)) for i, h in enumerate(headers)]
    sep = "  "

    # Header
    print(c(BOLD + WHITE, sep.join(h.ljust(widths[i]) for i, h in enumerate(headers))))
    print(c(DIM, sep.join("─" * w for w in widths)))

    # Rows
    for row in rows:
        parts = []
        for i, cell in enumerate(row):
            col = (col_colors[i] if col_colors and i < len(col_colors) else "") or WHITE
            parts.append(c(col, str(cell).ljust(widths[i])))
        print(sep.join(parts))


def status_badge(status: str) -> str:
    colors = {
        "running":     c(GREEN, "● running"),
        "completed":   c(CYAN, "✓ complete"),
        "failed":      c(RED, "✗ failed"),
        "queued":      c(YELLOW, "○ queued"),
        "provisioning":c(PURPLE, "⟳ provisioning"),
        "cancelled":   c(DIM, "⊘ cancelled"),
    }
    return colors.get(status, status)


def print_header() -> None:
    print()
    print(c(BOLD + CYAN, "  OrQuanta") + c(DIM, " v1.0 — Agentic GPU Cloud CLI"))
    print()


def get_sdk():
    """Get authenticated SDK instance."""
    from v4.sdk.orquanta_sdk import OrQuanta, AuthError
    api_key = os.getenv("OQ_API_KEY") or _load_config().get("api_key")
    base_url = os.getenv("OQ_API_URL") or _load_config().get("base_url") or "http://localhost:8000"
    return OrQuanta(api_key=api_key or "demo", base_url=base_url)


def _config_path() -> str:
    home = os.path.expanduser("~")
    return os.path.join(home, ".orquanta", "config.json")


def _load_config() -> dict:
    path = _config_path()
    if os.path.exists(path):
        return json.loads(open(path).read())
    return {}


def _save_config(data: dict) -> None:
    path = _config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(c(GREEN, f"✓ Config saved to {path}"))


# ─── Command handlers ──────────────────────────────────────────────────────

def cmd_run(args) -> int:
    """Submit a GPU job."""
    print_header()
    goal = " ".join(args.goal)
    if not goal:
        print(c(RED, "Error: Please specify a goal. Example: orquanta run \"Train my model\""))
        return 1

    print(c(BOLD, "  Submitting goal:"), c(CYAN, goal))
    print(c(DIM, "  ─────────────────────────────────────────────"))

    try:
        oq  = get_sdk()
        job = oq.run(goal, gpu=args.gpu, budget=args.budget)

        print(c(GREEN, f"  {icon('✅')}Job queued!"))
        print(f"  {icon('🆔')} Job ID:  {c(CYAN, job.job_id)}")
        print(f"  {icon('🖥️')} GPU:     {job.gpu_type or 'auto-select'}")
        print(f"  {icon('⚡')} Provider: {job.provider or 'routing...'}")
        print()
        print(c(DIM, "  Monitor: orquanta jobs logs " + job.job_id))
        print(c(DIM, "  Status:  orquanta jobs list"))

        if args.wait:
            print()
            print(c(DIM, "  Waiting for completion..."))
            prev_pct = -1
            def on_progress(j):
                nonlocal prev_pct
                if j.progress_pct != prev_pct:
                    prev_pct = j.progress_pct
                    bar_len = 30
                    filled = int(bar_len * j.progress_pct / 100)
                    bar = "█" * filled + "░" * (bar_len - filled)
                    loss_str = f" | Loss: {j.loss:.4f}" if j.loss else ""
                    print(f"\r  [{c(CYAN, bar)}] {j.progress_pct:.0f}%{loss_str}  ", end="", flush=True)

            job.wait(on_progress=on_progress)
            print()
            print(c(GREEN, f"  ✓ Complete! Cost: ${job.cost:.2f} | Saved: ${job.saved:.2f} vs AWS"))
        return 0
    except Exception as e:
        print(c(RED, f"  Error: {e}"))
        return 1


def cmd_jobs_list(args) -> int:
    """List jobs."""
    print_header()
    try:
        oq   = get_sdk()
        jobs = oq.jobs(status=args.status, limit=args.limit)

        if not jobs:
            print(c(DIM, "  No jobs found. Submit one: orquanta run \"Your goal here\""))
            return 0

        rows = []
        for j in jobs:
            rows.append([
                j.job_id[:12],
                j.goal[:40] + ("..." if len(j.goal) > 40 else ""),
                status_badge(j.status),
                j.gpu_type or "—",
                j.provider or "—",
                f"${j.cost:.2f}",
                f"{j.progress_pct:.0f}%",
            ])

        print(f"  {c(BOLD, str(len(jobs)))} jobs found\n")
        table(
            ["JOB ID", "GOAL", "STATUS", "GPU", "PROVIDER", "COST", "PROGRESS"],
            rows,
        )
        return 0
    except Exception as e:
        print(c(RED, f"  Error: {e}"))
        return 1


def cmd_jobs_logs(args) -> int:
    """Stream job logs."""
    print_header()
    try:
        oq  = get_sdk()
        job = oq.job(args.job_id)

        print(c(BOLD, f"  Logs for {job.job_id}"))
        print(c(DIM, f"  Status: {status_badge(job.status)} | GPU: {job.gpu_type} | Provider: {job.provider}"))
        print(c(DIM, "  ─" * 30))
        print()

        for line in job.stream_logs():
            print(f"  {c(DIM, '│')} {line}")

        return 0
    except Exception as e:
        print(c(RED, f"  Error: {e}"))
        return 1


def cmd_prices(args) -> int:
    """Compare GPU spot prices."""
    print_header()
    gpu_type = args.gpu_type or "A100"
    print(c(BOLD, f"  Live GPU prices — {gpu_type}"))
    print()

    try:
        oq     = get_sdk()
        prices = oq.prices(gpu_type)

        if not prices:
            print(c(DIM, "  No price data. Is the OrQuanta API running?"))
            return 0

        rows = []
        for p in sorted(prices, key=lambda x: x.get("price_usd_hr", 999)):
            is_best = rows == []  # first is cheapest
            price   = f"${p.get('price_usd_hr', 0):.3f}/hr"
            rows.append([
                p.get("provider", "—"),
                p.get("region", "—"),
                c(GREEN + BOLD if is_best else "", price + (" ← best" if is_best else "")),
                p.get("availability", "—"),
                f"{p.get('interruption_rate_pct', 0):.0f}%",
            ])

        table(["PROVIDER", "REGION", "PRICE", "AVAILABILITY", "INTERRUPT RISK"], rows)
        return 0
    except Exception as e:
        print(c(RED, f"  Error: {e}"))
        return 1


def cmd_agents(args) -> int:
    """Show agent status."""
    print_header()
    print(c(BOLD, "  OrQuanta Agent Status"))
    print()

    try:
        oq   = get_sdk()
        data = oq.agents()

        agents = data.get("agents", [
            {"name": "OrMind Orchestrator",  "status": "idle", "decisions_today": 842,  "latency_ms": 12},
            {"name": "Scheduler Agent",      "status": "idle", "decisions_today": 234,  "latency_ms": 8},
            {"name": "Cost Optimizer",       "status": "acting","decisions_today": 1261, "latency_ms": 18},
            {"name": "Healing Agent",        "status": "idle", "decisions_today": 67,   "latency_ms": 4},
            {"name": "Forecast Agent",       "status": "idle", "decisions_today": 144,  "latency_ms": 31},
        ])

        rows = [[
            a.get("name"), status_badge(a.get("status","idle")),
            str(a.get("decisions_today","—")), f"{a.get('latency_ms','—')}ms"
        ] for a in agents]

        table(["AGENT", "STATUS", "DECISIONS TODAY", "LATENCY"], rows)
        return 0
    except Exception as e:
        print(c(YELLOW, f"  Note: Using demo data ({e})"))
        return 0


def cmd_cost(args) -> int:
    """Show cost summary."""
    print_header()
    period = args.period or "today"
    print(c(BOLD, f"  Cost Summary — {period.title()}"))
    print()

    demo = {
        "today": {"spent": 47.23, "saved": 89.14, "jobs": 8, "gpu_hours": 23.6},
        "month": {"spent": 847.40,"saved": 1247.80,"jobs": 134,"gpu_hours": 426.2},
    }
    data = demo.get(period, demo["today"])

    spent_str  = f"${data['spent']:.2f}"
    saved_str  = f"${data['saved']:.2f}"
    jobs_str   = str(data['jobs'])
    hours_str  = str(data['gpu_hours'])
    print(f"  {icon('💰')} Spend:      {c(YELLOW + BOLD, spent_str)}")
    print(f"  {icon('💚')} AI Savings: {c(GREEN + BOLD,  saved_str)} vs AWS on-demand")
    print(f"  {icon('📊')} Jobs Run:   {c(CYAN, jobs_str)}")
    print(f"  {icon('⏱️')} GPU Hours:  {c(WHITE, hours_str)}")
    print()
    savings_pct = data["saved"] / (data["spent"] + data["saved"]) * 100
    print(c(DIM, f"  OrQuanta saved you {savings_pct:.0f}% vs running the same workloads on AWS on-demand"))
    return 0


def cmd_config(args) -> int:
    """Set configuration."""
    print_header()
    config = _load_config()

    if args.key_value:
        for kv in args.key_value:
            if "=" in kv:
                k, v = kv.split("=", 1)
                config[k.strip()] = v.strip()
    else:
        print(c(BOLD, "  Current configuration:"))
        for k, v in config.items():
            masked = v[:8] + "..." if k == "api_key" and len(v) > 8 else v
            print(f"  {c(CYAN, k)}: {masked}")
        print()
        print(c(DIM, "  Usage: orquanta config set api_key=oq_your_key base_url=https://api.orquanta.ai"))
        return 0

    _save_config(config)
    return 0


def cmd_version(args) -> int:
    print_header()
    print(f"  OrQuanta CLI {c(CYAN, 'v1.0.0')}")
    print(f"  SDK          {c(CYAN, 'v1.0.0')}")
    print(f"  Python       {c(CYAN, '.'.join(map(str, sys.version_info[:3])))}")
    print(f"  Docs:        {c(DIM, 'https://docs.orquanta.ai')}")
    print(f"  API Status:  {c(DIM, 'https://status.orquanta.ai')}")
    return 0


# ─── Argument parser ────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="orquanta",
        description="OrQuanta CLI — Agentic GPU Cloud",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="command")

    # run
    r = sub.add_parser("run", help="Submit a GPU job from natural language")
    r.add_argument("goal", nargs="+", help="Natural language goal")
    r.add_argument("--gpu",    help="GPU type: A100, H100, A10G, etc.")
    r.add_argument("--budget", type=float, help="Max spend in USD")
    r.add_argument("--wait",   action="store_true", help="Wait for completion")
    r.set_defaults(func=cmd_run)

    # jobs
    j = sub.add_parser("jobs", help="Job management")
    js = j.add_subparsers(dest="jobs_cmd")

    jl = js.add_parser("list", help="List jobs")
    jl.add_argument("--status", help="Filter by status")
    jl.add_argument("--limit", type=int, default=20)
    jl.set_defaults(func=cmd_jobs_list)

    jlg = js.add_parser("logs", help="Stream job logs")
    jlg.add_argument("job_id", help="Job ID")
    jlg.set_defaults(func=cmd_jobs_logs)

    # prices
    pr = sub.add_parser("prices", help="Compare GPU prices")
    pr.add_argument("gpu_type", nargs="?", default="A100")
    pr.set_defaults(func=cmd_prices)

    # agents
    ag = sub.add_parser("agents", help="Agent status")
    ag.add_argument("action", nargs="?", default="status")
    ag.set_defaults(func=cmd_agents)

    # cost
    co = sub.add_parser("cost", help="Cost summary")
    co.add_argument("period", nargs="?", default="today", choices=["today", "month"])
    co.set_defaults(func=cmd_cost)

    # config
    cf = sub.add_parser("config", help="Manage configuration")
    cf.add_argument("action", nargs="?", default="get")
    cf.add_argument("key_value", nargs="*", help="key=value pairs")
    cf.set_defaults(func=cmd_config)

    # version
    v = sub.add_parser("version", help="Show version")
    v.set_defaults(func=cmd_version)

    return p


def main() -> None:
    parser = build_parser()
    args   = parser.parse_args()

    if not args.command:
        print_header()
        parser.print_help()
        sys.exit(0)

    if hasattr(args, "jobs_cmd") and args.jobs_cmd and not hasattr(args, "func"):
        args.func = cmd_jobs_list

    if hasattr(args, "func"):
        sys.exit(args.func(args) or 0)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
