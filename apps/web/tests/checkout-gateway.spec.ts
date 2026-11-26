import { expect, test } from '@playwright/test';
import { spawnSync } from 'node:child_process';
import { randomBytes } from 'node:crypto';

const project = process.env.NIVARO_CHECKOUT_QA_PROJECT ?? '';
test.skip(!/^nivaro-orders-qa-[a-f0-9]{8}$/.test(project), 'Requires the disposable Orders stack and its synthetic delivery policy');

function purchaseEntitlements(orderId: string, customerId: string) {
  if (!/^nivaro-orders-qa-[a-f0-9]{8}$/.test(project)) throw new Error('Disposable Orders stack required');
  const query = spawnSync('docker', [
    'exec', '-i', `${project}-postgres-1`, 'psql', '-U', 'postgres', '-d', 'nivaro_catalog',
    '-At', '-v', 'ON_ERROR_STOP=1', '-v', `order_id=${orderId}`, '-v', `customer_id=${customerId}`,
  ], { encoding: 'utf8', timeout: 10_000, input: `
    SELECT (SELECT count(*) FROM purchase_entitlements e JOIN products p ON p.id = e.product_id
            WHERE e.customer_id = :'customer_id'::uuid AND p.slug = 'amd-ryzen-7-9800x3d'),
           (SELECT count(*) FROM delivered_order_inbox WHERE order_id = :'order_id'::uuid);
  ` });
  expect(query.status, 'Read entitlement from the disposable catalog').toBe(0);
  return query.stdout.trim();
}

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
  const variant = page.getByRole('combobox', { name: 'Variant', exact: true });
  const options = await variant.locator('option').evaluateAll(items => items.map(option => (option as HTMLOptionElement).value));
  expect(options).toHaveLength(2);
  const chosen = await variant.inputValue();
  const initialIsFirst = chosen === options[0];
  await variant.press(initialIsFirst ? 'End' : 'Home');
  await expect(variant).toHaveValue(initialIsFirst ? options[1] : options[0]);
  await variant.press(initialIsFirst ? 'Home' : 'End');
  await expect(variant).toHaveValue(chosen);
  await page.getByRole('button', { name: 'Add to cart', exact: true }).press('Enter');
  await expect(page.getByText('Added to your cart.')).toBeVisible();
  await page.getByRole('link', { name: 'Shopping cart (1)' }).click();
  const controls = page.getByRole('group', { name: /^Quantity: AMD Ryzen 7 9800X3D/ });
  const increase = controls.getByRole('button', { name: /^Increase quantity/ });
  const decrease = controls.getByRole('button', { name: /^Decrease quantity/ });
  await expect(decrease).toBeDisabled();
  await increase.press('Enter');
  await expect(page.getByText('2 items in your cart', { exact: true })).toBeVisible();
  await expect(decrease).toBeEnabled();
  await decrease.press('Enter');
  await expect(page.getByText('1 item in your cart', { exact: true })).toBeVisible();
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
    const paymentAttemptsUrl = '/api/v1/admin/payments/attempts';
    const refundQueueUrl = '/api/v1/admin/payments/refunds';
    expect((await page.request.get(paymentAttemptsUrl)).status()).toBe(401);
    expect((await page.request.get(refundQueueUrl)).status()).toBe(401);
    await page.goto('/en/admin/payments');
    await expect(page.getByRole('heading', { name: 'Payment administration access' })).toBeVisible();
    await expect(page.getByRole('table', { name: 'Payment attempts' })).toHaveCount(0);
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

    const staffContext = await page.context().browser()!.newContext({ baseURL, timezoneId: 'America/Los_Angeles', viewport: { width: 1487, height: 1058 } });
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
      const marketFilter = staff.getByLabel('Market', { exact: true });
      const referenceFilter = staff.getByLabel('Order reference', { exact: true });
      const applyFilters = staff.getByRole('button', { name: 'Apply filters' });
      const row = staff.getByRole('row').filter({ hasText: submittedId });
      const createdAt = await row.locator('time').getAttribute('datetime');
      expect(createdAt).toBeTruthy();
      await expect(row.locator('time')).toHaveText(new Intl.DateTimeFormat('en-US', {
        timeZone: 'Asia/Tehran', dateStyle: 'short', timeStyle: 'short',
      }).format(new Date(createdAt!)));
      await referenceFilter.fill('invalid');
      await applyFilters.press('Enter');
      await expect(staff.getByRole('alert').filter({ hasText: 'Enter the full order reference.' })).toBeVisible();
      await referenceFilter.fill(submittedId);
      await marketFilter.selectOption('ir');
      await applyFilters.click();
      await expect(staff.getByText('No orders match these filters.')).toBeVisible();
      await marketFilter.selectOption('international');
      const placedOn = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Tehran', dateStyle: 'short' }).format(new Date(createdAt!));
      await staff.getByLabel('Placed from (Tehran time)', { exact: true }).fill(placedOn);
      await staff.getByLabel('Placed through (Tehran time)', { exact: true }).fill(placedOn);
      await applyFilters.click();
      await expect(row.getByText('Paid', { exact: true })).toBeVisible();
      await expect(staff.getByRole('table', { name: 'Order list' }).locator('tbody tr')).toHaveCount(1);
      const ordersHistoryUrl = '/api/v1/admin/orders/history';
      const reversedDates = await staff.request.get(ordersHistoryUrl, { params: { placed_from: '2026-11-16', placed_through: '2026-11-15' } });
      expect(reversedDates.status()).toBe(422);
      expect((await reversedDates.json()).error.code).toBe('orders.invalid_date_range');
      expect((await staff.request.get(ordersHistoryUrl, { params: { placed_through: '9999-12-31' } })).status()).toBe(422);
      await staff.setViewportSize({ width: 1983, height: 793 });
      await staff.screenshot({ path: test.info().outputPath('staff-orders-en-dark-desktop.png'), fullPage: true });
      await staff.setViewportSize({ width: 360, height: 800 });
      expect(await staff.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(360);
      await staff.screenshot({ path: test.info().outputPath('staff-order-filters-en-dark-mobile.png'), fullPage: true });
      await staff.getByRole('button', { name: 'Clear filters' }).click();
      await expect(referenceFilter).toHaveValue('');
      await expect(marketFilter).toHaveValue('');
      const paymentList = await staff.request.get(paymentAttemptsUrl, {
        params: { order_id: submittedId, status: 'succeeded', market: 'international' },
      });
      expect(paymentList.status()).toBe(200);
      expect(paymentList.headers()['cache-control']).toBe('no-store');
      const { attempts } = await paymentList.json();
      expect(attempts).toHaveLength(1);
      const paymentDetail = await staff.request.get(`${paymentAttemptsUrl}/${attempts[0].id}`);
      expect(paymentDetail.status()).toBe(200);
      const paymentData = await paymentDetail.json();
      expect(paymentData).toMatchObject({
        attempt: { order_id: submittedId, amount_minor: 46600, captured_minor: 46600, currency: 'USD' },
        order: { status: 'paid', recorded_outcome: 'payment.succeeded', disposition: 'selected', compensation: null },
      });
      await staff.getByRole('link', { name: 'Payments', exact: true }).click();
      await staff.setViewportSize({ width: 1440, height: 1050 });
      await expect(staff).toHaveTitle(/Payments & reconciliation/);
      await staff.getByLabel('Order reference', { exact: true }).fill(submittedId);
      await staff.getByRole('combobox', { name: 'Market', exact: true }).selectOption('ir');
      const applyPayments = staff.getByRole('button', { name: 'Apply filters' });
      await applyPayments.press('Enter');
      await expect(staff.getByText('No payment attempts match these filters.')).toBeVisible();
      await staff.getByRole('combobox', { name: 'Market', exact: true }).selectOption('international');
      await applyPayments.click();
      const paymentRow = staff.getByRole('table', { name: 'Payment attempts' }).getByRole('button', { name: new RegExp(attempts[0].id) });
      await paymentRow.press('Enter');
      await expect(paymentRow).toHaveAttribute('aria-pressed', 'true');
      await expect(staff.getByRole('region', { name: 'Payment detail' }).getByText('$466.00', { exact: true })).toHaveCount(2);
      await expect(staff.getByText('No refund is recorded for this attempt.')).toBeVisible();

      const refundQueue = await staff.request.get(refundQueueUrl, { params: { state: 'completed', market: 'ir' } });
      expect(refundQueue.status()).toBe(200);
      const { refunds } = await refundQueue.json();
      const completedRefund = refunds.find((refund: { reason: string }) => refund.reason === 'payment.amount_mismatch');
      expect(completedRefund).toMatchObject({ currency: 'IRR', state: 'completed' });
      expect(completedRefund.confirmed_refund_minor).toBe(completedRefund.captured_minor);
      await staff.getByRole('link', { name: 'Refund queue', exact: true }).click();
      await expect(staff.getByRole('heading', { name: 'Refund queue' })).toBeVisible();
      await staff.getByLabel('Order reference', { exact: true }).fill(completedRefund.order_id);
      await staff.getByRole('button', { name: 'Apply filters' }).click();
      await expect(staff.getByText('No refunds match these filters.')).toBeVisible();
      await staff.getByRole('combobox', { name: 'State', exact: true }).selectOption('completed');
      await staff.getByRole('combobox', { name: 'Market', exact: true }).selectOption('ir');
      await staff.getByRole('button', { name: 'Apply filters' }).click();
      const refundRow = staff.getByRole('row').filter({ hasText: completedRefund.refund_id });
      await expect(refundRow.getByText('Completed', { exact: true })).toBeVisible();
      await staff.screenshot({ path: test.info().outputPath('admin-refunds-en-dark.png'), fullPage: true });
      await refundRow.getByRole('link', { name: 'View payment' }).click();
      await expect(staff).toHaveURL(new RegExp(`/admin/payments\\?attempt=${completedRefund.attempt_id}$`));
      await expect(staff.getByRole('region', { name: 'Payment detail' }).getByText(completedRefund.attempt_id, { exact: true })).toBeVisible();
      await expect(staff.getByRole('region', { name: 'Order & refund' }).getByText(completedRefund.refund_id, { exact: true })).toBeVisible();
      const pendingList = await staff.request.get(paymentAttemptsUrl, { params: { order_id: completedRefund.order_id, status: 'pending' } });
      expect(pendingList.status()).toBe(200);
      const [pendingAttempt] = (await pendingList.json()).attempts;
      expect(pendingAttempt.status).toBe('pending');
      const commandUrl = `${paymentAttemptsUrl}/${pendingAttempt.id}/reconcile`;
      const rejected = await staff.request.post(commandUrl, {
        headers: { Origin: origin, 'X-CSRF-Token': 'invalid', 'Idempotency-Key': randomBytes(16).toString('hex') },
      });
      expect(rejected.status()).toBe(403);
      await staff.goto(`/en/admin/payments?attempt=${pendingAttempt.id}`);
      const check = staff.getByRole('button', { name: 'Recheck payment status', exact: true });
      let operationId = '';
      await staff.route(`**${commandUrl}`, async route => {
        operationId = route.request().headers()['idempotency-key'];
        const accepted = await route.fetch();
        expect(accepted.status()).toBe(200);
        await route.abort('failed');
      }, { times: 1 });
      await check.click();
      await staff.getByRole('dialog').getByRole('button', { name: 'Confirm', exact: true }).click();
      await expect(staff.getByText('Could not load payment information.')).toBeVisible();
      await check.click();
      const replayed = staff.waitForResponse(response => response.url().endsWith(commandUrl) && response.request().method() === 'POST');
      await staff.getByRole('dialog').getByRole('button', { name: 'Confirm', exact: true }).click();
      const replayedRun = await replayed;
      expect(replayedRun.request().headers()['idempotency-key']).toBe(operationId);
      expect(await replayedRun.json()).toMatchObject({ result: 'observed', status_before: 'pending', status_after: 'failed' });
      await expect(staff.getByText('Provider observation recorded.')).toBeVisible();
      await expect(staff.getByRole('region', { name: 'Payment detail' }).getByText('Failed', { exact: true })).toBeVisible();

      const paymentsPreview = await staffContext.newPage();
      paymentsPreview.on('pageerror', error => exceptions.push(error.message));
      const mismatch = { ...paymentData.attempt, captured_minor: 46601, status: 'amount_mismatch' };
      const compensation = { refund_id: '63beddc3-f140-43ff-a04b-bf90158aefdd', captured_minor: 46601,
        closes_order: false, reason: 'payment.amount_mismatch', state: 'awaiting_evidence', retry_at: null, last_error: null };
      await paymentsPreview.route(`**${paymentAttemptsUrl}**`, async route => {
        const pathname = new URL(route.request().url()).pathname;
        await route.fulfill({ json: pathname === paymentAttemptsUrl ? { attempts: [mismatch], next_before: null }
          : { attempt: mismatch, order: { ...paymentData.order, recorded_outcome: 'payment.amount_mismatch', disposition: 'payment.amount_mismatch', compensation } } });
      });
      await paymentsPreview.goto('/en/admin/payments');
      await expect(paymentsPreview.getByRole('region', { name: 'Payment detail' }).getByText('+$0.01', { exact: true })).toBeVisible();
      await expect(paymentsPreview.getByRole('region', { name: 'Order & refund' }).getByText('Awaiting evidence')).toBeVisible();
      await paymentsPreview.screenshot({ path: test.info().outputPath('admin-payments-en-dark.png'), fullPage: true });
      await paymentsPreview.setViewportSize({ width: 390, height: 844 });
      await paymentsPreview.goto('/fa/admin/payments');
      await paymentsPreview.getByRole('combobox', { name: 'حالت نمایش' }).selectOption('light');
      await expect(paymentsPreview.getByRole('region', { name: 'سفارش و بازپرداخت' }).getByText('منتظر تأیید بازپرداخت')).toBeVisible();
      expect(await paymentsPreview.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
      await paymentsPreview.screenshot({ path: test.info().outputPath('admin-payments-fa-light.png'), fullPage: true });
      await paymentsPreview.getByRole('link', { name: 'صف بازپرداخت', exact: true }).click();
      await paymentsPreview.getByRole('combobox', { name: 'وضعیت', exact: true }).selectOption('completed');
      await paymentsPreview.getByLabel('شناسهٔ سفارش', { exact: true }).fill(completedRefund.order_id);
      await paymentsPreview.getByRole('button', { name: 'اعمال فیلترها', exact: true }).click();
      await expect(paymentsPreview.getByRole('row').filter({ hasText: completedRefund.refund_id })).toBeVisible();
      expect(await paymentsPreview.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
      await paymentsPreview.screenshot({ path: test.info().outputPath('admin-refunds-fa-light.png'), fullPage: true });
      await paymentsPreview.close();
      await staff.goto('/en/admin/orders');
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
      expect(purchaseEntitlements(submittedId, session.profile.id)).toBe('0|0');
      await fulfillment.getByRole('button', { name: 'Record delivery' }).click();
      await expect(audit.getByText('Delivered', { exact: true })).toBeVisible();
      await expect(audit.getByText(/Staff ID/)).toHaveCount(3);
      await expect.poll(() => purchaseEntitlements(submittedId, session.profile.id), { timeout: 15_000 }).toBe('1|1');

      const product = await page.request.get('/api/v1/catalog/products/amd-ryzen-7-9800x3d');
      expect(product.status()).toBe(200);
      const reviewUrl = `/api/v1/catalog/products/${(await product.json()).id}/reviews`;
      const moderatorUrl = '/api/v1/admin/catalog/reviews';
      expect((await page.request.get(moderatorUrl)).status()).toBe(401);
      const productPage = '/en/products/amd-ryzen-7-9800x3d';
      const reviewText = 'Delivers the expected performance. <b>Literal text</b>';
      const newReview = { rating: 5, body: reviewText, expected_version: 0 };
      expect((await page.request.put(`${reviewUrl}/mine`, { headers: { Origin: origin }, data: newReview })).status()).toBe(403);
      expect((await page.request.put(`${reviewUrl}/mine`, { headers, data: { ...newReview, verified_purchase: true } })).status()).toBe(422);
      await page.goto(`${productPage}#reviews`);
      const panel = page.getByRole('region', { name: 'Customer reviews' });
      await panel.getByRole('button', { name: 'Write a review' }).press('Enter');
      const rating = panel.getByRole('group', { name: 'Rating', exact: true });
      await rating.getByRole('radio', { name: '4', exact: true }).press('Space');
      await rating.getByRole('radio', { name: '4', exact: true }).press('ArrowRight');
      await expect(rating.getByRole('radio', { name: '5', exact: true })).toBeChecked();
      await panel.getByRole('textbox', { name: 'Review text' }).fill(reviewText);
      await panel.getByRole('button', { name: 'Submit review' }).press('Enter');
      await expect(panel.getByRole('status').filter({ hasText: 'Review submitted for moderation.' })).toBeVisible();
      const submittedReviews = await Promise.all(Array.from({ length: 3 }, () => page.request.put(`${reviewUrl}/mine`, { headers, data: newReview })));
      expect(submittedReviews.map(response => response.status())).toEqual([200, 200, 200]);
      const reviews = await Promise.all(submittedReviews.map(response => response.json()));
      const review = reviews[0];
      expect(new Set(reviews.map(entry => entry.id)).size).toBe(1);
      expect(review).toMatchObject({ status: 'pending', verified_purchase: true });
      expect(await (await page.request.get(reviewUrl)).json()).toMatchObject({ count: 0, average_rating: null, reviews: [] });
      const guest = await page.context().browser()!.newPage({ baseURL });
      try {
        await guest.goto(`${productPage}#reviews`);
        await expect(guest.getByText('No approved reviews yet.')).toBeVisible();
        await expect(guest.getByText(reviewText, { exact: true })).toHaveCount(0);
        await guest.getByRole('button', { name: 'Write a review' }).click();
        await expect(guest.getByRole('link', { name: 'Sign in to write a review' })).toHaveAttribute('href', '/en/login?next=review&product=amd-ryzen-7-9800x3d');
      } finally {
        await guest.close();
      }
      const adminSession = await (await staff.request.get('/api/v1/admin/auth/session')).json();
      const adminHeaders = { Origin: origin, 'X-CSRF-Token': adminSession.csrf_token };
      expect((await (await staff.request.get(moderatorUrl)).json()).reviews).toContainEqual(expect.objectContaining({ id: review.id, status: 'pending' }));
      const decisionUrl = `${moderatorUrl}/${review.id}/decision`;
      const approval = { status: 'approved', reason: 'Clear first-hand feedback', expected_version: review.version };
      await staff.goto('/en/admin/reviews');
      await staff.setViewportSize({ width: 1672, height: 941 });
      const details = staff.getByRole('region', { name: 'Selected review' });
      await expect(details.getByText(reviewText, { exact: true })).toBeVisible();
      await expect(details.getByText('Verified purchase')).toBeVisible();
      await details.getByRole('textbox', { name: 'Decision reason' }).fill(approval.reason);
      await staff.screenshot({ path: test.info().outputPath('reviews-staff-en-dark.png'), fullPage: true });
      await details.getByRole('button', { name: 'Approve review' }).press('Enter');
      await expect(staff.getByRole('status').filter({ hasText: 'Review decision saved.' })).toBeVisible();
      const approved = await staff.request.post(decisionUrl, { headers: adminHeaders, data: approval });
      expect(approved.status()).toBe(200);
      expect(await approved.json()).toMatchObject({ status: 'approved', version: review.version + 1 });
      const published = await (await page.request.get(reviewUrl)).json();
      expect(published).toMatchObject({ count: 1, average_rating: 5, reviews: [{ id: review.id, verified_purchase: true }] });
      expect(published.reviews[0]).not.toHaveProperty('customer_id');
      expect(published.reviews[0]).not.toHaveProperty('moderation_reason');
      const ranked = await page.request.get('/api/v1/catalog/products?sort=rating&page_size=1');
      expect(ranked.status()).toBe(200);
      expect((await ranked.json()).items[0].slug).toBe('amd-ryzen-7-9800x3d');
      await page.goto('/en/login?next=review&product=amd-ryzen-7-9800x3d');
      await expect(page).toHaveURL(new RegExp(`${productPage}\\?review=1#reviews$`));
      await page.setViewportSize({ width: 1448, height: 1086 });
      await page.getByRole('combobox', { name: 'Appearance' }).selectOption('dark');
      const approvedReviews = panel.getByRole('list', { name: 'Approved reviews' });
      await expect(approvedReviews.getByText(reviewText, { exact: true })).toBeVisible();
      await expect(approvedReviews.getByText('Verified purchase')).toBeVisible();
      await expect(approvedReviews.locator('b')).toHaveCount(0);
      await expect(panel.getByText('1 approved review')).toBeVisible();
      await panel.screenshot({ path: test.info().outputPath('reviews-product-en-dark.png') });
      await rating.getByRole('radio', { name: '4', exact: true }).press('Space');
      const edit = page.waitForResponse(response => response.request().method() === 'PUT' && response.url().endsWith(`${reviewUrl}/mine`));
      await panel.getByRole('button', { name: 'Submit review' }).press('Enter');
      const edited = await edit;
      expect(edited.status()).toBe(200);
      const updatedReview = await edited.json();
      expect(updatedReview).toMatchObject({ id: review.id, status: 'pending', moderation_reason: null });
      expect((await staff.request.post(decisionUrl, { headers: adminHeaders, data: approval })).status()).toBe(409);
      const rejection = { status: 'rejected', reason: 'Include specific performance details', expected_version: updatedReview.version };
      await expect(panel.getByText('No approved reviews yet.')).toBeVisible();
      await staff.goto('/fa/admin/reviews');
      await staff.getByRole('combobox', { name: 'حالت نمایش' }).selectOption('light');
      await staff.setViewportSize({ width: 360, height: 800 });
      const detailsFa = staff.getByRole('region', { name: 'دیدگاه انتخاب‌شده' });
      await expect(detailsFa.getByText(reviewText, { exact: true })).toBeVisible();
      await detailsFa.getByRole('textbox', { name: 'دلیل تصمیم' }).fill(rejection.reason);
      expect(await staff.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(360);
      await staff.screenshot({ path: test.info().outputPath('reviews-staff-fa-light.png'), fullPage: true });
      await detailsFa.getByRole('button', { name: 'رد دیدگاه' }).press('Enter');
      await expect(staff.getByRole('status').filter({ hasText: 'تصمیم بررسی ثبت شد.' })).toBeVisible();
      const own = await page.request.get(`${reviewUrl}/mine`);
      expect(own.status()).toBe(200);
      expect((await own.json()).review).toMatchObject({ id: review.id, status: 'rejected', moderation_reason: rejection.reason });
      expect((await (await page.request.get(reviewUrl)).json()).reviews).toEqual([]);
      await page.goto('/fa/products/amd-ryzen-7-9800x3d?review=1#reviews');
      await page.getByRole('combobox', { name: 'حالت نمایش' }).selectOption('light');
      await page.setViewportSize({ width: 360, height: 800 });
      const productFa = page.getByRole('region', { name: 'دیدگاه خریداران' });
      await expect(productFa.getByText('ردشده')).toBeVisible();
      await expect(productFa.getByText(rejection.reason, { exact: true })).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(360);
      await productFa.screenshot({ path: test.info().outputPath('reviews-product-fa-light.png') });

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
