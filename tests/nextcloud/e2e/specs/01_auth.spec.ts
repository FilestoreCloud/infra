/**
 * Test Nextcloud Web Authentication Flow.
 * SPDX-License-Identifier: AGPL-3.0-or-later
 */

import { test, expect } from "@playwright/test";
import { loginNextcloud } from "../support/auth.js";

test.describe("Nextcloud Authentication E2E", () => {
  test("Should successfully login and navigate to Files app", async ({
    page,
  }) => {
    test.setTimeout(120000);
    await loginNextcloud(page);

    // Navigate to Files app
    if (!page.url().includes("/apps/files")) {
      await page.goto("/index.php/apps/files/", { waitUntil: "domcontentloaded" });
    }
    await expect(page).toHaveURL(/apps\/files/, { timeout: 45000 });

    // Files list breadcrumbs or authenticated navigation must be visible
    const fileTable = page.locator(
      ".files-list__breadcrumbs, [data-cy-files-content-breadcrumbs], .app-navigation, aside.app-navigation, button:has-text('New'), #fileList, .files-list"
    );
    await expect(fileTable.first()).toBeVisible({ timeout: 20000 });
  });

  test("Should reject invalid credentials with error message", async ({
    page,
  }) => {
    await page.goto("/index.php/login", { waitUntil: "domcontentloaded" });

    const userInput = page.locator('#user, input[name="user"]');
    const passInput = page.locator('#password, input[name="password"]');
    const submitBtn = page.locator('#submit-form, button[type="submit"], button:has-text("Log in")');

    await userInput.fill("wrong_admin");
    await passInput.fill("InvalidPassword123!");
    await submitBtn.first().click();

    // URL must remain on login and either error alert is shown or redirect query indicates wrong user
    await expect(page).toHaveURL(/login/);
    await page.waitForTimeout(1000);
    const hasErrorAlert = await page
      .locator('.warning, .error, [role="alert"], #messageText, .input-field--error')
      .first()
      .isVisible({ timeout: 5000 })
      .catch(() => false);
    const hasUserParam = page.url().includes("user=wrong_admin") || page.url().includes("direct=1");
    expect(hasErrorAlert || hasUserParam).toBe(true);
  });
});
