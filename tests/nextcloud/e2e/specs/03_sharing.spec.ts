/**
 * Test Nextcloud Sharing UI and Public Sharing Lifecycle.
 * Validates:
 * 1. File sharing sidebar opens on row action click without conditional skips.
 * 2. Password-protected public share link creation via Nextcloud OCS Sharing API.
 * 3. Access verification in an isolated anonymous browser context.
 * 4. Password challenge submission against the share gate.
 * 5. Download of shared file and cryptographic SHA256 integrity verification.
 * 6. Share revocation via admin OCS API.
 * 7. Assertion of subsequent 404 / access denial upon reloading the anonymous context.
 * 8. Cleanup and teardown.
 *
 * SPDX-License-Identifier: AGPL-3.0-or-later
 */

import { test, expect } from "@playwright/test";
import crypto from "node:crypto";
import { loginNextcloud } from "../support/auth.js";

const USERNAME = process.env.NEXTCLOUD_USER || "admin";
const PASSWORD = process.env.NEXTCLOUD_PASSWORD || "admin";

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

async function streamToBuffer(stream: any): Promise<Buffer> {
  if (Buffer.isBuffer(stream)) {
    return stream;
  }
  const chunks: Buffer[] = [];
  for await (const chunk of stream) {
    chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
  }
  return Buffer.concat(chunks);
}

test.describe("Nextcloud Sharing Lifecycle & Sidebar E2E", () => {
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
    await page.goto(`${targetUrl}/index.php/apps/files/`);
    await page.waitForURL(/\/apps\/files/);
  });

  test("Should open file sharing tab when clicking share action", async ({
    page,
    request,
    baseURL,
  }) => {
    const targetUrl = resolveBaseUrl(baseURL);
    const nonce = Date.now().toString(36) + "_" + crypto.randomBytes(4).toString("hex");
    const testFileName = `share_sidebar_${nonce}.txt`;
    const davUrl = `${targetUrl}/remote.php/dav/files/${encodeURIComponent(USERNAME)}/${encodeURIComponent(testFileName)}`;
    const authHeader = getBasicAuthHeader(USERNAME, PASSWORD);

    // Create a guaranteed test file to avoid superficial skip on empty file list
    const createResp = await request.put(davUrl, {
      headers: {
        Authorization: authHeader,
        "Content-Type": "text/plain",
      },
      data: Buffer.from("Sidebar Share Action Test", "utf-8"),
    });
    expect([200, 201, 204]).toContain(createResp.status());

    try {
      await page.goto(`${targetUrl}/index.php/apps/files/`);
      const targetRow = page
        .locator(
          `tr:has-text("${testFileName}"), tr[data-file="${testFileName}"], [data-cy-files-list-row]:has-text("${testFileName}")`
        )
        .first();
      await expect(targetRow).toBeVisible({ timeout: 15000 });

      // Click share action icon on the specific row
      const shareAction = targetRow
        .locator('.action-share, button[aria-label*="Share"], a[data-action="Share"]')
        .first();
      await expect(shareAction).toBeVisible({ timeout: 10000 });
      await shareAction.click();

      // Assert sharing sidebar or modal tab becomes visible
      const shareTab = page.locator(
        '#app-sidebar, [aria-label="Sharing"], .sharing-tab, #app-sidebar-vue'
      );
      await expect(shareTab.first()).toBeVisible({ timeout: 15000 });
    } finally {
      await request.delete(davUrl, { headers: { Authorization: authHeader } }).catch(() => {});
    }
  });

  test("Should complete password-protected public share lifecycle: create, anonymous access, content match, and revocation", async ({
    page,
    request,
    browser,
    baseURL,
  }) => {
    const targetUrl = resolveBaseUrl(baseURL);
    const authHeader = getBasicAuthHeader(USERNAME, PASSWORD);

    // 1. Create a file with known payload and compute SHA256
    const nonce = Date.now().toString(36) + "_" + crypto.randomBytes(4).toString("hex");
    const testFileName = `share_lifecycle_${nonce}.txt`;
    const payloadContent = `Storix Public Sharing E2E Verification Payload - Nonce: ${nonce}`;
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
    expect([200, 201, 204]).toContain(uploadResp.status());

    const sharePassword = `SharePass_${crypto.randomBytes(4).toString("hex")}!9`;
    let shareId: number | string = "";
    let shareToken = "";
    let shareUrl = "";

    try {
      // 2. Create a password-protected public share link via Nextcloud OCS Sharing API
      const shareResp = await request.post(
        `${targetUrl}/ocs/v2.php/apps/files_sharing/api/v1/shares`,
        {
          headers: {
            "OCS-APIRequest": "true",
            Accept: "application/json",
            Authorization: authHeader,
          },
          form: {
            path: `/${testFileName}`,
            shareType: 3, // Public link
            permissions: 1, // Read-only
            password: sharePassword,
          },
        }
      );

      expect(shareResp.ok(), `OCS Share creation failed: ${await shareResp.text()}`).toBe(true);
      const shareJson = await shareResp.json();
      const ocsStatus = shareJson?.ocs?.meta?.statuscode;
      expect([100, 200]).toContain(ocsStatus);

      const shareData = shareJson?.ocs?.data;
      shareId = shareData.id;
      shareToken = shareData.token;
      shareUrl = shareData.url || `${targetUrl}/index.php/s/${shareToken}`;

      expect(shareId).toBeTruthy();
      expect(shareToken).toBeTruthy();

      // 3. Open the public share URL via an isolated anonymous browser context
      const anonContext = await browser.newContext({
        ignoreHTTPSErrors: true,
      });
      const anonPage = await anonContext.newPage();

      try {
        await anonPage.goto(shareUrl, { waitUntil: "domcontentloaded" });

        // 4. Authenticate against the share password gate
        const passwordInput = anonPage
          .locator('input#password, input[name="password"], input[type="password"]')
          .first();
        await expect(passwordInput).toBeVisible({ timeout: 15000 });

        await passwordInput.fill(sharePassword);
        const submitBtn = anonPage
          .locator(
            'button[type="submit"], input[type="submit"], #submit-password, button:has-text("Submit"), button:has-text("Authenticate")'
          )
          .first();
        await submitBtn.click();

        // 5. Download the shared file from the anonymous page and verify content / SHA256 match
        const downloadBtn = anonPage
          .locator(
            'a#downloadFile, a[href*="/download"], button#downloadFile, a.download, button:has-text("Download")'
          )
          .first();

        let downloadedBuffer: Buffer;
        if (await downloadBtn.isVisible({ timeout: 8000 }).catch(() => false)) {
          const [download] = await Promise.all([
            anonPage.waitForEvent("download", { timeout: 15000 }),
            downloadBtn.click(),
          ]);
          const stream = await download.createReadStream();
          downloadedBuffer = await streamToBuffer(stream);
        } else {
          // Direct download URL authenticated with session cookies in anonPage
          const downloadUrl = `${targetUrl}/index.php/s/${shareToken}/download`;
          const directResp = await anonPage.request.get(downloadUrl);
          expect(directResp.ok()).toBe(true);
          downloadedBuffer = await directResp.body();
        }

        const downloadedSha256 = crypto
          .createHash("sha256")
          .update(downloadedBuffer)
          .digest("hex");
        expect(downloadedSha256).toBe(expectedSha256);
        expect(downloadedBuffer.toString("utf-8")).toBe(payloadContent);

        // 6. Revoke the share link via admin OCS API
        const revokeResp = await request.delete(
          `${targetUrl}/ocs/v2.php/apps/files_sharing/api/v1/shares/${shareId}`,
          {
            headers: {
              "OCS-APIRequest": "true",
              Accept: "application/json",
              Authorization: authHeader,
            },
          }
        );
        expect(revokeResp.ok()).toBe(true);
        const revokeJson = await revokeResp.json();
        expect([100, 200]).toContain(revokeJson?.ocs?.meta?.statuscode);

        // 7. Reload the anonymous browser page and assert access is denied / returns HTTP 404
        const reloadResp = await anonPage.goto(shareUrl, {
          waitUntil: "domcontentloaded",
        });
        const reloadStatus = reloadResp?.status();
        if (reloadStatus === 404 || reloadStatus === 403) {
          expect(true).toBe(true);
        } else {
          const errorIndicator = anonPage
            .locator(
              '#body-login, .error, [role="alert"], h2:has-text("File not found"), :has-text("does not exist"), :has-text("Access denied"), :has-text("Page not found"), :has-text("Expired")'
            )
            .first();
          await expect(errorIndicator).toBeVisible({ timeout: 10000 });
        }

        // Also assert anonymous direct download endpoint returns 404 or 403
        const revokedDlResp = await anonPage.request.get(
          `${targetUrl}/index.php/s/${shareToken}/download`
        );
        expect([403, 404]).toContain(revokedDlResp.status());
      } finally {
        await anonContext.close();
      }
    } finally {
      // 8. Cleanup test file
      await request.delete(davUrl, { headers: { Authorization: authHeader } }).catch(() => {});
    }
  });
});
