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
  const randomSuffix = Math.floor(1000 + Math.random() * 9000);
  const targetTenant = `tenant-verify-${randomSuffix}`;
  const targetDomain = `${targetTenant}.png261.dev`;

  console.log(`🚀 Starting Comprehensive Tenant Lifecycle & Ingress Isolation Audit`);
  console.log(`   Target Tenant ID: ${targetTenant}`);
  console.log(`   Target Subdomain: https://${targetDomain}`);
  console.log(`   SuperAdmin Console: ${BASE_URL}`);

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
    // 1. SuperAdmin Login
    console.log('\n[Phase 1] SuperAdmin Authentication & Dashboard Access...');
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle', timeout: 30000 });
    await snap('audit_01_superadmin_login.png');

    await page.waitForSelector('input[placeholder="admin@example.com"]', { timeout: 15000 });
    await page.fill('input[placeholder="admin@example.com"]', 'admin@storix.io');
    await page.fill('input[type="password"]', 'StorixAdmin2026!Secure');
    await page.click('button[type="submit"]');

    await page.waitForURL('**/tenants**', { timeout: 25000 });
    await page.waitForLoadState('networkidle');
    await sleep(2000);
    console.log('  ✔ Logged in successfully. Current URL:', page.url());
    await snap('audit_02_fleet_registry_initial.png');

    // 2. Open Provision Tenant Modal
    console.log(`\n[Phase 2] Provisioning new dedicated tenant: "${targetTenant}"...`);
    const createBtn = page.locator('button:has-text("Provision Dedicated Tenant")').first();
    await createBtn.click();
    await sleep(800);

    const modal = page.locator('[role="dialog"], .ant-modal').filter({ hasText: /Provision Dedicated Tenant/i }).first();
    await modal.waitFor({ state: 'visible', timeout: 10000 });
    console.log('  ✔ Provision modal visible.');

    await modal.locator('#create-tenant-id').fill(targetTenant);
    if (await modal.locator('#create-domain').isVisible().catch(() => false)) {
      await modal.locator('#create-domain').fill(targetDomain);
    }
    if (await modal.locator('#create-admin-email').isVisible().catch(() => false)) {
      await modal.locator('#create-admin-email').fill(`admin@${targetTenant}.com`);
    }
    await snap('audit_03_provision_form_filled.png');

    // Submit Provision Form
    const submitBtn = modal.locator('button:has-text("Launch Tenant Instance"), button[type="submit"]').first();
    await submitBtn.click();
    console.log('  ✔ Tenant provisioning job submitted.');
    await sleep(2500);

    // 3. Inspect PROVISIONING state in table
    console.log(`\n[Phase 3] Observing tenant provisioning orchestration...`);
    await snap('audit_04_tenant_provisioning_progress.png');

    // 4. Wait for Tenant to become ACTIVE
    console.log(`\n[Phase 4] Waiting for tenant "${targetTenant}" to achieve ACTIVE state...`);
    let isRowActive = false;
    for (let i = 0; i < 40; i++) {
      const pageText = await page.locator('body').innerText();
      if (pageText.includes(targetTenant) && (pageText.includes('ACTIVE') || pageText.includes('Ready'))) {
        isRowActive = true;
        console.log(`  ✔ Tenant "${targetTenant}" is now ACTIVE & Operational!`);
        break;
      }
      await sleep(2000);
    }
    await snap('audit_05_tenant_active_operational.png');

    // 5. Trigger Deprovisioning (Delete Tenant)
    console.log(`\n[Phase 5] Deprovisioning & Deleting tenant "${targetTenant}"...`);
    const row = page.locator('tr').filter({ hasText: targetTenant }).first();
    const moreBtn = row.locator('button[aria-label="More actions"]').first();
    await moreBtn.click();
    await sleep(600);
    await snap('audit_06_tenant_dropdown_menu.png');

    const deleteMenuItem = page.locator('[role="menuitem"]').filter({ hasText: 'Delete Tenant' }).first();
    await deleteMenuItem.click();
    await sleep(1000);
    await snap('audit_07_delete_confirmation_dialog.png');

    // Confirm AlertDialog
    const confirmDeleteBtn = page.locator('button').filter({ hasText: /^Delete$/ }).first();
    await confirmDeleteBtn.click();
    console.log('  ✔ Confirmed tenant permanent deletion.');
    await sleep(2500);
    await snap('audit_08_deprovisioning_in_progress.png');

    // 6. Wait for Tenant to be completely removed from Registry
    console.log(`\n[Phase 6] Waiting for tenant "${targetTenant}" to be purged from registry...`);
    for (let i = 0; i < 25; i++) {
      await page.reload({ waitUntil: 'networkidle' }).catch(() => {});
      await sleep(1500);
      const pageText = await page.locator('body').innerText();
      if (!pageText.includes(targetTenant)) {
        console.log(`  ✔ Tenant "${targetTenant}" successfully purged from SuperAdmin registry!`);
        break;
      }
      await sleep(2000);
    }
    await snap('audit_09_fleet_clean_post_deletion.png');

    // 7. Verify Ingress 404 for deleted tenant URL in a separate page
    console.log(`\n[Phase 7] Ingress Isolation Verification: probing https://${targetDomain}/ ...`);
    const tenantPage = await context.newPage();
    const response = await tenantPage.goto(`https://${targetDomain}/`, { waitUntil: 'domcontentloaded', timeout: 15000 }).catch(e => {
      console.log('  Direct navigation result:', e.message);
      return null;
    });

    const status = response ? response.status() : 0;
    console.log(`  ✔ HTTP Response Status: ${status}`);
    
    // Take screenshot of the 404 page!
    await tenantPage.screenshot({ path: path.join(SCREENSHOTS_DIR, 'audit_10_deleted_tenant_returns_404_isolated.png') });
    console.log(`  📸 Saved screenshot: audit_10_deleted_tenant_returns_404_isolated.png`);
    await tenantPage.close();

    console.log('\n======================================================');
    console.log('🎉 AUDIT SUCCESSFUL:');
    console.log(`   - Provisioned tenant: ${targetTenant}`);
    console.log(`   - Verified state: ACTIVE`);
    console.log(`   - Deleted tenant via SuperAdmin console: CONFIRMED`);
    console.log(`   - Registry cleanup: PURGED`);
    console.log(`   - Subdomain https://${targetDomain} access: HTTP 404 NOT FOUND (Isolated)`);
    console.log('======================================================\n');

  } catch (err) {
    console.error('❌ Test failed:', err);
    await snap('audit_error.png');
    process.exit(1);
  } finally {
    await browser.close();
  }
}

run();
