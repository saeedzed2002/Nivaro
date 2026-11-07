import { ProductArtwork } from './product-artwork';
import Link from 'next/link';
import { ArrowUpRight } from 'lucide-react';
import { text, type Locale, type Product } from '@/lib/content';
import { ProductPrice } from './product-price';

export function ProductCard({ product, locale, categoryLabel }: { product: Product; locale: Locale; categoryLabel?: string }) {
  return <article className="product-card">
    <Link href={`/${locale}/products/${product.slug}`} className="product-image" aria-label={product.name}>
      <ProductArtwork image={product.image} locale={locale} sizes="(max-width: 600px) 90vw, (max-width: 1000px) 45vw, 25vw" />
      <span className="image-caption">{product.image.startsWith('schematic-') ? text(locale, 'نماد دسته', 'CATEGORY SYMBOL') : product.imageKind === 'exact_sku' ? text(locale, 'تصویر مدل', 'MODEL PHOTO') : text(locale, 'تصویر مفهومی', 'ILLUSTRATION')}</span>
      <span className="image-arrow"><ArrowUpRight size={20}/></span>
    </Link>
    <div className="product-body">
      <div className="product-kicker"><span>{categoryLabel ?? product.category}</span><span dir="ltr">{product.brand}</span></div>
      <h3><Link href={`/${locale}/products/${product.slug}`}><bdi>{product.name}</bdi></Link></h3>
      <div className="chips" dir="ltr">{product.highlights.slice(0, 2).map(item => <span key={item}>{item}</span>)}</div>
      <ProductPrice product={product} locale={locale}/>
      <Link className="card-link" href={`/${locale}/products/${product.slug}`}>{text(locale, 'بررسی محصول', 'Explore product')}<ArrowUpRight size={17}/></Link>
    </div>
  </article>;
}
