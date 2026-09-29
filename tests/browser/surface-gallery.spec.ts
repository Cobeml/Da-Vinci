import { test, expect } from "@playwright/test";
import data from "../../web/data/surface-gallery.json";

test("homepage does not advertise paused beta tools", async ({page})=>{
  await page.goto("/");
  await expect(page.getByTestId("surface-overview")).toHaveCount(0);
  await expect(page.locator('a[href="/vtol-tools"]')).toHaveCount(0);
  await expect(page.getByTestId("overview-model")).toBeVisible();
});

test("surface study shows matched progress, CAD and benchmark evidence", async ({ page, request }) => {
  const errors:string[]=[];
  page.on("pageerror",e=>errors.push(e.message));
  await page.goto("/vtol-tools");
  await expect(page.getByText("Beta · paused VTOL geometry-tool experiment",{exact:true})).toBeVisible();
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content","noindex, nofollow");
  await expect(page.getByRole("heading",{name:"Design progress",exact:true})).toBeVisible();
  await expect(page.getByTestId("surface-card")).toHaveCount(data.designs.length);
  await expect(page.getByText("Recorded tool results",{exact:true})).toHaveCount(data.designs.filter(d=>d.tool_evidence.length>0).length);
  if (Object.keys(data.validation).length) await expect(page.getByRole("definition").filter({hasText:"km est."})).toHaveCount(3);
  if (data.designs.length) {
    const hero=page.getByTestId("surface-overview");
    await expect(hero.getByTestId("vtol-canvas")).toHaveAttribute("data-loaded","true",{timeout:30000});
    await page.screenshot({path:"runtime/surface-overview.png"});
    await hero.getByRole("button",{name:"Internal layout",exact:true}).click();
    await expect(hero).toHaveAttribute("data-view","internal");
    await expect(hero.getByTestId("vtol-canvas")).toHaveAttribute("data-loaded","true");
    await hero.getByRole("button",{name:"Exterior",exact:true}).click();
    const research=page.locator("details").filter({has:page.locator("summary",{hasText:"Research, physics and validation limits"})});
    await expect(research).not.toHaveAttribute("open","");
    await research.locator("summary").click();
    await expect(research.getByRole("link",{name:"NeuralFoil",exact:true})).toBeVisible();
    await research.locator("summary").click();
    await page.getByRole("button",{name:"CST + surface tools",exact:true}).click();
    const rows=data.designs.filter(d=>d.arm==="surface_tools");
    await expect(page.getByTestId("surface-card")).toHaveCount(rows.length);
    const first=page.getByTestId("surface-card").first();
    await first.getByText("Airfoil sections",{exact:true}).click();
    await expect(first.getByRole("img",{name:"Baseline, root and tip airfoil comparison"})).toBeVisible();
    await first.getByText("Airfoil sections",{exact:true}).click();
    for (let i=0;i<rows.length;i++) {
      const card=page.getByTestId("surface-card").nth(i);
      await card.scrollIntoViewIfNeeded();
      await expect(card.getByText("Range est.",{exact:true})).toBeVisible();
      if (rows[i].assets["model.glb"]) await expect(card.getByTestId("vtol-canvas")).toHaveAttribute("data-loaded","true",{timeout:30000});
      const evidence=card.locator("details").filter({has:page.locator("summary",{hasText:"Recorded tool results"})});
      if (await evidence.count()) {
        await expect(evidence).not.toHaveAttribute("open","");
        await evidence.locator("summary").click();
        await expect(evidence.locator("pre").first()).toBeVisible();
        expect(await evidence.locator("pre").count()).toBeGreaterThanOrEqual(2);
        await evidence.locator("summary").click();
      }
    }
    await page.getByRole("button",{name:"Dimensional controls",exact:true}).click();
    const controls=data.designs.filter(d=>d.arm==="control");
    await expect(page.getByTestId("surface-card")).toHaveCount(controls.length);
    for (let i=0;i<controls.length;i++) {
      const card=page.getByTestId("surface-card").nth(i);
      await card.scrollIntoViewIfNeeded();
      if (controls[i].assets["model.glb"]) await expect(card.getByTestId("vtol-canvas")).toHaveAttribute("data-loaded","true",{timeout:30000});
    }
    const withStep=data.designs.find(d=>d.assets["model.step"]);
    if (withStep) expect(await (await request.get(withStep.assets["model.step"])).text()).toContain("ISO-10303-21");
  }
  for (const width of [1280,390]) {
    await page.setViewportSize({width,height:900});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  }
  await page.screenshot({path:"runtime/surface-mobile.png",fullPage:true});
  expect(errors).toEqual([]);
});
