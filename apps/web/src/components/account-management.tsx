'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { changeAccountRole, changeAccountStatus, getAccount, listAccountAudit, listAccounts, type Account, type AccountKind, type AuditEvent, type RoleChange } from '@/lib/accounts-client';
import { checkoutTime } from '@/lib/checkout-copy';
import { text, type Locale } from '@/lib/content';
import { IdentityError } from '@/lib/identity-client';
import { useAdminSession } from './admin-shared';
import { ConfirmAction } from './identity-shared';

const roleCopy = {
  customer: ['مشتری', 'Customer'],
  support_agent: ['کارشناس پشتیبانی', 'Support agent'],
  catalog_manager: ['مدیر کاتالوگ', 'Catalog manager'],
  sales_manager: ['مدیر فروش', 'Sales manager'],
  super_admin: ['مدیر ارشد', 'Super administrator'],
} as const;
const staffRoles: RoleChange[] = ['support_agent', 'catalog_manager', 'sales_manager', 'super_admin'];

function roleLabel(locale: Locale, role: Account['role']) {
  return text(locale, roleCopy[role][0], roleCopy[role][1]);
}

function statusLabel(locale: Locale, disabled: boolean) {
  return disabled ? text(locale, 'غیرفعال', 'Disabled') : text(locale, 'فعال', 'Active');
}

function accessLost(error: unknown) {
  return error instanceof IdentityError && (error.status === 401 || error.status === 403);
}

function AccountProblem({ locale, error, retry }: { locale: Locale; error: unknown; retry?: () => void }) {
  if (!error) return null;
  const code = error instanceof IdentityError ? error.code : '';
  const descriptions: Record<string, [string, string]> = {
    'account.last_super_admin': ['دست‌کم یک مدیر ارشد باید فعال بماند.', 'At least one super administrator must remain active.'],
    'account.version_conflict': ['حساب تغییر کرده است. اطلاعات تازه را بررسی کنید و تصمیم را دوباره بگیرید.', 'This account changed. Reload it and review the latest details before making the change.'],
    'account.not_found': ['حساب دیگر در دسترس نیست. فهرست را تازه کنید.', 'This account is no longer available. Refresh the list.'],
    'account.not_staff': ['این حساب، نقش مدیریتی ندارد.', 'This account has no staff role.'],
  };
  const label = descriptions[code];
  return <div className="accounts-problem">
    <p className="admin-notice error" role="alert">{accessLost(error)
      ? text(locale, 'دسترسی مدیریت حساب‌ها پایان یافته است.', 'Account management access has ended.')
      : label ? text(locale, ...label) : text(locale, 'ارتباط با سرویس هویت برقرار نشد.', 'Identity is unavailable.')}</p>
    {accessLost(error) ? <Link className="text-link" href={`/${locale}/admin/login`}>{text(locale, 'ورود مدیران', 'Administrator sign-in')}</Link>
      : retry && <button type="button" className="button secondary" onClick={retry}>{text(locale, 'بارگیری دوباره', 'Reload')}</button>}
  </div>;
}

export function AccountManagement({ locale }: { locale: Locale }) {
  const actor = useAdminSession();
  return actor ? <AccountsWorkspace key={actor.profile.id} locale={locale} actorId={actor.profile.id}/> : null;
}

function AccountsWorkspace({ locale, actorId }: { locale: Locale; actorId: string }) {
  const router = useRouter();
  const cache = useQueryClient();
  const [kind, setKind] = useState<AccountKind | undefined>();
  const [disabled, setDisabled] = useState<boolean | undefined>();
  const [selected, setSelected] = useState<string>();
  const [saved, setSaved] = useState(false);
  const [ended, setEnded] = useState(false);
  const prefix = ['managed-accounts', actorId] as const;
  const list = useInfiniteQuery({
    queryKey: [...prefix, 'list', kind, disabled],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam, signal }) => listAccounts(kind, disabled, pageParam, signal),
    getNextPageParam: page => page.next_before ?? undefined,
    retry: false, gcTime: 0, enabled: !ended,
  });
  const rows = [...new Map(list.data?.pages.flatMap(page => page.accounts.map(row => [row.id, row] as const))).values()];
  const id = rows.find(row => row.id === selected)?.id ?? rows[0]?.id;
  const detailKey = [...prefix, 'detail', id] as const;
  const detail = useQuery({
    queryKey: detailKey, queryFn: ({ signal }) => getAccount(id!, signal),
    enabled: !!id && !ended && !accessLost(list.error),
    retry: false, gcTime: 0, refetchOnWindowFocus: false,
  });

  function permissionEnded() {
    setEnded(true);
    router.replace(`/${locale}/admin/login`);
  }

  function onSaved(account: Account) {
    if (account.id === actorId && (account.disabled || account.role !== 'super_admin')) {
      permissionEnded();
      return;
    }
    cache.setQueryData([...prefix, 'detail', account.id], account);
    setSaved(true);
    void cache.invalidateQueries({ queryKey: [...prefix, 'list'] });
    void cache.invalidateQueries({ queryKey: [...prefix, 'audit', account.id] });
  }

  function resetSelection() {
    setSelected(undefined);
    setSaved(false);
  }

  const heading = text(locale, 'حساب‌ها و ممیزی', 'Accounts & audit');
  const authError = [list.error, detail.error].find(accessLost);
  if (ended || authError) return <>
    <header className="admin-heading"><h1>{heading}</h1></header>
    <AccountProblem locale={locale} error={authError ?? new IdentityError('session.invalid', 401)}/>
  </>;
  return <>
    <header className="admin-heading"><h1>{heading}</h1></header>
    <div className="admin-filter-row accounts-filters">
      <label>{text(locale, 'نوع حساب', 'Account type')}
        <select value={kind ?? ''} onChange={event => {
          const next = event.target.value;
          setKind(next === 'staff' || next === 'customer' ? next : undefined);
          resetSelection();
        }}>
          <option value="">{text(locale, 'همهٔ حساب‌ها', 'All accounts')}</option>
          <option value="staff">{text(locale, 'کارکنان', 'Staff')}</option>
          <option value="customer">{text(locale, 'حساب‌های مشتری', 'Customers')}</option>
        </select>
      </label>
      <label>{text(locale, 'وضعیت', 'Status')}
        <select value={disabled === undefined ? '' : disabled ? 'disabled' : 'active'} onChange={event => {
          const next = event.target.value;
          setDisabled(next === '' ? undefined : next === 'disabled');
          resetSelection();
        }}>
          <option value="">{text(locale, 'همهٔ وضعیت‌ها', 'All statuses')}</option>
          <option value="active">{statusLabel(locale, false)}</option>
          <option value="disabled">{statusLabel(locale, true)}</option>
        </select>
      </label>
    </div>
    <div className="accounts-layout">
      <section className="admin-panel accounts-list" aria-labelledby="accounts-list-title">
        <h2 id="accounts-list-title">{text(locale, 'حساب‌ها', 'Accounts')}</h2>
        {list.isPending && <p role="status">{text(locale, 'در حال دریافت حساب‌ها…', 'Loading accounts…')}</p>}
        <AccountProblem locale={locale} error={list.error} retry={() => void list.refetch()}/>
        {!list.isPending && !list.isError && !rows.length && <p>{text(locale, 'حسابی با این فیلترها پیدا نشد.', 'No accounts match these filters.')}</p>}
        {!!rows.length && <table className="admin-table accounts-table">
          <thead><tr><th scope="col">{text(locale, 'حساب', 'Account')}</th><th scope="col">{text(locale, 'نقش', 'Role')}</th><th scope="col">{text(locale, 'وضعیت', 'Status')}</th></tr></thead>
          <tbody>{rows.map(account => <tr key={account.id} data-selected={account.id === id}>
            <td><button type="button" className="accounts-select" aria-pressed={account.id === id}
              onClick={() => { setSelected(account.id); setSaved(false); }}>
              <strong><bdi>{account.name || account.staff_email || account.phone}</bdi></strong>
              {account.name && <small><bdi>{account.staff_email || account.phone}</bdi></small>}
            </button></td>
            <td>{roleLabel(locale, account.role)}</td>
            <td><span className={`admin-badge ${account.disabled ? '' : 'published'}`}>{statusLabel(locale, account.disabled)}</span></td>
          </tr>)}</tbody>
        </table>}
        {list.hasNextPage && <button type="button" className="button secondary accounts-more" disabled={list.isFetching}
          onClick={() => void list.fetchNextPage()}>{text(locale, 'حساب‌های بیشتر', 'More accounts')}</button>}
      </section>
      {id && <section className="admin-panel accounts-detail" aria-labelledby="accounts-detail-title">
        <h2 id="accounts-detail-title">{text(locale, 'خلاصهٔ حساب', 'Account summary')}</h2>
        {detail.isPending && <p role="status">{text(locale, 'در حال دریافت حساب…', 'Loading account…')}</p>}
        <AccountProblem locale={locale} error={detail.error} retry={() => void detail.refetch()}/>
        {detail.data && !detail.isError && <>
          <dl className="accounts-summary">
            {detail.data.name && <><dt>{text(locale, 'نام', 'Name')}</dt><dd><bdi>{detail.data.name}</bdi></dd></>}
            <dt>{text(locale, 'شمارهٔ همراه', 'Mobile number')}</dt><dd><bdi>{detail.data.phone}</bdi></dd>
            {detail.data.staff_email && <><dt>{text(locale, 'ایمیل کارکنان', 'Staff email')}</dt><dd><bdi>{detail.data.staff_email}</bdi></dd></>}
            <dt>{text(locale, 'نقش فعلی', 'Current role')}</dt><dd>{roleLabel(locale, detail.data.role)}</dd>
            <dt>{text(locale, 'وضعیت فعلی', 'Current status')}</dt><dd>{statusLabel(locale, detail.data.disabled)}</dd>
          </dl>
          {saved && <p className="admin-notice success" role="status">{text(locale, 'تغییر حساب ثبت شد.', 'Account change saved.')}</p>}
          <AccountActions key={`${id}:${detail.data.version}`} locale={locale} account={detail.data}
            onStart={() => setSaved(false)} onSaved={onSaved} onAccessLost={permissionEnded}
            reload={async () => (await detail.refetch()).isSuccess}/>
          <AccountAudit key={id} locale={locale} actorId={actorId} target={id}/>
        </>}
      </section>}
    </div>
  </>;
}

function AccountActions({ locale, account, onStart, onSaved, onAccessLost, reload }: {
  locale: Locale; account: Account; onStart: () => void; onSaved: (account: Account) => void;
  onAccessLost: () => void; reload: () => Promise<boolean>;
}) {
  const [role, setRole] = useState<Account['role']>(account.role);
  const change = useMutation({
    mutationFn: (action: { role: RoleChange } | { disabled: boolean }) =>
      'role' in action ? changeAccountRole(account, action.role) : changeAccountStatus(account, action.disabled),
    onMutate: onStart,
    onSuccess: onSaved,
    onError: error => { if (accessLost(error)) onAccessLost(); },
  });
  const conflict = change.error instanceof IdentityError && change.error.code === 'account.version_conflict';
  const busy = change.isPending || conflict;
  const statusAction = account.disabled ? text(locale, 'فعال‌کردن حساب', 'Enable account') : text(locale, 'غیرفعال‌کردن حساب', 'Disable account');
  async function apply(action: { role: RoleChange } | { disabled: boolean }) {
    try { await change.mutateAsync(action); } catch { /* The mutation error is shown in the panel. */ }
  }
  async function refreshAfterConflict() {
    if (await reload()) change.reset();
  }
  return <div className="accounts-actions">
    {account.role !== 'customer' && <section>
      <h3>{text(locale, 'نقش کارکنان', 'Staff role')}</h3>
      <label className="field">{text(locale, 'نقش جدید', 'New role')}
        <select value={role} disabled={busy} onChange={event => {
          const next = staffRoles.find(value => value === event.target.value);
          if (next) { setRole(next); change.reset(); }
        }}>
          {staffRoles.map(value => <option key={value} value={value}>{roleLabel(locale, value)}</option>)}
        </select>
      </label>
      <ConfirmAction locale={locale} appearance="primary" label={text(locale, 'ذخیرهٔ نقش', 'Save role')}
        title={text(locale, 'نقش تغییر کند؟', 'Change staff role?')} busy={busy || role === account.role}
        onConfirm={() => role === 'customer' ? Promise.resolve() : apply({ role })}>
        {text(locale, 'نشست‌های مدیریتی فعال این حساب بسته می‌شوند.', 'Active staff sessions for this account will end.')}
      </ConfirmAction>
    </section>}
    <section>
      <h3>{text(locale, 'وضعیت حساب', 'Account status')}</h3>
      <ConfirmAction locale={locale} label={statusAction}
        title={account.disabled ? text(locale, 'حساب فعال شود؟', 'Enable this account?') : text(locale, 'حساب غیرفعال شود؟', 'Disable this account?')}
        appearance={account.disabled ? 'primary' : 'danger'} busy={busy}
        onConfirm={() => apply({ disabled: !account.disabled })}>
        {account.disabled ? text(locale, 'حساب با ورود تازه دوباره قابل استفاده می‌شود.', 'The account can sign in again.')
          : text(locale, 'نشست‌های مشتری و کارکنان این حساب بسته می‌شوند.', 'All customer and staff sessions for this account will end.')}
      </ConfirmAction>
    </section>
    <AccountProblem locale={locale} error={change.error} retry={conflict ? () => void refreshAfterConflict() : undefined}/>
  </div>;
}

const auditCopy: Record<string, [string, string]> = {
  'admin.role_changed': ['تغییر نقش', 'Role changed'],
  'account.enabled': ['فعال‌شدن حساب', 'Account enabled'],
  'account.disabled': ['غیرفعال‌شدن حساب', 'Account disabled'],
  'admin.login': ['ورود مدیر', 'Staff sign-in'],
  'customer.login': ['ورود مشتری', 'Customer sign-in'],
  'admin.bootstrap': ['ایجاد مدیر ارشد اولیه', 'Initial super administrator created'],
  'admin.password_changed': ['تغییر گذرواژهٔ مدیر', 'Staff password changed'],
};

function auditValues(locale: Locale, event: AuditEvent) {
  if (event.previous_role && event.new_role) return [roleLabel(locale, event.previous_role), roleLabel(locale, event.new_role)];
  if (event.previous_disabled !== null && event.new_disabled !== null) return [statusLabel(locale, event.previous_disabled), statusLabel(locale, event.new_disabled)];
  return null;
}

function AccountAudit({ locale, actorId, target }: { locale: Locale; actorId: string; target: string }) {
  const trail = useInfiniteQuery({
    queryKey: ['managed-accounts', actorId, 'audit', target],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam, signal }) => listAccountAudit(target, pageParam, signal),
    getNextPageParam: page => page.next_before ?? undefined,
    retry: false, gcTime: 0,
  });
  const events = [...new Map(trail.data?.pages.flatMap(page => page.events.map(event => [event.id, event] as const))).values()];
  return <section className="accounts-audit" aria-labelledby="account-audit-title">
    <h3 id="account-audit-title">{text(locale, 'سابقهٔ ممیزی', 'Audit history')}</h3>
    {trail.isPending && <p role="status">{text(locale, 'در حال دریافت سابقه…', 'Loading audit history…')}</p>}
    <AccountProblem locale={locale} error={trail.error} retry={() => void trail.refetch()}/>
    {!trail.isPending && !trail.isError && !events.length && <p>{text(locale, 'رویدادی برای این حساب ثبت نشده است.', 'No audit events for this account.')}</p>}
    {!accessLost(trail.error) && <ol>{events.map(event => {
      const label = auditCopy[event.event];
      const values = auditValues(locale, event);
      return <li key={event.id}>
        <div><strong><bdi>{label ? text(locale, ...label) : event.event}</bdi></strong>
          <time dateTime={event.created_at}>{checkoutTime(event.created_at, locale)}</time></div>
        {values && <dl className="accounts-audit-values">
          <div><dt>{text(locale, 'قبل', 'Before')}</dt><dd>{values[0]}</dd></div>
          <div><dt>{text(locale, 'بعد', 'After')}</dt><dd>{values[1]}</dd></div>
        </dl>}
        {event.actor_id && <small>{text(locale, 'شناسهٔ اقدام‌کننده', 'Actor ID')} <bdi>{event.actor_id}</bdi></small>}
      </li>;
    })}</ol>}
    {trail.hasNextPage && <button type="button" className="button secondary" disabled={trail.isFetching || accessLost(trail.error)}
      onClick={() => void trail.fetchNextPage()}>{text(locale, 'رویدادهای بیشتر', 'More audit events')}</button>}
  </section>;
}
