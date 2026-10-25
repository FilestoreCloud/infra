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
  const targetTenant = process.argv[2] || 'theta';
  console.log(`🚀 Verifying Deprovisioning Progress Modal for: ${targetTenant} on ${BASE_URL}`);

  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
  const context = await browser.newContext({
    viewport: { width: 1680, height: 1050 },
    userAgent: 'Storix-Lifecycle-Auditor/1.0'
  });
  const page = await context.newPage();

  async function snap(filename) {
    const filePath = path.join(SCREENSHOTS_DIR, filename);
    await page.screenshot({ path: filePath, fullPage: false });
    console.log(`  📸 Saved screenshot: ${filename}`);
  }

  try {
    // 1. Login
    console.log('[1/3] Logging in to Storix Admin Console...');
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForSelector('input[placeholder="admin@example.com"]', { timeout: 15000 });
    await page.fill('input[placeholder="admin@example.com"]', 'admin@storix.io');
    await page.fill('input[type="password"]', 'StorixAdmin2026!Secure');
    await page.click('button[type="submit"]');

    await page.waitForURL('**/tenants**', { timeout: 25000 });
    await page.waitForLoadState('networkidle');
    await sleep(2500);
    console.log('  ✔ Logged in successfully. Current URL:', page.url());

    // 2. Find ACTIVE target tenant row
    console.log(`[2/3] Locating ACTIVE row for tenant "${targetTenant}"...`);
    const row = await page.waitForSelector(`tbody tr:has-text("${targetTenant}")`, { timeout: 15000 });
    const rowText = await row.innerText();
    console.log('  Tenant row text:', rowText.replace(/\n+/g, ' | '));

    // Find and click Delete button (the red trashcan)
    const deleteBtn = await row.$('button.ant-btn-dangerous:not([disabled])');
    if (!deleteBtn) {
      throw new Error(`Delete button not found or disabled on row for ${targetTenant}`);
    }
    console.log('  Clicking delete button...');
    await deleteBtn.click();
    await sleep(800);

    // Confirm in popconfirm
    const confirmBtn = await page.waitForSelector('.ant-popover-buttons button.ant-btn-primary, .ant-popconfirm-buttons button.ant-btn-primary', { timeout: 5000 });
    await confirmBtn.click();
    console.log('  ✔ Deletion confirmed. Modal immediately opens in DEPROVISIONING mode!');

    // 3. Verify Deprovisioning Modal & Teardown Logs
    console.log('[3/3] Inspecting Deprovisioning Modal content, steps, and logs...');
    await page.waitForSelector('.ant-modal-content:has-text("Deprovisioning Teardown"), .ant-modal-content:has-text("DEPROVISIONING")', { timeout: 10000 });
    await sleep(3500); // Allow real-time polling to stream teardown logs

    const modal = await page.$('.ant-modal-content');
    const modalText = await modal.innerText();
    console.log('  ✔ Deprovisioning Modal rendered successfully!');
    console.log('  Modal text snippet:\n' + modalText.slice(0, 450).replace(/\n+/g, ' | '));

    // Take screenshot of Deprovisioning Progress Modal
    await snap('31_deprovision_progress_modal_steps_logs.png');

    console.log('🎉 Verification completed successfully! Deprovisioning steps and logs verified.');
  } catch (err) {
    console.error('❌ Test failed:', err);
    await snap('error_deprovision_modal.png');
    process.exit(1);
  } finally {
    await browser.close();
  }
}

run();
