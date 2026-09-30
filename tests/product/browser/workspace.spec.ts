import { test, expect } from "@playwright/test";
import { mkdir } from "node:fs/promises";
test("create, evaluate, inspect and continue a local object", async ({
  page,
  request,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Objects", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "+ New object" }).click();
  await page.getByLabel("Object name", { exact: true }).fill("Browser sensor");
  await page.getByLabel("Object ID", { exact: true }).fill("browser-sensor");
  await page.getByLabel("New iterations").fill("1");
  await page.getByLabel("Provider").selectOption("replay");
  await page.getByRole("button", { name: "Start run", exact: true }).click();
  await expect(page).toHaveURL(/object\/\?id=browser-sensor/);
  await expect
    .poll(
      async () => {
        const r = await request.get("/api/v1/objects/browser-sensor");
        return (await r.json()).runs[0].status;
      },
      { timeout: 150000 },
    )
    .toBe("completed");
  // API completion can precede the UI's last live refresh and model swap.
  await expect(
    page.getByRole("region", { name: "Run progress" }).locator("strong"),
  ).toHaveText("completed");
  await expect(page.getByTestId("iteration-card")).toHaveCount(2);
  await expect(page.getByText("Best passing", { exact: true })).toBeVisible();
  await expect(
    page.locator("[data-geometry-ready=true]").first(),
  ).toBeVisible();
  await expect(page.locator("canvas").first()).toBeVisible();
  const canvas = page.locator("canvas").first(),
    box = await canvas.boundingBox();
  await expect(async () => {
    // Inspect the composited image the user sees, not the renderer's
    // currently bound WebGL framebuffer. Keep the visible-geometry check.
    const screenshot = await canvas.screenshot({ timeout: 3000 });
    const colored = await page.evaluate(async (png) => {
      const image = new Image();
      image.src = `data:image/png;base64,${png}`;
      await image.decode();
      const copy = document.createElement("canvas");
      copy.width = image.width;
      copy.height = image.height;
      const context = copy.getContext("2d")!;
      context.drawImage(image, 0, 0);
      const p = context.getImageData(0, 0, copy.width, copy.height).data;
      let colored = 0;
      for (let i = 0; i < p.length; i += 4)
        if (p[i] > p[i + 1] * 1.12 && p[i] > p[i + 2] * 1.12) colored++;
      return colored;
    }, screenshot.toString("base64"));
    expect(colored).toBeGreaterThan(100);
  }).toPass({ timeout: 10000 });
  if (box) {
    await page.mouse.move(box.x + 100, box.y + 100);
    await page.mouse.down();
    await page.mouse.move(box.x + 170, box.y + 120);
    await page.mouse.up();
  }
  const step = page.getByRole("link", { name: "STEP ↓" }).first();
  const download = await request.get((await step.getAttribute("href"))!);
  expect(download.status()).toBe(200);
  expect((await download.text()).slice(0, 100)).toContain("ISO-10303");
  await mkdir("runtime/product-screenshots", { recursive: true });
  await page.screenshot({
    path: "runtime/product-screenshots/object.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Continue from best" }).click();
  await page
    .getByLabel("Task description")
    .fill("Continue reducing mass while retaining all fixed checks.");
  await page.getByRole("button", { name: "Start run", exact: true }).click();
  await expect
    .poll(
      async () => {
        const r = await request.get("/api/v1/objects/browser-sensor");
        const d = await r.json();
        return d.runs.length === 2 && d.runs[0].status === "completed";
      },
      { timeout: 150000 },
    )
    .toBe(true);
  await expect(page.getByText("a previous run", { exact: true })).toBeVisible();
  const data = await (
    await request.get("/api/v1/objects/browser-sensor")
  ).json();
  expect(data.runs[0].parent_run_id).toBe(data.runs[1]._id);
  await page.reload();
  await expect(page.getByTestId("iteration-card")).toHaveCount(2);
  await page.goto("/");
  await expect(page.getByTestId("object-card")).toHaveCount(1);
  await expect(
    page.locator("[data-geometry-ready=true]").first(),
  ).toBeVisible();
  await page.screenshot({
    path: "runtime/product-screenshots/gallery.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.getByRole("link", { name: "View iterations" }).click();
  await expect(page.getByTestId("iteration-card")).toHaveCount(2);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  expect(errors).toEqual([]);
});
test("invalid YAML and cross-origin starts are rejected", async ({
  page,
  request,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "+ New object" }).click();
  await page.getByText("Load YAML configuration", { exact: true }).click();
  await page
    .getByLabel("YAML configuration", { exact: true })
    .fill("version: 999\nobject: bad");
  await page.getByRole("button", { name: "Apply YAML" }).click();
  await expect(
    page.getByRole("dialog", { name: "New object" }).getByRole("alert"),
  ).toBeVisible();
  const r = await request.post("/api/v1/runs", {
    headers: { Origin: "https://foreign.example" },
    data: { yaml: "version: 1" },
  });
  expect(r.status()).toBe(403);
});
