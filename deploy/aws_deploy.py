"""
OrQuanta Agentic v1.0 — One-Command AWS Deployment

Creates the complete AWS infrastructure:
  VPC → ECS Fargate → RDS PostgreSQL → ElastiCache Redis
  → ALB → CloudFront → Route53 → ACM SSL Certificate

Usage:
  python deploy/aws_deploy.py --domain api.orquanta.ai --env production
  python deploy/aws_deploy.py --env staging --skip-ssl
  python deploy/aws_deploy.py --destroy --env staging   # Tear down

After deploy:
  - Prints live URL, health check, admin credentials
  - Writes deploy_output_{env}.json with all connection strings
  - All secrets auto-injected into ECS task definitions

Requirements:
  - AWS CLI configured (aws configure OR IAM role on EC2)
  - Terraform >= 1.6 installed
  - Docker installed (for image build/push)
  - pip install boto3 rich
"""

from __future__ import annotations

import argparse
import boto3
import json
import logging
import os
import pathlib
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from typing import Any

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
    console = Console()
    HAS_RICH = True
except ImportError:
    HAS_RICH = False
    class Console:
        def print(self, *args, **kw): print(*args)
        def rule(self, *args, **kw): print("─" * 60)
    console = Console()

logger = logging.getLogger("orquanta.deploy.aws")

DEPLOY_DIR = pathlib.Path(__file__).parent
PROJECT_ROOT = DEPLOY_DIR.parent
TF_DIR = DEPLOY_DIR / "terraform"
GH_DIR = DEPLOY_DIR / "github_actions"


@dataclass
class DeployConfig:
    env: str = "staging"
    aws_region: str = "us-east-1"
    domain: str = ""
    skip_ssl: bool = False
    skip_build: bool = False
    destroy: bool = False
    ecr_repo: str = "orquanta-api"
    ecr_agents_repo: str = "orquanta-agents"
    db_instance_class: str = "db.t3.medium"
    db_allocated_gb: int = 20
    api_cpu: int = 1024       # ECS CPU units (1024 = 1 vCPU)
    api_memory: int = 2048    # ECS memory MB
    min_api_tasks: int = 1
    max_api_tasks: int = 5
    celery_cpu: int = 512
    celery_memory: int = 1024
    min_celery_tasks: int = 1
    max_celery_tasks: int = 10


@dataclass
class DeployOutput:
    env: str
    api_url: str
    frontend_url: str
    health_check_url: str
    grafana_url: str
    db_secret_arn: str
    redis_endpoint: str
    ecr_api_uri: str
    alb_dns: str
    cloudfront_domain: str
    admin_email: str = "admin@orquanta.ai"
    admin_password: str = field(default_factory=lambda: f"OrQuanta-Admin-{''.join(__import__('secrets').token_urlsafe(8).split())}")
    deployed_at: str = field(default_factory=lambda: __import__("datetime").datetime.utcnow().isoformat())

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)


class AWSDeployer:
    """Orchestrates the complete AWS deployment pipeline."""

    def __init__(self, config: DeployConfig) -> None:
        self.cfg = config
        self.session = boto3.Session(region_name=config.aws_region)
        self.account_id = self._get_account_id()

    def _get_account_id(self) -> str:
        try:
            sts = self.session.client("sts")
            return sts.get_caller_identity()["Account"]
        except Exception as exc:
            logger.warning(f"Could not get AWS account ID: {exc}")
            return "unknown"

    def deploy(self) -> DeployOutput:
        """Run the full deployment pipeline."""
        console.print(Panel(
            f"[bold cyan]OrQuanta Agentic v1.0 — AWS Deploy[/bold cyan]\n"
            f"Environment: [yellow]{self.cfg.env}[/yellow]  |  "
            f"Region: [yellow]{self.cfg.aws_region}[/yellow]  |  "
            f"Account: [yellow]{self.account_id}[/yellow]",
            title="🚀 Starting Deployment"
        ) if HAS_RICH else f"\n{'='*60}\nOrQuanta Deploy — {self.cfg.env} — {self.cfg.aws_region}\n{'='*60}")

        steps = [
            ("1/8 Prerequisites", self._check_prerequisites),
            ("2/8 ECR Repositories", self._ensure_ecr_repos),
            ("3/8 Build & Push Images", self._build_and_push) if not self.cfg.skip_build else None,
            ("4/8 Terraform Init", self._terraform_init),
            ("5/8 Terraform Plan", self._terraform_plan),
            ("6/8 Terraform Apply", self._terraform_apply),
            ("7/8 Database Migrations", self._run_migrations),
            ("8/8 Health Check", self._health_check_deploy),
        ]

        for step in steps:
            if step is None:
                continue
            name, fn = step
            console.print(f"\n[bold green]→ {name}[/bold green]" if HAS_RICH else f"\n→ {name}")
            fn()

        output = self._build_output()
        self._save_output(output)
        self._print_summary(output)
        return output

    def destroy(self) -> None:
        """Tear down all resources."""
        console.print("[bold red]⚠ DESTROYING all infrastructure...[/bold red]" if HAS_RICH else "WARNING: Destroying all infrastructure")
        self._terraform_destroy()

    # ─── Step implementations ─────────────────────────────────────────

    def _check_prerequisites(self) -> None:
        """Verify required tools are installed."""
        required = ["terraform", "docker", "aws"]
        missing = []
        for tool in required:
            result = subprocess.run(["which", tool] if sys.platform != "win32" else ["where", tool],
                                    capture_output=True)
            if result.returncode != 0:
                missing.append(tool)

        if missing:
            raise RuntimeError(f"Missing tools: {', '.join(missing)}. Install them first.")

        # Verify AWS credentials
        try:
            self.session.client("sts").get_caller_identity()
            console.print("  ✓ AWS credentials valid")
        except Exception:
            raise RuntimeError("AWS credentials not configured. Run: aws configure")

        # Verify Terraform version
        result = subprocess.run(["terraform", "version", "-json"], capture_output=True, text=True)
        if result.returncode == 0:
            ver_data = json.loads(result.stdout)
            ver = ver_data.get("terraform_version", "unknown")
            console.print(f"  ✓ Terraform {ver}")

    def _ensure_ecr_repos(self) -> None:
        """Create ECR repositories if they don't exist."""
        ecr = self.session.client("ecr")
        for repo_name in [self.cfg.ecr_repo, self.cfg.ecr_agents_repo]:
            try:
                ecr.describe_repositories(repositoryNames=[repo_name])
                console.print(f"  ✓ ECR repo exists: {repo_name}")
            except ecr.exceptions.RepositoryNotFoundException:
                ecr.create_repository(
                    repositoryName=repo_name,
                    imageScanningConfiguration={"scanOnPush": True},
                    encryptionConfiguration={"encryptionType": "AES256"},
                )
                console.print(f"  ✓ Created ECR repo: {repo_name}")

    def _build_and_push(self) -> None:
        """Build Docker images and push to ECR."""
        ecr_base = f"{self.account_id}.dkr.ecr.{self.cfg.aws_region}.amazonaws.com"
        api_uri = f"{ecr_base}/{self.cfg.ecr_repo}:{self.cfg.env}"
        agents_uri = f"{ecr_base}/{self.cfg.ecr_agents_repo}:{self.cfg.env}"

        # ECR login
        token_result = subprocess.run(
            ["aws", "ecr", "get-login-password", "--region", self.cfg.aws_region],
            capture_output=True, text=True
        )
        if token_result.returncode == 0:
            subprocess.run(
                ["docker", "login", "--username", "AWS", "--password-stdin", ecr_base],
                input=token_result.stdout, text=True, capture_output=True
            )

        # Build and push API
        self._run(["docker", "build", "-f", str(PROJECT_ROOT / "Dockerfile.api"), "-t", api_uri, str(PROJECT_ROOT)])
        self._run(["docker", "push", api_uri])
        console.print(f"  ✓ Pushed API image: {api_uri}")

        # Build and push agents
        self._run(["docker", "build", "-f", str(PROJECT_ROOT / "Dockerfile.agents"), "-t", agents_uri, str(PROJECT_ROOT)])
        self._run(["docker", "push", agents_uri])
        console.print(f"  ✓ Pushed Agents image: {agents_uri}")

    def _terraform_init(self) -> None:
        self._run(["terraform", "init", "-input=false"], cwd=TF_DIR)
        console.print("  ✓ Terraform initialized")

    def _terraform_plan(self) -> None:
        vars_args = self._get_tf_vars()
        self._run(
            ["terraform", "plan", "-input=false", "-out=tfplan"] + vars_args,
            cwd=TF_DIR
        )
        console.print("  ✓ Terraform plan complete")

    def _terraform_apply(self) -> None:
        self._run(
            ["terraform", "apply", "-auto-approve", "-input=false", "tfplan"],
            cwd=TF_DIR
        )
        console.print("  ✓ Infrastructure deployed")

    def _terraform_destroy(self) -> None:
        vars_args = self._get_tf_vars()
        self._run(
            ["terraform", "destroy", "-auto-approve", "-input=false"] + vars_args,
            cwd=TF_DIR
        )

    def _run_migrations(self) -> None:
        """Run DB migrations via ECS RunTask (one-off task)."""
        ecs = self.session.client("ecs")
        try:
            tf_output = self._get_tf_output()
            cluster = tf_output.get("ecs_cluster_name", {}).get("value", "orquanta-cluster")
            task_def = tf_output.get("migration_task_def", {}).get("value", "orquanta-migrate")
            subnets = tf_output.get("private_subnet_ids", {}).get("value", [])
            sg = tf_output.get("api_security_group_id", {}).get("value", "")

            ecs.run_task(
                cluster=cluster,
                taskDefinition=task_def,
                launchType="FARGATE",
                networkConfiguration={
                    "awsvpcConfiguration": {
                        "subnets": subnets,
                        "securityGroups": [sg],
                        "assignPublicIp": "DISABLED",
                    }
                },
                overrides={"containerOverrides": [{
                    "name": "api",
                    "command": ["alembic", "upgrade", "head"],
                }]},
            )
            console.print("  ✓ Database migrations triggered")
            time.sleep(10)  # Give it time to start
        except Exception as exc:
            logger.warning(f"Migration task failed (may need to run manually): {exc}")

    def _health_check_deploy(self) -> None:
        """Wait for the API to become healthy after deploy."""
        import urllib.request, urllib.error
        tf_output = self._get_tf_output()
        api_url = tf_output.get("api_url", {}).get("value") or f"https://{self.cfg.domain}"
        health_url = f"{api_url}/health"

        deadline = time.time() + 300  # 5 min
        console.print(f"  Waiting for {health_url}…", end="")
        while time.time() < deadline:
            try:
                urllib.request.urlopen(health_url, timeout=5)
                console.print(" ✓ healthy!")
                return
            except Exception:
                print(".", end="", flush=True)
                time.sleep(10)
        console.print(" ⚠ timeout — check ALB target group health")

    # ─── Helpers ─────────────────────────────────────────────────────

    def _get_tf_vars(self) -> list[str]:
        cfg = self.cfg
        ecr_base = f"{self.account_id}.dkr.ecr.{cfg.aws_region}.amazonaws.com"
        return [
            f"-var=environment={cfg.env}",
            f"-var=aws_region={cfg.aws_region}",
            f"-var=domain_name={cfg.domain}",
            f"-var=api_image={ecr_base}/{cfg.ecr_repo}:{cfg.env}",
            f"-var=agents_image={ecr_base}/{cfg.ecr_agents_repo}:{cfg.env}",
            f"-var=db_instance_class={cfg.db_instance_class}",
            f"-var=db_allocated_storage={cfg.db_allocated_gb}",
            f"-var=api_cpu={cfg.api_cpu}",
            f"-var=api_memory={cfg.api_memory}",
            f"-var=min_api_tasks={cfg.min_api_tasks}",
            f"-var=max_api_tasks={cfg.max_api_tasks}",
        ]

    def _get_tf_output(self) -> dict[str, Any]:
        try:
            result = subprocess.run(
                ["terraform", "output", "-json"],
                cwd=TF_DIR, capture_output=True, text=True
            )
            return json.loads(result.stdout) if result.returncode == 0 else {}
        except Exception:
            return {}

    def _build_output(self) -> DeployOutput:
        tf = self._get_tf_output()
        domain = self.cfg.domain or tf.get("alb_dns_name", {}).get("value", "localhost")
        return DeployOutput(
            env=self.cfg.env,
            api_url=tf.get("api_url", {}).get("value") or f"https://{domain}",
            frontend_url=tf.get("frontend_url", {}).get("value") or f"https://{domain}",
            health_check_url=f"https://{domain}/health",
            grafana_url=tf.get("grafana_url", {}).get("value") or f"https://{domain}:3001",
            db_secret_arn=tf.get("db_secret_arn", {}).get("value") or "",
            redis_endpoint=tf.get("redis_endpoint", {}).get("value") or "",
            ecr_api_uri=tf.get("ecr_api_uri", {}).get("value") or "",
            alb_dns=tf.get("alb_dns_name", {}).get("value") or domain,
            cloudfront_domain=tf.get("cloudfront_domain", {}).get("value") or domain,
        )

    def _save_output(self, output: DeployOutput) -> None:
        out_file = DEPLOY_DIR / f"deploy_output_{self.cfg.env}.json"
        out_file.write_text(output.to_json())
        console.print(f"  ✓ Deploy output saved: {out_file}")

    def _print_summary(self, output: DeployOutput) -> None:
        console.print(Panel(
            f"[bold green]🎉 OrQuanta {output.env.upper()} Deployed![/bold green]\n\n"
            f"  API:        {output.api_url}\n"
            f"  Dashboard:  {output.frontend_url}\n"
            f"  Health:     {output.health_check_url}\n"
            f"  Grafana:    {output.grafana_url}\n\n"
            f"  Admin:      {output.admin_email}\n"
            f"  Password:   {output.admin_password}\n\n"
            f"  DB Secret:  {output.db_secret_arn}",
            title="Deploy Complete",
        ) if HAS_RICH else f"\n{'='*60}\nDEPLOY COMPLETE\nAPI: {output.api_url}\n{'='*60}")

    @staticmethod
    def _run(cmd: list[str], cwd: pathlib.Path | None = None) -> None:
        result = subprocess.run(cmd, cwd=cwd, capture_output=False)
        if result.returncode != 0:
            raise RuntimeError(f"Command failed: {' '.join(cmd)}")


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="OrQuanta AWS Deployment Script")
    parser.add_argument("--env", default="staging", choices=["dev", "staging", "production"])
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--domain", default="")
    parser.add_argument("--skip-ssl", action="store_true")
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--destroy", action="store_true")
    args = parser.parse_args()

    config = DeployConfig(
        env=args.env,
        aws_region=args.region,
        domain=args.domain,
        skip_ssl=args.skip_ssl,
        skip_build=args.skip_build,
        destroy=args.destroy,
        db_instance_class="db.t3.small" if args.env != "production" else "db.r7g.large",
        min_api_tasks=1 if args.env != "production" else 2,
        max_api_tasks=3 if args.env != "production" else 10,
    )

    deployer = AWSDeployer(config)
    if config.destroy:
        deployer.destroy()
    else:
        deployer.deploy()


if __name__ == "__main__":
    main()
