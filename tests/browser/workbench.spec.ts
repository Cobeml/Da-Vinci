import { test, expect } from "@playwright/test";

test("renders measured CAD and navigates memory, tools, archive, and settings", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "From constraints to possibility." }),
  ).toBeVisible();
  await expect(page.locator(".viewport-label")).toContainText(
    "EVALUATED CAD GEOMETRY",
    { timeout: 30000 },
  );
  await expect(page.getByTestId("cad-canvas").locator("canvas")).toBeVisible();
  await page.getByRole("button", { name: "Top view", exact: true }).click();
  await page.getByRole("button", { name: "Side view", exact: true }).click();
  await page
    .getByRole("button", { name: "Isometric view", exact: true })
    .click();
  await page.getByRole("button", { name: "Toggle wireframe" }).click();
  await page.getByRole("button", { name: "Toggle wireframe" }).click();
  await page.screenshot({
    path: "runtime/workbench-desktop.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Memory", exact: true }).click();
  await expect(
    page.getByText("Feasible geometry archived").first(),
  ).toBeVisible();
  await page.getByRole("button", { name: "Tools", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "directional_projected_area" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Archive", exact: true }).click();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("link", { name: "Export run bundle" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/run-.*\.zip/);
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await expect(page.getByLabel("Maximum design rounds")).toHaveValue("4");
  expect(errors).toEqual([]);
});

test("mobile workbench stays within viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByTestId("cad-canvas")).toBeVisible();
  await page.screenshot({
    path: "runtime/workbench-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
});

test("run can be started and stopped through the interface", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Start replay run" }).click();
  await expect(page.getByRole("button", { name: "Stop run" })).toBeVisible();
  await page.getByRole("button", { name: "Stop run" }).click();
  await expect(
    page.getByRole("button", { name: "Start replay run" }),
  ).toBeVisible();
  await expect(
    page
      .getByText("Run stopped; active containers are being cancelled")
      .first(),
  ).toBeVisible();
});
