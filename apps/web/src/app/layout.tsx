import type { Metadata } from 'next';
import { Inter, Outfit } from 'next/font/google';
import Script from 'next/script';
import { Providers } from '@/components/providers';
import '@/styles/globals.css';

const inter = Inter({ subsets: ['latin'], variable: '--font-sans' });
const outfit = Outfit({ subsets: ['latin'], variable: '--font-display' });

export const metadata: Metadata = {
  title: 'Iudex - IA Jurídica Avançada',
  description: 'Plataforma de geração de documentos jurídicos com IA multi-agente',
  icons: {
    icon: '/icon.svg',
    apple: '/icon.svg',
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const isProd = process.env.NODE_ENV === 'production';
  return (
    <html lang="pt-BR" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        {/* eslint-disable-next-line @next/next/no-page-custom-font */}
        <link href="https://fonts.googleapis.com/css2?family=Google+Sans+Flex:wght@100..900&display=swap" rel="stylesheet" />
        <link rel="manifest" href="/manifest.json" />
        <meta name="theme-color" content="#0a0a0a" />
      </head>
      <body className={`${inter.variable} ${outfit.variable} font-google-sans`}>
        {!isProd && (
          <Script
            id="dev-sw-cleanup"
            strategy="beforeInteractive"
            dangerouslySetInnerHTML={{
              __html: `
(function () {
  try {
    // In dev, always remove Service Workers and caches to avoid stale UI/assets
    // (especially when a SW was registered previously and started intercepting _next assets).
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.getRegistrations().then(function (regs) {
        regs.forEach(function (r) { try { r.unregister(); } catch (e) {} });
      }).catch(function () {});
    }

    if ('caches' in window) {
      caches.keys().then(function (keys) {
        return Promise.all(keys.map(function (k) {
          if (/^iudex-/i.test(k) || /workbox|next-static/i.test(k)) return caches.delete(k);
          return Promise.resolve(false);
        }));
      }).catch(function () {});
    }
  } catch (e) {}
})();`,
            }}
          />
        )}
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
