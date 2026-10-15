import { defineConfig, devices } from "@playwright/test";
import path from "node:path";
export default defineConfig({
  testDir: ".",
  testMatch: "**/*.spec.ts",
  outputDir: path.join(__dirname, "test-results"),
  fullyParallel: false,
  workers: 1,
  timeout: 120000,
  expect: { timeout: 15000 },
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { open: "never", outputFolder: path.join(__dirname, "playwright-report") }]],
  use: {
    actionTimeout: 15000,
    baseURL: process.env.AEGIS_TEST_BASE_URL || "http://127.0.0.1:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
          ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH }
          : {},
      },
    },
  ],
});
