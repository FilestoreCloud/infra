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
    const submitBtn = page.locator('#submit-form, button[type="submit"]');

    await userInput.fill("wrong_admin");
    await passInput.fill("InvalidPassword123!");
    await submitBtn.click();

    // URL must remain on /login and error message should appear
    await expect(page).toHaveURL(/login/);
    const errorMsg = page.locator('.warning, .error, [role="alert"], #message');
    await expect(errorMsg.first()).toBeVisible({ timeout: 10000 });
  });

  test("Should successfully login and navigate to Files app", async ({
    page,
  }) => {
    await loginNextcloud(page);

    // Navigate to Files app
    await page.goto("/apps/files/");
    await expect(page).toHaveURL(/apps\/files/);

    // Files list table or main content view must be visible
    const fileTable = page.locator(
      "#fileList, .files-list, #app-content-files, main",
    );
    await expect(fileTable.first()).toBeVisible({ timeout: 15000 });
  });
});
