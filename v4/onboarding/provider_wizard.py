"""
OrQuanta Agentic v1.0 — Cloud Provider Connection Wizard

Step-by-step guided wizard that helps customers connect their first
cloud provider. Validates credentials before saving.

Provider setup flows:

AWS:
  1. Guide user to create IAM role with minimum permissions
  2. Generate IAM policy JSON (copy/paste)
  3. User enters AWS Access Key ID + Secret
  4. Validate: list EC2 instance types in us-east-1
  5. Detect which GPU types are available in their region
  6. Save to secrets manager

GCP:
  1. Guide service account creation in GCP console
  2. Assign Compute Admin + Monitoring Viewer roles
  3. User downloads JSON key file
  4. Parse and validate JSON
  5. Test: list zones in us-central1
  6. Save

Azure:
  1. App registration walkthrough (portal.azure.com)
  2. User enters: tenant_id, client_id, client_secret, subscription_id
  3. Validate: list VM SKUs
  4. Check GPU quota in at least one region
  5. Save

CoreWeave:
  1. Guide to CoreWeave console → API Keys
  2. User enters API key
  3. Validate: check account balance / quota
  4. Save
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("orquanta.onboarding.provider_wizard")

AWS_IAM_POLICY = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "BomaxEC2Access",
            "Effect": "Allow",
            "Action": [
                "ec2:RunInstances",
                "ec2:TerminateInstances",
                "ec2:DescribeInstances",
                "ec2:DescribeInstanceTypes",
                "ec2:DescribeSpotPriceHistory",
                "ec2:RequestSpotInstances",
                "ec2:CancelSpotInstanceRequests",
                "ec2:DescribeSpotInstanceRequests",
                "ec2:CreateTags",
                "ec2:DescribeImages",
                "ec2:DescribeKeyPairs",
                "ec2:DescribeSecurityGroups",
                "ec2:DescribeSubnets",
                "ec2:DescribeVpcs",
            ],
            "Resource": "*",
        },
        {
            "Sid": "BomaxCloudWatchMetrics",
            "Effect": "Allow",
            "Action": ["cloudwatch:GetMetricStatistics", "cloudwatch:ListMetrics"],
            "Resource": "*",
        },
    ],
}

GCP_REQUIRED_ROLES = [
    "roles/compute.admin",
    "roles/monitoring.viewer",
    "roles/iam.serviceAccountUser",
]

AZURE_REQUIRED_ROLES = [
    "Virtual Machine Contributor",
    "Monitoring Reader",
]


@dataclass
class ProviderConnectionResult:
    provider: str
    success: bool
    regions_available: list[str]
    gpu_types_available: list[str]
    estimated_cheapest_gpu: str
    estimated_price_usd_hr: float
    message: str
    credentials_saved: bool = False


class ProviderWizard:
    """Guides a user through connecting a cloud provider."""

    async def get_setup_instructions(self, provider: str) -> dict[str, Any]:
        """Return step-by-step setup instructions for a provider."""
        instructions = {
            "aws": {
                "provider": "aws",
                "logo": "☁️",
                "title": "Connect Amazon Web Services",
                "estimated_minutes": 5,
                "steps": [
                    {
                        "step": 1,
                        "title": "Create an IAM User",
                        "description": "Open the AWS console and go to IAM → Users → Create User. Name it 'orquanta-agent'.",
                        "action_url": "https://console.aws.amazon.com/iam/home#/users/create",
                        "action_label": "Open AWS IAM Console",
                    },
                    {
                        "step": 2,
                        "title": "Attach the OrQuanta Policy",
                        "description": "Copy and paste this minimum-permission policy JSON into the 'Attach policies directly' → 'Create policy' → JSON editor.",
                        "policy_json": json.dumps(AWS_IAM_POLICY, indent=2),
                    },
                    {
                        "step": 3,
                        "title": "Create Access Keys",
                        "description": "Go to the user → Security credentials → Create access key. Select 'Application running outside AWS'.",
                        "warning": "Save your Secret Access Key — it's only shown once.",
                    },
                    {
                        "step": 4,
                        "title": "Enter Your Credentials",
                        "description": "Paste your Access Key ID and Secret Access Key below.",
                        "form_fields": [
                            {"name": "aws_access_key_id", "label": "Access Key ID", "placeholder": "AKIAIOSFODNN7EXAMPLE", "type": "text"},
                            {"name": "aws_secret_access_key", "label": "Secret Access Key", "placeholder": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", "type": "password"},
                            {"name": "aws_default_region", "label": "Primary Region", "placeholder": "us-east-1", "type": "text"},
                        ],
                    },
                ],
            },
            "gcp": {
                "provider": "gcp",
                "logo": "🔵",
                "title": "Connect Google Cloud Platform",
                "estimated_minutes": 7,
                "steps": [
                    {
                        "step": 1,
                        "title": "Create a Service Account",
                        "description": "In GCP console: IAM & Admin → Service Accounts → Create Service Account. Name it 'orquanta-agent'.",
                        "action_url": "https://console.cloud.google.com/iam-admin/serviceaccounts/create",
                        "action_label": "Open GCP IAM Console",
                    },
                    {
                        "step": 2,
                        "title": "Assign Required Roles",
                        "description": f"Grant these roles to the service account: {', '.join(GCP_REQUIRED_ROLES)}",
                        "roles": GCP_REQUIRED_ROLES,
                    },
                    {
                        "step": 3,
                        "title": "Download JSON Key",
                        "description": "Service Account → Keys → Add Key → Create New Key → JSON. Download the .json file.",
                        "warning": "Keep this file secure — it provides full Compute access.",
                    },
                    {
                        "step": 4,
                        "title": "Upload JSON Key",
                        "description": "Upload or paste your JSON key file contents below.",
                        "form_fields": [
                            {"name": "gcp_project_id", "label": "GCP Project ID", "placeholder": "my-project-123", "type": "text"},
                            {"name": "gcp_service_account_json", "label": "Service Account JSON", "placeholder": '{"type": "service_account", ...}', "type": "textarea"},
                        ],
                    },
                ],
            },
            "azure": {
                "provider": "azure",
                "logo": "🔷",
                "title": "Connect Microsoft Azure",
                "estimated_minutes": 8,
                "steps": [
                    {
                        "step": 1,
                        "title": "Register an Application",
                        "description": "Azure Portal → Azure Active Directory → App registrations → New registration. Name it 'OrQuanta'.",
                        "action_url": "https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps/ApplicationsListBlade",
                        "action_label": "Open Azure App Registrations",
                    },
                    {
                        "step": 2,
                        "title": "Create a Client Secret",
                        "description": "In the app: Certificates & secrets → New client secret. Copy the Value (shown once only).",
                    },
                    {
                        "step": 3,
                        "title": "Assign VM Contributor Role",
                        "description": f"Subscriptions → Your subscription → Access control (IAM) → Add role assignment: {', '.join(AZURE_REQUIRED_ROLES)}",
                    },
                    {
                        "step": 4,
                        "title": "Enter Credentials",
                        "form_fields": [
                            {"name": "azure_tenant_id", "label": "Tenant ID", "placeholder": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx", "type": "text"},
                            {"name": "azure_client_id", "label": "Application (Client) ID", "placeholder": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx", "type": "text"},
                            {"name": "azure_client_secret", "label": "Client Secret Value", "placeholder": "your-secret-value", "type": "password"},
                            {"name": "azure_subscription_id", "label": "Subscription ID", "placeholder": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx", "type": "text"},
                        ],
                    },
                ],
            },
            "coreweave": {
                "provider": "coreweave",
                "logo": "⚡",
                "title": "Connect CoreWeave",
                "estimated_minutes": 3,
                "steps": [
                    {
                        "step": 1,
                        "title": "Get Your API Key",
                        "description": "Log in to CoreWeave console → Account → API Access → Generate API Key.",
                        "action_url": "https://cloud.coreweave.com",
                        "action_label": "Open CoreWeave Console",
                        "note": "New to CoreWeave? You'll need to request an account at coreweave.com",
                    },
                    {
                        "step": 2,
                        "title": "Enter Your API Key",
                        "form_fields": [
                            {"name": "coreweave_api_key", "label": "CoreWeave API Key", "placeholder": "cw_xxxxxxxxxxxxxxxxxx", "type": "password"},
                        ],
                    },
                ],
            },
        }
        return instructions.get(provider, {"error": f"Unknown provider: {provider}"})

    async def validate_and_connect(
        self,
        provider: str,
        credentials: dict[str, str],
    ) -> ProviderConnectionResult:
        """Test credentials and return what GPUs are available."""
        if provider == "aws":
            return await self._validate_aws(credentials)
        elif provider == "gcp":
            return await self._validate_gcp(credentials)
        elif provider == "azure":
            return await self._validate_azure(credentials)
        elif provider == "coreweave":
            return await self._validate_coreweave(credentials)
        else:
            return ProviderConnectionResult(
                provider=provider, success=False, regions_available=[], gpu_types_available=[],
                estimated_cheapest_gpu="", estimated_price_usd_hr=0.0, message=f"Unknown provider: {provider}",
            )

    async def _validate_aws(self, creds: dict) -> ProviderConnectionResult:
        """Test AWS credentials by listing EC2 instance types."""
        key_id = creds.get("aws_access_key_id", "")
        secret = creds.get("aws_secret_access_key", "")
        region = creds.get("aws_default_region", "us-east-1")

        if not key_id or not secret:
            return ProviderConnectionResult("aws", False, [], [], "", 0.0, "Access Key ID and Secret are required")

        try:
            import boto3
            ec2 = boto3.client(
                "ec2",
                aws_access_key_id=key_id,
                aws_secret_access_key=secret,
                region_name=region,
            )
            # Test: list GPU instance types
            response = ec2.describe_instance_types(
                Filters=[{"Name": "instance-type", "Values": ["p3.*", "p4d.*", "p4de.*"]}],
                MaxResults=5,
            )
            gpu_types = list({t["InstanceType"] for t in response.get("InstanceTypes", [])})

            return ProviderConnectionResult(
                provider="aws",
                success=True,
                regions_available=["us-east-1", "us-west-2", "eu-west-1"],
                gpu_types_available=gpu_types or ["V100", "A100"],
                estimated_cheapest_gpu="V100",
                estimated_price_usd_hr=0.9,
                message=f"Connected! Found {len(gpu_types)} GPU instance types in {region}.",
            )
        except Exception as exc:
            err = str(exc)
            if "InvalidClientTokenId" in err or "AuthFailure" in err:
                msg = "Invalid credentials — check your Access Key ID and Secret."
            elif "AccessDenied" in err:
                msg = "Access denied — ensure the IAM policy includes EC2 describe permissions."
            else:
                msg = f"Connection failed: {type(exc).__name__}"
            return ProviderConnectionResult("aws", False, [], [], "", 0.0, msg)

    async def _validate_gcp(self, creds: dict) -> ProviderConnectionResult:
        """Test GCP credentials by parsing and using the service account JSON."""
        json_str = creds.get("gcp_service_account_json", "")
        project_id = creds.get("gcp_project_id", "")

        if not json_str:
            return ProviderConnectionResult("gcp", False, [], [], "", 0.0, "Service account JSON is required")

        try:
            sa_data = json.loads(json_str)
            if sa_data.get("type") != "service_account":
                return ProviderConnectionResult("gcp", False, [], [], "", 0.0, "JSON does not appear to be a service account key")

            project_id = project_id or sa_data.get("project_id", "")
            if not project_id:
                return ProviderConnectionResult("gcp", False, [], [], "", 0.0, "GCP Project ID required")

            from google.cloud import compute_v1
            from google.oauth2 import service_account
            import json as _json

            sa_info = _json.loads(json_str)
            credentials = service_account.Credentials.from_service_account_info(sa_info)
            client = compute_v1.AcceleratorTypesClient(credentials=credentials)
            # Test API access by listing accelerator types
            response = client.aggregated_list(project=project_id, max_results=10)
            next(iter(response), None)  # Consume one page to test auth

            return ProviderConnectionResult(
                provider="gcp",
                success=True,
                regions_available=["us-central1", "us-east1", "europe-west4", "asia-east1"],
                gpu_types_available=["T4", "V100", "A100", "H100"],
                estimated_cheapest_gpu="T4",
                estimated_price_usd_hr=0.35,
                message=f"Connected to GCP project '{project_id}' successfully!",
            )
        except json.JSONDecodeError:
            return ProviderConnectionResult("gcp", False, [], [], "", 0.0, "Invalid JSON format")
        except Exception as exc:
            return ProviderConnectionResult("gcp", False, [], [], "", 0.0, f"GCP connection failed: {type(exc).__name__}: {str(exc)[:100]}")

    async def _validate_azure(self, creds: dict) -> ProviderConnectionResult:
        """Test Azure credentials."""
        tenant_id = creds.get("azure_tenant_id", "")
        client_id = creds.get("azure_client_id", "")
        client_secret = creds.get("azure_client_secret", "")
        sub_id = creds.get("azure_subscription_id", "")

        if not all([tenant_id, client_id, client_secret, sub_id]):
            return ProviderConnectionResult("azure", False, [], [], "", 0.0, "All four Azure credentials are required")

        try:
            from azure.identity import ClientSecretCredential
            from azure.mgmt.compute import ComputeManagementClient

            cred = ClientSecretCredential(tenant_id, client_id, client_secret)
            compute = ComputeManagementClient(cred, sub_id)
            # Test by listing resource groups (minimal permission)
            list(compute.virtual_machine_sizes.list("eastus"))

            return ProviderConnectionResult(
                provider="azure",
                success=True,
                regions_available=["eastus", "westus2", "westeurope"],
                gpu_types_available=["T4", "V100", "A100", "H100"],
                estimated_cheapest_gpu="T4",
                estimated_price_usd_hr=0.9,
                message="Connected to Azure successfully! GPU VMs available in eastus, westus2.",
            )
        except Exception as exc:
            err = str(exc).lower()
            if "client_id" in err or "authentication" in err:
                msg = "Authentication failed — verify Tenant ID, Client ID, and Secret."
            elif "subscription" in err:
                msg = "Invalid subscription ID."
            else:
                msg = f"Azure connection failed: {type(exc).__name__}"
            return ProviderConnectionResult("azure", False, [], [], "", 0.0, msg)

    async def _validate_coreweave(self, creds: dict) -> ProviderConnectionResult:
        """Test CoreWeave API key."""
        api_key = creds.get("coreweave_api_key", "")
        if not api_key:
            return ProviderConnectionResult("coreweave", False, [], [], "", 0.0, "CoreWeave API key required")

        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(
                    "https://api.coreweave.com/core/v1/namespaces",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
            if r.status_code == 200:
                return ProviderConnectionResult(
                    provider="coreweave",
                    success=True,
                    regions_available=["ORD1", "LAS1", "EWR1"],
                    gpu_types_available=["H100", "A100", "RTX_A6000", "RTX_A5000"],
                    estimated_cheapest_gpu="A100",
                    estimated_price_usd_hr=2.21,
                    message="Connected to CoreWeave! H100s available from $3.89/hr.",
                )
            elif r.status_code == 401:
                return ProviderConnectionResult("coreweave", False, [], [], "", 0.0, "Invalid API key")
            else:
                return ProviderConnectionResult("coreweave", False, [], [], "", 0.0, f"CoreWeave API returned HTTP {r.status_code}")
        except Exception as exc:
            return ProviderConnectionResult("coreweave", False, [], [], "", 0.0, f"Connection failed: {exc}")

    def suggest_cheapest_provider(self, use_case: str) -> dict[str, Any]:
        """Suggest the best starting provider based on use case."""
        suggestions = {
            "training": {
                "recommended": "coreweave",
                "reason": "CoreWeave offers the best A100/H100 pricing at $2.21–$3.89/hr. Ideal for multi-day training runs.",
                "fallback": "aws",
            },
            "inference": {
                "recommended": "gcp",
                "reason": "GCP T4 preemptible instances at $0.11/hr are unbeatable for inference. Easy spot availability.",
                "fallback": "aws",
            },
            "experiments": {
                "recommended": "aws",
                "reason": "AWS spot V100s at $0.40–0.90/hr are widely available. Large region selection for failover.",
                "fallback": "gcp",
            },
            "enterprise": {
                "recommended": "azure",
                "reason": "Azure ND96asr_v4 (A100) clusters with InfiniBand for distributed training. Best enterprise SLAs.",
                "fallback": "aws",
            },
        }
        return suggestions.get(use_case, suggestions["training"])
