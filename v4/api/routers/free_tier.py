"""
OrQuanta  -  Free GPU Tier API Router
=====================================
Exposes endpoints for the $0 GPU tier:

  POST /api/v1/free/notebook
    Generate a Colab-ready .ipynb from a goal
    Returns: { notebook_json, download_url, colab_url, kaggle_url }

  POST /api/v1/free/kaggle/submit
    Submit a job directly to Kaggle Kernels (user provides API creds)
    Returns: { kernel_ref, dashboard_url, status }

  GET  /api/v1/free/kaggle/status/{kernel_ref}
    Poll status of a Kaggle kernel

  GET  /api/v1/free/options
    Returns all available free GPU options and their current status

  GET  /api/v1/free/notebook/download/{job_id}
    Download a previously generated notebook as .ipynb file
"""
from __future__ import annotations

import base64
import json
import logging
import secrets
import urllib.parse
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger("orquanta.free_tier")

router = APIRouter(prefix="/api/v1/free", tags=["free-gpu"])

# In-memory store for generated notebooks (replace with DB/S3 in production)
_notebooks: dict[str, dict] = {}   # job_id -> { notebook_json, goal, created_at }


# --- Schemas ------------------------------------------------------------------

class NotebookRequest(BaseModel):
    goal: str
    model_id: str | None = None
    task_type: str | None = None   # auto-detect if None


class KaggleSubmitRequest(BaseModel):
    goal: str
    kaggle_username: str
    kaggle_api_key: str
    model_id: str | None = None


# --- Auth (reuse pattern from other routers) ----------------------------------

def _current_user(request: Request) -> dict:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return {"user_id": "demo", "email": "demo@orquanta.com"}
    # Free tier allows unauthenticated notebook generation
    return {"user_id": "anon", "email": ""}


CurrentUser = Annotated[dict, Depends(_current_user)]


# --- Routes -------------------------------------------------------------------

@router.get("/options")
async def get_free_options():
    """Returns all available $0 GPU options and their specs."""
    return {
        "free_options": [
            {
                "id":            "colab",
                "name":          "Google Colab",
                "icon":          "colab",
                "gpu":           "T4 16GB (free)  -  A100/H100 (paid)",
                "free_hours":    "~12 hrs/day (session limit)",
                "weekly_hours":  None,
                "cost":          "$0.00",
                "programmable":  False,
                "method":        "notebook",
                "description":   "OrQuanta generates a complete notebook. Click to open in Colab and run with 1 click.",
                "cta":           "Generate Colab Notebook",
                "setup_minutes": 1,
                "signup_url":    "https://colab.research.google.com",
            },
            {
                "id":            "kaggle",
                "name":          "Kaggle Kernels",
                "icon":          "kaggle",
                "gpu":           "T4 16GB or P100 16GB",
                "free_hours":    "Up to 9 hrs per session",
                "weekly_hours":  30,
                "cost":          "$0.00",
                "programmable":  True,
                "method":        "api",
                "description":   "OrQuanta submits and monitors your job on Kaggle's free GPU automatically.",
                "cta":           "Run on Kaggle (Auto)",
                "setup_minutes": 5,
                "signup_url":    "https://www.kaggle.com",
                "api_token_url": "https://www.kaggle.com/settings/account",
            },
            {
                "id":            "lambda",
                "name":          "Lambda Labs",
                "icon":          "lambda",
                "gpu":           "A10 24GB / A100 40GB",
                "free_hours":    "$10 free credits on signup",
                "weekly_hours":  None,
                "cost":          "$0 until credits exhausted",
                "programmable":  True,
                "method":        "api",
                "description":   "New users get $10 free GPU credits. OrQuanta auto-routes your jobs.",
                "cta":           "Get $10 Free Credits",
                "setup_minutes": 3,
                "signup_url":    "https://cloud.lambdalabs.com/sign-up",
                "referral_note": "Create account -> API Keys -> paste into OrQuanta",
            },
        ],
        "recommendation": "Start with Colab notebook (zero setup). Upgrade to Kaggle for automation.",
        "total_free_compute": "~42 GPU-hours/week available per user",
    }


@router.post("/notebook")
async def generate_notebook(body: NotebookRequest, user: CurrentUser):
    """
    Generate a complete, ready-to-run Colab notebook from a plain-English goal.
    Returns the notebook JSON + a download link + a direct Colab open URL.
    """
    if not body.goal or len(body.goal.strip()) < 5:
        raise HTTPException(status_code=422, detail="Goal must be at least 5 characters")

    from v4.providers.colab_generator import get_colab_generator
    gen      = get_colab_generator()
    notebook = gen.generate(goal=body.goal.strip(), model_id=body.model_id)
    nb_dict  = notebook.to_dict()
    nb_json  = notebook.to_json()

    # Store for download
    job_id = f"nb-{secrets.token_hex(8)}"
    _notebooks[job_id] = {
        "notebook_json": nb_json,
        "goal":          body.goal,
        "task_type":     notebook.task_type,
        "model_id":      notebook.model_id,
        "created_at":    datetime.now(timezone.utc).isoformat(),
        "filename":      notebook.get_download_filename(),
    }

    # Build Colab URL: encode the notebook as base64 for the Colab create endpoint
    nb_b64   = base64.b64encode(nb_json.encode()).decode()
    # Colab gist approach (most reliable): we offer the download + instruction
    colab_url = f"https://colab.research.google.com/github/googlecolab/colabtools/blob/main/notebooks/README.ipynb"

    logger.info(f"[FreeTier] Notebook generated: {job_id} | task={notebook.task_type} | user={user['user_id']}")

    return {
        "job_id":        job_id,
        "task_type":     notebook.task_type,
        "model_id":      notebook.model_id,
        "filename":      notebook.get_download_filename(),
        "download_url":  f"/api/v1/free/notebook/download/{job_id}",
        "cell_count":    len(nb_dict["cells"]),
        "instructions": [
            "1. Click 'Download Notebook' below",
            "2. Go to colab.research.google.com",
            "3. File -> Upload notebook -> select the downloaded .ipynb",
            "4. Runtime -> Change runtime type -> GPU (T4)",
            "5. Runtime -> Run all    Your free GPU job starts!",
        ],
        "kaggle_instructions": [
            "1. Click 'Download Notebook'",
            "2. Go to kaggle.com/code -> New Notebook",
            "3. File -> Import Notebook -> upload the .ipynb",
            "4. Click 'Run All'  -  Free T4 GPU (30hrs/week)",
        ],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "cost_usd":   0.0,
        "gpu_type":   "T4 16GB (Colab/Kaggle free tier)",
    }


@router.get("/notebook/download/{job_id}")
async def download_notebook(job_id: str):
    """Download a generated notebook as a .ipynb file."""
    record = _notebooks.get(job_id)
    if not record:
        raise HTTPException(status_code=404, detail="Notebook not found or expired")

    nb_bytes = record["notebook_json"].encode("utf-8")
    filename = record["filename"]

    return Response(
        content=nb_bytes,
        media_type="application/x-ipynb+json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/kaggle/submit")
async def kaggle_submit(body: KaggleSubmitRequest, user: CurrentUser):
    """
    Submit a job directly to Kaggle Kernels using user's API credentials.
    OrQuanta generates the notebook + submits + returns status URL.
    """
    from v4.providers.colab_generator import get_colab_generator
    from v4.providers.kaggle_provider import get_kaggle_provider

    # Verify credentials first
    provider = get_kaggle_provider(body.kaggle_username, body.kaggle_api_key)
    valid = await provider.check_credentials()
    if not valid:
        raise HTTPException(
            status_code=401,
            detail="Invalid Kaggle credentials. Get your API token at kaggle.com/settings/account"
        )

    # Generate notebook
    gen      = get_colab_generator()
    notebook = gen.generate(goal=body.goal, model_id=body.model_id)

    # Submit to Kaggle
    result = await provider.submit_job(
        goal=body.goal,
        notebook_ipynb=notebook.to_dict(),
    )

    logger.info(f"[FreeTier/Kaggle] Submitted {result['kernel_ref']} for {body.kaggle_username}")

    return {
        **result,
        "message":    "Job submitted to Kaggle free GPU. Monitor at the dashboard_url.",
        "poll_url":   f"/api/v1/free/kaggle/status/{result['kernel_ref'].replace('/', '__')}",
        "cost_usd":   0.0,
    }


@router.get("/kaggle/status/{kernel_ref_encoded}")
async def kaggle_status(kernel_ref_encoded: str, kaggle_username: str, kaggle_api_key: str):
    """Poll the status of a running Kaggle kernel."""
    from v4.providers.kaggle_provider import get_kaggle_provider

    kernel_ref = kernel_ref_encoded.replace("__", "/")
    provider   = get_kaggle_provider(kaggle_username, kaggle_api_key)
    status     = await provider.get_status(kernel_ref)
    return status
