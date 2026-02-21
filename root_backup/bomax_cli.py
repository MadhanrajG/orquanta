"""
OrQuanta CLI - Professional Command Line Interface
"""

import typer
import requests
import json
import time
import os
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.live import Live
from rich.layout import Layout
from rich.align import Align

app = typer.Typer(help="OrQuanta Cloud CLI - Enterprise Autonomous GPU Management")
console = Console()

API_URL = "http://localhost:8000/api/v1"
CONFIG_FILE = ".orquanta_config"

def get_api_key():
    if not os.path.exists(CONFIG_FILE):
        return None
    with open(CONFIG_FILE, "r") as f:
        return f.read().strip()

def save_api_key(key):
    with open(CONFIG_FILE, "w") as f:
        f.write(key)

def get_headers():
    key = get_api_key()
    if not key:
        console.print("[red]Not logged in. Run 'orquanta_cli.py login' first.[/red]")
        raise typer.Exit()
    return {"Authorization": f"Bearer {key}"}

@app.command()
def login(email: str = typer.Option(..., prompt=True), password: str = typer.Option(..., prompt=True, hide_input=True)):
    """Authenticate with OrQuanta Cloud"""
    with console.status("[bold green]Authenticating..."):
        try:
            # Try login first
            resp = requests.post(f"{API_URL}/auth/login", json={"email": email, "password": password})
            if resp.status_code == 200:
                key = resp.json()["api_key"]
                save_api_key(key)
                console.print(Panel(f"[green]Successfully logged in![/green]\nAPI Key stored securely.", title="Login Success"))
                return

            # If login fails, try register (auto-onboard for demo)
            console.print("[yellow]Account not found, registering new account...[/yellow]")
            reg_resp = requests.post(f"{API_URL}/auth/register", json={
                "email": email, "password": password, "full_name": "CLI User", "company": "CLI Corp"
            })
            if reg_resp.status_code == 200:
                key = reg_resp.json()["api_key"]
                save_api_key(key)
                console.print(Panel(f"[green]Account created & logged in![/green]", title="Registration Success"))
            else:
                console.print(f"[red]Login failed: {resp.text}[/red]")
        except Exception as e:
            console.print(f"[red]Connection failed: {e}[/red]")

@app.command()
def status():
    """View Live Platform Dashboard"""
    try:
        resp = requests.get(f"http://localhost:8000/api/v1/status") # Public endpoint
        data = resp.json()
        
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body")
        )
        
        layout["header"].update(Panel(f"[bold blue]🚀 {data['platform']} v{data['version']}[/bold blue] | Status: [green]{data['status'].upper()}[/green]", style="on #0f172a"))
        
        grid = Table.grid(expand=True)
        grid.add_column(justify="center", ratio=1)
        grid.add_column(justify="center", ratio=1)
        grid.add_column(justify="center", ratio=1)
        
        grid.add_row(
            Panel(f"[bold]{data['uptime']}[/bold]", title="Uptime", style="green"),
            Panel(f"[bold]{data['active_gpus']} / {data['total_gpus']}[/bold]", title="GPU Usage", style="yellow"),
            Panel(f"[bold]{data['active_users']}[/bold]", title="Active Users", style="blue"),
        )
        
        layout["body"].update(grid)
        console.print(layout)
        
    except Exception as e:
        console.print(f"[red]Could not fetch status: {e}[/red]")

@app.command()
def list():
    """List My Active Jobs"""
    headers = get_headers()
    jobs = requests.get(f"{API_URL}/jobs", headers=headers).json()
    
    table = Table(title="Active GPU Jobs")
    table.add_column("ID", style="cyan")
    table.add_column("Status", style="magenta")
    table.add_column("GPU", style="green")
    table.add_column("Created", style="dim")
    
    for job in jobs:
        status_color = "green" if job['status'] == 'running' else "yellow" if job['status'] == 'pending' else "blue"
        table.add_row(
            job['job_id'], 
            f"[{status_color}]{job['status'].upper()}[/{status_color}]",
            f"{job['gpu_count']}x {job['gpu_type']}",
            job['created_at'].split("T")[1][:8] # Show time only
        )
    console.print(table)

@app.command()
def launch(description: str = typer.Option(None, prompt="Describe your workload (for AI Advisor)")):
    """Launch a new GPU Job with AI Advisor"""
    headers = get_headers()
    
    # 1. AI Recommendation
    with console.status("[bold purple]🧠 AI Advisor analysis in progress..."):
        rec = requests.post(f"{API_URL}/ai/recommend", json={
            "workload_description": description, "priority": "performance"
        }).json()
        
    console.print(Panel(
        f"[bold]Recommendation:[/bold] {rec['gpu_count']}x [cyan]{rec['recommended_gpu']}[/cyan]\n"
        f"[bold]Reasoning:[/bold] {rec['reasoning']}\n"
        f"[bold]Est. Cost:[/bold] ${rec['estimated_cost']}/hr",
        title="🤖 OrQuanta Intelligence", border_style="purple"
    ))
    
    if Confirm.ask("🚀 Launch this configuration?"):
        job = requests.post(f"{API_URL}/jobs", headers=headers, json={
            "gpu_type": rec["recommended_gpu"],
            "gpu_count": rec["gpu_count"],
            "spot_instance": True
        }).json()
        console.print(f"[green]Job Launched Successfully![/green] ID: [bold]{job['job_id']}[/bold]")
        console.print(f"Run [cyan]python orquanta_cli.py logs {job['job_id']}[/cyan] to watch it.")

@app.command()
def logs(job_id: str):
    """Stream Live Logs for a Job"""
    headers = get_headers()
    console.print(f"[dim]Streaming logs for {job_id} (Ctrl+C to stop)...[/dim]")
    
    last_log_count = 0
    try:
        for _ in range(60): # Watch for 60 seconds max for demo
            resp = requests.get(f"{API_URL}/jobs/{job_id}/logs", headers=headers)
            if resp.status_code != 200:
                console.print(f"[red]Job not found or access denied.[/red]")
                break
                
            logs = resp.json().get("logs", [])
            if len(logs) > last_log_count:
                for log in logs[last_log_count:]:
                    console.print(f"[grey70]{log}[/grey70]")
                last_log_count = len(logs)
            
            time.sleep(2)
    except KeyboardInterrupt:
        console.print("\n[yellow]Log streaming stopped.[/yellow]")

if __name__ == "__main__":
    app()
