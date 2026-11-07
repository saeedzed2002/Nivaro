import Image from 'next/image';
import { CircuitBoard, HardDrive, Box, Zap, Fan } from 'lucide-react';
import { text, type Locale } from '@/lib/content';

const symbols = { motherboard: CircuitBoard, storage: HardDrive, case: Box, psu: Zap, cooler: Fan };

/** A category symbol is preferable to an invented photograph of an exact SKU. */
export function ProductArtwork({ image, locale, sizes, priority = false }: {
  image: string; locale: Locale; sizes: string; priority?: boolean;
}) {
  if (!image || image.startsWith('schematic-')) {
    const kind = image.slice('schematic-'.length) as keyof typeof symbols;
    const Symbol = symbols[kind] ?? Box;
    return <div className="hardware-symbol" role="img" aria-label={text(locale, 'نماد دسته؛ تصویر دقیق محصول موجود نیست', 'Category symbol; exact product photograph unavailable')}>
      <Symbol size={104} strokeWidth={1}/>
      <span>{text(locale, 'تصویر محصول در دسترس نیست', 'PRODUCT PHOTO PENDING')}</span>
    </div>;
  }
  if (/^media\/[0-9a-f-]{36}\/(320|640|1280)$/.test(image)) {
    return <Image src={`/api/v1/catalog/images/${image.slice(6)}`} unoptimized alt={text(locale, 'تصویر محصول', 'Product image')} fill sizes={sizes} priority={priority}/>;
  }
  return <Image src={`/images/${image}.webp`} alt={text(locale, 'تصویر مفهومی دسته؛ تصویر دقیق مدل نیست', 'Category illustration, not an exact model photograph')} fill sizes={sizes} priority={priority}/>;
}
