/**
 * Test Nextcloud Web Authentication Flow.
 * SPDX-License-Identifier: AGPL-3.0-or-later
 */

import { test, expect } from "@playwright/test";
import { loginNextcloud } from "../support/auth.ts";

test.describe("Nextcloud Authentication E2E", () => {
  test("Should reject invalid credentials with error message", async ({
    page,
  }) => {
    await page.goto("/index.php/login");

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

  test("Should successfully login and navigate to Files app", async ({
    page,
  }) => {
    await loginNextcloud(page);

    // Navigate to Files app
    await page.goto("/index.php/apps/files/");
    await expect(page).toHaveURL(/apps\/files/);

    // Files list table or main content view must be visible
    const fileTable = page.locator(
      "#fileList, .files-list, #app-content-files, main, #app-content",
    );
    await expect(fileTable.first()).toBeVisible({ timeout: 15000 });
  });
});
