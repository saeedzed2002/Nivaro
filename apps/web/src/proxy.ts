import { NextResponse, type NextRequest } from 'next/server';

export function proxy(request: NextRequest) {
  if (request.nextUrl.pathname === '/') return NextResponse.redirect(new URL('/fa', request.url));
  const headers = new Headers(request.headers);
  headers.set('x-nivaro-locale', request.nextUrl.pathname.startsWith('/en') ? 'en' : 'fa');
  return NextResponse.next({ request: { headers } });
}
export const config = { matcher: ['/', '/fa/:path*', '/en/:path*'] };
