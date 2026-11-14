import assert from 'node:assert/strict';

const origin = 'http://127.0.0.1:8082';
const cookies = new Map();

async function call(path, { method = 'GET', body, headers = {}, status = 200 } = {}) {
  const response = await fetch(`${origin}${path}`, {
    method,
    signal: AbortSignal.timeout(12000),
    headers: {
      Origin: origin,
      Cookie: [...cookies].map(([key, value]) => `${key}=${value}`).join('; '),
      ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
      ...headers,
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  assert.equal(response.status, status, `${method} ${path} returned ${response.status}`);
  for (const header of response.headers.getSetCookie()) {
    const pair = header.split(';', 1)[0];
    const split = pair.indexOf('=');
    const key = pair.slice(0, split);
    const value = pair.slice(split + 1);
    if (value && value !== '""' && !/;\s*max-age=0(?:;|$)/i.test(header)) cookies.set(key, value);
    else cookies.delete(key);
  }
  if (status === 204 || path.startsWith('/internal/')) return;
  return response.json();
}

await call('/internal/v1/cart/customer-check', { method: 'POST', status: 404 });
await call('/api/v1/cart', { status: 401 });
const guest = await call('/api/v1/cart/session', { method: 'POST', headers: { 'X-CSRF-Request': '1' } });
const guestCart = await call('/api/v1/cart?market=ir');
assert.equal(guestCart.owner_scope, 'guest');
const guestBuild = await call('/api/v1/builds', {
  method: 'POST', status: 201, headers: { 'X-CSRF-Token': guest.csrf_token },
  body: { name: 'Gateway test draft', market: 'ir', selections: [] },
});
const result = await call(`/api/v1/builds/${guestBuild.id}/review`);
assert.equal(result.blocker, 'build.empty');
assert.equal(result.evaluation.status, 'incomplete');

const phone = '+12025550100';
const challenge = await call('/api/v1/auth/otp/request', { method: 'POST', body: { phone } });
const customer = await call('/api/v1/auth/otp/verify', {
  method: 'POST',
  body: { phone, challenge_id: challenge.challenge_id, code: challenge.development_code },
});
const accountCart = await call('/api/v1/cart?market=ir');
assert.equal(accountCart.owner_scope, 'customer');
assert.notEqual(accountCart.id, guestCart.id);
await call(`/api/v1/builds/${guestBuild.id}`, { status: 404 });
await call('/api/v1/auth/logout', {
  method: 'POST', body: { all_devices: false }, headers: { 'X-CSRF-Token': customer.csrf_token },
});
assert.equal((await call('/api/v1/cart?market=ir')).id, guestCart.id);
assert.equal((await call(`/api/v1/builds/${guestBuild.id}`)).id, guestBuild.id);
console.log('Cart, identity, catalog evaluation and ownership verified through the real gateway.');
