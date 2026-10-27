import { notFound } from 'next/navigation';
import { Wrench } from 'lucide-react';
import { isLocale, text } from '@/lib/content';
import { listCatalog } from '@/lib/catalog-server';
import { BuildWorkspace } from '@/components/build-workspace';
import { CatalogUnavailableState } from '@/components/catalog-unavailable';

export default async function Build({ params }: {params:Promise<{locale:string}>}) {
  const {locale}=await params;
  if(!isLocale(locale)) notFound();
  const catalog=await listCatalog({page_size:100}).catch(()=>null);
  return <main id="main-content" className="container workspace-page"><div className="workspace-heading"><div><p className="eyebrow">NIVARO / BUILD LAB</p><h1><Wrench/>{text(locale,'میز اسمبل','Your build workspace')}</h1><p>{text(locale,'قطعات را انتخاب کن؛ سازگاری و جمع جزئی را بررسی کن.','Choose your components. Review compatibility and the partial total.')}</p></div></div>{catalog?<BuildWorkspace products={catalog.items} locale={locale}/>:<CatalogUnavailableState locale={locale}/>}</main>;
}
