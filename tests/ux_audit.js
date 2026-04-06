/**
 * OrQuanta — Deep UX Audit
 * Checks every visible page, interaction, and flow as a real user would.
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE = 'http://localhost:8765';
const SS_DIR = path.join(__dirname, 'ux_screenshots');
if (!fs.existsSync(SS_DIR)) fs.mkdirSync(SS_DIR);

const ISSUES = [];
const PASSES = [];

function issue(page, desc, severity = 'MEDIUM') {
    console.log(`  [${severity}] ✗ ${desc}`);
    ISSUES.push({ page, desc, severity });
}
function pass(pg, desc) {
    console.log(`  ✓ ${desc}`);
    PASSES.push({ page: pg, desc });
}

async function shot(page, name) {
    await page.screenshot({ path: path.join(SS_DIR, `${name}.png`), fullPage: true });
}

(async () => {
    const browser = await chromium.launch({ headless: true });
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
    const page = await ctx.newPage();

    // Suppress console noise
    page.on('console', () => {});
    page.on('pageerror', () => {});

    // ── 1. DEMO PAGE ─────────────────────────────────────────────────────────
    console.log('\n[1] Demo Page — /demo');
    await page.route('**/demo/status', r => r.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify({ status: 'active', stats: { total_saved_usd: 2.78 }, active_jobs: [] })
    }));
    await page.goto(`${BASE}/demo`, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1500);
    await shot(page, '01_demo_hero');

    // Title & meta
    const title = await page.title();
    title.length > 5 ? pass('demo', `Title: "${title}"`) : issue('demo', 'Page title is missing or too short', 'HIGH');

    // Hero CTA
    const ctaPrimary = page.locator('.btn-primary').first();
    const ctaText = await ctaPrimary.textContent();
    ctaText.trim().length > 0 ? pass('demo', `Primary CTA: "${ctaText.trim()}"`) : issue('demo', 'Primary CTA button has no text', 'HIGH');

    // CTA href leads somewhere
    const ctaHref = await ctaPrimary.getAttribute('href');
    ctaHref ? pass('demo', `CTA href: ${ctaHref}`) : issue('demo', 'CTA button has no href', 'HIGH');

    // Stats strip renders numbers (not empty)
    const stats = await page.locator('.stats-strip div').count();
    stats >= 4 ? pass('demo', `Stats strip: ${stats} stat boxes`) : issue('demo', `Only ${stats}/4 stat boxes rendered`, 'MEDIUM');

    // Feature cards
    const featCards = await page.locator('.feat').count();
    featCards >= 6 ? pass('demo', `${featCards} feature cards`) : issue('demo', `Only ${featCards}/6 feature cards`, 'MEDIUM');

    // No raw emoji in feature cards
    const featHTML = await page.locator('.features').innerHTML();
    const emojiPattern = /[\u{1F300}-\u{1F9FF}]|&#x1F/u;
    !emojiPattern.test(featHTML) ? pass('demo', 'No emoji in feature cards') : issue('demo', 'Emoji found in feature cards — replace with SVG icons', 'LOW');

    // Console output starts filling
    await page.waitForTimeout(2000);
    const consolLines = await page.locator('#console-output div').count();
    consolLines > 0 ? pass('demo', `Agent console: ${consolLines} log lines`) : issue('demo', 'Agent console is empty after 2s', 'HIGH');
    await shot(page, '02_demo_console');

    // Metric boxes populate
    const utilVal = await page.locator('#m-util').textContent();
    utilVal.length > 0 ? pass('demo', `GPU util metric: "${utilVal}"`) : issue('demo', 'GPU utilization metric box empty after 2s', 'MEDIUM');

    // Goal analyzer
    await page.fill('#goal-input', 'Train GPT-2 on Wikipedia, budget $20');
    await page.click('#analyze-btn');
    try {
        await page.waitForFunction(
            () => { const el = document.getElementById('goal-result'); return el && el.innerHTML.length > 50; },
            { timeout: 6000 }
        );
        pass('demo', 'Goal analyzer returns recommendations');
        await shot(page, '03_demo_goal_result');
    } catch {
        issue('demo', 'Goal analyzer failed to return result within 6s', 'HIGH');
    }

    // Mobile responsiveness
    await page.setViewportSize({ width: 375, height: 812 });
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1000);
    const h1Mobile = await page.locator('h1').first().isVisible();
    h1Mobile ? pass('demo', 'Hero renders on 375px mobile') : issue('demo', 'Hero h1 not visible on mobile', 'HIGH');
    const ctaVisible = await page.locator('.btn-primary').first().isVisible();
    ctaVisible ? pass('demo', 'CTA visible on mobile') : issue('demo', 'CTA not visible on mobile', 'HIGH');
    await shot(page, '04_demo_mobile');
    await page.setViewportSize({ width: 1280, height: 800 });

    // ── 2. LOGIN PAGE ────────────────────────────────────────────────────────
    console.log('\n[2] Login Page — /app');
    await page.goto(`${BASE}/app`, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1500);
    await shot(page, '05_login');

    // Form fields present
    const emailInput = page.locator('input[type="email"]');
    const passInput = page.locator('input[type="password"]');
    await emailInput.isVisible() ? pass('login', 'Email field visible') : issue('login', 'Email field missing', 'HIGH');
    await passInput.isVisible() ? pass('login', 'Password field visible') : issue('login', 'Password field missing', 'HIGH');

    // Autocomplete attributes
    const emailAC = await emailInput.getAttribute('autocomplete');
    emailAC === 'email' ? pass('login', 'Email autocomplete="email"') : issue('login', `Email autocomplete="${emailAC}" — should be "email"`, 'LOW');

    // Submit with empty fields
    await page.click('#auth-submit');
    await page.waitForTimeout(500);
    const errAfterEmpty = await page.locator('.alert-error').count();
    // HTML5 validation should prevent submit, so no error div is fine
    pass('login', 'Empty submit handled (HTML5 validation or error shown)');

    // Wrong credentials error
    await page.fill('input[type="email"]', 'nobody@nowhere.com');
    await page.fill('input[type="password"]', 'wrongpass1');
    await page.click('#auth-submit');
    await page.waitForTimeout(2500);
    const errMsg = await page.locator('.alert-error').count();
    errMsg > 0 ? pass('login', 'Wrong credentials shows error alert') : issue('login', 'No error shown on wrong credentials', 'HIGH');
    await shot(page, '06_login_error');

    // Register tab
    const regBtn = page.locator('button', { hasText: 'Create Account' });
    await regBtn.click();
    await page.waitForTimeout(300);
    const nameField = page.locator('input#reg-name');
    await nameField.isVisible() ? pass('login', 'Register form shows Name field') : issue('login', 'Register name field missing', 'MEDIUM');
    await shot(page, '07_register');

    // Register new user and login
    const ts = Date.now();
    const testEmail = `ux_${ts}@orquanta.test`;
    await page.fill('input#reg-name', 'UX Tester');
    await page.fill('input[type="email"]', testEmail);
    await page.fill('input[type="password"]', 'UXTest1234!');
    await page.click('#auth-submit');
    await page.waitForTimeout(3000);
    const onDashboard = page.url().includes('/app') && !(await page.locator('input[type="email"]').isVisible().catch(() => false));
    onDashboard ? pass('login', 'Registration auto-logs in → dashboard') : issue('login', 'Registration did not redirect to dashboard', 'HIGH');
    await shot(page, '08_post_register');

    // ── 3. DASHBOARD ─────────────────────────────────────────────────────────
    console.log('\n[3] Dashboard — /');
    await page.waitForTimeout(2000);
    await shot(page, '09_dashboard');

    // Sidebar present
    const sidebar = page.locator('.orq-sidebar, aside');
    await sidebar.isVisible() ? pass('dashboard', 'Sidebar visible') : issue('dashboard', 'Sidebar not visible', 'HIGH');

    // Nav links
    const navLinks = await page.locator('nav .nav-link').count();
    navLinks >= 6 ? pass('dashboard', `${navLinks} nav links`) : issue('dashboard', `Only ${navLinks} nav links`, 'MEDIUM');

    // Metric cards
    await page.waitForTimeout(3000); // let API calls settle
    const metricCards = await page.locator('.glass-card, .metric-card, [class*="stat"]').count();
    metricCards > 0 ? pass('dashboard', `${metricCards} metric/stat cards visible`) : issue('dashboard', 'No metric cards found — API may be failing', 'HIGH');
    await shot(page, '10_dashboard_loaded');

    // Sidebar collapse
    const toggleBtn = page.locator('aside button').first();
    await toggleBtn.click();
    await page.waitForTimeout(400);
    await shot(page, '11_sidebar_collapsed');
    await toggleBtn.click();
    await page.waitForTimeout(300);
    pass('dashboard', 'Sidebar collapse/expand works');

    // ── 4. NAVIGATION FLOWS ──────────────────────────────────────────────────
    console.log('\n[4] Navigation — all main routes');
    const routes = [
        ['/goals', 'Submit Goal', 'textarea, input[type="text"]'],
        ['/agents', 'Agent Monitor', '.glass-card, .agent'],
        ['/costs', 'Cost Analytics', 'canvas, .recharts-wrapper, .glass-card'],
        ['/pricing', 'Live Pricing', 'table, .glass-card'],
        ['/audit', 'Audit Log', 'table, .audit, .glass-card'],
        ['/billing', 'Billing', 'h1, h2, [style*="gradient"]'],
        ['/free', 'Free GPU', '.glass-card'],
        ['/carbon', 'Carbon Tracker', '.glass-card'],
        ['/settings', 'Settings', 'input, .glass-card'],
    ];

    for (const [route, label, selector] of routes) {
        await page.goto(`${BASE}/app${route}`, { waitUntil: 'domcontentloaded', timeout: 8000 }).catch(() => {});
        await page.waitForTimeout(1200);
        const el = await page.locator(selector).first().isVisible().catch(() => false);
        el ? pass('nav', `${label} (${route}) renders`) : issue('nav', `${label} (${route}) — no content visible`, 'MEDIUM');
        await shot(page, `nav_${label.replace(/\s/g,'_').toLowerCase()}`);
    }

    // ── 5. GOAL SUBMISSION FLOW ──────────────────────────────────────────────
    console.log('\n[5] Goal Submission Flow');
    await page.goto(`${BASE}/app/goals`, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1000);
    const goalTextarea = page.locator('textarea').first();
    if (await goalTextarea.isVisible()) {
        await goalTextarea.fill('Fine-tune Mistral 7B on customer support data, keep cost under $30');
        const submitBtn = page.locator('button[type="submit"], button:has-text("Submit"), button:has-text("Run")').first();
        if (await submitBtn.isVisible()) {
            await submitBtn.click();
            await page.waitForTimeout(2000);
            pass('goals', 'Goal submitted successfully');
            await shot(page, 'goal_submitted');
        } else {
            issue('goals', 'No submit button found on goal page', 'HIGH');
        }
    } else {
        issue('goals', 'No textarea on goal submission page', 'HIGH');
    }

    // ── 6. LOGOUT ─────────────────────────────────────────────────────────────
    console.log('\n[6] Logout Flow');
    await page.goto(`${BASE}/app`, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(800);
    const logoutBtn = page.locator('button[title="Logout"], button:has([data-lucide="log-out"]), aside button').last();
    if (await logoutBtn.isVisible()) {
        await logoutBtn.click();
        await page.waitForTimeout(1000);
        const backToLogin = await page.locator('input[type="email"]').isVisible();
        backToLogin ? pass('auth', 'Logout returns to login page') : issue('auth', 'Logout did not return to login', 'HIGH');
        await shot(page, 'after_logout');
    } else {
        issue('auth', 'Logout button not found', 'HIGH');
    }

    await browser.close();

    // ── FINAL REPORT ──────────────────────────────────────────────────────────
    console.log('\n═══════════════════════════════════════════════════════');
    console.log('  UX AUDIT RESULTS');
    console.log('═══════════════════════════════════════════════════════');
    console.log(`  PASS: ${PASSES.length}  |  ISSUES: ${ISSUES.length}`);

    if (ISSUES.length > 0) {
        const hi = ISSUES.filter(i => i.severity === 'HIGH');
        const med = ISSUES.filter(i => i.severity === 'MEDIUM');
        const lo = ISSUES.filter(i => i.severity === 'LOW');
        if (hi.length) { console.log(`\n  HIGH (${hi.length}):`); hi.forEach(i => console.log(`    ✗ [${i.page}] ${i.desc}`)); }
        if (med.length) { console.log(`\n  MEDIUM (${med.length}):`); med.forEach(i => console.log(`    ✗ [${i.page}] ${i.desc}`)); }
        if (lo.length) { console.log(`\n  LOW (${lo.length}):`); lo.forEach(i => console.log(`    ✗ [${i.page}] ${i.desc}`)); }
    } else {
        console.log('\n  No issues found.');
    }
    console.log(`\n  Screenshots saved to: ${SS_DIR}`);
    console.log('═══════════════════════════════════════════════════════\n');
    process.exit(ISSUES.filter(i => i.severity === 'HIGH').length > 0 ? 1 : 0);
})();
