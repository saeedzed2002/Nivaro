'use client';

import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { useEffect, useState, type ReactNode } from 'react';
import { readCart } from '@/lib/cart-client';
import type { Market } from '@/lib/content';

export const cartKey = (market: Market) => ['cart', market] as const;
export const buildsKey = (market: Market) => ['builds', market] as const;

export function useCart(market: Market) {
  return useQuery({ queryKey: cartKey(market), queryFn: ({ signal }) => readCart(market, signal), staleTime: 15_000 });
}

export function CartQueryProvider({ children }: { children: ReactNode }) {
  const [client] = useState(() => new QueryClient({ defaultOptions: { queries: { retry: false } } }));
  useEffect(() => {
    const reset = () => {
      void client.resetQueries({ queryKey: ['cart'] });
      void client.resetQueries({ queryKey: ['builds'] });
    };
    const storage = (event: StorageEvent) => { if (event.key === 'nivaro-customer-session') reset(); };
    window.addEventListener('nivaro-customer-session', reset);
    window.addEventListener('storage', storage);
    return () => {
      window.removeEventListener('nivaro-customer-session', reset);
      window.removeEventListener('storage', storage);
    };
  }, [client]);
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
