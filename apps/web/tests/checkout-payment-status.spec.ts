import { expect, test } from '@playwright/test';
import type { OrderStatus } from '../src/lib/checkout-client';

const cases = [
  { pending: 'payment_processing', final: 'paid', progress: 'Payment verified, confirming stock', complete: 'Payment and stock confirmed' },
  { pending: 'refund_pending', final: 'refunded', progress: 'Refund in progress', complete: 'Refund confirmed' },
] as const;

for (const scenario of cases) test(`checkout refreshes ${scenario.pending}`, async ({ page }) => {
  const orderId = '80823862-d2d5-49a2-af72-f786ab0a5a25';
  let status: OrderStatus['status'] = scenario.pending;
  await page.route('**/api/v1/auth/session', route => route.fulfill({ json: { csrf_token: 'test' } }));
  await page.route(`**/api/v1/orders/${orderId}`, route => route.fulfill({
    json: { id: orderId, status, version: status === scenario.final ? 4 : 3,
      reservation_expires_at: null, failure_code: null, totals: { currency: 'USD', total_minor: 1000 } },
  }));

  await page.goto(`/en/checkout/result?order=${orderId}`);
  await expect(page.getByRole('heading', { name: scenario.progress })).toBeVisible();
  status = scenario.final;
  await expect(page.getByRole('heading', { name: scenario.complete })).toBeVisible();
  await expect(page.getByText('$10.00', { exact: true })).toBeVisible();
});
