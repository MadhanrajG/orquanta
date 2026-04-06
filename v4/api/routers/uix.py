"""
OrQuanta UIXAgent API Router
Prefix: /api/v1/uix
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..middleware.auth import get_current_user

try:
    from ...agents.uix_agent import get_uix_agent
except ImportError:
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
    from v4.agents.uix_agent import get_uix_agent

router = APIRouter(prefix="/api/v1/uix", tags=["UIXAgent"])


@router.post("/audit", summary="Run full UI/UX audit of all 13 pages")
async def run_audit(user: dict = Depends(get_current_user)):
    """Trigger a full UIXAgent diagnostic audit. Returns scored report with issues and patches."""
    agent = get_uix_agent()
    report = await agent.run_full_audit()

    def _issue(i):
        return {
            "issue_id": i.issue_id, "page": i.page, "route": i.route,
            "category": i.category.value, "severity": i.severity.value,
            "title": i.title, "description": i.description,
            "element_hint": i.element_hint, "auto_fixable": i.auto_fixable,
            "fix_description": i.fix_description, "score_impact": i.score_impact,
        }

    return {
        "report_id": report.report_id,
        "created_at": report.created_at,
        "overall_platform_score": report.overall_platform_score,
        "pages_audited": report.pages_audited,
        "total_issues": report.total_issues,
        "critical_count": report.critical_count,
        "high_count": report.high_count,
        "medium_count": report.medium_count,
        "low_count": report.low_count,
        "auto_fixable_count": report.auto_fixable_count,
        "summary": report.summary,
        "page_scores": [
            {
                "page": ps.page, "route": ps.route,
                "overall_score": ps.overall_score, "grade": ps.grade,
                "scores_by_category": ps.scores_by_category,
                "issue_count": len(ps.issues),
            }
            for ps in report.page_scores
        ],
        "top_issues": [_issue(i) for i in report.top_issues],
    }


@router.get("/report", summary="Get last UIXAgent audit report")
async def get_report(user: dict = Depends(get_current_user)):
    agent = get_uix_agent()
    report = agent.get_last_report()
    if not report:
        return {"status": "no_audit_run", "message": "Run POST /api/v1/uix/audit first."}

    def _issue(i):
        return {
            "issue_id": i.issue_id, "page": i.page, "route": i.route,
            "category": i.category.value, "severity": i.severity.value,
            "title": i.title, "description": i.description,
            "element_hint": i.element_hint, "auto_fixable": i.auto_fixable,
            "fix_description": i.fix_description, "score_impact": i.score_impact,
        }

    return {
        "report_id": report.report_id,
        "created_at": report.created_at,
        "overall_platform_score": report.overall_platform_score,
        "total_issues": report.total_issues,
        "auto_fixable_count": report.auto_fixable_count,
        "summary": report.summary,
        "page_scores": [
            {
                "page": ps.page, "route": ps.route,
                "overall_score": ps.overall_score, "grade": ps.grade,
                "scores_by_category": ps.scores_by_category,
                "issue_count": len(ps.issues),
            }
            for ps in report.page_scores
        ],
        "top_issues": [_issue(i) for i in report.top_issues],
    }


@router.get("/patches", summary="List all generated code patches")
async def list_patches(user: dict = Depends(get_current_user)):
    agent = get_uix_agent()
    patches = agent.get_all_patches()
    return {
        "patches": [
            {
                "patch_id": p.patch_id, "issue_id": p.issue_id,
                "page": p.page, "patch_type": p.patch_type,
                "description": p.description, "auto_approved": p.auto_approved,
                "applied": p.applied, "applied_at": p.applied_at,
            }
            for p in patches
        ],
        "total": len(patches),
    }


@router.post("/patches/{patch_id}/apply", summary="Apply a code patch automatically")
async def apply_patch(patch_id: str, user: dict = Depends(get_current_user)):
    agent = get_uix_agent()
    result = await agent.apply_patch(patch_id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/history", summary="Audit history")
async def audit_history(user: dict = Depends(get_current_user)):
    agent = get_uix_agent()
    return {"history": agent.get_history()}
