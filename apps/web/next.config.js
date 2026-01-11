/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  transpilePackages: ['@iudex/shared'],
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api',
  },
  async rewrites() {
    // Dev/prod-friendly proxy: allows the browser to call same-origin /api/*
    // while Next routes it to the real backend.
    const target = process.env.API_PROXY_TARGET || 'http://localhost:8000';
    return [
      {
        source: '/api/:path*',
        destination: `${target}/api/:path*`,
      },
    ];
  },
  experimental: {
    serverActions: {
      allowedOrigins: ['localhost:3000', 'localhost:8000', '127.0.0.1:3000', '127.0.0.1:8000'],
    },
  },
};

module.exports = nextConfig;

