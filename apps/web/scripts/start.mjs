import { cpSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import { parseArgs } from 'node:util';

const root = fileURLToPath(new URL('../', import.meta.url));
const { values } = parseArgs({ options: {
  port: { type: 'string' },
  hostname: { type: 'string' },
} });
process.env.PORT = values.port || process.env.PORT || '3000';
process.env.HOSTNAME = values.hostname || '127.0.0.1';
process.env.NODE_ENV = 'production';
for (const directory of ['public', '.next/static']) {
  cpSync(resolve(root, directory), resolve(root, '.next/standalone', directory), { recursive: true });
}
await import(new URL('../.next/standalone/server.js', import.meta.url));
