import type { NextConfig } from 'next';

const config: NextConfig = {
  output: 'standalone',
  poweredByHeader: false,
  allowedDevOrigins: ['127.0.0.1'],
  images: { formats: ['image/avif', 'image/webp'] },
  async rewrites() {
    return [{ source: '/api/v1/catalog/:path*', destination: `${process.env.CATALOG_URL || 'http://catalog:8000'}/api/v1/catalog/:path*` }];
  },
};
export default config;
