// Reuse real website renders; generate vector QR codes and one-page print PDFs.
// npm install --prefix /tmp/davinci-flyer-tools --no-audit --no-fund qrcode jsqr
// node scripts/build_flyer.mjs
import { chromium } from "@playwright/test";
import sharp from "sharp";
import { createRequire } from "node:module";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const require = createRequire(import.meta.url);
const toolRoot = process.env.DAVINCI_FLYER_TOOLS || "/tmp/davinci-flyer-tools";
const QRCode = require(`${toolRoot}/node_modules/qrcode`);
const jsQR = require(`${toolRoot}/node_modules/jsqr`);
const source = "https://da-vinci-psi.vercel.app";
const output = resolve("docs/flyer");
await mkdir(`${output}/assets`, { recursive: true });
const data = JSON.parse(await readFile("web/data/sensor-gallery.json", "utf8"));
const passing = data.designs.filter((d) => d.evaluation.outcome === "passed");
const best = passing.reduce((a, b) =>
  a.evaluation.metrics.mass_g.value < b.evaluation.metrics.mass_g.value ? a : b,
);
const links = {
  demo: `${source}/demo`,
  github: "https://github.com/Cobeml/Da-Vinci",
};
for (const [name, url] of Object.entries(links)) {
  const svg = await QRCode.toString(url, {
    type: "svg", errorCorrectionLevel: "M", margin: 4, color: { dark: "#000000", light: "#ffffff" },
  });
  await writeFile(`${output}/assets/qr-${name}.svg`, svg);
  const { data: pixels, info } = await sharp(Buffer.from(svg)).resize(600, 600).ensureAlpha().raw().toBuffer({ resolveWithObject: true });
  const decoded = jsQR(new Uint8ClampedArray(pixels), info.width, info.height);
  if (decoded?.data !== url) throw Error(`QR verification failed: ${name}`);
}

const browser = await chromium.launch({ args: ["--enable-unsafe-swiftshader"] });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 }, deviceScaleFactor: 3 });
  await page.goto(`${source}/sensor`, { waitUntil: "networkidle" });
  async function capture(locator, name, width, height, zoomSteps = 0) {
    await locator.evaluate((element, size) => {
      element.style.cssText += `;position:fixed;inset:0 auto auto 0;width:${size[0]}px;height:${size[1]}px;z-index:9999;border-radius:0`;
    }, [width, height]);
    const canvas = locator.getByTestId("sensor-canvas");
    await canvas.waitFor();
    await page.waitForFunction((element) => element?.dataset.loaded === "true", await canvas.elementHandle());
    await page.waitForTimeout(1400);
    if (zoomSteps) {
      await canvas.hover();
      for (let step = 0; step < zoomSteps; step++) {
        await page.mouse.wheel(0, -100);
        await page.waitForTimeout(35);
      }
      await page.waitForTimeout(700);
    }
    await canvas.screenshot({ path: `${output}/assets/${name}.png` });
    await locator.evaluate((element) => element.removeAttribute("style"));
  }
  await capture(page.getByTestId("overview-model"), "mounted-sensor", 1100, 390, 10);
  // Hide viewer controls only for the asset capture; the live website is untouched.
  await page.addStyleTag({ content: '[class*="viewBar"], [class*="viewHint"] { visibility:hidden !important; }' });
  for (const [iteration, name] of [[passing[0].iteration, "mount-before"], [best.iteration, "mount-after"]]) {
    await capture(page.locator(`#iteration-${iteration} [class*="modelView"]`).first(), name, 500, 320);
  }
  await page.close();

  const print = await browser.newPage({ viewport: { width: 816, height: 1056 }, deviceScaleFactor: 2 });
  await print.goto(pathToFileURL(`${output}/flyer.html`).href, { waitUntil: "networkidle" });
  await print.evaluate(() => document.fonts.ready);
  await print.emulateMedia({ media: "print" });
  const bounds = await print.locator(".sheet").evaluate((el) => ({ width: el.scrollWidth, height: el.scrollHeight }));
  if (bounds.width > 816 || bounds.height > 1056) throw Error(`Flyer overflow: ${JSON.stringify(bounds)}`);
  const footer = await print.locator("footer").boundingBox();
  if (footer.y + footer.height > 1028) throw Error("Footer extends into the print margin");
  await print.pdf({ path: `${output}/da-vinci-flyer-letter.pdf`, format: "Letter", printBackground: true, preferCSSPageSize: true, tagged: true });
  await print.screenshot({ path: `${output}/preview.png`, fullPage: true });
  await print.addStyleTag({ content: "@page { size: A4; margin: 0; } .sheet { zoom: 0.972; }" });
  await print.pdf({ path: `${output}/da-vinci-flyer-a4.pdf`, format: "A4", printBackground: true, preferCSSPageSize: true, tagged: true });
  await writeFile(`${output}/evidence.json`, JSON.stringify({
    source, captured_at: new Date().toISOString(), links,
    baseline_mass_g: passing[0].evaluation.metrics.mass_g.value,
    best_mass_g: best.evaluation.metrics.mass_g.value,
    best_iteration: best.iteration,
    mass_reduction_percent: (1 - best.evaluation.metrics.mass_g.value / passing[0].evaluation.metrics.mass_g.value) * 100,
    qr_codes_verified: true,
    image_source: "Screenshots of the live website's actual CAD viewers; no generated replacement geometry.",
  }, null, 2) + "\n");
  console.log("Created Letter/A4 PDFs and preview; both QR destinations verified.");
} finally {
  await browser.close();
}
