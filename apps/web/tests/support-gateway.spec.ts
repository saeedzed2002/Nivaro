import { expect, test } from '@playwright/test';

const project = process.env.NIVARO_SUPPORT_QA_PROJECT ?? '';
const password = process.env.NIVARO_SUPPORT_QA_PASSWORD;
test.skip(!/^nivaro-support-qa-[a-f0-9]{8}$/.test(project) || !password, 'Requires the disposable Support stack');

test('a customer and a restricted support agent resolve an unanswered conversation', async ({ browser, baseURL }) => {
  test.setTimeout(75_000);
  const customerContext = await browser.newContext({ baseURL, viewport: { width: 390, height: 844 }, reducedMotion: 'reduce' });
  const staffContext = await browser.newContext({ baseURL, viewport: { width: 1440, height: 1000 } });
  try {
    const customer = await customerContext.newPage();
    const staff = await staffContext.newPage();
    const errors: string[] = [];
    customer.on('pageerror', error => errors.push(error.message));
    staff.on('pageerror', error => errors.push(error.message));

    await customer.goto('/en/login');
    await customer.getByLabel('Mobile number', { exact: true }).fill('+12025550102');
    await customer.getByRole('button', { name: 'Get sign-in code' }).press('Enter');
    const code = customer.getByTestId('development-code');
    await expect(code).toBeVisible();
    await customer.getByLabel('Sign-in code', { exact: true }).fill((await code.innerText()).trim());
    await customer.getByRole('button', { name: 'Verify and sign in' }).press('Enter');
    await expect(customer).toHaveURL(/\/en\/account$/);

    await customer.goto('/en/account/support');
    await customer.getByRole('button', { name: 'New conversation' }).press('Enter');
    const subject = 'Delivery question';
    await customer.getByLabel('Subject').fill(subject);
    await customer.getByRole('button', { name: 'Create conversation' }).press('Enter');
    const customerLog = customer.getByRole('log', { name: 'Conversation messages' });
    const question = 'Can I change my delivery window?';
    await customer.getByRole('textbox', { name: 'Message', exact: true }).fill(question);
    await customer.getByRole('button', { name: 'Send', exact: true }).press('Enter');
    await expect(customerLog.getByText(question, { exact: true })).toHaveCount(1);
    expect(await customer.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);

    await staff.goto('/en/admin/login');
    await staff.getByLabel('Email').fill('first@example.com');
    await staff.getByLabel('Password', { exact: true }).fill(password!);
    await staff.getByRole('button', { name: 'Sign in as administrator' }).press('Enter');
    await expect(staff.getByRole('link', { name: 'Support inbox', exact: true })).toBeVisible();
    await staff.goto('/en/admin');
    await expect(staff.getByRole('heading', { name: 'Staff overview' })).toBeVisible();
    await expect(staff.getByRole('heading', { name: 'Sales summary' })).toHaveCount(0);
    await expect(staff.getByRole('link', { name: 'Payments', exact: true })).toHaveCount(0);
    await staff.getByRole('link', { name: 'Open unanswered inbox' }).press('Enter');
    await expect(staff).toHaveURL(/\/en\/admin\/support\?unanswered=1$/);
    const unanswered = staff.getByRole('checkbox', { name: 'Unanswered only' });
    await expect(unanswered).toBeChecked();
    await staff.getByRole('button', { name: 'Claim conversation' }).press('Enter');
    const staffLog = staff.getByRole('log', { name: 'Conversation messages' });
    await expect(staffLog.getByText(question, { exact: true })).toBeVisible();
    expect(await staff.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await staff.setViewportSize({ width: 768, height: 900 });
    expect(await staff.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const answer = 'Your current delivery window is still available.';
    await staff.getByRole('textbox', { name: 'Reply', exact: true }).fill(answer);
    await staff.getByRole('button', { name: 'Send', exact: true }).press('Enter');
    await expect(customerLog.getByText(answer, { exact: true })).toHaveCount(1);
    await customer.reload();
    await expect(customerLog.getByText(answer, { exact: true })).toHaveCount(1);

    await staff.getByRole('button', { name: 'Refresh', exact: true }).press('Enter');
    const conversation = staff.getByRole('button', { name: new RegExp(subject) });
    await expect(conversation).toHaveCount(0);
    await unanswered.uncheck();
    await conversation.press('Enter');
    const status = staff.getByRole('combobox', { name: 'Conversation status' });
    await status.selectOption('closed');
    await expect(customer.getByRole('textbox', { name: 'Message', exact: true })).toBeDisabled({ timeout: 25_000 });
    await staff.goto('/en/admin/payments');
    await expect(staff.getByText('This account does not have permission to view payments.')).toBeVisible();
    expect(errors).toEqual([]);
  } finally {
    await Promise.all([customerContext.close(), staffContext.close()]);
  }
});
