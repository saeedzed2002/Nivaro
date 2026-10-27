export type Locale = 'fa' | 'en';
export type Market = 'ir' | 'international';
export type Theme = 'system' | 'dark' | 'light';
export const isLocale = (value: string): value is Locale => value === 'fa' || value === 'en';
export const text = (locale: Locale, fa: string, en: string) => locale === 'fa' ? fa : en;

export const categories = [
  { id: 'gpu', fa: 'کارت گرافیک', en: 'Graphics cards', image: 'gpu' },
  { id: 'cpu', fa: 'پردازنده', en: 'Processors', image: 'cpu' },
  { id: 'memory', fa: 'رم و حافظه', en: 'Memory', image: 'memory' },
  { id: 'keyboard', fa: 'کیبورد گیمینگ', en: 'Keyboards', image: 'keyboard' },
  { id: 'pc', fa: 'سیستم‌های آماده', en: 'Gaming PCs', image: 'showroom' },
] as const;

export type Reference = {
  amountMinor: number;
  currency: 'IRR' | 'USD';
  source: string;
  seller: string;
  packaging: { fa: string; en: string };
};
export type Product = {
  slug: string;
  name: string;
  category: string;
  brand: string;
  image: string;
  description: { fa: string; en: string };
  highlights: string[];
  offers: Partial<Record<Market, Reference>>;
};

// Retail observations from the dated research dossier, never store offers or stock.
export const referenceDate = '2026-10-27';
export const products: Product[] = [
  {
    slug: 'amd-ryzen-7-9800x3d', name: 'AMD Ryzen 7 9800X3D', category: 'cpu', brand: 'AMD', image: 'cpu',
    description: { fa: 'نقطهٔ شروع یک سیستم گیمینگ؛ مدل و نوع بسته‌بندی را پیش از انتخاب بررسی کن.', en: 'A starting point for your gaming build. Check the exact model and packaging before choosing.' },
    highlights: ['Ryzen 7', '9800X3D'],
    offers: {
      ir: { amountMinor: 1133900000, currency: 'IRR', source: 'https://www.bprshop.com/product/13105-AMD-Ryzen-7-9800X3D', seller: 'BPR', packaging: { fa: 'بسته‌بندی تری؛ قیمت عادی مرجع', en: 'Tray packaging; ordinary reference price' } },
      international: { amountMinor: 46900, currency: 'USD', source: 'https://www.walmart.com/ip/13796603933?classType=REGULAR', seller: 'Walmart', packaging: { fa: 'بسته‌بندی باکس؛ متفاوت از مرجع ایران', en: 'Boxed; differs from the Iran reference packaging' } },
    },
  },
  {
    slug: 'gigabyte-rtx-5070-eagle', name: 'GIGABYTE RTX 5070 EAGLE OC SFF 12GB', category: 'gpu', brand: 'GIGABYTE', image: 'gpu',
    description: { fa: 'برای انتخاب گرافیک، ابعاد کیس و مشخصات پاور را در کنار مدل کارت بررسی کن.', en: 'Check case clearance and power supply specifications alongside the graphics card model.' },
    highlights: ['RTX 5070', '12GB', 'EAGLE OC SFF'],
    offers: { ir: { amountMinor: 2750000000, currency: 'IRR', source: 'https://gsiran.com/products/graphics-card-gigabyte-rtx-5070-eagle-oc-sff-12g', seller: 'GSI', packaging: { fa: 'مدل ایگل؛ موجودی فروشگاه تأیید نشده', en: 'EAGLE model; store availability not verified' } } },
  },
  {
    slug: 'razer-blackwidow-v4-75', name: 'Razer BlackWidow V4 75%', category: 'keyboard', brand: 'Razer', image: 'keyboard',
    description: { fa: 'چیدمان جمع‌وجور، حس مکانیکی و نورپردازی رنگی؛ نسخهٔ مرجع سالگرد ایکس‌باکس است.', en: 'Compact keys, a mechanical feel and RGB lighting. Reference is the Xbox anniversary edition.' },
    highlights: ['75%', 'US layout', 'Xbox 25 Anniversary'],
    offers: { international: { amountMinor: 20999, currency: 'USD', source: 'https://www.razer.com/gaming-keyboards/razer-blackwidow-v4-75/RZ03-05004300-R3US', seller: 'Razer', packaging: { fa: 'نسخهٔ مونتاژشده؛ چیدمان آمریکا', en: 'Assembled edition; US layout' } } },
  },
  {
    slug: 'cyberpowerpc-gml-99707', name: 'CyberPowerPC GML 99707', category: 'pc', brand: 'CyberPowerPC', image: 'showroom',
    description: { fa: 'سیستم آمادهٔ مرجع؛ قیمت اعلام‌شدهٔ سازنده برای کل سیستم است.', en: 'A reference prebuilt system. The manufacturer price covers the complete advertised configuration.' },
    highlights: ['Ryzen 7 8700F', 'RTX 5060 Ti 16GB', '32GB DDR5', '2TB NVMe'],
    offers: { international: { amountMinor: 206900, currency: 'USD', source: 'https://www.cyberpowerpc.com/system/Prebuilt-PC-GML-99707', seller: 'CyberPowerPC', packaging: { fa: 'سیستم آماده؛ لوازم جانبی تأیید نشده', en: 'Prebuilt system; peripherals not confirmed' } } },
  },
  {
    slug: 'cyberpowerpc-gml-99673', name: 'CyberPowerPC GML 99673', category: 'pc', brand: 'CyberPowerPC', image: 'showroom',
    description: { fa: 'ترکیب آمادهٔ مرجع؛ مدل کامل همهٔ قطعات در خلاصهٔ منبع موجود نیست.', en: 'A reference prebuilt configuration. The source summary does not identify every component model.' },
    highlights: ['Ryzen 7 9800X3D', 'RTX 5070 Ti 16GB', '32GB DDR5', '2TB NVMe'],
    offers: { international: { amountMinor: 283900, currency: 'USD', source: 'https://www.cyberpowerpc.com/system/Prebuilt-PC-GML-99673', seller: 'CyberPowerPC', packaging: { fa: 'قیمت کل سیستم مرجع', en: 'Whole-system reference price' } } },
  },
];

export function formatMoney(reference: Reference, locale: Locale) {
  const language = locale === 'fa' ? 'fa-IR' : 'en-US';
  if (reference.currency === 'IRR') {
    return `${new Intl.NumberFormat(language).format(reference.amountMinor / 10)} ${locale === 'fa' ? 'تومان' : 'tomans'}`;
  }
  return new Intl.NumberFormat(language, { style: 'currency', currency: 'USD' }).format(reference.amountMinor / 100);
}

export function normalizeSearch(value: string) {
  return value.normalize('NFKC').replace(/ي/g, 'ی').replace(/ك/g, 'ک').replace(/\u200c/g, ' ').trim().toLocaleLowerCase();
}
