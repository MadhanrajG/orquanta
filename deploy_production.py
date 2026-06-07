#!/usr/bin/env python3
"""
OrQuanta Production Deploy — $0/month Stack
=============================================
Deploys all 3 services in the correct order:
  1. Build React frontend (Vite)
  2. Deploy to Cloudflare Pages
  3. Deploy Cloudflare Worker (edge router)
  4. Backend auto-deploys from git push to Render

Prerequisites:
  - npm install -g wrangler
  - wrangler login
  - cd v4/frontend && npm install
"""

import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(ROOT, "v4", "frontend")
DIST_DIR = os.path.join(FRONTEND_DIR, "dist")

RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"

def run(cmd, cwd=ROOT, check=True):
    print(f"  {CYAN}>{RESET} {cmd}")
    result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"  {RED}FAILED{RESET}: {result.stderr[:500]}")
        return False
    return True

def main():
    print(f"\n{BOLD}{CYAN}OrQuanta Production Deploy{RESET}")
    print(f"{CYAN}{'=' * 50}{RESET}\n")
    
    errors = []
    
    # Step 1: Build React Frontend
    print(f"{BOLD}[1/3] Building React Frontend...{RESET}")
    if not run("npm run build", cwd=FRONTEND_DIR):
        errors.append("Frontend build failed")
        print(f"  {RED}SKIP remaining steps — build failed{RESET}")
        return 1
    
    if os.path.isdir(DIST_DIR):
        file_count = sum(len(f) for _, _, f in os.walk(DIST_DIR))
        print(f"  {GREEN}OK{RESET} Built {file_count} files in dist/\n")
    else:
        errors.append("dist/ directory not found after build")
        return 1
    
    # Step 2: Deploy to Cloudflare Pages
    print(f"{BOLD}[2/3] Deploying to Cloudflare Pages...{RESET}")
    if not run(f"npx wrangler pages deploy dist --project-name orquanta-app --branch main", cwd=FRONTEND_DIR):
        errors.append("Cloudflare Pages deploy failed")
    else:
        print(f"  {GREEN}OK{RESET} Frontend deployed to orquanta-app.pages.dev\n")
    
    # Step 3: Deploy Cloudflare Worker
    print(f"{BOLD}[3/3] Deploying Cloudflare Worker...{RESET}")
    if not run("npx wrangler deploy", cwd=ROOT):
        errors.append("Worker deploy failed")
    else:
        print(f"  {GREEN}OK{RESET} Worker deployed to orquanta.com\n")
    
    # Summary
    print(f"\n{BOLD}{'=' * 50}{RESET}")
    if errors:
        print(f"{RED}Deploy completed with errors:{RESET}")
        for e in errors:
            print(f"  {RED}x{RESET} {e}")
        return 1
    else:
        print(f"{GREEN}{BOLD}All services deployed successfully!{RESET}")
        print(f"\n  Landing:   https://orquanta.com")
        print(f"  Dashboard: https://orquanta.com/app/")
        print(f"  API Docs:  https://orquanta.com/docs")
        print(f"  Health:    https://orquanta.com/health")
        print(f"\n  {YELLOW}Note:{RESET} Backend on Render auto-deploys from git push.")
        print(f"  Run: git add -A && git commit -m 'deploy: white UI + QA fixes' && git push origin main")
        return 0

if __name__ == "__main__":
    sys.exit(main())
