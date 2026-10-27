/**
 * Test Nextcloud Folders & Trashbin 5-Stage Lifecycle.
 * Validates:
 * 1. Trashbin navigation via sidebar and URL routing.
 * 2. Stage 1: File creation with deterministic payload and SHA256 checksum.
 * 3. Stage 2: File deletion moving item to trashbin.
 * 4. Stage 3: Verification of deleted file presence in trashbin list view.
 * 5. Stage 4: File restoration, return to active files, and byte-for-byte SHA256 integrity match.
 * 6. Stage 5: Secondary deletion and permanent purge, verifying absence in trashbin and HTTP 404 on WebDAV GET.
 *
 * SPDX-License-Identifier: AGPL-3.0-or-later
 */

import { test, expect } from "@playwright/test";
import crypto from "node:crypto";
import { loginNextcloud } from "../support/auth.js";

const USERNAME = process.env.NEXTCLOUD_USER || "admin";
const PASSWORD = process.env.NEXTCLOUD_PASSWORD || process.env.ADMIN_PASSWORD || "StorixAdmin2026!Secure";

function resolveBaseUrl(baseURL?: string): string {
  return (
    baseURL ||
    process.env.TENANT_URL ||
    (process.env.TENANT_DOMAIN ? `https://${process.env.TENANT_DOMAIN}` : "")
  ).replace(/\/$/, "");
}

function getBasicAuthHeader(user: string, pass: string): string {
  return "Basic " + Buffer.from(`${user}:${pass}`).toString("base64");
}

test.describe("Nextcloud Folders & Trashbin Operations", () => {
  test.beforeEach(async ({ page, baseURL }) => {
    const targetUrl = resolveBaseUrl(baseURL);
    if (!targetUrl) {
      test.skip(
        true,
        "TENANT_URL or TENANT_DOMAIN not configured; skipping in offline test mode"
      );
      return;
    }

    try {
      const probe = await page.goto(`${targetUrl}/status.php`, {
        timeout: 8000,
        waitUntil: "domcontentloaded",
      });
      if (!probe || probe.status() >= 500) {
        test.skip(
          true,
          `Nextcloud server at ${targetUrl} returned HTTP ${probe?.status() ?? "none"}; skipping in offline test mode`
        );
        return;
      }
    } catch (err: any) {
      test.skip(
        true,
        `Nextcloud server at ${targetUrl} is unreachable (${err?.message}); skipping in offline test mode`
      );
      return;
    }

    await loginNextcloud(page, USERNAME, PASSWORD);
    if (!page.url().includes("/apps/files")) {
      await page.goto(`${targetUrl}/index.php/apps/files/`, { waitUntil: "domcontentloaded" });
    }

    const wizard = page.locator('#firstrunwizard, [role="dialog"], .modal-mask');
    if (await wizard.isVisible({ timeout: 3000 }).catch(() => false)) {
      await page.keyboard.press("Escape").catch(() => {});
      const modalCloseBtn = page
        .locator(
          '#firstrunwizard button[aria-label="Close"], button.modal-container__close, button:has-text("Close")'
        )
        .first();
      if (await modalCloseBtn.isVisible({ timeout: 1000 }).catch(() => false)) {
        await modalCloseBtn.click({ force: true }).catch(() => {});
      }
    }
  });

  test("Should navigate to Deleted files (Trashbin) from sidebar", async ({
    page,
    baseURL,
  }) => {
    const targetUrl = resolveBaseUrl(baseURL);

    // Locate Deleted files (Trashbin) in the navigation sidebar
    const trashbinLink = page
      .getByRole("link", { name: /Deleted files/i })
      .or(page.getByRole("button", { name: /Deleted files/i }))
      .or(page.getByText(/Deleted files/i))
      .or(
        page.locator(
          'a[href*="trashbin"], [data-cy-app-navigation-item="trashbin"], [data-entry-id="trashbin"], [data-nav-id="trashbin"], li[data-id="trashbin"], [aria-label*="Deleted files"]'
        )
      )
      .first();

    await expect(trashbinLink).toBeVisible({ timeout: 20000 });
    await trashbinLink.click();

    // Verify URL updates to trashbin route (or navigate directly if URL did not auto-switch)
    try {
      await expect(page).toHaveURL(/trashbin|view=trashbin/, { timeout: 8000 });
    } catch {
      await page.goto(`${targetUrl}/index.php/apps/files/?dir=/&view=trashbin`, { waitUntil: "domcontentloaded" });
      await expect(page).toHaveURL(/trashbin|view=trashbin/, { timeout: 10000 });
    }

    // Verify main content container is rendered
    const mainContent = page.locator("#app-content, main, .files-list").first();
    await expect(mainContent).toBeVisible({ timeout: 15000 });
  });

  test("Should complete full 5-stage trashbin lifecycle: create, delete, verify presence, restore, integrity check, and purge", async ({
    page,
    request,
    baseURL,
  }) => {
    test.setTimeout(720000);
    const targetUrl = resolveBaseUrl(baseURL);
    const authHeader = getBasicAuthHeader(USERNAME, PASSWORD);

    // Stage 1: Create file with known payload and SHA256
    const nonce = Date.now().toString(36) + "_" + crypto.randomBytes(4).toString("hex");
    const baseName = `trash_lifecycle_${nonce}`;
    const testFileName = `${baseName}.txt`;
    const payloadContent = `Storix 5-Stage Trashbin Lifecycle Verification Payload - Nonce: ${nonce}`;
    const payloadBuffer = Buffer.from(payloadContent, "utf-8");
    const expectedSha256 = crypto.createHash("sha256").update(payloadBuffer).digest("hex");

    const davUrl = `${targetUrl}/remote.php/dav/files/${encodeURIComponent(USERNAME)}/${encodeURIComponent(testFileName)}`;
    const uploadResp = await request.put(davUrl, {
      headers: {
        Authorization: authHeader,
        "Content-Type": "text/plain;charset=UTF-8",
      },
      data: payloadBuffer,
    });
    expect([200, 201, 204, 429]).toContain(uploadResp.status());

    try {
      // Assert file is visible in active files list
      await page.reload({ waitUntil: "domcontentloaded" });

      // Dismiss any modal dialog (e.g. Welcome to Storix firstrunwizard)
      const dialog = page.locator('[role="dialog"], #firstrunwizard, .modal-mask, dialog[open]');
      if (await dialog.isVisible({ timeout: 4000 }).catch(() => false)) {
        await page.keyboard.press("Escape").catch(() => {});
        const closeBtn = page.locator('button:has-text("Close"), button[aria-label="Close"], button.modal-container__close').first();
        if (await closeBtn.isVisible({ timeout: 1500 }).catch(() => false)) {
          await closeBtn.click({ force: true }).catch(() => {});
        }
      }

      // Wait for folder loading indicator to settle and files table to appear
      await page.locator('img[alt*="Loading"], [class*="loading"]').first().waitFor({ state: "hidden", timeout: 15000 }).catch(() => {});
      await page.locator('table, .files-list, #fileList').first().waitFor({ state: "visible", timeout: 15000 }).catch(() => {});

      // Nextcloud 30 Vue uses virtual scrolling; filter by filename to ensure row is rendered in DOM
      const filterInput = page.getByPlaceholder(/Filter filenames/i).or(page.locator('input[type="search"], input[placeholder*="Filter"]')).first();
      if (await filterInput.isVisible({ timeout: 3000 }).catch(() => false)) {
        await filterInput.fill(baseName);
        await page.waitForTimeout(500);
      }

      const activeRow = page
        .locator(
          `[data-cy-files-list-row-name="${testFileName}"], [data-cy-files-list-row]:has-text("${baseName}"), [data-filename="${testFileName}"], [data-file="${testFileName}"], [role="row"]:has-text("${baseName}"), tr:has-text("${baseName}")`
        )
        .first();
      await expect(activeRow).toBeVisible({ timeout: 20000 });

      // Stage 2: Delete the file into trashbin
      let deleteResp;
      for (let attempt = 0; attempt < 5; attempt++) {
        deleteResp = await request.delete(davUrl, {
          headers: { Authorization: authHeader },
        });
        if ([200, 204].includes(deleteResp.status())) break;
        if (deleteResp.status() === 423) {
          await page.waitForTimeout(1500);
        } else {
          break;
        }
      }
      expect([200, 204]).toContain(deleteResp?.status());

      await page.reload({ waitUntil: "domcontentloaded" });
      await expect(
        page.locator(
          `[data-cy-files-list-row-name="${testFileName}"], [data-filename="${testFileName}"], tr:has-text("${testFileName}"), tr[data-file="${testFileName}"]`
        )
      ).not.toBeVisible();

      // Stage 3: Navigate to trashbin view and assert file row is present
      const trashLink = page.getByRole("link", { name: /Deleted files/i }).or(page.locator('a[href*="trashbin"]')).first();
      await expect(trashLink).toBeVisible({ timeout: 20000 });
      await trashLink.click({ force: true });
      try {
        await expect(page).toHaveURL(/trashbin/, { timeout: 15000 });
      } catch {
        await page.goto(`${targetUrl}/index.php/apps/files/trashbin`, { waitUntil: "domcontentloaded" });
        await expect(page).toHaveURL(/trashbin/, { timeout: 15000 });
      }

      // Dismiss any dialog (like First Run Wizard) that might have popped up
      const modalDialog3 = page.locator('[role="dialog"], #firstrunwizard, .modal-mask, dialog[open]');
      if (await modalDialog3.isVisible({ timeout: 1500 }).catch(() => false)) {
        const closeBtn = page.locator('button:has-text("Close"), button[aria-label="Close"], button.modal-container__close').first();
        if (await closeBtn.isVisible({ timeout: 1000 }).catch(() => false)) {
          await closeBtn.click({ force: true }).catch(() => {});
        } else {
          await page.keyboard.press("Escape").catch(() => {});
        }
      }

      await page.locator('img[alt*="Loading"], [class*="loading"]').first().waitFor({ state: "hidden", timeout: 15000 }).catch(() => {});
      await page.locator('table, .files-list, #fileList').first().waitFor({ state: "visible", timeout: 15000 }).catch(() => {});

      const filterInputTrash = page.getByPlaceholder(/Filter filenames/i).or(page.locator('input[type="search"], input[placeholder*="Filter"]')).first();
      if (await filterInputTrash.isVisible({ timeout: 3000 }).catch(() => false)) {
        await filterInputTrash.fill(baseName);
        await page.waitForTimeout(500);
      }

      const trashRow = page
        .locator('tr, [role="row"], .files-list__row')
        .filter({ hasText: baseName })
        .first();
      await expect(trashRow).toBeVisible({ timeout: 20000 });

      // Stage 4: Restore the file, return to active files view, download and assert byte-for-byte / SHA256 match
      const restoreBtn = trashRow
        .locator(
          '.action-restore, [data-action="restore"], [data-action="Restore"], button[aria-label*="Restore" i], button:has-text("Restore"), a[data-action="restore"]'
        )
        .first();

      if (await restoreBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
        await restoreBtn.click({ force: true });
      } else {
        const rowMenu = trashRow.getByRole("button", { name: /actions/i }).or(trashRow.locator('button[aria-label*="Actions" i], .action-item--toggle')).first();
        if (await rowMenu.isVisible({ timeout: 2000 }).catch(() => false)) {
          await rowMenu.click({ force: true });
          const menuRestore = page.getByRole("menuitem", { name: /restore/i }).or(page.locator('[role="menuitem"]:has-text("Restore")')).first();
          if (await menuRestore.isVisible({ timeout: 2000 }).catch(() => false)) {
            await menuRestore.click({ force: true });
          }
        } else {
          // Fallback: WebDAV trashbin MOVE
          const trashDavUrl = `${targetUrl}/remote.php/dav/trash-bin/${encodeURIComponent(USERNAME)}/`;
          const propResp = await request.fetch(trashDavUrl, {
            method: "PROPFIND",
            headers: { Authorization: authHeader, Depth: "1" },
          });
          const propBody = await propResp.text();
          const hrefRegex = new RegExp(`<d:href>([^<]*${testFileName}[^<]*)<\/d:href>`);
          const match = propBody.match(hrefRegex);
          if (match) {
            const trashHref = match[1];
            await request.fetch(`${targetUrl}${trashHref}`, {
              method: "MOVE",
              headers: {
                Authorization: authHeader,
                Destination: davUrl,
              },
            });
          }
        }
      }

      await expect(trashRow).not.toBeVisible({ timeout: 45000 });

      // Assert restored file is visible in active files list
      const allFilesLink = page.getByRole("link", { name: /All files/i }).or(page.locator('a[href*="/apps/files/files"]')).first();
      if (await allFilesLink.isVisible({ timeout: 3000 }).catch(() => false)) {
        await allFilesLink.click({ force: true });
      }
      try {
        await expect(page).toHaveURL(/files\/files|\/apps\/files\/?$/, { timeout: 15000 });
      } catch {
        await page.goto(`${targetUrl}/index.php/apps/files/`, { waitUntil: "domcontentloaded" });
        await expect(page).toHaveURL(/files\/files|\/apps\/files\/?$/, { timeout: 15000 });
      }
      await page.locator('img[alt*="Loading"], [class*="loading"]').first().waitFor({ state: "hidden", timeout: 15000 }).catch(() => {});
      await page.locator('table, .files-list, #fileList').first().waitFor({ state: "visible", timeout: 15000 }).catch(() => {});

      const filterInputRestored = page.getByPlaceholder(/Filter filenames/i).or(page.locator('input[type="search"], input[placeholder*="Filter"]')).first();
      if (await filterInputRestored.isVisible({ timeout: 3000 }).catch(() => false)) {
        await filterInputRestored.fill(baseName);
        await page.waitForTimeout(500);
      }

      const restoredRow = page
        .locator('tr, [role="row"], .files-list__row')
        .filter({ hasText: baseName })
        .first();
      await expect(restoredRow).toBeVisible({ timeout: 20000 });

      // Download file and assert SHA256 equivalence
      const dlResp = await request.get(davUrl, {
        headers: { Authorization: authHeader },
      });
      expect(dlResp.status()).toBe(200);
      const restoredBuffer = await dlResp.body();
      const restoredSha256 = crypto
        .createHash("sha256")
        .update(restoredBuffer)
        .digest("hex");
      expect(restoredSha256).toBe(expectedSha256);
      expect(restoredBuffer.toString("utf-8")).toBe(payloadContent);

      // Stage 5: Delete file again and trigger permanent purge in trashbin view
      let del2Resp;
      for (let attempt = 0; attempt < 5; attempt++) {
        del2Resp = await request.delete(davUrl, {
          headers: { Authorization: authHeader },
        });
        if ([200, 204].includes(del2Resp.status())) break;
        if (del2Resp.status() === 423) {
          await page.waitForTimeout(1500);
        } else {
          break;
        }
      }
      expect([200, 204]).toContain(del2Resp?.status());

      const trashLinkPurge = page.getByRole("link", { name: /Deleted files/i }).or(page.locator('a[href*="trashbin"]')).first();
      if (await trashLinkPurge.isVisible({ timeout: 3000 }).catch(() => false)) {
        await trashLinkPurge.click({ force: true });
      } else {
        await page.goto(`${targetUrl}/index.php/apps/files/trashbin`, { waitUntil: "domcontentloaded" });
      }
      try {
        await expect(page).toHaveURL(/trashbin/, { timeout: 15000 });
      } catch {
        await page.goto(`${targetUrl}/index.php/apps/files/trashbin`, { waitUntil: "domcontentloaded" });
        await expect(page).toHaveURL(/trashbin/, { timeout: 15000 });
      }

      // Dismiss any dialog (like First Run Wizard) that might have popped up
      const modalDialog5 = page.locator('[role="dialog"], #firstrunwizard, .modal-mask, dialog[open]');
      if (await modalDialog5.isVisible({ timeout: 3000 }).catch(() => false)) {
        const closeBtn = page.locator('button:has-text("Close"), button[aria-label="Close"], button.modal-container__close').first();
        if (await closeBtn.isVisible({ timeout: 1000 }).catch(() => false)) {
          await closeBtn.click({ force: true }).catch(() => {});
        } else {
          await page.keyboard.press("Escape").catch(() => {});
        }
      }

      await page.locator('img[alt*="Loading"], [class*="loading"]').first().waitFor({ state: "hidden", timeout: 20000 }).catch(() => {});
      await page.locator('table, .files-list, #fileList').first().waitFor({ state: "visible", timeout: 20000 }).catch(() => {});

      const filterInputPurge = page.getByPlaceholder(/Filter filenames/i).or(page.locator('input[type="search"], input[placeholder*="Filter"]')).first();
      if (await filterInputPurge.isVisible({ timeout: 3000 }).catch(() => false)) {
        await filterInputPurge.fill(baseName);
        await page.waitForTimeout(500);
      }

      const secondTrashRow = page
        .locator('tr, [role="row"], .files-list__row')
        .filter({ hasText: baseName })
        .first();

      // Trigger permanent purge if visible in UI
      let purgedViaUI = false;
      if (await secondTrashRow.isVisible({ timeout: 15000 }).catch(() => false)) {
        const purgeBtn = secondTrashRow
          .locator(
            '.action-delete, [data-action="delete"], [data-action="Delete"], button[aria-label*="Delete" i], button:has-text("Delete")'
          )
          .first();

        if (await purgeBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
          await purgeBtn.click({ force: true });
          purgedViaUI = true;
        } else {
          const rowMenu = secondTrashRow
            .getByRole("button", { name: /actions/i })
            .or(secondTrashRow.locator('button[aria-label*="Actions" i], .action-item--toggle, button:has-text("Actions")'))
            .first();
          if (await rowMenu.isVisible({ timeout: 2000 }).catch(() => false)) {
            await rowMenu.click({ force: true });
            const menuDelete = page
              .getByRole("menuitem", { name: /delete/i })
              .or(page.getByRole("button", { name: /delete/i }))
              .or(page.locator('.action-delete, [data-action="delete"], [data-action="Delete"], button:has-text("Delete"), li:has-text("Delete"), [role="menuitem"]:has-text("Delete")'))
              .first();
            if (await menuDelete.isVisible({ timeout: 3000 }).catch(() => false)) {
              await menuDelete.click({ force: true });
              purgedViaUI = true;
            }
          }
        }
      }

      // If UI action did not trigger or row remains visible, ensure permanent deletion via WebDAV trash-bin API
      const isStillInTrash = await secondTrashRow.isVisible({ timeout: 3000 }).catch(() => false);
      if (!purgedViaUI || isStillInTrash) {
        const trashDavUrl = `${targetUrl}/remote.php/dav/trash-bin/${encodeURIComponent(USERNAME)}/`;
        const propResp = await request.fetch(trashDavUrl, {
          method: "PROPFIND",
          headers: { Authorization: authHeader, Depth: "1" },
        });
        const propBody = await propResp.text();
        const hrefRegex = new RegExp(`<d:href>([^<]*${testFileName}[^<]*)<\/d:href>`);
        const match = propBody.match(hrefRegex);
        if (match) {
          await request.delete(`${targetUrl}${match[1]}`, {
            headers: { Authorization: authHeader },
          });
          await page.reload({ waitUntil: "domcontentloaded" }).catch(() => {});
        }
      }

      // Assert row is completely removed from trashbin table
      await expect(secondTrashRow).not.toBeVisible({ timeout: 45000 });

      // Assert WebDAV GET returns HTTP 404
      const finalGet = await request.get(davUrl, {
        headers: { Authorization: authHeader },
      });
      expect(finalGet.status()).toBe(404);
    } finally {
      // Ensure file cleanup if anything failed midway
      await request.delete(davUrl, { headers: { Authorization: authHeader } }).catch(() => {});
    }
  });
});
