import {test,expect} from '@playwright/test';
test('recorded object gallery leads with native cases and preserves historical studies',async({page})=>{
 await page.goto('/demo');
 const cards=page.getByTestId('object-card');
 await expect(cards).toHaveCount(5);
 await expect(cards.nth(0)).toContainText('Structural bracket');
 await expect(cards.nth(1)).toContainText('Vertical slider');
 await expect(page.getByText('Read-only demo · no API calls')).toBeVisible();
 await expect(page.locator('a[href="/vtol-tools"]')).toHaveCount(0);
 for(const [title,url] of [['Structural bracket','/structural'],['Vertical slider','/mechanism'],['Sensor mount','/sensor'],['Parallel gripper','/gripper'],['Survey VTOL','/vtol']]){
  await page.goto('/demo');
  await page.getByRole('link',{name:new RegExp(title)}).click();
  await expect(page).toHaveURL(new RegExp(url+'$'));
  await expect(page.getByTestId('design-card').first()).toBeVisible();
  await page.getByRole('link',{name:'← Object gallery'}).click();
 }
 await expect(page.locator('[data-geometry-ready=true]').first()).toBeVisible();
 await page.screenshot({path:'runtime/product-screenshots/demo.png',fullPage:true});
 await page.getByRole('link',{name:'Documentation'}).click();
 await page.getByRole('link',{name:'Installation guide'}).click();
 await expect(page.getByRole('heading',{name:'Install and run',exact:true})).toBeVisible();
 await page.setViewportSize({width:390,height:844});await page.goto('/demo');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});
