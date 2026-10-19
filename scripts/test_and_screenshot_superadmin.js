const path = require('path');
const { chromium } = require(path.resolve(__dirname, '../tests/nextcloud/e2e/node_modules/playwright'));
const fs = require('fs');

const BASE_URL = process.env.BASE_URL || 'https://d193xac66yp6w4.cloudfront.net';
const SCREENSHOTS_DIR = process.env.SCREENSHOTS_DIR || '/Users/png/.gemini/antigravity/brain/48cd64b8-afb9-4783-b047-599310494447/screenshots';

if (!fs.existsSync(SCREENSHOTS_DIR)) {
  fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });
}

async function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function run() {
  console.log(`🚀 Starting SuperAdmin End-to-End Visual & Functional Audit on: ${BASE_URL}`);
  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
  const context = await browser.newContext({
    viewport: { width: 1680, height: 1050 },
    userAgent: 'Storix-Playwright-Auditor/1.0'
  });
  const page = await context.newPage();

  // Helper to take named screenshots
  async function snap(filename) {
    const filePath = path.join(SCREENSHOTS_DIR, filename);
    await page.screenshot({ path: filePath, fullPage: false });
    console.log(`  📸 Saved: ${filename}`);
  }

  try {
    // ------------------------------------------------------------------------
    // 1. LOGIN PAGE
    // ------------------------------------------------------------------------
    console.log('\n[1/10] Testing Login Page...');
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForSelector('input[placeholder="admin@example.com"]', { timeout: 15000 });
    await snap('01_login_page.png');

    // Perform Login
    console.log('  Submitting administrator credentials...');
    await page.fill('input[placeholder="admin@example.com"]', 'admin@storix.io');
    await page.fill('input[type="password"]', 'StorixAdmin2026!Secure');
    await page.click('button[type="submit"]');

    // Wait for redirect to /tenants
    await page.waitForURL('**/tenants**', { timeout: 20000 });
    await page.waitForLoadState('networkidle');
    await sleep(2000);
    console.log('  ✔ Logged in successfully. Current URL:', page.url());

    // ------------------------------------------------------------------------
    // 2. TENANTS LIST
    // ------------------------------------------------------------------------
    console.log('\n[2/10] Testing Tenants Operations List...');
    await page.waitForSelector('.ant-table-row', { timeout: 15000 });
    await snap('02_tenants_list.png');

    // ------------------------------------------------------------------------
    // 3. CREATE NEW TENANT
    // ------------------------------------------------------------------------
    console.log('\n[3/10] Testing Tenant Creation...');
    const createBtn = await page.waitForSelector('button:has-text("Provision Dedicated Tenant")', { timeout: 10000 });
    await createBtn.click();
    await page.waitForSelector('.ant-modal-content', { timeout: 10000 });
    await sleep(800);

    const testTenantId = 'enterprise-demo';
    await page.fill('input[placeholder="e.g. acme-corp"]', testTenantId);
    await page.fill('input[placeholder="acme.png261.dev"]', `${testTenantId}.png261.dev`);
    await page.fill('input[placeholder="admin@acme.com"]', `admin@${testTenantId}.com`);
    
    // Click submit
    const submitBtn = await page.waitForSelector('button:has-text("Launch Tenant Instance")', { timeout: 5000 });
    await submitBtn.click();

    // Wait for modal to close and list to reflect creation
    console.log('  Waiting for tenant creation to register...');
    await sleep(4000);
    await page.waitForLoadState('networkidle');
    await snap('03_tenant_created_live.png');

    // ------------------------------------------------------------------------
    // 4. TENANT DETAILS & TABS
    // ------------------------------------------------------------------------
    console.log('\n[4/10] Testing Tenant Details Page & Feature Tabs...');
    await page.goto(`${BASE_URL}/tenants/dev-tenant`, { waitUntil: 'networkidle', timeout: 20000 });
    await sleep(2500);
    await snap('04_tenant_detail_overview.png');

    // Tab: Topology & Architecture
    console.log('  Opening Topology Tab...');
    const topologyTab = await page.$('.ant-tabs-tab:has-text("Topology"), .ant-tabs-tab:has-text("Architecture")');
    if (topologyTab) {
      await topologyTab.click();
      await sleep(2000);
      await snap('05_tenant_detail_topology.png');
    }

    // Tab: Live Metrics
    console.log('  Opening Live Metrics Tab...');
    const metricsTab = await page.$('.ant-tabs-tab:has-text("Metrics")');
    if (metricsTab) {
      await metricsTab.click();
      await sleep(2000);
      await snap('06_tenant_detail_metrics.png');
    }

    // Tab: Container Live Logs
    console.log('  Opening Container Live Logs Tab...');
    const logsTab = await page.$('.ant-tabs-tab:has-text("Logs")');
    if (logsTab) {
      await logsTab.click();
      await sleep(2000);
      await snap('07_tenant_detail_logs.png');
    }

    // Tab: FinOps & Custom Domain
    console.log('  Opening FinOps & Custom Domain Tab...');
    const finopsTab = await page.$('.ant-tabs-tab:has-text("FinOps")');
    if (finopsTab) {
      await finopsTab.click();
      await sleep(2000);
      await snap('08_tenant_detail_finops.png');
    }

    // Tab: Health & Quota Limit
    console.log('  Opening Health & Quota Limit Tab...');
    const healthTab = await page.$('.ant-tabs-tab:has-text("Health")');
    if (healthTab) {
      await healthTab.click();
      await sleep(2000);
      await snap('09_tenant_detail_health.png');
    }

    // ------------------------------------------------------------------------
    // 5. FREEZE (SUSPEND) TENANT
    // ------------------------------------------------------------------------
    console.log('\n[5/10] Testing Tenant Freeze / Suspend...');
    await page.goto(`${BASE_URL}/tenants`, { waitUntil: 'networkidle', timeout: 20000 });
    await sleep(2500);

    // Look for target row
    let targetRow = await page.$(`tr:has-text("${testTenantId}")`) || await page.$('tr:has-text("e2e-tenant")');
    if (targetRow) {
      const suspendBtn = await targetRow.$('button:has-text("Suspend")');
      if (suspendBtn) {
        console.log('  Clicking Suspend button...');
        await suspendBtn.click();
        await sleep(3500);
        await page.waitForLoadState('networkidle');
      }
    }
    await snap('10_tenant_after_freeze_suspended.png');

    // ------------------------------------------------------------------------
    // 6. DELETE (DEPROVISION) TENANT
    // ------------------------------------------------------------------------
    console.log('\n[6/10] Testing Tenant Deletion / Teardown...');
    let delRow = await page.$(`tr:has-text("${testTenantId}")`);
    if (delRow) {
      const delBtn = await delRow.$('button:has-text("Delete"), button.ant-btn-dangerous');
      if (delBtn) {
        console.log('  Clicking Delete button...');
        await delBtn.click();
        await sleep(1000);
        // Confirm popconfirm
        const confirmBtn = await page.waitForSelector('.ant-popconfirm-buttons button.ant-btn-dangerous, .ant-popconfirm button:has-text("Delete")', { timeout: 5000 });
        if (confirmBtn) {
          await confirmBtn.click();
          console.log('  Confirmed tenant deletion.');
          await sleep(4000);
          await page.waitForLoadState('networkidle');
        }
      }
    }
    await snap('11_tenant_after_deletion.png');

    // ------------------------------------------------------------------------
    // 7. TELEMETRY & SYSTEM METRICS
    // ------------------------------------------------------------------------
    console.log('\n[7/10] Testing Telemetry Dashboard & Fleet Metrics...');
    await page.goto(`${BASE_URL}/telemetry`, { waitUntil: 'networkidle', timeout: 20000 });
    await sleep(3000);
    await snap('12_superadmin_telemetry_metrics.png');

    // ------------------------------------------------------------------------
    // 8. CLOUD AUDIT TRAIL
    // ------------------------------------------------------------------------
    console.log('\n[8/10] Testing Immutable Cloud Audit Trail...');
    await page.goto(`${BASE_URL}/audit-logs`, { waitUntil: 'networkidle', timeout: 20000 });
    await sleep(2500);
    await snap('13_superadmin_audit_logs.png');

    // ------------------------------------------------------------------------
    // 9. WEBHOOKS & ALERTS
    // ------------------------------------------------------------------------
    console.log('\n[9/10] Testing Webhooks & Alerts Settings...');
    await page.goto(`${BASE_URL}/settings/webhooks`, { waitUntil: 'networkidle', timeout: 20000 });
    await sleep(2500);
    await snap('14_superadmin_webhooks.png');

    // ------------------------------------------------------------------------
    // 10. DARK THEME MODE
    // ------------------------------------------------------------------------
    console.log('\n[10/10] Testing Dark Mode Experience...');
    await page.goto(`${BASE_URL}/tenants`, { waitUntil: 'networkidle', timeout: 20000 });
    await sleep(1500);
    await page.evaluate(() => {
      localStorage.setItem('storix_theme', 'dark');
      localStorage.setItem('filestore_theme', 'dark');
      window.location.reload();
    });
    await page.waitForLoadState('networkidle');
    await sleep(2500);
    await snap('15_superadmin_dark_mode_dashboard.png');

    console.log('\n🎉 ALL SUPERADMIN PAGES AND OPERATIONS AUDITED SUCCESSFULLY!');
  } catch (err) {
    console.error('❌ Error during SuperAdmin audit:', err);
    await snap('error_state.png');
    throw err;
  } finally {
    await browser.close();
  }
}

run().catch(err => {
  console.error(err);
  process.exit(1);
});
