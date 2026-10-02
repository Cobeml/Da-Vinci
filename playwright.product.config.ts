import { defineConfig } from "@playwright/test";
export default defineConfig({
  outputDir: "test-results/product",
  testDir: "tests/product/browser",
  timeout: 180000,
  workers: 1,
  reporter: process.env.CI ? [["list"], ["github"]] : "list",
  use: {
    baseURL: "http://127.0.0.1:8742",
    viewport: { width: 1440, height: 1000 },
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    launchOptions: { args: ["--enable-unsafe-swiftshader"] },
  },
  webServer: {
    command: ".venv/bin/python -m scripts.product_browser",
    url: "http://127.0.0.1:8742/api/v1/health",
    timeout: 30000,
    reuseExistingServer: false,
  },
});
