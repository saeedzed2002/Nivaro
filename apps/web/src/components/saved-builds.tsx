'use client';

import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Boxes, Copy, Scale, Trash2, Wrench } from 'lucide-react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { useState } from 'react';
import { cartErrorCopy, compareBuilds, deleteBuild, duplicateBuild, listBuilds, type SavedBuild } from '@/lib/cart-client';
import { text, type Locale, type Market } from '@/lib/content';
import { buildsKey } from './cart-query';
import { usePreferences } from './preferences';

const builderUrl = (locale: Locale, id: string) => `/${locale}/build?draft=${encodeURIComponent(id)}`;
const slotLabels: Record<string, [string, string]> = {
  cpu: ['پردازنده', 'Processor'], motherboard: ['مادربرد', 'Motherboard'], memory: ['رم', 'Memory'], storage: ['ذخیره‌سازی', 'Storage'],
  case: ['کیس', 'Case'], psu: ['پاور', 'Power supply'], cooler: ['خنک‌کننده', 'Cooling'], gpu: ['کارت گرافیک', 'Graphics card'],
  monitor: ['مانیتور', 'Monitor'], keyboard: ['کیبورد', 'Keyboard'], mouse: ['ماوس', 'Mouse'], audio: ['صدا', 'Audio'], chair: ['صندلی', 'Chair'], desk: ['میز', 'Desk'], accessory: ['لوازم جانبی', 'Accessory'],
};

export function SavedBuilds({ locale }: { locale: Locale }) {
  const { market } = usePreferences();
  return <SavedBuildList key={market} locale={locale} market={market} />;
}

function SavedBuildList({ locale, market }: { locale: Locale; market: Market }) {
  const client = useQueryClient();
  const queryKey = [...buildsKey(market), 'list'];
  const list = useInfiniteQuery({ queryKey, initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam, signal }) => listBuilds(market, signal, pageParam),
    getNextPageParam: last => last.length === 30 ? last.at(-1)?.id : undefined });
  const drafts = list.data?.pages.flat() ?? [];
  const [selected, setSelected] = useState<string[]>([]);
  const [action, setAction] = useState<{ kind: 'copy' | 'delete'; build: Pick<SavedBuild, 'id' | 'version' | 'name'> }>();
  const [name, setName] = useState('');
  const ids = selected.filter(id => drafts.some(draft => draft.id === id));
  const mutation = useMutation({ mutationFn: async ({ kind, build }: NonNullable<typeof action>) => {
    if (kind === 'copy') return duplicateBuild(build, name.trim());
    await deleteBuild(build);
  }, onSuccess: () => setAction(undefined), onSettled: () => client.invalidateQueries({ queryKey: buildsKey(market) }) });
  return <>
    <div className="saved-heading"><h1>{text(locale, 'پیش‌نویس‌های اسمبل', 'Saved builds')}</h1>
      <Link className="button primary" href={`/${locale}/build`}><Wrench size={18} />{text(locale, 'بازکردن میز اسمبل', 'Open builder')}</Link></div>
    {list.isPending && <p role="status">{text(locale, 'در حال بارگیری…', 'Loading builds…')}</p>}
    {list.error && <div role="alert"><p>{cartErrorCopy(list.error, locale)}</p><button type="button" className="button secondary" onClick={() => void list.refetch()}>{text(locale, 'تلاش دوباره', 'Try again')}</button></div>}
    {list.isSuccess && drafts.length === 0 && <p className="workspace-panel">{text(locale, 'در این بازار هنوز پیش‌نویسی ذخیره نکرده‌ای.', 'You have no saved builds in this market.')}</p>}
    <div className="saved-list">{drafts.map(build => <article className="saved-card workspace-panel" key={build.id}>
      <label className="saved-select"><input type="checkbox" checked={ids.includes(build.id)} disabled={ids.length >= 2 && !ids.includes(build.id)} onChange={event => setSelected(event.target.checked ? [...ids, build.id] : ids.filter(id => id !== build.id))} aria-label={`${text(locale, 'انتخاب برای مقایسه', 'Select for comparison')}: ${build.name}`} /></label>
      <Boxes className="saved-icon" aria-hidden="true" /><div className="saved-title"><h2><bdi>{build.name}</bdi></h2><p>{build.mode === 'parts_only' ? text(locale, 'فقط قطعات', 'Parts only') : text(locale, 'پیکربندی سیستم کامل', 'Complete configuration')}</p></div>
      <div className="saved-actions"><Link className="button primary" href={builderUrl(locale, build.id)}>{text(locale, 'بازکردن', 'Open')}</Link>
        <button type="button" className="button secondary" onClick={() => { mutation.reset(); setName(`${build.name.slice(0, 88)} ${text(locale, 'کپی', 'copy')}`); setAction({ kind: 'copy', build }); }}><Copy size={16}/>{text(locale, 'کپی', 'Duplicate')}</button>
        <button type="button" className="icon-button" aria-label={`${text(locale, 'حذف', 'Delete')}: ${build.name}`} onClick={() => { mutation.reset(); setAction({ kind: 'delete', build }); }}><Trash2 size={18} /></button></div>
    </article>)}</div>
    {action && <form className="workspace-panel saved-confirm" onSubmit={event => { event.preventDefault(); mutation.mutate(action); }}>
      {action.kind === 'copy' ? <label className="field"><span>{text(locale, 'نام نسخهٔ کپی', 'Copy name')}</span><input required value={name} maxLength={100} onChange={event => setName(event.target.value)} /></label>
        : <p>{text(locale, 'پیش‌نویس حذف شود؟', 'Delete this draft?')} <bdi>{action.build.name}</bdi></p>}
      {mutation.error && <p role="alert">{cartErrorCopy(mutation.error, locale)}</p>}
      <div className="detail-actions"><button className="button primary" disabled={mutation.isPending || (action.kind === 'copy' && !name.trim())}>{action.kind === 'copy' ? text(locale, 'ساخت نسخهٔ کپی', 'Create copy') : text(locale, 'تأیید حذف', 'Confirm deletion')}</button>
        <button type="button" className="button secondary" disabled={mutation.isPending} onClick={() => setAction(undefined)}>{text(locale, 'انصراف', 'Cancel')}</button></div>
    </form>}
    <div className="detail-actions saved-footer">
      {ids.length === 2 ? <Link className="button primary" href={`/${locale}/build/compare?left=${encodeURIComponent(ids[0])}&right=${encodeURIComponent(ids[1])}`}><Scale size={18} />{text(locale, 'مقایسهٔ سیستم‌های انتخاب‌شده', 'Compare selected builds')}</Link>
        : drafts.length >= 2 && <p>{text(locale, 'برای مقایسه دو سیستم انتخاب کن.', 'Select two builds to compare.')}</p>}
      {list.hasNextPage && <button type="button" className="button secondary" disabled={list.isFetchingNextPage} onClick={() => void list.fetchNextPage()}>{text(locale, 'موارد بیشتر', 'Load more')}</button>}
    </div>
  </>;
}

function money(value: string | null | undefined, market: Market, locale: Locale) {
  if (value == null) return '—';
  const amount = BigInt(value);
  if (market === 'ir') return `${new Intl.NumberFormat(locale).format(amount / BigInt(10))} ${text(locale, 'تومان', 'tomans')}`;
  const dollars = BigInt(100);
  const cents = new Intl.NumberFormat(locale, { minimumIntegerDigits: 2, useGrouping: false }).format(amount % dollars);
  return new Intl.NumberFormat(locale, { style: 'currency', currency: 'USD' }).formatToParts(amount / dollars).map(part => part.type === 'fraction' ? cents : part.value).join('');
}

export function SavedBuildComparison({ locale }: { locale: Locale }) {
  const { market } = usePreferences();
  const params = useSearchParams();
  const left = params.get('left');
  const right = params.get('right');
  const eligible = Boolean(left && right && left !== right);
  const result = useQuery({ queryKey: [...buildsKey(market), 'compare', left, right], enabled: eligible,
    queryFn: ({ signal }) => compareBuilds(left!, right!, signal) });
  const data = result.data?.market === market ? result.data : undefined;
  const status = { compatible: ['سازگار', 'Compatible'], incompatible: ['ناسازگار', 'Incompatible'], incomplete: ['ناقص', 'Incomplete'], needs_review: ['نیاز به بررسی', 'Needs review'] } as const;
  return <>
    <div className="saved-heading"><h1>{text(locale, 'مقایسهٔ سیستم‌ها', 'Compare systems')}</h1><Link className="button secondary" href={`/${locale}/build/saved`}>{text(locale, 'پیش‌نویس‌ها', 'Saved builds')}</Link></div>
    {eligible && result.isPending && <p role="status">{text(locale, 'در حال بررسی سیستم‌ها…', 'Checking both configurations…')}</p>}
    {(!eligible || result.isError || (result.data && !data)) && <p role="alert" className="workspace-panel">{text(locale, 'دو پیش‌نویس از همین بازار را انتخاب کن.', 'Choose two saved builds in the current market.')}</p>}
    {data && <>
      <div className="saved-columns">{[data.left, data.right].map(column => <section className="workspace-panel" key={column.build.id}>
        <h2><Link href={builderUrl(locale, column.build.id)}><bdi>{column.build.name}</bdi></Link></h2>
        <dl><div><dt>{text(locale, 'قطعات اصلی', 'Core components')}</dt><dd><bdi>{money(column.known_components_minor, market, locale)}</bdi></dd></div>
          <div><dt>{text(locale, 'تجهیزات جانبی', 'Peripherals')}</dt><dd><bdi>{money(column.known_peripherals_minor, market, locale)}</bdi></dd></div>
          <div><dt>{text(locale, 'سازگاری', 'Compatibility')}</dt><dd>{column.evaluation ? status[column.evaluation.status][locale === 'fa' ? 0 : 1] : '—'}</dd></div></dl>
        {column.unpriced_slots.length > 0 && <p className="muted">{text(locale, 'جمع قیمت جزئی است.', 'The price subtotal is incomplete.')}</p>}
        {column.evaluation?.findings.length ? <details><summary>{text(locale, 'نتیجهٔ بررسی', 'Compatibility findings')}</summary><ul>{column.evaluation.findings.map((finding, index) => <li key={`${finding.code}-${index}`}>{finding.message[locale]}</li>)}</ul></details> : null}
      </section>)}</div>
      {data.price_status !== 'ready' && <p role="status">{text(locale, 'قیمت‌های فعلی در دسترس نیستند.', 'Current prices are unavailable.')}</p>}
      <table className="saved-table"><thead><tr><th scope="col">{text(locale, 'قطعه', 'Component')}</th><th scope="col"><bdi>{data.left.build.name}</bdi></th><th scope="col"><bdi>{data.right.build.name}</bdi></th></tr></thead>
        <tbody>{data.slots.map(slot => <tr key={slot.slot_key} className={slot.different ? 'saved-difference' : undefined}>
          <th scope="row">{slotLabels[slot.slot_key.split(':')[0]]?.[locale === 'fa' ? 0 : 1] ?? slot.slot_key}{slot.slot_key.includes(':') && <small> · <bdi>{slot.slot_key.split(':')[1]}</bdi></small>}{slot.different && <span className="sr-only">{text(locale, 'متفاوت', 'Different')}</span>}</th>
          {[slot.left, slot.right].map((part, index) => <td key={index}>{part ? <><strong><bdi>{part.summary?.name ?? text(locale, 'نامشخص', 'Unknown')}</bdi></strong><small>× <bdi>{new Intl.NumberFormat(locale).format(part.quantity ?? 1)}</bdi> · <bdi>{money(part.summary?.offer?.amount_minor?.toString(), market, locale)}</bdi></small></> : '—'}</td>)}
        </tr>)}</tbody></table>
    </>}
  </>;
}
