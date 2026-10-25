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
  const tenantId = process.argv[2] || 'kappa';
  const tenantDomain = `${tenantId}.png261.dev`;
  console.log(`🚀 Provisioning new tenant "${tenantId}" (${tenantDomain}) and verifying login screen bypasses setup wizard...`);

  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--ignore-certificate-errors']
  });
  const context = await browser.newContext({
    viewport: { width: 1680, height: 1050 },
    userAgent: 'Storix-AutoInstall-Auditor/1.0',
    ignoreHTTPSErrors: true
  });
  const page = await context.newPage();

  async function snap(filename) {
    const filePath = path.join(SCREENSHOTS_DIR, filename);
    await page.screenshot({ path: filePath, fullPage: false });
    console.log(`  📸 Saved screenshot: ${filename}`);
  }

  try {
    // 1. Login to SuperAdmin Console
    console.log('[1/5] Logging in to Storix Admin Console...');
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForSelector('input[placeholder="admin@example.com"]', { timeout: 15000 });
    await page.fill('input[placeholder="admin@example.com"]', 'admin@storix.io');
    await page.fill('input[type="password"]', 'StorixAdmin2026!Secure');
    await page.click('button[type="submit"]');

    await page.waitForURL('**/tenants**', { timeout: 25000 });
    await page.waitForLoadState('networkidle');
    await sleep(2000);
    console.log('  ✔ Logged in successfully.');

    // 2. Open Provision Tenant Modal
    console.log(`[2/5] Opening Provision Tenant Modal for "${tenantId}"...`);
    const provisionBtn = await page.waitForSelector('button:has-text("Provision Dedicated Tenant")', { timeout: 15000 });
    await provisionBtn.click();
    await page.waitForSelector('.ant-modal-title:has-text("Provision Dedicated Tenant")', { timeout: 10000 });

    // Fill form
    await page.fill('#tenant_id', tenantId);
    if (await page.$('#domain')) {
      await page.fill('#domain', tenantDomain);
    }
    await page.fill('#admin_email', `admin@${tenantId}.com`);
    
    // Submit
    const submitBtn = await page.waitForSelector('button:has-text("Launch Tenant Instance")', { timeout: 5000 });
    await submitBtn.click();
    console.log('  ✔ Submitted tenant creation form.');
    await sleep(3000);

    // 3. Monitor Provisioning Progress until ACTIVE (100%)
    console.log('[3/5] Monitoring provisioning lifecycle in real time...');
    let isProvisioned = false;
    for (let i = 0; i < 90; i++) { // poll up to ~4.5 minutes
      await sleep(3000);
      const content = await page.content();
      
      // Check if progress modal or table row indicates active
      if (content.includes('100%') || content.includes('Ready & Operational') || content.includes('ACTIVE')) {
        // Double check if tenant row has ACTIVE
        const rows = await page.$$('tbody tr.ant-table-row');
        for (const r of rows) {
          const txt = await r.innerText();
          if (txt.includes(tenantId) && (txt.includes('ACTIVE') || txt.includes('100%'))) {
            console.log(`  🎉 Tenant "${tenantId}" is ACTIVE & Operational at 100%!`);
            isProvisioned = true;
            break;
          }
        }
      }

      if (isProvisioned) break;

      if (i % 5 === 0) {
        console.log(`  [Poll ${i + 1}] Waiting for ECS task and Target Group health check...`);
      }
    }

    if (!isProvisioned) {
      throw new Error(`Tenant ${tenantId} did not reach 100% ACTIVE within timeout`);
    }

    await snap('32_tenant_provisioned_active_console.png');

    // 4. Visit the new tenant's web domain for the FIRST TIME!
    console.log(`[4/5] Navigating to https://${tenantDomain} for the FIRST TIME...`);
    const tenantPage = await context.newPage();
    
    let res = null;
    for (let retry = 0; retry < 15; retry++) {
      try {
        res = await tenantPage.goto(`https://${tenantDomain}`, { waitUntil: 'networkidle', timeout: 20000 });
        if (res && res.status() < 500) break;
      } catch (err) {
        console.log(`  Waiting for DNS / Target Group routing... (${err.message})`);
        await sleep(5000);
      }
    }

    await sleep(2000);
    const tenantUrl = tenantPage.url();
    const tenantTitle = await tenantPage.title();
    const tenantHtml = await tenantPage.content();

    console.log(`  URL: ${tenantUrl}`);
    console.log(`  Title: ${tenantTitle}`);

    // CRITICAL ASSERTION:
    // It MUST NOT show "Create an admin account" / installation wizard!
    const hasSetupWizard = tenantHtml.includes('Create an admin account') || 
                           tenantHtml.includes('Tạo tài khoản quản trị') || 
                           tenantHtml.includes('Finish setup') ||
                           tenantHtml.includes('Database user');

    if (hasSetupWizard) {
      await tenantPage.screenshot({ path: path.join(SCREENSHOTS_DIR, '33_ERROR_SHOWS_SETUP_WIZARD.png') });
      throw new Error(`FAILURE: Tenant ${tenantDomain} is displaying "Create an admin account" wizard!`);
    } else {
      console.log('  ✅ SUCCESS: "Create an admin account" wizard is NOT present!');
    }

    // CRITICAL ASSERTION:
    // It MUST show the standard Nextcloud Login Screen!
    const hasLoginScreen = tenantUrl.includes('/login') || 
                          tenantHtml.includes('login-form') || 
                          tenantHtml.includes('input#user') || 
                          (await tenantPage.$('input[name="user"], input#user, input[type="text"]')) !== null;

    if (!hasLoginScreen) {
      await tenantPage.screenshot({ path: path.join(SCREENSHOTS_DIR, '33_ERROR_NO_LOGIN_SCREEN.png') });
      throw new Error(`FAILURE: Tenant ${tenantDomain} is not showing standard Login Screen!`);
    } else {
      console.log('  ✅ SUCCESS: Standard Nextcloud Login Screen verified!');
    }

    await tenantPage.screenshot({ path: path.join(SCREENSHOTS_DIR, '33_tenant_first_visit_login_screen.png') });
    console.log('  📸 Saved screenshot: 33_tenant_first_visit_login_screen.png');

    // 5. Test logging in with admin credentials
    console.log('[5/5] Logging in as admin on the new tenant...');
    await tenantPage.fill('input#user, input[name="user"]', 'admin');
    await tenantPage.fill('input#password, input[name="password"]', 'StorixAdmin2026!Secure');
    await tenantPage.click('button#submit-form, button[type="submit"]');

    await tenantPage.waitForURL('**/apps/**', { timeout: 30000 });
    await tenantPage.waitForLoadState('networkidle');
    await sleep(3000);

    console.log(`  ✔ Logged in to Nextcloud dashboard successfully! Current URL: ${tenantPage.url()}`);
    await tenantPage.screenshot({ path: path.join(SCREENSHOTS_DIR, '34_tenant_admin_dashboard_logged_in.png') });
    console.log('  📸 Saved screenshot: 34_tenant_admin_dashboard_logged_in.png');

    console.log('\n🎉 ALL TESTS PASSED: Nextcloud auto-install succeeded, setup wizard completely eliminated!');
  } finally {
    await browser.close();
  }
}

run().catch(err => {
  console.error('❌ E2E Verification failed:', err);
  process.exit(1);
});
