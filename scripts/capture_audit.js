const path = require('path');
const { chromium } = require(path.resolve(__dirname, '../tests/nextcloud/e2e/node_modules/playwright'));

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1680, height: 1050 } });
  
  page.on('console', msg => console.log('BROWSER_LOG:', msg.text()));
  page.on('pageerror', err => console.log('PAGE_ERROR:', err.message));

  await page.goto('https://d193xac66yp6w4.cloudfront.net/login', { waitUntil: 'networkidle' });
  await page.fill('input[placeholder="admin@example.com"]', 'admin@storix.io');
  await page.fill('input[type="password"]', 'StorixAdmin2026!Secure');
  await page.click('button[type="submit"]');
  await page.waitForURL('**/tenants**', { timeout: 15000 });
  await page.waitForLoadState('networkidle');

  console.log('Clicking on Cloud Audit Trail menu item...');
  const auditLink = await page.waitForSelector('text="Cloud Audit Trail"', { timeout: 10000 });
  await auditLink.click();
  await page.waitForURL('**/audit-logs**', { timeout: 15000 });
  await page.waitForLoadState('networkidle');
  await new Promise(r => setTimeout(r, 3000));

  await page.screenshot({ path: '/Users/png/.gemini/antigravity/brain/48cd64b8-afb9-4783-b047-599310494447/screenshots/13_superadmin_audit_logs.png' });
  console.log('✔ Audit log screenshot saved successfully!');
  await browser.close();
})();
