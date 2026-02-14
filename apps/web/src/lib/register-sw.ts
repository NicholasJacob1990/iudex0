/**
 * Service Worker registration helper.
 *
 * Registra o SW apenas em produção (ou quando forçado via env).
 * Exibe toast via sonner quando uma nova versão está disponível.
 */

import { toast } from 'sonner';

const SW_URL = '/sw.js';
const SW_SCOPE = '/';

function shouldDeleteCacheKey(cacheKey: string): boolean {
  return (
    /^iudex-/i.test(cacheKey) ||
    /workbox/i.test(cacheKey) ||
    /next-static/i.test(cacheKey)
  );
}

async function cleanupServiceWorkersAndCaches(): Promise<void> {
  if (!('serviceWorker' in navigator)) return;

  try {
    const registrations = await navigator.serviceWorker.getRegistrations();
    await Promise.all(registrations.map((r) => r.unregister().catch(() => false)));
  } catch (err) {
    console.warn('[SW] Falha ao listar/remover registrations:', err);
  }

  // Limpar caches do service worker (mesmo sem registration ativa)
  try {
    if ('caches' in window) {
      const keys = await caches.keys();
      await Promise.all(keys.filter(shouldDeleteCacheKey).map((k) => caches.delete(k)));
    }
  } catch (err) {
    console.warn('[SW] Falha ao limpar caches:', err);
  }
}

/**
 * Registra o service worker.
 * Chamar uma vez no mount do app (ex: layout ou provider).
 */
export async function registerServiceWorker(): Promise<void> {
  if (!('serviceWorker' in navigator)) return;

  // Só registrar em produção, a menos que explicitamente habilitado
  const isDev = process.env.NODE_ENV === 'development';
  const forceInDev = process.env.NEXT_PUBLIC_SW_DEV === 'true';
  const devResetKey = '__iudex_dev_sw_reset_once__';
  const isLocalhost =
    typeof window !== 'undefined' &&
    /^(localhost|127\\.0\\.0\\.1)$/i.test(window.location.hostname);
  if (isDev && !forceInDev) {
    const shouldForceReload =
      typeof window !== 'undefined' &&
      !!navigator.serviceWorker.controller &&
      !sessionStorage.getItem(devResetKey);
    // Em dev, SW antigo pode ficar “preso” no browser e quebrar CSS/JS (cache-first).
    await cleanupServiceWorkersAndCaches();
    if (shouldForceReload) {
      sessionStorage.setItem(devResetKey, '1');
      window.location.reload();
    }
    return;
  }
  // Mesmo em produção, nunca registrar SW em localhost (evita cache preso durante testes com `next start`).
  if (isLocalhost) {
    await cleanupServiceWorkersAndCaches();
    return;
  }

  try {
    const registration = await navigator.serviceWorker.register(SW_URL, {
      scope: SW_SCOPE,
    });

    // Verificar atualizações periodicamente (a cada 60 min)
    setInterval(() => {
      registration.update().catch(() => {});
    }, 60 * 60 * 1000);

    // Detectar nova versão instalando
    registration.addEventListener('updatefound', () => {
      const newWorker = registration.installing;
      if (!newWorker) return;

      newWorker.addEventListener('statechange', () => {
        if (
          newWorker.state === 'installed' &&
          navigator.serviceWorker.controller
        ) {
          // Nova versão pronta — notificar o usuário
          toast('Nova versão disponível', {
            description: 'Recarregue a página para atualizar.',
            action: {
              label: 'Atualizar',
              onClick: () => {
                newWorker.postMessage('skipWaiting');
                window.location.reload();
              },
            },
            duration: Infinity,
          });
        }
      });
    });
  } catch (err) {
    console.warn('[SW] Falha ao registrar service worker:', err);
  }
}

/**
 * Remove o service worker e limpa caches.
 * Chamar no logout, por exemplo.
 */
export async function unregisterServiceWorker(): Promise<void> {
  await cleanupServiceWorkersAndCaches();
}
