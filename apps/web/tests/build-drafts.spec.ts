import { expect, test } from '@playwright/test';

const first = { id: 'draft-a', name: 'Studio Tower', market: 'international', currency: 'USD', mode: 'parts_only', version: 1,
  requires_dedicated_gpu: false, selections: [{ slot_key: 'storage:1', variant_id: 'fixture-ssd', quantity: 1 }] };
const second = { ...first, id: 'draft-b', name: 'Quiet Build' };
const evaluation = { status: 'incomplete', findings: [], estimated_power_w: null };

test('saved builds copy and compare on mobile, preserve transfer retry, and save a new revision', async ({ page }) => {
  let drafts = [first];
  const transferKeys: string[] = [];
  let reviewCount = 0;
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/api/v1/auth/**', route => route.fulfill({ status: 401, json: { error: { code: 'auth.required' } } }));
  await page.route('**/api/v1/cart{,/**,?*}', async route => {
    if (new URL(route.request().url()).pathname.endsWith('/session')) return route.fulfill({ json: { csrf_token: 'test-csrf' } });
    return route.fulfill({ json: { id: 'cart', owner_scope: 'guest', lines: [], groups: [] } });
  });
  await page.route('**/api/v1/builds{,/**,?*}', async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path.endsWith('/duplicate')) {
      expect(request.postDataJSON().expected_version).toBe(1);
      expect(request.headers()['x-csrf-token']).toBe('test-csrf');
      drafts = [...drafts, { ...second, name: request.postDataJSON().name }];
      return route.fulfill({ status: 201, json: drafts[1] });
    }
    if (path.endsWith('/comparison')) {
      const column = (build: typeof first) => ({ build, evaluation, known_components_minor: build.id === first.id ? '12599' : null, known_peripherals_minor: null, unpriced_slots: [] });
      return route.fulfill({ json: { market: 'international', price_status: 'ready', left: column(drafts[0]), right: column(drafts[1]), slots: [{
        slot_key: 'storage:1', different: true, left: { quantity: 1, summary: { name: 'Example NVMe SSD', offer: { amount_minor: 12599 } } },
        right: { quantity: 2, summary: { name: 'Example NVMe SSD', offer: null } },
      }] } });
    }
    if (path.endsWith('/cart-transfers')) {
      transferKeys.push(request.headers()['idempotency-key']);
      expect(request.postDataJSON().review_digest).toBe('a'.repeat(64));
      if (transferKeys.length === 1) return route.abort('connectionreset');
      return route.fulfill({ status: 201, json: { group_id: 'group', cart_version: 2 } });
    }
    const draft = drafts.find(build => path.includes(build.id));
    if (path.endsWith('/review')) {
      reviewCount++;
      return route.fulfill({ json: { build: draft, cart_version: 1, review_digest: 'a'.repeat(64), blocker: null, evaluation, lines: [] } });
    }
    if (draft && request.method() === 'PATCH') {
      const change = request.postDataJSON();
      expect(change.expected_version).toBe(1);
      expect(change.selections).toEqual(first.selections);
      const updated = { ...draft, name: change.name, version: 2 };
      drafts = drafts.map(item => item.id === draft.id ? updated : item);
      return route.fulfill({ json: updated });
    }
    return route.fulfill({ json: draft ?? drafts });
  });
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto('/en/build/saved');
  await page.getByRole('combobox', { name: 'Appearance' }).selectOption('dark');
  await page.getByRole('button', { name: 'Duplicate', exact: true }).click();
  await page.getByLabel('Copy name').fill('Quiet Build');
  await page.getByRole('button', { name: 'Create copy' }).click();
  await expect(page.getByRole('heading', { name: 'Quiet Build' })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath('saved-desktop.png'), fullPage: true });
  await page.getByRole('checkbox', { name: 'Select for comparison: Studio Tower' }).check();
  await page.getByRole('checkbox', { name: 'Select for comparison: Quiet Build' }).check();
  await page.getByRole('link', { name: 'Compare selected builds' }).click();
  await expect(page.getByText('$125.99', { exact: true }).first()).toBeVisible();
  await page.setViewportSize({ width: 375, height: 812 });
  await page.getByRole('combobox', { name: 'Appearance' }).selectOption('light');
  await page.getByRole('link', { name: 'Switch language to Persian' }).click();
  await expect(page.getByRole('heading', { name: 'مقایسهٔ سیستم‌ها', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Studio Tower' })).toBeVisible();
  await expect(page.getByRole('rowheader', { name: /ذخیره‌سازی/ })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
  await page.screenshot({ path: test.info().outputPath('compare-mobile-fa.png'), fullPage: true });
  await page.getByRole('link', { name: 'تغییر زبان به انگلیسی' }).click();
  await page.getByRole('link', { name: 'Quiet Build', exact: true }).click();
  await expect(page.getByLabel('Build name')).toHaveValue('Quiet Build');
  await expect(page.getByRole('heading', { name: 'Incomplete selection' })).toBeVisible();
  expect(reviewCount).toBeGreaterThan(0);
  await page.getByRole('button', { name: 'Confirm and add system to cart' }).click();
  await page.getByRole('button', { name: 'Retry the previous transfer' }).click();
  await expect(page.getByRole('link', { name: 'System added. View cart' })).toBeVisible();
  expect(transferKeys).toHaveLength(2);
  expect(transferKeys[0]).toBeTruthy();
  expect(transferKeys[0]).toBe(transferKeys[1]);
  await page.getByLabel('Build name').fill('Quiet Build revised');
  await page.getByRole('button', { name: 'Save build' }).click();
  await expect(page.getByText('Build saved.', { exact: true })).toBeVisible();
  expect(drafts[0].name).toBe('Studio Tower');
  expect(drafts[1].version).toBe(2);
  expect(errors).toEqual([]);
});
