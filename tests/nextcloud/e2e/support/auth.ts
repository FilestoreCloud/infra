/**
 * Nextcloud Official Authentication Helper for Playwright E2E.
 * SPDX-License-Identifier: AGPL-3.0-or-later
 */

import { Page, expect } from "@playwright/test";
import { generateTotp } from "./totp.js";

export async function loginNextcloud(
  page: Page,
  username: string = process.env.NEXTCLOUD_USER!,
  password: string = process.env.NEXTCLOUD_PASSWORD!,
) {
  await page.goto("/index.php/login");

  // Wait for login form elements
  const userInput = page.locator('#user, input[name="user"]');
  const passInput = page.locator('#password, input[name="password"]');
  const submitBtn = page.locator('#submit-form, button[type="submit"], button:has-text("Log in")');

  await expect(userInput).toBeVisible({ timeout: 15000 });

  await userInput.fill(username);
  await passInput.fill(password);
  
  await Promise.all([
    page.waitForURL(url => !url.pathname.includes("/login") || url.search.includes("dashboard") || url.search.includes("files"), {
      timeout: 30000,
    }).catch(() => {}),
    submitBtn.first().click(),
  ]);

  // If redirect lands on index.php, navigate to files app if needed
  if (!page.url().includes("/apps/")) {
    await page.goto("/index.php/apps/files/").catch(() => {});
  }

  // Verify authenticated header or navigation
  const headerMenu = page.locator("#header, header, .app-navigation, #appmenu, [role=\"navigation\"], #content, main");
  await expect(headerMenu.first()).toBeVisible({ timeout: 20000 });

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
  await page.goto(`${consoleUrl}/login`);

  const emailInput = page.locator('input#email, input[name="email"]');
  const passInput = page.locator('input#password, input[name="password"]');
  const submitBtn = page.locator('button[type="submit"]');

  await expect(emailInput).toBeVisible({ timeout: 15000 });
  await emailInput.fill(email);
  await passInput.fill(password);
  await submitBtn.click();

  // Check for Step 2: MFA Challenge
  const mfaInput = page
    .getByPlaceholder("000000")
    .or(page.locator('input[placeholder="000000"], input#mfa_code, input#mfaForm_mfa_code'))
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

