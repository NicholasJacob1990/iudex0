# AI Log - sei-playwright

## 2026-01-25 — Session Management & Window Control

### Objetivo
Adicionar funcionalidades de gerenciamento de sessão e controle de janela no sei-playwright, seguindo o padrão do tribunais-playwright.

### Arquivos Alterados
- `src/types.ts` — Adicionadas opções `cdpPort` e `keepAlive` na interface SEIConfig.playwright
- `src/browser/client.ts` — Adicionados métodos de controle de janela e sessão
- `src/client.ts` — Expostos métodos de window control no cliente híbrido

### Funcionalidades Adicionadas

#### Novas opções de configuração:
- `playwright.cdpPort` - Porta para servidor CDP (permite reconexão futura)
- `playwright.keepAlive` - Manter navegador aberto após close()

#### Métodos de controle de janela (via CDP):
- `minimizeWindow()` - Minimiza a janela do navegador
- `restoreWindow()` - Restaura a janela do navegador
- `maximizeWindow()` - Maximiza a janela
- `fullscreenWindow()` - Coloca em tela cheia
- `bringToFront()` - Traz a janela para frente
- `getWindowBounds()` - Obtém dimensões/posição da janela
- `setWindowBounds()` - Define dimensões/posição da janela

#### Métodos de gerenciamento de sessão:
- `getCdpEndpoint()` - Retorna endpoint CDP para reconexão
- `isSessionActive()` - Verifica se sessão está ativa
- `getContext()` - Obtém o contexto do browser
- `getBrowser()` - Obtém o browser atual

### Verificação
```bash
pnpm build  # OK - Build success
```

### Status
Implementação concluída. Os métodos seguem o mesmo padrão do tribunais-playwright.

---

## 2026-01-25 — Correção de Erros TypeScript na Refatoração ARIA

### Objetivo
Finalizar refatoração ARIA corrigindo erros de tipagem em `clickSmart`.

### Problema
Build falhava com 2 erros TypeScript:
```
src/browser/client.ts(2065,31): error TS2345: Argument of type 'Locator' is not assignable to parameter of type 'Page | FrameLocator'.
src/browser/client.ts(2151,33): error TS2345: Argument of type 'Locator' is not assignable to parameter of type 'Page | FrameLocator'.
```

### Causa Raiz
O método `clickSmart` aceita `Page | FrameLocator`, mas em dois locais passávamos um `Locator`:
1. `removeMarker()` — passava `marcadorEl.locator('xpath=..')`
2. `revokeAccess()` — passava `row` (um Locator de linha de tabela)

### Solução
Em vez de modificar a assinatura do `clickSmart`, refatorei as duas chamadas para usar locators encadeados diretamente:

```typescript
// Antes (erro)
await this.clickSmart(marcadorEl.locator('xpath=..'), { role: 'link', name: /excluir|remover/i });

// Depois (correto)
const parentEl = marcadorEl.locator('xpath=..');
const removeLink = parentEl.getByRole('link', { name: /excluir|remover/i })
  .or(parentEl.locator('img[title*="Excluir"], img[title*="Remover"]').locator('xpath=..'));
await removeLink.first().click();
```

### Arquivos Modificados
- `src/browser/client.ts` — Métodos `removeMarker()` e `revokeAccess()`

### Verificação
```bash
pnpm tsc --noEmit  # OK - sem erros
pnpm build         # OK - Build success
```

### Status
✅ Refatoração ARIA concluída sem erros de TypeScript.

---

## 2026-01-24 — SEI Daemon (Monitoramento Contínuo)

### Objetivo
Criar um serviço daemon que monitora o SEI continuamente e envia notificações de novos processos, blocos de assinatura e prazos.

### Arquivos Criados
- `src/daemon.ts` — SEIDaemon class com suporte a CDP
- `start-daemon.ts` — Script de inicialização
- `start-chrome-debug.sh` — Helper para iniciar Chrome com debugging
- `ecosystem.config.cjs` — Configuração PM2 para rodar em background

### Dois Modos de Operação

**Modo 1 - CDP (Recomendado para monitoramento)**
```bash
# Terminal 1: Inicia Chrome com debugging
./start-chrome-debug.sh

# Faça login no SEI manualmente

# Terminal 2: Inicia daemon conectando ao Chrome
SEI_CDP=http://localhost:9222 npx tsx start-daemon.ts
```

**Modo 2 - Browser Próprio (com credenciais)**
```bash
SEI_USER=xxx SEI_PASS=xxx SEI_ORGAO=CODEMGE npx tsx start-daemon.ts
```

### Recursos do Daemon

| Recurso | Descrição |
|---------|-----------|
| Monitoramento contínuo | Verifica novos itens a cada 1 minuto (configurável) |
| Tipos monitorados | processos_recebidos, blocos_assinatura, prazos |
| Relogin automático | Detecta sessão expirada e reconecta |
| Notificações por email | Configurável via SMTP |
| Webhooks | Envia POST para URL configurada |
| PM2 ready | Pode rodar como serviço background |

### Configuração de Notificações

```typescript
const daemon = new SEIDaemon({
  baseUrl: 'https://sei.mg.gov.br',
  browser: { cdpEndpoint: 'http://localhost:9222' },
  notifications: {
    email: {
      host: 'smtp.gmail.com',
      port: 587,
      auth: { user: 'x', pass: 'y' },
      from: 'noreply@meusite.com',
    },
    webhook: 'https://meu-sistema.com/webhook/sei',
    recipients: [
      { userId: '1', email: 'joao@email.com', nome: 'João' },
    ],
  },
});
```

### Rodar com PM2

```bash
pm2 start ecosystem.config.cjs
pm2 logs sei-daemon
pm2 stop sei-daemon
```

---

## 2026-01-24 — Persistent Context (Sessão Persistente)

### Objetivo
Permitir que a biblioteca mantenha sessão do Chrome entre execuções, evitando login repetido.

### Arquivos Modificados
- `src/types.ts` — Novas opções: `persistent`, `channel`, `cdpEndpoint`
- `src/browser/client.ts` — Suporte a persistent context e CDP connection

### Novas Opções de Configuração

```typescript
const client = new SEIClient({
  baseUrl: 'https://www.sei.mg.gov.br',
  playwright: {
    // Opção 1: Persistent Context (recomendado)
    persistent: true,                    // Mantém sessão entre execuções
    userDataDir: '~/.sei-playwright/chrome-profile', // (default)
    channel: 'chrome',                   // Usa Chrome instalado

    // Opção 2: CDP Connection (avançado)
    cdpEndpoint: 'http://localhost:9222', // Conecta a Chrome já aberto
  },
});
```

### Fluxo de Uso

1. **Primeira execução** (headless: false):
   - Abre Chrome visível
   - Faz login (manual ou automático)
   - Sessão é salva em `~/.sei-playwright/chrome-profile`

2. **Próximas execuções** (headless: true opcional):
   - Sessão já está salva
   - Pula login automaticamente
   - Pode rodar em background

### Benefícios
- Não precisa passar credenciais após primeiro login
- Pode usar autenticação de dois fatores
- Sessão persiste mesmo após reiniciar máquina
- Compatível com modo headless após login inicial

### Script de Teste
```bash
npx tsx test-persistent.ts          # Primeira vez (login)
npx tsx test-persistent.ts          # Segunda vez (já logado!)
npx tsx test-persistent.ts headless # Modo background
```

---

## 2026-01-24 — Refatoracao para Locators Semanticos ARIA

### Objetivo
Refatorar a biblioteca SEIBrowserClient para usar locators semanticos do Playwright (ARIA) em vez de seletores CSS, tornando a automacao mais robusta e resiliente a mudancas na interface do SEI.

### Arquivos Modificados
- `src/browser/client.ts` — Refatoracao completa (~2500 linhas)

### Principais Mudancas

**1. Login refatorado:**
```typescript
// ANTES (seletores CSS):
await page.fill(SEI_SELECTORS.login.usuario, usuario);
await page.click(SEI_SELECTORS.login.submit);

// DEPOIS (locators semanticos):
await page.getByRole('textbox', { name: /usu[aá]rio/i }).fill(usuario);
await page.getByRole('button', { name: /acessar|entrar/i }).click();
```

**2. Navegacao refatorada:**
```typescript
// ANTES:
await page.fill(SEI_SELECTORS.nav.pesquisa, texto);
await page.click(SEI_SELECTORS.nav.btnPesquisa);

// DEPOIS:
await page.getByRole('textbox', { name: /pesquis/i }).fill(texto);
await page.getByRole('button', { name: /pesquis/i }).click();
```

**3. Verificacao de login:**
```typescript
// DEPOIS (mais robusto):
const userIndicator = page.getByRole('link', { name: /sair|logout/i })
  .or(page.locator('#lnkUsuarioSistema'));
await userIndicator.first().waitFor({ timeout: 2000 });
```

**4. Arvore de documentos:**
```typescript
// DEPOIS:
const frame = page.frameLocator('iframe[name="ifrArvore"]');
const docLinks = await frame.getByRole('link').filter({ hasText: /\(\d+\)/ }).all();
```

**5. Acoes do processo:**
```typescript
// DEPOIS:
await page.getByRole('link', { name: /incluir.*documento/i })
  .or(page.locator('img[title*="Incluir Documento"]').locator('xpath=..'))
  .first().click();
```

**6. Novo metodo helper getAriaSnapshot():**
```typescript
async getAriaSnapshot(): Promise<object | null> {
  const ariaTree = await page.locator('body').ariaSnapshot();
  return { ariaSnapshot: ariaTree };
}
```

### Estrategia de Fallback
Cada metodo tenta primeiro o locator semantico e faz fallback para seletores CSS se falhar:
```typescript
try {
  await page.getByRole('button', { name: /salvar/i }).click();
} catch {
  await page.click(SEI_SELECTORS.newDocument.salvar);
}
```

### Helpers Criados
- `getTreeFrame(page)` — Obtem frame da arvore de documentos
- `getViewFrame(page)` — Obtem frame de visualizacao
- `getEditorFrame(page)` — Obtem frame do editor
- `getTextbox/getButton/getLink/getCombobox/getCheckbox/getRadio` — Helpers tipados

### Verificacao
```bash
pnpm build  # OK - Build completo sem erros
```

### Beneficios
1. **Mais robusto**: Locators semanticos nao quebram com mudancas de CSS
2. **Regex case-insensitive**: Funciona com variantes de acentuacao
3. **Fallback garantido**: SEI_SELECTORS mantido como backup
4. **Compatibilidade**: API publica 100% preservada

---

## 2026-01-24 — Correcao de Seletores de Login para SEI MG

### Problema
Login não preenchia senha e órgão no SEI MG (sei.mg.gov.br).

### Causa Raiz
1. **Campo de senha duplicado**: SEI MG usa dois inputs de senha:
   - `input[name="pwdSenha"]` com `display: none` (oculto)
   - `input#pwdSenha.masked` com `type="text"` (visível)
   - Playwright selecionava o campo oculto

2. **Seleção de órgão por valor**: O código usava `selectOption(selector, "CODEMGE")`
   mas "CODEMGE" é o **texto** da opção, não o valor (que é "86")

### Solução
- **selectors.ts**: Priorizar seletor `input#pwdSenha.masked` sobre `input[name="pwdSenha"]`
- **client.ts**: Usar `selectOption({ label: orgaoValue })` para selecionar pelo texto

### Arquivos Modificados
- `src/browser/selectors.ts` — Seletor de senha corrigido
- `src/browser/client.ts` — Método login() usa `{ label }` para órgão

### Teste
```bash
SEI_USER="xxx" SEI_PASS="xxx" SEI_ORGAO="CODEMGE" npx tsx test-lib.ts
# ✅ TODOS OS TESTES PASSARAM!
```

---

## 2026-01-24 — Paridade Completa: 52 Funções SEI

### Objetivo
Garantir paridade total entre SEI_TOOLS (Iudex) e MCP (sei-mcp), com 52 funções.

### Arquivos Modificados

**sei-playwright (biblioteca Node.js):**
- `src/api.ts` — Adicionados ~35 novos endpoints REST
- `src/browser/client.ts` — Adicionados ~20 novos métodos de automação
- `src/client.ts` — Ajustado método screenshot()

**integrations/iudex-chatbot:**
- `sei_tools.py` — Atualizado para 52 funções (era 23)
- `openai-functions.json` — 52 definições de função

### Novos Endpoints na API

| Categoria | Endpoints Adicionados |
|-----------|----------------------|
| Busca | `GET /process/search` |
| Processo | `POST /process/:id/open`, `GET /process/:id/status`, `GET /process/:id/download` |
| Anotações | `GET/POST /process/:id/annotations` |
| Marcadores | `POST/DELETE /process/:id/markers/:marcador` |
| Prazos | `POST /process/:id/deadline` |
| Acesso | `POST/DELETE /process/:id/access/:usuario` |
| Documento | `GET /document/:id/download`, `POST /document/:id/knowledge`, `POST /document/:id/publish` |
| Assinatura | `POST /documents/sign-multiple`, `POST /bloco/:id/sign` |
| Listagens | `/usuarios`, `/hipoteses-legais`, `/marcadores`, `/meus-processos` |
| Debug | `/screenshot`, `/snapshot`, `/current-page`, `/navigate`, `/click`, `/type`, `/select`, `/wait` |

### Métodos Adicionados ao SEIBrowserClient

- `listUsuarios()`, `listHipotesesLegais()`, `listMarcadores()`, `listMeusProcessos()`
- `searchProcessos()`, `downloadProcess()`, `downloadDocument()`
- `listAnnotations()`, `addAnnotation()`, `addMarker()`, `removeMarker()`
- `setDeadline()`, `grantAccess()`, `revokeAccess()`
- `getDocumentContent()`, `registerKnowledge()`, `schedulePublication()`
- `signBloco()`, `getBloco()`, `snapshot()`

### Verificação
```bash
npx tsc --noEmit  # OK - sem erros
```

---

## 2026-01-24 — SEI Tools Integration para Iudex Chat

### Objetivo
Criar integração de ferramentas SEI para o chat multi-provider do Iudex.

### Arquivos Criados/Modificados
- `integrations/iudex-chatbot/sei_tools.py` — SEIToolExecutor + SEI_TOOLS exportáveis
- `integrations/iudex-chatbot/router.py` — FastAPI endpoints para executar tools
- `integrations/iudex-chatbot/openai-functions.json` — 23 funções SEI
- `integrations/iudex-chatbot/__init__.py` — Exports do módulo
- `integrations/iudex-chatbot/README.md` — Documentação de integração
- `integrations/iudex-chatbot/requirements.txt` — Dependências

### Arquivos para remover (obsoletos)
- `integrations/iudex-chatbot/sei_chatbot.py` — Substituído por sei_tools.py
- `integrations/iudex-chatbot/example_usage.py` — Não necessário
- `integrations/iudex-chatbot/components/` — Widget não necessário (Iudex tem próprio)

### Decisões Tomadas
1. **Integração simplificada**: O chat do Iudex já tem os providers (GPT/Claude/Gemini).
   A integração fornece apenas:
   - `SEI_TOOLS` - Lista de ferramentas para registrar no chat
   - `SEI_SYSTEM_PROMPT` - Prompt adicional sobre SEI
   - `/api/sei/execute` - Endpoint para executar tool calls

2. **Arquitetura**:
   ```
   Chat Iudex (LLM) → tool_call → /api/sei/execute → sei-playwright API → SEI
   ```

### Endpoints da Integração
| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/api/sei/tools` | Lista tools (formato universal) |
| POST | `/api/sei/execute` | Executa tool call |
| GET | `/api/sei/session/{user_id}` | Verifica sessão |
| DELETE | `/api/sei/session/{user_id}` | Encerra sessão |

### Como usar no Iudex
```python
from integrations.sei_tools import SEI_TOOLS, SEI_SYSTEM_PROMPT, router

# 1. Registrar router
app.include_router(router, prefix="/api/sei")

# 2. Adicionar tools ao chat
chat.register_tools(SEI_TOOLS)

# 3. Adicionar prompt
system_prompt += SEI_SYSTEM_PROMPT

# 4. Quando LLM retornar tool_call:
result = await httpx.post("/api/sei/execute", json={
    "user_id": user_id,
    "function_name": tool_call.function.name,
    "arguments": tool_call.function.arguments
})
```
