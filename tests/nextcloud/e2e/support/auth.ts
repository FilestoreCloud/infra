/**
 * Nextcloud Official Authentication Helper for Playwright E2E.
 * SPDX-License-Identifier: AGPL-3.0-or-later
 */

import { Page, expect } from "@playwright/test";

export async function loginNextcloud(
  page: Page,
  username: string = process.env.NEXTCLOUD_USER || "admin",
  password: string = process.env.NEXTCLOUD_PASSWORD || "admin",
) {
  await page.goto("/index.php/login");

  // Wait for login form elements
  const userInput = page.locator('#user, input[name="user"]');
  const passInput = page.locator('#password, input[name="password"]');
  const submitBtn = page.locator('#submit-form, button[type="submit"]');

  await expect(userInput).toBeVisible({ timeout: 15000 });

  await userInput.fill(username);
  await passInput.fill(password);
  await submitBtn.click();

  // Wait for redirect to dashboard or files
  await page.waitForURL(/\/(apps\/(dashboard|files)|index\.php)/, {
    timeout: 20000,
  });

  // Verify authenticated header or navigation
  const headerMenu = page.locator("#header, header, .app-navigation, #appmenu");
  await expect(headerMenu.first()).toBeVisible({ timeout: 15000 });
}
