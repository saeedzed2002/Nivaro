import { expect, test } from '@playwright/test';
import { spawnSync } from 'node:child_process';
import { randomBytes } from 'node:crypto';

const project = process.env.NIVARO_CHECKOUT_QA_PROJECT ?? '';
test.skip(!/^nivaro-orders-qa-[a-f0-9]{8}$/.test(project), 'Requires the disposable Orders stack and its synthetic delivery policy');

test('checkout reviews the owned cart, rejects a stale address and recovers an interrupted confirmation', async ({ page, baseURL }) => {
  test.setTimeout(120_000);
  const origin = new URL(baseURL!).origin;
  const exceptions: string[] = [];
  page.on('pageerror', error => exceptions.push(error.message));
  await page.goto('/en/checkout');
  await page.getByRole('link', { name: 'Sign in', exact: true }).click();
  await page.getByLabel('Mobile number', { exact: true }).fill('+12025550102');
  await page.getByRole('button', { name: 'Get sign-in code' }).click();
  const developmentCode = page.getByTestId('development-code');
  await expect(developmentCode).toBeVisible();
  await page.getByLabel('Sign-in code', { exact: true }).fill((await developmentCode.textContent())!);
  await page.getByRole('button', { name: 'Verify and sign in' }).click();
  await expect(page).toHaveURL(/\/en\/checkout$/);
  await expect(page.getByText('Your account cart is empty.')).toBeVisible();

  const session = await (await page.request.get('/api/v1/auth/session')).json();
  const headers = { Origin: origin, 'X-CSRF-Token': session.csrf_token };
  const home = {
    label: 'Home', recipient: 'Checkout Test', country: 'US', city: 'Washington',
    postal_code: '20001', street: '10 Example Street', phone: '+12025550102',
  };
  const first = await page.request.post('/api/v1/me/addresses', { data: home, headers });
  expect(first.status()).toBe(201);
  const work = { ...home, label: 'Work', street: '20 Example Street' };
  const second = await page.request.post('/api/v1/me/addresses', { data: work, headers });
  expect(second.status()).toBe(201);
  const address = await second.json();

  await page.goto('/en/products/amd-ryzen-7-9800x3d');
  await page.getByRole('button', { name: 'Add to cart', exact: true }).click();
  await expect(page.getByText('Added to your cart.')).toBeVisible();
  await page.getByRole('link', { name: 'Shopping cart (1)' }).click();
  await page.getByRole('link', { name: 'Continue to checkout' }).click();
  await expect(page.getByRole('heading', { name: 'Checkout', exact: true })).toBeVisible();
  await page.getByRole('radio', { name: /^Work/ }).check();
  await expect(page.getByRole('button', { name: 'Confirm order' })).toHaveCount(0);
  const coupon = page.getByRole('textbox', { name: 'Promo code', exact: true });
  const summary = page.getByRole('complementary', { name: 'Order summary' });
  const alert = summary.getByRole('alert');
  await coupon.fill('NOT-AVAILABLE');
  await page.getByRole('button', { name: 'Apply code' }).click();
  await expect(alert).toContainText('This promo code cannot be used for this order.');
  await coupon.clear();
  const review = page.getByRole('button', { name: 'Review final total' });
  await review.click();
  await expect(summary).toContainText('$466.00');

  const updated = await page.request.put(`/api/v1/me/addresses/${address.id}`, {
    data: { ...work, street: '22 Example Street', version: address.version }, headers,
  });
  expect(updated.status()).toBe(200);
  await page.getByRole('button', { name: 'Confirm order' }).click();
  await expect(alert).toContainText('The address changed.');
  await expect(page.getByRole('radio', { name: /22 Example Street/ })).toBeChecked();
  await review.click();
  await expect(summary).toContainText('$466.00');

  await page.getByRole('combobox', { name: 'Appearance' }).selectOption('light');
  await page.setViewportSize({ width: 375, height: 812 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
  await page.screenshot({ path: test.info().outputPath('checkout-en-light-mobile.png'), fullPage: true });

  let submittedId = '';
  await page.route('**/api/v1/orders/checkout/*/confirm', async route => {
    const response = await route.fetch();
    expect(response.status()).toBe(200);
    submittedId = (await response.json()).id;
    await route.abort('failed');
  });
  await page.getByRole('button', { name: 'Confirm order' }).click();
  await expect(page.getByRole('heading', { name: 'Order awaiting payment' })).toBeVisible();
  expect(submittedId).toMatch(/^[0-9a-f-]{36}$/);
  expect(new URL(page.url()).searchParams.get('order')).toBe(submittedId);
  await expect(page.getByText('$466.00', { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText(submittedId, { exact: true })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath('checkout-result-en-light-mobile.png'), fullPage: true });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByRole('combobox', { name: 'Appearance' }).selectOption('dark');
  await page.getByRole('link', { name: 'Switch language to Persian' }).click();
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  await expect(page.getByRole('heading', { name: 'سفارش در انتظار پرداخت' })).toBeVisible();
  await expect(page.getByText(submittedId, { exact: true })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath('checkout-result-fa-dark-desktop.png'), fullPage: true });
  await page.getByRole('link', { name: 'بازگشت به سبد خرید' }).click();
  await page.getByRole('link', { name: 'ادامه به تسویه' }).click();
  await page.getByRole('button', { name: 'محاسبهٔ مبلغ نهایی' }).click();
  await expect(page.getByRole('button', { name: 'تأیید و ثبت سفارش' })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath('checkout-fa-dark-desktop.png'), fullPage: true });
  if (process.env.NIVARO_CHECKOUT_QA_PAYMENTS === '1') {
    const orderUrl = `/api/v1/orders/${submittedId}`;
    await page.goto(`/fa/checkout/result?order=${submittedId}&status=paid&result=success`);
    await expect(page.getByRole('heading', { name: 'سفارش در انتظار پرداخت' })).toBeVisible();
    const before = await (await page.request.get(orderUrl)).json();
    expect(before.payment_state).toBeNull();
    let submittedPayment = false;
    await page.route(`**${orderUrl}/payment`, async route => {
      const response = await route.fetch();
      expect(response.status()).toBe(202);
      submittedPayment = true;
      await route.abort('failed');
    });
    await page.getByRole('button', { name: 'پرداخت آزمایشی' }).click();
    await expect.poll(() => submittedPayment).toBe(true);
    await page.reload();
    await expect(page.getByRole('heading', { name: 'پرداخت و موجودی سفارش تأیید شد' })).toBeVisible({ timeout: 20_000 });
    const replay = await page.request.post(`${orderUrl}/payment`, {
      headers: { ...headers, 'Idempotency-Key': submittedId }, data: { order_version: before.version },
    });
    expect(replay.status()).toBe(202);
    expect((await replay.json()).status).toBe('paid');
    await expect.poll(async () => {
      const cart = await page.request.get('/api/v1/cart?market=international');
      expect(cart.status()).toBe(200);
      return (await cart.json()).lines;
    }, { timeout: 12_000 }).toEqual([]);
    await page.goto('/fa/account/orders');
    await expect(page.getByRole('heading', { name: 'سفارش‌های من' })).toBeVisible();
    const orders = page.getByRole('listitem').filter({ hasText: submittedId });
    await expect(orders.getByText('پرداخت‌شده', { exact: true })).toBeVisible();
    const details = orders.getByRole('link', { name: 'مشاهدهٔ جزئیات' });
    await expect(details).toHaveAttribute('href', `/fa/account/orders/${submittedId}`);
    await page.screenshot({ path: test.info().outputPath('orders-fa-dark-desktop.png'), fullPage: true });
    await details.click();
    await expect(page.getByRole('heading', { name: 'جزئیات سفارش', exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'اقلام خریداری‌شده', exact: true })).toBeVisible();
    await expect(page.getByText('22 Example Street', { exact: true })).toBeVisible();
    await expect(page.getByRole('list', { name: 'تاریخچهٔ وضعیت' })).toContainText('پرداخت‌شده');
    await page.screenshot({ path: test.info().outputPath('order-detail-fa-dark-desktop.png'), fullPage: true });
    await page.getByRole('combobox', { name: 'حالت نمایش' }).selectOption('light');
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
    await page.setViewportSize({ width: 360, height: 800 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(360);
    await page.screenshot({ path: test.info().outputPath('order-detail-fa-light-mobile.png'), fullPage: true });
    await page.getByRole('link', { name: 'بازگشت به سفارش‌ها' }).click();
    await expect(orders.getByText('پرداخت‌شده', { exact: true })).toBeVisible();

    expect((await page.request.get('/api/v1/admin/orders/history')).status()).toBe(401);
    const password = randomBytes(24).toString('base64url');
    if (!/^nivaro-orders-qa-[a-f0-9]{8}$/.test(project)) throw new Error('Disposable Orders stack required');
    const setup = spawnSync('docker', ['exec', '-i', `${project}-identity-1`, 'python', '-c', `
import asyncio, builtins, getpass, sys
from nivaro_identity.settings import Settings
from nivaro_identity.manage import manage
assert Settings().environment == 'test'
answers = iter(['+12025550100', 'fulfillment@example.com'])
builtins.input = lambda _: next(answers)
password = sys.stdin.read()
getpass.getpass = lambda _: password
asyncio.run(manage('bootstrap-admin'))
`], { input: password, encoding: 'utf8', timeout: 20_000 });
    expect(setup.status, 'Disposable staff bootstrap').toBe(0);

    const staffContext = await page.context().browser()!.newContext({ baseURL, viewport: { width: 1487, height: 1058 } });
    try {
      const staff = await staffContext.newPage();
      staff.on('pageerror', error => exceptions.push(error.message));
      await staff.goto('/en/admin/login');
      await staff.getByLabel('Email').fill('fulfillment@example.com');
      await staff.getByLabel('Password', { exact: true }).fill(password);
      await staff.getByRole('button', { name: 'Sign in as administrator', exact: true }).click();
      await staff.getByRole('link', { name: 'Manage orders' }).click();
      await staff.getByRole('combobox', { name: 'Appearance' }).selectOption('dark');
      await staff.getByLabel('Status', { exact: true }).selectOption('paid');
      const row = staff.getByRole('row').filter({ hasText: submittedId });
      await expect(row.getByText('Paid', { exact: true })).toBeVisible();
      await staff.setViewportSize({ width: 1983, height: 793 });
      await staff.screenshot({ path: test.info().outputPath('staff-orders-en-dark-desktop.png'), fullPage: true });
      await row.getByRole('link', { name: 'View order' }).click();
      await staff.setViewportSize({ width: 1487, height: 1058 });
      await expect(staff.getByText('22 Example Street', { exact: true })).toBeVisible();
      await expect(staff.getByText('AMD Ryzen 7 9800X3D', { exact: true })).toBeVisible();
      const fulfillment = staff.getByRole('region', { name: 'Fulfillment', exact: true });
      const audit = staff.getByRole('list', { name: 'Order audit timeline' });
      await fulfillment.getByRole('button', { name: 'Start preparation' }).click();
      const tracking = fulfillment.getByLabel('Tracking reference');
      await expect(tracking).toBeVisible();
      await expect(audit).toContainText('Preparing');
      await tracking.fill('A2-5105');
      await staff.screenshot({ path: test.info().outputPath('staff-order-en-dark-desktop.png'), fullPage: true });

      const staffUrl = `/api/v1/admin/orders/${submittedId}/fulfillment`;
      await staff.route(`**${staffUrl}`, async route => {
        if (route.request().method() !== 'POST') { await route.continue(); return; }
        const response = await route.fetch();
        expect(response.status()).toBe(200);
        await route.abort('failed');
      }, { times: 1 });
      await fulfillment.getByRole('button', { name: 'Record shipment' }).click();
      await expect(fulfillment.getByRole('alert')).toContainText('No response received.');
      await expect(tracking).toHaveValue('A2-5105');
      await fulfillment.getByRole('button', { name: 'Record shipment' }).click();
      await expect(audit.getByText('Shipped', { exact: true })).toHaveCount(1);
      await fulfillment.getByRole('button', { name: 'Record delivery' }).click();
      await expect(audit.getByText('Delivered', { exact: true })).toBeVisible();
      await expect(audit.getByText(/Staff ID/)).toHaveCount(3);
      await staff.goto(`/fa/admin/orders/${submittedId}`);
      await staff.getByRole('combobox', { name: 'حالت نمایش' }).selectOption('light');
      await staff.setViewportSize({ width: 360, height: 800 });
      await expect(staff.getByRole('region', { name: 'عملیات ارسال و تحویل' })).toContainText('A2-5105');
      expect(await staff.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(360);
      await staff.screenshot({ path: test.info().outputPath('staff-order-fa-light-mobile.png'), fullPage: true });
      await staff.getByRole('link', { name: 'بازگشت به سفارش‌ها' }).click();
      await expect(staff.locator('tr').filter({ hasText: submittedId }).getByText('تحویل‌شده', { exact: true })).toBeVisible();
      expect(await staff.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(360);
      await staff.screenshot({ path: test.info().outputPath('staff-orders-fa-light-mobile.png'), fullPage: true });
    } finally {
      await staffContext.close();
    }
    await page.goto(`/fa/account/orders/${submittedId}`);
    await expect(page.getByText('A2-5105', { exact: true })).toBeVisible();
    await expect(page.getByRole('list', { name: 'تاریخچهٔ وضعیت' })).toContainText('تحویل‌شده');
  }
  expect(exceptions).toEqual([]);
});
