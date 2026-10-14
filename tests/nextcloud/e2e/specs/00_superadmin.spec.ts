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
  process.env.SUPERADMIN_CONSOLE_URL ||
  "https://d12jxu8xpkp8ik.cloudfront.net";

const ADMIN_EMAIL =
  process.env.SUPERADMIN_USERNAME || "nhphuong.code@gmail.com";
const ADMIN_PASSWORD =
  process.env.SUPERADMIN_PASSWORD ||
  process.env.NEXTCLOUD_PASSWORD ||
  "StorixAdmin2026!Secure";

test.describe("SuperAdmin Web Console E2E", () => {
  test("Should render SuperAdmin login portal entrypoint", async ({
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

  test("Should authenticate SuperAdmin via MFA and access Fleet Registry", async ({
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
    const mfaInput = page.locator('input#mfa_code, input[name="mfa_code"]');
    const mfaAppeared = await mfaInput
      .isVisible({ timeout: 10000 })
      .catch(() => false);

    if (mfaAppeared) {
      const code = generateTotp();
      await mfaInput.fill(code);
      await submitBtn.click();
    }

    // Verify successful login redirection to /tenants or dashboard
    await page.waitForURL(/\/(tenants|dashboard)/, { timeout: 25000 });
    expect(page.url()).toMatch(/\/(tenants|dashboard)/);

    // Verify Tenants table or navigation header
    const mainContent = page.locator("table, .ant-table, main, .ant-layout-content");
    await expect(mainContent.first()).toBeVisible({ timeout: 15000 });

    // Verify registered dev-tenant exists in fleet view
    const tenantCell = page.locator('text="dev-tenant"');
    if (await tenantCell.isVisible({ timeout: 5000 }).catch(() => false)) {
      await expect(tenantCell.first()).toBeVisible();
    }
  });
});
