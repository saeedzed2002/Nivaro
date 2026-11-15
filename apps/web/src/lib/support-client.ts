'use client';

import createClient from 'openapi-fetch';
import type { components, paths } from './api/support-schema';
import { authorized, IdentityError, type Scope } from './identity-client';

export type Conversation = components['schemas']['Conversation'];
export type ConversationStatus = Conversation['status'];
export type SupportMessage = components['schemas']['Message'];
export type SupportHistory = components['schemas']['History'];

const client = createClient<paths>({ credentials: 'same-origin', cache: 'no-store',
  fetch: async request => {
    try { return await fetch(request, { signal: AbortSignal.any([request.signal, AbortSignal.timeout(8000)]) }); }
    catch (error) { if (request.signal.aborted) throw error; throw new IdentityError('support.unavailable'); }
  },
});

function unwrap<T>({ data, error, response }: { data?: T; error?: unknown; response: Response }) {
  if (!response.ok || !data) {
    const detail = error as components['schemas']['ErrorEnvelope'] | undefined;
    throw new IdentityError(detail?.error?.code ?? 'support.unavailable', response.status);
  }
  return data;
}

export const listSupport = (scope: Scope, signal?: AbortSignal, before?: string) => authorized(async () =>
  unwrap(await client.GET(scope === 'admin' ? '/api/v1/admin/support/conversations' : '/api/v1/support/conversations', {
    params: { query: { before } }, signal,
  })), scope);

export const createSupport = (subject: string, client_conversation_id: string) => authorized(async csrf =>
  unwrap(await client.POST('/api/v1/support/conversations', {
    headers: { 'X-CSRF-Token': csrf }, body: { subject, client_conversation_id },
  })));

export const claimSupport = (conversation: Conversation, agent_id: string) => authorized(async csrf =>
  unwrap(await client.PUT('/api/v1/admin/support/conversations/{conversation_id}/assignment', {
    params: { path: { conversation_id: conversation.id } }, headers: { 'X-CSRF-Token': csrf },
    body: { agent_id, expected_version: conversation.version },
  })), 'admin');

export const setSupportStatus = (conversation: Conversation, status: ConversationStatus) => authorized(async csrf =>
  unwrap(await client.PUT('/api/v1/admin/support/conversations/{conversation_id}/status', {
    params: { path: { conversation_id: conversation.id } }, headers: { 'X-CSRF-Token': csrf },
    body: { status, expected_version: conversation.version },
  })), 'admin');

type Frame = { conversation_id: string; schema_version: 1 };
export type SupportFrame =
  | Frame & { type: 'message.created'; payload: SupportMessage }
  | Frame & { type: 'sync.result'; request_id: string; payload: SupportHistory }
  | Frame & { type: 'message.accepted'; request_id: string; client_message_id: string; payload: { message_id: string; sequence: number; created_at: string } }
  | { type: 'error'; schema_version: 1; conversation_id: string | null; request_id: string | null; client_message_id: string | null; payload: { code: string } };

export const isSupportStatus = (value: unknown): value is ConversationStatus =>
  value === 'open' || value === 'waiting' || value === 'closed';
export const isSupportId = (value: unknown): value is string =>
  typeof value === 'string' && /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(value);
const nullableId = (value: unknown) => value === null || isSupportId(value);
const count = (value: unknown): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value >= 0;
const stamp = (value: unknown) => typeof value === 'string' && value.length <= 40 && Number.isFinite(Date.parse(value));
const record = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);

function isMessage(value: unknown, conversation: string) {
  return record(value) && value.conversation_id === conversation && isSupportId(value.id)
    && isSupportId(value.sender_id) && isSupportId(value.client_message_id)
    && (value.sender_kind === 'customer' || value.sender_kind === 'admin')
    && count(value.sequence) && value.sequence > 0 && stamp(value.created_at)
    && typeof value.body === 'string' && value.body.length > 0 && value.body.length <= 8000;
}

function isHistory(payload: Record<string, unknown>, conversation: string) {
  const row = payload.conversation;
  return record(row) && row.id === conversation && typeof row.subject === 'string' && row.subject.length <= 320
    && isSupportStatus(row.status) && nullableId(row.assigned_agent_id) && count(row.version)
    && count(row.last_sequence) && stamp(row.created_at) && (row.closed_at === null || stamp(row.closed_at))
    && typeof payload.has_more === 'boolean' && Array.isArray(payload.messages) && payload.messages.length <= 10
    && payload.messages.every(message => isMessage(message, conversation));
}

export function decodeSupportFrame(raw: unknown): SupportFrame | null {
  if (typeof raw !== 'string' || raw.length > 280_000) return null;
  let frame: unknown;
  try { frame = JSON.parse(raw); } catch { return null; }
  if (!record(frame) || frame.schema_version !== 1 || !record(frame.payload)) return null;
  const { type, conversation_id, request_id, client_message_id, payload } = frame;
  if (type === 'error') return nullableId(conversation_id) && nullableId(request_id) && nullableId(client_message_id)
    && typeof payload.code === 'string' && payload.code.length <= 100 ? frame as SupportFrame : null;
  if (!isSupportId(conversation_id)) return null;
  if (type === 'message.created') return isMessage(payload, conversation_id) ? frame as SupportFrame : null;
  if (!isSupportId(request_id)) return null;
  if (type === 'sync.result') return isHistory(payload, conversation_id) ? frame as SupportFrame : null;
  if (type === 'message.accepted') return isSupportId(client_message_id) && isSupportId(payload.message_id)
    && count(payload.sequence) && payload.sequence > 0 && stamp(payload.created_at) ? frame as SupportFrame : null;
  return null;
}
