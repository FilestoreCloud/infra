/**
 * Storix SuperAdmin & Tenant Deep Lifecycle Testing Support.
 *
 * Implements root-level verification for:
 * 1. Polling tenant status transitions to ACTIVE
 * 2. Probing Nextcloud HTTP health endpoint (/status.php)
 * 3. Isolated browser context tenant administrator authentication & storage access
 * 4. UI-driven and API fallback deprovisioning teardown guardrails
 *
 * SPDX-License-Identifier: AGPL-3.0-or-later
 */

import { Page, Browser, APIRequestContext, expect } from "@playwright/test";

export interface StatusPhpResponse {
  installed: boolean;
  maintenance: boolean;
  needsDbUpgrade?: boolean;
  version?: string;
  versionstring?: string;
  edition?: string;
  productname?: string;
  extendedSupport?: boolean;
  [key: string]: any;
}

/**
 * Poll tenant table row in SuperAdmin console until status transitions to ACTIVE.
 * Refine UI automatically polls every 2500ms when in-flight tenants exist.
 */
export async function pollTenantActiveState(
  page: Page,
  tenantId: string,
  timeoutMs: number = 120000
): Promise<void> {
  const startTime = Date.now();

  while (Date.now() - startTime < timeoutMs) {
    // If search box is present, filter by tenant ID to handle multi-page tables
    const searchInput = page
      .getByPlaceholder(/Search by Tenant ID/i)
      .or(page.locator('input[placeholder*="Search"]'))
      .first();

    if (await searchInput.isVisible().catch(() => false)) {
      const currentVal = await searchInput.inputValue().catch(() => "");
      if (currentVal !== tenantId) {
        await searchInput.fill(tenantId);
        await page.waitForTimeout(400);
      }
    }

    // Locate the tenant row
    const row = page.locator("tr").filter({ hasText: tenantId }).first();
    if (await row.isVisible().catch(() => false)) {
      // Check for early failure
      const failedBadge = row
        .locator('span, div, [class*="badge"]')
        .filter({ hasText: /^FAILED$/i })
        .first();
      if (await failedBadge.isVisible().catch(() => false)) {
        throw new Error(
          `Tenant ${tenantId} entered FAILED status during provisioning.`
        );
      }

      // Check if status badge is ACTIVE
      const activeBadge = row
        .locator('span, div, [class*="badge"]')
        .filter({ hasText: /^ACTIVE$/i })
        .first();

      if (await activeBadge.isVisible().catch(() => false)) {
        return;
      }
    }

    // Trigger refresh button periodically if present
    const refreshBtn = page
      .getByRole("button", { name: /Refresh/i })
      .or(page.locator('button:has-text("Refresh")'))
      .first();
    if (await refreshBtn.isVisible().catch(() => false)) {
      if ((Date.now() - startTime) % 10000 < 2500) {
        await refreshBtn.click().catch(() => {});
      }
    }

    await page.waitForTimeout(2000);
  }

  // Final assertion to produce detailed Playwright assertion error if timeout reached
  const finalRow = page.locator("tr").filter({ hasText: tenantId }).first();
  await expect(finalRow).toBeVisible({ timeout: 5000 });
  const finalBadge = finalRow
    .locator('span, div, [class*="badge"]')
    .filter({ hasText: /^ACTIVE$/i })
    .first();
  await expect(finalBadge).toBeVisible({ timeout: 5000 });
}

/**
 * Probe tenant's HTTP health endpoint (/status.php) returning HTTP 200,
 * installed: true, and maintenance: false.
 * Handles transient ECS/ALB initialization states (502, 503) with exponential/interval retry.
 */
export async function probeTenantStatusPhp(
  request: APIRequestContext,
  statusUrlOrTenantBase: string,
  hostHeader?: string,
  timeoutMs: number = 90000
): Promise<StatusPhpResponse> {
  const normalizedUrl = statusUrlOrTenantBase.endsWith("/status.php")
    ? statusUrlOrTenantBase
    : `${statusUrlOrTenantBase.replace(/\/+$/, "")}/status.php`;

  const startTime = Date.now();
  let lastError: any = null;
  let lastStatus: number | null = null;
  let lastBody: string = "";

  while (Date.now() - startTime < timeoutMs) {
    try {
      const headers: Record<string, string> = {};
      if (hostHeader) {
        headers["Host"] = hostHeader;
      }

      const response = await request.get(normalizedUrl, {
        headers,
        ignoreHTTPSErrors: true,
        timeout: 10000,
      });

      lastStatus = response.status();
      if (lastStatus === 200) {
        const body = await response.json().catch(() => null);
        if (body && typeof body === "object") {
          if (body.installed === true && body.maintenance === false) {
            return body as StatusPhpResponse;
          }
        }
      }
      lastBody = await response.text().catch(() => "");
    } catch (err: any) {
      lastError = err;
    }

    await new Promise((resolve) => setTimeout(resolve, 3000));
  }

  throw new Error(
    `probeTenantStatusPhp timed out after ${timeoutMs}ms for ${normalizedUrl}. ` +
      `Last HTTP status: ${lastStatus}, response body: ${lastBody.slice(0, 300)}, ` +
      `last error: ${lastError?.message || lastError}`
  );
}

/**
 * Authenticate into newly provisioned tenant as its administrator in an isolated
 * browser context (avoiding cookie/session collision with SuperAdmin console).
 * Verifies authenticated session navigation and basic storage layout (/index.php/apps/files/).
 */
export async function verifyTenantAdminSession(
  browser: Browser,
  tenantUrl: string,
  adminUser: string = "admin",
  adminPassword?: string,
  hostHeader?: string
): Promise<void> {
  const resolvedPassword =
    adminPassword ||
    process.env.NEXTCLOUD_PASSWORD ||
    process.env.ADMIN_PASSWORD ||
    process.env.SUPERADMIN_PASSWORD ||
    "Admin1234!";

  // Create clean isolated context without restricted Host headers
  const tenantContext = await browser.newContext({
    ignoreHTTPSErrors: true,
  });
  const tenantPage = await tenantContext.newPage();

  // If hostHeader is provided and differs from tenantUrl hostname, use page.route
  // rather than extraHTTPHeaders to safely route requests without triggering net::ERR_INVALID_ARGUMENT
  if (hostHeader && !tenantUrl.includes(hostHeader)) {
    await tenantPage.route("**/*", async (route) => {
      const headers = { ...route.request().headers(), host: hostHeader };
      await route.continue({ headers });
    }).catch(() => {});
  }

  try {
    const cleanBase = tenantUrl.trim().replace(/\/+$/, "");
    const loginUrl = cleanBase.includes("/index.php")
      ? cleanBase
      : `${cleanBase}/index.php/login`;
    await tenantPage.goto(loginUrl, {
      waitUntil: "domcontentloaded",
      timeout: 30000,
    });

    const userInput = tenantPage.locator('#user, input[name="user"]');
    const passInput = tenantPage.locator('#password, input[name="password"]');
    const submitBtn = tenantPage.locator(
      '#submit-form, button[type="submit"], button:has-text("Log in")'
    );

    if (await userInput.isVisible({ timeout: 10000 }).catch(() => false)) {
      await userInput.fill(adminUser);
      await passInput.fill(resolvedPassword);
      await Promise.all([
        tenantPage
          .waitForURL(
            (url) =>
              !url.pathname.includes("/login") ||
              url.pathname.includes("/apps/") ||
              url.search.includes("files") ||
              url.search.includes("dashboard"),
            { timeout: 30000 }
          )
          .catch(() => {}),
        submitBtn.first().click(),
      ]);
    }

    // Direct navigation to files app if not already on an apps view
    if (!tenantPage.url().includes("/apps/files")) {
      await tenantPage
        .goto(`${cleanBase}/index.php/apps/files/`, {
          waitUntil: "domcontentloaded",
          timeout: 20000,
        })
        .catch(() => {});
    }

    // Dismiss First Run Wizard modal if presented
    const wizard = tenantPage.locator('#firstrunwizard, [role="dialog"], .modal-mask');
    if (await wizard.isVisible({ timeout: 4000 }).catch(() => false)) {
      await tenantPage.keyboard.press("Escape").catch(() => {});
      const closeBtn = tenantPage
        .locator(
          '#firstrunwizard button[aria-label="Close"], button.modal-container__close, button:has-text("Close")'
        )
        .first();
      if (await closeBtn.isVisible({ timeout: 1500 }).catch(() => false)) {
        await closeBtn.click({ force: true }).catch(() => {});
      }
    }

    // Verify session and basic storage access (/index.php/apps/files/)
    const authenticatedLayout = tenantPage.locator(
      "#app-content, #app-content-files, #fileList, .files-list, #header, #appmenu, .app-navigation, main"
    );
    await expect(authenticatedLayout.first()).toBeVisible({ timeout: 20000 });
  } finally {
    await tenantContext.close();
  }
}

/**
 * Execute tenant deprovisioning cleanup via SuperAdmin UI popconfirm modal.
 * Triggers DELETE /api action and waits for the tenant row to be removed from the table.
 */
export async function deprovisionTenantViaUI(
  page: Page,
  tenantId: string,
  timeoutMs: number = 60000
): Promise<void> {
  // Filter or search for target tenant
  const searchInput = page
    .getByPlaceholder(/Search by Tenant ID/i)
    .or(page.locator('input[placeholder*="Search"]'))
    .first();

  if (await searchInput.isVisible({ timeout: 3000 }).catch(() => false)) {
    await searchInput.fill(tenantId);
    await page.waitForTimeout(500);
  }

  const row = page.locator("tr").filter({ hasText: tenantId }).first();
  await expect(row).toBeVisible({ timeout: 15000 });

  // Locate Delete action button:
  // In Shadcn/Lucide TenantTable: it is in the "More actions" DropdownMenu.
  // In classic Ant Design: it may be a direct button on the row.
  const directDeleteBtn = row
    .locator(
      'button[title="Delete Tenant"], button:has(svg.lucide-trash-2), button:has(.anticon-delete), button.text-red-500'
    )
    .first();

  if (await directDeleteBtn.isVisible({ timeout: 1500 }).catch(() => false)) {
    await directDeleteBtn.click();
  } else {
    // Open the More actions dropdown menu on the row
    const moreActionsBtn = row
      .locator(
        'button[aria-label="More actions"], button:has(svg.lucide-more-horizontal)'
      )
      .first();
    await expect(moreActionsBtn).toBeVisible({ timeout: 5000 });
    await moreActionsBtn.click();

    // Click "Delete Tenant" item in dropdown
    const deleteMenuItem = page
      .locator('[role="menuitem"], .dropdown-menu-item, div')
      .filter({ hasText: /Delete Tenant/i })
      .first();
    await expect(deleteMenuItem).toBeVisible({ timeout: 5000 });
    await deleteMenuItem.click();
  }

  // Confirm delete dialog: "Permanently Delete Tenant?"
  const confirmDialog = page
    .locator('[role="dialog"], .ant-modal, .ant-popconfirm')
    .filter({ hasText: /Permanently Delete|Delete tenant/i })
    .first();
  await expect(confirmDialog).toBeVisible({ timeout: 5000 });

  // Click Delete button in dialog footer
  const confirmBtn = confirmDialog
    .getByRole("button", { name: /^Delete$/i })
    .or(confirmDialog.locator('button:has-text("Delete"), button.bg-destructive'))
    .first();
  await confirmBtn.click();

  // If TenantProgressModal opens, dismiss/close it so it doesn't block the UI
  const progressCloseBtn = page
    .locator('[role="dialog"]')
    .filter({ hasText: /Deprovisioning Teardown/i })
    .locator('button:has-text("Close")')
    .first();
  if (await progressCloseBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
    await progressCloseBtn.click().catch(() => {});
  }

  // Verify tenant row is completely removed from table
  await expect(page.locator("tr").filter({ hasText: tenantId })).not.toBeVisible({
    timeout: timeoutMs,
  });
}

/**
 * Direct Control Plane API teardown fallback ensuring zero residual tenant resources
 * remain even if earlier test assertions or UI interactions encounter unexpected errors.
 */
export async function deprovisionTenantViaApi(
  request: APIRequestContext,
  consoleUrl: string,
  tenantId: string,
  token?: string
): Promise<void> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const apiEndpoint = `${consoleUrl.replace(/\/+$/, "")}/api`;
  try {
    await request.post(apiEndpoint, {
      headers,
      data: {
        action: "DELETE",
        tenant_id: tenantId,
      },
      ignoreHTTPSErrors: true,
      timeout: 15000,
    });
  } catch {
    // Teardown guardrail best-effort cleanup
  }
}
