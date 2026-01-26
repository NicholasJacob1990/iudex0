# AI Log - tribunais-playwright

## 2026-01-25 — Atualização do sei-mcp com Sessões e Janelas

### Resumo
Implementadas funcionalidades de múltiplas sessões, controle de janela e heartbeat no sei-mcp, seguindo o padrão do tribunais-playwright.

### Arquivos Criados no sei-mcp
- `src/sessions/session-manager.ts` — Gerenciador de sessões
- `src/sessions/index.ts` — Export do módulo

### Arquivos Modificados no sei-mcp
- `src/types/index.ts` — Novos tipos (SessionInfo, WindowState, etc.)
- `src/websocket/server.ts` — Suporte a múltiplos clientes e heartbeat
- `src/tools/all-tools.ts` — 10 novas ferramentas
- `src/tools/index.ts` — Handler para ferramentas de sessão
- `src/server.ts` — Integração do SessionManager

### Novas Ferramentas MCP no sei-mcp
| Ferramenta | Descrição |
|------------|-----------|
| `sei_list_sessions` | Lista sessões ativas |
| `sei_get_session_info` | Info de sessão |
| `sei_close_session` | Fecha sessão |
| `sei_switch_session` | Troca sessão |
| `sei_minimize_window` | Minimiza janela |
| `sei_restore_window` | Restaura janela |
| `sei_focus_window` | Foco na janela |
| `sei_get_window_state` | Estado da janela |
| `sei_set_window_bounds` | Define posição/tamanho |
| `sei_get_connection_status` | Status da conexão |

### Funcionalidades Adicionadas no sei-playwright
- `minimizeWindow()`, `restoreWindow()`, `maximizeWindow()`, `bringToFront()`
- `getCdpEndpoint()`, `getWindowBounds()`, `setWindowBounds()`
- Opções `cdpPort` e `keepAlive` na config

### Verificação
```bash
# sei-mcp
pnpm tsc --noEmit  # OK

# sei-playwright
pnpm build  # OK
```

---

## 2026-01-25 — MCP Server + API REST + Comparativo

### Objetivo
Criar servidor MCP para tribunais e API REST completa, similar ao sei-mcp.

### Arquivos Criados
- `src/mcp/server.ts` — Servidor MCP com 14 ferramentas
- `src/mcp/index.ts` — Export do MCP
- `src/api/server.ts` — API REST Express
- `src/api/index.ts` — Export da API
- `docs/COMPARATIVO.md` — Comparativo sei vs tribunais

### Ferramentas MCP Implementadas

| Ferramenta | Descrição |
|------------|-----------|
| `tribunal_criar_sessao` | Cria sessão do navegador |
| `tribunal_login` | Faz login (senha/certificado) |
| `tribunal_logout` | Faz logout |
| `tribunal_fechar_sessao` | Fecha sessão |
| `tribunal_minimizar` | Minimiza janela |
| `tribunal_restaurar` | Restaura janela |
| `tribunal_consultar_processo` | Consulta processo |
| `tribunal_listar_documentos` | Lista documentos |
| `tribunal_listar_movimentacoes` | Lista movimentações |
| `tribunal_baixar_processo` | Baixa metadados do processo |
| `tribunal_peticionar` | Protocola petição |
| `tribunal_screenshot` | Captura tela |
| `tribunal_listar_sessoes` | Lista sessões ativas |

### Endpoints REST

```
POST   /sessions                      - Criar sessão
GET    /sessions                      - Listar sessões
GET    /sessions/:id                  - Status da sessão
DELETE /sessions/:id                  - Encerrar sessão
POST   /sessions/:id/login            - Login
POST   /sessions/:id/logout           - Logout
POST   /sessions/:id/window/minimize  - Minimizar
POST   /sessions/:id/window/restore   - Restaurar
POST   /sessions/:id/window/focus     - Foco
GET    /sessions/:id/processo/:num    - Consultar
POST   /sessions/:id/processo/:num/peticao - Peticionar
POST   /sessions/:id/screenshot       - Screenshot
```

### Funcionalidades Adicionadas ao Base Client
- `minimizeWindow()` — Minimiza janela via CDP
- `restoreWindow()` — Restaura janela via CDP
- `bringToFront()` — Traz janela para frente
- `getCdpEndpoint()` — Retorna endpoint para reconexão
- `keepAlive` — Mantém navegador aberto após close()
- `cdpPort` — Define porta CDP para reconexão

### Execução
```bash
pnpm api         # Inicia API REST (porta 3000)
pnpm mcp         # Inicia servidor MCP
```

---

## 2026-01-25 — Refatoração para Seletores ARIA no EprocClient

### Objetivo
Garantir que o `EprocClient` use seletores semânticos ARIA (`getByRole`) como método primário, com fallback para CSS apenas quando necessário.

### Problema Identificado
O `EprocClient` sobrescrevia métodos do `BaseTribunalClient` e usava seletores CSS hardcoded em vez dos métodos ARIA (`fillSmart`, `clickSmart`, `selectSmart`).

### Arquivos Modificados
- `src/eproc/client.ts` — Refatorado para usar seletores ARIA

### Métodos Refatorados

| Método | Antes | Depois |
|--------|-------|--------|
| `loginWithPassword()` | `page.fill('#txtUsuario', ...)` | `this.fillSmart(this.selectors.login.cpfInput, ...)` |
| `loginWithCertificateA1()` | `page.click('button:has-text(...)')` | `this.clickSmart(this.selectors.login.certificadoBtn)` |
| `consultarProcesso()` | CSS hardcoded | `this.fillSmart()`, `this.clickSmart()` |
| `peticionar()` | CSS hardcoded | `this.clickSmart()`, `this.selectSmart()` |
| `anexarArquivo()` | CSS hardcoded | `this.clickSmart()`, `this.findSmart()` |
| `assinarEEnviar()` | CSS hardcoded | `this.clickSmart(this.selectors.peticao.assinarBtn)` |
| `abrirProcesso()` | CSS hardcoded | Seletores ARIA |
| `aguardarAssinatura()` | CSS hardcoded | `this.findSmart(this.selectors.common.successAlert)` |
| `capturarProtocolo()` | CSS hardcoded | `this.findSmart(this.selectors.peticao.protocoloText)` |
| `assinarDocumentos()` | CSS hardcoded | `page.getByRole('checkbox')` com fallback |

### Padrão Implementado

```typescript
// ANTES (CSS hardcoded)
await page.fill('#txtUsuario', auth.cpf);

// DEPOIS (ARIA com fallback)
await this.fillSmart(this.selectors.login.cpfInput, auth.cpf);

// Onde fillSmart usa:
page.getByRole(selector.role, { name: selector.name }).fill(value);
// Com fallback para:
page.fill(selector.fallback, value);
```

### Build
```bash
pnpm tsc --noEmit  # OK
```

---

## 2026-01-25 — Suporte a Captcha (Human-in-the-loop)

### Objetivo
Adicionar detecção e resolução de captchas no fluxo de automação, seguindo o padrão human-in-the-loop.

### Arquivos Criados/Modificados

- `src/core/captcha-handler.ts` — Handler completo para captchas
- `src/types/index.ts` — Tipos de captcha adicionados
- `src/core/base-client.ts` — Integração do captcha handler

### Recursos Implementados

#### Tipos de Captcha Suportados
| Tipo | Descrição |
|------|-----------|
| `image` | Captcha de imagem com texto |
| `recaptcha_v2` | Google reCAPTCHA v2 |
| `recaptcha_v3` | Google reCAPTCHA v3 |
| `hcaptcha` | hCaptcha |
| `audio` | Captcha de áudio |

#### Modos de Resolução
| Modo | Descrição |
|------|-----------|
| `manual` | Aguarda usuário resolver (timeout configurável) |
| `service` | Usa serviço externo (2captcha, anticaptcha, capsolver) |
| `hybrid` | Tenta serviço primeiro, fallback para manual |

#### Serviços Suportados
- 2captcha
- Anti-Captcha
- CapSolver
- DeathByCaptcha (em breve)

#### Eventos
- `captcha:detected` — Captcha detectado na página
- `captcha:required` — Resolução necessária
- `captcha:solved` — Captcha resolvido com sucesso
- `captcha:failed` — Falha na resolução

#### Notificações
- `captcha_detected` — Para webhook/callback
- `captcha_required` — Solicita interação do usuário
- `captcha_solved` — Confirma resolução
- `captcha_failed` — Informa falha

### Fluxo Human-in-the-loop

```
Automação detecta captcha
         │
         ▼
Notifica usuário (webhook/push)
         │
         ▼
Aguarda resolução (polling)
  - Manual: usuário preenche na tela
  - Serviço: 2captcha/anticaptcha resolve
         │
         ▼
Aplica solução e continua automação
```

### Build
```bash
pnpm tsc --noEmit  # OK
pnpm build         # OK (55KB ESM)
```

---

## 2026-01-25 — Criação Inicial do Projeto

### Objetivo
Criar biblioteca para automação de tribunais brasileiros (PJe, e-SAJ, eproc) seguindo o padrão do sei-playwright, com suporte a todos os métodos de autenticação.

### Arquivos Criados

**Estrutura:**
```
tribunais-playwright/
├── package.json
├── tsconfig.json
├── README.md
├── src/
│   ├── index.ts              # Exports principais
│   ├── types/index.ts        # Tipos TypeScript
│   ├── core/
│   │   ├── index.ts
│   │   └── base-client.ts    # Cliente base com autenticação
│   ├── pje/
│   │   ├── index.ts
│   │   ├── client.ts         # PJeClient
│   │   └── selectors.ts      # Seletores ARIA do PJe
│   ├── esaj/
│   │   ├── index.ts
│   │   └── selectors.ts      # Seletores ARIA do e-SAJ
│   └── eproc/
│       ├── index.ts
│       └── selectors.ts      # Seletores ARIA do eproc
├── examples/
│   └── basic.ts              # Exemplos de uso
└── docs/
    └── AI_LOG.md
```

### Recursos Implementados

#### Autenticação
| Tipo | Descrição | Interação |
|------|-----------|-----------|
| `password` | CPF + Senha | Automático |
| `certificate_a1` | Arquivo .pfx | Automático |
| `certificate_a3_physical` | Token USB | Aguarda PIN |
| `certificate_a3_cloud` | Certisign/Serasa | Aguarda aprovação no celular |

#### Funcionalidades
- `login()` — Login com qualquer método
- `consultarProcesso()` — Consulta dados
- `listarDocumentos()` — Lista documentos
- `listarMovimentacoes()` — Lista andamentos
- `peticionar()` — Peticiona com upload de arquivos
- `assinarDocumentos()` — Assina documentos
- `screenshot()` — Captura tela

#### Notificações (Human-in-the-Loop)
- Eventos: `login:pin_required`, `login:approval_required`, `peticao:signature_required`
- Callbacks: `onPinRequired`, `onApprovalRequired`
- Webhook: `webhookUrl` para integração externa

### Decisões Técnicas

1. **Seletores Semânticos ARIA**: Mesma abordagem do sei-playwright para robustez
2. **EventEmitter**: Para eventos tipados e integração com sistemas externos
3. **Sessão Persistente**: Opção `persistent: true` para reutilizar login
4. **Certificado A1 nativo**: Usa `clientCertificates` do Playwright (sem interação)

### Build
```bash
pnpm install  # OK
pnpm tsc --noEmit  # OK
pnpm build  # OK (ESM + CJS + DTS)
```

### Próximos Passos
- [ ] Implementar clientes específicos para e-SAJ e eproc
- [ ] Testar com instâncias reais dos tribunais
- [ ] Adicionar suporte a PJeOffice para A3 nuvem
- [ ] Criar integração MCP (tribunais-mcp)
- [ ] Testes automatizados

---
