#!/usr/bin/env python3
"""
OrQuanta CLI — Command-line interface for the OrQuanta AI GPU Cloud Platform.

Install: pip install typer httpx rich
Usage:
    python orquanta_cli.py login
    python orquanta_cli.py submit --gpu H100 --intent "Fine-tune Llama 3 on my dataset"
    python orquanta_cli.py jobs list
    python orquanta_cli.py jobs status <job_id>
    python orquanta_cli.py pricing --gpu A100
    python orquanta_cli.py agents
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

try:
    import typer
    import httpx
    from rich import print as rprint
    from rich.console import Console
    from rich.table import Table
    from rich.live import Live
    from rich.panel import Panel
    from rich.text import Text
    from rich.progress import Progress, SpinnerColumn, TextColumn
except ImportError:
    print("❌ Install required packages: pip install typer httpx rich")
    sys.exit(1)

app = typer.Typer(
    name="orquanta",
    help="🚀 OrQuanta AI GPU Cloud — Autonomous orchestration CLI",
    add_completion=False,
    rich_markup_mode="rich",
)
jobs_app = typer.Typer(help="GPU Job management")
app.add_typer(jobs_app, name="jobs")

console = Console()

# ── Config store ──────────────────────────────────────────────────────────────
CONFIG_PATH = Path.home() / ".orquanta" / "config.json"


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {}


def _save_config(cfg: dict):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


def _get_token() -> str:
    cfg = _load_config()
    token = cfg.get("token") or os.getenv("ORQUANTA_API_TOKEN", "")
    if not token:
        console.print("[bold red]❌ Not authenticated.[/] Run [bold cyan]orquanta login[/] first.")
        raise typer.Exit(1)
    return token


def _api_url() -> str:
    cfg = _load_config()
    return cfg.get("api_url") or os.getenv("ORQUANTA_API_URL", "http://localhost:8000")


def _headers() -> dict:
    return {"Authorization": f"Bearer {_get_token()}", "Content-Type": "application/json"}


def _client() -> httpx.Client:
    return httpx.Client(base_url=_api_url(), timeout=30)


# ── Auth ──────────────────────────────────────────────────────────────────────
@app.command()
def login(
    email: str = typer.Option(..., prompt="Email"),
    password: str = typer.Option(..., prompt="Password", hide_input=True),
    api_url: str = typer.Option("http://localhost:8000", help="OrQuanta API URL"),
):
    """Authenticate and save credentials locally."""
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        progress.add_task("Authenticating...", total=None)
        try:
            r = httpx.post(f"{api_url}/auth/login", json={"email": email, "password": password}, timeout=10)
        except httpx.ConnectError:
            console.print(f"[red]❌ Cannot connect to {api_url}[/]")
            raise typer.Exit(1)

    if r.status_code != 200:
        console.print(f"[red]❌ Login failed: {r.json().get('error', r.text)}[/]")
        raise typer.Exit(1)

    token = r.json()["access_token"]
    _save_config({"token": token, "email": email, "api_url": api_url})
    console.print(f"[bold green]✅ Logged in as [cyan]{email}[/cyan] → {api_url}[/]")


@app.command()
def logout():
    """Clear saved credentials."""
    if CONFIG_PATH.exists():
        CONFIG_PATH.unlink()
    console.print("[green]✅ Logged out[/]")


# ── Job submission ─────────────────────────────────────────────────────────────
@app.command()
def submit(
    intent: str = typer.Option(..., "--intent", "-i", help="Natural language job description"),
    gpu: str = typer.Option("H100", "--gpu", "-g", help="GPU type: H100, A100, RTX4090, T4"),
    gpu_count: int = typer.Option(1, "--count", "-n", help="Number of GPUs"),
    budget: float = typer.Option(50.0, "--budget", "-b", help="Max cost budget in USD"),
    watch: bool = typer.Option(False, "--watch", "-w", help="Stream job logs live"),
):
    """
    Submit a GPU job to OrQuanta.

    Example:
        orquanta submit --intent "Fine-tune Llama 3 on my dataset" --gpu H100 --budget 30
    """
    payload = {
        "intent": intent,
        "gpu_type": gpu,
        "gpu_count": gpu_count,
        "max_cost_usd": budget,
    }

    with _client() as client:
        r = client.post("/jobs/", json=payload, headers=_headers())

    if r.status_code not in (200, 201):
        console.print(f"[red]❌ Submission failed ({r.status_code}): {r.text[:200]}[/]")
        raise typer.Exit(1)

    job = r.json()
    job_id = job["job_id"]

    console.print(Panel(
        f"[bold cyan]Job ID:[/] {job_id}\n"
        f"[bold]Status:[/]  [yellow]{job.get('status', 'queued')}[/]\n"
        f"[bold]GPU:[/]     {gpu_count}× {gpu}\n"
        f"[bold]Budget:[/]  ${budget:.2f}",
        title="[bold green]✅ Job Submitted[/]",
        border_style="green",
    ))

    if watch:
        _watch_job(job_id)


# ── Job management ────────────────────────────────────────────────────────────
@jobs_app.command("list")
def jobs_list(
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Filter: queued|running|completed|failed"),
    limit: int = typer.Option(20, "--limit", "-l"),
):
    """List GPU jobs."""
    params = {"limit": limit}
    if status:
        params["status"] = status

    with _client() as client:
        r = client.get("/jobs/", params=params, headers=_headers())

    if r.status_code != 200:
        console.print(f"[red]❌ {r.status_code}: {r.text[:200]}[/]")
        raise typer.Exit(1)

    data = r.json()
    jobs = data if isinstance(data, list) else data.get("jobs", [])

    if not jobs:
        console.print("[dim]No jobs found.[/]")
        return

    table = Table(title=f"GPU Jobs ({len(jobs)} shown)", border_style="bright_blue")
    table.add_column("Job ID", style="cyan", no_wrap=True)
    table.add_column("Status", justify="center")
    table.add_column("GPU")
    table.add_column("Provider")
    table.add_column("Cost $")
    table.add_column("Duration")
    table.add_column("Intent", max_width=40)

    status_colors = {
        "queued": "yellow", "provisioning": "blue", "running": "bright_green",
        "completed": "green", "failed": "red", "cancelled": "dim"
    }

    for j in jobs:
        st = j.get("status", "?")
        color = status_colors.get(st, "white")
        dur_s = j.get("duration_seconds", 0)
        dur = f"{dur_s:.0f}s" if dur_s else "—"
        table.add_row(
            j.get("job_id", "?")[:20],
            f"[{color}]{st}[/]",
            f"{j.get('gpu_count',1)}× {j.get('gpu_type','?')}",
            j.get("provider", "—"),
            f"${j.get('cost_usd', 0.0):.4f}",
            dur,
            (j.get("intent") or "")[:40],
        )

    console.print(table)


@jobs_app.command("status")
def job_status(job_id: str = typer.Argument(..., help="Job ID to inspect")):
    """Get detailed status of a specific job."""
    with _client() as client:
        r = client.get(f"/jobs/{job_id}", headers=_headers())

    if r.status_code == 404:
        console.print(f"[red]❌ Job not found: {job_id}[/]")
        raise typer.Exit(1)

    j = r.json()
    st = j.get("status", "?")
    status_colors = {"running": "bright_green", "completed": "green", "failed": "red", "queued": "yellow"}
    color = status_colors.get(st, "white")

    console.print(Panel(
        f"[bold]Status:[/]    [{color}]{st}[/]\n"
        f"[bold]GPU:[/]       {j.get('gpu_count',1)}× {j.get('gpu_type','?')}\n"
        f"[bold]Provider:[/]  {j.get('provider','—')}\n"
        f"[bold]Region:[/]    {j.get('region','—')}\n"
        f"[bold]Cost:[/]      ${j.get('cost_usd', 0):.4f}\n"
        f"[bold]Duration:[/]  {j.get('duration_seconds',0):.0f}s\n"
        f"[bold]Exit Code:[/] {j.get('exit_code','—')}\n"
        f"[bold]Intent:[/]    {j.get('intent','')[:80]}",
        title=f"[bold]Job {job_id[:20]}[/]",
        border_style=color,
    ))

    logs = j.get("log_lines", [])
    if logs:
        console.print("\n[bold]Last 20 log lines:[/]")
        for line in logs[-20:]:
            console.print(f"  [dim]{line}[/]")


@jobs_app.command("cancel")
def job_cancel(job_id: str = typer.Argument(...)):
    """Cancel a running job."""
    with _client() as client:
        r = client.delete(f"/jobs/{job_id}", headers=_headers())
    if r.status_code in (200, 204):
        console.print(f"[green]✅ Job {job_id} cancelled[/]")
    else:
        console.print(f"[red]❌ Cancel failed: {r.text[:200]}[/]")


# ── Pricing ───────────────────────────────────────────────────────────────────
@app.command()
def pricing(
    gpu: str = typer.Option("H100", "--gpu", "-g", help="GPU type to compare"),
):
    """Compare live GPU spot prices across all providers."""
    with _client() as client:
        r = client.get(f"/providers/prices?gpu_type={gpu}", headers=_headers())

    if r.status_code != 200:
        console.print(f"[red]❌ {r.status_code}: {r.text[:200]}[/]")
        raise typer.Exit(1)

    data = r.json()
    prices = data.get("prices", [])
    recommended = data.get("recommended", {})

    table = Table(title=f"💰 Live {gpu} Pricing", border_style="bright_cyan")
    table.add_column("Provider", style="cyan")
    table.add_column("Region")
    table.add_column("$/hr", justify="right")
    table.add_column("Availability", justify="center")
    table.add_column("Interruption %", justify="right")

    for p in prices:
        is_best = p.get("provider") == recommended.get("provider") and p.get("region") == recommended.get("region")
        style = "bold green" if is_best else ""
        label = " ⭐ Best" if is_best else ""
        table.add_row(
            f"[{style}]{p['provider']}{label}[/]",
            p.get("region", "—"),
            f"[{style}]${p['price_usd_hr']:.3f}[/]",
            p.get("availability", "—"),
            f"{p.get('interruption_rate_pct', 0):.1f}%",
        )

    console.print(table)
    if recommended:
        console.print(f"\n[bold green]⭐ Recommendation:[/] {recommended.get('provider')} @ ${recommended.get('price_usd_hr', 0):.3f}/hr")


# ── Agents status ──────────────────────────────────────────────────────────────
@app.command()
def agents():
    """Show status of all AI agents."""
    with _client() as client:
        r = client.get("/agents/", headers=_headers())

    if r.status_code != 200:
        console.print(f"[red]❌ {r.status_code}: {r.text[:200]}[/]")
        raise typer.Exit(1)

    data = r.json()
    agents_list = data if isinstance(data, list) else data.get("agents", [])

    table = Table(title="🤖 OrQuanta AI Agents", border_style="bright_magenta")
    table.add_column("Agent", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Last Action")
    table.add_column("Actions Total", justify="right")

    for a in agents_list:
        st = a.get("status", "unknown")
        color = "green" if st == "running" else "yellow" if st == "idle" else "red"
        table.add_row(
            a.get("agent_name") or a.get("name", "?"),
            f"[{color}]{st}[/]",
            a.get("last_action") or "—",
            str(a.get("total_actions") or a.get("actions_taken", "—")),
        )

    console.print(table)


# ── Health check ──────────────────────────────────────────────────────────────
@app.command()
def health():
    """Check OrQuanta API health."""
    url = _api_url()
    try:
        r = httpx.get(f"{url}/health", timeout=5)
        data = r.json()
        if data.get("status") == "healthy":
            console.print(f"[bold green]✅ OrQuanta API is healthy[/] at {url}")
            console.print(f"   Version: {data.get('version','?')} | {data.get('timestamp','')}")
        else:
            console.print(f"[yellow]⚠️  API responded but status: {data.get('status')}[/]")
    except Exception as e:
        console.print(f"[red]❌ Cannot reach {url}: {e}[/]")
        raise typer.Exit(1)


# ── Goal submission ────────────────────────────────────────────────────────────
@app.command()
def goal(
    text: str = typer.Argument(..., help="Natural language goal"),
    budget: float = typer.Option(50.0, "--budget", "-b"),
):
    """Submit a high-level AI goal (agents plan and execute automatically)."""
    with _client() as client:
        r = client.post("/goals/", json={"raw_text": text, "budget_usd": budget}, headers=_headers())

    if r.status_code not in (200, 201):
        console.print(f"[red]❌ {r.status_code}: {r.text[:300]}[/]")
        raise typer.Exit(1)

    data = r.json()
    console.print(Panel(
        f"[bold cyan]Goal ID:[/] {data.get('goal_id', '?')}\n"
        f"[bold]Status:[/]  [yellow]{data.get('status', 'accepted')}[/]\n"
        f"[bold]Budget:[/]  ${budget:.2f}\n\n"
        f"[dim]Agents are now planning and will execute autonomously.[/]",
        title="[bold green]✅ Goal Accepted[/]",
        border_style="green",
    ))


# ── Live log watcher ───────────────────────────────────────────────────────────
def _watch_job(job_id: str):
    """Poll job status and stream log lines until completion."""
    console.print(f"\n[bold]Watching job {job_id}...[/] (Ctrl+C to stop)\n")
    seen_lines = 0
    try:
        while True:
            with _client() as client:
                r = client.get(f"/jobs/{job_id}", headers=_headers())
            if r.status_code != 200:
                break
            j = r.json()
            logs = j.get("log_lines", [])
            for line in logs[seen_lines:]:
                console.print(f"  [dim]{line}[/]")
            seen_lines = len(logs)
            st = j.get("status", "")
            if st in ("completed", "failed", "cancelled"):
                color = "green" if st == "completed" else "red"
                console.print(f"\n[bold {color}]Job {st}[/] — cost: ${j.get('cost_usd', 0):.4f}")
                break
            time.sleep(3)
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped watching.[/]")


# ── Models subcommands ────────────────────────────────────────────────────────
models_app = typer.Typer(help="Model registry and Hub")
app.add_typer(models_app, name="models")


@models_app.command("list")
def models_list(
    family: Optional[str] = typer.Option(None, help="Filter by model family"),
    limit: int = typer.Option(20, help="Max results"),
):
    """List available models in the OrQuanta Model Hub."""
    with _client() as c:
        try:
            params = {}
            if family:
                params["family"] = family
            r = c.get("/api/v1/models", params=params, headers=_headers())
            r.raise_for_status()
            data = r.json()
        except Exception as exc:
            console.print(f"[red]❌ {exc}[/]")
            raise typer.Exit(1)

    models = data.get("models", data) if isinstance(data, dict) else data
    table = Table(title="OrQuanta Model Hub", show_lines=True)
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Family", style="magenta")
    table.add_column("Parameters")
    table.add_column("Context")
    table.add_column("Licence")
    table.add_column("Status")
    for m in models[:limit]:
        table.add_row(
            m.get("model_id", ""),
            m.get("family", ""),
            str(m.get("parameters_b", "")),
            str(m.get("context_length", "")),
            m.get("licence", ""),
            m.get("deployment_status", ""),
        )
    console.print(table)


@models_app.command("search")
def models_search(query: str = typer.Argument(..., help="Search query")):
    """Search Hugging Face model hub."""
    with _client() as c:
        try:
            r = c.get("/api/v1/models/search/hf", params={"q": query, "limit": 10}, headers=_headers())
            r.raise_for_status()
            results = r.json()
        except Exception as exc:
            console.print(f"[red]❌ {exc}[/]")
            raise typer.Exit(1)

    models = results.get("models", results) if isinstance(results, dict) else results
    table = Table(title=f"HF Search: {query}", show_lines=True)
    table.add_column("ID", style="cyan")
    table.add_column("Downloads", justify="right")
    table.add_column("Licence")
    for m in models:
        table.add_row(
            m.get("modelId", m.get("model_id", "")),
            str(m.get("downloads", "")),
            m.get("licence", ""),
        )
    console.print(table)


@models_app.command("compat")
def models_compat(
    model_id: str = typer.Argument(..., help="Model ID"),
    gpu: str = typer.Option(..., "--gpu", help="GPU model (e.g. A100_80GB)"),
    quant: str = typer.Option("none", "--quant", help="Quantisation (none/int8/int4/fp8)"),
):
    """Check GPU compatibility for a model."""
    with _client() as c:
        try:
            r = c.post("/api/v1/models/check-compatibility",
                       json={"model_id": model_id, "gpu_model": gpu, "quantisation": quant},
                       headers=_headers())
            r.raise_for_status()
            result = r.json()
        except Exception as exc:
            console.print(f"[red]❌ {exc}[/]")
            raise typer.Exit(1)

    compatible = result.get("compatible", False)
    icon = "✅" if compatible else "❌"
    console.print(Panel(
        f"{icon} [bold]Compatible: {compatible}[/]\n"
        f"VRAM Required: {result.get('vram_required_gb', 'N/A')} GB\n"
        f"VRAM Available: {result.get('vram_available_gb', 'N/A')} GB\n"
        f"Notes: {'; '.join(result.get('notes', []))}",
        title=f"Compatibility: {model_id} on {gpu}",
    ))


# ── Deploy subcommands ────────────────────────────────────────────────────────
deploy_app = typer.Typer(help="Model deployments")
app.add_typer(deploy_app, name="deploy")


@deploy_app.command("start")
def deploy_start(
    model_id: str = typer.Option(..., "--model", help="Model ID to deploy"),
    engine: str = typer.Option("vllm", "--engine", help="Inference engine"),
    gpu: str = typer.Option("A100_80GB", "--gpu", help="GPU model"),
    provider: str = typer.Option("runpod", "--provider", help="GPU provider"),
    gpu_count: int = typer.Option(1, "--gpus", help="Number of GPUs"),
):
    """Start a model deployment."""
    with _client() as c:
        try:
            r = c.post("/api/v1/deployments",
                       json={"model_id": model_id, "engine": engine,
                             "gpu_model": gpu, "gpu_count": gpu_count, "provider": provider},
                       headers=_headers())
            r.raise_for_status()
            dep = r.json()
        except Exception as exc:
            console.print(f"[red]❌ {exc}[/]")
            raise typer.Exit(1)

    is_mock = dep.get("is_mock", True)
    icon = "🧪 [dim](mock)[/]" if is_mock else "🚀"
    console.print(Panel(
        f"{icon} Deployment ID: [bold cyan]{dep.get('deployment_id', dep.get('id', ''))}[/]\n"
        f"Status: {dep.get('status', 'pending')}\n"
        f"Model: {model_id}  Engine: {engine}",
        title="Deployment Started",
    ))


@deploy_app.command("list")
def deploy_list():
    """List active deployments."""
    with _client() as c:
        try:
            r = c.get("/api/v1/deployments", headers=_headers())
            r.raise_for_status()
            data = r.json()
        except Exception as exc:
            console.print(f"[red]❌ {exc}[/]")
            raise typer.Exit(1)

    deps = data.get("deployments", data) if isinstance(data, dict) else data
    table = Table(title="Deployments", show_lines=True)
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Model")
    table.add_column("Engine")
    table.add_column("Status")
    table.add_column("Mock", justify="center")
    for d in deps:
        table.add_row(
            d.get("deployment_id", d.get("id", "")),
            d.get("model_id", ""),
            d.get("engine", ""),
            d.get("status", ""),
            "🧪" if d.get("is_mock", True) else "✅",
        )
    console.print(table)


@deploy_app.command("status")
def deploy_status(deployment_id: str = typer.Argument(...)):
    """Get deployment status."""
    with _client() as c:
        try:
            r = c.get(f"/api/v1/deployments/{deployment_id}", headers=_headers())
            r.raise_for_status()
            d = r.json()
        except Exception as exc:
            console.print(f"[red]❌ {exc}[/]")
            raise typer.Exit(1)
    console.print_json(json.dumps(d, indent=2))


@deploy_app.command("stop")
def deploy_stop(deployment_id: str = typer.Argument(...)):
    """Stop a deployment."""
    with _client() as c:
        try:
            r = c.delete(f"/api/v1/deployments/{deployment_id}", headers=_headers())
            r.raise_for_status()
        except Exception as exc:
            console.print(f"[red]❌ {exc}[/]")
            raise typer.Exit(1)
    console.print(f"[green]✅ Deployment {deployment_id} stopped.[/]")


# ── Benchmark subcommands ─────────────────────────────────────────────────────
bench_app = typer.Typer(help="Benchmarking")
app.add_typer(bench_app, name="benchmark")


@bench_app.command("run")
def bench_run(
    model_id: str = typer.Option(..., "--model", help="Model ID"),
    deployment_id: str = typer.Option(..., "--deployment", help="Deployment ID"),
    requests: int = typer.Option(50, "--requests", help="Number of requests"),
    concurrency: int = typer.Option(4, "--concurrency"),
    context: int = typer.Option(512, "--context", help="Context length"),
):
    """Run an inference benchmark."""
    with _client() as c:
        try:
            r = c.post("/api/v1/benchmarks",
                       json={"model_id": model_id, "deployment_id": deployment_id,
                             "num_requests": requests, "concurrency": concurrency,
                             "context_length": context},
                       headers=_headers())
            r.raise_for_status()
            result = r.json()
        except Exception as exc:
            console.print(f"[red]❌ {exc}[/]")
            raise typer.Exit(1)

    is_mock = result.get("is_mock", True)
    console.print(Panel(
        f"{'🧪 MOCK — not real GPU execution' if is_mock else '📊 MEASURED'}\n\n"
        f"Benchmark ID : [cyan]{result.get('benchmark_id', '')}[/]\n"
        f"TPS          : {result.get('tps', 0):.1f} tokens/s\n"
        f"P50 Latency  : {result.get('p50_latency_ms', 0):.1f} ms\n"
        f"P95 Latency  : {result.get('p95_latency_ms', 0):.1f} ms\n"
        f"Failure Rate : {result.get('failure_rate', 0)*100:.1f}%\n"
        f"Cost/task    : ${result.get('cost_per_task_usd', 0):.6f}",
        title=f"Benchmark: {model_id}",
    ))


@bench_app.command("results")
def bench_results(model_id: Optional[str] = typer.Option(None, "--model")):
    """List benchmark results."""
    with _client() as c:
        params = {}
        if model_id:
            params["model_id"] = model_id
        try:
            r = c.get("/api/v1/benchmarks", params=params, headers=_headers())
            r.raise_for_status()
            results = r.json()
        except Exception as exc:
            console.print(f"[red]❌ {exc}[/]")
            raise typer.Exit(1)

    table = Table(title="Benchmark Results", show_lines=True)
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Model")
    table.add_column("TPS", justify="right")
    table.add_column("P95 ms", justify="right")
    table.add_column("Fail%", justify="right")
    table.add_column("Mock", justify="center")
    for res in results:
        cfg = res.get("config", {})
        table.add_row(
            res.get("benchmark_id", "")[:16] + "…",
            cfg.get("model_id", ""),
            f"{res.get('tps', 0):.1f}",
            f"{res.get('p95_latency_ms', 0):.0f}",
            f"{res.get('failure_rate', 0)*100:.1f}%",
            "🧪" if res.get("is_mock", True) else "✅",
        )
    console.print(table)


if __name__ == "__main__":
    app()
