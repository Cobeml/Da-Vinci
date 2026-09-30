import { test, expect } from "@playwright/test";
import data from "../../web/data/gripper-gallery.json";

test("gripper gallery loads evaluated CAD and independently moves jaws and displays frame stress", async ({
  page,
  request,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/gripper");
  const overview = page.getByTestId("overview-model");
  await expect(overview.getByTestId("gripper-canvas")).toHaveAttribute(
    "data-loaded",
    "true",
    { timeout: 30000 },
  );
  await overview.getByRole("button", { name: "On VTOL", exact: true }).click();
  await expect(overview.getByTestId("gripper-canvas")).toHaveAttribute(
    "data-mounted",
    "true",
  );
  await overview.getByRole("slider", { name: "Jaw opening" }).fill("20");
  await expect(overview.getByTestId("gripper-canvas")).toHaveAttribute(
    "data-gap",
    "20",
  );
  await page.waitForTimeout(700);
  await page.screenshot({ path: "runtime/gripper-mounted.png" });
  await overview
    .getByRole("button", { name: "Frame stress", exact: true })
    .click();
  await expect(overview.getByTestId("gripper-canvas")).toHaveAttribute(
    "data-frame",
    "true",
  );
  await overview.getByRole("button", { name: "CAD", exact: true }).click();
  await overview.getByRole("button", { name: "Gripper", exact: true }).click();
  await expect(overview.getByTestId("gripper-canvas")).toHaveAttribute(
    "data-mounted",
    "false",
  );
  await page.waitForTimeout(600);
  await page.screenshot({ path: "runtime/gripper-overview.png" });
  const cards = page.getByTestId("design-card");
  await expect(cards).toHaveCount(data.designs.length);
  for (let i = 0; i < data.designs.length; i++) {
    if (!data.designs[i].assets["model.glb"]) continue;
    const card = cards.nth(i),
      canvas = card.getByTestId("gripper-canvas");
    await card.scrollIntoViewIfNeeded();
    await expect(canvas).toHaveAttribute("data-loaded", "true", {
      timeout: 30000,
    });
    await card.getByRole("slider", { name: "Jaw opening" }).fill("35");
    await expect(canvas).toHaveAttribute("data-gap", "35");
    await card
      .getByRole("button", { name: "Frame stress", exact: true })
      .click();
    await expect(canvas).toHaveAttribute("data-frame", "true");
    if (i === 0) {
      await page.waitForTimeout(600);
      await card.screenshot({ path: "runtime/gripper-frame.png" });
    }
    await card.getByRole("button", { name: "CAD", exact: true }).click();
  }
  await cards
    .first()
    .getByRole("button", { name: "On VTOL", exact: true })
    .click();
  await expect(cards.first().getByTestId("gripper-canvas")).toHaveAttribute(
    "data-mounted",
    "true",
  );
  await expect(cards.nth(1).getByTestId("gripper-canvas")).toHaveAttribute(
    "data-mounted",
    "false",
  );
  await cards
    .first()
    .getByRole("button", { name: "Expand iteration 1" })
    .click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(
    page.getByRole("dialog").getByTestId("gripper-canvas"),
  ).toHaveAttribute("data-mounted", "true");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Gripper", exact: true })
    .click();
  await expect(
    page.getByRole("dialog").getByTestId("gripper-canvas"),
  ).toHaveAttribute("data-mounted", "false");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();
  const model = await request.get(data.designs[0].assets["model.step"]);
  expect(await model.text()).toContain("ISO-10303-21");
  expect(data.publishable).toBe(true);
  expect(data.reduction_percent).toBeGreaterThanOrEqual(15);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(500);
  await page.screenshot({
    path: "runtime/gripper-gallery.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
});

test("gripper overview and details fit laptop and mobile screens", async ({
  page,
}) => {
  await page.goto("/gripper");
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(width);
  }
  const summary = page.locator("summary", { hasText: "Agent harness setup" });
  await summary.click();
  await expect(
    page.getByRole("heading", { name: "Fixed acceptance checks" }),
  ).toBeVisible();
  await summary.click();
  await page.screenshot({ path: "runtime/gripper-mobile.png", fullPage: true });
});
