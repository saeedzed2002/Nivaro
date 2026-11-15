'use client';

import Link from 'next/link';
import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Inbox, MessageSquare, Plus, RefreshCw, Send } from 'lucide-react';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { checkoutTime } from '@/lib/checkout-copy';
import { text, type Locale } from '@/lib/content';
import { IdentityError, type IdentitySession, type Scope } from '@/lib/identity-client';
import { claimSupport, createSupport, isSupportStatus, listSupport, setSupportStatus, type Conversation, type ConversationStatus } from '@/lib/support-client';
import { startSupportThread, type ThreadState } from '@/lib/support-thread';
import { useAdminSession } from './admin-shared';

const statuses = ['open', 'waiting', 'closed'] as const;

function statusLabel(locale: Locale, status: ConversationStatus) {
  const labels = { open: ['باز', 'Open'], waiting: ['در انتظار', 'Waiting'], closed: ['بسته', 'Closed'] } as const;
  return text(locale, labels[status][0], labels[status][1]);
}

function SupportProblem({ locale, error }: { locale: Locale; error: unknown }) {
  if (!error) return null;
  const code = error instanceof IdentityError ? error.code : error;
  const labels: Record<string, [string, string]> = {
    'support.not_found': ['این گفت‌وگو دیگر در دسترس شما نیست. فهرست را تازه کنید.', 'This conversation is no longer available to you. Refresh the list.'],
    'support.version_conflict': ['گفت‌وگو تغییر کرده است. اطلاعات تازه را بررسی و دوباره اقدام کنید.', 'The conversation changed. Review the current information and try again.'],
    'support.closed': ['گفت‌وگو بسته شده است.', 'The conversation is closed.'],
    'support.rate_limited': ['کمی صبر کنید و دوباره بفرستید.', 'Wait a moment and try sending again.'],
    'request.too_large': ['حجم پیام زیاد است. متن را کوتاه‌تر کنید.', 'The message is too large. Shorten the text.'],
    'request.invalid': ['متن و اندازهٔ پیام را بررسی کنید.', 'Check the message text and length.'],
    'auth.required': ['نشست شما پایان یافته است. دوباره وارد شوید.', 'Your session ended. Sign in again.'],
    'auth.forbidden': ['حساب شما اجازهٔ این عملیات را ندارد.', 'Your account cannot perform this action.'],
  };
  const label = typeof code === 'string' ? labels[code] : undefined;
  return <p className="support-error" role="alert">{label ? text(locale, ...label)
    : text(locale, 'ارتباط با پشتیبانی برقرار نشد. دوباره تلاش کنید.', 'Support is unavailable. Try again.')}</p>;
}

export function SupportInbox({ locale }: { locale: Locale }) {
  const session = useAdminSession();
  return session ? <SupportWorkspace key={session.profile.id} locale={locale} scope="admin" session={session}/> : null;
}

export function CustomerSupport({ locale, session }: { locale: Locale; session: IdentitySession }) {
  return <SupportWorkspace key={session.profile.id} locale={locale} scope="customer" session={session}/>;
}

function SupportWorkspace({ locale, scope, session }: { locale: Locale; scope: Scope; session: IdentitySession }) {
  const [selectedId, setSelectedId] = useState<string>();
  const [filter, setFilter] = useState<ConversationStatus | ''>('');
  const [override, setOverride] = useState<Conversation>();
  const [creating, setCreating] = useState(false);
  const group = useQueryClient();
  const staff = scope === 'admin';
  const userId = session.profile.id;
  const manage = staff && session.permissions.includes('users.manage');
  const queryKey = ['support-conversations', scope, userId] as const;
  const queue = useInfiniteQuery({
    queryKey, initialPageParam: undefined as string | undefined,
    queryFn: ({ signal, pageParam }) => listSupport(scope, signal, pageParam),
    getNextPageParam: page => page.next_before ?? undefined,
    gcTime: 0, retry: false,
  });
  const rows = new Map(queue.data?.pages.flatMap(page => page.conversations.map(row => [row.id, row] as const)));
  const known = override && rows.get(override.id);
  if (override && (!known || override.version >= known.version)) rows.set(override.id, override);
  const visible = [...rows.values()].filter(row => !filter || row.status === filter);
  const selected = visible.find(row => row.id === selectedId) ?? visible[0];
  const assignment = useMutation({
    mutationFn: (row: Conversation) => claimSupport(row, userId),
    onSuccess: updated,
    onError: () => { void refresh(); },
  });

  function updated(row: Conversation) {
    setOverride(row);
    setSelectedId(row.id);
    void group.invalidateQueries({ queryKey });
  }

  async function refresh() {
    const result = await queue.refetch();
    if (result.isSuccess) setOverride(undefined);
  }

  function keepDraft() {
    return !document.querySelector('.support-thread[data-unsaved="true"]')
      || window.confirm(text(locale, 'پیام ارسال‌نشده کنار گذاشته شود؟', 'Leave this conversation and discard the unsent message?'));
  }

  const title = staff ? text(locale, 'صندوق پشتیبانی', 'Support inbox') : text(locale, 'پشتیبانی', 'Support');
  const canRead = selected && (!staff || manage || selected.assigned_agent_id === userId);
  return <>
    <header className="support-heading"><div><h1>{title}</h1>{!staff &&
      <p className="muted">{text(locale, 'با تیم پشتیبانی گفت‌وگو کنید و پاسخ‌ها را همین‌جا دنبال کنید.', 'Talk to support and follow replies here.')}</p>}</div>
      <button type="button" className="button secondary" disabled={queue.isFetching} onClick={() => void refresh()}>
        <RefreshCw size={16}/>{text(locale, 'تازه‌سازی', 'Refresh')}
      </button>
    </header>
    <div className={`support-workspace ${staff ? '' : 'support-customer'}`}>
      <section className="support-queue" aria-labelledby="support-queue-title">
        <div className="support-queue-head"><h2 id="support-queue-title">{staff ? text(locale, 'صف گفت‌وگوها', 'Queue') : text(locale, 'گفت‌وگوهای من', 'My conversations')}</h2>
          {staff && <label className="field">{text(locale, 'وضعیت', 'Status')}
            <select value={filter} onChange={event => {
              if (keepDraft()) setFilter(isSupportStatus(event.target.value) ? event.target.value : '');
            }}>
              <option value="">{text(locale, 'همهٔ وضعیت‌ها', 'All statuses')}</option>
              {statuses.map(status => <option key={status} value={status}>{statusLabel(locale, status)}</option>)}
            </select>
          </label>}
          {!staff && <button type="button" className="button primary"
            onClick={() => { if (creating || keepDraft()) setCreating(true); }}>
            <Plus size={17}/>{text(locale, 'گفت‌وگوی جدید', 'New conversation')}
          </button>}
        </div>
        {queue.isPending && <p className="support-queue-note" role="status">{text(locale, 'در حال دریافت گفت‌وگوها…', 'Loading conversations…')}</p>}
        <SupportProblem locale={locale} error={queue.error}/>
        {!queue.isPending && !queue.isError && !visible.length && <p className="support-queue-note muted">{text(locale, 'گفت‌وگویی در این فهرست نیست.', 'No conversations in this list.')}</p>}
        <ul className="support-rows">{visible.map(row => <li key={row.id}><button type="button"
          aria-pressed={!creating && selected?.id === row.id} onClick={() => {
            if ((creating || selected?.id !== row.id) && keepDraft()) { setCreating(false); setSelectedId(row.id); assignment.reset(); }
          }}>
          <bdi>{row.subject}</bdi>
          <small><span>{statusLabel(locale, row.status)}</span><time dateTime={row.created_at}>{checkoutTime(row.created_at, locale)}</time></small>
          {staff && <small>{!row.assigned_agent_id ? text(locale, 'بدون کارشناس', 'Unassigned')
            : row.assigned_agent_id === userId ? text(locale, 'ارجاع به من', 'Assigned to me') : text(locale, 'ارجاع‌شده', 'Assigned')}</small>}
        </button></li>)}</ul>
        {queue.hasNextPage && <button type="button" className="button secondary support-more" disabled={queue.isFetching}
          onClick={() => void queue.fetchNextPage()}>{text(locale, 'گفت‌وگوهای بیشتر', 'More conversations')}</button>}
      </section>
      {creating ? <NewConversation locale={locale} onCancel={() => setCreating(false)} onSaved={row => { updated(row); setCreating(false); }}/>
        : selected && canRead ? <SupportThread key={selected.id} locale={locale} scope={scope} userId={userId}
        conversation={selected} onUpdated={updated} onRefresh={refresh}/>
        : selected ? <section className="support-placeholder">
          <Inbox size={33}/><h2><bdi>{selected.subject}</bdi></h2>
          <p>{text(locale, 'برای دیدن پیام‌ها و پاسخ دادن، گفت‌وگو را بپذیرید.', 'Claim the conversation to read and reply.')}</p>
          <button type="button" className="button primary" disabled={assignment.isPending}
            onClick={() => assignment.mutate(selected)}>{text(locale, 'پذیرفتن گفت‌وگو', 'Claim conversation')}</button>
          <SupportProblem locale={locale} error={assignment.error}/>
        </section> : <section className="support-placeholder"><MessageSquare size={34}/>
          <h2>{text(locale, 'گفت‌وگوهای پشتیبانی', 'Support conversations')}</h2>
          <p>{text(locale, 'یک گفت‌وگو را از فهرست انتخاب کنید.', 'Select a conversation from the list.')}</p>
        </section>}
    </div>
  </>;
}

function NewConversation({ locale, onCancel, onSaved }: { locale: Locale; onCancel: () => void; onSaved: (row: Conversation) => void }) {
  const [subject, setSubject] = useState('');
  const previous = useRef<{ subject: string; id: string } | null>(null);
  const mutation = useMutation({
    mutationFn: ({ subject, id }: { subject: string; id: string }) => createSupport(subject, id),
    onSuccess: onSaved,
  });
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = subject.trim();
    if (!value || mutation.isPending) return;
    if (previous.current?.subject !== value) previous.current = { subject: value, id: crypto.randomUUID() };
    mutation.mutate(previous.current);
  }
  return <form className="support-thread support-new" onSubmit={submit}>
    <h2>{text(locale, 'گفت‌وگوی جدید', 'New conversation')}</h2>
    <label className="field">{text(locale, 'موضوع', 'Subject')}
      <input dir="auto" autoFocus required maxLength={160} value={subject} onChange={event => setSubject(event.target.value)}/>
    </label>
    <SupportProblem locale={locale} error={mutation.error}/>
    <div className="support-buttons">
      <button type="submit" className="button primary" disabled={mutation.isPending || !subject.trim()}>{text(locale, 'ایجاد گفت‌وگو', 'Create conversation')}</button>
      <button type="button" className="button secondary" disabled={mutation.isPending} onClick={onCancel}>{text(locale, 'انصراف', 'Cancel')}</button>
    </div>
  </form>;
}

function SupportThread({ locale, scope, userId, conversation, onUpdated, onRefresh }: {
  locale: Locale; scope: Scope; userId: string; conversation: Conversation;
  onUpdated: (row: Conversation) => void; onRefresh: () => Promise<void>;
}) {
  const [initial] = useState(conversation);
  const [state, setState] = useState<ThreadState>({
    conversation, messages: [], connection: 'connecting', pending: null,
    receipts: { own_sequence: 0, peer_sequence: 0 },
  });
  const [draft, setDraft] = useState('');
  const [attempt, setAttempt] = useState(0);
  const control = useRef<ReturnType<typeof startSupportThread> | null>(null);
  const log = useRef<HTMLDivElement>(null);
  const pinned = useRef(true);
  const row = conversation.version > state.conversation.version ? conversation : state.conversation;
  const change = useMutation({
    mutationFn: (status: ConversationStatus) => setSupportStatus(row, status),
    onSuccess: onUpdated,
    onError: () => { void onRefresh(); },
  });

  useEffect(() => {
    const thread = startSupportThread(initial, scope, userId, setState);
    control.current = thread;
    return () => { control.current = null; thread.close(); };
  }, [initial, scope, userId, attempt]);
  useEffect(() => {
    const element = log.current;
    if (element && pinned.current) element.scrollTop = element.scrollHeight;
  }, [state.messages]);
  useEffect(() => {
    const viewport = log.current;
    if (!viewport || !state.messages.length) return;
    const visible = new Map<Element, number>();
    function markVisible() {
      if (document.visibilityState !== 'visible') return;
      const sequence = Math.max(0, ...visible.values());
      if (sequence) control.current?.markRead(sequence);
    }
    const observer = new IntersectionObserver(entries => {
      for (const entry of entries) {
        const sequence = Number((entry.target as HTMLElement).dataset.supportSequence);
        if (entry.isIntersecting && entry.intersectionRect.height > 0) visible.set(entry.target, sequence);
        else visible.delete(entry.target);
      }
      markVisible();
    });
    for (const message of viewport.querySelectorAll('[data-support-sequence]')) observer.observe(message);
    document.addEventListener('visibilitychange', markVisible);
    return () => {
      observer.disconnect();
      document.removeEventListener('visibilitychange', markVisible);
    };
  }, [state.messages]);

  const allowed = state.connection === 'online' && row.status !== 'closed';
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (allowed && control.current?.submit(draft)) {
      pinned.current = true;
      setDraft('');
    }
  }

  const title = scope === 'admin' ? text(locale, 'پاسخ', 'Reply') : text(locale, 'پیام', 'Message');
  const connection = {
    connecting: text(locale, 'در حال اتصال…', 'Connecting…'),
    online: text(locale, 'متصل', 'Connected'),
    offline: text(locale, 'آفلاین، در حال اتصال دوباره…', 'Offline, reconnecting…'),
    denied: text(locale, 'دسترسی ندارید', 'Access unavailable'),
  }[state.connection];
  const blocked = state.connection === 'denied';
  return <section className="support-thread" aria-labelledby="support-thread-title" data-unsaved={!!(draft.trim() || state.pending)}>
    <header className="support-thread-head">
      <div><h2 id="support-thread-title"><bdi>{row.subject}</bdi></h2><div className="support-thread-meta">
        <span>{statusLabel(locale, row.status)}</span>
        <span className={`support-connection ${state.connection}`} role="status">{connection}</span>
      </div></div>
      {scope === 'admin' && !blocked && <label className="field">{text(locale, 'وضعیت گفت‌وگو', 'Conversation status')}
        <select value={row.status} disabled={change.isPending || state.connection !== 'online'}
          onChange={event => { if (isSupportStatus(event.target.value)) change.mutate(event.target.value); }}>
          {statuses.map(status => <option key={status} value={status}>{statusLabel(locale, status)}</option>)}
        </select>
      </label>}
    </header>
    <SupportProblem locale={locale} error={state.error || change.error}/>
    <div ref={log} className="support-log" role="log" aria-label={text(locale, 'پیام‌های گفت‌وگو', 'Conversation messages')} tabIndex={0}
      onScroll={({ currentTarget: area }) => { pinned.current = area.scrollHeight - area.scrollTop - area.clientHeight < 55; }}>
      {state.connection === 'online' && !state.messages.length && <p className="muted">{text(locale, 'هنوز پیامی ثبت نشده است.', 'No messages yet.')}</p>}
      {state.messages.map(message => {
        const mine = message.sender_id === userId && message.sender_kind === scope;
        return <article className={mine ? 'support-message mine' : 'support-message'} key={message.id}
          data-support-sequence={message.sequence}>
          <p dir="auto">{message.body}</p><small>
            {mine ? text(locale, 'شما', 'You') : message.sender_kind === 'admin' ? text(locale, 'پشتیبانی', 'Support') : text(locale, 'مشتری', 'Customer')}
            <time dateTime={message.created_at}>{checkoutTime(message.created_at, locale)}</time>
            {mine && message.sequence <= state.receipts.peer_sequence && <span>{text(locale, 'خوانده شد', 'Read')}</span>}
          </small>
        </article>;
      })}
    </div>
    {blocked ? <div className="support-compose">{state.error === 'auth.required' &&
      <Link className="text-link" href={scope === 'admin' ? `/${locale}/admin/login` : `/${locale}/login?next=support`}>{text(locale, 'ورود دوباره', 'Sign in again')}</Link>}
      <button type="button" className="button secondary" onClick={() => { void onRefresh(); setAttempt(value => value + 1); }}>{text(locale, 'بررسی دوباره', 'Check again')}</button></div>
      : <form className="support-compose" onSubmit={submit}>
        {state.pending ? <div className="support-pending" role="status">
          <p dir="auto">{state.pending.body}</p>
          {!state.pending.error && <small>{text(locale, 'در انتظار تأیید ثبت پیام…', 'Waiting for confirmation…')}</small>}
          <SupportProblem locale={locale} error={state.pending.error}/>
          {state.pending.error && <div className="support-buttons">
            <button type="button" className="button secondary" disabled={!allowed} onClick={() => control.current?.retry()}>{text(locale, 'ارسال دوباره', 'Retry send')}</button>
            <button type="button" className="button secondary" onClick={() => { if (state.pending) setDraft(state.pending.body); control.current?.discard(); }}>{text(locale, 'ویرایش پیام', 'Edit message')}</button>
          </div>}
        </div> : <label className="field">{title}<textarea dir="auto" value={draft} onChange={event => setDraft(event.target.value)}
          maxLength={4000} rows={2} disabled={row.status === 'closed'}/></label>}
        {row.status === 'closed' && <p className="muted">{text(locale, 'گفت‌وگو بسته است.', 'This conversation is closed.')}</p>}
        <button type="submit" className="button primary" disabled={!allowed || !!state.pending || !draft.trim()}><Send size={16}/>{text(locale, 'ارسال', 'Send')}</button>
      </form>}
  </section>;
}
