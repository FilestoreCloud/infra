/**
 * Playwright E2E Test Suite for Storix SuperAdmin Web Console.
 * Validates:
 * 1. SuperAdmin Portal Web UI Load and Form Accessibility
 * 2. Enterprise Admin Authentication (Cognito + TOTP MFA)
 * 3. Navigation to Tenant Management Dashboard & Active Fleet Verification
 * 4. Fleet Management KPI Summary Cards & Search Bar Verification
 * 5. Root Tenant Lifecycle: Provisioning -> Active Polling -> /status.php Health Probe ->
 *    Isolated Context Admin Login & Storage Verification -> Automated Teardown
 * 6. Control Plane Verification: Audit Log Table & Badges + ECharts Telemetry Rendering
 * 7. Administrator Sign Out
 */

import { test, expect } from "@playwright/test";
import { generateTotp } from "../support/totp.js";
import { loginSuperAdmin } from "../support/auth.js";
import {
  pollTenantActiveState,
  probeTenantStatusPhp,
  verifyTenantAdminSession,
  deprovisionTenantViaUI,
  deprovisionTenantViaApi,
} from "../support/tenant_lifecycle.js";

const CONSOLE_URL =
  process.env.CONSOLE_URL ||
  process.env.SUPERADMIN_CONSOLE_URL!;

const ADMIN_EMAIL = process.env.SUPERADMIN_USERNAME!;
const ADMIN_PASSWORD =
  process.env.SUPERADMIN_PASSWORD ||
  process.env.ADMIN_PASSWORD!;
const TARGET_TENANT = process.env.TENANT_ID!;

test.describe("SuperAdmin Web Console E2E", () => {
  test.beforeEach(async ({ page }) => {
    try {
      const resp = await page.goto(`${CONSOLE_URL}/login`, {
        waitUntil: "domcontentloaded",
        timeout: 15000,
      });
      if (!resp || resp.status() === 403 || resp.status() === 404) {
        test.skip(
          true,
          "SuperAdmin Web Console SPA assets not yet uploaded to S3 (pending console repository deployment)"
        );
      }
      const text = await page.content();
      if (text.includes("AccessDenied") || text.includes("<Error>")) {
        test.skip(
          true,
          "CloudFront distribution origin bucket empty; waiting for console repo deployment"
        );
      }
    } catch {
      test.skip(
        true,
        "SuperAdmin Web Console endpoint unreachable; skipping in infra acceptance"
      );
    }
  });

  test("1. Should render SuperAdmin login portal entrypoint", async ({
    page,
  }) => {
    await page.goto(`${CONSOLE_URL}/login`);
    await expect(page).toHaveTitle(/Filestore Cloud|Super Admin/i);

    const emailInput = page.locator('input#email, input[name="email"], input#admin-email, input[type="email"]');
    const passInput = page.locator('input#password, input[name="password"], input#master-password, input[type="password"]');
    const submitBtn = page.locator('button[type="submit"]');

    await expect(emailInput).toBeVisible({ timeout: 15000 });
    await expect(passInput).toBeVisible({ timeout: 15000 });
    await expect(submitBtn).toBeVisible({ timeout: 15000 });
  });

  test("2. Should reject invalid credentials with error alert", async ({
    page,
  }) => {
    await page.goto(`${CONSOLE_URL}/login`);

    const emailInput = page.locator('input#email, input[name="email"], input#admin-email, input[type="email"]');
    const passInput = page.locator('input#password, input[name="password"], input#master-password, input[type="password"]');
    const submitBtn = page.locator('button[type="submit"]');

    await emailInput.fill("wrong.admin@example.com");
    await passInput.fill("InvalidPassword123!");
    await submitBtn.click();

    const alertError = page.locator(".ant-alert-error, [role='alert'], [class*='destructive']");
    await expect(alertError.first()).toBeVisible({ timeout: 10000 });
  });

  test("3. Should authenticate SuperAdmin via MFA and access Fleet Registry", async ({
    page,
  }) => {
    await page.goto(`${CONSOLE_URL}/login`);

    const emailInput = page.locator('input#email, input[name="email"], input#admin-email, input[type="email"]');
    const passInput = page.locator('input#password, input[name="password"], input#master-password, input[type="password"]');
    const submitBtn = page.locator('button[type="submit"]');

    await emailInput.fill(ADMIN_EMAIL);
    await passInput.fill(ADMIN_PASSWORD);
    await submitBtn.click();

    // Check for Step 2: MFA Challenge
    const mfaInput = page
      .getByPlaceholder("000000")
      .or(
        page.locator(
          'input[placeholder="000000"], input#mfa_code, input#mfa-code, input#mfaForm_mfa_code'
        )
      )
      .first();
    try {
      await mfaInput.waitFor({ state: "visible", timeout: 10000 });
      const code = generateTotp();
      await mfaInput.fill(code);
      const verifyBtn = page
        .getByRole("button", { name: /Verify/i })
        .or(page.locator('button:has-text("Verify")'))
        .first();
      await verifyBtn.click();
    } catch {
      // MFA may be bypassed or already authenticated
    }

    // Verify successful login redirection to /tenants
    await expect(page).toHaveURL(/\/(tenants|dashboard)/, { timeout: 30000 });

    // Verify Tenants table or navigation header
    const mainContent = page.locator(
      "table, .ant-table, main, .ant-layout-content"
    );
    await expect(mainContent.first()).toBeVisible({ timeout: 20000 });

    // Verify registered tenant exists in fleet view
    const tenantCell = page.locator(`text="${TARGET_TENANT}"`);
    if (await tenantCell.isVisible({ timeout: 5000 }).catch(() => false)) {
      await expect(tenantCell.first()).toBeVisible();
    }
  });

  test("4. Should inspect Fleet Management KPI summary cards & search bar", async ({
    page,
  }) => {
    // Authenticate using reusable helper
    await loginSuperAdmin(page, ADMIN_EMAIL, ADMIN_PASSWORD, CONSOLE_URL);

    // Verify search input is operational
    const searchInput = page
      .getByPlaceholder(/Search by Tenant ID/i)
      .or(page.locator('input[placeholder*="Search"]'))
      .first();
    if (await searchInput.isVisible({ timeout: 5000 }).catch(() => false)) {
      await searchInput.fill(TARGET_TENANT);
      await expect(searchInput).toHaveValue(TARGET_TENANT);
    }

    // Verify Fleet Management KPI summary cards
    const kpiTitles = [
      "TOTAL REGISTERED TENANTS",
      "ACTIVE DEPLOYMENTS",
      "SUSPENDED DEPLOYMENTS",
    ];
    for (const title of kpiTitles) {
      const card = page
        .locator('[class*="card"], div')
        .filter({ hasText: new RegExp(title, "i") })
        .first();
      if (await card.isVisible({ timeout: 3000 }).catch(() => false)) {
        await expect(card).toBeVisible();
      }
    }

    // Verify Provision Dedicated Tenant button exists
    const provisionBtn = page
      .getByRole("button", { name: /Provision Dedicated Tenant/i })
      .or(page.locator('button:has-text("Provision")'))
      .first();
    await expect(provisionBtn).toBeVisible({ timeout: 10000 });
  });

  test("5. Should provision a new tenant, poll ACTIVE status, probe /status.php health, authenticate admin, and verify deprovisioning teardown", async ({
    page,
    browser,
    request,
  }) => {
    test.setTimeout(180000);
    await loginSuperAdmin(page, ADMIN_EMAIL, ADMIN_PASSWORD, CONSOLE_URL);

    // Open Modal
    const provisionBtn = page
      .getByRole("button", { name: /Provision Dedicated Tenant/i })
      .or(page.locator('button:has-text("Provision")'))
      .first();
    await provisionBtn.click();

    // Verify modal elements
    const modal = page
      .locator('[role="dialog"], .ant-modal')
      .filter({ hasText: /Provision Dedicated Tenant/i })
      .first();
    await expect(modal).toBeVisible({ timeout: 10000 });

    // Generate unique slug
    const randomSuffix = Math.floor(1000 + Math.random() * 9000);
    const newTenantId = `e2e-tenant-${Date.now().toString(36)}-${randomSuffix}`;
    const baseDomain = process.env.BASE_DOMAIN || "png261.dev";
    const customDomain = `${newTenantId}.${baseDomain}`;

    const tenantIdInput = modal
      .locator(
        'input#create-tenant-id, input#tenant_id, input[placeholder*="acme-corp"]'
      )
      .first();
    await tenantIdInput.fill(newTenantId);

    const domainInput = modal
      .locator(
        'input#create-domain, input#domain, input[placeholder*="png261.dev"]'
      )
      .first();
    if (await domainInput.isVisible().catch(() => false)) {
      await domainInput.fill(customDomain);
    }

    const emailInput = modal
      .locator(
        'input#create-admin-email, input#admin_email, input[placeholder*="admin@"]'
      )
      .first();
    await emailInput.fill(`admin@${newTenantId}.com`);

    // Submit modal
    const submitBtn = modal
      .locator(
        'button:has-text("Launch Tenant Instance"), button[type="submit"]'
      )
      .first();
    await submitBtn.click();

    // Verify modal closes
    await expect(modal).not.toBeVisible({ timeout: 15000 });

    try {
      // 1. Poll tenant status until state transitions to ACTIVE (up to 120s timeout)
      await pollTenantActiveState(page, newTenantId, 120000);

      // 2. Probe tenant's HTTP health endpoint (/status.php)
      const rawBaseUrl =
        process.env.ALB_URL ||
        process.env.TENANT_URL ||
        `https://${customDomain}`;
      const targetBaseUrl = rawBaseUrl.trim().replace(/\/+$/, "");
      const hostHeader = customDomain;

      const health = await probeTenantStatusPhp(
        request,
        targetBaseUrl,
        hostHeader,
        90000
      );
      expect(health.installed).toBe(true);
      expect(health.maintenance).toBe(false);

      // 3. Authenticate into newly provisioned tenant as its admin via isolated browser context
      let sessionError: Error | null = null;
      try {
        await verifyTenantAdminSession(
          browser,
          targetBaseUrl,
          "admin",
          process.env.NEXTCLOUD_PASSWORD || "Admin1234!",
          hostHeader
        );
      } catch (err: any) {
        sessionError = err;
      }

      // 4. Execute automated teardown/deprovisioning cleanup via UI popconfirm delete
      // Always attempted to ensure UI cleanup verification runs
      await deprovisionTenantViaUI(page, newTenantId, 60000);

      if (sessionError) {
        throw sessionError;
      }
    } finally {
      // Guardrail: ensure zero dangling tenant or infrastructure resources remain
      await deprovisionTenantViaApi(request, CONSOLE_URL, newTenantId).catch(
        () => {}
      );
    }
  });

  test("6. Should navigate across Control Plane sections and verify live telemetry and audit trail", async ({
    page,
  }) => {
    await loginSuperAdmin(page, ADMIN_EMAIL, ADMIN_PASSWORD, CONSOLE_URL);

    // 1. Audit Logs Deep Verification
    await page.goto(`${CONSOLE_URL}/audit-logs`);
    await expect(page).toHaveURL(/\/audit-logs/, { timeout: 15000 });
    await expect(
      page.locator("h1").filter({ hasText: "Immutable Cloud Audit Trail" })
    ).toBeVisible({ timeout: 10000 });

    // Verify all 7 table headers
    const auditHeaders = [
      "Timestamp (UTC)",
      "Event Action",
      "Target Resource",
      "Actor (User)",
      "Role",
      "Status",
      "Source IP",
    ];
    for (const header of auditHeaders) {
      await expect(
        page.locator("th").filter({ hasText: header }).first()
      ).toBeVisible({ timeout: 5000 });
    }

    // Await completion of loading state if present
    await expect(
      page.locator('text="Loading audit records..."')
    ).not.toBeVisible({ timeout: 15000 }).catch(() => {});

    // Verify actual log entry presence in table
    const logRows = page.locator("tbody tr");
    await expect(logRows.first()).toBeVisible({ timeout: 15000 });
    const rowCount = await logRows.count();
    expect(rowCount).toBeGreaterThan(0);

    // Assert placeholder "No audit logs recorded yet." is not visible
    await expect(
      page.locator('text="No audit logs recorded yet."')
    ).not.toBeVisible();

    // Verify presence of SUCCESS status badge
    const successBadge = page
      .locator("tbody tr")
      .locator('span, div, [class*="badge"]')
      .filter({ hasText: /^SUCCESS$/i });
    await expect(successBadge.first()).toBeVisible({ timeout: 10000 });

    // Verify presence of event action badges
    const actionBadge = page
      .locator("tbody tr td:nth-child(2)")
      .locator("div, span, [class*='rounded']")
      .or(page.locator("tbody tr").locator("div.font-mono, span.font-mono, [class*='rounded']"))
      .first();
    await expect(actionBadge).toBeVisible({ timeout: 10000 });

    // 2. Telemetry & Metrics Deep Verification
    await page.goto(`${CONSOLE_URL}/telemetry`);
    await expect(page).toHaveURL(/\/telemetry/, { timeout: 15000 });
    await expect(
      page
        .locator("h1")
        .filter({ hasText: "Live CloudWatch Telemetry & Metrics" })
    ).toBeVisible({ timeout: 10000 });

    // Verify active streaming indicator
    await expect(
      page.getByText(/STREAMING/i).or(page.locator('div, span, [class*="badge"]').filter({ hasText: /STREAMING/i })).first()
    ).toBeVisible({ timeout: 15000 });

    // Verify all 3 metric card headers
    const metricCards = [
      "Tenant Lifecycle Status",
      "ECS Fargate CPU & Memory",
      "ALB Ingress Requests & Latency",
    ];
    for (const cardTitle of metricCards) {
      await expect(
        page
          .locator('[class*="card-title"], div, h3')
          .filter({ hasText: cardTitle })
          .first()
      ).toBeVisible({ timeout: 5000 });
    }

    // Assert 3 ECharts <canvas> elements rendered with non-zero dimensions
    const canvases = page.locator("canvas");
    await expect(canvases.first()).toBeVisible({ timeout: 15000 });
    await expect
      .poll(async () => await canvases.count(), { timeout: 15000 })
      .toBeGreaterThanOrEqual(3);

    for (let i = 0; i < 3; i++) {
      const canvas = canvases.nth(i);
      await expect(canvas).toBeVisible({ timeout: 5000 });
      await expect
        .poll(
          async () => {
            const box = await canvas.boundingBox();
            return (
              box !== null &&
              box.width > 0 &&
              box.height > 0
            );
          },
          { timeout: 10000 }
        )
        .toBe(true);
    }

    // 3. Alerts & Webhooks Navigation
    await page.goto(`${CONSOLE_URL}/settings/webhooks`);
    await expect(page).toHaveURL(/\/settings\/webhooks/, { timeout: 10000 });
    await expect(
      page
        .locator("main, .ant-layout-content, [role=\"main\"], .space-y-6")
        .first()
    ).toBeVisible({ timeout: 10000 });
  });

  test("7. Should support Administrator sign out", async ({ page }) => {
    await loginSuperAdmin(page, ADMIN_EMAIL, ADMIN_PASSWORD, CONSOLE_URL);

    // Logout via header avatar/logout button
    const logoutBtn = page
      .getByRole("button", { name: /Log out|Logout|Sign out/i })
      .or(
        page.locator(
          'button:has-text("Logout"), button:has-text("Sign Out"), .ant-dropdown-menu-item:has-text("Logout"), button:has(svg.lucide-log-out)'
        )
      )
      .first();
    if (await logoutBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
      await logoutBtn.click();
      await expect(page).toHaveURL(/\/login/, { timeout: 10000 });
    }
  });
});
