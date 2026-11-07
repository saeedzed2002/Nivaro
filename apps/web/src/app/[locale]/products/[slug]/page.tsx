import type { Metadata } from 'next';
import { ProductGallery } from '@/components/product-gallery';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import { MessageSquare, ArrowDown, SlidersHorizontal } from 'lucide-react';
import { ProductPrice } from '@/components/product-price';
import { ProductCard } from '@/components/product-card';
import { CatalogUnavailableState } from '@/components/catalog-unavailable';
import { getCatalogProduct, getProductGallery, listCatalog, listCategories, productView } from '@/lib/catalog-server';
import { specLabel, specValue } from '@/lib/specifications';
import { isLocale, text } from '@/lib/content';

type Props = { params: Promise<{ locale: string; slug: string }> };
export async function generateMetadata({ params }: Props): Promise<Metadata> { const { slug } = await params; const product = await getCatalogProduct(slug).catch(() => null); return { title: product?.name || 'Product' }; }

export default async function ProductDetail({ params }: Props) {
  const { locale, slug } = await params;
  if (!isLocale(locale)) notFound();
  const [record, collection, categories] = await Promise.all([getCatalogProduct(slug).catch(() => undefined), listCatalog({page_size: 5}).catch(() => null), listCategories().catch(() => [])]);
  if (record === undefined) return <main id="main-content" className="container detail-page"><h1>{text(locale,'جزئیات محصول','Product details')}</h1><CatalogUnavailableState locale={locale}/></main>;
  if (!record) notFound();
  const images = await getProductGallery(record.id).catch(() => []);
  const product = productView(record);
  const products = collection?.items.map(productView) ?? [];
  const category = categories.find(c=>c.id===product.category);
  const facts = Object.entries(record.variants[0].specifications).filter(([key,value]) => key !== 'kind' && !Array.isArray(value) && (value === null || typeof value !== 'object'));
  return <main id="main-content" className="container detail-page">
    <div className="breadcrumb"><Link href={`/${locale}`}>{text(locale,'خانه','Home')}</Link><span>/</span><Link href={`/${locale}/products?category=${product.category}`}>{category?.[locale]}</Link><span>/</span><bdi>{product.name}</bdi></div>
    <div className="detail-hero"><ProductGallery images={images} fallback={product.image} fallbackKind={product.imageKind} locale={locale}/><div className="detail-info"><p className="eyebrow" dir="ltr">{product.brand}</p><h1><bdi>{product.name}</bdi></h1><p className="detail-description">{product.description[locale]}</p><div className="chips" dir="ltr">{product.highlights.map(h=><span key={h}>{h}</span>)}</div><ProductPrice product={product} locale={locale} detailed/><div className="detail-actions"><a href="#specifications" className="button primary">{text(locale,'بررسی مشخصات','Explore specifications')}<ArrowDown size={18}/></a><Link href={`/${locale}/compare?product=${product.slug}`} className="button secondary"><SlidersHorizontal size={18}/>{text(locale,'مقایسه','Compare')}</Link></div></div></div>
    <nav className="detail-tabs" aria-label={text(locale,'بخش‌های محصول','Product sections')}><a href="#specifications">{text(locale,'مشخصات ثبت‌شده','Recorded specifications')}</a><a href="#reviews">{text(locale,'دیدگاه‌ها','Reviews')}</a><a href="#related">{text(locale,'محصولات دیگر','More to explore')}</a></nav>
    <div className="detail-lower"><section id="specifications" className="specification-panel"><h2>{text(locale,'مشخصات ثبت‌شده','Recorded specifications')}</h2><dl><div><dt>{text(locale,'مدل','Model')}</dt><dd><bdi>{product.name}</bdi></dd></div><div><dt>{text(locale,'برند','Brand')}</dt><dd><bdi>{product.brand}</bdi></dd></div><div><dt>{text(locale,'دسته‌بندی','Category')}</dt><dd>{category?.[locale]}</dd></div><div><dt>{text(locale,'اطلاعات مرجع','Reference details')}</dt><dd><bdi>{product.highlights.join(' · ')}</bdi></dd></div>{facts.map(([key,value])=><div key={key}><dt>{specLabel(key,locale)}</dt><dd><bdi>{specValue(value,locale)}</bdi></dd></div>)}</dl><div className="variant-list">{record.variants.map(variant=><p key={variant.id}><bdi>{variant.sku}</bdi> · {variant.packaging[locale]}</p>)}</div><div className="source-line">{record.variants[0].evidence?.map(e=><a href={e.url} key={e.url} target="_blank" rel="noopener noreferrer">{text(locale,'منبع مشخصات','Specification source')} ↗ <bdi>{e.checked_on}</bdi></a>)}</div><p className="muted">{text(locale,'سازگاری، گارانتی و موجودی نیوارو هنوز تأیید نشده‌اند. مشخصات ناموجود را قطعی فرض نکن.','Nivaro compatibility, warranty and stock are not verified. Unavailable specifications remain unknown.')}</p></section><section id="reviews" className="review-panel"><h2>{text(locale,'دیدگاه خریداران','Customer reviews')}</h2><MessageSquare size={36}/><h3>{text(locale,'دیدگاه‌ها هنوز فعال نیستند','Reviews are not active yet')}</h3><p>{text(locale,'پس از فعال‌شدن حساب کاربری و بررسی دیدگاه‌ها، تجربهٔ خرید اینجا نمایش داده می‌شود.','Customer experiences will appear here after accounts and review moderation are available.')}</p></section></div>
    <section id="related" className="section"><div className="section-heading"><h2>{text(locale,'بیشتر بررسی کن','More to explore')}</h2><Link href={`/${locale}/products`} className="text-link">{text(locale,'همهٔ محصولات','All products')}</Link></div><div className="product-grid home-products">{products.filter(p=>p.slug!==slug).slice(0,4).map(p=><ProductCard key={p.slug} product={p} locale={locale} categoryLabel={categories.find(c=>c.id===p.category)?.[locale]}/>)}</div></section>
  </main>;
}
