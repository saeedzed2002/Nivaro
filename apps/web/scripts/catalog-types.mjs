import { readFile, writeFile } from 'node:fs/promises';
import openapiTS, { astToString } from 'openapi-typescript';

for (const service of ['catalog', 'identity']) {
const source = new URL(`../../../contracts/openapi/${service}.json`, import.meta.url);
const destination = new URL(`../src/lib/api/${service}-schema.ts`, import.meta.url);
const header = `/** Generated from contracts/openapi/${service}.json. Run pnpm contracts:generate. */\n`;
const result = header + astToString(await openapiTS(source));
if (process.argv.includes('--check')) {
  const existing = await readFile(destination, 'utf8');
  if (existing.replaceAll('\r\n', '\n') !== result) {
    throw new Error(`${service} types are stale. Run pnpm contracts:generate.`);
  }
  console.log(`${service} TypeScript contract matches OpenAPI.`);
} else {
  await writeFile(destination, result);
  console.log(`Generated ${service} TypeScript contract.`);
}
}
