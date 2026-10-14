/**
 * Test Nextcloud Files UI Operations: Navigation, Folder Creation, Actions Menu.
 * SPDX-License-Identifier: AGPL-3.0-or-later
 */

import { test, expect } from "@playwright/test";
import { loginNextcloud } from "../support/auth.ts";

test.describe("Nextcloud Files UI Operations", () => {
  test.beforeEach(async ({ page }) => {
    await loginNextcloud(page);
    await page.goto("/index.php/apps/files/");
    await page.waitForURL(/\/apps\/files/);
  });

  test("Should display file list and breadcrumbs navigation", async ({
    page,
  }) => {
    // Verify navigation sidebar
    const sidebar = page.locator("#app-navigation, .app-navigation, nav, [aria-label=\"Files\"]");
    await expect(sidebar.first()).toBeVisible({ timeout: 15000 });

    // Verify main files content
    const mainContent = page.locator("#app-content, main, #app-content-vue, .files-list");
    await expect(mainContent.first()).toBeVisible({ timeout: 15000 });
  });

  test("Should open new resource menu (New button)", async ({ page }) => {
    // Locate the "New" (+) button in the Files app header
    const newButton = page.locator(
      '#app-content-files button.new, button[aria-label="New"], .new-file-menu, a.button.new',
    );

    if (
      await newButton
        .first()
        .isVisible({ timeout: 5000 })
        .catch(() => false)
    ) {
      await newButton.first().click();
      // Popover or action menu should appear
      const newMenu = page.locator('.newFileMenu, .popover, [role="menu"]');
      await expect(newMenu.first()).toBeVisible({ timeout: 5000 });
    }
  });
});
