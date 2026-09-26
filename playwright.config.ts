import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests/browser",
  timeout: process.env.DAVINCI_E2E_ATLAS === "1" ? 420000 : 90000,
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:3215",
    viewport: { width: 1440, height: 1000 },
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    launchOptions: { args: ["--enable-unsafe-swiftshader"] },
  },
});
