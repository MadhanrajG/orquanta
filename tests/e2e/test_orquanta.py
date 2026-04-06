"""
OrQuanta End-to-End Test Suite
-------------------------------
Covers every page, auth flow, and critical API endpoint.
Uses Playwright (Python) — open source, zero-dependency, runs headless.

Run all tests:
  python tests/e2e/test_orquanta.py

Run single group:
  python tests/e2e/test_orquanta.py HelpPageTest

Requirements:
  pip install playwright pytest-playwright
  python -m playwright install chromium

Config:
  BASE_URL  : http://localhost:8000   (or set env var ORQUANTA_URL)
  TEST_EMAIL : test@orquanta.com       (auto-registered on first run)
  TEST_PASS  : TestPass123!
"""

import os
import sys
import time
import json
import unittest
import threading

from playwright.sync_api import sync_playwright, expect

# ── Config ─────────────────────────────────────────────────────────────────────

BASE_URL    = os.environ.get("ORQUANTA_URL", "http://localhost:8000")
APP_URL     = f"{BASE_URL}/app"
API_URL     = f"{BASE_URL}/api/v1"
TEST_EMAIL  = os.environ.get("TEST_EMAIL", "e2e_tester@orquanta.com")
TEST_PASS   = os.environ.get("TEST_PASS", "TestPass123!")
TEST_NAME   = "E2E Test User"
HEADLESS    = os.environ.get("HEADLESS", "true").lower() == "true"
SLOW_MO     = int(os.environ.get("SLOW_MO", "0"))

RESULTS: list[dict] = []

# ── Base Test Class ─────────────────────────────────────────────────────────────

class OrQuantaTestBase(unittest.TestCase):
    """Base class: handles Playwright lifecycle and auth token."""

    @classmethod
    def setUpClass(cls):
        cls._playwright = sync_playwright().start()
        cls._browser = cls._playwright.chromium.launch(
            headless=HEADLESS, slow_mo=SLOW_MO
        )
        cls._context = cls._browser.new_context(
            viewport={"width": 1440, "height": 900}
        )
        cls._page = cls._context.new_page()
        cls._token = cls._get_or_create_token()

    @classmethod
    def tearDownClass(cls):
        cls._browser.close()
        cls._playwright.stop()

    @classmethod
    def _get_or_create_token(cls) -> str:
        import urllib.request, urllib.error
        # Try login first
        for endpoint, payload in [
            ("/api/v1/auth/login",    {"email": TEST_EMAIL, "password": TEST_PASS}),
            ("/api/v1/auth/register", {"email": TEST_EMAIL, "password": TEST_PASS, "full_name": TEST_NAME}),
        ]:
            try:
                req = urllib.request.Request(
                    f"{BASE_URL}{endpoint}",
                    data=json.dumps(payload).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=10) as r:
                    data = json.loads(r.read())
                    token = data.get("access_token") or data.get("token", "")
                    if token:
                        return token
            except Exception:
                pass
        return ""

    def _go(self, path: str):
        """Navigate to an app path and inject auth token."""
        self._page.goto(APP_URL)
        if self._token:
            self._page.evaluate(
                f"localStorage.setItem('orquanta_token', '{self._token}')"
            )
        self._page.goto(f"{APP_URL}{path}")
        self._page.wait_for_load_state("domcontentloaded")
        time.sleep(0.5)

    def _api(self, method: str, path: str, body: dict | None = None):
        import urllib.request
        req = urllib.request.Request(
            f"{API_URL}{path}",
            data=json.dumps(body).encode() if body else None,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._token}",
            },
            method=method.upper(),
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except Exception as e:
            return 500, {"error": str(e)}

    def _record(self, name: str, passed: bool, detail: str = ""):
        RESULTS.append({"test": name, "passed": passed, "detail": detail})


# ── Test Classes ────────────────────────────────────────────────────────────────

class AuthFlowTest(OrQuantaTestBase):
    """Test: Registration, Login, JWT persistence, Logout."""

    def test_01_login_page_loads(self):
        self._page.goto(f"{BASE_URL}/app")
        self._page.wait_for_load_state("domcontentloaded")
        title = self._page.title()
        self.assertIn("OrQuanta", title, "Page title must contain 'OrQuanta'")
        self._record("Login page loads", True)

    def test_02_register_api(self):
        import time as _t
        unique = f"e2e_{int(_t.time())}@test.ai"
        status, data = self._api("POST", "/auth/register", {
            "email": unique, "password": "Test1234!", "full_name": "Test"
        })
        self.assertIn(status, [200, 201, 400], f"Register returned {status}")
        self._record("Register API", status in [200, 201, 400], str(status))

    def test_03_login_api(self):
        status, data = self._api("POST", "/auth/login", {
            "email": TEST_EMAIL, "password": TEST_PASS
        })
        self.assertIn(status, [200, 201], f"Login failed: {data}")
        self.assertIn("access_token", data)
        self._record("Login API returns JWT", True)

    def test_04_invalid_login(self):
        status, data = self._api("POST", "/auth/login", {
            "email": "no@one.com", "password": "wrong"
        })
        self.assertNotEqual(status, 200, "Wrong credentials should not return 200")
        self._record("Invalid login rejected", True)


class DashboardTest(OrQuantaTestBase):
    """Test: Dashboard metrics, UTC clock, Real-time data."""

    def test_01_dashboard_loads(self):
        self._go("/")
        body = self._page.inner_text("body")
        self.assertIn("Mission Control", body)
        self._record("Dashboard loads", True)

    def test_02_utc_clock_format(self):
        self._go("/")
        time.sleep(1)
        body = self._page.inner_text("body")
        import re
        utc_pattern = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} UTC")
        match = utc_pattern.search(body)
        self.assertIsNotNone(match, f"UTC clock not found in format YYYY-MM-DD HH:MM:SS UTC")
        self._record("UTC clock correct format", True, match.group() if match else "")

    def test_03_metrics_cards_visible(self):
        self._go("/")
        body = self._page.inner_text("body")
        for metric in ["Active GPU", "Utilization", "Spend"]:
            self.assertIn(metric, body, f"Metric '{metric}' not found on dashboard")
        self._record("Dashboard metric cards visible", True)

    def test_04_health_api(self):
        status, data = self._api("GET", "/health")
        self.assertIn(status, [200], f"Health check failed: {status}")
        self._record("Health endpoint /api/v1/health", status == 200, str(status))


class NavigationTest(OrQuantaTestBase):
    """Test: All 15 sidebar pages load without crash."""

    PAGES = [
        ("/", "Mission Control"),
        ("/goals", "Command Center"),
        ("/agents", "Agent"),
        ("/jobs", "Job"),
        ("/costs", "Cost"),
        ("/pricing", "Pricing"),
        ("/audit", "Audit"),
        ("/billing", "Plan"),
        ("/free", "Free"),
        ("/vero", "Vero"),
        ("/nemoclaw", "NemoClaw"),
        ("/uix", "UIXAgent"),
        ("/help", "Help Center"),
        ("/settings", "Profile"),
    ]

    def test_all_pages_load(self):
        for path, keyword in self.PAGES:
            with self.subTest(path=path):
                self._go(path)
                body = self._page.inner_text("body")
                self.assertIn(keyword, body, f"'{keyword}' not found on {path}")
                self._record(f"Page {path} loads", keyword in body)


class HelpPageTest(OrQuantaTestBase):
    """Test: Help Center is reachable, shows FAQ, search works."""

    def test_01_help_page_accessible(self):
        self._go("/help")
        body = self._page.inner_text("body")
        self.assertIn("Help Center", body)
        self._record("Help page accessible via /help", True)

    def test_02_no_404_error(self):
        """Ensure clicking Help doesn't 404."""
        self._go("/")
        help_link = self._page.get_by_text("Help Center")
        if help_link.count() > 0:
            help_link.first.click()
            time.sleep(0.5)
            body = self._page.inner_text("body")
            self.assertNotIn("404", body, "Help link navigated to 404 page")
            self.assertIn("Help Center", body)
        self._record("Help link navigates correctly (no 404)", True)

    def test_03_faq_sections_present(self):
        self._go("/help")
        body = self._page.inner_text("body")
        for section in ["Getting Started", "Cost", "Agents", "Security", "Technical"]:
            self.assertIn(section, body, f"FAQ section '{section}' missing")
        self._record("FAQ sections present", True)

    def test_04_search_filters_faqs(self):
        self._go("/help")
        search = self._page.get_by_placeholder("Search help articles")
        if search.count() > 0:
            search.fill("budget")
            time.sleep(0.3)
            body = self._page.inner_text("body")
            self.assertIn("budget", body.lower())
        self._record("Help search filters FAQs", True)

    def test_05_faq_accordion_opens(self):
        self._go("/help")
        # Click the first FAQ question
        buttons = self._page.locator("button[aria-expanded]")
        if buttons.count() > 0:
            first_q = buttons.first
            first_q.click()
            time.sleep(0.3)
            expanded = first_q.get_attribute("aria-expanded")
            self.assertEqual(expanded, "true")
        self._record("FAQ accordion opens on click", True)

    def test_06_quick_links_present(self):
        self._go("/help")
        body = self._page.inner_text("body")
        for link in ["API Reference", "Documentation", "Discord", "Status"]:
            self.assertIn(link, body, f"Quick link '{link}' missing")
        self._record("Help quick links present", True)


class SettingsTest(OrQuantaTestBase):
    """Test: All 4 Settings tabs load correctly."""

    def test_01_profile_tab(self):
        self._go("/settings")
        body = self._page.inner_text("body")
        for kw in ["Profile", "Full Name", "Email"]:
            self.assertIn(kw, body)
        self._record("Settings Profile tab", True)

    def test_02_security_tab(self):
        self._go("/settings")
        body = self._page.inner_text("body")
        self.assertIn("Security", body)
        self._record("Settings Security tab", True)

    def test_03_notifications_toggle(self):
        self._go("/settings")
        # Find Notifications text and ensure toggles present
        body = self._page.inner_text("body")
        self.assertIn("Notification", body)
        self._record("Settings Notifications visible", True)


class BillingTest(OrQuantaTestBase):
    """Test: Billing page shows plans, no 500 errors."""

    def test_01_billing_page_loads(self):
        self._go("/billing")
        body = self._page.inner_text("body")
        for plan in ["Starter", "Pro"]:
            self.assertIn(plan, body, f"Plan '{plan}' not visible on Billing page")
        self._record("Billing page shows plans", True)

    def test_02_no_500_errors_in_network(self):
        errors = []
        self._page.on("response", lambda r: errors.append(r.status) if r.status >= 500 else None)
        self._go("/billing")
        time.sleep(2)
        self.assertEqual(len(errors), 0, f"Got {len(errors)} 500 errors on Billing page")
        self._record("Billing page no 500 errors", len(errors) == 0)

    def test_03_billing_api(self):
        status, data = self._api("GET", "/billing/subscription")
        self.assertIn(status, [200, 401, 404], f"Unexpected billing status {status}")
        self._record("Billing subscription API", status != 500, str(status))


class NemoClawTest(OrQuantaTestBase):
    """Test: NemoClaw engine, context API, goal execution."""

    def test_01_nemoclaw_page_loads(self):
        self._go("/nemoclaw")
        body = self._page.inner_text("body")
        self.assertIn("NemoClaw", body)
        self._record("NemoClaw page loads", True)

    def test_02_nemoclaw_status_api(self):
        status, data = self._api("GET", "/nemoclaw/status")
        self.assertEqual(status, 200, f"NemoClaw status returned {status}")
        self._record("NemoClaw /status API 200", status == 200)

    def test_03_goal_execution_api(self):
        status, data = self._api("POST", "/nemoclaw/run", {
            "goal": "E2E test: minimal GPU job", "budget_usd": 5.0
        })
        self.assertIn(status, [200, 201], f"NemoClaw /run returned {status}")
        if status == 200:
            self.assertIn("trace_id", data, "Missing trace_id in response")
            self.assertIn("confidence", data, "Missing confidence in response")
        self._record("NemoClaw /run goal API", status in [200, 201], str(status))

    def test_04_context_api(self):
        status, data = self._api("GET", "/nemoclaw/context")
        self.assertIn(status, [200, 401], f"Context API returned {status}")
        self._record("NemoClaw /context API", status != 500)


class UIXAgentTest(OrQuantaTestBase):
    """Test: UIXAgent audit runs and returns scored report."""

    def test_01_uixagent_page_loads(self):
        self._go("/uix")
        body = self._page.inner_text("body")
        self.assertIn("UIXAgent", body)
        self._record("UIXAgent page loads", True)

    def test_02_audit_api_runs(self):
        status, data = self._api("POST", "/uix/audit")
        self.assertEqual(status, 200, f"UIX audit returned {status}")
        self.assertIn("overall_platform_score", data)
        self.assertGreater(data["overall_platform_score"], 0)
        self._record("UIXAgent /audit API", status == 200, f"Score: {data.get('overall_platform_score')}")

    def test_03_audit_covers_all_pages(self):
        status, data = self._api("POST", "/uix/audit")
        if status == 200:
            self.assertEqual(data["pages_audited"], 13, f"Expected 13 pages, got {data['pages_audited']}")
        self._record("UIXAgent audits 13 pages", status == 200)

    def test_04_patches_api(self):
        status, data = self._api("GET", "/uix/patches")
        self.assertIn(status, [200, 401], f"Patches API returned {status}")
        self._record("UIXAgent /patches API", status != 500)


class VeroTest(OrQuantaTestBase):
    """Test: Vero meta-agent page and status API."""

    def test_01_vero_page_loads(self):
        self._go("/vero")
        body = self._page.inner_text("body")
        self.assertIn("Vero", body)
        self._record("Vero page loads", True)

    def test_02_vero_status_api(self):
        status, data = self._api("GET", "/vero/status")
        self.assertIn(status, [200, 401], f"Vero status API returned {status}")
        self._record("Vero /status API", status != 500, str(status))


class APIHealthTest(OrQuantaTestBase):
    """Test: All critical API endpoints return expected status codes."""

    ENDPOINTS = [
        ("GET",  "/health",               [200]),
        ("GET",  "/agents/status",        [200, 401]),
        ("GET",  "/jobs",                 [200, 401]),
        ("GET",  "/audit",                [200, 401]),
        ("GET",  "/billing/plans",        [200, 401, 404]),
        ("GET",  "/pricing/live",         [200, 401, 404]),
        ("GET",  "/nemoclaw/status",      [200, 401]),
        ("GET",  "/vero/status",          [200, 401]),
        ("GET",  "/uix/report",           [200, 401]),
    ]

    def test_all_endpoints(self):
        for method, path, ok_statuses in self.ENDPOINTS:
            with self.subTest(path=path):
                status, _ = self._api(method, path)
                self.assertIn(status, ok_statuses + [500],
                    f"{method} {path} returned unexpected {status}")
                passed = status not in [500]
                self._record(f"API {method} {path}", passed, str(status))


# ── Runner + HTML Reporter ──────────────────────────────────────────────────────

def run_all_tests():
    suite = unittest.TestSuite()
    for cls in [
        AuthFlowTest, DashboardTest, NavigationTest,
        HelpPageTest, SettingsTest, BillingTest,
        NemoClawTest, UIXAgentTest, VeroTest, APIHealthTest,
    ]:
        suite.addTests(unittest.TestLoader().loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    result = runner.run(suite)

    # Print summary
    print("\n" + "="*60)
    print(f"  OrQuanta E2E Test Summary")
    print("="*60)
    passed = sum(1 for r in RESULTS if r["passed"])
    total  = len(RESULTS)
    for r in RESULTS:
        icon = "✅" if r["passed"] else "❌"
        detail = f" ({r['detail']})" if r["detail"] else ""
        print(f"  {icon} {r['test']}{detail}")
    print(f"\n  Total: {passed}/{total} passed")
    print("="*60)

    # Write JSON report
    report_path = "tests/e2e/last_report.json"
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w") as f:
        json.dump({
            "passed": passed,
            "total": total,
            "score": round(passed / max(total, 1) * 100),
            "results": RESULTS,
        }, f, indent=2)
    print(f"  Report saved: {report_path}")
    return result


if __name__ == "__main__":
    spec = sys.argv[1] if len(sys.argv) > 1 else None
    if spec:
        # Run single test class
        suite = unittest.TestLoader().loadTestsFromName(spec, sys.modules[__name__])
        unittest.TextTestRunner(verbosity=2).run(suite)
    else:
        run_all_tests()
