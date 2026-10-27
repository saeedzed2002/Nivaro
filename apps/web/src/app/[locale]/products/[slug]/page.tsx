import type { Metadata } from 'next';
import Image from 'next/image';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import { MessageSquare, ArrowDown, SlidersHorizontal, Info } from 'lucide-react';
import { ProductPrice } from '@/components/product-price';
import { ProductCard } from '@/components/product-card';
import { AvailabilityDialog } from '@/components/availability-dialog';
import { products, categories, isLocale, text } from '@/lib/content';

type Props = { params: Promise<{ locale: string; slug: string }> };
export async function generateMetadata({ params }: Props): Promise<Metadata> { const { slug } = await params; return { title: products.find(p=>p.slug===slug)?.name || 'Product' }; }

export default async function ProductDetail({ params }: Props) {
  const { locale, slug } = await params;
  const product = products.find(p=>p.slug===slug);
  if (!isLocale(locale) || !product) notFound();
  const category = categories.find(c=>c.id===product.category);
  return <main id="main-content" className="container detail-page">
    <div className="breadcrumb"><Link href={`/${locale}`}>{text(locale,'خانه','Home')}</Link><span>/</span><Link href={`/${locale}/products?category=${product.category}`}>{category?.[locale]}</Link><span>/</span><bdi>{product.name}</bdi></div>
    <div className="detail-hero"><figure className="detail-art"><div><Image src={`/images/${product.image}.webp`} alt={text(locale,'تصویر مفهومی دستهٔ محصول؛ تصویر دقیق این مدل نیست','Conceptual category illustration; not a photograph of this exact model')} fill priority sizes="(max-width: 800px) 100vw, 55vw"/></div><figcaption><Info size={15}/>{text(locale,'تصویر مفهومی؛ ظاهر دقیق مدل را از منبع محصول بررسی کن.','Concept illustration. Verify the exact model appearance at the product source.')}</figcaption></figure><div className="detail-info"><p className="eyebrow" dir="ltr">{product.brand}</p><h1><bdi>{product.name}</bdi></h1><p className="detail-description">{product.description[locale]}</p><div className="chips" dir="ltr">{product.highlights.map(h=><span key={h}>{h}</span>)}</div><ProductPrice product={product} locale={locale} detailed/><div className="detail-actions"><a href="#specifications" className="button primary">{text(locale,'بررسی مشخصات','Explore specifications')}<ArrowDown size={18}/></a><AvailabilityDialog locale={locale} title={text(locale,'مقایسهٔ محصولات','Compare products')} className="button secondary"><SlidersHorizontal size={18}/>{text(locale,'مقایسه','Compare')}</AvailabilityDialog></div></div></div>
    <nav className="detail-tabs" aria-label={text(locale,'بخش‌های محصول','Product sections')}><a href="#specifications">{text(locale,'مشخصات ثبت‌شده','Recorded specifications')}</a><a href="#reviews">{text(locale,'دیدگاه‌ها','Reviews')}</a><a href="#related">{text(locale,'محصولات دیگر','More to explore')}</a></nav>
    <div className="detail-lower"><section id="specifications" className="specification-panel"><h2>{text(locale,'مشخصات ثبت‌شده','Recorded specifications')}</h2><dl><div><dt>{text(locale,'مدل','Model')}</dt><dd><bdi>{product.name}</bdi></dd></div><div><dt>{text(locale,'برند','Brand')}</dt><dd><bdi>{product.brand}</bdi></dd></div><div><dt>{text(locale,'دسته‌بندی','Category')}</dt><dd>{category?.[locale]}</dd></div><div><dt>{text(locale,'اطلاعات مرجع','Reference details')}</dt><dd><bdi>{product.highlights.join(' · ')}</bdi></dd></div></dl><p className="muted">{text(locale,'سازگاری، گارانتی و موجودی نیوارو هنوز تأیید نشده‌اند. مشخصات ناموجود را قطعی فرض نکن.','Nivaro compatibility, warranty and stock are not verified. Unavailable specifications remain unknown.')}</p></section><section id="reviews" className="review-panel"><h2>{text(locale,'دیدگاه خریداران','Customer reviews')}</h2><MessageSquare size={36}/><h3>{text(locale,'دیدگاه‌ها هنوز فعال نیستند','Reviews are not active yet')}</h3><p>{text(locale,'پس از فعال‌شدن حساب کاربری و بررسی دیدگاه‌ها، تجربهٔ خرید اینجا نمایش داده می‌شود.','Customer experiences will appear here after accounts and review moderation are available.')}</p></section></div>
    <section id="related" className="section"><div className="section-heading"><h2>{text(locale,'بیشتر بررسی کن','More to explore')}</h2><Link href={`/${locale}/products`} className="text-link">{text(locale,'همهٔ محصولات','All products')}</Link></div><div className="product-grid home-products">{products.filter(p=>p.slug!==slug).slice(0,4).map(p=><ProductCard key={p.slug} product={p} locale={locale}/>)}</div></section>
  </main>;
}
