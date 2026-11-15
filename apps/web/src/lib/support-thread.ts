'use client';

import { IdentityError, readSession, type Scope } from './identity-client';
import { decodeSupportFrame, type Conversation, type ReadState, type SupportMessage } from './support-client';

type Pending = { id: string; body: string; error?: string };
export type ThreadState = {
  connection: 'connecting' | 'online' | 'offline' | 'denied';
  messages: SupportMessage[];
  conversation: Conversation;
  pending: Pending | null;
  receipts: ReadState;
  error?: string;
};

export function startSupportThread(
  conversation: Conversation, scope: Scope, userId: string, update: (state: ThreadState) => void,
) {
  const state: ThreadState = {
    conversation, connection: 'connecting', messages: [], pending: null,
    receipts: { own_sequence: 0, peer_sequence: 0 },
  };
  const bySequence = new Map<number, SupportMessage>();
  let cursor = 0;
  let highest = 0;
  let socket: WebSocket | undefined;
  let disposed = false;
  let attempts = 0;
  let reconnect: ReturnType<typeof setTimeout> | undefined;
  let timeout: ReturnType<typeof setTimeout> | undefined;
  let deliveryTimeout: ReturnType<typeof setTimeout> | undefined;
  let readTimeout: ReturnType<typeof setTimeout> | undefined;
  let readRequest: string | undefined;
  let wantedRead = 0;
  let request: string | undefined;
  let sent: string | undefined;
  let needsSubscription = true;

  function emit() { if (!disposed) update({ ...state }); }
  function merge(incoming: SupportMessage[]) {
    let changed = false;
    for (const message of incoming) {
      const previous = bySequence.get(message.sequence);
      if (previous?.id !== message.id || previous.body !== message.body) {
        bySequence.set(message.sequence, message);
        highest = Math.max(highest, message.sequence);
        changed = true;
      }
      if (message.sender_kind === scope && message.sender_id === userId && message.client_message_id === state.pending?.id) {
        state.pending = null;
        clearTimeout(deliveryTimeout);
      }
    }
    while (bySequence.has(cursor + 1)) cursor++;
    if (changed) state.messages = [...bySequence.values()].sort((a, b) => a.sequence - b.sequence);
  }

  function transmit(frame: object) {
    if (socket?.readyState !== WebSocket.OPEN) return false;
    const encoded = JSON.stringify({ ...frame, schema_version: 1, conversation_id: conversation.id });
    if (new TextEncoder().encode(encoded).length > 16384) return false;
    socket.send(encoded);
    return true;
  }

  function sync() {
    if (request || socket?.readyState !== WebSocket.OPEN) return;
    const id = crypto.randomUUID();
    if (!transmit({ type: needsSubscription ? 'conversation.subscribe' : 'sync.request', request_id: id, payload: { after: cursor } })) return;
    request = id;
    clearTimeout(timeout);
    timeout = setTimeout(() => socket?.close(4000), 8000);
  }

  function sendPending() {
    const item = state.pending;
    if (needsSubscription || !item || item.error || sent === item.id) return;
    if (transmit({ type: 'message.send', request_id: crypto.randomUUID(), client_message_id: item.id, payload: { body: item.body } })) {
      sent = item.id;
      deliveryTimeout = setTimeout(() => socket?.close(4000), 8000);
    } else if (socket?.readyState === WebSocket.OPEN) {
      state.pending = { ...item, error: 'request.too_large' };
      emit();
    }
  }

  function sendRead() {
    const sequence = Math.min(cursor, wantedRead);
    if (needsSubscription || readRequest || sequence <= state.receipts.own_sequence) return;
    const id = crypto.randomUUID();
    if (!transmit({ type: 'message.read', request_id: id, payload: { sequence } })) return;
    readRequest = id;
    readTimeout = setTimeout(() => {
      readRequest = undefined;
      sendRead();
    }, 8_000);
  }

  function settleRead() {
    clearTimeout(readTimeout);
    readRequest = undefined;
  }

  function deny(code: string) {
    state.connection = 'denied';
    state.error = code;
    state.messages = [];
    bySequence.clear();
    settleRead();
    socket?.close();
    emit();
  }

  async function open(validateSession: boolean) {
    if (disposed || state.connection === 'denied') return;
    if (validateSession) {
      try {
        const session = await readSession(scope);
        if (disposed) return;
        if (session.profile.id !== userId) { deny('auth.required'); return; }
      } catch (error) {
        if (disposed) return;
        if (error instanceof IdentityError && (error.status === 401 || error.status === 403)) deny(error.code);
        else schedule(true);
        return;
      }
    }
    const endpoint = new URL('/ws/support', location.origin);
    endpoint.protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const connection = new WebSocket(endpoint, scope === 'admin' ? 'nivaro.support.staff.v1' : 'nivaro.support.customer.v1');
    socket = connection;
    timeout = setTimeout(() => connection.close(), 8000);
    connection.onopen = () => {
      if (disposed || socket !== connection) return;
      clearTimeout(timeout);
      needsSubscription = true;
      sync();
    };
    connection.onmessage = ({ data }) => {
      if (disposed || socket !== connection || state.connection === 'denied') return;
      const frame = decodeSupportFrame(data);
      if (!frame || frame.conversation_id !== conversation.id) return;
      switch (frame.type) {
        case 'sync.result': {
          if (frame.request_id !== request) return;
          clearTimeout(timeout);
          request = undefined;
          needsSubscription = false;
          attempts = 0;
          state.connection = 'online';
          state.error = undefined;
          state.conversation = frame.payload.conversation;
          merge(frame.payload.messages);
          state.receipts = frame.payload.receipts;
          sendPending();
          sendRead();
          if (frame.payload.has_more || cursor < highest) sync();
          break;
        }
        case 'message.created':
          merge([frame.payload]);
          sendRead();
          if (cursor < highest) sync();
          break;
        case 'message.read':
          state.receipts = frame.payload;
          if (frame.request_id === readRequest) settleRead();
          sendRead();
          break;
        case 'message.accepted': {
          const item = state.pending;
          if (item?.id !== frame.client_message_id) return;
          merge([{ id: frame.payload.message_id, client_message_id: item.id,
            conversation_id: conversation.id, sender_id: userId, sender_kind: scope,
            sequence: frame.payload.sequence, created_at: frame.payload.created_at, body: item.body }]);
          if (cursor < highest) sync();
          break;
        }
        case 'error':
          if (frame.payload.code === 'support.not_found') { deny(frame.payload.code); return; }
          if (frame.payload.code === 'auth.required') return;
          if (frame.request_id === readRequest) {
            settleRead();
            if (frame.payload.code !== 'support.unavailable') wantedRead = state.receipts.own_sequence;
          }
          if (frame.client_message_id && frame.client_message_id === state.pending?.id) {
            clearTimeout(deliveryTimeout);
            sent = undefined;
            state.pending = { ...state.pending, error: frame.payload.code };
          }
          if (frame.request_id === request) {
            request = undefined;
            state.error = frame.payload.code;
            clearTimeout(timeout);
            if (needsSubscription) connection.close(4000);
          }
          break;
      }
      emit();
    };
    connection.onclose = ({ code }) => {
      if (disposed || socket !== connection || state.connection === 'denied') return;
      clearTimeout(timeout);
      clearTimeout(deliveryTimeout);
      settleRead();
      request = undefined;
      sent = undefined;
      if (code === 4403) { deny('auth.forbidden'); return; }
      state.connection = 'offline';
      emit();
      schedule(code === 4401 || code === 1006);
    };
  }

  function schedule(validateSession: boolean) {
    const windowMs = Math.min(30_000, 500 * 2 ** Math.min(attempts++, 6));
    reconnect = setTimeout(() => void open(validateSession), windowMs * (0.5 + Math.random() / 2));
  }

  const periodic = setInterval(sync, 20_000);
  emit();
  void open(false);
  return {
    markRead(sequence: number) {
      wantedRead = Math.max(wantedRead, sequence);
      sendRead();
    },
    submit(body: string) {
      if (state.pending || state.connection !== 'online' || !body.trim()) return false;
      state.pending = { id: crypto.randomUUID(), body: body.trim() };
      sendPending();
      emit();
      return true;
    },
    retry() {
      if (!state.pending?.error || state.connection !== 'online') return;
      state.pending = { ...state.pending, error: undefined };
      sendPending();
      emit();
    },
    discard() {
      if (!state.pending?.error) return;
      state.pending = null;
      emit();
    },
    close() {
      disposed = true;
      clearInterval(periodic);
      clearTimeout(reconnect);
      clearTimeout(timeout);
      clearTimeout(deliveryTimeout);
      settleRead();
      socket?.close();
    },
  };
}
