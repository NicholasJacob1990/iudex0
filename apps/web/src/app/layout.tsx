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
        {!isProd && (
          <script
            dangerouslySetInnerHTML={{
              __html: `
(function () {
  try {
    var KEY = '__iudex_runtime_call_fix__';
    var CHUNK_KEY = '__iudex_chunk_reload_once__';
    var buildReturnTo = function () {
      return window.location.pathname + window.location.search + window.location.hash;
    };
    var redirectToReset = function () {
      var returnTo = buildReturnTo();
      window.location.replace('/dev-reset.html?auto=1&returnTo=' + encodeURIComponent(returnTo));
    };
    var isChunkLoadMessage = function (value) {
      var text = String(value || '');
      return /ChunkLoadError|Loading chunk .* failed/i.test(text);
    };
    var handleChunkFailure = function () {
      if (!sessionStorage.getItem(CHUNK_KEY)) {
        sessionStorage.setItem(CHUNK_KEY, '1');
        var retryUrl = new URL(window.location.href);
        retryUrl.searchParams.set('__chunk_retry', String(Date.now()));
        window.location.replace(retryUrl.toString());
        return;
      }
      redirectToReset();
    };

    window.addEventListener('error', function (event) {
      var message = String((event && event.message) || '');
      var filename = String((event && event.filename) || '');
      var eventError = event && event.error ? String(event.error.message || event.error.name || '') : '';
      var target = event && event.target;
      var chunkScriptLoadError =
        !!target &&
        target.tagName === 'SCRIPT' &&
        typeof target.src === 'string' &&
        target.src.indexOf('/_next/static/chunks/') >= 0;
      var isChunkError =
        chunkScriptLoadError ||
        isChunkLoadMessage(message) ||
        isChunkLoadMessage(eventError);
      var isWebpackCallError =
        message.indexOf("Cannot read properties of undefined (reading 'call')") >= 0 &&
        filename.indexOf('/_next/static/chunks/webpack.js') >= 0;

      if (isChunkError) {
        handleChunkFailure();
        return;
      }
      if (!isWebpackCallError) return;
      if (sessionStorage.getItem(KEY)) return;
      sessionStorage.setItem(KEY, '1');
      redirectToReset();
    }, true);

    window.addEventListener('unhandledrejection', function (event) {
      var reason = event && event.reason;
      var reasonText = String(
        (reason && (reason.message || reason.name)) || reason || ''
      );
      if (isChunkLoadMessage(reasonText)) {
        handleChunkFailure();
      }
    }, true);
  } catch (_) {}
})();`,
            }}
          />
        )}
        {/* react-grab disabled — was causing webpack hydration error in dev
        {process.env.NODE_ENV === 'development' && (
          <Script
            src="//unpkg.com/react-grab/dist/index.global.js"
            crossOrigin="anonymous"
            strategy="beforeInteractive"
          />
        )} */}
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
    var SW_RESET_KEY = '__iudex_dev_sw_reset_once__';
    var shouldForceReload = false;

    // In dev, always remove Service Workers and caches to avoid stale UI/assets
    // (especially when a SW was registered previously and started intercepting _next assets).
    if ('serviceWorker' in navigator) {
      var hadController = !!navigator.serviceWorker.controller;
      navigator.serviceWorker.getRegistrations().then(function (regs) {
        if (regs.length > 0) shouldForceReload = shouldForceReload || hadController;
        regs.forEach(function (r) { try { r.unregister(); } catch (e) {} });
      }).then(function () {
        if (shouldForceReload && !sessionStorage.getItem(SW_RESET_KEY)) {
          sessionStorage.setItem(SW_RESET_KEY, '1');
          window.location.reload();
        }
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
