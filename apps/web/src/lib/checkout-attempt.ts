'use client';

import { useSyncExternalStore } from 'react';
import { isUuid } from './content';
type Attempt = { cartId: string; orderId: string; confirmation: string };
const storageKey = 'nivaro-checkout-attempt-v1';
let fallback: string | null = null;

function stored() {
  try { return window.sessionStorage.getItem(storageKey); }
  catch { return fallback; }
}

function subscribe(listener: () => void) {
  window.addEventListener(storageKey, listener);
  return () => window.removeEventListener(storageKey, listener);
}

function write(value: string | null) {
  fallback = value;
  try {
    if (value === null) window.sessionStorage.removeItem(storageKey);
    else window.sessionStorage.setItem(storageKey, value);
  } catch { /* The attempt stays recoverable within the current page session. */ }
  window.dispatchEvent(new Event(storageKey));
}

export function rememberCheckoutAttempt(attempt: Attempt) { write(JSON.stringify(attempt)); }

export function clearCheckoutAttempt(orderId: string) {
  if (parseAttempt(stored())?.orderId === orderId) write(null);
}

function parseAttempt(value: string | null): Attempt | null {
  if (!value) return null;
  try {
    const attempt = JSON.parse(value) as Partial<Attempt> | null;
    if (typeof attempt?.cartId === 'string' && isUuid(attempt.cartId) &&
        typeof attempt.orderId === 'string' && isUuid(attempt.orderId) &&
        typeof attempt.confirmation === 'string' && /^[0-9a-f]{64}$/.test(attempt.confirmation)) return {
      cartId: attempt.cartId, orderId: attempt.orderId, confirmation: attempt.confirmation,
    };
  } catch { /* Ignore malformed session storage. */ }
  return null;
}

export function useCheckoutAttempt() { return parseAttempt(useSyncExternalStore(subscribe, stored, () => null)); }
