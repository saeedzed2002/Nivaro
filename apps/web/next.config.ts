import type { NextConfig } from 'next';

const config: NextConfig = {
  output: 'standalone',
  poweredByHeader: false,
  allowedDevOrigins: ['127.0.0.1'],
  images: { formats: ['image/avif', 'image/webp'] },
  async rewrites() {
    const gateway = process.env.NIVARO_WEB_PREVIEW_GATEWAY;
    const catalog = process.env.CATALOG_URL || 'http://catalog:8000';
    const rewrites = [{ source: '/api/v1/catalog/:path*', destination: `${catalog}/api/v1/catalog/:path*` }];
    if (gateway) {
      for (const resource of ['auth', 'cart', 'builds']) {
        const source = `/api/v1/${resource}/:path*`;
        rewrites.push({ source, destination: gateway + source });
      }
    }
    return rewrites;
  },
};
export default config;
