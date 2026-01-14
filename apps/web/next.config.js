/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  transpilePackages: ['@iudex/shared'],
  env: {
    // Important: keep this empty by default so the frontend uses same-origin `/api`
    // (via the rewrite below). This avoids CORS/cookie issues in dev.
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || '',
  },
  // NOTE: We proxy `/api/*` via `src/app/api/[...path]/route.ts` to preserve headers
  // and avoid cross-origin redirects. No rewrite needed.
  experimental: {
    serverActions: {
      allowedOrigins: ['localhost:3000', 'localhost:8000', '127.0.0.1:3000', '127.0.0.1:8000'],
    },
  },
};

module.exports = nextConfig;

