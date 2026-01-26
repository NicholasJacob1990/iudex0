/**
 * Iudex Tribunais Extension - Popup Script
 * Interface de configuracao, status e licenciamento
 */

// ===========================================
// Configuration
// ===========================================

const API_BASE_URL = 'https://api.iudex.com.br/api/v1';
const CHECKOUT_URL = 'https://iudex.com.br/checkout';
const PRODUCT_TYPE = 'tribunais-mcp';

// ===========================================
// DOM Elements
// ===========================================

const elements = {
  // Version
  version: document.getElementById('version'),

  // License
  licenseBar: document.getElementById('licenseBar'),
  licenseBadge: document.getElementById('licenseBadge'),
  licenseText: document.getElementById('licenseText'),
  upgradeBtn: document.getElementById('upgradeBtn'),

  // Auth
  authSection: document.getElementById('authSection'),
  loginForm: document.getElementById('loginForm'),
  registerForm: document.getElementById('registerForm'),
  loginEmail: document.getElementById('loginEmail'),
  loginBtn: document.getElementById('loginBtn'),
  registerEmail: document.getElementById('registerEmail'),
  registerName: document.getElementById('registerName'),
  registerBtn: document.getElementById('registerBtn'),
  termsLink: document.getElementById('termsLink'),

  // Main content
  mainContent: document.getElementById('mainContent'),

  // Status
  statusIndicator: document.getElementById('statusIndicator'),
  statusText: document.getElementById('statusText'),
  connectBtn: document.getElementById('connectBtn'),

  // Usage
  usageStats: document.getElementById('usageStats'),
  usedToday: document.getElementById('usedToday'),
  remainingOps: document.getElementById('remainingOps'),
  usageProgressBar: document.getElementById('usageProgressBar'),

  // Config
  serverUrl: document.getElementById('serverUrl'),
  userId: document.getElementById('userId'),
  autoConnect: document.getElementById('autoConnect'),
  saveBtn: document.getElementById('saveBtn'),

  // Operations
  operationsList: document.getElementById('operationsList'),

  // Signature
  signaturePending: document.getElementById('signaturePending'),
  signatureInfo: document.getElementById('signatureInfo'),
  signBtn: document.getElementById('signBtn'),

  // CAPTCHA
  captchaPending: document.getElementById('captchaPending'),
  captchaTitle: document.getElementById('captchaTitle'),
  captchaInfo: document.getElementById('captchaInfo'),
  captchaImageContainer: document.getElementById('captchaImageContainer'),
  captchaImage: document.getElementById('captchaImage'),
  captchaText: document.getElementById('captchaText'),
  captchaRecaptchaContainer: document.getElementById('captchaRecaptchaContainer'),
  openTribunalBtn: document.getElementById('openTribunalBtn'),
  submitCaptchaBtn: document.getElementById('submitCaptchaBtn'),
  cancelCaptchaBtn: document.getElementById('cancelCaptchaBtn'),
  captchaTimer: document.getElementById('captchaTimer'),

  // Plans
  plansSection: document.getElementById('plansSection'),

  // Footer
  manageSubscription: document.getElementById('manageSubscription'),
  logoutLink: document.getElementById('logoutLink'),

  // Toast
  toast: document.getElementById('toast'),
};

// ===========================================
// State
// ===========================================

let state = {
  isLoggedIn: false,
  email: null,
  license: null,
  isConnected: false,
  pendingOperations: [],
  currentCaptcha: null,
  captchaTimerInterval: null,
};

// ===========================================
// Initialization
// ===========================================

document.addEventListener('DOMContentLoaded', async () => {
  // Version
  const manifest = chrome.runtime.getManifest();
  elements.version.textContent = `v${manifest.version}`;

  // Load stored data
  await loadStoredData();

  // Check authentication
  if (state.email) {
    await checkLicense();
    showMainContent();
  } else {
    showAuthSection();
  }

  // Setup event listeners
  setupEventListeners();

  // Load config
  await loadConfig();

  // Refresh status periodically
  setInterval(refreshStatus, 2000);
});

// ===========================================
// Data Loading
// ===========================================

async function loadStoredData() {
  try {
    const data = await chrome.storage.local.get(['licenseEmail', 'license']);
    state.email = data.licenseEmail || null;
    state.license = data.license || null;
  } catch (error) {
    console.error('Error loading stored data:', error);
  }
}

async function loadConfig() {
  try {
    const response = await chrome.runtime.sendMessage({ type: 'get_config' });
    elements.serverUrl.value = response.serverUrl || 'ws://localhost:3101';
    elements.userId.value = response.userId || '';
    elements.autoConnect.checked = response.autoConnect !== false;
  } catch (error) {
    console.error('Error loading config:', error);
  }
}

// ===========================================
// Authentication
// ===========================================

function showAuthSection() {
  elements.authSection.classList.remove('hidden');
  elements.mainContent.style.display = 'none';
  elements.licenseBar.style.display = 'none';
}

function showMainContent() {
  elements.authSection.classList.add('hidden');
  elements.mainContent.style.display = 'block';
  elements.licenseBar.style.display = 'flex';
  refreshStatus();
  checkPendingSignature();
  checkPendingCaptcha();
}

async function handleLogin() {
  const email = elements.loginEmail.value.trim();

  if (!email || !isValidEmail(email)) {
    showToast('Digite um email valido', 'error');
    return;
  }

  elements.loginBtn.disabled = true;
  elements.loginBtn.textContent = 'Verificando...';

  try {
    // Check license
    const response = await fetch(`${API_BASE_URL}/licenses/check`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, product: PRODUCT_TYPE }),
    });

    const result = await response.json();

    if (result.valid || result.can_start_trial) {
      // Save email
      await chrome.storage.local.set({ licenseEmail: email });
      state.email = email;

      if (result.license) {
        state.license = result.license;
        await chrome.storage.local.set({ license: result.license });
      }

      showToast('Login realizado!', 'success');
      await checkLicense();
      showMainContent();
    } else {
      showToast(result.message || 'Licenca nao encontrada', 'error');
    }
  } catch (error) {
    console.error('Login error:', error);
    showToast('Erro ao verificar. Tente novamente.', 'error');
  } finally {
    elements.loginBtn.disabled = false;
    elements.loginBtn.textContent = 'Entrar';
  }
}

async function handleRegister() {
  const email = elements.registerEmail.value.trim();

  if (!email || !isValidEmail(email)) {
    showToast('Digite um email valido', 'error');
    return;
  }

  elements.registerBtn.disabled = true;
  elements.registerBtn.textContent = 'Criando...';

  try {
    // Start trial
    const response = await fetch(`${API_BASE_URL}/licenses/trial/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, product: PRODUCT_TYPE }),
    });

    if (response.ok) {
      const result = await response.json();

      // Save data
      await chrome.storage.local.set({
        licenseEmail: email,
        license: result.license,
      });

      state.email = email;
      state.license = result.license;

      showToast('Teste gratuito iniciado!', 'success');
      await checkLicense();
      showMainContent();
    } else {
      const error = await response.json();
      showToast(error.detail || 'Erro ao criar conta', 'error');
    }
  } catch (error) {
    console.error('Register error:', error);
    showToast('Erro ao criar conta. Tente novamente.', 'error');
  } finally {
    elements.registerBtn.disabled = false;
    elements.registerBtn.textContent = 'Iniciar Teste Gratuito';
  }
}

async function handleLogout() {
  await chrome.storage.local.remove(['licenseEmail', 'license']);
  state.email = null;
  state.license = null;
  state.isLoggedIn = false;

  showToast('Logout realizado', 'info');
  showAuthSection();
}

// ===========================================
// License Management
// ===========================================

async function checkLicense() {
  if (!state.email) return;

  try {
    const response = await fetch(`${API_BASE_URL}/licenses/check`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: state.email, product: PRODUCT_TYPE }),
    });

    const result = await response.json();

    if (result.license) {
      state.license = result.license;
      await chrome.storage.local.set({ license: result.license });
    }

    updateLicenseUI(result);
    await checkUsage();
  } catch (error) {
    console.error('Error checking license:', error);
    // Use cached license if available
    if (state.license) {
      updateLicenseUI({
        valid: state.license.status === 'active' || state.license.status === 'trialing',
        license: state.license,
        plan: state.license.plan,
        message: 'Modo offline',
      });
    }
  }
}

function updateLicenseUI(result) {
  const { valid, license, plan, days_remaining, message } = result;

  // Badge
  elements.licenseBadge.className = 'license-badge';

  if (!license) {
    elements.licenseBadge.classList.add('free');
    elements.licenseBadge.textContent = 'Free';
    elements.licenseText.textContent = 'Inicie seu teste gratuito';
    elements.upgradeBtn.style.display = 'block';
    return;
  }

  switch (license.status) {
    case 'trialing':
      elements.licenseBadge.classList.add('trial');
      elements.licenseBadge.textContent = 'Trial';
      elements.licenseText.textContent = `${days_remaining} dias restantes`;
      elements.upgradeBtn.style.display = 'block';
      break;
    case 'active':
      elements.licenseBadge.classList.add('active');
      elements.licenseBadge.textContent = plan === 'professional' ? 'Pro' : plan === 'office' ? 'Office' : 'Ativo';
      elements.licenseText.textContent = license.cancel_at_period_end
        ? `Cancela em ${days_remaining} dias`
        : 'Licenca ativa';
      elements.upgradeBtn.style.display = plan === 'professional' ? 'block' : 'none';
      elements.upgradeBtn.textContent = plan === 'professional' ? 'Upgrade' : 'Upgrade';
      break;
    case 'past_due':
    case 'unpaid':
      elements.licenseBadge.classList.add('expired');
      elements.licenseBadge.textContent = 'Pendente';
      elements.licenseText.textContent = 'Pagamento pendente';
      elements.upgradeBtn.style.display = 'block';
      elements.upgradeBtn.textContent = 'Regularizar';
      break;
    case 'canceled':
      elements.licenseBadge.classList.add('expired');
      elements.licenseBadge.textContent = 'Cancelado';
      elements.licenseText.textContent = 'Assinatura cancelada';
      elements.upgradeBtn.style.display = 'block';
      elements.upgradeBtn.textContent = 'Reativar';
      break;
    default:
      elements.licenseBadge.classList.add('expired');
      elements.licenseBadge.textContent = 'Expirado';
      elements.licenseText.textContent = message || 'Licenca expirada';
      elements.upgradeBtn.style.display = 'block';
  }
}

async function checkUsage() {
  if (!state.email) return;

  try {
    const response = await fetch(`${API_BASE_URL}/usage/check`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: state.email, product: PRODUCT_TYPE }),
    });

    const result = await response.json();
    updateUsageUI(result);
  } catch (error) {
    console.error('Error checking usage:', error);
  }
}

function updateUsageUI(usage) {
  const { used_today, remaining, limit, unlimited } = usage;

  elements.usedToday.textContent = used_today || 0;

  if (unlimited) {
    elements.remainingOps.textContent = '∞';
    elements.usageProgressBar.style.width = '0%';
    elements.usageProgressBar.className = 'usage-progress-bar';
  } else {
    elements.remainingOps.textContent = remaining || 0;

    const total = limit || 50;
    const percentage = Math.min(100, (used_today / total) * 100);
    elements.usageProgressBar.style.width = `${percentage}%`;

    // Color based on usage
    elements.usageProgressBar.className = 'usage-progress-bar';
    if (percentage >= 90) {
      elements.usageProgressBar.classList.add('danger');
    } else if (percentage >= 70) {
      elements.usageProgressBar.classList.add('warning');
    }

    // Warning class on stat
    if (remaining <= 5 && !unlimited) {
      elements.remainingOps.parentElement.classList.add('warning');
    } else {
      elements.remainingOps.parentElement.classList.remove('warning');
    }
  }
}

// ===========================================
// Checkout & Plans
// ===========================================

function openCheckout(plan, interval) {
  const url = new URL(CHECKOUT_URL);
  url.searchParams.set('product', PRODUCT_TYPE);
  url.searchParams.set('plan', plan);
  url.searchParams.set('interval', interval);
  if (state.email) {
    url.searchParams.set('email', state.email);
  }

  chrome.tabs.create({ url: url.toString() });
}

async function openPortal() {
  if (!state.email) {
    showToast('Faca login primeiro', 'error');
    return;
  }

  try {
    const response = await fetch(`${API_BASE_URL}/portal/create`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: state.email }),
    });

    if (response.ok) {
      const { url } = await response.json();
      chrome.tabs.create({ url });
    } else {
      const error = await response.json();
      showToast(error.detail || 'Erro ao abrir portal', 'error');
    }
  } catch (error) {
    console.error('Portal error:', error);
    showToast('Erro ao abrir portal', 'error');
  }
}

function togglePlansSection() {
  const isVisible = elements.plansSection.classList.contains('visible');
  elements.plansSection.classList.toggle('visible', !isVisible);
}

// ===========================================
// Connection Management
// ===========================================

async function refreshStatus() {
  try {
    const status = await chrome.runtime.sendMessage({ type: 'get_status' });
    state.isConnected = status.isConnected;
    state.pendingOperations = status.pendingOperations || [];
    updateStatusUI(status);
    updateOperationsUI(state.pendingOperations);
  } catch (error) {
    console.error('Error getting status:', error);
  }
}

function updateStatusUI(status) {
  const { isConnected, reconnectAttempts } = status;

  elements.statusIndicator.className = 'status-indicator';

  if (isConnected) {
    elements.statusIndicator.classList.add('connected');
    elements.statusText.textContent = 'Conectado';
    elements.connectBtn.textContent = 'Desconectar';
    elements.connectBtn.className = 'connect-btn disconnect';
  } else if (reconnectAttempts > 0 && reconnectAttempts < 10) {
    elements.statusIndicator.classList.add('connecting');
    elements.statusText.textContent = `Reconectando... (${reconnectAttempts}/10)`;
    elements.connectBtn.textContent = 'Cancelar';
    elements.connectBtn.className = 'connect-btn disconnect';
  } else {
    elements.statusText.textContent = 'Desconectado';
    elements.connectBtn.textContent = 'Conectar';
    elements.connectBtn.className = 'connect-btn connect';
  }

  elements.serverUrl.disabled = isConnected;
  elements.userId.disabled = isConnected;
}

function updateOperationsUI(operations) {
  if (!operations || operations.length === 0) {
    elements.operationsList.innerHTML = '<div class="empty-state">Nenhuma operacao pendente</div>';
    return;
  }

  const html = operations.map(op => {
    const time = new Date(op.timestamp).toLocaleTimeString();
    return `
      <div class="operation-item">
        <span class="action">${formatAction(op.action)}</span>
        <span class="status ${op.status}">${formatStatus(op.status)}</span>
        <div class="time">${time}</div>
      </div>
    `;
  }).join('');

  elements.operationsList.innerHTML = html;
}

function formatAction(action) {
  const actions = {
    'request_interaction': 'Interacao Solicitada',
    'execute_browser_action': 'Acao no Navegador',
    'request_signature': 'Assinatura Digital',
    'ping': 'Ping',
  };
  return actions[action] || action;
}

function formatStatus(status) {
  const statuses = {
    'processing': 'Processando',
    'completed': 'Concluido',
    'failed': 'Falhou',
  };
  return statuses[status] || status;
}

// ===========================================
// Config Management
// ===========================================

async function saveConfig() {
  const config = {
    serverUrl: elements.serverUrl.value.trim(),
    userId: elements.userId.value.trim(),
    autoConnect: elements.autoConnect.checked,
  };

  if (!config.serverUrl) {
    showToast('URL do servidor e obrigatoria', 'error');
    return;
  }

  try {
    elements.saveBtn.disabled = true;
    elements.saveBtn.textContent = 'Salvando...';

    await chrome.runtime.sendMessage({ type: 'save_config', config });

    elements.saveBtn.textContent = 'Salvo!';
    showToast('Configuracao salva', 'success');

    setTimeout(() => {
      elements.saveBtn.textContent = 'Salvar Configuracao';
      elements.saveBtn.disabled = false;
    }, 1500);
  } catch (error) {
    console.error('Save config error:', error);
    showToast('Erro ao salvar', 'error');
    elements.saveBtn.textContent = 'Salvar Configuracao';
    elements.saveBtn.disabled = false;
  }
}

// ===========================================
// Connection Toggle
// ===========================================

async function toggleConnection() {
  try {
    if (state.isConnected) {
      await chrome.runtime.sendMessage({ type: 'disconnect' });
    } else {
      await chrome.runtime.sendMessage({ type: 'connect' });
    }
    setTimeout(refreshStatus, 500);
  } catch (error) {
    console.error('Connection toggle error:', error);
  }
}

// ===========================================
// Signature Handling
// ===========================================

async function checkPendingSignature() {
  try {
    const { pendingSignature } = await chrome.storage.local.get('pendingSignature');

    if (pendingSignature) {
      const age = Date.now() - pendingSignature.timestamp;

      if (age > 5 * 60 * 1000) {
        await chrome.storage.local.remove('pendingSignature');
        elements.signaturePending.style.display = 'none';
        return;
      }

      elements.signatureInfo.textContent =
        `${pendingSignature.tribunal || 'Tribunal'}: ${pendingSignature.processNumber || 'Documento'} aguardando assinatura`;
      elements.signaturePending.style.display = 'block';
    } else {
      elements.signaturePending.style.display = 'none';
    }
  } catch (error) {
    console.error('Error checking pending signature:', error);
  }
}

async function handleSignature() {
  try {
    const { pendingSignature } = await chrome.storage.local.get('pendingSignature');

    if (!pendingSignature) {
      showToast('Nenhuma assinatura pendente', 'error');
      return;
    }

    elements.signBtn.disabled = true;
    elements.signBtn.textContent = 'Processando...';

    await chrome.runtime.sendMessage({
      type: 'signature_completed',
      data: pendingSignature,
    });

    await chrome.storage.local.remove('pendingSignature');
    elements.signaturePending.style.display = 'none';
    showToast('Assinatura realizada!', 'success');
  } catch (error) {
    console.error('Signature error:', error);
    showToast('Erro ao processar assinatura', 'error');
  } finally {
    elements.signBtn.disabled = false;
    elements.signBtn.textContent = 'Assinar com Certificado A3';
  }
}

// ===========================================
// CAPTCHA Handling
// ===========================================

async function checkPendingCaptcha() {
  try {
    const { pendingCaptcha } = await chrome.storage.local.get('pendingCaptcha');

    if (pendingCaptcha) {
      const expiresAt = new Date(pendingCaptcha.expiresAt).getTime();
      const now = Date.now();

      if (now >= expiresAt) {
        await chrome.storage.local.remove('pendingCaptcha');
        hideCaptcha();
        return;
      }

      showCaptcha(pendingCaptcha);
    } else {
      hideCaptcha();
    }
  } catch (error) {
    console.error('Error checking pending CAPTCHA:', error);
  }
}

function showCaptcha(data) {
  state.currentCaptcha = data;
  const { captcha, tribunal, expiresAt } = data;

  const captchaTypeLabels = {
    'image': 'CAPTCHA de Imagem',
    'recaptcha_v2': 'reCAPTCHA v2',
    'recaptcha_v3': 'reCAPTCHA v3',
    'hcaptcha': 'hCaptcha',
    'unknown': 'CAPTCHA',
  };

  elements.captchaTitle.textContent = captchaTypeLabels[captcha.type] || 'CAPTCHA';
  elements.captchaInfo.textContent = `${tribunal || 'Tribunal'}: Resolva para continuar`;

  if (captcha.type === 'image') {
    elements.captchaImageContainer.style.display = 'block';
    elements.captchaRecaptchaContainer.style.display = 'none';
    elements.submitCaptchaBtn.style.display = 'block';

    if (captcha.imageBase64) {
      elements.captchaImage.src = `data:image/png;base64,${captcha.imageBase64}`;
    } else if (captcha.imageUrl) {
      elements.captchaImage.src = captcha.imageUrl;
    }

    elements.captchaText.value = '';
    elements.captchaText.focus();
  } else {
    elements.captchaImageContainer.style.display = 'none';
    elements.captchaRecaptchaContainer.style.display = 'block';
    elements.submitCaptchaBtn.style.display = 'none';
  }

  startCaptchaTimer(new Date(expiresAt));
  elements.captchaPending.style.display = 'block';
}

function hideCaptcha() {
  state.currentCaptcha = null;
  elements.captchaPending.style.display = 'none';
  elements.captchaText.value = '';

  if (state.captchaTimerInterval) {
    clearInterval(state.captchaTimerInterval);
    state.captchaTimerInterval = null;
  }
}

function startCaptchaTimer(expiresAt) {
  if (state.captchaTimerInterval) {
    clearInterval(state.captchaTimerInterval);
  }

  function updateTimer() {
    const now = Date.now();
    const remaining = expiresAt.getTime() - now;

    if (remaining <= 0) {
      elements.captchaTimer.textContent = 'Expirado!';
      clearInterval(state.captchaTimerInterval);
      setTimeout(() => cancelCaptcha(), 1000);
      return;
    }

    const minutes = Math.floor(remaining / 60000);
    const seconds = Math.floor((remaining % 60000) / 1000);
    elements.captchaTimer.textContent = `Expira em: ${minutes}:${seconds.toString().padStart(2, '0')}`;
  }

  updateTimer();
  state.captchaTimerInterval = setInterval(updateTimer, 1000);
}

async function submitCaptcha() {
  if (!state.currentCaptcha) return;

  const text = elements.captchaText.value.trim();

  if (!text) {
    showToast('Digite o texto do CAPTCHA', 'error');
    return;
  }

  elements.submitCaptchaBtn.disabled = true;
  elements.submitCaptchaBtn.textContent = 'Enviando...';

  try {
    await chrome.runtime.sendMessage({
      type: 'captcha_solution',
      data: {
        captchaId: state.currentCaptcha.captchaId,
        jobId: state.currentCaptcha.jobId,
        success: true,
        solution: { text },
      },
    });

    showToast('CAPTCHA enviado!', 'success');
    hideCaptcha();
  } catch (error) {
    console.error('CAPTCHA submit error:', error);
    showToast('Erro ao enviar CAPTCHA', 'error');
  } finally {
    elements.submitCaptchaBtn.disabled = false;
    elements.submitCaptchaBtn.textContent = 'Enviar';
  }
}

async function cancelCaptcha() {
  if (!state.currentCaptcha) return;

  try {
    await chrome.runtime.sendMessage({
      type: 'captcha_solution',
      data: {
        captchaId: state.currentCaptcha.captchaId,
        jobId: state.currentCaptcha.jobId,
        success: false,
        error: 'Cancelado pelo usuario',
      },
    });

    hideCaptcha();
  } catch (error) {
    console.error('CAPTCHA cancel error:', error);
  }
}

async function openTribunalPage() {
  if (!state.currentCaptcha) return;

  const { tribunalUrl } = state.currentCaptcha;

  if (tribunalUrl) {
    await chrome.tabs.create({ url: tribunalUrl, active: true });
  } else {
    showToast('URL do tribunal nao disponivel', 'error');
  }
}

// ===========================================
// Event Listeners
// ===========================================

function setupEventListeners() {
  // Auth tabs
  document.querySelectorAll('.auth-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.auth-tab').forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.auth-form').forEach(f => f.classList.remove('active'));

      tab.classList.add('active');
      const formId = tab.dataset.tab === 'login' ? 'loginForm' : 'registerForm';
      document.getElementById(formId).classList.add('active');
    });
  });

  // Auth actions
  elements.loginBtn.addEventListener('click', handleLogin);
  elements.registerBtn.addEventListener('click', handleRegister);
  elements.logoutLink.addEventListener('click', (e) => {
    e.preventDefault();
    handleLogout();
  });

  // Enter key on email inputs
  elements.loginEmail.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') handleLogin();
  });
  elements.registerEmail.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') handleRegister();
  });

  // Terms link
  elements.termsLink.addEventListener('click', (e) => {
    e.preventDefault();
    chrome.tabs.create({ url: 'https://iudex.com.br/termos' });
  });

  // License actions
  elements.upgradeBtn.addEventListener('click', togglePlansSection);
  elements.manageSubscription.addEventListener('click', (e) => {
    e.preventDefault();
    openPortal();
  });

  // Plan cards
  document.querySelectorAll('.plan-card').forEach(card => {
    card.addEventListener('click', () => {
      const plan = card.dataset.plan;
      const interval = card.dataset.interval;
      openCheckout(plan, interval);
    });
  });

  // Connection
  elements.connectBtn.addEventListener('click', toggleConnection);
  elements.saveBtn.addEventListener('click', saveConfig);

  // Signature
  elements.signBtn.addEventListener('click', handleSignature);

  // CAPTCHA
  elements.submitCaptchaBtn.addEventListener('click', submitCaptcha);
  elements.cancelCaptchaBtn.addEventListener('click', cancelCaptcha);
  elements.openTribunalBtn.addEventListener('click', openTribunalPage);
  elements.captchaText.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') submitCaptcha();
  });

  // Listen for messages from background
  chrome.runtime.onMessage.addListener((message) => {
    if (message.type === 'status_update') {
      state.isConnected = message.status.isConnected;
      state.pendingOperations = message.status.pendingOperations || [];
      updateStatusUI(message.status);
      updateOperationsUI(state.pendingOperations);
    } else if (message.type === 'server_event') {
      if (message.event === 'signature_required') {
        checkPendingSignature();
      }
    } else if (message.type === 'captcha_required') {
      checkPendingCaptcha();
    } else if (message.type === 'license_updated') {
      checkLicense();
    }
  });
}

// ===========================================
// Utilities
// ===========================================

function isValidEmail(email) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

function showToast(message, type = 'info') {
  elements.toast.textContent = message;
  elements.toast.className = `toast ${type} visible`;

  setTimeout(() => {
    elements.toast.classList.remove('visible');
  }, 3000);
}
