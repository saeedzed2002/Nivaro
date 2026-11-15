'use client';

import Link from 'next/link';
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { AlertCircle, Box, CheckCircle2, ExternalLink, FolderTree, MessageSquare, PackageCheck, UserRound, LogOut, RefreshCw, ShieldCheck } from 'lucide-react';
import { IdentityError, logout, readSession, type IdentitySession } from '@/lib/identity-client';
import { type InitialIdentity } from '@/lib/identity-server';
import { text, type Locale } from '@/lib/content';

export function CatalogNotice({ error, locale }: { error: unknown; locale: Locale }) {
  if (!error) return null;
  const e = error instanceof IdentityError ? error : new IdentityError('catalog.unavailable');
  const descriptions: Record<string, [string, string]> = {
    'media.too_large': ['حجم هر تصویر باید حداکثر ۸ مِبی‌بایت باشد.', 'Each image must be at most 8 MiB.'],
    'catalog.image_required': ['پیش از حذف آخرین تصویر، محصول را به پیش‌نویس برگردانید.', 'Return the product to draft before removing its last image.'],
    'catalog.version_conflict': ['این محصول تغییر کرده است. نوشته‌های شما حفظ شده‌اند؛ نسخهٔ تازه را بارگیری و تغییرات را مقایسه کنید.', 'This product changed. Your draft is preserved; load the latest version and compare before saving.'],
    'catalog.stock_version_conflict': ['موجودی تغییر کرده است. پیش از ثبت، نسخهٔ تازه را بارگیری کنید.', 'Stock changed. Load the latest version before adjusting it.'],
    'catalog.price_version_conflict': ['قیمت تغییر کرده است. نوشته‌های شما حفظ شده‌اند؛ پیش از ثبت، قیمت فعلی را بارگیری کنید.', 'Price changed. Your draft is preserved; load the current price before saving.'],
    'catalog.offer_not_ready': ['عرضه به محصول منتشرشده، تصویر آماده و موجودی بررسی‌شده نیاز دارد.', 'Sale eligibility needs a published product, ready image and verified stock.'],
    'catalog.variant_kind_immutable': ['برای تغییر نوع قطعه، گونهٔ جدید بسازید.', 'Create a new variant for a different hardware type.'],
    'catalog.variant_limit': ['هر محصول حداکثر ۱۰۰ گونه دارد.', 'A product supports at most 100 variants.'],
    'catalog.category_version_conflict': ['دسته‌بندی تغییر کرده است. نوشته‌های شما حفظ شده‌اند؛ نسخهٔ فعلی را بررسی کنید.', 'Category changed. Your draft is preserved; compare the current version.'],
    'catalog.category_hierarchy': ['فقط دو سطح مجاز است؛ دستهٔ دارای زیرمجموعه باید در سطح اصلی بماند.', 'Only two levels are allowed; a category with children must stay at the top level.'],
    'catalog.category_not_found': ['دستهٔ انتخاب‌شده پیدا نشد. فهرست را دوباره بارگیری کنید.', 'Selected category not found. Reload the category list.'],
    'catalog.category_limit': ['حداکثر تعداد دسته‌ها ثبت شده است.', 'The category limit has been reached.'],
    'catalog.stock_reserved': ['موجودی کل نمی‌تواند از تعداد رزروشده کمتر باشد.', 'Physical stock cannot be lower than reserved units.'],
    'catalog.constraint_conflict': ['این نامک یا شناسهٔ کالا قبلاً ثبت شده یا با اطلاعات موجود ناسازگار است.', 'This slug or SKU already exists, or the change conflicts with stored data.'],
    'catalog.not_publishable': ['برای انتشار، اطلاعات کامل، یک گونهٔ معتبر و تصویر آماده لازم است.', 'Publication needs complete content, a valid variant and a ready image.'],
    'catalog.not_found': ['محصول پیدا نشد. به فهرست محصولات برگردید.', 'Product not found. Return to the product list.'],
    'request.invalid': ['مقادیر فرم را بررسی کنید. تغییرات ذخیره نشده‌اند.', 'Check the form values. Changes were not saved.'],
    'csrf.invalid': ['اعتبار درخواست تغییر کرده است؛ دوباره تلاش کنید.', 'Request verification changed; please try again.'],
  };
  const message = e.status === 401 ? text(locale, 'نشست مدیریت پایان یافته است. نوشته‌های خود را نگه دارید و دوباره وارد شوید.', 'Your staff session ended. Keep your draft and sign in again.')
    : e.status === 403 ? text(locale, 'اجازهٔ انجام این عملیات وجود ندارد.', 'You do not have permission to perform this action.')
    : descriptions[e.code] ? text(locale, descriptions[e.code][0], descriptions[e.code][1])
    : text(locale, 'ارتباط برقرار نشد. نوشته‌های شما حفظ شده‌اند. برای اطمینان از نتیجه، اطلاعات فعلی را دوباره بارگیری کنید.', 'Connection unavailable. Your draft is preserved. Reload the current data to check whether your last change was saved.');
  return <div className="admin-notice error" role="alert"><AlertCircle size={20}/><div>{message}{e.status === 401 && <Link className="text-link" href={`/${locale}/admin/login`}>{text(locale, 'ورود مدیران', 'Administrator sign-in')}</Link>}</div></div>;
}

export function StatusBadge({ status, locale }: { status: 'draft' | 'published' | 'archived'; locale: Locale }) {
  const labels = { draft: ['پیش‌نویس', 'Draft'], published: ['منتشرشده', 'Published'], archived: ['بایگانی', 'Archived'] } as const;
  return <span className={`admin-badge ${status}`}><span/>{text(locale, labels[status][0], labels[status][1])}</span>;
}

const AdminSession = createContext<IdentitySession | null>(null);
export const useAdminSession = () => useContext(AdminSession);

const workspaces = {
  catalog: { title: ['مدیریت کاتالوگ', 'Catalog workspace'], access: ['دسترسی مدیریت محصولات', 'Product administration access'], denied: ['این حساب مجوز مدیریت کاتالوگ ندارد.', 'This account does not have catalog management permission.'] },
  orders: { title: ['مدیریت سفارش‌ها', 'Order workspace'], access: ['دسترسی مدیریت سفارش‌ها', 'Order administration access'], denied: ['این حساب مجوز مشاهدهٔ سفارش‌ها را ندارد.', 'This account does not have permission to view orders.'] },
  reviews: { title: ['مدیریت دیدگاه‌ها', 'Review workspace'], access: ['دسترسی بررسی دیدگاه‌ها', 'Review moderation access'], denied: ['این حساب مجوز بررسی دیدگاه‌ها را ندارد.', 'This account does not have permission to moderate reviews.'] },
} as const;

export function AdminShell({ locale, initial, children, selfProfile = false, workspace = 'catalog' }: { locale: Locale; initial: InitialIdentity; selfProfile?: boolean; workspace?: keyof typeof workspaces; children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [identity, setIdentity] = useState(initial.session);
  const [checking, setChecking] = useState(!initial.session && !initial.unavailable);
  const [error, setError] = useState<unknown>(initial.unavailable ? new IdentityError('identity.unavailable') : null);
  const [attempt, setAttempt] = useState(0);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let alive = true;
    readSession('admin').then(value => { if (alive) { setIdentity(value); setError(null); } })
      .catch(e => { if (alive) { setIdentity(null); setError(e); } })
      .finally(() => { if (alive) setChecking(false); });
    return () => { alive = false; };
  }, [attempt]);
  const catalogAllowed = identity?.permissions.includes('catalog.write');
  const ordersAllowed = identity?.permissions.includes('orders.read');
  const reviewsAllowed = identity?.permissions.includes('reviews.moderate');
  const allowed = { catalog: catalogAllowed, orders: ordersAllowed, reviews: reviewsAllowed }[workspace];
  const { title, access, denied } = workspaces[workspace];
  async function signOut() {
    if (document.querySelector('[data-unsaved="true"]') && !window.confirm(text(locale, 'تغییرات ذخیره‌نشده کنار گذاشته شوند؟', 'Leave and discard unsaved changes?'))) return;
    setBusy(true);
    try { await logout('admin', false); setIdentity(null); router.replace(`/${locale}/admin/login`); router.refresh(); }
    catch (e) { setError(e); } finally { setBusy(false); }
  }
  return <main id="main-content" className="admin-page container">
    <div className="admin-layout"><aside className="admin-sidebar">
      <div className="admin-sidebar-title"><ShieldCheck size={24}/><div><strong>{text(locale, title[0], title[1])}</strong><small>{text(locale, 'نیوارو گیمینگ', 'Nivaro Gaming')}</small></div></div>
      <nav aria-label={text(locale, 'ناوبری مدیریت', 'Administration navigation')}>
        {catalogAllowed && <><Link href={`/${locale}/admin/products`} aria-current={pathname.includes('/admin/products') ? 'page' : undefined}><Box size={19}/>{text(locale, 'محصولات', 'Products')}</Link><Link href={`/${locale}/admin/categories`} aria-current={pathname.endsWith('/admin/categories') ? 'page' : undefined}><FolderTree size={19}/>{text(locale, 'دسته‌بندی‌ها', 'Categories')}</Link></>}
        {ordersAllowed && <Link href={`/${locale}/admin/orders`} aria-current={workspace === 'orders' ? 'page' : undefined}><PackageCheck size={19}/>{text(locale, 'سفارش‌ها', 'Orders')}</Link>}
        {reviewsAllowed && <Link href={`/${locale}/admin/reviews`} aria-current={workspace === 'reviews' ? 'page' : undefined}><MessageSquare size={19}/>{text(locale, 'دیدگاه‌ها', 'Reviews')}</Link>}
        {identity && <Link href={`/${locale}/admin/profile`} aria-current={pathname.endsWith('/admin/profile') ? 'page' : undefined}><UserRound size={19}/>{text(locale, 'پروفایل من', 'My profile')}</Link>}
        <Link href={`/${locale}/admin/login`}><ShieldCheck size={19}/>{text(locale, 'نشست و دسترسی‌ها', 'Session & permissions')}</Link>
        <Link href={`/${locale}`}><ExternalLink size={19}/>{text(locale, 'مشاهدهٔ فروشگاه', 'View storefront')}</Link>
        {identity && <button disabled={busy} onClick={() => void signOut()}><LogOut size={19}/>{text(locale, 'خروج از مدیریت', 'Sign out of staff session')}</button>}
      </nav>
      <p className="admin-sidebar-note">{text(locale, 'هر تغییر با حساب مدیر ثبت می‌شود.', 'Changes are recorded with the staff account responsible.')}</p>
    </aside><div className="admin-content">
      {(selfProfile ? identity : allowed) ? <AdminSession.Provider value={identity}><CatalogNotice error={error} locale={locale}/>{children}</AdminSession.Provider> : <section className="admin-panel admin-access">
        <ShieldCheck size={36}/><h1>{text(locale, access[0], access[1])}</h1>
        {checking ? <p role="status">{text(locale, 'در حال بررسی دسترسی…', 'Checking your access…')}</p> : <>
          {identity && !allowed ? <p>{text(locale, denied[0], denied[1])}</p>
            : workspace !== 'catalog' && error instanceof IdentityError && error.status === 401 ? <p>{text(locale, 'با حساب کارکنان وارد شوید.', 'Sign in with a staff account.')}</p>
              : <CatalogNotice error={error} locale={locale}/>}
          <div className="admin-actions"><Link className="button primary" href={`/${locale}/admin/login`}>{text(locale, 'ورود مدیران', 'Administrator sign-in')}</Link><button className="button secondary" onClick={() => { setChecking(true); setAttempt(v => v + 1); }}><RefreshCw size={16}/>{text(locale, 'بررسی دوباره', 'Check again')}</button></div>
        </>}
      </section>}
    </div></div>
  </main>;
}

export function Readiness({ ready, children }: { ready: boolean; children: ReactNode }) {
  return <li>{ready ? <CheckCircle2 size={19}/> : <AlertCircle size={19}/>}<span>{children}</span></li>;
}
