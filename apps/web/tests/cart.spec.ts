import { expect, test } from '@playwright/test';

const one = { id: 'variant-one', group_id: 'group-one', slot_key: 'storage:1', quantity: 2, version: 1, variant_id: 'ssd-one',
  observed_price_minor: 12999, observed_price_version: 1, status: 'available', price_changed: false,
  summary: { name: 'Example NVMe SSD', image: '/images/showroom.webp', offer: { amount_minor: 12999 } } };

test('cart shows groups and exact estimates, reconciles conflicts, and isolates market views', async ({ page }) => {
  let lines = [{ ...one }, { ...one, id: 'loose', group_id: null, slot_key: null, quantity: 1 }];
  let version = 1;
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/api/v1/auth/**', route => route.fulfill({ status: 401, json: { error: { code: 'auth.required' } } }));
  await page.route('**/api/v1/cart{,/**,?*}', async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname.endsWith('/session')) return route.fulfill({ json: { csrf_token: 'test' } });
    if (request.method() === 'PATCH') {
      const body = request.postDataJSON();
      expect(body.expected_group_version).toBe(1);
      expect(body.expected_version).toBe(1);
      expect(request.headers()['x-csrf-token']).toBe('test');
      lines = lines.map(line => line.id === one.id ? { ...line, quantity: 3 } : line);
      version++;
      return route.fulfill({ status: 409, json: { error: { code: 'cart.version_conflict' } } });
    }
    if (request.method() === 'DELETE') {
      lines = lines.filter(line => line.id !== 'loose');
      version++;
      return route.fulfill({ json: { version } });
    }
    const market = url.searchParams.get('market');
    const domestic = market === 'ir';
    const current = domestic ? [] : lines;
    return route.fulfill({ json: { id: 'cart', version, owner_scope: 'guest', market, currency: domestic ? 'IRR' : 'USD',
      groups: domestic ? [] : [{ id: 'group-one', name: 'Example PC', mode: 'parts_only', version: 1 }], lines: current,
      catalog_status: 'ready', estimated_total_minor: String(current.reduce((amount, line) => amount + 12999 * line.quantity, 0)) } });
  });
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto('/en/cart');
  await page.getByRole('combobox', { name: 'Appearance' }).selectOption('dark');
  await expect(page.getByRole('heading', { name: 'Example PC' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Shopping cart (3)' })).toBeVisible();
  await expect(page.getByText('$389.97', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Checkout unavailable' })).toBeDisabled();
  await page.getByRole('button', { name: 'Increase quantity: Example NVMe SSD' }).first().click();
  await expect(page.getByRole('main').getByRole('alert')).toContainText('Your cart changed');
  await expect(page.getByRole('link', { name: 'Shopping cart (4)' })).toBeVisible();
  await page.getByRole('button', { name: 'Remove: Example NVMe SSD', exact: true }).last().click();
  await expect(page.getByRole('link', { name: 'Shopping cart (3)' })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath('cart-desktop.png'), fullPage: true });
  await page.setViewportSize({ width: 375, height: 812 });
  await page.getByRole('combobox', { name: 'Appearance' }).selectOption('light');
  await page.getByRole('link', { name: 'Switch language to Persian' }).click();
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  await expect(page.getByRole('heading', { name: 'Example PC' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
  await page.screenshot({ path: test.info().outputPath('cart-mobile-fa.png'), fullPage: true });
  await page.getByRole('combobox', { name: 'بازار فروش' }).selectOption('ir');
  await expect(page.getByRole('heading', { name: 'سبد خرید خالی است' })).toBeVisible();
  expect(errors).toEqual([]);
});
