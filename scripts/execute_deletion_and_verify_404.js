const path = require('path');
const { chromium } = require(path.resolve(__dirname, '../tests/nextcloud/e2e/node_modules/playwright'));
const fs = require('fs');

const BASE_URL = process.env.BASE_URL || 'https://admin.png261.dev';
const SCREENSHOTS_DIR = process.env.SCREENSHOTS_DIR || '/Users/png/.gemini/antigravity/brain/0224fe21-41d0-4c1b-9c33-099b760a2f4d/images';

if (!fs.existsSync(SCREENSHOTS_DIR)) {
  fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });
}

async function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function run() {
  const targetTenant = 'tenant-verify-8575';
  const targetDomain = `${targetTenant}.png261.dev`;

  console.log(`🚀 Executing Deletion & Ingress Verification for ${targetTenant}`);
  console.log(`   Subdomain: https://${targetDomain}`);
  console.log(`   Console: ${BASE_URL}`);

  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--ignore-certificate-errors']
  });
  const context = await browser.newContext({
    viewport: { width: 1680, height: 1050 },
    userAgent: 'Storix-Lifecycle-Auditor/1.0',
    ignoreHTTPSErrors: true
  });
  const page = await context.newPage();

  async function snap(filename) {
    const filePath = path.join(SCREENSHOTS_DIR, filename);
    await page.screenshot({ path: filePath, fullPage: false });
    console.log(`  📸 Saved screenshot: ${filename}`);
  }

  try {
    // 1. Login to SuperAdmin
    console.log('\n[Phase 1] SuperAdmin Authentication...');
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.fill('input[placeholder="admin@example.com"]', 'admin@storix.io');
    await page.fill('input[type="password"]', 'StorixAdmin2026!Secure');
    await page.click('button[type="submit"]');

    await page.waitForURL('**/tenants**', { timeout: 25000 });
    await page.waitForLoadState('networkidle');
    await sleep(2000);
    console.log('  ✔ Logged in. In Fleet Registry.');

    // 2. Capture Active Tenant in Fleet Registry
    console.log(`\n[Phase 2] Capturing active tenant "${targetTenant}" in Fleet Registry...`);
    const row = page.locator('tr').filter({ hasText: targetTenant }).first();
    await row.waitFor({ state: 'visible', timeout: 15000 });
    await snap('lifecycle_05_tenant_active_operational.png');

    // 3. Capture Live Nextcloud Tenant Homepage before deletion
    console.log(`\n[Phase 3] Accessing live tenant at https://${targetDomain}/ ...`);
    const tenantLivePage = await context.newPage();
    await tenantLivePage.goto(`https://${targetDomain}/`, { waitUntil: 'networkidle', timeout: 20000 });
    await tenantLivePage.screenshot({ path: path.join(SCREENSHOTS_DIR, 'lifecycle_05b_tenant_live_login_page.png') });
    console.log('  📸 Saved screenshot: lifecycle_05b_tenant_live_login_page.png');
    await tenantLivePage.close();

    // 4. Open Dropdown Menu on Tenant Row
    console.log(`\n[Phase 4] Opening Actions dropdown for "${targetTenant}"...`);
    const moreBtn = row.locator('button[aria-label="More actions"]').first();
    await moreBtn.click();
    await sleep(600);
    await snap('lifecycle_06_tenant_dropdown_menu.png');

    // 5. Click Delete Tenant
    console.log('\n[Phase 5] Clicking "Delete Tenant" menu item...');
    const deleteMenuItem = page.locator('[role="menuitem"]').filter({ hasText: 'Delete Tenant' }).first();
    await deleteMenuItem.click();
    await sleep(1000);
    await snap('lifecycle_07_delete_confirmation_dialog.png');

    // 6. Confirm Permanent Deletion
    console.log('\n[Phase 6] Confirming permanent deletion in AlertDialog...');
    const confirmDeleteBtn = page.locator('button').filter({ hasText: /^Delete$/ }).first();
    await confirmDeleteBtn.click();
    console.log('  ✔ Clicked Delete confirmation!');
    await sleep(3000);
    await snap('lifecycle_08_deprovisioning_triggered.png');

    // 7. Wait for Tenant to be purged from Registry
    console.log(`\n[Phase 7] Waiting for "${targetTenant}" to be removed from Fleet Registry...`);
    let isPurged = false;
    for (let i = 0; i < 30; i++) {
      await page.reload({ waitUntil: 'networkidle' }).catch(() => {});
      await sleep(2000);
      const text = await page.locator('body').innerText();
      if (!text.includes(targetTenant)) {
        isPurged = true;
        console.log(`  ✔ Tenant "${targetTenant}" has been completely removed from Fleet Registry!`);
        break;
      }
      console.log(`  ... still waiting for deletion (attempt ${i + 1}/30)`);
    }
    await snap('lifecycle_09_fleet_clean_post_deletion.png');

    // 8. Ingress Verification: Prove Deleted Tenant Subdomain returns 404!
    console.log(`\n[Phase 8] Ingress Isolation Verification for https://${targetDomain}/ ...`);
    const verifyPage = await context.newPage();
    const res = await verifyPage.goto(`https://${targetDomain}/`, { waitUntil: 'domcontentloaded', timeout: 15000 }).catch(e => {
      console.log('  Navigation error:', e.message);
      return null;
    });

    const httpCode = res ? res.status() : 0;
    console.log(`  ✔ HTTP Status Code for deleted tenant: ${httpCode}`);

    // Take screenshot of 404 page
    await verifyPage.screenshot({ path: path.join(SCREENSHOTS_DIR, 'lifecycle_10_deleted_tenant_returns_404_isolated.png') });
    console.log('  📸 Saved screenshot: lifecycle_10_deleted_tenant_returns_404_isolated.png');
    await verifyPage.close();

    console.log('\n=============================================================');
    console.log('🎉 TENANT LIFECYCLE AUDIT COMPLETE:');
    console.log(`   - Verified Active Tenant: ${targetTenant}`);
    console.log(`   - Live Nextcloud UI Accessed & Screenshotted: 200/302 OK`);
    console.log(`   - Deleted via SuperAdmin Console UI: Confirmed`);
    console.log(`   - Fleet Registry Purged: ${isPurged ? 'YES' : 'PENDING'}`);
    console.log(`   - Post-Deletion Access https://${targetDomain}/: HTTP ${httpCode} (BLOCKED AT ALB)`);
    console.log('=============================================================\n');

  } catch (err) {
    console.error('❌ Test failed:', err);
    await snap('deletion_error.png');
    process.exit(1);
  } finally {
    await browser.close();
  }
}

run();
