/**
 * Preload script - Bridge entre main e renderer
 */

import { contextBridge, ipcRenderer } from 'electron';

// API exposta para o renderer
const api = {
  // Configurações
  getConfig: () => ipcRenderer.invoke('get-config'),
  setConfig: (key: string, value: unknown) => ipcRenderer.invoke('set-config', key, value),

  // Conexão
  connect: (serverUrl?: string) => ipcRenderer.invoke('connect', serverUrl),
  disconnect: () => ipcRenderer.invoke('disconnect'),
  getConnectionStatus: () => ipcRenderer.invoke('get-connection-status'),

  // Certificados
  listCertificates: () => ipcRenderer.invoke('list-certificates'),
  getCertificateInfo: (certId: string) => ipcRenderer.invoke('get-certificate-info', certId),
  selectCertificateFile: () => ipcRenderer.invoke('select-certificate-file'),

  // Operações
  approveOperation: (operationId: string, approved: boolean) =>
    ipcRenderer.invoke('approve-operation', operationId, approved),

  executeSignature: (data: {
    operationId: string;
    certificateId: string;
    pin: string;
    dataToSign: string;
  }) => ipcRenderer.invoke('execute-signature', data),

  // CAPTCHA
  solveCaptcha: (data: {
    captchaId: string;
    jobId: string;
    success: boolean;
    solution?: { token?: string; text?: string };
    error?: string;
  }) => ipcRenderer.invoke('solve-captcha', data),

  // Shell
  openExternal: (url: string) => ipcRenderer.invoke('open-external', url),

  // Eventos
  on: (channel: string, callback: (...args: unknown[]) => void) => {
    const validChannels = [
      'ws-status',
      'ws-error',
      'operation-request',
      'signature-request',
      'captcha-request',
      'browser-action',
      'auto-connect',
    ];

    if (validChannels.includes(channel)) {
      ipcRenderer.on(channel, (_event, ...args) => callback(...args));
    }
  },

  off: (channel: string) => {
    ipcRenderer.removeAllListeners(channel);
  },
};

// Expor API para window.api
contextBridge.exposeInMainWorld('api', api);

// Tipos para TypeScript no renderer
export type ElectronAPI = typeof api;
