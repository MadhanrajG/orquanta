"""
OrQuanta Agentic v1.0 — Email Templates

Beautiful HTML emails for all customer communications:
  - Welcome (with first job tutorial)
  - Job completed (with results summary)
  - Cost alert (budget threshold reached)
  - Weekly usage report
  - Invoice (itemized GPU usage)
  - Trial ending in 3 days
  - Payment failed (with retry link)

All templates:
  - Responsive mobile layout
  - Dark-themed, OrQuanta branded
  - Plain-text fallback included
  - CAN-SPAM compliant (unsubscribe link)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


BRAND_COLOR = "#6366f1"
BRAND_ACCENT = "#06b6d4"
BG_COLOR = "#0f1117"
SURFACE_COLOR = "#161822"
APP_URL = os.getenv("APP_URL", "https://app.orquanta.ai")
UNSUBSCRIBE_BASE = os.getenv("UNSUBSCRIBE_URL", f"{APP_URL}/unsubscribe")


BASE_STYLE = f"""
  body {{ margin:0; padding:0; background:{BG_COLOR}; font-family: 'Inter', -apple-system, BlinkMacSystemFont, Arial, sans-serif; color:#f1f5f9; }}
  .wrapper {{ max-width:600px; margin:0 auto; background:{SURFACE_COLOR}; border-radius:16px; overflow:hidden; border:1px solid rgba(255,255,255,0.08); }}
  .header {{ background:linear-gradient(135deg,{BRAND_COLOR},{BRAND_ACCENT}); padding:32px 40px; }}
  .logo {{ font-size:24px; font-weight:800; color:white; letter-spacing:-0.5px; text-decoration:none; }}
  .badge {{ background:rgba(255,255,255,0.2); border-radius:6px; padding:2px 8px; font-size:12px; font-weight:700; letter-spacing:1px; color:white; margin-left:8px; }}
  .body {{ padding:40px; }}
  h1 {{ font-size:28px; font-weight:800; margin:0 0 16px; color:#f1f5f9; letter-spacing:-0.5px; }}
  h2 {{ font-size:20px; font-weight:700; margin:24px 0 12px; color:#f1f5f9; }}
  p {{ font-size:16px; line-height:1.7; color:#94a3b8; margin:0 0 16px; }}
  .btn {{ display:inline-block; padding:14px 28px; border-radius:10px; background:linear-gradient(135deg,{BRAND_COLOR},#4f46e5); color:white; font-weight:700; font-size:15px; text-decoration:none; margin:8px 0; }}
  .card {{ background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.08); border-radius:12px; padding:20px 24px; margin:16px 0; }}
  .metric {{ display:inline-block; text-align:center; min-width:120px; }}
  .metric-value {{ font-size:32px; font-weight:800; color:#f1f5f9; }}
  .metric-label {{ font-size:13px; color:#475569; margin-top:4px; }}
  .green {{ color:#10b981; }}
  .amber {{ color:#f59e0b; }}
  .red {{ color:#ef4444; }}
  .cyan {{ color:{BRAND_ACCENT}; }}
  table {{ width:100%; border-collapse:collapse; }}
  th {{ text-align:left; font-size:11px; font-weight:700; letter-spacing:1.5px; text-transform:uppercase; color:#475569; padding:10px 0; border-bottom:1px solid rgba(255,255,255,0.06); }}
  td {{ padding:12px 0; font-size:14px; color:#94a3b8; border-bottom:1px solid rgba(255,255,255,0.04); }}
  .footer {{ padding:24px 40px; border-top:1px solid rgba(255,255,255,0.06); text-align:center; }}
  .footer p {{ font-size:12px; color:#334155; margin:4px 0; }}
  .footer a {{ color:#475569; text-decoration:none; }}
"""

def _base_html(content: str, unsubscribe_url: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700;800&display=swap" rel="stylesheet" />
  <style>{BASE_STYLE}</style>
</head>
<body>
  <div style="padding:24px 0; background:{BG_COLOR};">
    <div class="wrapper">
      <div class="header">
        <a href="{APP_URL}" class="logo">⚡ OrQuanta <span class="badge">v4.0</span></a>
      </div>
      <div class="body">{content}</div>
      <div class="footer">
        <p>You received this email because you signed up for OrQuanta Agentic.</p>
        <p><a href="{unsubscribe_url or UNSUBSCRIBE_BASE}">Unsubscribe</a> &bull; <a href="{APP_URL}/privacy">Privacy Policy</a> &bull; <a href="{APP_URL}/terms">Terms</a></p>
        <p>OrQuanta Agentic Inc. &bull; AI GPU Cloud Management</p>
      </div>
    </div>
  </div>
</body>
</html>"""


@dataclass
class Email:
    to: str
    subject: str
    html: str
    text: str    # Plain-text fallback


class EmailTemplates:
    """All OrQuanta email templates."""

    @staticmethod
    def welcome(
        name: str,
        email: str,
        plan: str,
        trial_ends: str,
        verification_url: str,
    ) -> Email:
        plan_display = plan.title()
        content = f"""
<h1>Welcome to OrQuanta, {name.split()[0]}! 🚀</h1>
<p>You're on the <strong style="color:{BRAND_COLOR}">{plan_display}</strong> plan with a <strong>14-day free trial</strong> ending on <strong style="color:#f1f5f9">{trial_ends}</strong>. No charges until then.</p>

<div class="card">
  <h2 style="margin-top:0">✉️ First: Verify Your Email</h2>
  <p style="margin-bottom:20px">Click the button below to activate your account and access the dashboard.</p>
  <a href="{verification_url}" class="btn">Verify My Email</a>
</div>

<h2>🎯 Your 3-Step Quick Start</h2>
<div class="card">
  <p><strong style="color:#f1f5f9">Step 1 — Connect a Provider (5 min)</strong><br>Link AWS, GCP, Azure, or CoreWeave. Our wizard guides you through creating the right permissions.</p>
  <p><strong style="color:#f1f5f9">Step 2 — Submit Your First Goal (1 min)</strong><br>Type a natural language description of your ML task. Agents handle everything else.</p>
  <p><strong style="color:#f1f5f9">Step 3 — Watch Agents Work</strong><br>See real-time cost comparison, GPU provisioning, and job execution in the dashboard.</p>
</div>

<a href="{APP_URL}/onboarding" class="btn">Start Onboarding →</a>

<p style="margin-top:24px">Questions? Reply to this email — we personally respond within 24 hours.</p>
"""
        text = f"""Welcome to OrQuanta, {name}!

You're on the {plan_display} plan with a 14-day free trial ending {trial_ends}.

Step 1: Verify your email: {verification_url}
Step 2: Connect a cloud provider
Step 3: Submit your first ML goal

Get started: {APP_URL}/onboarding
"""
        return Email(to=email, subject=f"Welcome to OrQuanta — your 14-day trial has started 🚀", html=_base_html(content), text=text)

    @staticmethod
    def job_completed(
        to: str,
        name: str,
        job_id: str,
        goal_summary: str,
        gpu_type: str,
        provider: str,
        duration_min: float,
        cost_usd: float,
        saved_usd: float,
        artifacts_url: str,
    ) -> Email:
        content = f"""
<h1>✅ Job Complete!</h1>
<p>Your GPU job finished successfully. Here's your summary:</p>

<div class="card">
  <p style="font-size:14px;color:#475569;margin:0 0 8px">Goal</p>
  <p style="color:#f1f5f9;margin:0"><strong>{goal_summary}</strong></p>
</div>

<div style="display:flex; gap:32px; margin:24px 0;">
  <div class="metric">
    <div class="metric-value green">${cost_usd:.2f}</div>
    <div class="metric-label">Total Cost</div>
  </div>
  <div class="metric">
    <div class="metric-value cyan">${saved_usd:.2f}</div>
    <div class="metric-label">Saved vs On-Demand</div>
  </div>
  <div class="metric">
    <div class="metric-value">{duration_min:.0f}m</div>
    <div class="metric-label">Duration</div>
  </div>
</div>

<table>
  <tr><th>Field</th><th>Value</th></tr>
  <tr><td>GPU Type</td><td style="color:#f1f5f9">{gpu_type}</td></tr>
  <tr><td>Provider</td><td style="color:#f1f5f9">{provider.upper()}</td></tr>
  <tr><td>Job ID</td><td style="font-family:monospace;color:#6366f1">{job_id}</td></tr>
</table>

<a href="{artifacts_url}" class="btn" style="margin-top:24px">Download Artifacts →</a>
"""
        text = f"""Job Complete!

Goal: {goal_summary}
Cost: ${cost_usd:.2f} (saved ${saved_usd:.2f} vs on-demand)
Duration: {duration_min:.0f} minutes
GPU: {gpu_type} on {provider}

Download artifacts: {artifacts_url}
"""
        return Email(
            to=to, subject=f"✅ Job complete — ${cost_usd:.2f} (saved ${saved_usd:.2f})",
            html=_base_html(content), text=text,
        )

    @staticmethod
    def cost_alert(
        to: str,
        name: str,
        daily_budget_usd: float,
        spent_usd: float,
        threshold_pct: float,
        reset_time: str,
    ) -> Email:
        pct = int((spent_usd / daily_budget_usd) * 100)
        content = f"""
<h1>⚠️ Budget Alert</h1>
<p>You've reached <strong style="color:#f59e0b">{pct}%</strong> of your daily budget limit.</p>

<div class="card">
  <div style="display:flex; justify-content:space-between; align-items:center;">
    <div>
      <p style="margin:0;color:#475569;font-size:13px">Spent Today</p>
      <div class="metric-value amber">${spent_usd:.2f}</div>
    </div>
    <div>
      <p style="margin:0;color:#475569;font-size:13px">Daily Limit</p>
      <div class="metric-value">${daily_budget_usd:.2f}</div>
    </div>
    <div>
      <p style="margin:0;color:#475569;font-size:13px">Resets At</p>
      <div style="font-size:16px;font-weight:700;color:#f1f5f9">{reset_time}</div>
    </div>
  </div>
  <div style="background:rgba(245,158,11,0.1);border-radius:8px;height:8px;margin-top:16px;">
    <div style="background:#f59e0b;height:8px;border-radius:8px;width:{min(pct,100)}%"></div>
  </div>
</div>

<p>If you need more capacity today, increase your budget limit or pause running jobs.</p>
<a href="{APP_URL}/settings/safety" class="btn">Adjust Budget Limits →</a>
<a href="{APP_URL}/jobs" class="btn" style="background:rgba(255,255,255,0.08);margin-left:12px">View Running Jobs</a>
"""
        text = f"""Budget Alert — {pct}% Used

You've spent ${spent_usd:.2f} of your ${daily_budget_usd:.2f} daily budget.
Budget resets at: {reset_time}

Adjust limits: {APP_URL}/settings/safety
"""
        return Email(
            to=to, subject=f"⚠️ Budget alert — {pct}% of ${daily_budget_usd:.0f}/day limit reached",
            html=_base_html(content), text=text,
        )

    @staticmethod
    def weekly_report(
        to: str,
        name: str,
        week_of: str,
        jobs_run: int,
        gpu_hours: float,
        total_spend_usd: float,
        saved_usd: float,
        top_gpu_type: str,
        top_provider: str,
        cost_trend: str,  # "↑ +12%" or "↓ -8%"
        recommendations: list[str],
    ) -> Email:
        recs_html = "".join(f"<li style='margin-bottom:8px;color:#94a3b8'>{r}</li>" for r in recommendations[:3])
        content = f"""
<h1>📊 Weekly Report — {week_of}</h1>
<p>Here's how your GPU workloads performed this week, {name.split()[0]}.</p>

<div style="display:flex; gap:24px; flex-wrap:wrap; margin:24px 0;">
  <div class="metric">
    <div class="metric-value">{jobs_run}</div>
    <div class="metric-label">Jobs Completed</div>
  </div>
  <div class="metric">
    <div class="metric-value">{gpu_hours:.1f}h</div>
    <div class="metric-label">GPU Hours</div>
  </div>
  <div class="metric">
    <div class="metric-value">${total_spend_usd:.0f}</div>
    <div class="metric-label">Total Spend</div>
  </div>
  <div class="metric">
    <div class="metric-value green">${saved_usd:.0f}</div>
    <div class="metric-label">Saved vs On-Demand</div>
  </div>
</div>

<table>
  <tr><th>Metric</th><th>Value</th></tr>
  <tr><td>Most Used GPU</td><td style="color:#f1f5f9">{top_gpu_type}</td></tr>
  <tr><td>Top Provider</td><td style="color:#f1f5f9">{top_provider.upper()}</td></tr>
  <tr><td>Spend Trend</td><td style="color:#f59e0b">{cost_trend}</td></tr>
  <tr><td>Avg Cost per Job</td><td style="color:#f1f5f9">${total_spend_usd/max(jobs_run,1):.2f}</td></tr>
  <tr><td>Savings Rate</td><td class="green">{saved_usd/(total_spend_usd+saved_usd)*100:.0f}%</td></tr>
</table>

<h2>💡 OrQuanta Recommendations</h2>
<ul style="padding-left:20px">{recs_html}</ul>

<a href="{APP_URL}/analytics" class="btn">View Full Analytics →</a>
"""
        text = f"""Weekly Report — {week_of}

Jobs Completed: {jobs_run}
GPU Hours: {gpu_hours:.1f}h
Total Spend: ${total_spend_usd:.2f}
Saved vs On-Demand: ${saved_usd:.2f}
Top GPU: {top_gpu_type} on {top_provider}

View analytics: {APP_URL}/analytics
"""
        return Email(
            to=to, subject=f"📊 Your week: {jobs_run} jobs, ${total_spend_usd:.0f} spent, ${saved_usd:.0f} saved",
            html=_base_html(content), text=text,
        )

    @staticmethod
    def trial_ending(
        to: str,
        name: str,
        days_left: int,
        plan: str,
        price_usd_mo: int,
        upgrade_url: str,
    ) -> Email:
        urgency_color = "#ef4444" if days_left <= 1 else "#f59e0b"
        content = f"""
<h1 style="color:{urgency_color}">⏰ Your trial ends in {days_left} day{"s" if days_left != 1 else ""}!</h1>
<p>Your 14-day free trial of OrQuanta {plan.title()} ends soon. Add a payment method to keep your agents running.</p>

<div class="card">
  <p style="margin:0;color:#475569;font-size:13px">Current Plan</p>
  <p style="font-size:24px;font-weight:800;margin:4px 0;color:#f1f5f9">{plan.title()} — ${price_usd_mo}/month</p>
  <p style="margin:0;color:#94a3b8">Billed monthly. Cancel anytime.</p>
</div>

<p>Don't lose access to:</p>
<ul style="color:#94a3b8;line-height:2">
  <li>Active AI agents monitoring your cloud costs</li>
  <li>Automatic spot instance failover</li>
  <li>Real-time GPU telemetry and alerts</li>
  <li>Complete audit trail of all decisions</li>
</ul>

<a href="{upgrade_url}" class="btn">Add Payment Method →</a>
"""
        text = f"""Your OrQuanta trial ends in {days_left} day(s).

Plan: {plan.title()} — ${price_usd_mo}/month
Add payment method to continue: {upgrade_url}
"""
        return Email(
            to=to,
            subject=f"⏰ Your OrQuanta trial ends in {days_left} day{'s' if days_left != 1 else ''} — add payment to continue",
            html=_base_html(content), text=text,
        )

    @staticmethod
    def payment_failed(
        to: str,
        name: str,
        amount_usd: float,
        retry_url: str,
        retry_date: str,
    ) -> Email:
        content = f"""
<h1 style="color:#ef4444">❌ Payment Failed</h1>
<p>We couldn't process your payment of <strong style="color:#f1f5f9">${amount_usd:.2f}</strong> for OrQuanta.</p>

<div class="card" style="border-color:rgba(239,68,68,0.3);background:rgba(239,68,68,0.05)">
  <p>Your account remains active for now, but running jobs will pause if payment isn't resolved within 72 hours.</p>
  <p>We'll automatically retry on <strong style="color:#f1f5f9">{retry_date}</strong>.</p>
</div>

<p><strong>Common reasons for payment failure:</strong></p>
<ul style="color:#94a3b8;line-height:2">
  <li>Expired credit card</li>
  <li>Insufficient funds</li>
  <li>Card issuer blocked the transaction</li>
</ul>

<a href="{retry_url}" class="btn" style="background:linear-gradient(135deg,#ef4444,#dc2626)">Update Payment Method →</a>
"""
        text = f"""Payment Failed — ${amount_usd:.2f}

Update payment method: {retry_url}
We'll retry on: {retry_date}
"""
        return Email(
            to=to, subject=f"⚠️ Action required: payment of ${amount_usd:.2f} failed",
            html=_base_html(content), text=text,
        )

    @staticmethod
    def invoice(
        to: str,
        org_name: str,
        invoice_id: str,
        period: str,
        line_items: list[dict[str, Any]],
        subtotal_usd: float,
        tax_usd: float,
        total_usd: float,
        invoice_url: str,
    ) -> Email:
        rows = "".join(
            f"<tr><td>{item['description']}</td><td>{item.get('hours', '')}h</td><td>${item['amount_usd']:.2f}</td></tr>"
            for item in line_items
        )
        content = f"""
<h1>📄 Invoice #{invoice_id}</h1>
<p>Thank you for using OrQuanta! Here's your invoice for <strong style="color:#f1f5f9">{period}</strong>.</p>

<div class="card">
  <p style="margin:0;color:#475569;font-size:13px">Billed To</p>
  <p style="font-size:18px;font-weight:700;color:#f1f5f9;margin:4px 0">{org_name}</p>
</div>

<table style="margin-top:24px">
  <thead><tr><th>Description</th><th>Hours</th><th>Amount</th></tr></thead>
  <tbody>{rows}</tbody>
</table>

<div class="card" style="margin-top:16px">
  <table>
    <tr><td style="color:#475569">Subtotal</td><td style="text-align:right;color:#f1f5f9">${subtotal_usd:.2f}</td></tr>
    <tr><td style="color:#475569">Tax</td><td style="text-align:right;color:#f1f5f9">${tax_usd:.2f}</td></tr>
    <tr><td style="font-weight:700;font-size:18px;color:#f1f5f9">Total</td><td style="text-align:right;font-weight:800;font-size:18px;color:#f1f5f9">${total_usd:.2f}</td></tr>
  </table>
</div>

<a href="{invoice_url}" class="btn" style="margin-top:24px">Download PDF Invoice →</a>
"""
        text = f"""Invoice #{invoice_id} — {period}

Total: ${total_usd:.2f}
Download: {invoice_url}
"""
        return Email(
            to=to, subject=f"Invoice #{invoice_id} — ${total_usd:.2f} for {period}",
            html=_base_html(content), text=text,
        )
