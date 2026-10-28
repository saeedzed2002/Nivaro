import { spawnSync } from 'node:child_process';
import { mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';
import { chromium, expect } from '@playwright/test';

// Deliberately opt-in: changes one known local research record and stops catalog briefly.
if (process.env.NIVARO_DEMO_RUNTIME_CHECK !== '1') throw new Error('Set NIVARO_DEMO_RUNTIME_CHECK=1 for the local demo only.');
const root = fileURLToPath(new URL('../../../', import.meta.url));
const base = 'http://127.0.0.1:8080';
const slug = 'amd-ryzen-7-9700x';
const marker = `Nivaro database visibility probe ${Date.now()}`;
const docker = (...args) => {
  const result = spawnSync('docker', ['compose', ...args], { cwd: root, encoding: 'utf8', timeout: 45_000 });
  if (result.error || result.status !== 0) throw new Error(`Docker check failed: ${result.error?.message ?? result.stderr}`);
  return result.stdout;
};
const changeName = (expected, name) => docker('exec', '-T', 'catalog', 'python', '-c', `
import sys
from sqlalchemy import create_engine, update
from nivaro_catalog.settings import Settings
from nivaro_catalog.infrastructure.models import ProductRow
with create_engine(Settings().database_url()).begin() as db:
    result = db.execute(update(ProductRow).where(ProductRow.slug == sys.argv[1], ProductRow.name == sys.argv[2]).values(name=sys.argv[3]))
    if result.rowcount != 1:
        raise SystemExit('Probe record changed concurrently; refusing to overwrite it.')
`, slug, expected, name);
const browser = await chromium.launch(process.env.CHROMIUM_EXECUTABLE ? { executablePath: process.env.CHROMIUM_EXECUTABLE } : {});
const page = await browser.newPage();
const original = await fetch(`${base}/api/v1/catalog/products/${slug}`).then(r => {
  if (!r.ok) throw new Error('Catalog not ready before probe');
  return r.json();
});
let changed = false, stopped = false;
try {
  changeName(original.name, marker);
  changed = true;
  await page.goto(`${base}/en/products/${slug}`);
  await expect(page.locator('h1')).toHaveText(marker);
  await page.goto(`${base}/en/products?category=cpu`);
  await expect(page.locator('.product-card h3').filter({ hasText: marker })).toBeVisible();
  console.log('PASS: committed database change reached detail and collection without web rebuild.');
  changeName(marker, original.name);
  changed = false;
  stopped = true;
  docker('stop', 'catalog');
  for (const path of ['/en', '/en/products', `/en/products/${slug}`, '/en/compare', '/en/build']) {
    await page.goto(`${base}${path}`);
    await expect(page.getByRole('heading', { name: 'Catalog temporarily unavailable' })).toBeVisible();
    await expect(page.locator('.product-card')).toHaveCount(0);
  }
  if (process.env.QA_OUTPUT_DIR) {
    await mkdir(process.env.QA_OUTPUT_DIR, { recursive: true });
    await page.screenshot({ path: join(process.env.QA_OUTPUT_DIR, 'catalog-outage.png'), fullPage: true });
  }
  console.log('PASS: actual catalog outage renders explicit unavailable states on all five templates.');
} finally {
  try {
    if (stopped) {
      docker('start', 'catalog');
      await expect.poll(async () => fetch(`${base}/api/v1/catalog/products/${slug}`).then(r => r.status).catch(() => 0), { timeout: 30_000 }).toBe(200);
    }
    if (changed) changeName(marker, original.name);
    await page.goto(`${base}/en/products/${slug}`);
    await expect(page.locator('h1')).toHaveText(original.name);
    console.log('PASS: original record restored and catalog recovered in storefront.');
  } finally {
    await browser.close();
  }
}
