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
  console.log(`🚀 Verifying Live Metrics & Telemetry on: ${BASE_URL}`);
  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
  const context = await browser.newContext({
    viewport: { width: 1680, height: 1050 },
    userAgent: 'Storix-Metrics-Auditor/1.0'
  });
  const page = await context.newPage();

  async function snap(filename) {
    const filePath = path.join(SCREENSHOTS_DIR, filename);
    await page.screenshot({ path: filePath, fullPage: false });
    console.log(`  📸 Saved screenshot: ${filename}`);
  }

  try {
    console.log('[1/3] Logging in...');
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForSelector('input[placeholder="admin@example.com"]', { timeout: 15000 });
    await page.fill('input[placeholder="admin@example.com"]', 'admin@storix.io');
    await page.fill('input[type="password"]', 'StorixAdmin2026!Secure');
    await page.click('button[type="submit"]');

    await page.waitForURL('**/tenants**', { timeout: 25000 });
    await page.waitForLoadState('networkidle');
    await sleep(2000);
    console.log('  ✔ Authenticated successfully');

    console.log('[2/3] Opening Tenant Show Metrics Tab (tenant: test)...');
    await page.goto(`${BASE_URL}/tenants/show/test?tab=metrics`, { waitUntil: 'networkidle', timeout: 30000 });
    await sleep(3500);

    // Look for canvas or chart element
    await page.waitForSelector('canvas', { timeout: 15000 });
    console.log('  ✔ Canvas chart detected and rendered');

    // Wait a couple seconds to see streaming countdown
    await sleep(2000);
    await snap('18_tenant_metrics_live_updated.png');

    console.log('[3/3] Opening Fleet Live Telemetry (/telemetry)...');
    await page.goto(`${BASE_URL}/telemetry`, { waitUntil: 'networkidle', timeout: 30000 });
    await sleep(3000);
    await snap('19_fleet_telemetry_live.png');

    console.log('🎉 Verification complete!');
  } catch (err) {
    console.error('❌ Verification failed:', err);
    try {
      await snap('error_metrics_verification.png');
    } catch (_) {}
    process.exit(1);
  } finally {
    await browser.close();
  }
}

run();
