import type { Metadata } from 'next';
import { cookies, headers } from 'next/headers';
import '@fontsource-variable/vazirmatn';
import '@fontsource-variable/inter';
import './globals.css';
import { PreferencesProvider } from '@/components/preferences';
import type { Market, Theme } from '@/lib/content';

export const metadata: Metadata = { title: { default: 'Nivaro Gaming | نیوارو گیمینگ', template: '%s | Nivaro Gaming' }, description: 'Gaming hardware, components and a more considered PC build. قطعات کامپیوتر و تجهیزات گیمینگ نیوارو.' };

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const [requestHeaders, cookieStore] = await Promise.all([headers(), cookies()]);
  const locale = requestHeaders.get('x-nivaro-locale') === 'en' ? 'en' : 'fa';
  const storedMarket = cookieStore.get('nivaro-market')?.value;
  const storedTheme = cookieStore.get('nivaro-theme')?.value;
  const market: Market = storedMarket === 'ir' || storedMarket === 'international' ? storedMarket : locale === 'fa' ? 'ir' : 'international';
  const theme: Theme = storedTheme === 'light' || storedTheme === 'dark' ? storedTheme : 'system';
  return <html lang={locale === 'fa' ? 'fa-IR' : 'en'} dir={locale === 'fa' ? 'rtl' : 'ltr'} data-theme={theme}><body><PreferencesProvider initialMarket={market} initialTheme={theme}>{children}</PreferencesProvider></body></html>;
}
