import { test, expect, type BrowserContext } from '@playwright/test';
import { randomBytes } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import path from 'node:path';

const project = process.env.NIVARO_IDENTITY_QA_PROJECT || '';
test.describe.configure({ mode: 'serial' });
const base = process.env.TEST_BASE_URL || 'http://127.0.0.1:8080';
test.skip(!/^nivaro-p03-qa-[a-z0-9]+$/.test(project), 'Use the isolated identity browser helper; never reset real accounts or limits.');
let seedCookies: Awaited<ReturnType<BrowserContext['cookies']>>;
const adminPassword = randomBytes(24).toString('base64url');
function operator(code: string, input = '') {
  if (!/^nivaro-p03-qa-[a-z0-9]+$/.test(project)) throw new Error('Disposable test project required');
  const result = spawnSync('docker', ['compose', '-p', project, '-f', 'compose.yaml', '-f', 'compose.identity-qa.yaml', 'exec', '-T', 'identity', 'python', '-c', code], { cwd: path.resolve('../..'), input, encoding: 'utf8', timeout: 20_000 });
  if (result.status !== 0) throw new Error('Disposable identity operator check failed');
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
test('admin credentials are separate; customer login never grants staff access', async ({ page, context }) => {
  await context.addCookies(seedCookies);
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
  await page.reload();
  await expect(page.getByText('Support replies', { exact: true })).toBeVisible();
  await expect(page.getByText('Refunds', { exact: true })).toHaveCount(0);
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
