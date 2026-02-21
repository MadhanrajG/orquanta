#!/usr/bin/env python3
"""
OrQuanta Quickstart
===================
The fastest way to see OrQuanta's 5 AI agents in action.
No cloud accounts needed — runs fully in demo mode.

Usage:
    python quickstart.py           # Full demo with 3 scenarios
    python quickstart.py --api     # Start API only (no browser)
    python quickstart.py --check   # Verify deps and exit
"""
import sys, os, time, subprocess, webbrowser, importlib

ASCII_LOGO = """
  ██████╗  ██████╗ 
 ██╔═══██╗██╔═══██╗
 ██║   ██║██║   ██║
 ██║   ██║██║▄▄ ██║
 ╚██████╔╝╚██████╔╝
  ╚═════╝  ╚══▀▀═╝ 
"""

CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"

def c(color, text): return f"{color}{text}{RESET}"

REQUIRED_PACKAGES = [
    ("fastapi",      "fastapi>=0.110"),
    ("uvicorn",      "uvicorn[standard]"),
    ("pydantic",     "pydantic>=2"),
    ("redis",        "redis"),
    ("jose",         "python-jose[cryptography]"),
    ("passlib",      "passlib[bcrypt]"),
    ("httpx",        "httpx"),
]

def banner():
    print(c(CYAN, ASCII_LOGO))
    print(c(BOLD, "  OrQuanta Agentic v1.0"))
    print(c(DIM,  "  Orchestrate. Optimize. Evolve."))
    print()

def check_python():
    v = sys.version_info
    if v < (3, 11):
        print(c(RED, f"  ✗ Python 3.11+ required (you have {v.major}.{v.minor})"))
        sys.exit(1)
    print(c(GREEN, f"  ✓ Python {v.major}.{v.minor}.{v.micro}"))

def check_deps():
    missing = []
    for module, pip_name in REQUIRED_PACKAGES:
        try:
            importlib.import_module(module)
            print(c(GREEN, f"  ✓ {pip_name}"))
        except ImportError:
            print(c(YELLOW, f"  ○ {pip_name} — not installed"))
            missing.append(pip_name)
    return missing

def install_missing(missing):
    if not missing:
        return True
    print()
    print(c(YELLOW, f"  Installing {len(missing)} missing packages..."))
    cmd = [sys.executable, "-m", "pip", "install", "--quiet"] + missing
    result = subprocess.run(cmd)
    return result.returncode == 0

def start_api():
    print(c(DIM, "  Starting OrQuanta API on http://localhost:8000 ..."))
    env = os.environ.copy()
    env["DEMO_MODE"] = "true"
    env["JWT_SECRET"] = "orquanta-quickstart-secret-2026"
    env["DATABASE_URL"] = "sqlite+aiosqlite:///./orquanta_quickstart.db"
    
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "v4.api.main:app",
         "--host", "0.0.0.0", "--port", "8000", "--log-level", "warning"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc

def wait_for_api(max_tries=20):
    import urllib.request, urllib.error
    for i in range(max_tries):
        try:
            r = urllib.request.urlopen("http://localhost:8000/health", timeout=2)
            if r.status == 200:
                return True
        except Exception:
            pass
        time.sleep(1.5)
        print(c(DIM, f"  Waiting for API... ({i+1}/{max_tries})"), end="\r")
    print()
    return False

def main():
    banner()

    api_only = "--api" in sys.argv
    check_only = "--check" in sys.argv

    print(c(BOLD, "  Checking dependencies"))
    print(c(DIM,  "  " + "─" * 38))
    check_python()
    missing = check_deps()

    if check_only:
        if missing:
            print(c(YELLOW, f"\n  {len(missing)} packages missing. Run: pip install -r requirements_minimal.txt"))
        else:
            print(c(GREEN, "\n  ✓ All dependencies satisfied. Ready to launch!"))
        sys.exit(0)

    if missing:
        print()
        response = input(c(YELLOW, f"  Install {len(missing)} missing packages? [Y/n] ")).strip().lower()
        if response in ("", "y", "yes"):
            if not install_missing(missing):
                print(c(RED, "  ✗ Installation failed. Run: pip install -r requirements_minimal.txt"))
                sys.exit(1)
        else:
            print(c(RED, "  Aborted. Run: pip install -r requirements_minimal.txt"))
            sys.exit(1)

    print()
    print(c(BOLD, "  Starting OrQuanta in Demo Mode"))
    print(c(DIM,  "  " + "─" * 38))
    print(c(DIM,  "  DEMO_MODE=true — no cloud accounts needed"))
    print(c(DIM,  "  3 scenarios will run automatically:"))
    print(c(DIM,  "    1. Cost Optimizer (Lambda Labs vs AWS)"))
    print(c(DIM,  "    2. Self-Healing (OOM recovery in 8.3s)"))
    print(c(DIM,  "    3. Natural Language Goal → Running GPU job"))
    print()

    proc = start_api()

    print(c(DIM, "  Waiting for API..."), end="", flush=True)
    if wait_for_api():
        print(c(GREEN, "\r  ✓ OrQuanta API ready at http://localhost:8000    "))
    else:
        print(c(YELLOW, "\r  ⚠ API may still be starting — opening browser anyway"))

    print()

    if not api_only:
        demo_url = "http://localhost:8000/demo"
        dash_url = "http://localhost:3000"

        print(c(GREEN, "  ✓ Opening demo in browser..."))
        print()
        print(c(BOLD, "  ┌─────────────────────────────────────────┐"))
        print(c(BOLD, "  │") + c(CYAN, "  OrQuanta is running!                    ") + c(BOLD, "│"))
        print(c(BOLD, "  │") + f"  Demo:      {c(CYAN, demo_url)}       " + c(BOLD, "│"))
        print(c(BOLD, "  │") + f"  API Docs:  {c(CYAN, 'http://localhost:8000/docs')}  " + c(BOLD, "│"))
        print(c(BOLD, "  │") + f"  Dashboard: {c(CYAN, dash_url)}           " + c(BOLD, "│"))
        print(c(BOLD, "  └─────────────────────────────────────────┘"))
        print()
        print(c(DIM, "  Press Ctrl+C to stop"))

        time.sleep(1)
        webbrowser.open(demo_url)

    try:
        proc.wait()
    except KeyboardInterrupt:
        print()
        print(c(DIM, "  Stopping OrQuanta..."))
        proc.terminate()
        proc.wait()
        print(c(GREEN, "  ✓ Stopped cleanly. Thanks for trying OrQuanta!"))
        print()
        print(c(DIM, "  Next steps:"))
        print(c(DIM, "    1. Get a Lambda Labs API key: https://cloud.lambdalabs.com/api-keys"))
        print(c(DIM, "    2. Add to .env: LAMBDA_LABS_API_KEY=your_key"))
        print(c(DIM, "    3. Run: python start_orquanta.py"))
        print(c(DIM, "    4. Submit your first real GPU job in natural language"))
        print()

if __name__ == "__main__":
    main()
