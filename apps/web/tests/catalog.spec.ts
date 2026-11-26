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

test('the builder totals only selected priced parts', async ({ page }) => {
  await page.goto('/en/build');
  const total = page.locator('.partial-total dd');
  const add = page.getByRole('button', { name: 'Add to cart', exact: true });
  await expect(total).toHaveText('—');
  await expect(add).toBeDisabled();
  await page.getByLabel('Processor', { exact: true }).selectOption({ label: 'AMD Ryzen 7 9700X · boxed' });
  await expect(total).toHaveText('$269.00');
  await expect(add).toBeEnabled();
  await page.getByLabel('Motherboard', { exact: true }).selectOption({ label: 'MSI MAG B650 TOMAHAWK WIFI · standard' });
  await expect(total).toHaveText('$444.99');
  await expect(page.locator('.build-warning')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Check compatibility' })).toHaveCount(0);
  await page.getByLabel('Processor', { exact: true }).selectOption('');
  await expect(total).toHaveText('$175.99');
  await page.getByRole('combobox', { name: 'Sales market' }).selectOption('ir');
  await expect(total).toHaveText('—');
  await page.getByLabel('Processor', { exact: true }).selectOption({ label: 'AMD Ryzen 7 9700X · tray' });
  await expect(total).toHaveText('61,000,000 toman');
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
