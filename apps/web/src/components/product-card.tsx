import Image from 'next/image';
import Link from 'next/link';
import { ArrowUpRight } from 'lucide-react';
import { categories, text, type Locale, type Product } from '@/lib/content';
import { ProductPrice } from './product-price';

export function ProductCard({ product, locale }: { product: Product; locale: Locale }) {
  const category = categories.find(c => c.id === product.category);
  return <article className="product-card">
    <Link href={`/${locale}/products/${product.slug}`} className="product-image" aria-label={product.name}>
      <Image src={`/images/${product.image}.webp`} alt={text(locale, 'تصویر مفهومی این دسته؛ تصویر دقیق محصول نیست', 'Concept illustration of this category, not an exact product photograph')} fill sizes="(max-width: 600px) 90vw, (max-width: 1000px) 45vw, 25vw" />
      <span className="image-caption">{text(locale, 'تصویر مفهومی', 'ILLUSTRATION')}</span>
      <span className="image-arrow"><ArrowUpRight size={20}/></span>
    </Link>
    <div className="product-body">
      <div className="product-kicker"><span>{category?.[locale]}</span><span dir="ltr">{product.brand}</span></div>
      <h3><Link href={`/${locale}/products/${product.slug}`}><bdi>{product.name}</bdi></Link></h3>
      <div className="chips" dir="ltr">{product.highlights.slice(0, 2).map(item => <span key={item}>{item}</span>)}</div>
      <ProductPrice product={product} locale={locale}/>
      <Link className="card-link" href={`/${locale}/products/${product.slug}`}>{text(locale, 'بررسی محصول', 'Explore product')}<ArrowUpRight size={17}/></Link>
    </div>
  </article>;
}
