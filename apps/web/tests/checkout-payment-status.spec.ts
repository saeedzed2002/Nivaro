import { expect, test } from '@playwright/test';
import type { OrderStatus } from '../src/lib/checkout-client';

test('checkout status refreshes while the verified payment awaits stock', async ({ page }) => {
  const orderId = '80823862-d2d5-49a2-af72-f786ab0a5a25';
  let status: OrderStatus['status'] = 'payment_processing';
  await page.route('**/api/v1/auth/session', route => route.fulfill({ json: { csrf_token: 'test' } }));
  await page.route(`**/api/v1/orders/${orderId}`, route => route.fulfill({
    json: { id: orderId, status, version: status === 'paid' ? 4 : 3,
      reservation_expires_at: null, failure_code: null, totals: { currency: 'USD', total_minor: 1000 } },
  }));

  await page.goto(`/en/checkout/result?order=${orderId}`);
  await expect(page.getByRole('heading', { name: 'Payment verified, confirming stock' })).toBeVisible();
  status = 'paid';
  await expect(page.getByRole('heading', { name: 'Payment and stock confirmed' })).toBeVisible();
  await expect(page.getByText('$10.00', { exact: true })).toBeVisible();
});
