/**
 * Iudex Tribunais Desktop
 *
 * App Electron para assinatura com certificado A3 físico (token USB)
 *
 * Funcionalidades:
 * - Conecta ao servidor Iudex via WebSocket
 * - Detecta certificados no sistema (tokens USB)
 * - Executa assinaturas quando solicitado
 * - Interface para aprovar operações
 */

import { app, BrowserWindow, ipcMain, dialog, Tray, Menu, nativeImage, Notification, shell } from 'electron';
import { electronApp, optimizer, is } from '@electron-toolkit/utils';
import { join } from 'path';
import Store from 'electron-store';
import { WebSocketClient } from './websocket-client';
import { CertificateManager } from './certificate-manager';

// Store para configurações persistentes
const store = new Store({
  defaults: {
    serverUrl: 'ws://localhost:3101',
    autoConnect: true,
    minimizeToTray: true,
    userId: '',
  },
});

let mainWindow: BrowserWindow | null = null;
let tray: Tray | null = null;
let wsClient: WebSocketClient | null = null;
let certManager: CertificateManager | null = null;

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 480,
    height: 640,
    minWidth: 400,
    minHeight: 500,
    show: false,
    autoHideMenuBar: true,
    frame: true,
    titleBarStyle: 'hiddenInset',
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false,
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.on('ready-to-show', () => {
    mainWindow?.show();
  });

  mainWindow.on('close', (event) => {
    if (store.get('minimizeToTray') && !app.isQuitting) {
      event.preventDefault();
      mainWindow?.hide();
    }
  });

  // Carregar UI
  if (is.dev && process.env['ELECTRON_RENDERER_URL']) {
    mainWindow.loadURL(process.env['ELECTRON_RENDERER_URL']);
  } else {
    mainWindow.loadFile(join(__dirname, '../renderer/index.html'));
  }
}

function createTray(): void {
  const icon = nativeImage.createFromDataURL(
    'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
  );

  tray = new Tray(icon);

  const contextMenu = Menu.buildFromTemplate([
    {
      label: 'Abrir Iudex Tribunais',
      click: () => mainWindow?.show(),
    },
    {
      label: 'Status',
      enabled: false,
      id: 'status',
    },
    { type: 'separator' },
    {
      label: 'Reconectar',
      click: () => wsClient?.reconnect(),
    },
    { type: 'separator' },
    {
      label: 'Sair',
      click: () => {
        app.isQuitting = true;
        app.quit();
      },
    },
  ]);

  tray.setToolTip('Iudex Tribunais');
  tray.setContextMenu(contextMenu);

  tray.on('click', () => {
    mainWindow?.show();
  });
}

function updateTrayStatus(connected: boolean): void {
  if (!tray) return;

  const menu = tray.getContextMenu();
  const statusItem = menu?.getMenuItemById('status');
  if (statusItem) {
    statusItem.label = connected ? 'Conectado' : 'Desconectado';
  }

  tray.setToolTip(`Iudex Tribunais - ${connected ? 'Conectado' : 'Desconectado'}`);
}

function showNotification(title: string, body: string): void {
  new Notification({ title, body }).show();
}

// =============================================
// IPC Handlers
// =============================================

function setupIpcHandlers(): void {
  // Configurações
  ipcMain.handle('get-config', () => {
    return store.store;
  });

  ipcMain.handle('set-config', (_event, key: string, value: unknown) => {
    store.set(key, value);
    return true;
  });

  // Conexão WebSocket
  ipcMain.handle('connect', async (_event, serverUrl?: string) => {
    const url = serverUrl || store.get('serverUrl');
    const userId = store.get('userId');

    if (!userId) {
      return { success: false, error: 'userId não configurado' };
    }

    try {
      if (wsClient) {
        wsClient.disconnect();
      }

      wsClient = new WebSocketClient(url as string, userId as string);

      wsClient.on('connected', () => {
        mainWindow?.webContents.send('ws-status', 'connected');
        updateTrayStatus(true);
      });

      wsClient.on('disconnected', () => {
        mainWindow?.webContents.send('ws-status', 'disconnected');
        updateTrayStatus(false);
      });

      wsClient.on('error', (error) => {
        mainWindow?.webContents.send('ws-error', error);
      });

      wsClient.on('operation', async (data) => {
        mainWindow?.webContents.send('operation-request', data);
        showNotification('Operação Solicitada', data.message || 'Aprove a operação');
        mainWindow?.show();
      });

      wsClient.on('signature-required', async (data) => {
        mainWindow?.webContents.send('signature-request', data);
        showNotification('Assinatura Necessária', 'Insira o PIN do token para assinar');
        mainWindow?.show();
      });

      wsClient.on('captcha-required', async (data) => {
        mainWindow?.webContents.send('captcha-request', data);
        const captchaTypeLabels: Record<string, string> = {
          'image': 'CAPTCHA de Imagem',
          'recaptcha_v2': 'reCAPTCHA',
          'recaptcha_v3': 'reCAPTCHA v3',
          'hcaptcha': 'hCaptcha',
          'unknown': 'CAPTCHA'
        };
        const captchaType = data.captcha?.type || 'unknown';
        showNotification(
          captchaTypeLabels[captchaType] || 'CAPTCHA Necessário',
          `${data.tribunal || 'Tribunal'}: Resolva o CAPTCHA para continuar`
        );
        mainWindow?.show();
      });

      await wsClient.connect();
      return { success: true };
    } catch (error) {
      return { success: false, error: String(error) };
    }
  });

  ipcMain.handle('disconnect', () => {
    wsClient?.disconnect();
    return { success: true };
  });

  ipcMain.handle('get-connection-status', () => {
    return wsClient?.isConnected() || false;
  });

  // Certificados
  ipcMain.handle('list-certificates', async () => {
    if (!certManager) {
      certManager = new CertificateManager();
    }
    return await certManager.listCertificates();
  });

  ipcMain.handle('get-certificate-info', async (_event, certId: string) => {
    if (!certManager) {
      certManager = new CertificateManager();
    }
    return await certManager.getCertificateInfo(certId);
  });

  // Operações
  ipcMain.handle('approve-operation', async (_event, operationId: string, approved: boolean) => {
    if (!wsClient) {
      return { success: false, error: 'Não conectado' };
    }

    wsClient.sendResponse(operationId, approved ? 'approved' : 'rejected');
    return { success: true };
  });

  ipcMain.handle('execute-signature', async (_event, data: {
    operationId: string;
    certificateId: string;
    pin: string;
    dataToSign: string;
  }) => {
    if (!certManager) {
      certManager = new CertificateManager();
    }

    try {
      const signature = await certManager.sign(
        data.certificateId,
        data.pin,
        Buffer.from(data.dataToSign, 'base64')
      );

      wsClient?.sendResponse(data.operationId, 'signed', {
        signature: signature.toString('base64'),
      });

      return { success: true, signature: signature.toString('base64') };
    } catch (error) {
      wsClient?.sendResponse(data.operationId, 'error', {
        error: String(error),
      });
      return { success: false, error: String(error) };
    }
  });

  // Dialog para selecionar certificado
  ipcMain.handle('select-certificate-file', async () => {
    const result = await dialog.showOpenDialog(mainWindow!, {
      title: 'Selecionar Certificado',
      filters: [
        { name: 'Certificados', extensions: ['pfx', 'p12'] },
      ],
      properties: ['openFile'],
    });

    if (result.canceled) {
      return null;
    }

    return result.filePaths[0];
  });

  // CAPTCHA
  ipcMain.handle('solve-captcha', async (_event, data: {
    captchaId: string;
    jobId: string;
    success: boolean;
    solution?: { token?: string; text?: string };
    error?: string;
  }) => {
    if (!wsClient) {
      return { success: false, error: 'Não conectado' };
    }

    wsClient.sendCaptchaSolution(
      data.captchaId,
      data.jobId,
      data.success,
      data.solution,
      data.error
    );

    return { success: true };
  });

  // Shell - abrir URL externa
  ipcMain.handle('open-external', async (_event, url: string) => {
    await shell.openExternal(url);
    return { success: true };
  });
}

// =============================================
// App Lifecycle
// =============================================

app.whenReady().then(() => {
  electronApp.setAppUserModelId('com.iudex.tribunais-desktop');

  app.on('browser-window-created', (_, window) => {
    optimizer.watchWindowShortcuts(window);
  });

  createWindow();
  createTray();
  setupIpcHandlers();

  // Auto-conectar se configurado
  if (store.get('autoConnect') && store.get('userId')) {
    setTimeout(() => {
      mainWindow?.webContents.send('auto-connect');
    }, 1000);
  }

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    } else {
      mainWindow?.show();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', () => {
  app.isQuitting = true;
  wsClient?.disconnect();
});

// Declaração para TypeScript
declare module 'electron' {
  interface App {
    isQuitting?: boolean;
  }
}
