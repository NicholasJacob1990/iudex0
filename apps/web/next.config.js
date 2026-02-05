const fs = require('fs');
const path = require('path');

class FixServerChunkRuntimePathPlugin {
  apply(compiler) {
    compiler.hooks.afterEmit.tap('FixServerChunkRuntimePathPlugin', () => {
      const outputPath = compiler.options?.output?.path;
      if (!outputPath) return;

      const runtimePath = path.join(outputPath, 'webpack-runtime.js');
      if (!fs.existsSync(runtimePath)) return;

      const source = fs.readFileSync(runtimePath, 'utf8');
      const patched = source.replace(
        /return\s+(?:(?:"chunks\/"\s*\+\s*)|(?:""\s*\+\s*))?chunkId\s*\+\s*["']\.js["']\s*;?/g,
        'return (typeof chunkId === "string" ? "" : "chunks/") + chunkId + ".js";'
      );

      if (patched !== source) {
        fs.writeFileSync(runtimePath, patched, 'utf8');
      }
    });
  }
}

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  transpilePackages: ['@iudex/shared'],

  // Cache headers e security headers
  async headers() {
    const isProd = process.env.NODE_ENV === 'production';
    const securityHeaders = [
      { key: 'X-Content-Type-Options', value: 'nosniff' },
      { key: 'X-Frame-Options', value: 'DENY' },
      { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
    ];

    return [
      // Static assets (hashed by Next.js — immutable)
      {
        source: '/_next/static/:path*',
        headers: [
          ...securityHeaders,
          // In dev, aggressive caching breaks HMR and can leave the UI unstyled.
          { key: 'Cache-Control', value: isProd ? 'public, max-age=31536000, immutable' : 'no-store, must-revalidate' },
        ],
      },
      // Images
      {
        source: '/images/:path*',
        headers: [
          ...securityHeaders,
          { key: 'Cache-Control', value: isProd ? 'public, max-age=86400, stale-while-revalidate=604800' : 'no-store, must-revalidate' },
        ],
      },
      // Logos
      {
        source: '/logos/:path*',
        headers: [
          ...securityHeaders,
          { key: 'Cache-Control', value: isProd ? 'public, max-age=86400, stale-while-revalidate=604800' : 'no-store, must-revalidate' },
        ],
      },
      // Fonts
      {
        source: '/fonts/:path*',
        headers: [
          ...securityHeaders,
          { key: 'Cache-Control', value: isProd ? 'public, max-age=31536000, immutable' : 'no-store, must-revalidate' },
        ],
      },
      // Service Worker — must not be cached long-term
      {
        source: '/sw.js',
        headers: [
          { key: 'Cache-Control', value: 'public, max-age=0, must-revalidate' },
          { key: 'Service-Worker-Allowed', value: '/' },
        ],
      },
      // Manifest
      {
        source: '/manifest.json',
        headers: [
          { key: 'Cache-Control', value: 'public, max-age=86400' },
        ],
      },
      // All other pages — security headers only
      {
        source: '/:path*',
        headers: securityHeaders,
      },
    ];
  },
  webpack: (config, { isServer }) => {
    // In some dev builds, Next/webpack can emit server chunks to
    // `.next/server/chunks/*` but generate a runtime that tries to `require`
    // them from `.next/server/*`, causing "Cannot find module './<id>.js'".
    // Patch the runtime so numeric chunk ids resolve under `chunks/`.
    if (isServer) {
      config.plugins.push(new FixServerChunkRuntimePathPlugin());
    }

    return config;
  },
  eslint: {
    // We run `npm run lint` in CI/dev; Next's built-in lint runner is not compatible
    // with ESLint 9 flat config options in this repo.
    ignoreDuringBuilds: true,
  },
  env: {
    // Important: keep this empty by default so the frontend uses same-origin `/api`
    // (via the rewrite below). This avoids CORS/cookie issues in dev.
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || '',
  },
  // NOTE: We proxy `/api/*` via `src/app/api/[...path]/route.ts` to preserve headers
  // and avoid cross-origin redirects. No rewrite needed.
  experimental: {
    serverActions: {
      // Include common dev ports so we can switch origins to bypass SW/caches.
      allowedOrigins: [
        'localhost:3000',
        '127.0.0.1:3000',
        'localhost:3001',
        '127.0.0.1:3001',
        'localhost:3010',
        '127.0.0.1:3010',
        'localhost:8000',
        '127.0.0.1:8000',
      ],
    },
  },
};

module.exports = nextConfig;
