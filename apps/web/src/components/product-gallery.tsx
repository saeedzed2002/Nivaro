'use client';

import Image from 'next/image';
import { useState } from 'react';
import { Info } from 'lucide-react';
import type { PublicImage } from '@/lib/catalog-server';
import { text, type Locale } from '@/lib/content';
import { ProductArtwork } from './product-artwork';

export function ProductGallery({ images, fallback, fallbackKind, locale }: { images: PublicImage[]; fallback: string; fallbackKind?: 'illustration' | 'exact_sku'; locale: Locale }) {
  const [selected, setSelected] = useState(0);
  const current = images[selected] || images[0];
  function source(image: PublicImage, small = false) {
    const widths = Object.keys(image.urls).map(Number).sort((a, b) => a - b);
    return image.urls[String(small ? widths[0] : widths.at(-1))];
  }
  return <figure className="detail-art">
    <div>{current ? <Image src={source(current)} unoptimized alt={current.alt[locale] || ''} fill sizes="(max-width: 800px) 100vw, 55vw" priority/> : <ProductArtwork image={fallback} locale={locale} priority sizes="(max-width: 800px) 100vw, 55vw"/>}</div>
    {images.length > 1 && <nav className="product-gallery-thumbs" aria-label={text(locale, 'تصاویر محصول', 'Product images')}>{images.map((item, index) => <button type="button" key={item.id} aria-pressed={index === selected} aria-label={text(locale, `نمایش تصویر ${index + 1}: ${item.alt.fa}`, `Show image ${index + 1}: ${item.alt.en}`)} onClick={() => setSelected(index)}><Image src={source(item, true)} unoptimized fill sizes="76px" alt=""/></button>)}</nav>}
    <figcaption><Info size={15}/>{(current?.image_kind ?? fallbackKind) === 'exact_sku' ? text(locale, 'تصویر مدل محصول؛ ثبت‌شده توسط فروشگاه.', 'Product model photograph supplied by the store.') : text(locale, 'تصویر مفهومی؛ ظاهر دقیق مدل را از منبع محصول بررسی کن.', 'Concept illustration. Verify the exact model appearance at the product source.')}</figcaption>
  </figure>;
}
