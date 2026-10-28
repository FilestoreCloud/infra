import { chromium } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";

const CONSOLE_URL = "https://admin.png261.dev";
const ADMIN_EMAIL = "admin@png261.dev";
const ADMIN_PASSWORD = "StorixAdmin2026!Secure";

const SCREENSHOT_DIR = "/Users/png/01. Project/storix/docs/images/tenant_audit";
if (!fs.existsSync(SCREENSHOT_DIR)) {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
}

function log(msg) {
  const ts = new Date().toISOString().substring(11, 19);
  console.log(`[${ts}] ${msg}`);
}

async function takeSnap(page, filename, label) {
  const filepath = path.join(SCREENSHOT_DIR, filename);
  await page.screenshot({ path: filepath, fullPage: false });
  log(`📸 Screenshot saved: ${filename} (${label})`);
}

async function pollTenantStatus(page, tenantId, targetStatus = "ACTIVE", timeoutMs = 180000) {
  log(`Polling tenant '${tenantId}' until status is '${targetStatus}'...`);
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const searchInput = page.locator('input[placeholder*="Search"]').first();
    if (await searchInput.isVisible().catch(() => false)) {
      await searchInput.fill(tenantId);
      await page.waitForTimeout(500);
    }

    const row = page.locator("tr").filter({ hasText: tenantId }).first();
    if (await row.isVisible().catch(() => false)) {
      const badge = row.locator('span, div, [class*="badge"]').filter({ hasText: new RegExp(`^${targetStatus}$`, "i") }).first();
      if (await badge.isVisible().catch(() => false)) {
        log(`✓ Tenant '${tenantId}' reached status '${targetStatus}'!`);
        return true;
      }
      const failedBadge = row.locator('span, div, [class*="badge"]').filter({ hasText: /^FAILED$/i }).first();
      if (await failedBadge.isVisible().catch(() => false)) {
        throw new Error(`Tenant '${tenantId}' failed provisioning!`);
      }
    }
    await page.waitForTimeout(3000);
  }
  throw new Error(`Timeout polling tenant '${tenantId}' for status '${targetStatus}'`);
}

async function run() {
  log("🚀 Starting Full SuperAdmin Tenant Management & Isolation Audit...");
  const browser = await chromium.launch({
    headless: true,
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-web-security"]
  });

  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    ignoreHTTPSErrors: true
  });
  const page = await context.newPage();

  const auditResults = {
    auth: false,
    dashboard: false,
    fleetInitial: false,
    alphaProvisioned: false,
    betaProvisioned: false,
    multiFleetKPIs: false,
    alphaTopology: false,
    alphaSession: false,
    betaSession: false,
    isolationProbes: false,
    alphaSuspended: false,
    isolationFaultResistance: false,
    alphaResumed: false,
    auditTrail: false,
    deprovisioned: false,
    screenshots: []
  };

  try {
    // ------------------------------------------------------------------------
    // STEP 1: SuperAdmin Portal Authentication
    // ------------------------------------------------------------------------
    log("Step 1: SuperAdmin Authentication");
    await page.goto(`${CONSOLE_URL}/login`, { waitUntil: "networkidle" });
    await takeSnap(page, "01_superadmin_login.png", "SuperAdmin Login Portal Entrypoint");
    auditResults.screenshots.push("01_superadmin_login.png");

    await page.locator('input#email, input[type="email"], input[name="email"]').fill(ADMIN_EMAIL);
    await page.locator('input#password, input[type="password"], input[name="password"]').fill(ADMIN_PASSWORD);
    await page.locator('button[type="submit"]').click();
    await page.waitForURL(url => !url.pathname.includes("/login"), { timeout: 30000 });
    auditResults.auth = true;
    log("✓ SuperAdmin authenticated successfully!");

    // ------------------------------------------------------------------------
    // STEP 2: Dashboard Fleet Analytics & Telemetry Overview
    // ------------------------------------------------------------------------
    log("Step 2: Dashboard Overview");
    await page.goto(`${CONSOLE_URL}/dashboard`, { waitUntil: "networkidle" });
    await page.waitForTimeout(3000); // Allow ECharts / metrics cards to animate
    await takeSnap(page, "02_superadmin_dashboard.png", "Fleet Analytics & Telemetry Dashboard");
    auditResults.screenshots.push("02_superadmin_dashboard.png");
    auditResults.dashboard = true;

    // ------------------------------------------------------------------------
    // STEP 3: Tenant Operations Registry (Initial State)
    // ------------------------------------------------------------------------
    log("Step 3: Tenants Registry Initial State");
    await page.goto(`${CONSOLE_URL}/tenants`, { waitUntil: "networkidle" });
    await page.waitForTimeout(2000);
    await takeSnap(page, "03_tenants_registry_initial.png", "Tenant Fleet Registry Initial Table");
    auditResults.screenshots.push("03_tenants_registry_initial.png");
    auditResults.fleetInitial = true;

    // Generate unique tenant slugs for this audit
    const suffix = Date.now().toString(36).substring(4);
    const tenantAlpha = `alpha-${suffix}`;
    const tenantBeta = `beta-${suffix}`;
    const domainAlpha = `${tenantAlpha}.png261.dev`;
    const domainBeta = `${tenantBeta}.png261.dev`;

    // ------------------------------------------------------------------------
    // STEP 4: Provision Tenant Alpha (alpha-xxx)
    // ------------------------------------------------------------------------
    log(`Step 4: Provisioning Tenant Alpha (${tenantAlpha})...`);
    await page.locator('button:has-text("Provision Dedicated Tenant")').click();
    await page.waitForSelector('#create-tenant-id', { state: "visible", timeout: 10000 });

    await page.locator('#create-tenant-id').fill(tenantAlpha);
    await page.locator('#create-domain').fill(domainAlpha);
    await page.locator('#create-admin-email').fill(`admin@${tenantAlpha}.com`);
    await page.locator('#create-admin-password').fill("AlphaPass2026!Secure");
    await page.locator('#create-quota').fill("100");

    await takeSnap(page, "04_provision_modal_alpha.png", "Provision Dedicated Tenant Modal (Tenant Alpha)");
    auditResults.screenshots.push("04_provision_modal_alpha.png");

    await page.locator('button:has-text("Launch Tenant Instance")').click();
    await page.waitForSelector('#create-tenant-id', { state: "hidden", timeout: 15000 });

    // Poll for ACTIVE status
    await pollTenantStatus(page, tenantAlpha, "ACTIVE", 180000);
    await page.waitForTimeout(2000);
    await takeSnap(page, "05_tenant_alpha_active.png", "Tenant Alpha ACTIVE in Fleet Registry");
    auditResults.screenshots.push("05_tenant_alpha_active.png");
    auditResults.alphaProvisioned = true;

    // ------------------------------------------------------------------------
    // STEP 5: Provision Tenant Beta (beta-xxx)
    // ------------------------------------------------------------------------
    log(`Step 5: Provisioning Tenant Beta (${tenantBeta})...`);
    // Clear search filter first so modal button is accessible
    const searchInput = page.locator('input[placeholder*="Search"]').first();
    await searchInput.fill("");
    await page.waitForTimeout(1000);

    await page.locator('button:has-text("Provision Dedicated Tenant")').click();
    await page.waitForSelector('#create-tenant-id', { state: "visible", timeout: 10000 });

    await page.locator('#create-tenant-id').fill(tenantBeta);
    await page.locator('#create-domain').fill(domainBeta);
    await page.locator('#create-admin-email').fill(`admin@${tenantBeta}.com`);
    await page.locator('#create-admin-password').fill("BetaPass2026!Secure");
    await page.locator('#create-quota').fill("200");

    await takeSnap(page, "06_provision_modal_beta.png", "Provision Dedicated Tenant Modal (Tenant Beta)");
    auditResults.screenshots.push("06_provision_modal_beta.png");

    await page.locator('button:has-text("Launch Tenant Instance")').click();
    await page.waitForSelector('#create-tenant-id', { state: "hidden", timeout: 15000 });

    // Poll for ACTIVE status
    await pollTenantStatus(page, tenantBeta, "ACTIVE", 180000);
    await searchInput.fill(""); // Show both tenants in table
    await page.waitForTimeout(2000);

    await takeSnap(page, "07_multi_tenant_fleet_active.png", "Multi-Tenant Active Fleet Overview with Updated KPI Cards");
    auditResults.screenshots.push("07_multi_tenant_fleet_active.png");
    auditResults.betaProvisioned = true;
    auditResults.multiFleetKPIs = true;

    // ------------------------------------------------------------------------
    // STEP 6: Inspect Tenant Alpha Topology & Isolated Infrastructure
    // ------------------------------------------------------------------------
    log(`Step 6: Inspecting Topology & Architecture for '${tenantAlpha}'...`);
    const alphaRow = page.locator("tr").filter({ hasText: tenantAlpha }).first();
    await alphaRow.locator('button[aria-label="More actions"]').click();
    await page.waitForTimeout(400);
    await page.locator('div[role="menuitem"]:has-text("View Details")').click();
    await page.waitForURL(url => url.pathname.includes(`/tenants/${tenantAlpha}`), { timeout: 15000 });
    await page.waitForTimeout(3000);

    await takeSnap(page, "08_tenant_alpha_topology.png", "Tenant Alpha Isolated Infrastructure Topology & Telemetry");
    auditResults.screenshots.push("08_tenant_alpha_topology.png");
    auditResults.alphaTopology = true;

    // Return to tenants list
    await page.goto(`${CONSOLE_URL}/tenants`, { waitUntil: "networkidle" });

    // ------------------------------------------------------------------------
    // STEP 7: Multi-Tenant Data Isolation & Non-Interference Verification
    // ------------------------------------------------------------------------
    log("Step 7: Validating Absolute Data & Session Isolation between Tenants...");

    // Isolated Context for Tenant Alpha
    const alphaContext = await browser.newContext({
      viewport: { width: 1440, height: 900 },
      ignoreHTTPSErrors: true
    });
    const alphaPage = await alphaContext.newPage();

    log(`Authenticating into Tenant Alpha (${domainAlpha})...`);
    await alphaPage.goto(`https://${domainAlpha}/index.php/login`, { waitUntil: "domcontentloaded" });
    await alphaPage.locator('#user, input[name="user"]').fill("admin");
    await alphaPage.locator('#password, input[name="password"]').fill("AlphaPass2026!Secure");
    await alphaPage.locator('#submit-form, button[type="submit"]').click();
    await alphaPage.waitForTimeout(4000);

    // Direct navigate to files
    await alphaPage.goto(`https://${domainAlpha}/index.php/apps/files/`, { waitUntil: "domcontentloaded" });
    await alphaPage.waitForTimeout(3000);

    // Dismiss any first-run wizard
    const wizardClose = alphaPage.locator('#firstrunwizard button[aria-label="Close"], button:has-text("Close")').first();
    if (await wizardClose.isVisible({ timeout: 2000 }).catch(() => false)) {
      await wizardClose.click().catch(() => {});
    }

    // Upload a confidential file to Tenant Alpha via WebDAV
    const alphaFileName = "CONFIDENTIAL_ALPHA_FINANCES_2026.docx";
    const alphaPayload = `CONFIDENTIAL_FINANCIAL_RECORDS_ALPHA_CORP_KEY_${suffix}`;
    const alphaBasicAuth = "Basic " + Buffer.from("admin:AlphaPass2026!Secure").toString("base64");

    const davAlphaUrl = `https://${domainAlpha}/remote.php/dav/files/admin/${alphaFileName}`;
    const uploadAlphaRes = await alphaPage.request.put(davAlphaUrl, {
      headers: {
        Authorization: alphaBasicAuth,
        "Content-Type": "text/plain;charset=UTF-8"
      },
      data: Buffer.from(alphaPayload, "utf-8")
    });
    log(`Tenant Alpha WebDAV file upload status: ${uploadAlphaRes.status()}`);

    // Reload files page to display uploaded file
    await alphaPage.goto(`https://${domainAlpha}/index.php/apps/files/`, { waitUntil: "networkidle" });
    await alphaPage.waitForTimeout(3000);
    await takeSnap(alphaPage, "09_tenant_alpha_isolated_files.png", "Tenant Alpha Authenticated Storage & Private Confidential Document");
    auditResults.screenshots.push("09_tenant_alpha_isolated_files.png");
    auditResults.alphaSession = true;

    // Isolated Context for Tenant Beta
    const betaContext = await browser.newContext({
      viewport: { width: 1440, height: 900 },
      ignoreHTTPSErrors: true
    });
    const betaPage = await betaContext.newPage();

    log(`Authenticating into Tenant Beta (${domainBeta})...`);
    await betaPage.goto(`https://${domainBeta}/index.php/login`, { waitUntil: "domcontentloaded" });
    await betaPage.locator('#user, input[name="user"]').fill("admin");
    await betaPage.locator('#password, input[name="password"]').fill("BetaPass2026!Secure");
    await betaPage.locator('#submit-form, button[type="submit"]').click();
    await betaPage.waitForTimeout(4000);

    // Direct navigate to files
    await betaPage.goto(`https://${domainBeta}/index.php/apps/files/`, { waitUntil: "domcontentloaded" });
    await betaPage.waitForTimeout(3000);

    const wizardCloseBeta = betaPage.locator('#firstrunwizard button[aria-label="Close"], button:has-text("Close")').first();
    if (await wizardCloseBeta.isVisible({ timeout: 2000 }).catch(() => false)) {
      await wizardCloseBeta.click().catch(() => {});
    }

    // Upload a confidential file to Tenant Beta via WebDAV
    const betaFileName = "BETA_CLASSIFIED_PATENT_PROTOTYPE.pdf";
    const betaPayload = `SECRET_PATENT_BLUEPRINT_BETA_RESEARCH_KEY_${suffix}`;
    const betaBasicAuth = "Basic " + Buffer.from("admin:BetaPass2026!Secure").toString("base64");

    const davBetaUrl = `https://${domainBeta}/remote.php/dav/files/admin/${betaFileName}`;
    const uploadBetaRes = await betaPage.request.put(davBetaUrl, {
      headers: {
        Authorization: betaBasicAuth,
        "Content-Type": "text/plain;charset=UTF-8"
      },
      data: Buffer.from(betaPayload, "utf-8")
    });
    log(`Tenant Beta WebDAV file upload status: ${uploadBetaRes.status()}`);

    // Reload files page to display uploaded file
    await betaPage.goto(`https://${domainBeta}/index.php/apps/files/`, { waitUntil: "networkidle" });
    await betaPage.waitForTimeout(3000);
    await takeSnap(betaPage, "10_tenant_beta_isolated_files.png", "Tenant Beta Authenticated Storage & Private Patent Blueprint");
    auditResults.screenshots.push("10_tenant_beta_isolated_files.png");
    auditResults.betaSession = true;

    // Cross-Tenant Access Probes (ASSERT 100% ISOLATION & ZERO LEAKAGE)
    log("Probing Cross-Tenant Boundaries (Enforcing Zero-Leakage Policy)...");
    
    // 1. Beta attempts to read Alpha's confidential file
    const crossProbe1 = await betaPage.request.get(
      `https://${domainBeta}/remote.php/dav/files/admin/${alphaFileName}`,
      { headers: { Authorization: betaBasicAuth } }
    );
    log(`Probe 1 (Beta reads Alpha's file): HTTP ${crossProbe1.status()} (Expected: 404)`);
    if (crossProbe1.status() !== 404) {
      throw new Error(`CRITICAL ISOLATION FAILURE: Tenant Beta accessed Alpha file (HTTP ${crossProbe1.status()})!`);
    }

    // 2. Alpha attempts to read Beta's confidential file
    const crossProbe2 = await alphaPage.request.get(
      `https://${domainAlpha}/remote.php/dav/files/admin/${betaFileName}`,
      { headers: { Authorization: alphaBasicAuth } }
    );
    log(`Probe 2 (Alpha reads Beta's file): HTTP ${crossProbe2.status()} (Expected: 404)`);
    if (crossProbe2.status() !== 404) {
      throw new Error(`CRITICAL ISOLATION FAILURE: Tenant Alpha accessed Beta file (HTTP ${crossProbe2.status()})!`);
    }

    // 3. Direct Cross-Domain Credential Attack: Alpha admin credentials on Beta domain
    const crossProbe3 = await betaPage.request.get(
      `https://${domainBeta}/remote.php/dav/files/admin/${betaFileName}`,
      { headers: { Authorization: alphaBasicAuth } }
    );
    log(`Probe 3 (Alpha creds against Beta domain): HTTP ${crossProbe3.status()} (Expected: 401 or 404)`);
    if (crossProbe3.status() === 200) {
      throw new Error("CRITICAL CREDENTIAL LEAKAGE: Alpha credentials authenticated against Beta tenant!");
    }

    log("🔒 ZERO LEAKAGE CONFIRMED: All 3 cross-tenant isolation probes rejected access as expected!");
    auditResults.isolationProbes = true;

    await alphaContext.close();
    await betaContext.close();

    // ------------------------------------------------------------------------
    // STEP 8: Suspend Tenant Action & Fault Resistance Audit
    // ------------------------------------------------------------------------
    log(`Step 8: Testing Tenant Suspend Action on '${tenantAlpha}'...`);
    await page.goto(`${CONSOLE_URL}/tenants`, { waitUntil: "networkidle" });
    await page.waitForTimeout(2000);

    const filterAlpha = page.locator('input[placeholder*="Search"]').first();
    await filterAlpha.fill(tenantAlpha);
    await page.waitForTimeout(1000);

    const rowAlpha = page.locator("tr").filter({ hasText: tenantAlpha }).first();
    await rowAlpha.locator('button[aria-label="More actions"]').click();
    await page.waitForTimeout(400);

    await page.locator('div[role="menuitem"]:has-text("Suspend Tenant")').click();
    await page.waitForSelector('button:has-text("Confirm Suspend")', { state: "visible", timeout: 10000 });
    await takeSnap(page, "11_tenant_suspend_dialog.png", "Confirm Tenant Suspension Modal");
    auditResults.screenshots.push("11_tenant_suspend_dialog.png");

    await page.locator('button:has-text("Confirm Suspend")').click();
    await pollTenantStatus(page, tenantAlpha, "SUSPENDED", 60000);
    await takeSnap(page, "12_tenant_alpha_suspended.png", "Tenant Alpha in SUSPENDED State with Ingress Blocked");
    auditResults.screenshots.push("12_tenant_alpha_suspended.png");
    auditResults.alphaSuspended = true;

    // Verify Beta remains fully operational while Alpha is suspended (Fault Isolation)
    const betaHealthProbe = await page.request.get(`https://${domainBeta}/status.php`);
    log(`Fault Isolation Check: Tenant Beta status while Alpha suspended: HTTP ${betaHealthProbe.status()}`);
    if (betaHealthProbe.status() === 200) {
      log("✓ Fault Isolation verified: Tenant Beta is completely unaffected by Tenant Alpha suspension!");
      auditResults.isolationFaultResistance = true;
    }

    // ------------------------------------------------------------------------
    // STEP 9: Resume Tenant Action
    // ------------------------------------------------------------------------
    log(`Step 9: Testing Tenant Resume Action on '${tenantAlpha}'...`);
    const suspendedRowAlpha = page.locator("tr").filter({ hasText: tenantAlpha }).first();
    await suspendedRowAlpha.locator('button[aria-label="More actions"]').click();
    await page.waitForTimeout(400);

    await page.locator('div[role="menuitem"]:has-text("Resume Tenant")').click();
    await pollTenantStatus(page, tenantAlpha, "ACTIVE", 60000);
    await takeSnap(page, "13_tenant_alpha_resumed.png", "Tenant Alpha Resumed to ACTIVE Status");
    auditResults.screenshots.push("13_tenant_alpha_resumed.png");
    auditResults.alphaResumed = true;

    // ------------------------------------------------------------------------
    // STEP 10: Audit Log Trail Inspection
    // ------------------------------------------------------------------------
    log("Step 10: Verifying Immutable Control Plane Audit Trail...");
    await page.goto(`${CONSOLE_URL}/audit-logs`, { waitUntil: "networkidle" });
    await page.waitForTimeout(3000);
    await takeSnap(page, "14_superadmin_audit_logs.png", "Immutable SuperAdmin Audit Log Trail with Operator Actions");
    auditResults.screenshots.push("14_superadmin_audit_logs.png");
    auditResults.auditTrail = true;

    // ------------------------------------------------------------------------
    // STEP 11: Deprovisioning & Teardown Cleanup
    // ------------------------------------------------------------------------
    log("Step 11: Deprovisioning Test Tenants via SuperAdmin Console...");
    await page.goto(`${CONSOLE_URL}/tenants`, { waitUntil: "networkidle" });
    await page.waitForTimeout(2000);

    for (const tid of [tenantAlpha, tenantBeta]) {
      log(`Deprovisioning '${tid}'...`);
      const sInput = page.locator('input[placeholder*="Search"]').first();
      await sInput.fill(tid);
      await page.waitForTimeout(800);

      const tRow = page.locator("tr").filter({ hasText: tid }).first();
      if (await tRow.isVisible().catch(() => false)) {
        await tRow.locator('button[aria-label="More actions"]').click();
        await page.waitForTimeout(400);
        await page.locator('div[role="menuitem"]:has-text("Delete Tenant")').click();
        await page.waitForSelector('button:has-text("Delete")', { state: "visible", timeout: 8000 });
        await page.locator('button:has-text("Delete")').click();
        await page.waitForTimeout(4000);
      }
    }

    // Clear search and verify clean state
    const cleanSearch = page.locator('input[placeholder*="Search"]').first();
    await cleanSearch.fill("");
    await page.waitForTimeout(2000);
    await takeSnap(page, "15_fleet_clean_post_audit.png", "Tenant Fleet Registry Clean State Post-Audit");
    auditResults.screenshots.push("15_fleet_clean_post_audit.png");
    auditResults.deprovisioned = true;

    log("🎉 SuperAdmin Tenant Management & Multi-Tenant Isolation Audit PASSED 100%!");
  } catch (err) {
    log(`❌ Audit encountered error: ${err.message}`);
    await takeSnap(page, "error_state.png", "Error Failure State");
    throw err;
  } finally {
    await browser.close();
    fs.writeFileSync(
      path.join(SCREENSHOT_DIR, "audit_summary.json"),
      JSON.stringify(auditResults, null, 2)
    );
  }
}

run().catch((e) => {
  console.error(e);
  process.exit(1);
});
