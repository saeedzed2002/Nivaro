import { test, expect } from '@playwright/test';

test('invalid price range is actionable and changing markets clears price inputs', async ({ page }) => {
  await page.goto('/en/products?min=500&max=100');
  await expect(page.getByRole('main').getByRole('alert')).toContainText('Minimum price must not exceed maximum price');
  await page.getByRole('combobox', { name: 'Sales market' }).selectOption('ir');
  await expect(page).not.toHaveURL(/min=|max=/);
  await expect(page.locator('input[name="min"]')).toHaveValue('');
  await expect(page.locator('input[name="max"]')).toHaveValue('');
  await expect(page.locator('.product-card')).toHaveCount(12);
  await page.goto('/fa/products?min=-1');
  await expect(page.getByRole('main').getByRole('alert')).toContainText('قیمت معتبر');
});

test('comparison retries a failed request without discarding selections', async ({ page }) => {
  await page.route('**/api/v1/catalog/comparisons', route => route.fulfill({ status: 503, contentType: 'application/json', body: '{}' }));
  await page.goto('/en/compare');
  await expect(page.getByRole('button', { name: 'Retry comparison' })).toBeVisible();
  const selection = await page.getByLabel('First product', { exact: true }).inputValue();
  await page.unroute('**/api/v1/catalog/comparisons');
  await page.getByRole('button', { name: 'Retry comparison' }).click();
  await expect(page.locator('.comparison-table')).toBeVisible();
  await expect(page.getByLabel('First product', { exact: true })).toHaveValue(selection);
});

test('documented full build stays under review and unknown prices never become zero', async ({ page }) => {
  await page.goto('/en/build');
  await page.getByLabel('Processor', { exact: true }).selectOption({ label: 'AMD Ryzen 7 9700X · boxed' });
  await expect(page.locator('.partial-total dd')).toHaveText('—');
  const parts = [
    ['Motherboard', 'MSI MAG B650 TOMAHAWK WIFI'],
    ['Memory', 'Kingston FURY Beast RGB KF560C36BBEAK2-32'],
    ['Storage', 'Samsung 990 PRO 1TB MZ-V9P1T0BW'],
    ['Case', 'Corsair 4000D AIRFLOW CC-9011200-WW'],
    ['Power supply', 'Seasonic FOCUS GX-850 ATX 3.1'],
    ['Cooling', 'Noctua NH-U12S'],
  ];
  for (const [role, name] of parts) await page.getByLabel(role, { exact: true }).selectOption({ label: `${name} · standard` });
  await page.getByRole('button', { name: 'Check compatibility' }).click();
  await expect(page.locator('.evaluation-status')).toHaveText('Needs further review');
  await expect(page.locator('.partial-total dd')).toHaveText('—');
  await expect(page.locator('.build-warning')).toContainText('7 selections have no price');
  await page.screenshot({ path: test.info().outputPath('complete-build-needs-review.png'), fullPage: true });
});

test('comparison shows differences and independent missing prices',async({page})=>{
  await page.goto('/en/compare');
  await expect(page.locator('.comparison-table')).toBeVisible();
  await expect(page.locator('.comparison-table')).toContainText('Unknown');
  await page.getByLabel('Differences only').check();
  await expect(page.locator('.comparison-table tbody')).toContainText('TDP');
  await expect(page.locator('.comparison-table tbody')).not.toContainText('Threads');
  await page.getByRole('combobox',{name:'Sales market'}).selectOption('international');
  await expect(page.locator('.comparison-table')).toBeVisible();
  await page.getByLabel('Comparison category').selectOption('keyboard');
  await expect(page.locator('.comparison-table')).toHaveCount(0);
  await expect(page.getByRole('main')).toContainText('Select two different variants');
});

test('builder evaluates real selections and invalidates stale results on changes',async({page})=>{
  await page.goto('/en/build');
  await page.getByRole('combobox',{name:'Sales market'}).selectOption('ir');
  await page.getByLabel('Processor',{exact:true}).selectOption({label:'AMD Ryzen 7 9800X3D · tray'});
  await expect(page.locator('.partial-total')).toContainText('113,390,000');
  await page.getByRole('button',{name:'Check compatibility'}).click();
  await expect(page.locator('.evaluation-status')).toHaveText('Incomplete selection');
  await page.getByLabel('Processor',{exact:true}).selectOption({label:'AMD Ryzen 7 9700X · boxed'});
  await expect(page.locator('.evaluation-status')).toHaveCount(0);
  await expect(page.locator('.build-warning')).toContainText('no price');
  await page.getByRole('button',{name:'Check compatibility'}).click();
  await expect(page.locator('.evaluation-status')).toHaveText('Incomplete selection');
  await expect(page.locator('.evaluation-result')).toContainText('Previous evidence was stale');
  await page.getByRole('combobox',{name:'Sales market'}).selectOption('international');
  await expect(page.locator('.evaluation-status')).toHaveCount(0);
});

test('failed evaluation preserves selections and offers retry',async({page})=>{
  await page.goto('/en/build');
  await page.getByLabel('Processor',{exact:true}).selectOption({label:'AMD Ryzen 7 9700X · boxed'});
  await page.route('**/api/v1/catalog/build-evaluations',route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:{code:'catalog.unavailable',message:'Unavailable',details:[],request_id:'test'}})}));
  await page.getByRole('button',{name:'Check compatibility'}).click();
  await expect(page.getByRole('main').getByRole('alert')).toContainText('selections are preserved');
  await expect(page.getByLabel('Processor',{exact:true})).not.toHaveValue('');
  await page.unroute('**/api/v1/catalog/build-evaluations');
  await page.getByRole('button',{name:'Check compatibility'}).click();
  await expect(page.locator('.evaluation-status')).toHaveText('Incomplete selection');
});
