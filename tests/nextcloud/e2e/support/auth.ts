/**
 * Nextcloud Official Authentication Helper for Playwright E2E.
 * SPDX-License-Identifier: AGPL-3.0-or-later
 */

import { Page, expect } from "@playwright/test";
import { generateTotp } from "./totp.js";

export async function loginNextcloud(
  page: Page,
  username: string = process.env.NEXTCLOUD_USER || "admin",
  password: string = process.env.NEXTCLOUD_PASSWORD || process.env.ADMIN_PASSWORD || "StorixAdmin2026!Secure",
) {
  // Set Authorization header on page extraHTTPHeaders to support HTTP Basic Auth over plain HTTP (ALB)
  const authHeader = "Basic " + Buffer.from(`${username}:${password}`).toString("base64");
  await page.setExtraHTTPHeaders({
    Authorization: authHeader,
  }).catch(() => {});

  // Direct navigation to Files app
  await page.goto("/index.php/apps/files/", { waitUntil: "domcontentloaded" }).catch(() => {});

  // If page was redirected to /login, attempt interactive form submission
  try {
    const cur = new URL(page.url());
    if (cur.pathname.includes("/login")) {
      const userInput = page
        .getByLabel(/Account name or email/i)
        .or(page.locator('#user, input[name="user"], input#user_id'))
        .first();
      const passInput = page
        .getByLabel(/^Password/i)
        .or(page.locator('#password, input[name="password"]'))
        .first();
      const submitBtn = page
        .getByRole("button", { name: /^Log in$/i })
        .or(page.locator('#submit-form, button[type="submit"], input[type="submit"]'))
        .first();

      if (await userInput.isVisible({ timeout: 5000 }).catch(() => false)) {
        await userInput.fill(username);
        await passInput.fill(password);
        await Promise.all([
          page.waitForURL(url => !url.pathname.includes("/login"), { timeout: 30000 }).catch(() => {}),
          submitBtn.click().catch(() => passInput.press("Enter")),
        ]);
      }
    }
  } catch {}

  // Ensure redirect lands on Files app (Nextcloud defaults to /apps/dashboard/ upon login)
  try {
    const postUrl = new URL(page.url());
    if (!postUrl.pathname.includes("/login") && !postUrl.pathname.includes("/apps/files")) {
      await page.goto("/index.php/apps/files/", { waitUntil: "domcontentloaded" }).catch(() => {});
      await page.waitForURL(
        url => !url.pathname.includes("/login") && url.pathname.includes("/apps/files"),
        { timeout: 25000 }
      ).catch(() => {});
    }
  } catch {}

  // Verify authenticated navigation on Files app or generic authenticated shell
  const headerMenu = page.locator(
    ".app-navigation, aside.app-navigation, .files-list__breadcrumbs, [data-cy-files-content-breadcrumbs], nav[aria-label='Current directory path'], #header, button:has-text('New')"
  );
  await expect(headerMenu.first()).toBeVisible({ timeout: 25000 });

  // Dismiss First Run Wizard modal if presented
  const wizard = page.locator('#firstrunwizard, [role="dialog"], .modal-mask');
  if (await wizard.isVisible({ timeout: 4000 }).catch(() => false)) {
    await page.keyboard.press("Escape").catch(() => {});
    const modalCloseBtn = page.locator('#firstrunwizard button[aria-label="Close"], button.modal-container__close, button:has-text("Close")').first();
    if (await modalCloseBtn.isVisible({ timeout: 1000 }).catch(() => false)) {
      await modalCloseBtn.click({ force: true }).catch(() => {});
    }
  }
}

/**
 * SuperAdmin Web Console Authentication Helper for Playwright E2E.
 * Performs enterprise credential login, handles TOTP MFA challenge,
 * and asserts redirection to /tenants or /dashboard.
 */
export async function loginSuperAdmin(
  page: Page,
  email: string = process.env.SUPERADMIN_USERNAME || "admin@example.com",
  password: string = process.env.SUPERADMIN_PASSWORD || process.env.ADMIN_PASSWORD || "SuperAdmin123!",
  consoleUrl: string = process.env.CONSOLE_URL || process.env.SUPERADMIN_CONSOLE_URL || "http://localhost:3000"
): Promise<void> {
  await page.goto(`${consoleUrl}/login`, { waitUntil: "domcontentloaded" });

  const emailInput = page.locator('input#email, input[name="email"], input#admin-email, input[type="email"]');
  const passInput = page.locator('input#password, input[name="password"], input#master-password, input[type="password"]');
  const submitBtn = page.locator('button[type="submit"]');

  await expect(emailInput).toBeVisible({ timeout: 15000 });
  await emailInput.fill(email);
  await passInput.fill(password);
  await submitBtn.click();

  // Check for Step 2: MFA Challenge
  const mfaInput = page
    .getByPlaceholder("000000")
    .or(page.locator('input[placeholder="000000"], input#mfa_code, input#mfa-code, input#mfaForm_mfa_code'))
    .first();

  try {
    await mfaInput.waitFor({ state: "visible", timeout: 8000 });
    const code = generateTotp();
    await mfaInput.fill(code);
    const verifyBtn = page
      .getByRole("button", { name: /Verify/i })
      .or(page.locator('button:has-text("Verify")'))
      .first();
    await verifyBtn.click();
  } catch {
    // MFA challenge may be bypassed or session already established
  }

  // Verify successful redirection to /tenants or /dashboard
  await expect(page).toHaveURL(/\/(tenants|dashboard)/, { timeout: 30000 });

  // Verify main content or table layout is rendered
  const mainContent = page.locator("table, .ant-table, main, .ant-layout-content");
  await expect(mainContent.first()).toBeVisible({ timeout: 20000 });
}

