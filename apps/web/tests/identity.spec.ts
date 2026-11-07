import { test, expect, type BrowserContext } from '@playwright/test';
import { randomBytes } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import type { AdminDetail } from '../src/lib/admin-catalog-client';

const project = process.env.NIVARO_IDENTITY_QA_PROJECT || '';
test.describe.configure({ mode: 'serial' });
const base = process.env.TEST_BASE_URL || 'http://127.0.0.1:8080';
test.skip(!/^nivaro-p03-qa-[a-z0-9]+$/.test(project), 'Use the isolated identity browser helper; never reset real accounts or limits.');
let seedCookies: Awaited<ReturnType<BrowserContext['cookies']>>;
let staffCookies: Awaited<ReturnType<BrowserContext['cookies']>> | undefined;
const adminPassword = randomBytes(24).toString('base64url');
function operator(code: string, input = '') {
  if (!/^nivaro-p03-qa-[a-z0-9]+$/.test(project)) throw new Error('Disposable test project required');
  const result = spawnSync('docker', ['compose', '-p', project, '-f', 'compose.yaml', '-f', 'compose.identity-qa.yaml', 'exec', '-T', 'identity', 'python', '-c', code], { cwd: path.resolve('../..'), input, encoding: 'utf8', timeout: 20_000 });
  if (result.status !== 0) throw new Error('Disposable identity operator check failed');
}
function identityService(action: 'stop' | 'start') {
  if (!/^nivaro-p03-qa-[a-z0-9]+$/.test(project)) throw new Error('Disposable test project required');
  const result = spawnSync('docker', ['compose', '-p', project, '-f', 'compose.yaml', '-f', 'compose.identity-qa.yaml', action, 'identity'], { cwd: path.resolve('../..'), encoding: 'utf8', timeout: 30_000 });
  if (result.status !== 0) throw new Error(`Disposable identity ${action} failed`);
}
test.beforeAll(async ({ browser }) => {
  operator(`import asyncio,builtins,getpass,json,sys
from nivaro_identity.settings import Settings
from nivaro_identity.manage import manage
assert Settings().environment == 'test'
values=json.load(sys.stdin)
answers=iter(['+12025550100','staff@example.com'])
builtins.input=lambda _:next(answers)
getpass.getpass=lambda _:values['password']
asyncio.run(manage('bootstrap-admin'))`, JSON.stringify({ password: adminPassword }));
  const context = await browser.newContext();
  const request = await context.request.post(`${base}/api/v1/auth/otp/request`, { headers: { Origin: base }, data: { phone: '+12025550100' } });
  expect(request.status()).toBe(200);
  const challenge = await request.json();
  const verified = await context.request.post(`${base}/api/v1/auth/otp/verify`, { headers: { Origin: base }, data: { phone: '+12025550100', challenge_id: challenge.challenge_id, code: challenge.development_code } });
  expect(verified.status()).toBe(200);
  seedCookies = await context.cookies();
  await context.close();
});

for (const locale of ['fa', 'en']) for (const theme of ['dark', 'light']) for (const width of [360, 768, 1440]) {
  test(`identity ${locale} ${theme} ${width}: five templates`, async ({ page, context }) => {
    await context.addCookies([{ name: 'nivaro-theme', value: theme, url: base }]);
    await page.setViewportSize({ width, height: 1000 });
    const errors: string[] = [];
    page.on('pageerror', e => errors.push(e.message));
    for (const route of ['/login', '/admin/login', '/account', '/account/profile', '/account/addresses']) {
      if (route === '/account') await context.addCookies(seedCookies);
      await page.goto(`/${locale}${route}`);
      await expect(page.locator('h1')).toBeVisible();
      if (route.startsWith('/account')) await expect(page.locator('.account-sidebar')).toBeVisible();
      if (route.startsWith('/account')) await expect(page.getByRole('link', { name: locale === 'fa' ? 'حساب کاربری' : 'Your account', exact: true })).toBeVisible();
      if (route === '/account/addresses') await expect(page.locator('.address-empty')).toBeVisible();
      await page.evaluate(() => document.fonts.ready);
      await expect.poll(() => page.locator('main img').evaluateAll(images => images.every(image => {
        if (!(image instanceof HTMLImageElement)) return true;
        const bounds = image.getBoundingClientRect();
        return bounds.top >= innerHeight || bounds.bottom <= 0 || (image.complete && image.naturalWidth > 0);
      }))).toBe(true);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await expect(page.locator('html')).toHaveAttribute('dir', locale === 'fa' ? 'rtl' : 'ltr');
      await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
      await page.screenshot({ path: test.info().outputPath(`${locale}-${theme}-${width}-${route.replaceAll('/', '-')}.png`), fullPage: true, animations: 'disabled' });
    }
    expect(errors).toEqual([]);
  });
}
test('customer code, profile, address, expiry recovery across two tabs and logout', async ({ page, context }) => {
  await page.goto('/en/login');
  await page.getByLabel('Mobile number', { exact: true }).fill('+12025550101');
  await page.getByRole('button', { name: 'Get sign-in code' }).click();
  await expect(page.getByTestId('development-code')).toBeVisible();
  const code = await page.getByTestId('development-code').textContent();
  await page.getByLabel('Sign-in code', { exact: true }).fill(code!);
  await page.getByRole('button', { name: 'Verify and sign in' }).click();
  await expect(page).toHaveURL(/\/en\/account$/);
  await page.goto('/en/account/profile');
  await page.getByLabel('Full name').fill('Browser test');
  await page.getByRole('button', { name: 'Save changes' }).click();
  await expect(page.getByRole('status')).toHaveText('Account details saved.');
  await page.reload();
  await expect(page.getByLabel('Full name')).toHaveValue('Browser test');
  await page.goto('/en/account/addresses');
  await page.getByRole('button', { name: 'Add address' }).click();
  for (const [label, value] of [['Address label', 'QA home'], ['Recipient name', 'Synthetic recipient'], ['Two-letter country code', 'IR'], ['City', 'تهران'], ['Postal code', '۱۲۳۴۵۶۷۸۹۰'], ['Street address', 'Synthetic browser address']]) await page.getByLabel(label, { exact: true }).fill(value);
  await page.getByRole('button', { name: 'Save address', exact: true }).click();
  await expect(page.getByRole('status')).toHaveText('Address saved.');
  await expect(page.getByText('1234567890', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Edit', exact: true }).click();
  await page.getByLabel('Address label', { exact: true }).fill('QA updated');
  await page.getByRole('button', { name: 'Save address', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'QA updated' })).toBeVisible();
  await page.getByRole('button', { name: 'Delete', exact: true }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('button', { name: 'Confirm', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'No addresses yet' })).toBeVisible();
  // Refresh cookies survive; access cookie expires. Both tabs coordinate recovery.
  await context.clearCookies({ name: 'nivaro_customer_access' });
  const second = await context.newPage();
  await Promise.all([page.goto('/en/account/profile'), second.goto('/en/account/profile')]);
  for (const tab of [page, second]) await expect(tab.getByLabel('Full name')).toHaveValue('Browser test');
  const cookies = await context.cookies();
  expect(cookies.filter(c => c.name.startsWith('nivaro_customer_')).every(c => c.httpOnly)).toBe(true);
  expect(cookies.find(c => c.name === 'nivaro_customer_refresh')?.path).toBe('/api/v1/auth/refresh');
  expect(await page.evaluate(() => document.cookie)).not.toContain('nivaro_customer');
  expect(await page.evaluate(() => JSON.stringify(localStorage))).not.toContain('token');
  await page.goto('/en/account');
  await page.getByRole('button', { name: 'Sign out everywhere', exact: true }).click();
  await page.getByRole('button', { name: 'Confirm', exact: true }).click();
  await expect(page).toHaveURL(/\/en\/login$/);
  await second.reload();
  await expect(second.getByRole('link', { name: 'Sign in', exact: true })).toBeVisible();
  await expect(second.getByLabel('Full name')).toHaveCount(0);
});
test('staff product workspace: responsive references, persistence, conflicts and stock', async ({ page, context }) => {
  test.setTimeout(180_000);
  page.setDefaultTimeout(15_000);
  await page.goto('/en/admin/products');
  await expect(page.getByRole('heading', { name: 'Product administration access' })).toBeVisible();
  const signedIn = await context.request.post(`${base}/api/v1/admin/auth/login`, { headers: { Origin: base }, data: { email: 'staff@example.com', password: adminPassword } });
  expect(signedIn.status()).toBe(200);
  staffCookies = (await context.cookies()).filter(cookie => cookie.name.startsWith('nivaro_admin_'));
  const listing = await context.request.get(`${base}/api/v1/admin/catalog/products?q=9700X`);
  const productId = (await listing.json()).items[0].id;
  const productUrl = `${base}/api/v1/admin/catalog/products/${productId}`;
  const original = await (await context.request.get(productUrl)).json();
  const errors: string[] = [];
  page.on('pageerror', e => errors.push(e.message));
  for (const locale of ['fa', 'en']) for (const theme of ['dark', 'light']) for (const width of [360, 768, 1440]) {
    await context.addCookies([{ name: 'nivaro-theme', value: theme, url: base }]);
    await page.setViewportSize({ width, height: 1100 });
    for (const route of ['products', `products/${productId}`]) {
      await page.goto(`/${locale}/admin/${route}`);
      if (route === 'products') await expect(page.locator('.admin-table tbody tr')).toHaveCount(10);
      else await expect(page.getByLabel(locale === 'fa' ? 'نام محصول و مدل' : 'Product name and model')).toHaveValue(original.name);
      await page.evaluate(() => document.fonts.ready);
      // Full-page capture must load thumbnails below the browser's lazy-load range.
      for (const thumbnail of await page.locator('.admin-thumbnail img').all()) await thumbnail.scrollIntoViewIfNeeded();
      await expect.poll(() => page.locator('.admin-thumbnail img').evaluateAll(images => images.every(image => !(image instanceof HTMLImageElement) || image.complete && image.naturalWidth > 0))).toBe(true);
      await page.evaluate(() => window.scrollTo(0, 0));
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await expect(page.locator('html')).toHaveAttribute('dir', locale === 'fa' ? 'rtl' : 'ltr');
      await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
      await page.screenshot({ path: test.info().outputPath(`staff-${locale}-${theme}-${width}-${route === 'products' ? 'list' : 'editor'}.png`), fullPage: true, animations: 'disabled' });
    }
  }
  expect(errors).toEqual([]);
  await page.setViewportSize({ width: 1280, height: 1000 });
  await page.goto('/en/admin/products');
  await page.getByLabel('Product name or SKU').fill('no-result-fixture');
  await page.getByRole('button', { name: 'Apply filters', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'No products found' })).toBeVisible();
  await page.getByRole('link', { name: 'Show all products' }).click();
  await expect(page.locator('.admin-table tbody tr')).toHaveCount(10);
  await page.getByRole('button', { name: 'Next', exact: true }).click();
  await expect(page.locator('.admin-table tbody tr')).toHaveCount(2);
  await page.getByRole('link', { name: 'Add product', exact: true }).click();
  await page.getByLabel('Product name and model').fill('UI draft fixture');
  await page.getByLabel('URL slug', { exact: true }).fill('ui-draft-' + randomBytes(6).toString('hex'));
  const category = page.getByRole('combobox', { name: 'Category', exact: true });
  await category.selectOption({ index: 1 });
  await page.getByLabel('Persian description').fill('محصول آزمایشی رابط');
  await page.getByLabel('English description').fill('Disposable UI test product');
  await page.getByRole('button', { name: 'Save changes', exact: true }).click();
  await expect(page).toHaveURL(/\/admin\/products\/[0-9a-f-]{36}$/);
  await expect(page.getByRole('button', { name: 'Publish product', exact: true })).toBeDisabled();
  await page.goto(`/en/admin/products/${productId}`);
  const name = page.getByLabel('Product name and model');
  await expect(name).toHaveValue(original.name);
  await name.fill('Preserved UI draft');
  const csrf = (await (await context.request.get(`${base}/api/v1/admin/auth/csrf`, { headers: { 'X-CSRF-Request': '1', Origin: base } })).json()).csrf_token;
  const { slug, description, category_id, brand, highlights } = original;
  const external = await context.request.put(productUrl, { headers: { Origin: base, 'X-CSRF-Token': csrf }, data: { slug, description, category_id, brand, highlights, name: 'Changed in another tab', expected_version: original.version } });
  expect(external.status()).toBe(200);
  await page.getByRole('button', { name: 'Save changes', exact: true }).click();
  await expect(page.getByRole('main').getByRole('alert')).toContainText('This product changed');
  await expect(name).toHaveValue('Preserved UI draft');
  await page.getByRole('button', { name: 'Load latest version to compare' }).click();
  await expect(page.getByRole('heading', { name: 'Compare with current version' })).toBeVisible();
  await expect(name).toHaveValue('Preserved UI draft');
  await page.getByRole('button', { name: 'Replace form with current version' }).click();
  await expect(name).toHaveValue('Changed in another tab');
  await name.fill(original.name);
  await page.getByRole('button', { name: 'Save changes', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Changes saved');
  await page.reload();
  await expect(name).toHaveValue(original.name);
  await page.route('**/api/v1/admin/catalog/products/' + productId, route => route.request().method() === 'PUT' ? route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: { code: 'catalog.unavailable' } }) }) : route.continue());
  await name.fill('Retain on outage');
  await page.getByRole('button', { name: 'Save changes', exact: true }).click();
  await expect(page.getByRole('main').getByRole('alert')).toContainText('Your draft is preserved');
  await expect(name).toHaveValue('Retain on outage');
  await page.unroute('**/api/v1/admin/catalog/products/' + productId);
  await name.fill(original.name);
  await page.getByRole('tab', { name: 'Variants & stock' }).click();
  const stockForm = page.locator('.admin-stock-form').first();
  await stockForm.getByLabel('Physical stock', { exact: true }).fill('2');
  await stockForm.getByLabel('Stock adjustment reason').fill('UI count verification');
  await stockForm.getByLabel('Physical stock has been verified').check();
  await stockForm.getByRole('button', { name: 'Review stock adjustment' }).click();
  await page.getByRole('button', { name: 'Confirm stock change' }).click();
  await expect(stockForm.getByLabel('Physical stock', { exact: true })).toHaveValue('2');
  await expect(stockForm.getByLabel('Stock adjustment reason')).toHaveValue('');
  await stockForm.getByLabel('Physical stock', { exact: true }).fill('0');
  await stockForm.getByLabel('Stock adjustment reason').fill('Restore disposable fixture');
  await stockForm.getByLabel('Physical stock has been verified').uncheck();
  await stockForm.getByRole('button', { name: 'Review stock adjustment' }).click();
  await page.getByRole('button', { name: 'Confirm stock change' }).click();
  await expect(stockForm.getByLabel('Stock adjustment reason')).toHaveValue('');
  await page.getByRole('tab', { name: 'Change history' }).click();
  await expect(page.locator('.admin-audit')).toContainText('Stock adjusted');
  await expect(page.locator('.admin-audit')).toContainText('Restore disposable fixture');
  await page.getByRole('tab', { name: 'Basic information' }).click();
  await page.getByRole('button', { name: 'Archive product', exact: true }).click();
  await page.getByRole('button', { name: 'Confirm', exact: true }).click();
  await expect(page.locator('.admin-heading .admin-badge')).toHaveText('Archived');
  await page.getByRole('button', { name: 'Publish product', exact: true }).click();
  await page.getByRole('button', { name: 'Confirm', exact: true }).click();
  await expect(page.locator('.admin-heading .admin-badge')).toHaveText('Published');
});

test('staff edits typed variants and independent prices without losing failed drafts', async ({ page, context }) => {
  test.setTimeout(180_000);
  page.setDefaultTimeout(15_000);
  expect((await context.request.post(`${base}/api/v1/admin/auth/login`, { headers: { Origin: base }, data: { email: 'staff@example.com', password: adminPassword } })).status()).toBe(200);
  const listing = await (await context.request.get(`${base}/api/v1/admin/catalog/products?q=UI%20draft%20fixture`)).json();
  const productId = listing.items[0].id;
  const productUrl = `${base}/api/v1/admin/catalog/products/${productId}`;
  const current = async (): Promise<AdminDetail> => (await context.request.get(productUrl)).json();
  await page.goto(`/en/admin/products/${productId}`);
  await page.getByRole('tab', { name: 'Models & specifications' }).click();
  const variantForm = page.locator('.admin-variant-form');
  for (const kind of ['motherboard', 'memory', 'storage', 'case', 'psu', 'cooler', 'gpu', 'peripheral', 'prebuilt', 'cpu']) {
    await variantForm.getByRole('combobox', { name: 'Hardware type', exact: true }).selectOption(kind);
    await expect(variantForm.locator('.admin-spec-grid')).toBeVisible();
  }
  await variantForm.getByLabel('SKU', { exact: true }).fill('QA-CPU');
  await variantForm.getByLabel('Persian packaging').fill('بستهٔ آزمایشی');
  await variantForm.getByLabel('English packaging').fill('Synthetic browser fixture');
  await variantForm.getByLabel('Exact CPU model').fill('QA CPU');
  await variantForm.getByRole('combobox', { name: 'Integrated graphics', exact: true }).selectOption('false');
  await variantForm.getByRole('button', { name: 'Add source', exact: true }).click();
  await variantForm.getByLabel('Source URL').fill('https://example.com/synthetic-specification');
  await variantForm.getByLabel('Checked on (Gregorian)', { exact: true }).fill('2026-10-29');
  await variantForm.getByLabel('Source note').fill('Synthetic fixture; not real product data');
  await variantForm.getByRole('button', { name: 'Save variant' }).click();
  await expect(page.getByRole('status')).toContainText('Changes saved');
  await expect(variantForm.getByRole('combobox', { name: 'Hardware type', exact: true })).toBeDisabled();
  let product = await current();
  const cpu = product.variants.find(row => row.sku === 'QA-CPU')!;
  expect(cpu.specifications).toMatchObject({ kind: 'cpu', model: 'QA CPU', integrated_graphics: false, included_cooler: null, cores: null });
  expect(cpu.evidence?.[0].note).toContain('Synthetic');
  expect(cpu.on_hand).toBe(0);
  expect(cpu.stock_verified).toBe(false);
  await page.getByRole('combobox', { name: 'Choose variant', exact: true }).selectOption('new');
  await variantForm.getByRole('combobox', { name: 'Hardware type', exact: true }).selectOption('psu');
  await variantForm.getByLabel('SKU', { exact: true }).fill('QA-PSU');
  await variantForm.getByLabel('Persian packaging').fill('آزمایشی');
  await variantForm.getByLabel('English packaging').fill('Synthetic');
  await variantForm.getByLabel('Rated power (W)', { exact: true }).fill('450');
  await variantForm.getByRole('button', { name: 'Add row', exact: true }).click();
  await variantForm.getByLabel('Connector or form name', { exact: true }).fill('ATX24');
  await variantForm.getByLabel('Count', { exact: true }).fill('1');
  await variantForm.getByRole('button', { name: 'Save variant' }).click();
  await expect(page.getByRole('status')).toContainText('Changes saved');
  product = await current();
  expect(product.variants.find(row => row.sku === 'QA-PSU')?.specifications).toMatchObject({ kind: 'psu', wattage_w: 450, connectors: { ATX24: 1 }, length_mm: null });
  await page.getByRole('combobox', { name: 'Choose variant', exact: true }).selectOption(cpu.id);
  await variantForm.getByLabel('Exact CPU model').fill('Preserve failed model');
  await expect(page.getByRole('tab', { name: 'Market prices' })).toBeDisabled();
  await page.route(`**/api/v1/admin/catalog/products/${productId}/variants/${cpu.id}`, route => route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: { code: 'catalog.unavailable' } }) }));
  await variantForm.getByRole('button', { name: 'Save variant' }).click();
  await expect(variantForm.getByRole('alert')).toContainText('Your draft is preserved');
  await expect(variantForm.getByLabel('Exact CPU model')).toHaveValue('Preserve failed model');
  await page.unroute(`**/api/v1/admin/catalog/products/${productId}/variants/${cpu.id}`);
  await variantForm.getByRole('button', { name: 'Discard variant changes' }).click();
  await variantForm.getByLabel('Exact CPU model').fill('QA CPU revised');
  await variantForm.getByRole('button', { name: 'Save variant' }).click();
  await expect(page.getByRole('status')).toContainText('Changes saved');
  expect((await current()).variants.find(row => row.id === cpu.id)?.specifications).toMatchObject({ model: 'QA CPU revised', integrated_graphics: false, cores: null });
  await page.getByRole('tab', { name: 'Market prices' }).click();
  const offerForm = page.locator('.admin-offer-form');
  await expect(offerForm.getByRole('checkbox', { name: 'Offer for sale in this market' })).toBeDisabled();
  async function fillOffer(amount: string, label: string) {
    await offerForm.getByLabel(label, { exact: true }).fill(amount);
    await offerForm.getByLabel('Seller', { exact: true }).fill('Synthetic QA merchant');
    await offerForm.getByLabel('Source URL').fill('https://example.com/synthetic-price');
    await offerForm.getByLabel('Checked on (Gregorian)', { exact: true }).fill('2026-10-29');
    await offerForm.getByLabel('Source note').fill('Synthetic price; never a merchant quote');
    await offerForm.getByLabel('Price change reason').fill('Disposable browser price verification');
    await offerForm.getByRole('button', { name: 'Review price change' }).click();
  }
  await fillOffer('۱۲۳۴۵۶', 'Amount (whole tomans)');
  await expect(page.getByRole('dialog')).toContainText('123456 tomans');
  await page.getByRole('button', { name: 'Confirm price save' }).click();
  await expect(offerForm.getByLabel('Price change reason')).toHaveValue('');
  await offerForm.getByRole('combobox', { name: 'Price market' }).selectOption('international');
  await fillOffer('129.99', 'Amount (USD)');
  await page.getByRole('button', { name: 'Confirm price save' }).click();
  await expect(offerForm.getByLabel('Price change reason')).toHaveValue('');
  await expect(offerForm.getByRole('combobox', { name: 'Price market' })).toHaveValue('international');
  product = await current();
  const prices = product.variants.find(row => row.id === cpu.id)!.offers!;
  expect(prices.find(row => row.market === 'ir')).toMatchObject({ amount_minor: 1234560, currency: 'IRR', reference_only: true, available_for_sale: false });
  const usd = prices.find(row => row.market === 'international')!;
  expect(usd).toMatchObject({ amount_minor: 12999, currency: 'USD' });
  await offerForm.getByLabel('Amount (USD)', { exact: true }).fill('131.25');
  await offerForm.getByLabel('Price change reason').fill('Stale price draft');
  await expect(offerForm.getByRole('combobox', { name: 'Price market' })).toBeDisabled();
  const csrf = (await (await context.request.get(`${base}/api/v1/admin/auth/csrf`, { headers: { 'X-CSRF-Request': '1', Origin: base } })).json()).csrf_token;
  const { price_version, ...priceContent } = usd;
  expect((await context.request.put(`${productUrl}/variants/${cpu.id}/offers`, { headers: { Origin: base, 'X-CSRF-Token': csrf }, data: { ...priceContent, expected_version: product.version, expected_price_version: price_version, amount_minor: 13099, reason: 'Concurrent disposable edit' } })).status()).toBe(200);
  await offerForm.getByRole('button', { name: 'Review price change' }).click();
  await page.getByRole('button', { name: 'Confirm price save' }).click();
  await expect(offerForm.getByRole('alert')).toContainText('Your draft is preserved');
  await expect(offerForm.getByLabel('Amount (USD)', { exact: true })).toHaveValue('131.25');
  page.once('dialog', dialog => dialog.accept());
  await offerForm.getByRole('button', { name: 'Reload current price' }).click();
  await expect(offerForm.getByLabel('Amount (USD)', { exact: true })).toHaveValue('130.99');
  expect((await current()).variants.find(row => row.id === cpu.id)?.offers?.find(row => row.market === 'ir')?.amount_minor).toBe(1234560);
  const pageErrors: string[] = [];
  page.on('pageerror', error => pageErrors.push(error.message));
  for (const locale of ['fa', 'en']) for (const theme of ['light', 'dark']) for (const width of [360, 768, 1440]) {
    await context.addCookies([{ name: 'nivaro-theme', value: theme, url: base }]);
    await page.setViewportSize({ width, height: 1100 });
    await page.goto(`/${locale}/admin/products/${productId}`);
    for (const section of ['variants', 'prices']) {
      await page.locator(`#tab-${section}`).click();
      await expect(page.locator(section === 'variants' ? '.admin-variant-form' : '.admin-offer-form')).toBeVisible();
      await page.evaluate(() => document.fonts.ready);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({ path: test.info().outputPath(`${locale}-${theme}-${width}-${section}.png`), fullPage: true, animations: 'disabled' });
    }
  }
  expect(pageErrors).toEqual([]);
});

test('staff category hierarchy preserves drafts, versions and responsive layouts', async ({ page, context }) => {
  test.setTimeout(180_000);
  page.setDefaultTimeout(15_000);
  const endpoint = `${base}/api/v1/admin/catalog/categories`;
  expect((await context.request.get(endpoint)).status()).toBe(401);
  expect((await context.request.post(`${base}/api/v1/admin/auth/login`, { headers: { Origin: base }, data: { email: 'staff@example.com', password: adminPassword } })).status()).toBe(200);
  const slug = 'category-ui-' + randomBytes(6).toString('hex');
  expect((await context.request.post(endpoint, { headers: { Origin: base }, data: { slug, name: { fa: 'آزمایشی', en: 'Synthetic root' }, parent_id: null } })).status()).toBe(403);
  await page.goto('/en/admin/categories');
  await page.getByRole('button', { name: 'Add category', exact: true }).click();
  const english = page.getByLabel('English name', { exact: true });
  const save = page.getByRole('button', { name: 'Save category', exact: true });
  await page.getByLabel('Persian name', { exact: true }).fill('تجهیزات آزمایشی');
  await english.fill('Synthetic root');
  await page.getByLabel('URL slug', { exact: true }).fill(slug);
  await save.click();
  await expect(page.locator('.admin-category-editor .success')).toContainText('Category saved');
  const rows = await (await context.request.get(endpoint)).json();
  const root = rows.find((row: { slug: string }) => row.slug === slug);
  expect(root.version).toBe(1);
  await page.getByRole('button', { name: 'Add category', exact: true }).click();
  await page.getByLabel('Persian name', { exact: true }).fill('زیرمجموعهٔ آزمایشی');
  await english.fill('Synthetic child');
  await page.getByLabel('URL slug', { exact: true }).fill(`${slug}-child`);
  await page.getByRole('combobox', { name: 'Parent category', exact: true }).selectOption(root.id);
  await save.click();
  await expect(page.locator('.admin-category-editor .success')).toContainText('Category saved');
  await expect(page.getByRole('combobox', { name: 'Parent category', exact: true }).locator('option', { hasText: 'Synthetic child' })).toHaveCount(0);
  await page.getByRole('button', { name: 'Edit Synthetic root', exact: true }).click();
  await expect(page.getByRole('combobox', { name: 'Parent category', exact: true })).toBeDisabled();
  await english.fill('My preserved category draft');
  const csrf = (await (await context.request.get(`${base}/api/v1/admin/auth/csrf`, { headers: { 'X-CSRF-Request': '1', Origin: base } })).json()).csrf_token;
  const update = { slug: root.slug, name: { ...root.name, en: 'Concurrent category name' }, parent_id: null, expected_version: root.version };
  expect((await context.request.put(`${endpoint}/${root.id}`, { headers: { Origin: base, 'X-CSRF-Token': csrf }, data: update })).status()).toBe(200);
  await save.click();
  await expect(page.getByRole('main').getByRole('alert')).toContainText('Category changed');
  await expect(english).toHaveValue('My preserved category draft');
  await page.getByRole('button', { name: 'Compare current category', exact: true }).click();
  await expect(page.locator('.admin-conflict')).toContainText('Concurrent category name');
  await expect(english).toHaveValue('My preserved category draft');
  await page.getByRole('button', { name: 'Replace with current category', exact: true }).click();
  await expect(english).toHaveValue('Concurrent category name');
  await page.route(`**/api/v1/admin/catalog/categories/${root.id}`, route => route.request().method() === 'PUT' ? route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: { code: 'catalog.unavailable' } }) }) : route.continue());
  await english.fill('Synthetic root renamed');
  await save.click();
  await expect(page.getByRole('main').getByRole('alert')).toContainText('Your draft is preserved');
  await expect(english).toHaveValue('Synthetic root renamed');
  await page.unroute(`**/api/v1/admin/catalog/categories/${root.id}`);
  await save.click();
  await expect(page.locator('.admin-category-editor .success')).toContainText('Category saved');
  const publicRows = await (await context.request.get(`${base}/api/v1/catalog/categories`)).json();
  expect(publicRows.find((row: { id: string }) => row.id === root.id).name.en).toBe('Synthetic root renamed');
  await page.getByLabel('Search categories', { exact: true }).fill('nothing-matches-this');
  await expect(page.getByRole('heading', { name: 'No categories found' })).toBeVisible();
  await page.getByLabel('Search categories', { exact: true }).fill('');
  await expect(page.getByRole('button', { name: 'Edit Synthetic root renamed', exact: true })).toBeVisible();
  const errors: string[] = [];
  page.on('pageerror', e => errors.push(e.message));
  for (const locale of ['fa', 'en']) for (const theme of ['dark', 'light']) for (const width of [360, 768, 1440]) {
    await context.addCookies([{ name: 'nivaro-theme', value: theme, url: base }]);
    await page.setViewportSize({ width, height: 1100 });
    await page.goto(`/${locale}/admin/categories`);
    await page.getByRole('button', { name: locale === 'fa' ? 'ویرایش تجهیزات آزمایشی' : 'Edit Synthetic root renamed', exact: true }).click();
    await page.evaluate(() => document.fonts.ready);
    await page.evaluate(() => window.scrollTo(0, 0));
    await expect(page.locator('html')).toHaveAttribute('dir', locale === 'fa' ? 'rtl' : 'ltr');
    await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: test.info().outputPath(`${locale}-${theme}-${width}-categories.png`), fullPage: true, animations: 'disabled' });
  }
  expect(errors).toEqual([]);
});

test('media gallery: real processing, failed replacement, conflicts, cover and public views', async ({ page, context }) => {
  test.skip(process.env.NIVARO_MEDIA_BROWSER !== '1', 'Requires the disposable media worker overlay');
  test.setTimeout(180_000);
  if (staffCookies) await context.addCookies(staffCookies);
  else {
    const signed = await context.request.post(`${base}/api/v1/admin/auth/login`, { headers: { Origin: base }, data: { email: 'staff@example.com', password: adminPassword } });
    expect(signed.status()).toBe(200);
  }
  const list = await (await context.request.get(`${base}/api/v1/admin/catalog/products?q=RTX`)).json();
  const id = list.items[0].id;
  const endpoint = `${base}/api/v1/admin/catalog/products/${id}`;
  const readGallery = async () => (await (await context.request.get(`${endpoint}/images`)).json());
  const errors: string[] = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto(`/en/admin/products/${id}`);
  await page.getByRole('tab', { name: 'Images', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Product images', exact: true })).toBeVisible();
  async function upload(alt: string, invalid = false) {
    await page.getByLabel('Image file', { exact: true }).setInputFiles(invalid ? { name: 'forged.png', mimeType: 'image/png', buffer: Buffer.from('<svg>not an allowed image</svg>') } : path.resolve('public/images/gpu.webp'));
    await page.getByLabel('Persian alternative text').fill('نمای آزمایشی کارت گرافیک');
    await page.getByLabel('English alternative text').fill(alt);
    await page.getByRole('button', { name: 'Upload for processing', exact: true }).click();
    await expect(page.getByRole('status')).toContainText('Image received');
  }
  await upload('Synthetic graphics card view');
  await expect.poll(async () => (await readGallery()).items[0]?.pending?.state, { timeout: 30_000 }).toBe('ready');
  await expect(page.locator('.admin-gallery-tile img')).toBeVisible();
  const first = (await readGallery()).items[0].active.id;
  await page.getByRole('button', { name: 'Add image', exact: true }).click();
  await upload('Synthetic second view');
  await expect.poll(async () => (await readGallery()).items[1]?.pending?.state, { timeout: 30_000 }).toBe('ready');
  await expect(page.getByRole('button', { name: 'Use as cover image', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: 'Use as cover image', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Gallery updated');
  const cover = (await readGallery()).items[0].active.id;
  expect(cover).not.toBe(first);
  await upload('Rejected forged replacement', true);
  await expect(page.getByRole('main').getByRole('alert')).toContainText('could not be processed', { timeout: 30_000 });
  expect((await readGallery()).items[0].active.id).toBe(cover);
  await page.getByLabel('Image file', { exact: true }).setInputFiles(path.resolve('public/images/gpu.webp'));
  await page.getByLabel('Persian alternative text').fill('متن حفظ‌شده');
  await page.getByLabel('English alternative text').fill('Preserved image draft');
  const current = await (await context.request.get(endpoint)).json();
  const csrf = (await (await context.request.get(`${base}/api/v1/admin/auth/csrf`, { headers: { Origin: base, 'X-CSRF-Request': '1' } })).json()).csrf_token;
  const { slug, name, description, category_id, brand, highlights } = current;
  expect((await context.request.put(endpoint, { headers: { Origin: base, 'X-CSRF-Token': csrf }, data: { slug, name: name + ' media QA', description, category_id, brand, highlights, expected_version: current.version } })).status()).toBe(200);
  await page.getByRole('button', { name: 'Upload for processing', exact: true }).click();
  await expect(page.getByRole('main').getByRole('alert').first()).toContainText('product changed');
  await expect(page.getByLabel('English alternative text')).toHaveValue('Preserved image draft');
  expect(await page.getByLabel('Image file', { exact: true }).evaluate((el: HTMLInputElement) => el.files?.length)).toBe(1);
  await page.getByRole('button', { name: 'Discard file and text' }).click();
  await page.getByRole('button', { name: 'Reload current status' }).click();
  for (const locale of ['fa', 'en']) for (const theme of ['dark', 'light']) for (const width of [360, 768, 1440]) {
    await context.addCookies([{ name: 'nivaro-theme', value: theme, url: base }]);
    await page.setViewportSize({ width, height: 1100 });
    await page.goto(`/${locale}/admin/products/${id}`);
    await page.getByRole('tab', { name: locale === 'fa' ? 'تصاویر' : 'Images', exact: true }).click();
    await expect(page.locator('.admin-gallery-tile img')).toHaveCount(2);
    await page.evaluate(() => document.fonts.ready);
    await expect.poll(() => page.locator('.admin-gallery-tile img').evaluateAll(images => images.every(el => (el as HTMLImageElement).complete && (el as HTMLImageElement).naturalWidth > 0))).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: test.info().outputPath(`${locale}-${theme}-${width}-gallery.png`), fullPage: true, animations: 'disabled' });
    await page.goto(`/${locale}/products/${slug}`);
    await expect(page.locator('.product-gallery-thumbs button')).toHaveCount(2);
    await page.locator('.product-gallery-thumbs button').nth(1).click();
    await expect(page.locator('.detail-art > div img')).toHaveAttribute('alt', locale === 'fa' ? 'نمای آزمایشی کارت گرافیک' : 'Synthetic graphics card view');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: test.info().outputPath(`${locale}-${theme}-${width}-public-gallery.png`), fullPage: true, animations: 'disabled' });
  }
  await page.goto(`/en/admin/products/${id}`);
  await page.getByRole('tab', { name: 'Images', exact: true }).click();
  await page.getByRole('button', { name: 'Remove this image', exact: true }).click();
  await page.getByRole('button', { name: 'Confirm', exact: true }).click();
  await expect(page.locator('.admin-gallery-tile')).toHaveCount(1);
  const publicGallery = await context.request.get(`${base}/api/v1/catalog/products/${id}/images`);
  expect((await publicGallery.json()).map((item: { id: string }) => item.id)).toEqual([first]);
  expect((await context.request.get(`${base}/api/v1/catalog/images/${cover}/320`)).status()).toBe(404);
  expect(errors).toEqual([]);
});
test('admin credentials are separate; customer login never grants staff access', async ({ page, context }) => {
  test.setTimeout(90_000);
  await context.addCookies(seedCookies);
  expect((await context.request.get(`${base}/api/v1/admin/catalog/products`)).status()).toBe(401);
  expect((await context.request.post(`${base}/internal/v1/catalog/admin-check`, { data: {} })).status()).toBe(404);
  await page.goto('/en/admin/login');
  await expect(page.getByLabel('Email', { exact: true })).toBeVisible();
  await page.getByLabel('Email', { exact: true }).fill('staff@example.com');
  await page.getByLabel('Password', { exact: true }).fill('incorrect');
  await page.getByRole('button', { name: 'Sign in as administrator' }).click();
  await expect(page.getByRole('main').getByRole('alert')).toContainText('invalid');
  await page.getByLabel('Password', { exact: true }).fill(adminPassword);
  await page.getByRole('button', { name: 'Show password' }).click();
  await expect(page.getByLabel('Password', { exact: true })).toHaveAttribute('type', 'text');
  await page.getByRole('button', { name: 'Hide password' }).click();
  await page.getByRole('button', { name: 'Sign in as administrator' }).click();
  await expect(page.getByRole('heading', { name: 'Staff session' })).toBeVisible();
  await expect(page.getByText('Refunds', { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText('User management', { exact: true })).toBeVisible();
  const catalog = await context.request.get(`${base}/api/v1/admin/catalog/products`);
  expect(catalog.status()).toBe(200);
  const products = await catalog.json();
  expect(products.total).toBe(13);
  const productUrl = `${base}/api/v1/admin/catalog/products/${products.items[0].id}`;
  const productResponse = await context.request.get(productUrl);
  expect(productResponse.status()).toBe(200);
  const product = await productResponse.json();
  const beforeAudit = (await (await context.request.get(`${productUrl}/audit`)).json()).total;
  const { slug, name, description, category_id, brand, highlights } = product;
  const content = { slug, name, description, category_id, brand, highlights };
  const csrfResponse = await context.request.get(`${base}/api/v1/admin/auth/csrf`, { headers: { Origin: base, 'X-CSRF-Request': '1' } });
  expect(csrfResponse.status()).toBe(200);
  const { csrf_token: csrf } = await csrfResponse.json();
  const edit = { ...content, expected_version: product.version, name: `${name} QA` };
  expect((await context.request.put(productUrl, { headers: { Origin: base }, data: edit })).status()).toBe(403);
  expect((await context.request.put(productUrl, { headers: { Origin: 'https://untrusted.test', 'X-CSRF-Token': csrf }, data: edit })).status()).toBe(403);
  const headers = { Origin: base, 'X-CSRF-Token': csrf };
  const changed = await context.request.put(productUrl, { headers, data: edit });
  expect(changed.status()).toBe(200);
  expect((await changed.json()).version).toBe(product.version + 1);
  expect((await context.request.put(productUrl, { headers, data: edit })).status()).toBe(409);
  const restored = await context.request.put(productUrl, { headers, data: { ...content, expected_version: product.version + 1 } });
  expect(restored.status()).toBe(200);
  const audit = await context.request.get(`${productUrl}/audit`);
  expect(audit.status()).toBe(200);
  expect((await audit.json()).total).toBe(beforeAudit + 2);
  // Real outage in the disposable stack: a cached public key must not grant access.
  try {
    identityService('stop');
    expect((await context.request.get(`${base}/api/v1/admin/catalog/products`)).status()).toBe(503);
    expect((await context.request.put(productUrl, { headers, data: { ...content, expected_version: product.version + 2 } })).status()).toBe(503);
    expect((await context.request.get(`${base}/api/v1/catalog/products`)).status()).toBe(200);
  } finally {
    identityService('start');
    await expect.poll(async () => (await context.request.get(`${base}/api/v1/admin/catalog/products`)).status(), { timeout: 30_000 }).toBe(200);
  }
  // Role changes are checked by the server on the next request, not trusted from old JWTs.
  operator(`import asyncio
from sqlalchemy import update
from nivaro_identity.settings import Settings
from nivaro_identity.infrastructure.database import Database
from nivaro_identity.infrastructure.models import Administrator
assert Settings().environment == 'test'
async def change():
 db=Database(Settings())
 async with db.sessions() as s,s.begin():
  await s.execute(update(Administrator).values(role='support_agent'))
 await db.engine.dispose()
asyncio.run(change())`);
  expect((await context.request.get(`${base}/api/v1/admin/catalog/products`)).status()).toBe(401);
  await page.reload();
  await expect(page.getByText('Support replies', { exact: true })).toBeVisible();
  await expect(page.getByText('Refunds', { exact: true })).toHaveCount(0);
  expect((await context.request.get(`${base}/api/v1/admin/catalog/products`)).status()).toBe(403);
  await page.goto('/en/admin/products');
  await expect(page.getByText('This account does not have catalog management permission.')).toBeVisible();
  await expect(page.locator('.admin-table')).toHaveCount(0);
  await page.goto('/en/admin/login');
  await page.getByRole('button', { name: 'Sign out of staff session' }).click();
  await expect(page.getByLabel('Email', { exact: true })).toBeVisible();
  await page.goto('/en/account');
  await expect(page.locator('.account-sidebar')).toBeVisible();
});
test('service failure preserves profile draft and retry succeeds', async ({ page, context }) => {
  await context.addCookies(seedCookies);
  await page.goto('/fa/account/profile');
  await page.getByLabel('نام و نام خانوادگی', { exact: true }).fill('آزمایش قطع ارتباط');
  await page.route('**/api/v1/me', route => route.request().method() === 'PATCH' ? route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: { code: 'identity.unavailable', request_id: 'qa' } }) }) : route.continue());
  await page.getByRole('button', { name: 'ذخیرهٔ تغییرات' }).click();
  await expect(page.getByRole('main').getByRole('alert')).toContainText('حفظ شده');
  await expect(page.getByLabel('نام و نام خانوادگی')).toHaveValue('آزمایش قطع ارتباط');
  await page.unroute('**/api/v1/me');
  await page.getByRole('button', { name: 'ذخیرهٔ تغییرات' }).click();
  await expect(page.getByRole('status')).toContainText('ذخیره شد');
});
