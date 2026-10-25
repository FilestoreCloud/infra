/**
 * SPDX-FileCopyrightText: 2024 Nextcloud GmbH and Nextcloud contributors
 * SPDX-License-Identifier: AGPL-3.0-or-later
 */

import { defineConfig, devices } from "@playwright/test";

const defaultBaseUrl =
  process.env.TENANT_URL ||
  (process.env.TENANT_DOMAIN ? `https://${process.env.TENANT_DOMAIN}` : undefined);

export default defineConfig({
  testDir: "./specs",
  timeout: 120000,
  expect: {
    timeout: 15000,
  },
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: defaultBaseUrl,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    ignoreHTTPSErrors: true,
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        launchOptions: {
          args: [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-web-security",
            defaultBaseUrl
              ? `--unsafely-treat-insecure-origin-as-secure=${defaultBaseUrl}`
              : "",
          ].filter(Boolean),
        },
      },
    },
  ],
});
