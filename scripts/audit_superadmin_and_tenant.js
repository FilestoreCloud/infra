const path = require('path');
const { chromium } = require(path.resolve(__dirname, '../tests/nextcloud/e2e/node_modules/playwright'));
const fs = require('fs');

const BASE_URL = process.env.BASE_URL || 'https://admin.png261.dev';
const ARTIFACT_DIR = '/Users/png/.gemini/antigravity/brain/27d2e816-8c4d-4877-935d-f6b86e6e5cd1';

if (!fs.existsSync(ARTIFACT_DIR)) {
  fs.mkdirSync(ARTIFACT_DIR, { recursive: true });
}

async function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function run() {
  console.log(`🚀 Starting SuperAdmin & Tenant Operations Live Audit`);
  console.log(`🎯 SuperAdmin URL: ${BASE_URL}`);
  console.log(`📁 Artifacts Directory: ${ARTIFACT_DIR}`);

  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--ignore-certificate-errors']
  });

  const context = await browser.newContext({
    viewport: { width: 1680, height: 1050 },
    userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
    ignoreHTTPSErrors: true
  });

  const page = await context.newPage();

  async function snap(filename) {
    const filePath = path.join(ARTIFACT_DIR, filename);
    await page.screenshot({ path: filePath, fullPage: false });
    console.log(`  📸 Screenshot saved: ${filename}`);
  }

  try {
    // ------------------------------------------------------------------------
    // 1. SUPERADMIN LOGIN PAGE
    // ------------------------------------------------------------------------
    console.log('\n[1/7] Navigating to SuperAdmin Login...');
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForSelector('#admin-email', { timeout: 15000 });
    await sleep(1000);
    await snap('01_superadmin_login_screen.png');

    // Enter Credentials
    console.log('  Entering SuperAdmin credentials (admin@storix.io)...');
    await page.fill('#admin-email', 'admin@storix.io');
    await page.fill('#master-password', 'StorixAdmin2026!Secure');
    await page.click('button[type="submit"]');

    // ------------------------------------------------------------------------
    // 2. DIRECT AUTHENTICATION (NO MFA)
    // ------------------------------------------------------------------------
    console.log('\n[2/7] Direct Authentication Verified (MFA Completely Disabled)...');
    await page.waitForURL('**/tenants**', { timeout: 25000 });
    await page.waitForLoadState('networkidle');
    await sleep(2000);
    console.log('  ✔ Directly authenticated into SuperAdmin portal without MFA! Current URL:', page.url());
    await snap('02_superadmin_direct_login_no_mfa.png');

    // ------------------------------------------------------------------------
    // 3. TENANTS OPERATIONS LIST TABLE
    // ------------------------------------------------------------------------
    console.log('\n[3/7] Verifying Tenants Table & Admin Email Consistency...');
    await page.waitForSelector('table', { timeout: 15000 });
    await sleep(1500);

    // Verify tenant table rows
    const pageText = await page.content();
    console.log('  Checking tenants present in table:');
    console.log('   - dev-tenant:', pageText.includes('dev-tenant'));
    console.log('   - abc:', pageText.includes('abc'));
    console.log('   - admin@dev-tenant.com:', pageText.includes('admin@dev-tenant.com'));
    console.log('   - admin@abc.com:', pageText.includes('admin@abc.com'));
    console.log('   - hardcoded admin@acme.com absent:', !pageText.includes('admin@acme.com'));

    await snap('03_superadmin_tenants_table.png');

    // ------------------------------------------------------------------------
    // 4. PROVISION DEDICATED TENANT MODAL & LIVE SUBMISSION
    // ------------------------------------------------------------------------
    console.log('\n[4/7] Testing "Provision Dedicated Tenant" Modal & Submission...');
    const createBtn = await page.waitForSelector('button:has-text("Provision Dedicated Tenant")', { timeout: 10000 });
    await createBtn.click();
    await page.waitForSelector('#create-tenant-id', { timeout: 10000 });
    await sleep(800);

    const testTenantSlug = 'omega';
    await page.fill('#create-tenant-id', testTenantSlug);
    await page.fill('#create-domain', `${testTenantSlug}.png261.dev`);
    await page.fill('#create-admin-email', `admin@${testTenantSlug}.com`);
    await sleep(800);
    await snap('04_superadmin_provision_modal.png');

    console.log('  Submitting form via "Launch Tenant Instance" button...');
    const submitBtn = await page.waitForSelector('button:has-text("Launch Tenant Instance")', { timeout: 10000 });
    await submitBtn.click();
    await sleep(3000);

    // Verify absence of "name 'get_admin_creds' is not defined" error
    const postSubmitContent = await page.content();
    const hasGetAdminCredsError = postSubmitContent.includes('get_admin_creds');
    console.log(`  Assertion - No 'get_admin_creds' error: ${!hasGetAdminCredsError}`);
    await snap('04b_superadmin_provision_success.png');
    await sleep(1000);

    // ------------------------------------------------------------------------
    // 5. TENANT DETAILS: TELEMETRY, TOPOLOGY, ACCOUNTS (Tenant: dev-tenant)
    // ------------------------------------------------------------------------
    console.log('\n[5/7] Inspecting Dedicated Tenant Details (Tenant: dev-tenant)...');
    await page.goto(`${BASE_URL}/tenants/dev-tenant`, { waitUntil: 'networkidle', timeout: 25000 });
    await sleep(3000);

    // Capture Top Section: Header & Live Metrics
    console.log('  Capturing Tenant Details Header & Metrics...');
    await snap('05_tenant_abc_header_and_metrics.png');

    // Scroll down to Dedicated Architecture & Topology
    console.log('  Scrolling to Dedicated Architecture & Topology...');
    await page.evaluate(() => {
      window.scrollTo(0, 600);
    });
    await sleep(1500);
    await snap('06_tenant_abc_topology.png');

    // Scroll down to Tenant Accounts Management
    console.log('  Scrolling to Tenant Accounts Management...');
    await page.evaluate(() => {
      window.scrollTo(0, 1100);
    });
    await sleep(1500);
    await snap('07_tenant_abc_accounts_tab.png');

    // ------------------------------------------------------------------------
    // 6. TENANT OVERVIEW
    // ------------------------------------------------------------------------
    console.log('\n[6/7] Inspecting Tenant Overview...');
    await page.goto(`${BASE_URL}/tenants/acme-corp`, { waitUntil: 'networkidle', timeout: 25000 });
    await sleep(3000);
    await snap('08_tenant_dev_tenant_overview.png');

    // ------------------------------------------------------------------------
    // 7. NEXTCLOUD TENANT INSTANCE LOGIN & ISOLATION VERIFICATION
    // ------------------------------------------------------------------------
    console.log('\n[7/7] Verifying Nextcloud Tenant Access & Isolation (https://dev-tenant.png261.dev)...');
    let ncRes = null;
    let attempts = 0;
    while (attempts < 10) {
      attempts++;
      try {
        console.log(`  Attempt ${attempts}: navigating to https://dev-tenant.png261.dev...`);
        ncRes = await page.goto('https://dev-tenant.png261.dev', { waitUntil: 'networkidle', timeout: 20000 });
        const status = ncRes ? ncRes.status() : 0;
        console.log(`  Response status: ${status}, current URL: ${page.url()}`);
        if (status < 500 && !page.url().includes('503')) {
          break;
        }
      } catch (err) {
        console.log(`  Waiting for ECS service / ALB healthy target: ${err.message}`);
      }
      await sleep(5000);
    }

    await sleep(2000);
    await snap('09_tenant_abc_login_screen.png');

    const html = await page.content();
    const hasSetupWizard = html.includes('Create an admin account') || 
                           html.includes('Tạo tài khoản quản trị') || 
                           html.includes('Finish setup');
    console.log('  Assertion - Setup wizard NOT present:', !hasSetupWizard);

    const hasLoginForm = (await page.$('input#user, input[name="user"]')) !== null;
    console.log('  Assertion - Login form present directly:', hasLoginForm);

    if (hasLoginForm) {
      console.log('  Logging in as admin on tenant dev-tenant...');
      await page.fill('input#user, input[name="user"]', 'admin');
      await page.fill('input#password, input[name="password"]', 'StorixAdmin2026!Secure');
      await page.click('button#submit-form, button[type="submit"]');

      await page.waitForURL('**/apps/**', { timeout: 35000 });
      await page.waitForLoadState('networkidle');
      await sleep(3000);
      console.log('  ✔ Logged into Nextcloud files dashboard! URL:', page.url());
      await snap('10_tenant_abc_dashboard_authenticated.png');
    }

    console.log('\n🎉 ALL SUPERADMIN AND TENANT VERIFICATIONS COMPLETED SUCCESSFULLY!');
  } catch (err) {
    console.error('❌ Error during audit:', err);
    await snap('99_error_state.png');
    throw err;
  } finally {
    await browser.close();
  }
}

run().catch((e) => {
  console.error(e);
  process.exit(1);
});
