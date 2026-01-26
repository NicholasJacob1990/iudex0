# Comparativo: SEI vs Tribunais

## Comparação entre MCPs

### sei-mcp (46 ferramentas)

| Categoria | Ferramentas |
|-----------|-------------|
| **Autenticação** | `sei_login`, `sei_logout`, `sei_get_session` |
| **Processos** | `sei_search_process`, `sei_open_process`, `sei_create_process`, `sei_get_status`, `sei_forward_process`, `sei_conclude_process`, `sei_reopen_process`, `sei_relate_processes` |
| **Documentos** | `sei_list_documents`, `sei_get_document`, `sei_create_document`, `sei_upload_document`, `sei_upload_document_base64` |
| **Assinatura** | `sei_sign_document`, `sei_sign_multiple`, `sei_sign_block` |
| **Download** | `sei_download_process`, `sei_download_document` |
| **Anotações** | `sei_add_annotation`, `sei_list_annotations` |
| **Blocos** | `sei_list_blocks`, `sei_create_block`, `sei_get_block`, `sei_add_to_block`, `sei_remove_from_block`, `sei_release_block` |
| **Marcadores** | `sei_add_marker`, `sei_remove_marker` |
| **Prazos** | `sei_set_deadline` |
| **Ciência** | `sei_register_knowledge`, `sei_cancel_document` |
| **Publicação** | `sei_schedule_publication` |
| **Listagens** | `sei_list_document_types`, `sei_list_process_types`, `sei_list_units`, `sei_list_users`, `sei_list_hipoteses_legais`, `sei_list_marcadores`, `sei_list_my_processes` |
| **Acesso** | `sei_grant_access`, `sei_revoke_access` |
| **Navegação** | `sei_navigate`, `sei_click`, `sei_type`, `sei_select`, `sei_wait`, `sei_screenshot`, `sei_snapshot`, `sei_get_current_page` |

### tribunais-mcp (14 ferramentas)

| Categoria | Ferramentas |
|-----------|-------------|
| **Sessão** | `tribunal_criar_sessao`, `tribunal_fechar_sessao`, `tribunal_listar_sessoes` |
| **Autenticação** | `tribunal_login`, `tribunal_logout` |
| **Janela** | `tribunal_minimizar`, `tribunal_restaurar` |
| **Processos** | `tribunal_consultar_processo`, `tribunal_listar_documentos`, `tribunal_listar_movimentacoes`, `tribunal_baixar_processo` |
| **Peticionamento** | `tribunal_peticionar` |
| **Utilidades** | `tribunal_screenshot` |

### sei-mcp (52 ferramentas) - ATUALIZADO

| Categoria | Novas Ferramentas |
|-----------|-------------------|
| **Sessão** | `sei_list_sessions`, `sei_get_session_info`, `sei_close_session`, `sei_switch_session` |
| **Janela** | `sei_minimize_window`, `sei_restore_window`, `sei_focus_window`, `sei_get_window_state`, `sei_set_window_bounds` |
| **Conexão** | `sei_get_connection_status` |

### Funcionalidades Comparadas (ATUALIZADO)

| Funcionalidade | sei-mcp | tribunais-mcp |
|----------------|---------|---------------|
| Múltiplas sessões | ✅ | ✅ |
| Controle de janela | ✅ | ✅ |
| Heartbeat/Reconexão | ✅ | ✅ |
| Criar processos | ✅ | ❌ |
| Tramitar processos | ✅ | ❌ |
| Blocos de assinatura | ✅ | ❌ |
| Marcadores e anotações | ✅ | ❌ |
| Publicação oficial | ✅ | ❌ |
| Certificado digital | ❌ | ✅ |
| Human-in-the-loop | ❌ | ✅ |
| Detecção de captcha | ❌ | ✅ |

---

## Comparação entre Bibliotecas

### sei-playwright

| Recurso | Descrição |
|---------|-----------|
| **Sistema** | SEI (Sistema Eletrônico de Informações) |
| **Autenticação** | Usuário/senha |
| **API** | REST + WebSocket + SOAP |
| **Seletores** | ARIA semânticos com fallback CSS |
| **Sessão** | Persistente (cookies) |
| **Daemon** | Modo background com watcher |
| **Notificações** | Push notifications |
| **Documentos** | Criar, editar, assinar, baixar |
| **Processos** | Criar, tramitar, relacionar, concluir |

### tribunais-playwright

| Recurso | Descrição |
|---------|-----------|
| **Sistemas** | PJe, e-SAJ, eproc |
| **Autenticação** | Senha, Certificado A1, A3 físico, A3 nuvem |
| **API** | REST + MCP |
| **Seletores** | ARIA semânticos com fallback CSS |
| **Sessão** | Persistente + reconexão CDP |
| **Controle** | Minimizar/restaurar janela |
| **Captcha** | Detecção + resolução (manual/serviço) |
| **Documentos** | Listar, baixar metadados |
| **Processos** | Consultar, peticionar |

### Arquitetura

```
sei-playwright/
├── src/
│   ├── browser/client.ts    # Cliente Playwright
│   ├── soap/client.ts       # Cliente SOAP
│   ├── api.ts               # REST API
│   ├── daemon.ts            # Modo background
│   └── watcher.ts           # Monitor de mudanças

tribunais-playwright/
├── src/
│   ├── core/
│   │   ├── base-client.ts   # Cliente base
│   │   └── captcha-handler.ts
│   ├── eproc/client.ts      # EprocClient
│   ├── pje/client.ts        # PJeClient
│   ├── api/server.ts        # REST API
│   └── mcp/server.ts        # MCP Server
```

### Métodos de Autenticação

| Método | sei-playwright | tribunais-playwright |
|--------|----------------|---------------------|
| Usuário/Senha | ✅ | ✅ |
| Certificado A1 (.pfx) | ❌ | ✅ (automático) |
| Certificado A3 físico | ❌ | ✅ (human-in-the-loop) |
| Certificado A3 nuvem | ❌ | ✅ (human-in-the-loop) |
| 2FA | ❌ | ✅ |

### Funcionalidades de Sessão

| Funcionalidade | sei-playwright | tribunais-playwright |
|----------------|----------------|---------------------|
| Sessão persistente | ✅ | ✅ |
| Múltiplas sessões | ❌ | ✅ |
| Reconexão CDP | ❌ | ✅ |
| Controle de janela | ❌ | ✅ |
| Modo headless | ✅ | ✅ |
| Modo headed | ✅ | ✅ |

### Captcha

| Tipo | sei-playwright | tribunais-playwright |
|------|----------------|---------------------|
| Imagem | ❌ | ✅ |
| reCAPTCHA v2 | ❌ | ✅ |
| reCAPTCHA v3 | ❌ | ✅ |
| hCaptcha | ❌ | ✅ |
| Serviços (2captcha) | ❌ | ✅ |

---

## Resumo

| Aspecto | sei-playwright/mcp | tribunais-playwright/mcp |
|---------|-------------------|-------------------------|
| **Foco** | SEI (administrativo) | Tribunais (judicial) |
| **Maturidade** | Mais completo | Em desenvolvimento |
| **Ferramentas MCP** | 52 | 14 |
| **Autenticação** | Básica | Avançada (certificados) |
| **Human-in-the-loop** | Não | Sim |
| **Captcha** | Não | Sim |
| **Múltiplas Sessões** | ✅ Sim | ✅ Sim |
| **Controle de Janela** | ✅ Sim | ✅ Sim |
| **Heartbeat/Reconexão** | ✅ Sim | ✅ Sim |

### Quando usar cada um

- **sei-playwright/mcp**: Automação completa do SEI para órgãos públicos
- **tribunais-playwright/mcp**: Automação de tribunais para advogados/escritórios
