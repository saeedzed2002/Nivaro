import { readFile, writeFile } from 'node:fs/promises';
import openapiTS, { astToString } from 'openapi-typescript';

const source = new URL('../../../contracts/openapi/catalog.json', import.meta.url);
const destination = new URL('../src/lib/api/catalog-schema.ts', import.meta.url);
const header = '/** Generated from contracts/openapi/catalog.json. Run pnpm contracts:generate. */\n';
const result = header + astToString(await openapiTS(source));
if (process.argv.includes('--check')) {
  const existing = await readFile(destination, 'utf8');
  if (existing.replaceAll('\r\n', '\n') !== result) {
    throw new Error('Catalog types are stale. Run pnpm contracts:generate.');
  }
  console.log('Catalog TypeScript contract matches OpenAPI.');
} else {
  await writeFile(destination, result);
  console.log('Generated catalog TypeScript contract.');
}
