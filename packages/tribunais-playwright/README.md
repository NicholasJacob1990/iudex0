# tribunais-playwright

Biblioteca TypeScript para automação de tribunais brasileiros (PJe, e-SAJ, eproc) com suporte completo a certificado digital.

## Recursos

- **Login com CPF/Senha** - Para consultas e acompanhamento
- **Certificado A1 (.pfx)** - Automação completa sem interação
- **Certificado A3 Físico (Token USB)** - Pausa e aguarda PIN do usuário
- **Certificado A3 Nuvem (Certisign, Serasa, etc.)** - Pausa e aguarda aprovação no celular
- **Captcha** - Detecta e aguarda resolução manual ou via serviços (2captcha, anticaptcha)
- **Sessão Persistente** - Login uma vez, reutiliza sessão
- **Notificações** - Webhook, callbacks, eventos para integração

## Instalação

```bash
pnpm add tribunais-playwright
# ou
npm install tribunais-playwright
```

## Uso Básico

### Login com Senha (Consulta)

```typescript
import { PJeClient } from 'tribunais-playwright';

const pje = new PJeClient({
  baseUrl: 'https://pje.trt3.jus.br',
  auth: {
    type: 'password',
    cpf: '12345678900',
    senha: 'minhaSenha',
  },
});

await pje.init();
await pje.login();

// Consultar processo
const processo = await pje.consultarProcesso('0001234-56.2025.5.03.0001');
```

### Login com Certificado A1 (Automático)

```typescript
const pje = new PJeClient({
  baseUrl: 'https://pje.trt3.jus.br',
  auth: {
    type: 'certificate_a1',
    pfxPath: '/path/to/certificado.pfx',
    passphrase: 'senha-do-pfx',
  },
});

await pje.init();
await pje.login();

// Peticionar (100% automático)
const resultado = await pje.peticionar({
  numeroProcesso: '0001234-56.2025.5.03.0001',
  tipo: 'Petição Simples',
  arquivos: ['/path/to/peticao.pdf'],
});
```

### Login com Certificado A3 Físico (Token USB)

```typescript
const pje = new PJeClient({
  baseUrl: 'https://pje.trt3.jus.br',
  auth: {
    type: 'certificate_a3_physical',
    pinTimeout: 300000, // 5 minutos

    onPinRequired: async () => {
      // Notifica usuário para digitar PIN
      console.log('Digite o PIN do token na janela do sistema');
      await sendPushNotification('PIN necessário');
    },
  },
  playwright: {
    headless: false, // Precisa ver a janela do PIN
  },
});

await pje.init();
await pje.login(); // Aguarda PIN

const resultado = await pje.peticionar({...}); // Aguarda PIN novamente
```

### Login com Certificado A3 Nuvem (Certisign, Serasa)

```typescript
const pje = new PJeClient({
  baseUrl: 'https://pje.trt3.jus.br',
  auth: {
    type: 'certificate_a3_cloud',
    provider: 'certisign', // ou 'serasa', 'safeweb', 'soluti'
    approvalTimeout: 120000, // 2 minutos

    onApprovalRequired: async (info) => {
      // Envia push para o celular do usuário
      await sendPushNotification(info.message);
    },
  },
  webhookUrl: 'https://meu-sistema.com/webhook', // Opcional
});

await pje.init();
await pje.login(); // Aguarda aprovação no celular

const resultado = await pje.peticionar({...}); // Aguarda aprovação novamente
```

## Captcha (Human-in-the-loop)

### Resolução Manual

```typescript
const pje = new PJeClient({
  baseUrl: 'https://pje.trt3.jus.br',
  auth: { type: 'password', cpf: '...', senha: '...' },
  captcha: {
    mode: 'manual',
    manualTimeout: 300000, // 5 minutos

    // Notifica quando captcha aparece
    onCaptchaDetected: async (info) => {
      console.log(`Captcha ${info.type} detectado!`);
      if (info.imageBase64) {
        // Exibe imagem para o usuário
        await sendToFrontend({ type: 'captcha', image: info.imageBase64 });
      }
    },

    // Obtém solução do usuário
    onCaptchaRequired: async (info) => {
      // Aguarda usuário digitar no frontend
      return await waitForUserInput('captcha-solution');
    },
  },
});
```

### Via Serviço Externo (2captcha, anticaptcha)

```typescript
const pje = new PJeClient({
  // ...
  captcha: {
    mode: 'service',
    service: {
      provider: '2captcha', // ou 'anticaptcha', 'capsolver'
      apiKey: 'sua-api-key',
      timeout: 120000,
    },
  },
});
```

### Modo Híbrido (tenta serviço, fallback manual)

```typescript
const pje = new PJeClient({
  // ...
  captcha: {
    mode: 'hybrid',
    service: {
      provider: 'anticaptcha',
      apiKey: 'sua-api-key',
    },
    onCaptchaRequired: async (info) => {
      // Fallback: usuário resolve manualmente
      return await askUser('Digite o captcha:');
    },
  },
});
```

### Tipos de Captcha Suportados

| Tipo | Descrição | Resolução |
|------|-----------|-----------|
| `image` | Captcha de imagem com texto | Manual ou serviço |
| `recaptcha_v2` | "Não sou um robô" | Manual ou serviço |
| `hcaptcha` | Similar ao reCAPTCHA | Manual ou serviço |
| `audio` | Captcha de áudio | Manual |

### Eventos de Captcha

```typescript
pje.on('captcha:detected', (info) => {
  console.log(`Captcha ${info.type} detectado`);
});

pje.on('captcha:required', (info) => {
  // Notificar usuário para resolver
  sendPushNotification('Resolva o captcha para continuar');
});

pje.on('captcha:solved', ({ captcha, solution }) => {
  console.log(`Resolvido em ${solution.solveTime}ms por ${solution.solvedBy}`);
});

pje.on('captcha:failed', ({ captcha, error }) => {
  console.error(`Falha: ${error}`);
});
```

## Eventos

```typescript
pje.on('login:success', ({ usuario }) => {
  console.log(`Logado como ${usuario}`);
});

pje.on('login:pin_required', ({ timeout }) => {
  console.log(`Aguardando PIN (timeout: ${timeout}ms)`);
});

pje.on('login:approval_required', (info) => {
  console.log(`Aprove no app ${info.provider}`);
});

pje.on('peticao:signature_required', (info) => {
  // Notifica usuário para assinar
});

pje.on('peticao:success', (resultado) => {
  console.log(`Protocolo: ${resultado.numeroProtocolo}`);
});

pje.on('error', ({ error }) => {
  console.error(error);
});
```

## Webhook de Notificações

```typescript
const pje = new PJeClient({
  // ...
  webhookUrl: 'https://meu-sistema.com/webhook/certificado',
  onNotification: async (notif) => {
    // Também recebe localmente
    console.log(notif.type, notif.message);
  },
});
```

Payload do webhook:
```json
{
  "type": "signature_pending",
  "message": "Aprove a assinatura no app Certisign",
  "expiresIn": 120,
  "data": {
    "type": "signature",
    "provider": "certisign"
  },
  "timestamp": "2025-01-25T12:00:00.000Z"
}
```

## Tribunais Suportados

### PJe (Processo Judicial Eletrônico)
- Justiça do Trabalho: TRT1-24, TST
- Justiça Federal: TRF1-6
- Justiça Estadual: TJMG, TJSP, TJRJ, etc.

### e-SAJ
- TJSP, TJMT, TJMS, TJAC, TJAL, TJAM

### eproc
- TRF4, JFRS, JFSC, JFPR, TJRS

## Sessão Persistente

Para evitar login repetido:

```typescript
const pje = new PJeClient({
  // ...
  playwright: {
    persistent: true,
    userDataDir: '~/.tribunais-playwright/pje-trt3',
  },
});

await pje.init();

if (await pje.isSessionActive()) {
  console.log('Já logado!');
} else {
  await pje.login();
}
```

## API

### PJeClient

| Método | Descrição |
|--------|-----------|
| `init()` | Inicializa navegador |
| `close()` | Fecha navegador |
| `login()` | Faz login (método depende do auth) |
| `logout()` | Encerra sessão |
| `isSessionActive()` | Verifica se está logado |
| `consultarProcesso(numero)` | Consulta dados do processo |
| `listarDocumentos(numero)` | Lista documentos do processo |
| `listarMovimentacoes(numero)` | Lista movimentações |
| `peticionar(opcoes)` | Peticiona no processo |
| `assinarDocumentos(opcoes)` | Assina documentos |
| `screenshot()` | Captura tela |

## Variáveis de Ambiente

```bash
# Opcional - para testes
PJE_BASE_URL=https://pje.trt3.jus.br
PJE_CPF=12345678900
PJE_SENHA=minhaSenha
PJE_PFX_PATH=/path/to/certificado.pfx
PJE_PFX_PASSPHRASE=senha
```

## Fluxo Human-in-the-Loop

```
┌─────────────────────────────────────────────────────────────────┐
│                    AUTOMAÇÃO (Playwright)                        │
│  1. Login com CPF/senha (se disponível)                         │
│  2. Navegar até processo                                        │
│  3. Preencher petição (tipo, descrição, anexos)                 │
│  4. Clicar em "Assinar"                                         │
└─────────────────────┬───────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│              🔔 NOTIFICA USUÁRIO (via webhook/callback)         │
│                                                                  │
│  A3 Físico: "Insira o token e digite o PIN"                    │
│  A3 Nuvem:  "Aprove no app remoteID do celular"                 │
└─────────────────────┬───────────────────────────────────────────┘
                      │
                      ▼ (usuário aprova)
┌─────────────────────────────────────────────────────────────────┐
│                    AUTOMAÇÃO CONTINUA                           │
│  5. Detecta assinatura concluída                                │
│  6. Confirma envio                                              │
│  7. Retorna número do protocolo                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Licença

MIT
