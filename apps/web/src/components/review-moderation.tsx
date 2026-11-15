'use client';

import Link from 'next/link';
import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { checkoutTime } from '@/lib/checkout-copy';
import { text, type Locale } from '@/lib/content';
import { IdentityError } from '@/lib/identity-client';
import { decideReview, listModerationQueue, type ReviewDecision, type SavedReview } from '@/lib/reviews-client';
import { useAdminSession } from './admin-shared';
import { ReviewProblem, ReviewRating, reviewStatus, VerifiedPurchase } from './review-fields';

const statuses = ['pending', 'approved', 'rejected'] as const;

export function ReviewModeration({ locale }: { locale: Locale }) {
  const staff = useAdminSession();
  const client = useQueryClient();
  const prefix = ['review-moderation', staff?.profile.id] as const;
  const [status, setStatus] = useState<SavedReview['status']>('pending');
  const [selectedId, setSelectedId] = useState<string>();
  const [saved, setSaved] = useState(false);
  const queue = useInfiniteQuery({
    queryKey: [...prefix, status], initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam, signal }) => listModerationQueue(status, pageParam, signal),
    getNextPageParam: page => page.next_before ?? undefined,
    gcTime: 0, refetchOnWindowFocus: false,
  });
  const rows = new Map(queue.data?.pages.flatMap(page => page.reviews.map(review => [review.id, review] as const)));
  const selected = (selectedId ? rows.get(selectedId) : undefined) ?? rows.values().next().value;

  function onSaved(review: SavedReview) {
    setSaved(true);
    void client.invalidateQueries({ queryKey: prefix });
    void client.resetQueries({ queryKey: ['product-reviews', review.product_id] });
  }

  return <>
    <header className="admin-heading"><h1>{text(locale, 'بررسی دیدگاه‌ها', 'Review moderation')}</h1></header>
    <div className="admin-filter-row staff-order-filter"><label><span id="moderation-status-label">{text(locale, 'وضعیت', 'Status')}</span>
      <select aria-labelledby="moderation-status-label" value={status} onChange={event => { setStatus(event.target.value as SavedReview['status']); setSelectedId(undefined); setSaved(false); }}>
        {statuses.map(value => <option key={value} value={value}>{reviewStatus(locale, value)}</option>)}
      </select>
    </label></div>
    {saved && <p className="admin-notice success" role="status">{text(locale, 'تصمیم بررسی ثبت شد.', 'Review decision saved.')}</p>}
    {queue.isPending ? <p role="status">{text(locale, 'در حال دریافت دیدگاه‌ها…', 'Loading reviews…')}</p>
      : queue.isError ? <><ReviewProblem locale={locale} error={queue.error}/>
        {queue.error instanceof IdentityError && queue.error.status === 401
          ? <Link href={`/${locale}/admin/login`} className="button secondary">{text(locale, 'ورود مدیران', 'Administrator sign-in')}</Link>
          : <button className="button secondary" onClick={() => void queue.refetch()}>{text(locale, 'بارگیری دوباره', 'Reload')}</button>}
      </>
      : !selected ? <p className="admin-panel">{text(locale, 'دیدگاهی در این وضعیت وجود ندارد.', 'No reviews match this status.')}</p>
      : <div className="review-moderation-layout">
        <section className="admin-panel review-queue" aria-labelledby="review-queue-heading">
          <h2 id="review-queue-heading">{text(locale, 'فهرست دیدگاه‌ها', 'Review queue')}</h2>
          <ul>{[...rows.values()].map(review => <li key={review.id}><button type="button" className="review-queue-item" aria-pressed={review.id === selected.id} onClick={() => { setSelectedId(review.id); setSaved(false); }}>
            <div className="review-meta"><ReviewRating locale={locale} value={review.rating}/><time dateTime={review.created_at}>{checkoutTime(review.created_at, locale)}</time></div>
            <bdi className="review-excerpt">{review.body}</bdi>
          </button></li>)}</ul>
          {queue.hasNextPage && <button className="button secondary" disabled={queue.isFetching} onClick={() => void queue.fetchNextPage()}>{text(locale, 'دیدگاه‌های بیشتر', 'More reviews')}</button>}
        </section>
        <ReviewDecisionPanel key={selected.id} review={selected} locale={locale} onSaved={onSaved} reload={async () => (await queue.refetch()).isSuccess} busy={queue.isFetching}/>
      </div>}
  </>;
}

function ReviewDecisionPanel({ review, locale, onSaved, reload, busy }: { review: SavedReview; locale: Locale; onSaved: (review: SavedReview) => void; reload: () => Promise<boolean>; busy: boolean }) {
  const [reason, setReason] = useState('');
  const [draftVersion, setDraftVersion] = useState(review.version);
  const decision = useMutation({
    mutationFn: (body: ReviewDecision) => decideReview(review.id, body),
    onSuccess: saved => { setReason(''); onSaved(saved); },
  });
  const error = decision.error;
  const blocked = error instanceof IdentityError && [401, 403].includes(error.status);
  const conflict = error instanceof IdentityError && error.status === 409;
  const changed = draftVersion !== review.version;

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const submitter = (event.nativeEvent as SubmitEvent).submitter;
    const next = submitter instanceof HTMLButtonElement ? submitter.value : '';
    if ((next !== 'approved' && next !== 'rejected') || next === review.status || !reason.trim() || busy || decision.isPending || blocked || conflict || changed) return;
    decision.mutate({ status: next, reason, expected_version: draftVersion });
  }

  async function refresh() {
    if (await reload()) decision.reset();
  }

  return <section className="admin-panel review-decision" aria-labelledby="selected-review-heading">
    <header className="admin-panel-heading"><h2 id="selected-review-heading">{text(locale, 'دیدگاه انتخاب‌شده', 'Selected review')}</h2><span>{reviewStatus(locale, review.status)}</span></header>
    <p className="review-product-ref">{text(locale, 'شناسهٔ محصول', 'Product reference')} <bdi dir="ltr">{review.product_id}</bdi></p>
    <div className="review-meta"><ReviewRating locale={locale} value={review.rating}/>
      {review.verified_purchase && <VerifiedPurchase locale={locale}/>}
      <time dateTime={review.created_at}>{checkoutTime(review.created_at, locale)}</time>
    </div>
    <p className="review-body review-decision-body" dir="auto">{review.body}</p>
    {review.moderation_reason && <p className="review-body">{text(locale, 'دلیل تصمیم قبلی: ', 'Previous decision reason: ')}<bdi>{review.moderation_reason}</bdi></p>}
    {error && <ReviewProblem locale={locale} error={error}/>}
    {conflict && <button type="button" className="button secondary" disabled={busy} onClick={() => void refresh()}>{text(locale, 'بارگیری دیدگاه‌ها', 'Reload reviews')}</button>}
    {!conflict && changed && <div className="admin-notice" role="status"><span>{text(locale, 'نسخهٔ جدید دیدگاه را بررسی کنید.', 'Review the updated content.')}</span>
      <button type="button" className="button secondary" onClick={() => setDraftVersion(review.version)}>{text(locale, 'انتخاب نسخهٔ فعلی', 'Use current version')}</button></div>}
    {blocked && error.status === 401 && <Link href={`/${locale}/admin/login`} className="button secondary">{text(locale, 'ورود مدیران', 'Administrator sign-in')}</Link>}
    <form className="admin-form" onSubmit={submit} data-unsaved={reason.trim() ? 'true' : undefined}>
      <label>{text(locale, 'دلیل تصمیم', 'Decision reason')}<textarea dir="auto" value={reason} onChange={event => setReason(event.target.value)} rows={4} maxLength={400} required disabled={decision.isPending}/></label>
      <div className="admin-actions">
        {review.status !== 'rejected' && <button type="submit" value="rejected" className="button secondary" disabled={!reason.trim() || busy || decision.isPending || blocked || conflict || changed}>{text(locale, 'رد دیدگاه', 'Reject review')}</button>}
        {review.status !== 'approved' && <button type="submit" value="approved" className="button primary" disabled={!reason.trim() || busy || decision.isPending || blocked || conflict || changed}>{text(locale, 'تأیید دیدگاه', 'Approve review')}</button>}
      </div>
    </form>
  </section>;
}
