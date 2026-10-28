import type { Metadata } from 'next';
import Image from 'next/image';
import Link from 'next/link';
import { cookies } from 'next/headers';
import { notFound } from 'next/navigation';
import { Search, ArrowRight, SlidersHorizontal } from 'lucide-react';
import { ProductCard } from '@/components/product-card';
import { CatalogUnavailableState } from '@/components/catalog-unavailable';
import { listCatalog, listCategories, productView, type CatalogQuery } from '@/lib/catalog-server';
import { isLocale, text } from '@/lib/content';

type Props = { params: Promise<{ locale: string }>; searchParams: Promise<Record<string, string | string[] | undefined>> };
export async function generateMetadata({ params }: Props): Promise<Metadata> { const { locale } = await params; return { title: locale === 'fa' ? 'محصولات و قطعات گیمینگ' : 'Gaming hardware collection' }; }
export default async function Products({ params, searchParams }: Props) {
  const [{ locale }, query, cookieStore] = await Promise.all([params, searchParams, cookies()]);
  if (!isLocale(locale)) notFound();
  const q = typeof query.q === 'string' ? query.q.slice(0,100) : '';
  const category = typeof query.category === 'string' ? query.category.slice(0,80) : '';
  const brand = typeof query.brand === 'string' ? query.brand.slice(0,120) : '';
  const sorts = ['featured','name','newest','price_asc','price_desc'] as const;
  const sort = sorts.find(s => s === query.sort) ?? 'featured';
  const page = Math.floor(Math.max(1, Math.min(10000, Number(query.page) || 1)));
  const market = cookieStore.get('nivaro-market')?.value === 'international' ? 'international' : 'ir';
  const minor = (value: unknown) => {
    if (value === undefined || value === '') return undefined;
    const pattern = market === 'ir' ? /^\d{1,12}$/ : /^\d{1,10}(\.\d{1,2})?$/;
    if (typeof value !== 'string' || !pattern.test(value)) return null;
    const amount = Math.round(Number(value) * (market === 'ir' ? 10 : 100));
    return amount <= 9_000_000_000_000 ? amount : null;
  };
  const minimum = minor(query.min), maximum = minor(query.max);
  const invalidPrice = minimum === null || maximum === null;
  const invalidRange = minimum != null && maximum != null && minimum > maximum;
  const filterError = invalidPrice
    ? text(locale,'قیمت معتبر و غیرمنفی وارد کن؛ تومان باید عدد صحیح باشد.','Enter a valid non-negative price; toman amounts must be whole numbers.')
    : invalidRange ? text(locale,'حداقل قیمت نباید از حداکثر بیشتر باشد.','Minimum price must not exceed maximum price.') : null;
  const filters: CatalogQuery = { q, category, brand, sort, page, page_size: 24, market, min_price: minimum ?? undefined, max_price: maximum ?? undefined, in_stock: query.stock === '1' };
  const [catalog, categoryData] = await Promise.all([filterError ? Promise.resolve(null) : listCatalog(filters).catch(() => null), listCategories().catch(() => null)]);
  const categories = categoryData ?? [];
  const result = catalog?.items.map(productView) ?? [];
  const pageLink = (value: number) => { const p = new URLSearchParams(); for(const [key,v] of Object.entries(query)) if(typeof v === 'string') p.set(key,v); p.set('page',String(value)); return `/${locale}/products?${p}`; };
  return <main id="main-content" className="container listing-page">
    <div className="collection-banner"><Image src="/images/showroom.webp" alt="" fill sizes="100vw"/><div><p className="eyebrow">{text(locale,'از انتخاب تا تجربه','FROM PARTS TO POSSIBILITIES')}</p><h2>{text(locale,'سیستمی بساز که مال تو باشد.','Build something that’s yours.')}</h2><Link href={`/${locale}/build`} className="text-link">{text(locale,'رفتن به میز اسمبل','Open the build workspace')}<ArrowRight size={18}/></Link></div></div>
    <div className="breadcrumb"><Link href={`/${locale}`}>{text(locale,'خانه','Home')}</Link><span>/</span><span>{text(locale,'محصولات','Collection')}</span></div>
    <div className="section-heading"><div><p className="eyebrow">{text(locale,'دنیای قطعات و تجهیزات','THE HARDWARE COLLECTION')}</p><h1>{text(locale,'ارتقای بعدی تو، اینجاست.','Find your next upgrade.')}</h1></div>{catalog && <span className="result-count">{new Intl.NumberFormat(locale).format(catalog.total)} {text(locale,'محصول مرجع','reference products')}</span>}</div>
    <p className="section-caption">{text(locale,'قیمت‌های مرجع مربوط به پژوهش‌اند؛ موجودی و فروش فعال نیست. تصاویر، نمونهٔ مفهومی دستهٔ محصول‌اند.','Retail prices are research references, not active offers or stock. Images are conceptual category illustrations.')}</p>
    <div className="catalog-layout">
      <aside className="filter-panel"><form key={`${market}:${JSON.stringify(query)}`} action={`/${locale}/products`}><h2><SlidersHorizontal size={18}/>{text(locale,'فیلتر محصولات','Refine your search')}</h2>
        <label className="field"><span>{text(locale,'جست‌وجو','Search')}</span><input name="q" defaultValue={q} placeholder={text(locale,'نام یا مدل','Name or model')} maxLength={100}/></label>
        <fieldset><legend>{text(locale,'دسته‌بندی','Category')}</legend><label className="radio-option"><input type="radio" name="category" value="" defaultChecked={!category}/>{text(locale,'همهٔ محصولات','All components')}</label>{categories.map(c=><label className="radio-option" key={c.id}><input type="radio" name="category" value={c.id} defaultChecked={category===c.id}/>{c[locale]}</label>)}</fieldset>
        <label className="field"><span>{text(locale,'برند','Brand')}</span><input name="brand" defaultValue={brand} maxLength={120} placeholder={text(locale,'نام دقیق برند','Exact brand name')}/></label>
        <label className="field"><span>{text(locale,'ترتیب نمایش','Sort by')}</span><select name="sort" defaultValue={sort}><option value="featured">{text(locale,'منتخب','Featured')}</option><option value="name">{text(locale,'نام محصول','Product name')}</option><option value="newest">{text(locale,'جدیدترین','Newest')}</option><option value="price_asc">{text(locale,'قیمت صعودی','Price: low to high')}</option><option value="price_desc">{text(locale,'قیمت نزولی','Price: high to low')}</option></select></label>
        <label className="field"><span>{text(locale,'حداقل قیمت','Minimum price')} ({market==='ir'?text(locale,'تومان','toman'):'USD'})</span><input name="min" aria-invalid={Boolean(filterError)} aria-describedby={filterError?"price-filter-error":undefined} type="number" min="0" step={market==='ir'?'1':'0.01'} defaultValue={typeof query.min==='string'?query.min:''}/></label>
        <label className="field"><span>{text(locale,'حداکثر قیمت','Maximum price')}</span><input name="max" aria-invalid={Boolean(filterError)} aria-describedby={filterError?"price-filter-error":undefined} type="number" min="0" step={market==='ir'?'1':'0.01'} defaultValue={typeof query.max==='string'?query.max:''}/></label>
        <label className="radio-option"><input name="stock" type="checkbox" value="1" defaultChecked={query.stock==='1'}/>{text(locale,'فقط موجود برای فروش','Available for sale only')}</label>
        <button className="button primary">{text(locale,'اعمال فیلترها','Apply filters')}<ArrowRight size={16}/></button><Link className="reset-filters" href={`/${locale}/products`}>{text(locale,'پاک کردن فیلترها','Reset filters')}</Link>
      </form></aside>
      <section aria-label={text(locale,'نتایج محصولات','Product results')}>
        {filterError ? <div className="empty-state" role="alert" id="price-filter-error"><SlidersHorizontal size={36}/><h2>{text(locale,'بازهٔ قیمت را اصلاح کن','Check your price range')}</h2><p>{filterError}</p></div> : !catalog ? <CatalogUnavailableState locale={locale}/> : result.length ? <><div className="product-grid catalog-products">{result.map(product=><ProductCard key={product.slug} product={product} locale={locale} categoryLabel={categories.find(c=>c.id===product.category)?.[locale]}/>)}</div><nav className="pagination" aria-label={text(locale,'صفحه‌های محصولات','Product pages')}>{page>1 && <Link href={pageLink(page-1)} className="button secondary">{text(locale,'قبلی','Previous')}</Link>}<span>{new Intl.NumberFormat(locale).format(page)} / {new Intl.NumberFormat(locale).format(Math.max(1,Math.ceil(catalog.total/24)))}</span>{page*24<catalog.total && <Link href={pageLink(page+1)} className="button secondary">{text(locale,'بعدی','Next')}</Link>}</nav></> : <div className="empty-state"><Search size={40}/><h2>{text(locale,'محصولی با این انتخاب پیدا نشد','No matching products yet')}</h2><p>{text(locale,'دسته‌بندی یا عبارت جست‌وجو را تغییر بده.','Try a different category or search term.')}</p><Link className="button primary" href={`/${locale}/products`}>{text(locale,'دیدن همهٔ محصولات','View all products')}</Link></div>}
      </section>
    </div>
  </main>;
}
