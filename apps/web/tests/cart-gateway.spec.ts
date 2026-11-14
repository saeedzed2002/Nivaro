import { expect, test } from '@playwright/test';

const project = process.env.NIVARO_CART_QA_PROJECT ?? '';
test.skip(!/^nivaro-p05-qa-[a-f0-9]{8}$/.test(project), 'Requires the disposable cart gateway stack and its catalog fixture');

test('browser edits a transferred group, then merges the guest cart into an isolated account', async ({ page }) => {
  test.setTimeout(90_000);
  const exceptions: string[] = [];
  page.on('pageerror', error => exceptions.push(error.message));
  await page.goto('/en/products/amd-ryzen-7-9800x3d');
  const add = page.getByRole('button', { name: 'Add to cart', exact: true });
  await expect(add).toBeEnabled();
  await add.click();
  await expect(page.getByText('Added to your cart.')).toBeVisible();
  await expect(page.getByRole('link', { name: 'Shopping cart (1)' })).toBeVisible();

  await page.goto('/en/build');
  const cpu = page.getByLabel('Processor', { exact: true });
  await expect(cpu.locator('option').filter({ hasText: '9800X3D' }).first()).toBeAttached();
  const variant = await cpu.locator('option').filter({ hasText: '9800X3D' }).first().getAttribute('value');
  await cpu.selectOption(variant!);
  await page.getByLabel('Evaluation mode').selectOption('parts_only');
  await page.getByLabel('Build name').fill('Gateway build');
  await page.getByRole('button', { name: 'Save build' }).click();
  await expect(page).toHaveURL(/\/en\/build\?draft=/);
  const draftUrl = page.url();
  await page.getByRole('button', { name: 'Confirm and add system to cart' }).click();
  await page.getByRole('link', { name: 'System added. View cart' }).click();
  await expect(page.getByRole('heading', { name: 'Gateway build' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Shopping cart (2)' })).toBeVisible();

  await page.getByRole('link', { name: 'Edit system' }).click();
  await expect(page).toHaveURL(/\/en\/build\?group=/);
  await expect(page.getByLabel('Build name')).toHaveValue('Gateway build');
  await page.getByLabel('Build name').fill('Reviewed system');
  await page.getByRole('button', { name: 'Review system changes' }).click();
  await expect(page.getByRole('region', { name: 'System change review' })).toContainText('$459.00');
  await page.getByRole('button', { name: 'Confirm system changes' }).click();
  await expect(page.getByRole('heading', { name: 'Reviewed system', exact: true })).toBeVisible();
  await page.goto(draftUrl);
  await expect(page.getByLabel('Build name')).toHaveValue('Gateway build');

  await page.goto('/en/login');
  await page.getByLabel('Mobile number', { exact: true }).fill('+12025550101');
  await page.getByRole('button', { name: 'Get sign-in code' }).click();
  const developmentCode = page.getByTestId('development-code');
  await expect(developmentCode).toBeVisible();
  await page.getByLabel('Sign-in code', { exact: true }).fill((await developmentCode.textContent())!);
  await page.getByRole('button', { name: 'Verify and sign in' }).click();
  await expect(page).toHaveURL(/\/en\/account$/);
  await page.goto('/en/cart');
  await expect(page.getByRole('heading', { name: 'Your cart is empty' })).toBeVisible();
  await page.getByRole('button', { name: 'Merge guest cart' }).click();
  await expect(page.getByRole('heading', { name: 'Reviewed system' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Shopping cart (2)' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Merge guest cart' })).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole('link', { name: 'Shopping cart (2)' })).toBeVisible();
  await page.setViewportSize({ width: 375, height: 812 });
  await page.getByRole('combobox', { name: 'Appearance' }).selectOption('light');
  await page.getByRole('link', { name: 'Switch language to Persian' }).click();
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  await expect(page.getByRole('heading', { name: 'Reviewed system' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
  await page.screenshot({ path: test.info().outputPath('merged-cart-fa-mobile.png'), fullPage: true });
  expect(exceptions).toEqual([]);
});
