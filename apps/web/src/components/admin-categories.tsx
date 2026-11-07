'use client';

import { useEffect, useRef, useState, type FormEvent } from 'react';
import { CheckCircle2, FolderTree, Pencil, Plus, RefreshCw, Save, Search } from 'lucide-react';
import { listManagedCategories, saveManagedCategory, type CategoryContent, type ManagedCategory } from '@/lib/admin-catalog-client';
import { text, type Locale } from '@/lib/content';
import { CatalogNotice } from './admin-shared';

const empty: CategoryContent = { slug: '', name: { fa: '', en: '' }, parent_id: null };
const content = (row: ManagedCategory): CategoryContent => ({ slug: row.slug, name: row.name, parent_id: row.parent_id || null });

export function AdminCategories({ locale }: { locale: Locale }) {
  const [rows, setRows] = useState<ManagedCategory[]>([]);
  const [selected, setSelected] = useState<ManagedCategory | null>(null);
  const [draft, setDraft] = useState<CategoryContent>(empty);
  const [opened, setOpened] = useState(false);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);
  const [comparison, setComparison] = useState<ManagedCategory | null>(null);
  const editor = useRef<HTMLHeadingElement>(null);
  const dirty = opened && JSON.stringify(draft) !== JSON.stringify(selected ? content(selected) : empty);
  useEffect(() => {
    let alive = true;
    listManagedCategories().then(value => { if (alive) setRows(value); }).catch(e => { if (alive) setLoadError(e); }).finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, []);
  useEffect(() => {
    if (!dirty) return;
    const before = (event: BeforeUnloadEvent) => { event.preventDefault(); };
    const navigation = (event: MouseEvent) => {
      const anchor = (event.target as Element).closest('a');
      if (!anchor || event.defaultPrevented || anchor.target === '_blank' || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      if (!window.confirm(text(locale, 'تغییرات ذخیره‌نشده کنار گذاشته شوند؟', 'Leave and discard unsaved changes?'))) { event.preventDefault(); event.stopPropagation(); }
    };
    window.addEventListener('beforeunload', before); document.addEventListener('click', navigation, true);
    return () => { window.removeEventListener('beforeunload', before); document.removeEventListener('click', navigation, true); };
  }, [dirty, locale]);
  async function refresh() {
    setLoading(true);
    try { setRows(await listManagedCategories()); setLoadError(null); } catch (e) { setLoadError(e); } finally { setLoading(false); }
  }
  function adopt(row: ManagedCategory | null) { setSelected(row); setDraft(row ? content(row) : empty); setOpened(true); setError(null); setComparison(null); }
  function choose(row: ManagedCategory | null) {
    if (busy || (dirty && !window.confirm(text(locale, 'ویرایش فعلی کنار گذاشته شود؟', 'Discard the current category draft?')))) return;
    adopt(row); setSaved(false); requestAnimationFrame(() => editor.current?.focus());
  }
  function update(value: Partial<CategoryContent>) { setDraft(current => ({ ...current, ...value })); setSaved(false); }
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(null); setSaved(false);
    try {
      const row = await saveManagedCategory(draft, selected || undefined);
      setRows(current => [...current.filter(item => item.id !== row.id), row]); adopt(row); setSaved(true);
      await refresh();
    } catch (e) { setError(e); } finally { setBusy(false); }
  }
  async function compare() {
    if (!selected) return;
    setBusy(true);
    try {
      const current = await listManagedCategories();
      setRows(current); setComparison(current.find(row => row.id === selected.id) || null);
    } catch (e) { setError(e); } finally { setBusy(false); }
  }
  const roots = rows.filter(row => !row.parent_id).sort((a, b) => a.name[locale].localeCompare(b.name[locale], locale));
  const ordered = roots.flatMap(root => [root, ...rows.filter(row => row.parent_id === root.id).sort((a, b) => a.name[locale].localeCompare(b.name[locale], locale))]);
  const normalized = query.trim().toLocaleLowerCase();
  const visible = ordered.filter(row => `${row.name.fa} ${row.name.en} ${row.slug}`.toLocaleLowerCase().includes(normalized));
  const number = (value: number) => new Intl.NumberFormat(locale === 'fa' ? 'fa-IR' : 'en-US').format(value);
  return <div data-unsaved={dirty}>
    <div className="admin-heading"><div><p className="eyebrow">{text(locale, 'ساختار کاتالوگ', 'CATALOG STRUCTURE')}</p><h1>{text(locale, 'دسته‌بندی‌ها', 'Categories')}</h1><p>{text(locale, 'ساختار دو سطحی محصولات فروشگاه', 'A two-level structure for store products')}</p></div><button className="button primary" disabled={busy || loading} onClick={() => choose(null)}><Plus size={18}/>{text(locale, 'افزودن دسته', 'Add category')}</button></div>
    <CatalogNotice error={loadError} locale={locale}/>{!!loadError && <button className="button secondary" disabled={loading} onClick={() => void refresh()}><RefreshCw size={17}/>{text(locale, 'تلاش دوباره', 'Try again')}</button>}
    <div className={`admin-category-layout ${opened ? 'with-editor' : ''}`}>
      <section className="admin-category-list"><label className="admin-search"><Search size={18}/><span className="sr-only">{text(locale, 'جست‌وجوی دسته‌بندی', 'Search categories')}</span><input value={query} onChange={e => setQuery(e.target.value)} maxLength={120} placeholder={text(locale, 'نام یا نامک دسته…', 'Category name or slug…')}/></label>
        <p className="admin-hint" role="status">{loading ? text(locale, 'در حال دریافت دسته‌ها…', 'Loading categories…') : text(locale, `${number(visible.length)} دسته‌بندی`, `${number(visible.length)} categories`)}</p>
        {!loading && !visible.length && <div className="admin-panel admin-empty"><FolderTree size={30}/><h2>{text(locale, 'دسته‌ای پیدا نشد', 'No categories found')}</h2><p>{text(locale, 'عبارت جست‌وجو را تغییر دهید یا دسته‌ای اضافه کنید.', 'Change your search or add a category.')}</p></div>}
        {!loading && visible.length > 0 && <div className="admin-table-wrap"><table className="admin-table admin-category-table"><caption className="sr-only">{text(locale, 'ساختار دسته‌بندی‌ها', 'Category hierarchy')}</caption><thead><tr>{[text(locale, 'نام و نامک', 'Name and slug'), text(locale, 'دستهٔ والد', 'Parent'), text(locale, 'محصولات مستقیم', 'Direct products'), text(locale, 'عملیات', 'Actions')].map(label => <th scope="col" key={label}>{label}</th>)}</tr></thead><tbody>{visible.map(row => <tr key={row.id} data-selected={selected?.id === row.id}>
          <td><div className={`admin-category-name ${row.parent_id ? 'child' : ''}`}><FolderTree size={18}/><div><strong>{row.name[locale]}</strong><small dir="ltr">{row.slug}</small></div></div></td>
          <td data-label={text(locale, 'والد', 'Parent')}>{rows.find(item => item.id === row.parent_id)?.name[locale] || text(locale, 'اصلی', 'Top level')}</td>
          <td data-label={text(locale, 'محصولات', 'Products')}>{number(row.product_count)}</td>
          <td><button type="button" className="admin-edit-link" disabled={busy} onClick={() => choose(row)} aria-label={text(locale, `ویرایش ${row.name[locale]}`, `Edit ${row.name[locale]}`)}><Pencil size={15}/>{text(locale, 'ویرایش', 'Edit')}</button></td>
        </tr>)}</tbody></table></div>}
      </section>
      {opened && <section className="admin-panel admin-category-editor"><h2 ref={editor} tabIndex={-1}>{selected ? text(locale, 'ویرایش دسته‌بندی', 'Edit category') : text(locale, 'دسته‌بندی جدید', 'New category')}</h2>
        <form className="admin-form" onSubmit={submit}><fieldset disabled={busy}>
          <label>{text(locale, 'نام فارسی', 'Persian name')}<input value={draft.name.fa} onChange={e => update({ name: { ...draft.name, fa: e.target.value } })} required pattern=".*\S.*" maxLength={120} dir="rtl"/></label>
          <label>{text(locale, 'نام انگلیسی', 'English name')}<input value={draft.name.en} onChange={e => update({ name: { ...draft.name, en: e.target.value } })} required pattern=".*\S.*" maxLength={120} dir="ltr"/></label>
          <label>{text(locale, 'نامک نشانی', 'URL slug')}<input value={draft.slug} onChange={e => update({ slug: e.target.value })} required pattern="[a-z0-9]+(-[a-z0-9]+)*" maxLength={80} dir="ltr"/></label>
          <label>{text(locale, 'دستهٔ والد', 'Parent category')}<select value={draft.parent_id || ''} onChange={e => update({ parent_id: e.target.value || null })} disabled={!!selected?.child_count}><option value="">{text(locale, 'بدون والد (دستهٔ اصلی)', 'No parent (top level)')}</option>{roots.filter(row => row.id !== selected?.id).map(row => <option value={row.id} key={row.id}>{row.name[locale]}</option>)}</select></label>
          <p className="admin-hint">{selected?.child_count ? text(locale, 'این دسته زیرمجموعه دارد؛ باید در سطح اصلی بماند.', 'This category has children and must remain at the top level.') : text(locale, 'فقط دو سطح مجاز است. محصولات و ارتباط‌های موجود حفظ می‌شوند.', 'Only two levels are allowed. Existing product links are preserved.')}</p>
          <div className="admin-actions"><button className="button primary" disabled={!dirty || busy}><Save size={16}/>{text(locale, 'ذخیرهٔ دسته', 'Save category')}</button><button className="button secondary" type="button" onClick={() => { adopt(selected); setSaved(false); }}>{text(locale, 'انصراف از ویرایش', 'Discard changes')}</button></div>
        </fieldset></form>
        {saved && <p className="admin-notice success" role="status"><CheckCircle2 size={18}/>{text(locale, 'دسته‌بندی ذخیره شد.', 'Category saved.')}</p>}<CatalogNotice error={error} locale={locale}/>
        {!!error && selected && <button className="text-link" disabled={busy} onClick={() => void compare()}>{text(locale, 'بررسی نسخهٔ فعلی', 'Compare current category')}</button>}
        {comparison && <section className="admin-conflict admin-panel"><h3>{text(locale, 'نسخهٔ فعلی سرور', 'Current server version')}</h3><p>{comparison.name.fa} / {comparison.name.en}</p><p dir="ltr">{comparison.slug}</p><p>{text(locale, 'والد:', 'Parent:')} {rows.find(row => row.id === comparison.parent_id)?.name[locale] || text(locale, 'اصلی', 'Top level')}</p><p>{text(locale, 'نوشته‌های شما حفظ شده‌اند. جایگزینی، فرم فعلی را کنار می‌گذارد.', 'Your draft is preserved. Replacement discards the current form.')}</p><button className="button secondary" onClick={() => adopt(comparison)}>{text(locale, 'جایگزینی با نسخهٔ فعلی', 'Replace with current category')}</button></section>}
      </section>}
    </div>
  </div>;
}
