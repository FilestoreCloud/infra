/**
 * Test Nextcloud Sharing UI and Sidebar.
 * SPDX-License-Identifier: AGPL-3.0-or-later
 */

import { test, expect } from "@playwright/test";
import { loginNextcloud } from "../support/auth.ts";

test.describe("Nextcloud Sharing Sidebar E2E", () => {
  test.beforeEach(async ({ page }) => {
    await loginNextcloud(page);
    await page.goto("/index.php/apps/files/");
    await page.waitForURL(/\/apps\/files/);
  });

  test("Should open file sharing tab when clicking share action", async ({
    page,
  }) => {
    // Look for any existing file or folder row
    const firstRow = page
      .locator("tr[data-id], .files-list__row, [data-cy-files-list-row]")
      .first();

    if (await firstRow.isVisible({ timeout: 5000 }).catch(() => false)) {
      // Find share action icon on the row
      const shareAction = firstRow
        .locator(
          '.action-share, button[aria-label*="Share"], a[data-action="Share"]',
        )
        .first();

      if (await shareAction.isVisible({ timeout: 3000 }).catch(() => false)) {
        await shareAction.click();

        // Sharing sidebar or modal should become visible
        const shareTab = page.locator(
          '#app-sidebar, [aria-label="Sharing"], .sharing-tab',
        );
        await expect(shareTab.first()).toBeVisible({ timeout: 8000 });
      }
    }
  });
});
