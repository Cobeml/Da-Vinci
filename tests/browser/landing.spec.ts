import { test, expect } from "@playwright/test";

test("landing contains only branding, navigation and the mounted sensor preview", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Da Vinci", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("img", { name: "Da Vinci logo" })).toBeVisible();
  await expect(
    page.getByText("Recursive Improvement CAD harness", { exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("link")).toHaveCount(5);
  await expect(page.getByRole("link", { name: "GitHub" })).toHaveAttribute(
    "href", "https://github.com/Cobeml/Da-Vinci",
  );
  const model = page.getByTestId("sensor-canvas");
  await expect(model).toHaveAttribute("data-mounted", "true");
  await expect(model).toHaveAttribute("data-loaded", "true", {
    timeout: 30000,
  });
  await page.waitForTimeout(600);
  await page.screenshot({
    path: "runtime/landing-desktop.png",
    fullPage: true,
  });
  await page.getByRole("link", { name: "Demo" }).click();
  await expect(page).toHaveURL(/\/demo$/);
  await page.goto("/");
  await page.getByRole("link", { name: "Docs" }).click();
  await expect(page).toHaveURL(/\/docs$/);
  await page.goto("/");
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(model).toHaveAttribute("data-loaded", "true");
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
  await page.waitForTimeout(500);
  await page.screenshot({ path: "runtime/landing-mobile.png", fullPage: true });
  expect(errors).toEqual([]);
});
