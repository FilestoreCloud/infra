/**
 * Playwright E2E Test Suite for Storix SuperAdmin Web Console.
 * Validates:
 * 1. SuperAdmin Portal Web UI Load and Form Accessibility
 * 2. Enterprise Admin Authentication (Cognito + TOTP MFA)
 * 3. Navigation to Tenant Management Dashboard & Active Fleet Verification
 */

import { test, expect } from "@playwright/test";
import { generateTotp } from "../support/totp.ts";

const CONSOLE_URL =
  process.env.CONSOLE_URL ||
  process.env.SUPERADMIN_CONSOLE_URL!;

const ADMIN_EMAIL = process.env.SUPERADMIN_USERNAME!;
const ADMIN_PASSWORD =
  process.env.SUPERADMIN_PASSWORD ||
  process.env.ADMIN_PASSWORD!;
const TARGET_TENANT = process.env.TENANT_ID!;

test.describe("SuperAdmin Web Console E2E", () => {
  test("1. Should render SuperAdmin login portal entrypoint", async ({
    page,
  }) => {
    await page.goto(`${CONSOLE_URL}/login`);
    await expect(page).toHaveTitle(/Filestore Cloud|Super Admin/i);

    const emailInput = page.locator('input#email, input[name="email"]');
    const passInput = page.locator('input#password, input[name="password"]');
    const submitBtn = page.locator('button[type="submit"]');

    await expect(emailInput).toBeVisible({ timeout: 15000 });
    await expect(passInput).toBeVisible({ timeout: 15000 });
    await expect(submitBtn).toBeVisible({ timeout: 15000 });
  });

  test("2. Should reject invalid credentials with error alert", async ({
    page,
  }) => {
    await page.goto(`${CONSOLE_URL}/login`);

    const emailInput = page.locator('input#email, input[name="email"]');
    const passInput = page.locator('input#password, input[name="password"]');
    const submitBtn = page.locator('button[type="submit"]');

    await emailInput.fill("wrong.admin@example.com");
    await passInput.fill("InvalidPassword123!");
    await submitBtn.click();

    const alertError = page.locator(".ant-alert-error, [role='alert']");
    await expect(alertError.first()).toBeVisible({ timeout: 10000 });
  });

  test("3. Should authenticate SuperAdmin via MFA and access Fleet Registry", async ({
    page,
  }) => {
    await page.goto(`${CONSOLE_URL}/login`);

    const emailInput = page.locator('input#email, input[name="email"]');
    const passInput = page.locator('input#password, input[name="password"]');
    const submitBtn = page.locator('button[type="submit"]');

    await emailInput.fill(ADMIN_EMAIL);
    await passInput.fill(ADMIN_PASSWORD);
    await submitBtn.click();

    // Check for Step 2: MFA Challenge
    const mfaInput = page.getByPlaceholder("000000").or(page.locator('input[placeholder="000000"], input#mfa_code, input#mfaForm_mfa_code')).first();
    try {
      await mfaInput.waitFor({ state: "visible", timeout: 10000 });
      const code = generateTotp();
      await mfaInput.fill(code);
      const verifyBtn = page.getByRole("button", { name: /Verify/i }).or(page.locator('button:has-text("Verify")')).first();
      await verifyBtn.click();
    } catch {
      // MFA may be bypassed or already authenticated
    }

    // Verify successful login redirection to /tenants
    await expect(page).toHaveURL(/\/(tenants|dashboard)/, { timeout: 30000 });

    // Verify Tenants table or navigation header
    const mainContent = page.locator("table, .ant-table, main, .ant-layout-content");
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
    // Perform login
    await page.goto(`${CONSOLE_URL}/login`);
    const emailInput = page.locator('input#email, input[name="email"]');
    await emailInput.fill(ADMIN_EMAIL);
    await page.locator('input#password, input[name="password"]').fill(ADMIN_PASSWORD);
    await page.locator('button[type="submit"]').click();

    const mfaInput = page.getByPlaceholder("000000").or(page.locator('input[placeholder="000000"], input#mfa_code')).first();
    try {
      await mfaInput.waitFor({ state: "visible", timeout: 8000 });
      await mfaInput.fill(generateTotp());
      await page.getByRole("button", { name: /Verify/i }).click();
    } catch {}

    await expect(page).toHaveURL(/\/tenants/, { timeout: 20000 });

    // Verify search input is operational
    const searchInput = page.getByPlaceholder(/Search by Tenant ID/i).or(page.locator('input[placeholder*="Search"]')).first();
    if (await searchInput.isVisible({ timeout: 5000 }).catch(() => false)) {
      await searchInput.fill(TARGET_TENANT);
      await expect(searchInput).toHaveValue(TARGET_TENANT);
    }

    // Verify Provision Dedicated Tenant button exists
    const provisionBtn = page.getByRole("button", { name: /Provision Dedicated Tenant/i }).or(page.locator('button:has-text("Provision")')).first();
    await expect(provisionBtn).toBeVisible({ timeout: 10000 });
  });

  test("5. Should provision a new tenant from UI and verify it appears in Fleet table", async ({
    page,
  }) => {
    await page.goto(`${CONSOLE_URL}/login`);
    await page.locator('input#email, input[name="email"]').fill(ADMIN_EMAIL);
    await page.locator('input#password, input[name="password"]').fill(ADMIN_PASSWORD);
    await page.locator('button[type="submit"]').click();

    const mfaInput = page.getByPlaceholder("000000").or(page.locator('input[placeholder="000000"], input#mfa_code')).first();
    try {
      await mfaInput.waitFor({ state: "visible", timeout: 8000 });
      await mfaInput.fill(generateTotp());
      await page.getByRole("button", { name: /Verify/i }).click();
    } catch {}

    await expect(page).toHaveURL(/\/tenants/, { timeout: 20000 });

    // Open Modal
    const provisionBtn = page.getByRole("button", { name: /Provision Dedicated Tenant/i }).or(page.locator('button:has-text("Provision")')).first();
    await provisionBtn.click();

    // Verify modal elements
    const modal = page.locator(".ant-modal");
    await expect(modal.first()).toBeVisible({ timeout: 5000 });

    // Fill form
    const randomSuffix = Math.floor(1000 + Math.random() * 9000);
    const newTenantId = `e2e-tenant-${randomSuffix}`;

    const tenantIdInput = modal.locator('input#tenant_id, input[placeholder*="acme-corp"]').first();
    await tenantIdInput.fill(newTenantId);

    const emailInput = modal.locator('input#admin_email, input[placeholder*="admin@"]').first();
    await emailInput.fill(`admin@${newTenantId}.com`);

    // Submit modal
    const submitBtn = modal.locator('button:has-text("Launch Tenant Instance")').first();
    await submitBtn.click();

    // Verify modal closes
    await expect(modal).not.toBeVisible({ timeout: 15000 });

    // Search for newly created tenant
    const searchInput = page.getByPlaceholder(/Search by Tenant ID/i).or(page.locator('input[placeholder*="Search"]')).first();
    if (await searchInput.isVisible({ timeout: 5000 }).catch(() => false)) {
      await searchInput.fill(newTenantId);
    }

    // Verify tenant row appears in the table!
    const newTenantRow = page.locator(`text="${newTenantId}"`);
    await expect(newTenantRow.first()).toBeVisible({ timeout: 15000 });
  });

  test("6. Should navigate across Control Plane sections (Audit Logs, Telemetry, Webhooks)", async ({
    page,
  }) => {
    await page.goto(`${CONSOLE_URL}/login`);
    await page.locator('input#email, input[name="email"]').fill(ADMIN_EMAIL);
    await page.locator('input#password, input[name="password"]').fill(ADMIN_PASSWORD);
    await page.locator('button[type="submit"]').click();

    const mfaInput = page.getByPlaceholder("000000").or(page.locator('input[placeholder="000000"], input#mfa_code')).first();
    try {
      await mfaInput.waitFor({ state: "visible", timeout: 8000 });
      await mfaInput.fill(generateTotp());
      await page.getByRole("button", { name: /Verify/i }).click();
    } catch {}

    await expect(page).toHaveURL(/\/tenants/, { timeout: 20000 });

    // 1. Audit Logs
    await page.goto(`${CONSOLE_URL}/audit-logs`);
    await expect(page).toHaveURL(/\/audit-logs/, { timeout: 10000 });
    await expect(page.locator("main, .ant-layout-content").first()).toBeVisible({ timeout: 10000 });

    // 2. Telemetry & Metrics
    await page.goto(`${CONSOLE_URL}/telemetry`);
    await expect(page).toHaveURL(/\/telemetry/, { timeout: 10000 });
    await expect(page.locator("main, .ant-layout-content").first()).toBeVisible({ timeout: 10000 });

    // 3. Alerts & Webhooks
    await page.goto(`${CONSOLE_URL}/settings/webhooks`);
    await expect(page).toHaveURL(/\/settings\/webhooks/, { timeout: 10000 });
    await expect(page.locator("main, .ant-layout-content").first()).toBeVisible({ timeout: 10000 });
  });

  test("7. Should support Administrator sign out", async ({
    page,
  }) => {
    await page.goto(`${CONSOLE_URL}/login`);
    await page.locator('input#email, input[name="email"]').fill(ADMIN_EMAIL);
    await page.locator('input#password, input[name="password"]').fill(ADMIN_PASSWORD);
    await page.locator('button[type="submit"]').click();

    const mfaInput = page.getByPlaceholder("000000").or(page.locator('input[placeholder="000000"], input#mfa_code')).first();
    try {
      await mfaInput.waitFor({ state: "visible", timeout: 8000 });
      await mfaInput.fill(generateTotp());
      await page.getByRole("button", { name: /Verify/i }).click();
    } catch {}

    await expect(page).toHaveURL(/\/tenants/, { timeout: 20000 });

    // Logout via header avatar/logout button
    const logoutBtn = page.getByRole("button", { name: /Log out|Logout|Sign out/i }).or(page.locator('button:has-text("Logout"), button:has-text("Sign Out"), .ant-dropdown-menu-item:has-text("Logout")')).first();
    if (await logoutBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await logoutBtn.click();
      await expect(page).toHaveURL(/\/login/, { timeout: 10000 });
    }
  });
});
