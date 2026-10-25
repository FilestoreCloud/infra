const path = require('path');
const { chromium } = require(path.resolve(__dirname, '../tests/nextcloud/e2e/node_modules/playwright'));
const fs = require('fs');

const BASE_URL = process.env.BASE_URL || 'https://admin.png261.dev';
const SCREENSHOTS_DIR = process.env.SCREENSHOTS_DIR || '/Users/png/.gemini/antigravity/brain/48cd64b8-afb9-4783-b047-599310494447/screenshots';

if (!fs.existsSync(SCREENSHOTS_DIR)) {
  fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });
}

async function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function run() {
  const targetTenant = process.argv[2] || 'acme';
  console.log(`🚀 Testing Tenant Deprovisioning & Real-Time Progress for: ${targetTenant} on ${BASE_URL}`);

  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
  const context = await browser.newContext({
    viewport: { width: 1680, height: 1050 },
    userAgent: 'Storix-Deprovision-Auditor/1.0'
  });
  const page = await context.newPage();

  async function snap(filename) {
    const filePath = path.join(SCREENSHOTS_DIR, filename);
    await page.screenshot({ path: filePath, fullPage: false });
    console.log(`  📸 Saved screenshot: ${filename}`);
  }

  try {
    // 1. Login
    console.log('[1/4] Logging in to Storix Admin Console...');
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForSelector('input[placeholder="admin@example.com"]', { timeout: 15000 });
    await page.fill('input[placeholder="admin@example.com"]', 'admin@storix.io');
    await page.fill('input[type="password"]', 'StorixAdmin2026!Secure');
    await page.click('button[type="submit"]');

    await page.waitForURL('**/tenants**', { timeout: 25000 });
    await page.waitForLoadState('networkidle');
    await sleep(2000);
    console.log('  ✔ Logged in successfully. Current URL:', page.url());

    // 2. Locate Target Tenant Row
    console.log(`[2/4] Locating tenant "${targetTenant}" in table...`);
    const rows = await page.$$('tbody tr.ant-table-row');
    let tenantRow = null;
    for (const r of rows) {
      const text = await r.innerText();
      const lines = text.split('\n').map(s => s.trim()).filter(Boolean);
      if (lines.includes(targetTenant)) {
        tenantRow = r;
        break;
      }
    }
    if (!tenantRow) {
      tenantRow = await page.$(`tr:has-text("${targetTenant}")`);
    }
    if (!tenantRow) {
      throw new Error(`Tenant "${targetTenant}" not found in tenants table!`);
    }
    console.log(`  ✔ Found row for tenant "${targetTenant}"`);

    // 3. Click Delete button
    console.log(`[3/4] Triggering Delete for "${targetTenant}"...`);
    const delBtn = await tenantRow.$('button:has-text("Delete"), button.ant-btn-dangerous');
    if (!delBtn) {
      throw new Error(`Delete button not found for tenant "${targetTenant}"`);
    }
    await delBtn.click();
    await sleep(1000);

    // Confirm popconfirm
    const confirmBtn = await page.waitForSelector(
      '.ant-popconfirm-buttons button.ant-btn-dangerous, .ant-popconfirm button:has-text("Delete")',
      { timeout: 8000 }
    );
    if (!confirmBtn) {
      throw new Error('Popconfirm delete confirmation button not found!');
    }
    await confirmBtn.click();
    console.log('  ✔ Confirmed deletion modal.');

    // 4. Capture Progress Card & Polling
    console.log('[4/4] Monitoring Teardown & Deprovisioning Progress...');
    let teardownCompleted = false;
    let cardCaptured = false;

    for (let i = 0; i < 40; i++) {
      await sleep(2500);

      // Check if progress card is visible
      const progressCard = await page.$('.ant-card:has-text("Deprovisioning"), .ant-card:has-text("Teardown"), .ant-card:has-text("DELETING")');
      if (progressCard && !cardCaptured) {
        console.log('  🎯 Real-time Progress Card detected!');
        const text = await progressCard.innerText();
        console.log(`  Card text:\n${text.split('\n').map(l => '    ' + l).join('\n')}`);
        await snap('27_tenant_deprovision_progress_active.png');
        cardCaptured = true;
      }

      // Check table to see if tenant row is still present
      const curRows = await page.$$('tbody tr.ant-table-row');
      let remainingRow = null;
      for (const r of curRows) {
        const text = await r.innerText();
        const lines = text.split('\n').map(s => s.trim()).filter(Boolean);
        if (lines.includes(targetTenant)) {
          remainingRow = r;
          break;
        }
      }
      if (!remainingRow) {
        console.log(`  🎉 Tenant "${targetTenant}" has been completely removed from registry table!`);
        teardownCompleted = true;
        await sleep(2000);
        await snap('28_after_destroy_tenants_purged.png');
        break;
      } else {
        const rowText = await remainingRow.innerText();
        console.log(`  [Poll ${i+1}] Tenant status in row: ${rowText.replace(/\n/g, ' | ')}`);
      }
    }

    if (!teardownCompleted) {
      console.log('  ⚠️ Teardown still running in background, checking final state...');
      await snap('29_deprovision_in_progress_state.png');
    }

    console.log('✔ Playwright verification finished.');
  } catch (err) {
    console.error('❌ Error during deprovisioning test:', err);
    await snap('error_deprovision_failure.png');
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
}

run();
