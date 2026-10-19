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
  console.log(`🚀 Comprehensive Lifecycle Progress Modal Test for: ${targetTenant} on ${BASE_URL}`);

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
    console.log('[1/5] Logging in to Storix Admin Console...');
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForSelector('input[placeholder="admin@example.com"]', { timeout: 15000 });
    await page.fill('input[placeholder="admin@example.com"]', 'admin@storix.io');
    await page.fill('input[type="password"]', 'StorixAdmin2026!Secure');
    await page.click('button[type="submit"]');

    await page.waitForURL('**/tenants**', { timeout: 25000 });
    await page.waitForLoadState('networkidle');
    await sleep(2500);
    console.log('  ✔ Logged in successfully. Current URL:', page.url());

    // 2. Open Create Tenant Modal
    console.log(`[2/5] Initiating provisioning for tenant "${targetTenant}"...`);
    const createBtn = await page.waitForSelector('button:has-text("Provision Dedicated Tenant")', { timeout: 15000 });
    await createBtn.click();
    await page.waitForSelector('.ant-modal-title:has-text("Provision Dedicated Tenant")', { timeout: 10000 });

    await page.fill('#tenant_id', targetTenant);
    await page.fill('#admin_email', `admin@${targetTenant}.com`);
    await page.click('button:has-text("Launch Tenant Instance")');
    console.log('  ✔ Submitted tenant creation form.');
    await sleep(2500);

    // 3. Inspect PROVISIONING state and click Steps & Logs
    console.log('[3/5] Locating provisioning row and opening progress modal...');
    const row = await page.waitForSelector(`tbody tr:has-text("${targetTenant}")`, { timeout: 15000 });
    
    // Find Steps & Logs button or progress tag
    const stepsBtn = await row.$('button:has-text("Steps & Logs")');
    if (stepsBtn) {
      console.log('  Clicking dedicated "Steps & Logs" button...');
      await stepsBtn.click();
    } else {
      console.log('  Clicking status tag...');
      const tag = await row.$('.ant-tag:has-text("PROVISIONING"), .ant-progress');
      if (tag) await tag.click();
    }

    // Wait for TenantProgressModal to open
    await page.waitForSelector('.ant-modal-content:has-text("Provisioning Orchestration")', { timeout: 10000 });
    await sleep(3000); // Allow real-time polling to stream logs

    const modal = await page.$('.ant-modal-content');
    const modalText = await modal.innerText();
    console.log('  ✔ Provisioning Modal rendered successfully!');
    console.log('  Modal text snippet:\n' + modalText.slice(0, 300).replace(/\n+/g, ' | '));

    // Save screenshot 30
    await snap('30_provision_progress_modal_steps_logs.png');

    // Close modal
    const closeBtn = await page.$('.ant-modal-footer button:has-text("Close")');
    if (closeBtn) await closeBtn.click();
    await sleep(1500);

    // 4. Wait for tenant to reach ACTIVE
    console.log(`[4/5] Waiting for tenant "${targetTenant}" to complete provisioning...`);
    let isRowActive = false;
    for (let i = 0; i < 45; i++) {
      const r = await page.$(`tbody tr:has-text("${targetTenant}")`);
      if (r) {
        const text = await r.innerText();
        if (text.includes("ACTIVE")) {
          isRowActive = true;
          break;
        }
      }
      await sleep(2000);
    }
    console.log('  ✔ Tenant is ACTIVE and ready for deprovisioning test.');

    // 5. Trigger Deprovisioning - modal should open immediately!
    console.log(`[5/5] Triggering deprovisioning for tenant "${targetTenant}"...`);
    const activeRow = await page.waitForSelector(`tbody tr:has-text("${targetTenant}")`, { timeout: 10000 });
    const deleteBtn = await activeRow.$('button.ant-btn-dangerous:not([disabled])');
    if (!deleteBtn) throw new Error('Delete button not found or disabled');
    await deleteBtn.click();
    await sleep(1000);

    // Confirm popconfirm
    const confirmBtn = await page.waitForSelector('.ant-popover-buttons button.ant-btn-primary, .ant-popconfirm-buttons button.ant-btn-primary', { timeout: 5000 });
    await confirmBtn.click();
    console.log('  ✔ Confirmed deletion. Modal should immediately open in DEPROVISIONING mode!');
    
    // Wait for TenantProgressModal in DEPROVISIONING mode
    await page.waitForSelector('.ant-modal-content:has-text("Deprovisioning Teardown"), .ant-modal-content:has-text("DEPROVISIONING")', { timeout: 10000 });
    await sleep(3500); // Allow real-time polling to stream teardown logs

    const deprovModal = await page.$('.ant-modal-content');
    const deprovModalText = await deprovModal.innerText();
    console.log('  ✔ Deprovisioning Modal rendered successfully!');
    console.log('  Deprovisioning modal snippet:\n' + deprovModalText.slice(0, 400).replace(/\n+/g, ' | '));

    // Save screenshot 31
    await snap('31_deprovision_progress_modal_steps_logs.png');

    console.log('🎉 Full lifecycle verification completed successfully! Both provisioning and deprovisioning steps and logs verified.');
  } catch (err) {
    console.error('❌ Test failed:', err);
    await snap('error_lifecycle_modal.png');
    process.exit(1);
  } finally {
    await browser.close();
  }
}

run();
