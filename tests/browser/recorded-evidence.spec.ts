import { test, expect } from '@playwright/test';
import { createHash } from 'node:crypto';

test('native evidence downloads agree with manifests and display failed candidates', async ({page,request})=>{
 for (const slug of ['structural','mechanism']) {
  await page.goto(`/${slug}`);
  await expect(page.locator('[data-geometry-ready=true]').first()).toBeVisible();
  await expect(page.getByTestId('design-card').first()).toContainText('Physical failure');
  await expect(page.getByTestId('design-card').last()).toContainText('Accepted under stated tests');
  if(slug==='mechanism') {
   await expect(page.getByTestId('design-card')).toHaveCount(5);
   await expect(page.getByTestId('design-card').nth(1)).toContainText('Invalid setup');
   await expect(page.getByRole('img',{name:/Recorded lift trajectory/})).toBeVisible();
  }
  const disclosure=page.getByText('Report and provenance',{exact:true});
  await disclosure.focus();await page.keyboard.press('Enter');
  await expect(page.getByRole('link',{name:'Artifact checksum manifest'})).toBeVisible();
  const manifest=await (await request.get(`/studies/${slug}/manifest.json`)).json();
  for(const [url,expected] of Object.entries(manifest.files) as [string,{sha256:string;bytes:number}][]) {
   const response=await request.get(url);expect(response.ok()).toBeTruthy();
   const data=await response.body();expect(data.length).toBe(expected.bytes);
   expect(createHash('sha256').update(data).digest('hex')).toBe(expected.sha256);
  }
  await page.screenshot({path:`runtime/product-screenshots/${slug}-desktop.png`,fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await page.evaluate(()=>window.scrollTo(0,0));
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:`runtime/product-screenshots/${slug}-mobile.png`,fullPage:true});
  await page.setViewportSize({width:1440,height:1000});
 }
});

test('docs expose both journeys, adapter scopes, evidence and rendered architecture',async({page,request})=>{
 await page.goto('/docs');
 await expect(page.getByRole('link',{name:'External coding agent →',exact:true})).toBeVisible();
 await expect(page.getByRole('link',{name:'Built-in agent →',exact:true})).toBeVisible();
 const paths=await page.locator('a[href^="/docs/"]').evaluateAll(as=>as.map(a=>a.getAttribute('href')!));
 for(const path of new Set(paths)) expect((await request.get(path)).ok(),path).toBeTruthy();
 await page.goto('/docs/architecture/');
 await expect(page.getByRole('group',{name:'Shared experiment lifecycle'})).toBeVisible();
 await expect(page.locator('code.language-mermaid')).toHaveCount(0);
 await page.goto('/docs/quickstart/');
 const href=await page.getByRole('link',{name:'complete external journey'}).getAttribute('href');
 await page.goto(href!);
 await expect(page.locator('#external-coding-agent-no-model-key-or-database')).toBeVisible();
 expect((await request.get('/docs/evidence/mechanism-results.json')).ok()).toBeTruthy();
 await page.setViewportSize({width:390,height:844}); await page.goto('/docs');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test('a missing model has an accessible fallback while CAD download stays available',async({page})=>{
 await page.route('**/studies/structural/*model.glb',route=>route.abort());
 await page.goto('/structural');
 await expect(page.getByText('Preview unavailable. STEP download remains available.').first()).toBeVisible();
 await expect(page.getByRole('link',{name:'Download STEP'}).first()).toHaveAttribute('href',/\.step$/);
});
