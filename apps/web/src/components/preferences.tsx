'use client';

import { createContext, useContext, useState, type ReactNode } from 'react';
import type { Market, Theme } from '@/lib/content';

type Preferences = { market: Market; theme: Theme; setMarket: (market: Market) => void; setTheme: (theme: Theme) => void };
const Context = createContext<Preferences | null>(null);

export function PreferencesProvider({ children, initialMarket, initialTheme }: { children: ReactNode; initialMarket: Market; initialTheme: Theme }) {
  const [market, updateMarket] = useState(initialMarket);
  const [theme, updateTheme] = useState(initialTheme);
  const setMarket = (value: Market) => {
    updateMarket(value);
    document.cookie = `nivaro-market=${value}; Path=/; Max-Age=31536000; SameSite=Lax`;
  };
  const setTheme = (value: Theme) => {
    updateTheme(value);
    document.documentElement.dataset.theme = value;
    document.cookie = `nivaro-theme=${value}; Path=/; Max-Age=31536000; SameSite=Lax`;
  };
  return <Context value={{ market, theme, setMarket, setTheme }}>{children}</Context>;
}

export function usePreferences() {
  const value = useContext(Context);
  if (!value) throw new Error('PreferencesProvider is required');
  return value;
}
