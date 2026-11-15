import { expect, test } from '@playwright/test';

const project = process.env.NIVARO_CHECKOUT_QA_PROJECT ?? '';
test.skip(!/^nivaro-orders-qa-[a-f0-9]{8}$/.test(project), 'Requires the disposable Orders stack and its synthetic delivery policy');

test('checkout reviews the owned cart, rejects a stale address and recovers an interrupted confirmation', async ({ page, baseURL }) => {
  test.setTimeout(90_000);
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
  }
  expect(exceptions).toEqual([]);
});
