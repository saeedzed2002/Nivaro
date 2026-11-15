'use client';

import Link from 'next/link';
import { MessageSquare } from 'lucide-react';
import { useEffect, useState, type FormEvent } from 'react';
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { checkoutTime } from '@/lib/checkout-copy';
import { text, type Locale } from '@/lib/content';
import { IdentityError } from '@/lib/identity-client';
import { listProductReviews, readOwnReview, saveOwnReview, type ReviewInput } from '@/lib/reviews-client';
import { ReviewProblem, ReviewRating, reviewStatus, VerifiedPurchase } from './review-fields';

const publicKey = (productId: string) => ['product-reviews', productId] as const;

export function ProductReviews({ productId, slug, locale, openEditor }: { productId: string; slug: string; locale: Locale; openEditor: boolean }) {
  const [editing, setEditing] = useState(openEditor);
  const list = useInfiniteQuery({
    queryKey: publicKey(productId), initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam, signal }) => listProductReviews(productId, pageParam, signal),
    getNextPageParam: page => page.next_before ?? undefined,
    staleTime: 10_000,
  });
  useEffect(() => {
    const close = () => setEditing(false);
    const storage = (event: StorageEvent) => { if (event.key === 'nivaro-customer-session') close(); };
    window.addEventListener('nivaro-customer-session', close);
    window.addEventListener('storage', storage);
    return () => {
      window.removeEventListener('nivaro-customer-session', close);
      window.removeEventListener('storage', storage);
    };
  }, []);
  const summary = list.data?.pages[0];
  const reviews = new Map(list.data?.pages.flatMap(page => page.reviews.map(review => [review.id, review] as const)));
  const count = new Intl.NumberFormat(locale).format(summary?.count ?? 0);
  return <section id="reviews" className="review-panel" aria-labelledby="reviews-heading">
    <h2 id="reviews-heading">{text(locale, 'دیدگاه خریداران', 'Customer reviews')}</h2>
    {list.isPending && <p role="status">{text(locale, 'در حال دریافت دیدگاه‌ها…', 'Loading reviews…')}</p>}
    {list.isError && <><ReviewProblem locale={locale} error={list.error}/><button className="button secondary" onClick={() => void list.refetch()}>{text(locale, 'تلاش مجدد', 'Retry')}</button></>}
    {summary && summary.count === 0 && <div className="review-empty">
      <MessageSquare size={32} aria-hidden="true"/>
      <p>{text(locale, 'هنوز دیدگاهی تأیید نشده است.', 'No approved reviews yet.')}</p>
    </div>}
    {summary && summary.average_rating !== null && <p className="review-average">
      <ReviewRating locale={locale} value={summary.average_rating}/>
      <span>{text(locale, `${count} دیدگاه`, summary.count === 1 ? '1 approved review' : `${count} approved reviews`)}</span>
    </p>}
    {!!reviews.size && <ul className="review-list" aria-label={text(locale, 'دیدگاه‌های تأییدشده', 'Approved reviews')}>
      {[...reviews.values()].map(review => <li key={review.id}>
        <div className="review-meta"><ReviewRating locale={locale} value={review.rating}/>
          {review.verified_purchase && <VerifiedPurchase locale={locale}/>}
          <time dateTime={review.created_at}>{checkoutTime(review.created_at, locale)}</time>
        </div>
        <p className="review-body" dir="auto">{review.body}</p>
      </li>)}
    </ul>}
    {list.hasNextPage && <button className="button secondary" disabled={list.isFetching} onClick={() => void list.fetchNextPage()}>{text(locale, 'دیدگاه‌های بیشتر', 'More reviews')}</button>}
    <button className="button secondary review-open-editor" aria-expanded={editing} aria-controls="product-review-editor" onClick={() => setEditing(value => !value)}>
      {editing ? text(locale, 'بستن فرم دیدگاه', 'Close review editor') : text(locale, 'نوشتن دیدگاه', 'Write a review')}
    </button>
    <div id="product-review-editor">{editing && <ReviewEditor productId={productId} locale={locale} slug={slug}/>}</div>
  </section>;
}

function ReviewEditor({ productId, locale, slug }: { productId: string; locale: Locale; slug: string }) {
  const queryClient = useQueryClient();
  const key = ['my-product-review', productId] as const;
  const [draft, setDraft] = useState<ReviewInput | null>(null);
  const own = useQuery({ queryKey: key, queryFn: ({ signal }) => readOwnReview(productId, signal), gcTime: 0, refetchOnWindowFocus: false });
  const mutation = useMutation({
    mutationFn: (body: ReviewInput) => saveOwnReview(productId, body),
    onSuccess: review => {
      queryClient.setQueryData(key, { review });
      setDraft(null);
      void queryClient.resetQueries({ queryKey: publicKey(productId) });
    },
  });
  const review = own.data?.review;
  const input = draft ?? { rating: review?.rating ?? 0, body: review?.body ?? '', expected_version: review?.version ?? 0 };
  const error = mutation.error ?? own.error;
  const status = error instanceof IdentityError ? error.status : 0;
  const [reloaded, setReloaded] = useState(false);

  async function reload() {
    const result = await own.refetch();
    if (!result.isSuccess) return;
    setDraft(current => current && { ...current, expected_version: result.data.review?.version ?? 0 });
    mutation.reset();
    setReloaded(true);
  }

  function change(next: Partial<ReviewInput>) {
    setDraft({ ...input, ...next });
    setReloaded(false);
    if (mutation.isSuccess) mutation.reset();
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (input.rating && input.body.trim() && status !== 409 && !mutation.isPending) {
      setReloaded(false);
      mutation.mutate(input);
    }
  }

  if (own.isPending) return <p role="status">{text(locale, 'در حال دریافت دیدگاه شما…', 'Loading your review…')}</p>;
  if (status === 401) return <Link className="button secondary review-open-editor" href={`/${locale}/login?next=review&product=${encodeURIComponent(slug)}`}>{text(locale, 'برای نوشتن دیدگاه وارد شوید', 'Sign in to write a review')}</Link>;
  if (own.isError) return <><ReviewProblem locale={locale} error={own.error}/><button className="button secondary" onClick={() => void reload()}>{text(locale, 'تلاش مجدد', 'Retry')}</button></>;

  return <form className="review-editor" onSubmit={submit}>
    <h3>{text(locale, 'دیدگاه شما', 'Your review')}</h3>
    {review && <div className="review-meta"><span>{reviewStatus(locale, review.status)}</span>{review.verified_purchase && <VerifiedPurchase locale={locale}/>}</div>}
    {review?.moderation_reason && <p className="review-body" dir="auto">{text(locale, 'دلیل بررسی: ', 'Moderation reason: ')}<bdi>{review.moderation_reason}</bdi></p>}
    <fieldset disabled={mutation.isPending}>
      <legend>{text(locale, 'امتیاز', 'Rating')}</legend>
      <div className="review-options">{[1, 2, 3, 4, 5].map(value => <label key={value}>
        <input type="radio" name="review-rating" value={value} checked={input.rating === value} onChange={() => change({ rating: value })} required/>
        <span>{new Intl.NumberFormat(locale).format(value)}</span>
      </label>)}</div>
    </fieldset>
    <label className="field">{text(locale, 'متن دیدگاه', 'Review text')}
      <textarea dir="auto" rows={4} value={input.body} onChange={event => change({ body: event.target.value })} required maxLength={2000} disabled={mutation.isPending}/>
    </label>
    {mutation.isSuccess && <p role="status">{mutation.data.status === 'pending'
      ? text(locale, 'دیدگاه برای بررسی ثبت شد.', 'Review submitted for moderation.') : text(locale, 'دیدگاه ذخیره شد.', 'Review saved.')}</p>}
    {reloaded && <p role="status">{text(locale, 'نسخهٔ فعلی بارگیری شد و متن شما حفظ شد.', 'The current version is loaded and your draft was kept.')}</p>}
    {mutation.isError && <ReviewProblem locale={locale} error={error}/>}
    {status === 409 && <button type="button" className="button secondary" onClick={() => void reload()}>{text(locale, 'بارگیری نسخهٔ فعلی', 'Reload current review')}</button>}
    <button className="button primary" disabled={mutation.isPending || own.isFetching || status === 409}>{text(locale, 'ثبت دیدگاه', 'Submit review')}</button>
  </form>;
}
