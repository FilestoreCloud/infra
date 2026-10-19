const path = require('path');
const { chromium } = require(path.resolve(__dirname, '../tests/nextcloud/e2e/node_modules/playwright'));
const fs = require('fs');

const SCREENSHOTS_DIR = process.env.SCREENSHOTS_DIR || '/Users/png/.gemini/antigravity/brain/48cd64b8-afb9-4783-b047-599310494447/screenshots';

if (!fs.existsSync(SCREENSHOTS_DIR)) {
  fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });
}

async function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function run() {
  const tenantId = process.argv[2] || 'omega';
  const tenantDomain = `${tenantId}.png261.dev`;
  console.log(`🚀 Verifying login screen and auto-install bypass for newly provisioned tenant "${tenantId}" (${tenantDomain})...`);

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

  try {
    console.log(`[1/3] Navigating to https://${tenantDomain} on first visit...`);
    let res = null;
    for (let retry = 0; retry < 15; retry++) {
      try {
        res = await page.goto(`https://${tenantDomain}`, { waitUntil: 'networkidle', timeout: 25000 });
        if (res && res.status() < 500) break;
      } catch (err) {
        console.log(`  Waiting for DNS / Target Group routing... (${err.message})`);
        await sleep(4000);
      }
    }

    await sleep(2000);
    const tenantUrl = page.url();
    const tenantTitle = await page.title();
    const tenantHtml = await page.content();

    console.log(`  URL: ${tenantUrl}`);
    console.log(`  Title: ${tenantTitle}`);

    // CRITICAL ASSERTION 1:
    // It MUST NOT show "Create an admin account" / installation wizard!
    const hasSetupWizard = tenantHtml.includes('Create an admin account') || 
                           tenantHtml.includes('Tạo tài khoản quản trị') || 
                           tenantHtml.includes('Finish setup') ||
                           tenantHtml.includes('Database user');

    if (hasSetupWizard) {
      await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '33_ERROR_SHOWS_SETUP_WIZARD.png') });
      throw new Error(`FAILURE: Tenant ${tenantDomain} is displaying "Create an admin account" wizard!`);
    } else {
      console.log('  ✅ SUCCESS: "Create an admin account" wizard is NOT present!');
    }

    // CRITICAL ASSERTION 2:
    // It MUST show the standard Nextcloud Login Screen!
    const hasLoginScreen = tenantUrl.includes('/login') || 
                          tenantHtml.includes('login-form') || 
                          tenantHtml.includes('input#user') || 
                          (await page.$('input[name="user"], input#user, input[type="text"]')) !== null;

    if (!hasLoginScreen) {
      await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '33_ERROR_NO_LOGIN_SCREEN.png') });
      throw new Error(`FAILURE: Tenant ${tenantDomain} is not showing standard Login Screen!`);
    } else {
      console.log('  ✅ SUCCESS: Standard Nextcloud Login Screen verified directly!');
    }

    const loginScreenshotPath = path.join(SCREENSHOTS_DIR, '33_tenant_first_visit_login_screen.png');
    await page.screenshot({ path: loginScreenshotPath });
    console.log(`  📸 Saved screenshot: 33_tenant_first_visit_login_screen.png`);

    // [2/3] Authenticate as tenant admin
    console.log('[2/3] Logging in as admin on the new tenant instance...');
    await page.fill('input#user, input[name="user"]', 'admin');
    await page.fill('input#password, input[name="password"]', 'StorixAdmin2026!Secure');
    await page.click('button#submit-form, button[type="submit"]');

    await page.waitForURL('**/apps/**', { timeout: 35000 });
    await page.waitForLoadState('networkidle');
    await sleep(3000);

    console.log(`  ✔ Logged in to Nextcloud dashboard successfully! Current URL: ${page.url()}`);
    const dashScreenshotPath = path.join(SCREENSHOTS_DIR, '34_tenant_admin_dashboard_logged_in.png');
    await page.screenshot({ path: dashScreenshotPath });
    console.log(`  📸 Saved screenshot: 34_tenant_admin_dashboard_logged_in.png`);

    console.log('\n🎉 ALL TESTS PASSED: Nextcloud auto-install succeeded, setup wizard completely eliminated!');
  } finally {
    await browser.close();
  }
}

run().catch(err => {
  console.error('❌ Verification failed:', err);
  process.exit(1);
});
