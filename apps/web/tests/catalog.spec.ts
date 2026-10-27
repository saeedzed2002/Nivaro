import { test, expect } from '@playwright/test';

test('comparison shows differences and independent missing prices',async({page})=>{
  await page.goto('/en/compare');
  await expect(page.locator('.comparison-table')).toBeVisible();
  await expect(page.locator('.comparison-table')).toContainText('Unknown');
  await page.getByLabel('Differences only').check();
  await expect(page.locator('.comparison-table tbody')).toContainText('TDP');
  await expect(page.locator('.comparison-table tbody')).not.toContainText('Threads');
  await page.getByRole('combobox',{name:'Sales market'}).selectOption('international');
  await expect(page.locator('.comparison-table')).toBeVisible();
  await page.getByLabel('Comparison category').selectOption('keyboard');
  await expect(page.locator('.comparison-table')).toHaveCount(0);
  await expect(page.getByRole('main')).toContainText('Select two different variants');
});

test('builder evaluates real selections and invalidates stale results on changes',async({page})=>{
  await page.goto('/en/build');
  await page.getByRole('combobox',{name:'Sales market'}).selectOption('ir');
  await page.getByLabel('Processor',{exact:true}).selectOption({label:'AMD Ryzen 7 9800X3D · tray'});
  await expect(page.locator('.partial-total')).toContainText('113,390,000');
  await page.getByRole('button',{name:'Check compatibility'}).click();
  await expect(page.locator('.evaluation-status')).toHaveText('Incomplete selection');
  await page.getByLabel('Processor',{exact:true}).selectOption({label:'AMD Ryzen 7 9700X · boxed'});
  await expect(page.locator('.evaluation-status')).toHaveCount(0);
  await expect(page.locator('.build-warning')).toContainText('no price');
  await page.getByRole('button',{name:'Check compatibility'}).click();
  await expect(page.locator('.evaluation-status')).toHaveText('Incomplete selection');
  await expect(page.locator('.evaluation-result')).toContainText('Previous evidence was stale');
  await page.getByRole('combobox',{name:'Sales market'}).selectOption('international');
  await expect(page.locator('.evaluation-status')).toHaveCount(0);
});

test('failed evaluation preserves selections and offers retry',async({page})=>{
  await page.goto('/en/build');
  await page.getByLabel('Processor',{exact:true}).selectOption({label:'AMD Ryzen 7 9700X · boxed'});
  await page.route('**/api/v1/catalog/build-evaluations',route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:{code:'catalog.unavailable',message:'Unavailable',details:[],request_id:'test'}})}));
  await page.getByRole('button',{name:'Check compatibility'}).click();
  await expect(page.getByRole('main').getByRole('alert')).toContainText('selections are preserved');
  await expect(page.getByLabel('Processor',{exact:true})).not.toHaveValue('');
  await page.unroute('**/api/v1/catalog/build-evaluations');
  await page.getByRole('button',{name:'Check compatibility'}).click();
  await expect(page.locator('.evaluation-status')).toHaveText('Incomplete selection');
});
