import type { Metadata } from 'next';
import Image from 'next/image';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import { Search, ArrowRight, SlidersHorizontal } from 'lucide-react';
import { ProductCard } from '@/components/product-card';
import { AvailabilityDialog } from '@/components/availability-dialog';
import { categories, products, isLocale, normalizeSearch, text } from '@/lib/content';

type Props = { params: Promise<{ locale: string }>; searchParams: Promise<Record<string, string | string[] | undefined>> };
export async function generateMetadata({ params }: Props): Promise<Metadata> { const { locale } = await params; return { title: locale === 'fa' ? 'محصولات و قطعات گیمینگ' : 'Gaming hardware collection' }; }

export default async function Products({ params, searchParams }: Props) {
  const [{ locale }, query] = await Promise.all([params, searchParams]);
  if (!isLocale(locale)) notFound();
  const q = typeof query.q === 'string' ? query.q.slice(0,100) : '';
  const category = typeof query.category === 'string' ? query.category : '';
  const brand = typeof query.brand === 'string' ? query.brand : '';
  const sort = query.sort === 'name' ? 'name' : 'featured';
  const term = normalizeSearch(q);
  const result = products.filter(p => (!category || p.category === category) && (!brand || p.brand === brand) && normalizeSearch(`${p.name} ${p.brand} ${p.description.fa} ${p.description.en} ${categories.find(c => c.id === p.category)?.fa}`).includes(term));
  if (sort === 'name') result.sort((a,b) => a.name.localeCompare(b.name));
  return <main id="main-content" className="container listing-page">
    <div className="collection-banner"><Image src="/images/showroom.webp" alt="" fill sizes="100vw"/><div><p className="eyebrow">{text(locale,'از انتخاب تا تجربه','FROM PARTS TO POSSIBILITIES')}</p><h2>{text(locale,'سیستمی بساز که مال تو باشد.','Build something that’s yours.')}</h2><AvailabilityDialog locale={locale} title={text(locale,'میز اسمبل','Build workspace')} className="text-link">{text(locale,'آشنایی با میز اسمبل','Discover the build workspace')}<ArrowRight size={18}/></AvailabilityDialog></div></div>
    <div className="breadcrumb"><Link href={`/${locale}`}>{text(locale,'خانه','Home')}</Link><span>/</span><span>{text(locale,'محصولات','Collection')}</span></div>
    <div className="section-heading"><div><p className="eyebrow">{text(locale,'دنیای قطعات و تجهیزات','THE HARDWARE COLLECTION')}</p><h1>{text(locale,'ارتقای بعدی تو، اینجاست.','Find your next upgrade.')}</h1></div><span className="result-count">{new Intl.NumberFormat(locale).format(result.length)} {text(locale,'محصول مرجع','reference products')}</span></div>
    <p className="section-caption">{text(locale,'قیمت‌های مرجع مربوط به پژوهش‌اند؛ موجودی و فروش فعال نیست. تصاویر، نمونهٔ مفهومی دستهٔ محصول‌اند.','Retail prices are research references, not active offers or stock. Images are conceptual category illustrations.')}</p>
    <div className="catalog-layout">
      <aside className="filter-panel"><form action={`/${locale}/products`}><h2><SlidersHorizontal size={18}/>{text(locale,'فیلتر محصولات','Refine your search')}</h2><label className="field"><span>{text(locale,'جست‌وجو','Search')}</span><input name="q" defaultValue={q} placeholder={text(locale,'نام یا مدل','Name or model')} maxLength={100}/></label><fieldset><legend>{text(locale,'دسته‌بندی','Category')}</legend><label className="radio-option"><input type="radio" name="category" value="" defaultChecked={!category}/>{text(locale,'همهٔ محصولات','All components')}</label>{categories.map(c=><label className="radio-option" key={c.id}><input type="radio" name="category" value={c.id} defaultChecked={category===c.id}/>{c[locale]}</label>)}</fieldset><label className="field"><span>{text(locale,'برند','Brand')}</span><select name="brand" defaultValue={brand}><option value="">{text(locale,'همهٔ برندها','All brands')}</option>{[...new Set(products.map(p=>p.brand))].map(b=><option key={b}>{b}</option>)}</select></label><label className="field"><span>{text(locale,'ترتیب نمایش','Sort by')}</span><select name="sort" defaultValue={sort}><option value="featured">{text(locale,'منتخب','Featured')}</option><option value="name">{text(locale,'نام محصول','Product name')}</option></select></label><button className="button primary">{text(locale,'اعمال فیلترها','Apply filters')}<ArrowRight size={16}/></button><Link className="reset-filters" href={`/${locale}/products`}>{text(locale,'پاک کردن فیلترها','Reset filters')}</Link></form></aside>
      <section aria-label={text(locale,'نتایج محصولات','Product results')}>{q || category || brand ? <div className="active-filter">{text(locale,'انتخاب فعلی:','Current selection:')} <bdi>{[q,categories.find(c=>c.id===category)?.[locale],brand].filter(Boolean).join(' / ')}</bdi></div> : null}{result.length ? <div className="product-grid catalog-products">{result.map(product=><ProductCard key={product.slug} product={product} locale={locale}/>)}</div> : <div className="empty-state"><Search size={40}/><h2>{text(locale,'محصولی با این انتخاب پیدا نشد','No matching products yet')}</h2><p>{text(locale,'فهرست مرجع فعلی محدود است. دسته‌بندی یا عبارت جست‌وجو را تغییر بده.','This reference collection is still small. Try a different category or search term.')}</p><Link className="button primary" href={`/${locale}/products`}>{text(locale,'دیدن همهٔ محصولات','View all products')}</Link></div>}</section>
    </div>
  </main>;
}
