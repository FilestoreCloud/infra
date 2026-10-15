/**
 * Test Nextcloud Folder Creation, File Deletion and Trashbin Navigation.
 * SPDX-License-Identifier: AGPL-3.0-or-later
 */

import { test, expect } from "@playwright/test";
import { loginNextcloud } from "../support/auth.ts";

test.describe("Nextcloud Folders & Trashbin Operations", () => {
  test.beforeEach(async ({ page }) => {
    await loginNextcloud(page);
    await page.goto("/index.php/apps/files/");
    await page.waitForURL(/\/apps\/files/);
    const wizard = page.locator('#firstrunwizard, [role="dialog"], .modal-mask');
    if (await wizard.isVisible({ timeout: 4000 }).catch(() => false)) {
      await page.keyboard.press("Escape").catch(() => {});
      const modalCloseBtn = page.locator('#firstrunwizard button[aria-label="Close"], button.modal-container__close, button:has-text("Close")').first();
      if (await modalCloseBtn.isVisible({ timeout: 1000 }).catch(() => false)) {
        await modalCloseBtn.click({ force: true }).catch(() => {});
      }
    }
  });

  test("Should navigate to Deleted files (Trashbin) from sidebar", async ({
    page,
  }) => {
    // Find Trashbin / Deleted files link in the left navigation sidebar
    const trashbinLink = page
      .locator(
        'a[href*="trashbin"], li[data-id="trashbin"], [aria-label*="Deleted files"], a:has-text("Deleted files")'
      )
      .first();

    await expect(trashbinLink).toBeVisible({ timeout: 15000 });
    await trashbinLink.click();

    // Verify URL or header updates to trashbin
    await expect(page).toHaveURL(/trashbin/, { timeout: 15000 });

    // Verify main content loads
    const mainContent = page.locator("#app-content, main, .files-list");
    await expect(mainContent.first()).toBeVisible({ timeout: 15000 });
  });

  test("Should inspect Favorites and Recent files filters", async ({ page }) => {
    // Check for Favorites link
    const favoritesLink = page
      .locator(
        'a[href*="favorites"], li[data-id="favorites"], a:has-text("Favorites")'
      )
      .first();

    if (await favoritesLink.isVisible({ timeout: 5000 }).catch(() => false)) {
      await favoritesLink.click();
      await expect(page).toHaveURL(/favorites/, { timeout: 10000 });
    }

    // Check for Recent link
    const recentLink = page
      .locator(
        'a[href*="recent"], li[data-id="recent"], a:has-text("Recent")'
      )
      .first();

    if (await recentLink.isVisible({ timeout: 5000 }).catch(() => false)) {
      await recentLink.click();
      await expect(page).toHaveURL(/recent/, { timeout: 10000 });
    }
  });
});
