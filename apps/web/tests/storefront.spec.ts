import { test, expect } from '@playwright/test';

for (const locale of ['fa', 'en']) {
  for (const theme of ['light', 'dark']) {
    for (const width of [360, 768, 1440]) {
      test(`${locale} ${theme} ${width}: readable home, collection and detail`, async ({ page, context }) => {
        await context.addCookies([{ name:'nivaro-theme', value:theme, url:process.env.TEST_BASE_URL || 'http://127.0.0.1:8080' }]);
        await page.setViewportSize({width,height:1000});
        const errors: string[] = [];
        page.on('pageerror',e=>errors.push(e.message));
        page.on('console',message=>{if(message.type()==='error') errors.push(message.text());});
        for (const path of ['', '/products', '/products/amd-ryzen-7-9800x3d']) {
          await page.goto(`/${locale}${path}`);
          await expect(page.locator('html')).toHaveAttribute('dir',locale==='fa'?'rtl':'ltr');
          await expect(page.locator('html')).toHaveAttribute('data-theme',theme);
          await expect(page.locator('h1')).toBeVisible();
          await expect(page.getByRole('banner')).toBeVisible();
          await expect(page.getByRole('search')).toBeVisible();
          await page.evaluate(()=>document.fonts.ready);
          await expect.poll(()=>page.locator('img').evaluateAll(images=>images.every(image=>{
            if (!(image instanceof HTMLImageElement)) return true;
            const bounds = image.getBoundingClientRect();
            return bounds.width === 0 || bounds.height === 0 || bounds.top >= innerHeight || bounds.bottom <= 0 || (image.complete && image.naturalWidth > 0);
          }))).toBe(true);
          expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
          await expect(page.getByRole('main')).toBeVisible();
          await page.screenshot({path:test.info().outputPath(`${locale}-${theme}-${width}-${path ? path.includes('amd')?'detail':'products':'home'}.png`),fullPage:true,animations:'disabled'});
        }
        expect(errors).toEqual([]);
      });
    }
  }
}

test('filters are in the URL, empty results recover, and product links work', async ({page})=>{
  await page.goto('/en/products');
  await page.getByRole('radio',{name:'Keyboards',exact:true}).check();
  await page.getByRole('button',{name:'Apply filters'}).click();
  await expect(page).toHaveURL(/category=keyboard/);
  await expect(page.locator('.product-card')).toHaveCount(1);
  await page.getByRole('link',{name:'Explore product',exact:true}).click();
  await expect(page.locator('h1')).toContainText('BlackWidow');
  await page.goto('/en/products?q=does-not-exist');
  await expect(page.getByRole('heading',{name:'No matching products yet'})).toBeVisible();
  await page.getByRole('link',{name:'View all products',exact:true}).click();
  await expect(page.locator('.product-card')).toHaveCount(5);
});

test('language preserves market and route; explicit market changes prices',async({page})=>{
  await page.goto('/en/products/amd-ryzen-7-9800x3d');
  await page.getByRole('combobox',{name:'Sales market'}).selectOption('ir');
  await expect(page.locator('.detailed .price')).toContainText('113,390,000');
  await page.getByRole('link',{name:'Switch language to Persian'}).click();
  await expect(page).toHaveURL('/fa/products/amd-ryzen-7-9800x3d');
  await expect(page.getByRole('combobox',{name:'بازار فروش'})).toHaveValue('ir');
  await page.getByRole('combobox',{name:'بازار فروش'}).selectOption('international');
  await expect(page.locator('.detailed .price')).toContainText('۴۶۹');
  await page.reload();
  await expect(page.getByRole('combobox',{name:'بازار فروش'})).toHaveValue('international');
});

test('feature dialog traps focus, closes with Escape, and returns focus',async({page})=>{
  await page.goto('/en');
  const trigger=page.getByRole('button',{name:'Shopping bag; not active yet'});
  await trigger.click();
  await expect(page.locator('dialog[open]')).toContainText('not active yet');
  await page.keyboard.press('Escape');
  await expect(page.locator('dialog[open]')).toHaveCount(0);
  await expect(trigger).toBeFocused();
});

test('theme persists and reduced motion is respected',async({page})=>{
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.goto('/en');
  await page.getByRole('combobox',{name:'Appearance'}).selectOption('light');
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-theme','light');
  expect(await page.locator('.hero-copy').evaluate(e=>getComputedStyle(e).animationName)).toBe('none');
});
