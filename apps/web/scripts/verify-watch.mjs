import { readFile, writeFile } from 'node:fs/promises';
import { chromium, expect } from '@playwright/test';

// Run against Compose development mode with `docker compose watch` already active.
const source = new URL('../src/components/footer.tsx', import.meta.url);
const original = await readFile(source, 'utf8');
const originalText = 'Made for a more considered build';
const marker = 'Nivaro live sync verified';
if (!original.includes(originalText) || original.includes(marker)) {
  throw new Error('Footer source differs from the expected reversible probe.');
}
const browser = await chromium.launch(process.env.CHROMIUM_EXECUTABLE
  ? { executablePath: process.env.CHROMIUM_EXECUTABLE } : {});
const page = await browser.newPage();
let changed = false;
try {
  await page.goto(`${process.env.TEST_BASE_URL || 'http://127.0.0.1:8080'}/en`);
  await expect(page.getByText(originalText, { exact: true })).toBeVisible();
  // A normal navigation clears this flag; successful Fast Refresh retains it.
  await page.evaluate(() => { window.nivaroWatchProbe = 'same-document'; });
  await writeFile(source, original.replace(originalText, marker));
  changed = true;
  await expect(page.getByText(marker, { exact: true })).toBeVisible({ timeout: 30_000 });
  expect(await page.evaluate(() => window.nivaroWatchProbe)).toBe('same-document');
  console.log('PASS: host edit reached the existing browser document through Compose Watch.');
} finally {
  try {
    if (changed) {
      const current = await readFile(source, 'utf8');
      // Restore only our marker; preserve any concurrent edits by the owner.
      if (current.includes(marker)) await writeFile(source, current.replace(marker, originalText));
      await expect(page.getByText(originalText, { exact: true })).toBeVisible({ timeout: 30_000 });
      expect(await readFile(source, 'utf8')).toBe(original);
      console.log('PASS: original footer restored and reflected live.');
    }
  } finally {
    await browser.close();
  }
}
