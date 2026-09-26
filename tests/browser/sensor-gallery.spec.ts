import { test, expect } from "@playwright/test";
import data from "../../web/data/sensor-gallery.json";

test("gallery shows every measured design and independent VTOL controls", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", e => errors.push(e.message));
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Da Vinci/ })).toBeVisible();
  const overview = page.getByRole("region", { name: "Project overview" });
  const selected = overview.getByTestId("sensor-canvas");
  await expect(selected).toHaveAttribute("data-loaded", "true", { timeout: 30000 });
  await expect(selected).toHaveAttribute("data-mounted", "true");
  await expect(overview.getByRole("heading", { name: "MongoDB Atlas" })).toBeVisible();
  for (const [name, url] of [
    ["Reflexion (2023)", "https://arxiv.org/abs/2303.11366"],
    ["Voyager (2023)", "https://voyager.minedojo.org/"],
    ["Self-Refine (2023)", "https://arxiv.org/abs/2303.17651"],
  ]) await expect(overview.getByRole("link", { name: new RegExp(name.replace(/[()]/g, "\\$&")) })).toHaveAttribute("href", url);
  await overview.getByRole("button", { name: /Expand iteration/ }).click();
  await expect(page.getByRole("dialog").getByTestId("sensor-canvas")).toHaveAttribute("data-mounted", "true");
  await page.keyboard.press("Escape");
  await page.waitForTimeout(700);
  await page.screenshot({ path: "runtime/sensor-overview.png" });
  await overview.getByRole("link", { name: "View all 8 iterations" }).click();
  await expect(page).toHaveURL(/#designs$/);
  const cards = page.getByTestId("design-card");
  await expect(cards).toHaveCount(data.designs.length);
  await expect(page.getByText("From constraints to possibility.")).toHaveCount(0);
  for (let i = 0; i < data.designs.length; i++) {
    const card = cards.nth(i);
    await card.scrollIntoViewIfNeeded();
    const canvas = card.getByTestId("sensor-canvas");
    await expect(canvas).toHaveAttribute("data-loaded", "true", { timeout: 30000 });
    await expect(card.getByText(data.designs[i].evaluation.metrics.mass_g.value.toFixed(1), { exact: false }).first()).toBeVisible();
    await card.getByRole("button", { name: "On VTOL", exact: true }).click();
    await expect(canvas).toHaveAttribute("data-mounted", "true");
    await expect(card.getByText("VTOL reference · mount highlighted")).toBeVisible();
    if (i === 0) {
      await expect(cards.nth(1).getByTestId("sensor-canvas")).toHaveAttribute("data-mounted", "false");
      await page.waitForTimeout(1000);
      await card.screenshot({ path: "runtime/sensor-mounted.png" });
    }
    await card.getByRole("button", { name: "Mount", exact: true }).click();
    await expect(canvas).toHaveAttribute("data-mounted", "false");
  }
  await cards.first().getByRole("button", { name: "Expand iteration 1" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("dialog").getByRole("button", { name: "On VTOL", exact: true }).click();
  await page.waitForTimeout(1000);
  await page.screenshot({ path: "runtime/sensor-expanded.png" });
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(1000);
  await page.screenshot({ path: "runtime/sensor-gallery.png", fullPage: true });
  expect(errors).toEqual([]);
});

test("gallery is usable at laptop and mobile widths and exports actual STEP", async ({ page, request }) => {
  await page.goto("/");
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await expect(page.getByTestId("design-card").first()).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  }
  await expect(page.getByTestId("sensor-canvas").first()).toHaveAttribute("data-loaded", "true", { timeout: 30000 });
  await page.waitForTimeout(600);
  await page.screenshot({ path: "runtime/sensor-gallery-mobile.png", fullPage: true });
  const model = await request.get(data.designs[0].step_url);
  expect(model.ok()).toBeTruthy();
  expect(await model.text()).toContain("ISO-10303-21");
  const passing = data.designs.filter(d => d.evaluation.outcome === "passed");
  expect(Math.min(...passing.map(d => d.evaluation.metrics.mass_g.value))).toBeLessThan(passing[0].evaluation.metrics.mass_g.value);
});
