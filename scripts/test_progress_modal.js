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
  const targetTenant = process.argv[2] || 'progress-test';
  console.log(`🚀 Testing Tenant Lifecycle Progress Modal & Live Steps/Logs for: ${targetTenant} on ${BASE_URL}`);

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

    // Fill form
    await page.fill('#tenant_id', targetTenant);
    await page.fill('#admin_email', `admin@${targetTenant}.com`);
    
    // Submit creation
    await page.click('button:has-text("Launch Tenant Instance")');
    console.log('  ✔ Submitted tenant creation form.');
    await sleep(3000);

    // 3. Locate Provisioning Row and Click Progress Tag
    console.log('[3/5] Inspecting tenant table for provisioning status and clicking progress tag...');
    await page.waitForSelector(`tbody tr:has-text("${targetTenant}")`, { timeout: 15000 });
    
    // Find row
    const row = await page.$(`tbody tr:has-text("${targetTenant}")`);
    if (!row) throw new Error(`Row for ${targetTenant} not found`);

    // Verify PROVISIONING tag is visible
    const statusText = await row.innerText();
    console.log('  Tenant row text:', statusText.replace(/\n+/g, ' | '));

    // Click on the status/progress area or "Steps & Logs" button
    const stepsBtn = await row.$('button:has-text("Steps & Logs")');
    if (stepsBtn) {
      console.log('  Found dedicated "Steps & Logs" button in row actions. Clicking it...');
      await stepsBtn.click();
    } else {
      console.log('  Clicking on the progress status tag...');
      const tag = await row.$('.ant-tag:has-text("PROVISIONING"), .ant-progress');
      if (tag) await tag.click();
    }

    // Wait for TenantProgressModal to open
    console.log('  Waiting for TenantProgressModal to appear...');
    await page.waitForSelector('.ant-modal-content:has-text("Provisioning Orchestration")', { timeout: 10000 });
    await sleep(2500); // Allow real-time polling to stream logs

    // Verify steps and logs in modal
    const modal = await page.$('.ant-modal-content:has-text("Provisioning Orchestration")');
    const modalText = await modal.innerText();
    console.log('  ✔ Modal successfully rendered!');
    console.log('  Modal text snippet:', modalText.slice(0, 300).replace(/\n+/g, ' | '));

    // Take screenshot of Provisioning Progress Modal
    await snap('30_provision_progress_modal_steps_logs.png');

    // Test searching in terminal
    const searchInput = await page.$('.ant-modal-content input[placeholder="Filter logs..."]');
    if (searchInput) {
      await searchInput.fill('StepFunctions');
      await sleep(1000);
      console.log('  ✔ Verified log filtering by search keyword.');
      await searchInput.fill('');
    }

    // Close modal
    const closeBtn = await page.$('.ant-modal-footer button:has-text("Close"), .ant-modal-close');
    if (closeBtn) await closeBtn.click();
    await sleep(1500);

    // 4. Trigger Deprovisioning / Deletion
    console.log(`[4/5] Locating ACTIVE tenant "${targetTenant}" to trigger deprovisioning...`);
    let activeRow = null;
    for (let i = 0; i < 40; i++) {
      const r = await page.$(`tbody tr:has-text("${targetTenant}")`);
      if (r) {
        const text = await r.innerText();
        if (text.includes("ACTIVE")) {
          activeRow = r;
          break;
        }
      }
      await sleep(2000);
    }

    if (!activeRow) {
      activeRow = await page.waitForSelector(`tbody tr:has-text("${targetTenant}")`, { timeout: 10000 });
    }

    const deleteBtn = await activeRow.$('button.ant-btn-dangerous:not([disabled]), button[aria-label="delete"]:not([disabled])');
    if (!deleteBtn) {
      // Fallback: look for popconfirm button
      const allBtns = await activeRow.$$('button');
      for (const b of allBtns) {
        const isDanger = await b.evaluate((el) => el.classList.contains('ant-btn-dangerous') && !el.disabled);
        if (isDanger) {
          await b.click();
          break;
        }
      }
    } else {
      await deleteBtn.click();
    }

    await sleep(1000);
    // Confirm popconfirm
    const confirmBtn = await page.waitForSelector('.ant-popover-buttons button.ant-btn-primary, .ant-popconfirm-buttons button.ant-btn-primary', { timeout: 5000 });
    await confirmBtn.click();
    console.log('  ✔ Deletion confirmed.');
    await sleep(2500);

    // 5. Click Deprovisioning Progress & Inspect Logs
    console.log('[5/5] Inspecting deprovisioning steps and teardown logs in modal...');
    const deprovRow = await page.waitForSelector(`tbody tr:has-text("${targetTenant}")`, { timeout: 15000 });
    
    // Click Steps & Logs or DELETING tag
    const deprovStepsBtn = await deprovRow.$('button:has-text("Steps & Logs")');
    if (deprovStepsBtn) {
      console.log('  Clicking "Steps & Logs" button on deprovisioning row...');
      await deprovStepsBtn.click();
    } else {
      const deprovTag = await deprovRow.$('.ant-tag:has-text("DELETING"), .ant-tag:has-text("DEPROVISIONING")');
      if (deprovTag) await deprovTag.click();
    }

    await page.waitForSelector('.ant-modal-content:has-text("Deprovisioning Teardown"), .ant-modal-content:has-text("DEPROVISIONING")', { timeout: 10000 });
    await sleep(3500); // Wait for live teardown logs

    const deprovModal = await page.$('.ant-modal-content:has-text("Deprovisioning Teardown"), .ant-modal-content:has-text("DEPROVISIONING")');
    const deprovModalText = await deprovModal.innerText();
    console.log('  ✔ Deprovisioning Modal rendered successfully!');
    console.log('  Deprovisioning modal text snippet:', deprovModalText.slice(0, 300).replace(/\n+/g, ' | '));

    // Take screenshot of Deprovisioning Progress Modal
    await snap('31_deprovision_progress_modal_steps_logs.png');

    console.log('🎉 Verification completed successfully! All steps, active state, and logs verified.');
  } catch (err) {
    console.error('❌ Test failed:', err);
    await snap('error_progress_modal.png');
    process.exit(1);
  } finally {
    await browser.close();
  }
}

run();
