'use client';

import { useId, useRef, type ReactNode } from 'react';
import { X, Wrench } from 'lucide-react';
import { text, type Locale } from '@/lib/content';

export function AvailabilityDialog({ locale, title, children, className = '', label }: { locale: Locale; title: string; children: ReactNode; className?: string; label?: string }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  return <>
    <button className={className} aria-label={label} onClick={() => dialog.current?.showModal()}>{children}</button>
    <dialog ref={dialog} className="feature-dialog" aria-labelledby={titleId} onClick={event => { if (event.target === dialog.current) dialog.current.close(); }}>
      <div className="dialog-content">
        <form method="dialog"><button className="icon-button close" aria-label={text(locale, 'بستن', 'Close')}><X size={20} /></button></form>
        <Wrench className="accent" size={32} />
        <p className="eyebrow">{text(locale, 'در حال ساخت', 'IN DEVELOPMENT')}</p>
        <h2 id={titleId}>{title}</h2>
        <p>{text(locale, 'این بخش هنوز فعال نشده است. در نسخهٔ فعلی می‌توانی محصولات مرجع و مشخصات ثبت‌شده را ببینی؛ خرید و ذخیرهٔ سیستم هنوز در دسترس نیست.', 'This feature is not active yet. You can explore reference products and recorded specifications in this version; purchasing and saved builds are not available yet.')}</p>
        <form method="dialog"><button className="button primary">{text(locale, 'ادامهٔ بررسی محصولات', 'Keep exploring')}</button></form>
      </div>
    </dialog>
  </>;
}
