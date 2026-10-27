import { notFound } from 'next/navigation';
import Image from 'next/image';
import { Scale } from 'lucide-react';
import { isLocale, text } from '@/lib/content';
import { listCatalog } from '@/lib/catalog-server';
import { ProductComparison } from '@/components/product-comparison';
import { CatalogUnavailableState } from '@/components/catalog-unavailable';

export default async function Compare({ params, searchParams }: { params: Promise<{locale:string}>; searchParams: Promise<{product?:string}> }) {
  const [{locale},query] = await Promise.all([params,searchParams]);
  if (!isLocale(locale)) notFound();
  const catalog = await listCatalog({page_size:100}).catch(()=>null);
  return <main id="main-content" className="container workspace-page"><div className="workspace-heading"><div><p className="eyebrow">NIVARO / COMPARE</p><h1><Scale/>{text(locale,'مقایسهٔ محصولات','Compare products')}</h1><p>{text(locale,'تفاوت‌ها را ببین؛ انتخابت را آگاهانه انجام بده.','See the differences. Make a more informed choice.')}</p></div><div className="workspace-heading-art"><Image src="/images/showroom.webp" alt="" fill sizes="35vw"/></div></div>{catalog?<ProductComparison products={catalog.items} initialSlug={query.product} locale={locale}/>:<CatalogUnavailableState locale={locale}/>}</main>;
}
