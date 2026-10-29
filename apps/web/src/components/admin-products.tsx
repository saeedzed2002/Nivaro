'use client';

import Link from 'next/link';
import { useEffect, useState, type FormEvent } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Box, ChevronLeft, ChevronRight, ImageIcon, Pencil, Plus, RefreshCw, Search } from 'lucide-react';
import { adminCategories, listAdminProducts, type AdminCategory, type AdminPage, type Filters } from '@/lib/admin-catalog-client';
import { text, type Locale } from '@/lib/content';
import { CatalogNotice, StatusBadge } from './admin-shared';
import { ProductArtwork } from './product-artwork';

export function AdminProducts({ locale }: { locale: Locale }) {
  const router = useRouter();
  const params = useSearchParams();
  const query = params.toString();
  const [data, setData] = useState<AdminPage | null>(null);
  const [categories, setCategories] = useState<AdminCategory[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [attempt, setAttempt] = useState(0);
  const number = (value: number) => new Intl.NumberFormat(locale === 'fa' ? 'fa-IR' : 'en-US').format(value);
  useEffect(() => {
    let alive = true;
    const url = new URLSearchParams(query);
    const status = url.get('status');
    const filters: Filters = { q: (url.get('q') || '').slice(0, 100), page: Math.min(10000, Math.max(1, Number(url.get('page')) || 1)), page_size: 10 };
    if (status === 'draft' || status === 'published' || status === 'archived') filters.status = status;
    const category = url.get('category');
    if (category && /^[0-9a-f-]{36}$/i.test(category)) filters.category_id = category;
    Promise.all([listAdminProducts(filters), adminCategories()]).then(([products, groups]) => {
      if (alive) { setData(products); setCategories(groups); setError(null); }
    }).catch(e => { if (alive) { setError(e); setData(null); } }).finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [query, attempt]);
  function navigate(next: URLSearchParams) { setLoading(true); setError(null); router.push(`/${locale}/admin/products?${next}`, { scroll: false }); }
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const next = new URLSearchParams();
    for (const key of ['q', 'status', 'category']) { const value = String(form.get(key) || '').trim(); if (value) next.set(key, value); }
    if (next.toString() === query) { setLoading(true); setAttempt(n => n + 1); } else navigate(next);
  }
  function page(value: number) { const next = new URLSearchParams(query); next.set('page', String(value)); navigate(next); }
  return <>
    <div className="admin-heading"><div><p className="eyebrow">{text(locale, 'کاتالوگ فروشگاه', 'STORE CATALOG')}</p><h1>{text(locale, 'محصولات', 'Products')}</h1><p>{text(locale, 'از قطعات سیستم تا تجهیزات ستاپ؛ اطلاعات هر محصول را مدیریت کنید.', 'Manage the components and equipment behind every setup.')}</p></div><Link href={`/${locale}/admin/products/new`} className="button primary"><Plus size={19}/>{text(locale, 'افزودن محصول', 'Add product')}</Link></div>
    <form className="admin-filters admin-panel" onSubmit={submit} key={query} role="search" aria-label={text(locale, 'فیلتر محصولات مدیریت', 'Filter administration products')}>
      <label className="admin-search"><Search size={20}/><span className="sr-only">{text(locale, 'نام محصول یا شناسهٔ کالا', 'Product name or SKU')}</span><input name="q" defaultValue={params.get('q') || ''} maxLength={100} placeholder={text(locale, 'جست‌وجو با نام محصول یا شناسهٔ کالا…', 'Search by product name or SKU…')}/></label>
      <div className="admin-filter-row"><label>{text(locale, 'دسته‌بندی', 'Category')}<select name="category" defaultValue={params.get('category') || ''}><option value="">{text(locale, 'همهٔ دسته‌ها', 'All categories')}</option>{categories.map(category => <option key={category.id} value={category.id}>{category.name[locale]}</option>)}</select></label>
      <label>{text(locale, 'وضعیت انتشار', 'Publication status')}<select name="status" defaultValue={params.get('status') || ''}><option value="">{text(locale, 'همهٔ وضعیت‌ها', 'All statuses')}</option><option value="draft">{text(locale, 'پیش‌نویس', 'Draft')}</option><option value="published">{text(locale, 'منتشرشده', 'Published')}</option><option value="archived">{text(locale, 'بایگانی', 'Archived')}</option></select></label>
      <button className="button secondary" disabled={loading}>{text(locale, 'اعمال فیلتر', 'Apply filters')}</button>{query && <Link className="text-link" href={`/${locale}/admin/products`} onClick={() => setLoading(true)}>{text(locale, 'پاک‌کردن فیلترها', 'Clear filters')}</Link>}</div>
    </form>
    <div className="admin-result-heading"><p role="status">{loading ? text(locale, 'در حال دریافت محصولات…', 'Loading products…') : data ? text(locale, `${number(data.total)} محصول`, `${number(data.total)} products`) : ''}</p><span className="admin-hint"><ImageIcon size={16}/>{text(locale, 'انتشار به اطلاعات کامل و تصویر آماده نیاز دارد.', 'Publication needs complete content and a ready image.')}</span></div>
    <CatalogNotice error={error} locale={locale}/>{!!error && <button className="button secondary" onClick={() => { setLoading(true); setAttempt(n => n + 1); }}><RefreshCw size={16}/>{text(locale, 'تلاش دوباره', 'Try again')}</button>}
    {data && !loading && (data.items.length ? <>
      <div className="admin-table-wrap"><table className="admin-table"><caption className="sr-only">{text(locale, 'فهرست محصولات مدیریت', 'Administration product list')}</caption><thead><tr>{[text(locale, 'محصول', 'Product'), text(locale, 'دسته‌بندی', 'Category'), text(locale, 'گونه‌ها', 'Variants'), text(locale, 'وضعیت انتشار', 'Publication'), text(locale, 'تصویر', 'Image'), text(locale, 'عملیات', 'Actions')].map(label => <th key={label} scope="col">{label}</th>)}</tr></thead><tbody>{data.items.map(product => <tr key={product.id}>
        <td><div className="admin-product-name"><div className="admin-thumbnail">{product.image ? <ProductArtwork image={product.image} locale={locale} sizes="64px"/> : <Box size={30}/>}</div><div><strong dir="auto">{product.name}</strong><small dir="auto">{product.brand || '—'}</small></div></div></td>
        <td data-label={text(locale, 'دسته‌بندی', 'Category')}>{categories.find(category => category.id === product.category_id)?.name[locale] || '—'}</td>
        <td data-label={text(locale, 'گونه‌ها', 'Variants')}>{number(product.variant_count)}</td>
        <td><StatusBadge status={product.status} locale={locale}/></td>
        <td><span className={`admin-media ${product.image_ready ? 'ready' : ''}`}><ImageIcon size={15}/>{product.image_ready ? text(locale, 'آماده', 'Ready') : text(locale, 'نیازمند تصویر', 'Image needed')}</span></td>
        <td><Link className="admin-edit-link" href={`/${locale}/admin/products/${product.id}`} aria-label={text(locale, `ویرایش ${product.name}`, `Edit ${product.name}`)}><Pencil size={15}/>{text(locale, 'ویرایش', 'Edit')}</Link></td>
      </tr>)}</tbody></table></div>
      <nav className="admin-pagination" aria-label={text(locale, 'صفحه‌بندی محصولات', 'Product pagination')}><button className="button secondary" disabled={data.page <= 1} onClick={() => page(data.page - 1)}><ChevronLeft size={17}/>{text(locale, 'قبلی', 'Previous')}</button><span>{text(locale, `صفحهٔ ${number(data.page)} از ${number(Math.ceil(data.total / data.page_size))}`, `Page ${number(data.page)} of ${number(Math.ceil(data.total / data.page_size))}`)}</span><button className="button secondary" disabled={data.page * data.page_size >= data.total} onClick={() => page(data.page + 1)}>{text(locale, 'بعدی', 'Next')}<ChevronRight size={17}/></button></nav>
    </> : <section className="admin-empty admin-panel"><Search size={32}/><h2>{text(locale, 'محصولی پیدا نشد', 'No products found')}</h2><p>{text(locale, 'عبارت جست‌وجو یا فیلترها را تغییر دهید.', 'Change your search or filters to find products.')}</p><Link className="button secondary" href={`/${locale}/admin/products`}>{text(locale, 'نمایش همهٔ محصولات', 'Show all products')}</Link></section>)}
  </>;
}
