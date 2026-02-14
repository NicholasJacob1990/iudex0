/**
 * Configuracao MSAL para autenticacao Microsoft SSO no Outlook Add-in.
 *
 * Usa Nested App Authentication (NAA) quando disponivel (Office host),
 * com fallback para PublicClientApplication com popup.
 */

import {
  type IPublicClientApplication,
  type AccountInfo,
  type AuthenticationResult,
  PublicClientApplication,
  InteractionRequiredAuthError,
} from '@azure/msal-browser';

const AZURE_CLIENT_ID = import.meta.env.VITE_AZURE_CLIENT_ID || '';

const isDev = import.meta.env.DEV;

const redirectUri = isDev
  ? 'https://localhost:3200'
  : import.meta.env.VITE_REDIRECT_URI || 'https://app.vorbium.com.br';

const msalConfig = {
  auth: {
    clientId: AZURE_CLIENT_ID,
    authority: 'https://login.microsoftonline.com/common',
    redirectUri,
  },
  cache: {
    cacheLocation: 'localStorage' as const,
  },
};

const loginScopes = ['User.Read', 'Mail.Read', 'Calendars.ReadWrite'];

let msalInstance: IPublicClientApplication | null = null;
let isNAA = false;

/**
 * Inicializa MSAL usando NAA (Nested App Authentication) quando disponivel,
 * com fallback para PublicClientApplication.
 */
export async function initializeMsal(): Promise<IPublicClientApplication> {
  if (msalInstance) return msalInstance;

  // Tenta NAA primeiro (disponivel dentro do Office host)
  try {
    const mod = await import('@azure/msal-browser') as Record<string, unknown>;
    const createNAA = mod.createNestablePublicClientApplication as
      | ((config: typeof msalConfig) => Promise<IPublicClientApplication>)
      | undefined;
    if (typeof createNAA === 'function') {
      msalInstance = await createNAA(msalConfig);
      isNAA = true;
      console.info('[MSAL] Inicializado via NAA (Nested App Authentication)');
      return msalInstance;
    }
  } catch {
    console.info('[MSAL] NAA nao disponivel, usando fallback PCA');
  }

  // Fallback: PublicClientApplication com popup
  const pca = new PublicClientApplication(msalConfig);
  await pca.initialize();
  msalInstance = pca;
  isNAA = false;
  console.info('[MSAL] Inicializado via PublicClientApplication (popup)');
  return msalInstance;
}

/**
 * Adquire token silenciosamente ou via interacao (popup).
 * Retorna o access_token da Microsoft para enviar ao backend.
 */
export async function acquireToken(): Promise<AuthenticationResult> {
  const msal = await initializeMsal();

  const accounts: AccountInfo[] = msal.getAllAccounts();
  const account = accounts[0] || undefined;

  const silentRequest = {
    scopes: loginScopes,
    account,
  };

  // Tenta aquisicao silenciosa primeiro
  if (account) {
    try {
      const result = await msal.acquireTokenSilent(silentRequest);
      return result;
    } catch (error) {
      if (!(error instanceof InteractionRequiredAuthError)) {
        throw error;
      }
      // Interacao necessaria, continua para popup/redirect
    }
  }

  // NAA usa ssoSilent antes de popup
  if (isNAA) {
    try {
      const result = await msal.ssoSilent({ scopes: loginScopes });
      return result;
    } catch {
      // Continua para popup
    }
  }

  // Popup como ultimo recurso
  const result = await msal.acquireTokenPopup({ scopes: loginScopes });
  return result;
}

/**
 * Faz logout da conta Microsoft.
 */
export async function msalLogout(): Promise<void> {
  if (!msalInstance) return;

  const accounts = msalInstance.getAllAccounts();
  if (accounts.length > 0) {
    try {
      await msalInstance.logoutPopup({
        account: accounts[0],
      });
    } catch {
      // Logout silencioso se popup falhar
      msalInstance.setActiveAccount(null);
    }
  }
}

export { loginScopes, isNAA };
