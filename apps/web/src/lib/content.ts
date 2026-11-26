export type Locale = 'fa' | 'en';
export type Market = 'ir' | 'international';
export type Theme = 'system' | 'dark' | 'light';
export const isLocale = (value: string): value is Locale => value === 'fa' || value === 'en';
export const marketForLocale = (stored: string | undefined, locale: Locale): Market =>
  stored === 'ir' || stored === 'international' ? stored : locale === 'fa' ? 'ir' : 'international';
export const text = (locale: Locale, fa: string, en: string) => locale === 'fa' ? fa : en;
export const isUuid = (value: string) => /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(value);

export type Reference = {
  checkedOn?: string;
  amountMinor: number;
  currency: 'IRR' | 'USD';
  source: string;
  seller: string;
  packaging: { fa: string; en: string };
};
export type Product = {
  imageKind?: 'illustration' | 'exact_sku';
  slug: string;
  name: string;
  category: string;
  brand: string;
  image: string;
  description: { fa: string; en: string };
  highlights: string[];
  offers: Partial<Record<Market, Reference>>;
};

export function formatMoney(reference: Reference, locale: Locale) {
  const language = locale === 'fa' ? 'fa-IR' : 'en-US';
  if (reference.currency === 'IRR') {
    return `${new Intl.NumberFormat(language).format(reference.amountMinor / 10)} ${locale === 'fa' ? 'تومان' : 'tomans'}`;
  }
  return new Intl.NumberFormat(language, { style: 'currency', currency: 'USD' }).format(reference.amountMinor / 100);
}

export function formatCommerceMoney(value: number | string, currency: Reference['currency'], locale: Locale) {
  const amount = BigInt(value);
  const language = locale === 'fa' ? 'fa-IR' : 'en-US';
  if (currency === 'IRR') return `${new Intl.NumberFormat(language).format(amount / BigInt(10))} ${text(locale, 'تومان', 'tomans')}`;
  const hundred = BigInt(100);
  const cents = new Intl.NumberFormat(language, { minimumIntegerDigits: 2, useGrouping: false }).format(amount % hundred);
  return new Intl.NumberFormat(language, { style: 'currency', currency: 'USD' }).formatToParts(amount / hundred)
    .map(part => part.type === 'fraction' ? cents : part.value).join('');
}

export function normalizeSearch(value: string) {
  return value.normalize('NFKC').replace(/ي/g, 'ی').replace(/ك/g, 'ک').replace(/\u200c/g, ' ').trim().toLocaleLowerCase();
}
