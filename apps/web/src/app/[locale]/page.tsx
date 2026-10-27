import Image from 'next/image';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import { ArrowLeft, ArrowRight, ArrowUpRight, Boxes, Layers3, SlidersHorizontal } from 'lucide-react';
import { ProductCard } from '@/components/product-card';
import { AvailabilityDialog } from '@/components/availability-dialog';
import { categories, products, text, isLocale } from '@/lib/content';

export default async function Home({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  const Arrow = locale === 'fa' ? ArrowLeft : ArrowRight;
  return <main id="main-content">
    <section className="hero">
      <Image src="/images/showroom.webp" alt={text(locale, 'تصویر مفهومی یک سیستم سفید با فن‌های رنگی روی میز گیمینگ', 'Conceptual white gaming PC with multicolor fans on a studio desk')} fill priority sizes="100vw" className="hero-image hero-dark" />
      <Image src="/images/showroom-light.webp" alt={text(locale, 'تصویر مفهومی همان سیستم در فضای روشن', 'Concept illustration of the same gaming PC in daylight')} fill priority sizes="100vw" className="hero-image hero-light" />
      <div className="hero-shade"/>
      <div className="container hero-inner"><div className="hero-copy">
        <p className="eyebrow"><span className="small-line"/>{text(locale, 'دنیای تو. انتخاب تو.', 'YOUR WORLD. YOUR BUILD.')}</p>
        <h1>{text(locale, 'سیستم تو،', 'Your setup.')}<br/><span>{text(locale, 'با انتخاب تو.', 'Your rules.')}</span></h1>
        <p className="hero-description">{text(locale, 'از اولین قطعه تا ستاپ کامل؛ هر انتخاب، یک قدم نزدیک‌تر به تجربهٔ بازی تو.', 'From the first component to the final detail. Find the hardware that makes your setup yours.')}</p>
        <div className="hero-buttons"><Link href={`/${locale}/products`} className="button primary">{text(locale, 'کشف قطعات', 'Explore components')}<Arrow size={19}/></Link><AvailabilityDialog locale={locale} title={text(locale, 'اسمبل سیستم', 'Build your PC')} className="button secondary">{text(locale, 'میز اسمبل', 'Build your PC')}<Boxes size={20}/></AvailabilityDialog></div>
        <div className="hero-footnote"><span className="rgb-dots"><i/><i/><i/></span><span>{text(locale, 'یک ستاپ، به رنگ خودت', 'A setup that feels like you')}</span></div>
      </div></div>
      <span className="hero-image-note">{text(locale, 'تصویر مفهومی', 'CONCEPT IMAGE')}</span>
    </section>
    <section className="container category-section" aria-label={text(locale, 'دسته‌بندی محصولات', 'Product categories')}>
      <div className="category-strip">{categories.map(category => <Link key={category.id} href={`/${locale}/products?category=${category.id}`} className="category-tile"><div><Image src={`/images/${category.image}.webp`} alt="" fill sizes="(max-width: 600px) 40vw, 20vw"/></div><span>{category[locale]}<ArrowUpRight size={16}/></span></Link>)}</div>
    </section>
    <section className="container section collection-section"><div className="section-heading"><div><p className="eyebrow">{text(locale, 'برای ارتقای بعدی تو', 'THE NEXT UPGRADE')}</p><h2>{text(locale, 'از اینجا شروع کن', 'Find your next upgrade.')}</h2></div><Link href={`/${locale}/products`} className="text-link">{text(locale, 'همهٔ محصولات', 'Explore collection')}<Arrow size={18}/></Link></div><p className="section-caption">{text(locale, 'مدل‌های واقعی با قیمت مرجع مستند؛ عرضهٔ فروشگاه هنوز فعال نیست.', 'Real models with documented retail references. Store offers are not live yet.')}</p><div className="product-grid home-products">{products.slice(0,4).map(product => <ProductCard key={product.slug} product={product} locale={locale}/>)}</div></section>
    <section className="container"><div className="keyboard-banner"><div className="keyboard-art"><Image src="/images/keyboard.webp" alt={text(locale, 'تصویر مفهومی کیبورد مکانیکی با نورپردازی رنگی', 'Concept illustration of a mechanical RGB keyboard')} fill sizes="(max-width: 700px) 100vw, 50vw"/></div><div className="keyboard-copy"><p className="eyebrow">{text(locale, 'فراتر از یک کلیک', 'MAKE EVERY KEY YOURS')}</p><h2>{text(locale, 'کیبوردی برای', 'Feel every move.')}<br/><span>{text(locale, 'سبک بازی تو', 'Own every color.')}</span></h2><p>{text(locale, 'چیدمان جمع‌وجور یا کامل، سوییچ مکانیکی و نورپردازی رنگی؛ جزئیاتی که تجربه را عوض می‌کنند.', 'Compact layouts. Mechanical switches. Your kind of RGB. Find the details that make a difference.')}</p><Link href={`/${locale}/products?category=keyboard`} className="button secondary">{text(locale, 'دیدن کیبوردها', 'Explore keyboards')}<Arrow size={18}/></Link></div></div></section>
    <section className="container section build-teaser"><div><p className="eyebrow">{text(locale, 'از قطعه تا سیستم', 'A MORE CONSIDERED BUILD')}</p><h2>{text(locale, 'هر قطعه، جای خودش.', 'Every component has its place.')}</h2><p>{text(locale, 'میز اسمبل برای کنار هم گذاشتن انتخاب‌ها، بررسی سازگاری و مقایسهٔ دو سیستم در حال ساخت است.', 'A workspace for choosing parts, checking compatibility and comparing two builds is in development.')}</p><AvailabilityDialog locale={locale} title={text(locale, 'میز اسمبل نیوارو', 'The Nivaro build workspace')} className="button secondary">{text(locale, 'دربارهٔ میز اسمبل', 'About the build workspace')}<Arrow size={18}/></AvailabilityDialog></div><div className="build-steps">{[{ icon: Boxes, fa: 'قطعاتت را انتخاب کن', en: 'Choose your components', detailFa: 'از پردازنده تا آخرین وسیلهٔ ستاپ', detailEn: 'From the processor to your last peripheral' },{ icon: Layers3, fa: 'سازگاری را بررسی کن', en: 'Check the fit', detailFa: 'تفاوتِ سازگار، ناسازگار و نامشخص', detailEn: 'Clear compatible, conflicting and unknown states' },{ icon: SlidersHorizontal, fa: 'دو انتخاب را مقایسه کن', en: 'Compare your options', detailFa: 'قطعات و قیمت‌های یک بازار', detailEn: 'Parts and prices within the same market' }].map((step,i)=><div className="build-step" key={step.en}><span className="step-number" dir="ltr">0{i+1}</span><step.icon size={24}/><div><h3>{locale==='fa'?step.fa:step.en}</h3><p>{locale==='fa'?step.detailFa:step.detailEn}</p></div></div>)}</div></section>
  </main>;
}
