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
        /return\\s+\"\"\\s*\\+\\s*chunkId\\s*\\+\\s*\"\\.js\";/g,
        'return \"chunks/\" + chunkId + \".js\";'
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
  webpack: (config, { isServer }) => {
    // In some dev builds, Next/webpack can emit server chunks to
    // `.next/server/chunks/*` but generate a runtime that tries to `require`
    // them from `.next/server/*`, causing "Cannot find module './<id>.js'".
    // Force a consistent server chunk path.
    if (isServer) {
      config.output.chunkFilename = 'chunks/[id].js';
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
      allowedOrigins: ['localhost:3000', 'localhost:8000', '127.0.0.1:3000', '127.0.0.1:8000'],
    },
  },
};

module.exports = nextConfig;
