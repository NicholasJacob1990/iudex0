# sei-playwright

Biblioteca TypeScript para automação do SEI! (Sistema Eletrônico de Informações) usando Playwright.

Ideal para:
- Agentes automatizados de geração de documentos
- Integração com sistemas de minutas
- Automação de workflows governamentais
- Execução headless em containers

## Instalação

```bash
pnpm add sei-playwright
# ou
npm install sei-playwright
```

## Uso Básico

```typescript
import { SEIClient } from 'sei-playwright';

const sei = new SEIClient({
  baseUrl: 'https://sei.mg.gov.br',
  browser: {
    usuario: 'meu.usuario',
    senha: 'minhaSenha',
  },
  playwright: { headless: true },
});

await sei.init();
await sei.login();

// Abrir processo
await sei.openProcess('5030.01.0002527/2025-32');

// Listar documentos
const docs = await sei.listDocuments();
console.log(docs);

// Criar documento
await sei.createDocument('5030.01.0002527/2025-32', {
  idSerie: 'Despacho',
  descricao: 'Meu despacho',
  conteudoHtml: '<p>Texto do documento</p>',
});

await sei.close();
```

## Modos de Operação

### 1. Browser Only (padrão)

Usa Playwright para controlar o navegador. Funciona com qualquer instância do SEI.

```typescript
const sei = new SEIClient({
  baseUrl: 'https://sei.mg.gov.br',
  mode: 'browser',
  browser: { usuario: 'x', senha: 'y' },
  playwright: { headless: true },
});
```

### 2. SOAP Only

Usa a API SOAP nativa do SEI. Requer cadastro do sistema no SEI.

```typescript
const sei = new SEIClient({
  baseUrl: 'https://sei.mg.gov.br',
  mode: 'soap',
  soap: {
    siglaSistema: 'MEU_SISTEMA',
    identificacaoServico: 'MinhaChave123',
  },
});

await sei.init();
sei.setUnidade('110000001'); // ID da unidade

const tipos = await sei.listProcessTypes();
```

### 3. Híbrido (recomendado)

Tenta SOAP primeiro, fallback para browser se falhar.

```typescript
const sei = new SEIClient({
  baseUrl: 'https://sei.mg.gov.br',
  mode: 'auto', // padrão
  soap: { ... },
  browser: { ... },
  playwright: { headless: true },
});
```

## API

### SEIClient

| Método | Descrição | SOAP | Browser |
|--------|-----------|------|---------|
| `init()` | Inicializa clientes | ✅ | ✅ |
| `close()` | Fecha conexões | ✅ | ✅ |
| `login()` | Login no SEI | ❌ | ✅ |
| `logout()` | Logout do SEI | ❌ | ✅ |
| `isLoggedIn()` | Verifica sessão | ❌ | ✅ |
| `listProcessTypes()` | Lista tipos de processo | ✅ | ❌ |
| `listDocumentTypes()` | Lista tipos de documento | ✅ | ❌ |
| `listUnits()` | Lista unidades | ✅ | ❌ |
| `listUsers()` | Lista usuários | ✅ | ❌ |
| `openProcess()` | Abre processo | ❌ | ✅ |
| `getProcess()` | Consulta processo | ✅ | ❌ |
| `createProcess()` | Cria processo | ✅ | ❌ |
| `forwardProcess()` | Tramita processo | ✅ | ✅ |
| `concludeProcess()` | Conclui processo | ✅ | ✅ |
| `reopenProcess()` | Reabre processo | ✅ | ✅ |
| `listDocuments()` | Lista documentos | ❌ | ✅ |
| `createDocument()` | Cria documento | ✅ | ✅ |
| `uploadDocument()` | Upload externo | ✅ | ✅ |
| `signDocument()` | Assina documento | ❌ | ✅ |
| `screenshot()` | Captura tela | ❌ | ✅ |

### Criação de Documento

```typescript
await sei.createDocument(numeroProcesso, {
  // Tipo de documento (série)
  idSerie: 'Despacho', // ou 'Parecer Jurídico', 'Nota Técnica', etc.
  tipo: 'G', // G=Gerado, R=Recebido/Externo

  // Campos básicos
  descricao: 'Descrição do documento',
  numero: '29/2026', // Para Parecer, Anexo, etc.

  // Partes
  interessados: ['EUROFARMA LABORATÓRIOS S.A.'],
  destinatarios: ['Gerência de Patrimônio'], // Para Despacho, CI

  // Observações
  observacao: 'Observações adicionais',

  // Acesso
  nivelAcesso: 0, // 0=Público, 1=Restrito, 2=Sigiloso
  hipoteseLegal: 'Documento Preparatório',

  // Conteúdo (documento gerado)
  conteudoHtml: '<p>Texto do documento</p>',

  // Arquivo (documento externo)
  nomeArquivo: 'contrato.pdf',
  conteudoBase64: '...',
});
```

## Watcher - Monitor de Comunicações

O `SEIWatcher` monitora novos processos, documentos e comunicações usando **polling híbrido** (SOAP quando disponível, fallback para Playwright).

### Tipos Monitorados

| Tipo | Descrição |
|------|-----------|
| `processos_recebidos` | Novos processos recebidos na unidade |
| `processos_gerados` | Processos gerados pela unidade |
| `blocos_assinatura` | Blocos de assinatura pendentes |
| `retornos_programados` | Processos com retorno programado |
| `prazos` | Processos com prazo vencendo |

### Exemplo Completo

```typescript
import { SEIClient, SEIWatcher } from 'sei-playwright';

const sei = new SEIClient({
  baseUrl: 'https://sei.mg.gov.br',
  browser: { usuario: 'x', senha: 'y' },
  playwright: { headless: true },
});

await sei.init();
await sei.login();

// Criar watcher
const watcher = new SEIWatcher(sei, {
  interval: 30000, // 30 segundos
  types: ['processos_recebidos', 'blocos_assinatura'],
  preferSoap: true, // Usar SOAP se disponível
});

// Handlers de eventos
watcher.on('processos_recebidos', (event) => {
  console.log('Novos processos:', event.items);

  for (const item of event.items) {
    // Enviar notificação, email, etc.
    console.log(`Processo ${item.numero} de ${item.remetente}`);
  }
});

watcher.on('blocos_assinatura', (event) => {
  console.log('Blocos para assinar:', event.items);
});

watcher.on('error', (error) => {
  console.error('Erro:', error);
});

// Iniciar monitoramento
watcher.start();

// Parar quando necessário
// watcher.stop();
```

### Estratégia Híbrida

```
┌─────────────────────────────────────────┐
│            SEIWatcher                   │
│                                         │
│  ┌─────────────┐    ┌─────────────┐    │
│  │  SOAP API   │ OR │  Playwright │    │
│  │  (rápido)   │    │  (fallback) │    │
│  └──────┬──────┘    └──────┬──────┘    │
│         │                  │            │
│         ▼                  ▼            │
│  ┌─────────────────────────────────┐   │
│  │     Comparar com estado anterior │   │
│  └─────────────────────────────────┘   │
│                  │                      │
│                  ▼                      │
│  ┌─────────────────────────────────┐   │
│  │   Emitir eventos para novos itens│   │
│  └─────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

### Integração com Notificações

```typescript
watcher.on('processos_recebidos', async (event) => {
  for (const processo of event.items) {
    // Push notification
    await sendPushNotification({
      title: 'Novo Processo',
      body: `${processo.numero} - ${processo.tipo}`,
    });

    // Email
    await sendEmail({
      to: 'usuario@email.com',
      subject: `Novo processo: ${processo.numero}`,
      body: `Recebido de ${processo.remetente}`,
    });

    // Slack/Teams
    await sendSlackMessage({
      channel: '#sei-alertas',
      text: `📥 Novo processo: ${processo.numero}`,
    });
  }
});
```

## Uso com Docker

```dockerfile
FROM mcr.microsoft.com/playwright:v1.48.0-jammy

WORKDIR /app
COPY package.json pnpm-lock.yaml ./
RUN corepack enable && pnpm install --frozen-lockfile

COPY . .
RUN pnpm build

CMD ["node", "dist/index.js"]
```

## Variáveis de Ambiente

```bash
SEI_BASE_URL=https://sei.mg.gov.br
SEI_USUARIO=meu.usuario
SEI_SENHA=minhaSenha
SEI_HEADLESS=true

# Para SOAP (opcional)
SEI_SIGLA_SISTEMA=MEU_SISTEMA
SEI_IDENTIFICACAO_SERVICO=MinhaChave123
SEI_ID_UNIDADE=110000001
```

## Comparação com SEI-MCP

| Aspecto | sei-playwright | sei-mcp |
|---------|---------------|---------|
| Execução | Standalone/Container | Extensão Chrome |
| Headless | ✅ | ❌ |
| Sessão existente | ❌ | ✅ |
| Interação visual | Opcional | Sempre |
| Ideal para | Agentes automatizados | Uso interativo |

## Desenvolvimento

```bash
# Clone
git clone https://github.com/seu-usuario/sei-playwright.git
cd sei-playwright

# Instale dependências
pnpm install

# Build
pnpm build

# Teste
pnpm test

# Exemplo
SEI_USUARIO=x SEI_SENHA=y pnpm example
```

## Licença

MIT
