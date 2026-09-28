import { test, expect } from "@playwright/test";
import data from "../../web/data/vtol-gallery.json";

test("VTOL gallery displays archived aircraft, layout views and measured benchmarks", async ({ page, request }) => {
  const errors: string[] = [];
  page.on("pageerror", e => errors.push(e.message));
  await page.goto("/vtol");
  const overview = page.getByTestId("overview-model");
  await expect(overview.getByTestId("vtol-canvas")).toHaveAttribute("data-loaded", "true", { timeout: 30000 });
  await overview.getByRole("button", { name: "Internal layout", exact: true }).click();
  await expect(overview).toHaveAttribute("data-view", "internal");
  await expect(overview.getByTestId("vtol-canvas")).toHaveAttribute("data-loaded", "true");
  await page.screenshot({ path: "runtime/vtol-internal.png" });
  await overview.getByRole("button", { name: "Exterior", exact: true }).click();
  await page.waitForTimeout(500);
  await page.screenshot({ path: "runtime/vtol-overview.png" });
  const cards = page.getByTestId("design-card");
  await expect(cards).toHaveCount(data.designs.length);
  for (let i = 0; i < data.designs.length; i++) {
    const card = cards.nth(i);
    await card.scrollIntoViewIfNeeded();
    if (data.designs[i].assets["model.glb"]) await expect(card.getByTestId("vtol-canvas")).toHaveAttribute("data-loaded", "true", { timeout: 30000 });
    await expect(card.getByText("Range est.", { exact: true })).toBeVisible();
    await expect(card.getByText("Payload capacity est.", { exact: true })).toBeVisible();
  }
  await cards.first().getByText("Physics results and agent reflection", { exact: true }).click();
  await expect(cards.first().getByRole("img", { name: "Electrical cruise power versus airspeed" })).toBeVisible();
  await cards.first().getByRole("button", { name: "Expand iteration 1" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();
  const step = await request.get(data.designs[0].assets["model.step"]);
  expect(await step.text()).toContain("ISO-10303-21");
  await page.screenshot({ path: "runtime/vtol-gallery.png", fullPage: true });
  expect(errors).toEqual([]);
});

test("VTOL results remain concise and usable on laptop and mobile", async ({ page }) => {
  await page.goto("/vtol");
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  }
  const physics = page.locator("details", { has: page.locator("summary", { hasText: "Agent harness setup and physics" }) });
  await expect(physics).not.toHaveAttribute("open", "");
  await physics.locator("summary").click();
  await expect(physics.getByRole("link", { name: "UIUC experimental propeller data" })).toBeVisible();
  await physics.locator("summary").click();
  await page.screenshot({ path: "runtime/vtol-mobile.png", fullPage: true });
});
