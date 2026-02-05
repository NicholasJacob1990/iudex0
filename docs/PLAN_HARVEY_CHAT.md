# Plano: Nova Página de Chat com Claude Agent SDK (Estilo Harvey)

> **Objetivo:** Criar uma nova página de chat no Iudex inspirada na UI/UX do Harvey AI, com Canvas inteligente, integração de fontes (LexisNexis + internas), e movida pelo Claude Agent SDK.

---

## 1. Visão Geral da Arquitetura

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           NOVA PÁGINA: /ask                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌─────────────────────────────┐  ┌────────────────────┐  │
│  │   SIDEBAR    │  │      CHAT + CANVAS          │  │   SOURCES PANEL    │  │
│  │              │  │                             │  │                    │  │
│  │ • Knowledge  │  │  ┌─────────────────────┐   │  │ • Citações         │  │
│  │   Sources    │  │  │   THREAD AREA       │   │  │ • Shepard's Status │  │
│  │              │  │  │   (Mensagens)       │   │  │ • Links LexisNexis │  │
│  │ • History    │  │  └─────────────────────┘   │  │ • Fontes Internas  │  │
│  │              │  │  ┌─────────────────────┐   │  │ • Legislação       │  │
│  │ • Library    │  │  │   CANVAS EDITOR     │   │  │ • Jurisprudência   │  │
│  │   (Prompts)  │  │  │   (Documento)       │   │  │                    │  │
│  │              │  │  └─────────────────────┘   │  │ • Filtros:         │  │
│  │ • Workflows  │  │  ┌─────────────────────┐   │  │   - Jurisdição     │  │
│  │              │  │  │   INPUT AREA        │   │  │   - Tipo           │  │
│  │ • Guidance   │  │  │   + File Upload     │   │  │   - Data           │  │
│  │              │  │  └─────────────────────┘   │  │                    │  │
│  └──────────────┘  └─────────────────────────────┘  └────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Funcionalidades do Harvey a Implementar

### 2.1 Knowledge Sources (Fontes de Conhecimento)

| Fonte | Descrição | Implementação |
|-------|-----------|---------------|
| **LexisNexis (Ask LexisNexis)** | Jurisprudência, estatutos e regulamentos dos EUA | API LexisNexis + Protégé AI |
| **Fontes Internas** | Corpus do usuário, documentos, contratos | RAG existente (ChromaDB) |
| **Web Search** | Pesquisa na web em tempo real | Perplexity API (já integrado) |
| **Legislação BR** | Legislação brasileira | Base interna + scraping |
| **Jurisprudência BR** | Tribunais brasileiros | Base interna + APIs tribunais |
| **EDGAR (SEC)** | Filings dos EUA | API EDGAR |

#### Seletores de Fonte (como Harvey):
```typescript
interface KnowledgeSource {
  id: string;
  name: string;
  icon: React.ReactNode;
  enabled: boolean;
  jurisdictions?: string[];  // Para LexisNexis
  contentTypes?: ('case_law' | 'statutes' | 'regulations')[];
  publishedOnly?: boolean;   // Excluir não publicados
}
```

### 2.2 Canvas/Draft Editor (Editor de Documentos)

**Comportamento de Abertura Automática:**
- Detectar intenção de geração de documento (minuta, petição, parecer, etc.)
- Abrir canvas automaticamente quando Claude gerar documento
- Manter thread de chat à esquerda, canvas à direita

**Modos de Query (como Harvey):**
| Modo | Descrição |
|------|-----------|
| **Auto** | Claude decide se edita canvas ou responde |
| **Edit** | Força edição do documento no canvas |
| **Answer** | Força resposta sem editar canvas |

**Features do Canvas:**
- [ ] Editor TipTap (já existe no projeto)
- [ ] Histórico de versões com restore
- [ ] "Show Edits" toggle (diffs: vermelho=deletado, azul=adicionado)
- [ ] Export para Word (.docx) com tracked changes
- [ ] Export para Markdown e PDF
- [ ] Seleção de texto para edição contextual
- [ ] Integração com prompts de biblioteca

### 2.3 Sources Panel (Painel de Fontes)

**Informações a Exibir:**
```typescript
interface Citation {
  id: string;
  type: 'case_law' | 'statute' | 'regulation' | 'internal' | 'web';
  title: string;
  citation: string;  // Ex: "123 F.3d 456 (2d Cir. 2020)"
  source: string;    // Ex: "LexisNexis", "Corpus Interno"
  url?: string;

  // LexisNexis specific
  shepardSignal?: 'positive' | 'negative' | 'caution' | 'neutral';
  shepardStatus?: 'followed' | 'distinguished' | 'overruled' | 'criticized';

  // Internal specific
  documentId?: string;
  relevanceScore?: number;

  // Snippet
  snippet: string;
  pageNumber?: number;
}
```

**UI do Sources Panel:**
- Agrupamento por tipo (Jurisprudência, Legislação, Documentos Internos)
- Shepard's Signals visuais (ícones coloridos)
- Hover para preview do snippet
- Click para abrir fonte completa
- Contador de citações por tipo
- Filtros por jurisdição/data

### 2.4 Integração LexisNexis

**Fluxo de Integração:**
```
User Query → Claude Agent → LexisNexis API → Protégé AI → Results
                                ↓
                    Shepard's Validation
                                ↓
                    Formatted Citations
```

**Endpoints Necessários:**
```python
# Backend
POST /api/lexisnexis/search
POST /api/lexisnexis/validate-citations
GET  /api/lexisnexis/case/{citation}
GET  /api/lexisnexis/shepards/{citation}
```

**Parâmetros de Busca LexisNexis:**
```typescript
interface LexisNexisSearchParams {
  query: string;
  jurisdictions: string[];     // ["federal", "ny", "ca"]
  contentTypes: string[];      // ["case_law", "statutes"]
  includeUnpublished: boolean;
  dateRange?: { from: string; to: string };
  legalClassification?: 'civil' | 'criminal' | 'both';
}
```

### 2.5 Claude Agent SDK Integration

**Agent Loop:**
```python
from anthropic import Anthropic

class LegalResearchAgent:
    def __init__(self):
        self.client = Anthropic()
        self.tools = [
            lexisnexis_search_tool,
            internal_corpus_search_tool,
            web_search_tool,
            document_generator_tool,
            citation_validator_tool,
        ]

    async def run(self, user_message: str, context: dict):
        messages = [{"role": "user", "content": user_message}]

        while True:
            response = await self.client.messages.create(
                model="claude-opus-4-5-20251101",
                max_tokens=16000,
                tools=self.tools,
                messages=messages,
                system=LEGAL_RESEARCH_SYSTEM_PROMPT,
            )

            # Yield thinking for UI
            if response.thinking:
                yield {"type": "thinking", "content": response.thinking}

            # Handle tool calls
            if response.stop_reason == "tool_use":
                tool_calls = [b for b in response.content if b.type == "tool_use"]

                for tool_call in tool_calls:
                    yield {"type": "tool_call", "tool": tool_call.name, "input": tool_call.input}

                    result = await self.execute_tool(tool_call)
                    yield {"type": "tool_result", "tool": tool_call.name, "result": result}

                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})
                continue

            # Final response
            yield {"type": "content", "content": response.content[0].text}
            break
```

**Tools a Implementar:**

| Tool | Descrição |
|------|-----------|
| `lexisnexis_search` | Busca no LexisNexis com filtros |
| `internal_corpus_search` | Busca no corpus interno (RAG) |
| `web_search` | Busca na web via Perplexity |
| `generate_document` | Gera documento (minuta, petição) |
| `validate_citations` | Valida citações via Shepard's |
| `analyze_document` | Analisa documento uploaded |
| `compare_documents` | Compara versões de documentos |

---

## 3. Componentes Frontend

### 3.1 Estrutura de Arquivos

```
apps/web/src/
├── app/(dashboard)/ask/
│   ├── page.tsx                    # Página principal
│   └── layout.tsx                  # Layout com sidebar
│
├── components/ask/
│   ├── ask-interface.tsx           # Container principal
│   ├── ask-sidebar.tsx             # Sidebar com fontes/history
│   ├── ask-thread.tsx              # Área de mensagens
│   ├── ask-canvas.tsx              # Editor de documentos
│   ├── ask-sources-panel.tsx       # Painel de fontes
│   ├── ask-input.tsx               # Input com upload
│   ├── ask-message.tsx             # Mensagem individual
│   ├── knowledge-source-selector.tsx
│   ├── jurisdiction-picker.tsx
│   ├── shepard-signal.tsx          # Componente de status Shepard's
│   ├── citation-card.tsx           # Card de citação
│   ├── version-history.tsx         # Histórico de versões do canvas
│   └── query-mode-toggle.tsx       # Auto/Edit/Answer toggle
│
├── stores/
│   └── ask-store.ts                # Estado da página Ask
│
└── lib/
    └── ask-api-client.ts           # Cliente API para Ask
```

### 3.2 Store (Zustand)

```typescript
// stores/ask-store.ts

interface AskState {
  // Thread
  messages: AskMessage[];
  isStreaming: boolean;

  // Canvas
  canvasContent: string;
  canvasVisible: boolean;
  canvasMode: 'auto' | 'edit' | 'answer';
  versions: CanvasVersion[];
  showEdits: boolean;

  // Sources
  citations: Citation[];
  sourcesExpanded: boolean;
  sourceFilters: SourceFilters;

  // Knowledge Sources
  enabledSources: KnowledgeSource[];
  lexisNexisConfig: LexisNexisConfig;

  // Agent
  agentRunning: boolean;
  currentToolCall: ToolCall | null;
  toolApprovalRequired: boolean;

  // Actions
  sendMessage: (content: string, attachments?: File[]) => Promise<void>;
  setCanvasContent: (content: string) => void;
  toggleCanvas: () => void;
  setQueryMode: (mode: 'auto' | 'edit' | 'answer') => void;
  restoreVersion: (versionId: string) => void;
  approveToolCall: (approved: boolean) => void;
  setSourceFilters: (filters: SourceFilters) => void;
}
```

### 3.3 Layout Responsivo

```
Desktop (>1280px):
┌────────┬──────────────────────────────┬────────────┐
│Sidebar │  Thread  │    Canvas        │  Sources   │
│ 240px  │   flex   │    flex          │   320px    │
└────────┴──────────────────────────────┴────────────┘

Tablet (768-1280px):
┌────────┬──────────────────────────────┐
│Sidebar │  Thread/Canvas (tabs)        │
│ 200px  │          flex                │
└────────┴──────────────────────────────┘
Sources: Bottom sheet

Mobile (<768px):
┌────────────────────────────────────────┐
│  Thread/Canvas (tabs)                  │
│               full                     │
└────────────────────────────────────────┘
Sidebar: Drawer
Sources: Bottom sheet
```

---

## 4. Backend Implementation

### 4.1 Novos Endpoints

```python
# apps/api/app/api/endpoints/ask.py

@router.post("/ask/chat")
async def ask_chat(
    request: AskChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Main endpoint for Ask page - uses Claude Agent SDK
    Returns SSE stream with thinking, tool calls, and content
    """
    pass

@router.post("/ask/lexisnexis/search")
async def lexisnexis_search(
    request: LexisNexisSearchRequest,
    current_user: User = Depends(get_current_user),
):
    """Search LexisNexis for legal content"""
    pass

@router.get("/ask/lexisnexis/shepards/{citation}")
async def get_shepards_status(
    citation: str,
    current_user: User = Depends(get_current_user),
):
    """Get Shepard's status for a citation"""
    pass

@router.post("/ask/canvas/export")
async def export_canvas(
    request: CanvasExportRequest,
    current_user: User = Depends(get_current_user),
):
    """Export canvas to DOCX/PDF with tracked changes"""
    pass
```

### 4.2 Services

```python
# apps/api/app/services/ask/

├── agent_service.py          # Claude Agent SDK orchestration
├── lexisnexis_service.py     # LexisNexis API integration
├── sources_service.py        # Aggregates all sources
├── canvas_service.py         # Document generation & versioning
└── citation_service.py       # Citation extraction & validation
```

### 4.3 Agent Service (Claude SDK)

```python
# apps/api/app/services/ask/agent_service.py

from anthropic import Anthropic
from typing import AsyncGenerator

class AskAgentService:
    def __init__(self):
        self.client = Anthropic()

    async def run_agent(
        self,
        user_message: str,
        context: AskContext,
        enabled_sources: list[str],
    ) -> AsyncGenerator[AskEvent, None]:

        tools = self._build_tools(enabled_sources)
        system_prompt = self._build_system_prompt(context)

        messages = [{"role": "user", "content": user_message}]

        while True:
            # Create message with extended thinking
            response = await self.client.messages.create(
                model="claude-opus-4-5-20251101",
                max_tokens=16000,
                tools=tools,
                messages=messages,
                system=system_prompt,
                # Enable extended thinking
                thinking={
                    "type": "enabled",
                    "budget_tokens": 10000
                }
            )

            # Process response blocks
            for block in response.content:
                if block.type == "thinking":
                    yield AskEvent(type="thinking", content=block.thinking)

                elif block.type == "tool_use":
                    yield AskEvent(
                        type="tool_call",
                        tool_name=block.name,
                        tool_input=block.input
                    )

                    # Execute tool
                    result = await self._execute_tool(block.name, block.input)

                    yield AskEvent(
                        type="tool_result",
                        tool_name=block.name,
                        result=result
                    )

                elif block.type == "text":
                    yield AskEvent(type="content", content=block.text)

            # Check if we need to continue (tool results to process)
            if response.stop_reason == "tool_use":
                # Add assistant response and tool results to messages
                messages.append({"role": "assistant", "content": response.content})

                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        result = await self._execute_tool(block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result)
                        })

                messages.append({"role": "user", "content": tool_results})
                continue

            # Done
            break

    def _build_tools(self, enabled_sources: list[str]) -> list[dict]:
        tools = []

        if "lexisnexis" in enabled_sources:
            tools.append({
                "name": "lexisnexis_search",
                "description": "Search LexisNexis for US case law, statutes, and regulations. Returns Shepard's validated citations.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Legal research query"},
                        "jurisdictions": {"type": "array", "items": {"type": "string"}},
                        "content_types": {"type": "array", "items": {"type": "string"}},
                        "include_unpublished": {"type": "boolean", "default": False}
                    },
                    "required": ["query"]
                }
            })

        if "internal_corpus" in enabled_sources:
            tools.append({
                "name": "internal_corpus_search",
                "description": "Search internal document corpus for relevant content",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "document_types": {"type": "array", "items": {"type": "string"}},
                        "date_range": {"type": "object"}
                    },
                    "required": ["query"]
                }
            })

        if "web_search" in enabled_sources:
            tools.append({
                "name": "web_search",
                "description": "Search the web for current information",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"}
                    },
                    "required": ["query"]
                }
            })

        # Always include document generation
        tools.append({
            "name": "generate_document",
            "description": "Generate a legal document (memo, brief, contract, petition, etc.)",
            "input_schema": {
                "type": "object",
                "properties": {
                    "document_type": {"type": "string"},
                    "content": {"type": "string"},
                    "format": {"type": "string", "enum": ["markdown", "structured"]}
                },
                "required": ["document_type", "content"]
            }
        })

        return tools
```

---

## 5. Integração LexisNexis (Detalhada)

### 5.1 API LexisNexis (Protégé AI)

**Autenticação:**
```python
# OAuth 2.0 Client Credentials Flow
async def get_lexisnexis_token():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://auth.lexisnexis.com/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": settings.LEXISNEXIS_CLIENT_ID,
                "client_secret": settings.LEXISNEXIS_CLIENT_SECRET,
                "scope": "search shepards"
            }
        )
        return response.json()["access_token"]
```

**Busca:**
```python
async def search_lexisnexis(
    query: str,
    jurisdictions: list[str],
    content_types: list[str],
) -> LexisNexisSearchResult:
    token = await get_lexisnexis_token()

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.lexisnexis.com/v1/search",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "query": query,
                "sources": content_types,
                "jurisdictions": jurisdictions,
                "options": {
                    "includeShepards": True,
                    "maxResults": 20
                }
            }
        )
        return LexisNexisSearchResult(**response.json())
```

### 5.2 Shepard's Citations Integration

```typescript
// Frontend component
interface ShepardSignalProps {
  signal: 'positive' | 'negative' | 'caution' | 'neutral';
  status?: string;
}

const ShepardSignal: React.FC<ShepardSignalProps> = ({ signal, status }) => {
  const colors = {
    positive: 'bg-green-500',    // Green - Still good law
    negative: 'bg-red-500',      // Red - Overruled/No longer good law
    caution: 'bg-yellow-500',    // Yellow - Some negative treatment
    neutral: 'bg-gray-500',      // Gray - Cited
  };

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger>
          <div className={cn('w-3 h-3 rounded-full', colors[signal])} />
        </TooltipTrigger>
        <TooltipContent>
          <p>{status || `Shepard's: ${signal}`}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
};
```

---

## 6. Casos de Uso Prioritários

### 6.1 Pesquisa Jurídica Guiada

```
Usuário: "Qual o entendimento do STJ sobre prescrição intercorrente
         em execução fiscal após a Lei 11.051/2004?"

Claude Agent:
1. [Thinking] Analisando query... tema envolve prescrição, execução fiscal, STJ
2. [Tool: internal_corpus_search] Buscando no corpus interno...
3. [Tool: web_search] Buscando jurisprudência atualizada...
4. [Content] Gera resposta com citações e fontes
```

### 6.2 Geração de Minuta com Canvas

```
Usuário: "Elabore uma petição inicial de cobrança de honorários advocatícios
         sucumbenciais com base nos documentos anexos"

Claude Agent:
1. [Thinking] Analisando documentos e identificando elementos...
2. [Tool: analyze_document] Extrai informações dos anexos
3. [Tool: internal_corpus_search] Busca modelos de petição similares
4. [Tool: generate_document] Gera petição inicial
5. [Canvas Opens] Documento aparece no canvas para edição
6. [Sources Panel] Mostra documentos de referência usados
```

### 6.3 Verificação de Precedentes

```
Usuário: "Verifique se os precedentes citados nesta petição ainda são válidos"
[Upload: petição.pdf]

Claude Agent:
1. [Tool: analyze_document] Extrai citações da petição
2. [Tool: lexisnexis_search] Valida cada citação via Shepard's
3. [Sources Panel] Mostra status de cada citação:
   - REsp 1.123.456/SP ✓ (válido)
   - REsp 2.345.678/RJ ⚠️ (superado)
4. [Content] Relatório de validação com recomendações
```

---

## 7. Roadmap de Implementação

### Fase 1: Estrutura Base (1-2 semanas)
- [ ] Nova rota `/ask` no Next.js
- [ ] Layout com sidebar + thread + canvas
- [ ] Componente AskInterface básico
- [ ] Store Zustand (ask-store.ts)
- [ ] Endpoint `/api/ask/chat` básico

### Fase 2: Claude Agent SDK (1-2 semanas)
- [ ] Integração Claude Agent SDK no backend
- [ ] Agent loop com tools básicas
- [ ] Streaming SSE com eventos (thinking, tool_call, content)
- [ ] UI de tool calls em execução
- [ ] Thinking panel

### Fase 3: Canvas Editor (1 semana)
- [ ] Integrar TipTap existente
- [ ] Abertura automática do canvas
- [ ] Modos Auto/Edit/Answer
- [ ] Histórico de versões
- [ ] Show Edits toggle
- [ ] Export DOCX/PDF

### Fase 4: Sources Panel (1 semana)
- [ ] Componente de citações
- [ ] Agrupamento por tipo
- [ ] Filtros de jurisdição/data
- [ ] Preview no hover
- [ ] Link para fonte original

### Fase 5: Integração LexisNexis (2 semanas)
- [ ] Registro na API LexisNexis (parceria comercial)
- [ ] Service de autenticação OAuth
- [ ] Busca com Protégé AI
- [ ] Shepard's Citations
- [ ] UI de sinais visuais

### Fase 6: Fontes Internas (1 semana)
- [ ] Conectar RAG existente (ChromaDB)
- [ ] Busca em corpus do usuário
- [ ] Busca em legislação BR
- [ ] Busca em jurisprudência BR

### Fase 7: Polish & Testes (1 semana)
- [ ] Testes E2E com Playwright
- [ ] Otimização de performance
- [ ] Responsividade mobile
- [ ] Documentação

---

## 8. Configurações Necessárias

### 8.1 Variáveis de Ambiente

```env
# .env
# Claude Agent SDK
ANTHROPIC_API_KEY=sk-ant-...

# LexisNexis
LEXISNEXIS_CLIENT_ID=...
LEXISNEXIS_CLIENT_SECRET=...
LEXISNEXIS_API_URL=https://api.lexisnexis.com

# Feature Flags
FEATURE_ASK_PAGE=true
FEATURE_LEXISNEXIS=true
FEATURE_CANVAS=true
```

### 8.2 Dependências Adicionais

**Frontend (apps/web/package.json):**
```json
{
  "@anthropic-ai/sdk": "^0.30.0",
  "diff": "^5.2.0"  // Para show edits no canvas
}
```

**Backend (apps/api/requirements.txt):**
```txt
anthropic>=0.40.0
httpx>=0.27.0  # Para chamadas async LexisNexis
```

---

## 9. Métricas de Sucesso

| Métrica | Target |
|---------|--------|
| Tempo de resposta inicial | < 2s |
| Tempo médio de pesquisa completa | < 15s |
| Taxa de citações válidas | > 95% |
| Satisfação do usuário | > 4.5/5 |
| Uso do canvas | > 60% das sessões |
| Precisão das fontes | > 90% |

---

## 10. Considerações de Segurança

1. **Dados sensíveis:** Queries e documentos NÃO devem ser logados em produção
2. **LexisNexis:** Tokens de acesso devem expirar e ser renovados
3. **Canvas:** Versões antigas devem ser criptografadas em repouso
4. **Rate Limiting:** Implementar rate limit por usuário para evitar abuse
5. **RBAC:** Apenas usuários com licença podem acessar LexisNexis

---

## 11. Integração com Funcionalidades Existentes do Iudex

### 11.1 Páginas Existentes a Considerar

| Página | Rota | Funcionalidades |
|--------|------|-----------------|
| **Minuta** | `/minuta` | Chat + Canvas split, multi-agent, quality profiles, playbooks |
| **Workflows** | `/workflows` | Builder visual LangGraph, 10+ node types |
| **Workflow Builder** | `/workflows/[id]` | Editor individual com citations, version history |

### 11.2 Componentes para Reutilizar

**De `components/chat/`:**
- `ChatInterface` - Container principal de mensagens
- `ChatInput` - Input com slash/at commands
- `chat-message.tsx` - Renderização de mensagens
- `deep-research-button.tsx` - Pesquisa profunda
- `sources-badge.tsx` - Badge de fontes RAG
- `model-selector.tsx` - Seleção de modelos
- `slash-command-menu.tsx` - Menu de comandos /
- `at-command-menu.tsx` - Menu de menções @

**De `components/workflows/`:**
- `citations-panel.tsx` - Painel de citações (adaptar para Sources Panel)
- `draft-editor.tsx` - Editor de rascunhos (adaptar para Canvas)
- `version-history.tsx` - Histórico de versões

**De `stores/`:**
- `chat-store.ts` - Estado do chat (2500+ linhas)
- `canvas-store.ts` - Estado do canvas
- `context-store.ts` - Contexto de arquivos/corpus

### 11.3 Funcionalidades Existentes para Manter

| Funcionalidade | Componente/Store | Status |
|----------------|------------------|--------|
| Streaming SSE | `chat-store.sendMessage()` | ✅ Reutilizar |
| Multi-model | `chat-store.selectedModels` | ✅ Reutilizar |
| Deep Research | `deep-research-button.tsx` | ✅ Reutilizar |
| Web Search | `chat-store.webSearch` | ✅ Reutilizar |
| RAG (corpus) | `sources-badge.tsx` | ✅ Reutilizar |
| Upload arquivos | `apiClient.uploadDocument` | ✅ Reutilizar |
| Slash commands | `slash-command-menu.tsx` | ✅ Reutilizar |
| Canvas editor | `CanvasContainer` | ✅ Adaptar |
| Playbooks | `PlaybookSelector` | ✅ Reutilizar |

### 11.4 Novas Funcionalidades para Adicionar

| Funcionalidade | Inspiração Harvey | Implementação |
|----------------|-------------------|---------------|
| Sources Panel lateral | `harvey-sources-panel-click.png` | Novo componente |
| Streaming UI dinâmica | `harvey-video-streaming-*.png` | Novo componente |
| "Finished in N steps" | Screenshots vídeo | Modificar chat-message |
| Citation hover preview | `harvey-footnote-hover-preview.png` | Novo componente |
| Mode toggle (Auto/Edit/Answer) | Screenshots vídeo | Novo componente |
| Follow-ups sugeridos | Screenshots vídeo | Novo componente |
| Shepard's signals | `harvey-sources-panel-click.png` | Novo componente (futuro) |
| LexisNexis integration | Documentação Harvey | Backend (futuro) |

### 11.5 Arquitetura da Página `/ask`

```
/ask (nova página sandbox)
├── Reutiliza: ChatInterface, ChatInput, stores
├── Adiciona: AskSourcesPanel, AskStreamingStatus, AskModeToggle
├── Layout: Thread (esquerda) + Canvas (centro) + Sources (direita)
└── Canvas: Abre automaticamente ao detectar geração de documento
```

---

## 12. Próximos Passos Imediatos

1. ✅ **Analisar funcionalidades existentes** - Mapeado acima
2. 🔄 **Criar estrutura de arquivos** da nova página `/ask`
3. **Criar `ask-store.ts`** estendendo chat-store com estado adicional
4. **Implementar `AskSourcesPanel`** baseado em citations-panel
5. **Implementar `AskStreamingStatus`** para estados dinâmicos
6. **Adaptar Canvas** para auto-open baseado em atividade
7. **Testar integração** com funcionalidades existentes

---

## 13. Referências Visuais Capturadas

Os seguintes screenshots foram capturados do Harvey AI para referência de UI/UX:

### 12.1 Screenshots Salvos

| Arquivo | Descrição |
|---------|-----------|
| `harvey-home.png` | Homepage do Harvey Support |
| `harvey-assistant-overview.png` | Página de documentação do Assistant |
| `harvey-assistant-workflows-ui.png` | **UI principal do Harvey** - Sidebar + Input + Knowledge Sources + Workflows recomendados |
| `harvey-lexisnexis-page.png` | Documentação da integração LexisNexis |
| `harvey-lexisnexis-source-selection.png` | **Modal de seleção LexisNexis** - Jurisdiction, Publication Status, Legal Classification |
| `harvey-lexisnexis-filters.png` | **Filtros de Jurisdição** - Lista completa de circuits e estados |
| `harvey-drafting-page.png` | Documentação do Draft Editor |
| `harvey-draft-generated-ui.png` | **Canvas Editor UI** - Thread (esquerda) + Editor (direita) + Toolbar + Versões |
| `harvey-workflows-overview.png` | Documentação de Workflows |
| `harvey-workflows-sidebar-ui.png` | **Lista de Workflows predefinidos** - General, Transactional, categorias e tipos de output |
| `harvey-sources-panel-click.png` | **SOURCES PANEL + LexisNexis Modal** - Painel lateral de fontes + visualização de caso |
| `harvey-footnote-hover-preview.png` | **Hover Preview de Citações** - Popup com snippet e Shepard's signal |

**Localização:** `docs/screenshots/`

### 12.2 Elementos-Chave da UI do Harvey

#### Sidebar (Navegação Principal)
- **Assistant** - Área de chat principal
- **Vault** - Armazenamento seguro de documentos
- **Workflows** - Fluxos de trabalho predefinidos
- **History** - Histórico de conversas
- **Library** - Biblioteca de prompts
- **Guidance** - Guias e ajuda

#### Área de Input
- Campo "Ask Harvey anything..."
- **Botões de ação:**
  - `+ Files and sources` - Upload e seleção de fontes
  - `≡ Prompts` - Biblioteca de prompts
  - `↔ Customize` - Customização
  - `✨ Improve` - Melhorar prompt automaticamente
  - `Ask Harvey` (botão principal)

#### Knowledge Sources (Badges)
- LexisNexis® (vermelho)
- iManage (azul)
- Web search (globo)
- Completed RFPs
- Jurisdições (Singapore, Sweden, etc.)

#### Recommended Workflows
Cards com:
- Título do workflow
- Descrição breve
- Tipo de output (Draft, Table, Output)
- Número de steps

#### Canvas/Draft Editor
- **Layout lado a lado:** Thread (esquerda) + Editor (direita)
- **Toolbar de formatação:** Paragraph, B, I, U, S, listas, links, undo/redo
- **Show Edits toggle:** Mostra diferenças (vermelho=deletado, azul=adicionado)
- **Version History:** Dropdown para restaurar versões anteriores
- **Modos de query:** Auto | Edit | Answer
- **Botões:** New thread, Share, Export

#### LexisNexis Selection Modal
- **Descrição:** "Get answers to US primary law questions from LexisNexis Protégé™ AI assistant"
- **Campos:**
  - Publication Status: All Content / Published Only
  - Jurisdiction: Federal, State circuits (1st-11th), etc.
  - Legal Classification: Civil, Criminal, Both
- **Botões:** "Yes, ask LexisNexis®" | "No, answer without it"

#### Sources Panel (CRÍTICO - Painel de Fontes Lateral)

**Estrutura do Painel (lado esquerdo da resposta):**
```
┌─────────────────────────────────┐
│ Sources                         │
├─────────────────────────────────┤
│ LexisNexis® Case Law            │
│                                 │
│ ⚠️ McMorris v. Carlos Lopez &   │
│    Assocs., LLC, 995 F.3d 295   │
│    (2nd Circuit | Apr 26, 2021) │
│    [1] [7] [27] [29]            │
│                                 │
│ ⚠️ Clemens v. ExecuPharm Inc.,  │
│    48 F.4th 146                 │
│    (3rd Circuit | Sep 2, 2022)  │
│    [2] [3] [5] [10] [12] [32]   │
│                                 │
│ ⚠️ Legg v. Leaders Life Ins.    │
│    Co., 574 F. Supp. 3d 985     │
│    (Oklahoma Western | Dec 2021)│
│    [4] [11] [14] [33]           │
└─────────────────────────────────┘
```

**Shepard's Signals (Ícones de Status):**
| Ícone | Cor | Significado |
|-------|-----|-------------|
| 🔴 | Vermelho | **Negative** - Overruled, não é mais boa lei |
| ⚠️ | Amarelo | **Caution** - Questionado ou criticado |
| 🟢 | Verde | **Positive** - Seguido, ainda é boa lei |
| ⚪ | Cinza | **Neutral** - Apenas citado, sem análise |

**Comportamento ao Clicar em Fonte:**
1. Abre modal do LexisNexis com:
   - Header: "Ask LexisNexis" + botão Login
   - Título do caso completo
   - Tabs: Document | Citing Decisions (N) | History | Other Citing Sources | Table of Authorities
   - Navegação lateral: Top of Document, Search Terms, Disposition, Case Summary, Headnotes, Counsel, Judges, Opinion
   - **Shepard's® Panel** (lado direito):
     - Status: "Questioned" com link "Why?"
     - História: "No subsequent appellate history. Prior history available."
     - **Citing Decisions (breakdown):**
       - Questioned: 4
       - Caution: 5
       - Positive: 35
       - Neutral: 1
       - Cited: 87
     - Source Information: "2nd Circuit - US Court of Appeals Cases"

#### Hover Preview de Citações (Footnotes)

**Comportamento ao passar mouse sobre número de citação [N]:**
```
┌──────────────────────────────────────────────────┐
│ ⚠️ Solares v. City of Miami, 166 So. 3d 887     │
│                                                  │
│ ...be resolved before reaching the merits of a   │
│ case. [Before a court can consider whether an    │
│ action is illegal, the court must be presented   │
│ with a justiciable case or controversy between   │
│ parties who have standing.] Ferreiro v.          │
│ Philadelphia Indem. Ins. Co., 928 So. 2d 374,   │
│ 376 (Fla. 3d DCA 2006) ("The issue of standing  │
│ is a threshold inquiry which must be made at     │
│ the outset of the case before addressing         │
│ [the merits].")...                              │
│                                                  │
│                          View reference →        │
└──────────────────────────────────────────────────┘
```

**Elementos do Preview:**
- Shepard's signal (ícone colorido)
- Título do caso + citação completa
- Snippet do texto com **destaque azul** na parte relevante
- Citações relacionadas inline
- Botão "View reference →" para abrir completo

**Ações Disponíveis na Resposta:**
- 📋 Copy - Copia resposta
- ⬇️ Export - Exporta para Word/PDF
- 🔄 Rewrite - Reescreve resposta

**Aviso Importante:**
> "AI generated content must be verified in the LexisNexis® database."

#### Filtros de Jurisdição (Modal Completo)

**Estrutura do Modal de Filtros:**
```
┌─────────────────────────────────────────────────────┐
│ LexisNexis®                                     ✕   │
├─────────────────────┬───────────────────────────────┤
│ ☑️ Select all       │ ☐ All Federal                 │
│ ☑️ Publication      │ ☐ United States Supreme Court │
│    Status      ▶   │ ☐ 1st Circuit                 │
│ ☑️ Jurisdiction ▶   │ ☐ 2nd Circuit                 │
│ ☐ Legal            │ ☐ 3rd Circuit                 │
│   Classification ▶ │ ☐ 4th Circuit                 │
│   (Select up to 1)  │ ☐ 5th Circuit                 │
│                     │ ☐ 6th Circuit                 │
│                     │ ☐ 7th Circuit                 │
│                     │ ☐ 8th Circuit                 │
│                     │ ☐ 9th Circuit                 │
│                     │ ☐ 10th Circuit                │
│                     │ ☑️ 11th Circuit               │
│                     │ ☐ D.C. Circuit                │
│                     │ ☐ Federal Circuit             │
│                     │ ────────────────────          │
│                     │ ☐ Alabama                     │
│                     │ ☐ Alaska                      │
│                     │ ☐ Arizona                     │
│                     │ ... (todos os estados)        │
├─────────────────────┴───────────────────────────────┤
│                              [Cancel]  [Add]        │
└─────────────────────────────────────────────────────┘
```

**Categorias de Filtros:**
1. **Publication Status** (obrigatório, pré-selecionado):
   - All Content (inclui não publicados)
   - Published Only
2. **Jurisdiction** (opcional, até 3 seleções):
   - Federal: Supreme Court, Circuits 1-11, D.C., Federal
   - Estados: Todos os 50 estados + D.C.
3. **Legal Classification** (opcional, até 1):
   - Civil
   - Criminal

### 12.3 Workflows Predefinidos do Harvey

#### Categoria: General
| Workflow | Output | Steps |
|----------|--------|-------|
| Draft a Client Alert | Draft | 2 steps |
| Draft from Template | Draft | 3 steps |
| Extract Timeline of Key Events | Table | 1 step |
| Proofread for Spelling and Grammar | Draft | 1 step |
| Summarize Interview Calls | Output | 4 steps |
| Transcribe Audio to Text | Output | 3 steps |
| Translate into Another Language | Output | 2 steps |
| PPM - CIMA Rules Checklist | Review table | 13 columns |

#### Categoria: Transactional
| Workflow | Output | Steps/Columns |
|----------|--------|---------------|
| Analyze Change of Control Provisions | Review table | 13 columns |
| Draft an Interim Operating Covenants Memo | Draft | 2 steps |
| Draft an Item 1.01 Disclosure | Draft | 2 steps |
| Extract Key Data from Contracts | Review table | 4 columns |
| Extract Terms from Agreements with Shareholders | Review table | 38 columns |
| Extract Terms from Credit Agreements | Review table | 33 columns |
| Extract Terms from IP Agreements | Review table | 14 columns |
| Extract Terms from Lease Agreements | Review table | 25 columns |

#### Categoria: Litigation
| Workflow | Output |
|----------|--------|
| Analyze a Deposition Transcript for Key Topics | Summary |
| Analyze a Court Transcript for Key Topics | Summary |
| Draft Legal Research Memo | Draft |
| Summarize Discovery Responses and Objections | Table |

#### Categoria: Financial Services
| Workflow | Output |
|----------|--------|
| Generate Diligence Insights | Report |
| Summarize Interview Calls | Summary |
| Transcribe Audio to Text | Output |
| Check a Diligence Request List | Comparison |

---

## 12.4 Streaming UI & Animações Dinâmicas (NOVO - Capturado dos Vídeos)

Screenshots capturados dos vídeos do Harvey mostrando as animações de streaming em tempo real:

**Arquivos de Vídeo Capturados:**
| Arquivo | Descrição |
|---------|-----------|
| `harvey-video-streaming-1.png` | **UI Inicial** - Input + Workflows recomendados |
| `harvey-video-streaming-2.png` | **Canvas + Sources Panel** - Layout completo |
| `harvey-video-streaming-3.png` | **Estados de Streaming** - "Answering...", "Generating new version..." |
| `harvey-video-streaming-4.png` | **LexisNexis Case View** - Shepard's Panel com breakdown |
| `harvey-video-streaming-5.png` | **Popup de Sugestão** - Detecção automática de query jurídica |
| `harvey-video-streaming-6.png` | **Hover Preview** - Citação com snippet destacado |
| `harvey-video-streaming-7.png` | **Follow-ups Sugeridos** - Lista de perguntas relacionadas |
| `harvey-video-streaming-8.png` | **Layout 3 Colunas** - Thread + Canvas + Version History |
| `harvey-video-streaming-9.png` | **Estados em Tempo Real** - "Adding citations...", "Edits complete" |

### 12.4.1 Estados de Streaming Dinâmico (Thread)

**Indicadores de Progresso no Topo da Mensagem:**
```
┌────────────────────────────────────────────────────┐
│ H  Finished in 4 steps ∨                           │
│                                                    │
│ [Conteúdo da resposta...]                          │
└────────────────────────────────────────────────────┘
```

**Estados em Tempo Real (durante geração):**
| Estado | Descrição | Ícone |
|--------|-----------|-------|
| `Answering...` | Processando query inicial | ⏳ Spinner |
| `Adding citations...` | Buscando e adicionando citações | 📚 |
| `Generating new version...` | Gerando nova versão no canvas | ✏️ |
| `Edits complete` | Edições finalizadas | ✅ |
| `Finished in N steps` | Conclusão com contador de passos | ✓ |

**Implementação Proposta:**
```typescript
interface StreamingState {
  status: 'idle' | 'thinking' | 'tool_call' | 'generating' | 'complete';
  currentStep: string;  // Ex: "Adding citations..."
  stepsCompleted: number;
  totalSteps?: number;
  toolName?: string;    // Ex: "lexisnexis_search"
}

// Componente de Status
const StreamingStatus = ({ state }: { state: StreamingState }) => (
  <div className="flex items-center gap-2 text-sm text-muted-foreground">
    {state.status !== 'complete' && <Spinner className="h-4 w-4" />}
    {state.status === 'complete' && <Check className="h-4 w-4 text-green-500" />}
    <span>
      {state.status === 'complete'
        ? `Finished in ${state.stepsCompleted} steps`
        : state.currentStep
      }
    </span>
    {state.status === 'complete' && (
      <ChevronDown className="h-4 w-4 cursor-pointer" />
    )}
  </div>
);
```

### 12.4.2 Popup de Sugestão de Fonte (Detecção Automática)

**Comportamento:**
Quando usuário digita query que implica direito primário dos EUA, aparece popup preto sugerindo LexisNexis:

```
┌─────────────────────────────────────────────────────────────────┐
│ Get answers to US primary law questions from LexisNexis         │
│ Protégé™ AI assistant                                           │
│                                                                 │
│ Publication Status    All Primary Law                           │
│ Jurisdiction          3rd Circuit; 6th Circuit                  │
│ Legal Classification  Civil; Criminal                           │
│                                                                 │
│ ┌──────────────────────┐  ┌────────────────────────┐            │
│ │ Yes, ask 🔴 LexisNexis® │  │ No, answer without it │            │
│ └──────────────────────┘  └────────────────────────┘            │
└─────────────────────────────────────────────────────────────────┘
```

**Detecção de Query Jurídica:**
```typescript
const LEGAL_QUERY_PATTERNS = [
  /circuit/i,
  /statute/i,
  /regulation/i,
  /case law/i,
  /court/i,
  /§\s*\d+/,         // Referências a seções (§ 1983)
  /F\.\s*\d+d/i,     // Federal Reporter citations
  /U\.S\.C\./i,      // US Code
  /CFR/i,            // Code of Federal Regulations
];

const detectLegalQuery = (query: string): boolean => {
  return LEGAL_QUERY_PATTERNS.some(pattern => pattern.test(query));
};
```

### 12.4.3 Hover Preview de Citações

**Comportamento ao passar mouse sobre footnote [N]:**
```
┌──────────────────────────────────────────────────────────────┐
│ ⚠️ United States ex rel. Bergman v. Abbott Labs.,            │
│    995 F. Supp. 2d 357 (E.D. Pa. 2014) | U.S. District      │
│    Court, E.D. Pennsylvania                                  │
│                                                              │
│ ...Following other Circuits, the Third Circuit has           │
│ determined "[c]ompliance with the AKS is clearly a           │
│ condition of payment under Parts C and D of Medicare."       │
│ [TEXTO DESTACADO EM AMARELO] Wilkins, 659 F.3d at 314.      │
│ Thus, "[f]alsely certifying compliance with the...           │
│                                                              │
│                                      View reference →        │
└──────────────────────────────────────────────────────────────┘
```

**Componente React:**
```typescript
interface CitationPreviewProps {
  citation: Citation;
  snippet: string;
  highlightedText: string;
  onViewReference: () => void;
}

const CitationPreview = ({ citation, snippet, highlightedText, onViewReference }) => (
  <Popover>
    <PopoverTrigger asChild>
      <sup className="cursor-pointer text-blue-600 hover:underline">[{citation.footnoteNumber}]</sup>
    </PopoverTrigger>
    <PopoverContent className="w-96 p-4" side="top">
      <div className="flex items-start gap-2">
        <ShepardSignal signal={citation.shepardSignal} />
        <div>
          <p className="font-semibold">{citation.title}</p>
          <p className="text-sm text-muted-foreground">{citation.citation}</p>
        </div>
      </div>
      <div className="mt-3 text-sm">
        {renderSnippetWithHighlight(snippet, highlightedText)}
      </div>
      <Button
        variant="ghost"
        className="mt-2 w-full justify-end"
        onClick={onViewReference}
      >
        View reference →
      </Button>
    </PopoverContent>
  </Popover>
);
```

### 12.4.4 Follow-ups Sugeridos

**Lista de perguntas relacionadas geradas automaticamente:**
```
┌─────────────────────────────────────────────────────────────────┐
│ Follow-ups                                                       │
│                                                                 │
│ • Explain how the Third Circuit's approach to causation under   │
│   the AKS affects the ability of plaintiffs to survive a        │
│   motion to dismiss.                                            │
│                                                                 │
│ • Describe what the Sixth Circuit requires a plaintiff to       │
│   demonstrate in order to meet the but-for causation standard   │
│   under the AKS.                                                │
│                                                                 │
│ • Evaluate the practical implications of the differing          │
│   causation standards between the Third and Sixth Circuits      │
│   for FCA litigation involving AKS violations.                  │
│                                                                 │
│ • Clarify in what way both circuits treat claims tainted by     │
│   AKS violations as automatically false under the FCA,          │
│   despite their different causation analyses.                   │
└─────────────────────────────────────────────────────────────────┘
```

**Implementação:**
```typescript
interface FollowUpSuggestion {
  id: string;
  question: string;
  context: 'deepen' | 'compare' | 'apply' | 'clarify';
}

const FollowUpSuggestions = ({ suggestions, onSelect }) => (
  <div className="mt-4 border-t pt-4">
    <h4 className="text-sm font-medium mb-2">Follow-ups</h4>
    <ul className="space-y-2">
      {suggestions.map((suggestion) => (
        <li
          key={suggestion.id}
          className="text-sm text-muted-foreground hover:text-foreground cursor-pointer"
          onClick={() => onSelect(suggestion.question)}
        >
          • {suggestion.question}
        </li>
      ))}
    </ul>
  </div>
);
```

### 12.4.5 Version History no Thread

**Layout com Versões:**
```
┌────────────────────────────────────────┐
│ ✓ Great - Now revise this into a       │
│   succinct research email with two     │
│   paragraphs                           │
│                                        │
│ ○ Finished in 3 steps ∨                │
├────────────────────────────────────────┤
│ Version 1                     3:21 PM  │
│                                        │
│ I drafted a concise two-paragraph      │
│ research email contrasting the Third   │
│ and Sixth Circuits' causation          │
│ standards under the AKS...             │
│                                        │
│ ⎯ ▽ ▽  ⭐ ↗                            │
│                                        │
│ ○ No code changes                      │
│ ○ Finished in 1 step ∨                 │
├────────────────────────────────────────┤
│ Version 2                     3:21 PM  │
└────────────────────────────────────────┘
```

**Componente de Versões:**
```typescript
interface CanvasVersion {
  id: string;
  number: number;
  timestamp: Date;
  content: string;
  summary: string;
  hasCodeChanges: boolean;
  stepsCount: number;
}

const VersionHistory = ({ versions, currentVersion, onRestore }) => (
  <div className="space-y-3">
    {versions.map((version) => (
      <div
        key={version.id}
        className={cn(
          "p-3 rounded-lg border",
          version.id === currentVersion ? "border-primary" : "border-border"
        )}
      >
        <div className="flex justify-between text-sm">
          <span className="font-medium">Version {version.number}</span>
          <span className="text-muted-foreground">
            {format(version.timestamp, 'h:mm a')}
          </span>
        </div>
        <p className="text-sm mt-1 text-muted-foreground line-clamp-2">
          {version.summary}
        </p>
        <div className="flex items-center gap-4 mt-2 text-xs text-muted-foreground">
          <span>{version.hasCodeChanges ? '✏️ Has changes' : '○ No changes'}</span>
          <span>○ Finished in {version.stepsCount} step{version.stepsCount > 1 ? 's' : ''}</span>
        </div>
      </div>
    ))}
  </div>
);
```

### 12.4.6 Mode Selector (Auto | Edit | Answer)

**Toggle no rodapé do Canvas:**
```
┌─────────────────────────────────────────────────────────────┐
│ Ask Harvey. Requires LexisNexis Protégé™ to search U.S.     │
│ primary law.                                                │
│                                                             │
│ +  ☰  ···                               [Auto] [Edit] [Answer] │
└─────────────────────────────────────────────────────────────┘
```

**Implementação:**
```typescript
type QueryMode = 'auto' | 'edit' | 'answer';

const QueryModeToggle = ({ mode, onChange }) => (
  <div className="flex rounded-lg border bg-muted p-1">
    {(['auto', 'edit', 'answer'] as QueryMode[]).map((m) => (
      <button
        key={m}
        className={cn(
          "px-3 py-1 text-sm rounded-md transition-colors",
          mode === m
            ? "bg-background shadow-sm font-medium"
            : "text-muted-foreground hover:text-foreground"
        )}
        onClick={() => onChange(m)}
      >
        {m.charAt(0).toUpperCase() + m.slice(1)}
      </button>
    ))}
  </div>
);
```

### 12.4.7 Toolbar de Ações na Resposta

**Botões após resposta gerada:**
```
┌─────────────────────────────────────────────────────────────────┐
│ 📋 Copy   ⬇️ Export   🔄 Rewrite   📝 Open in editor    ⭐ ↗   │
└─────────────────────────────────────────────────────────────────┘
```

**Ações:**
| Botão | Ação | Atalho |
|-------|------|--------|
| Copy | Copia resposta para clipboard | Ctrl+C |
| Export | Exporta para Word/PDF | Ctrl+E |
| Rewrite | Regenera resposta | Ctrl+R |
| Open in editor | Abre no canvas para edição | Ctrl+O |
| ⭐ | Favorita resposta | - |
| ↗ | Compartilha | - |

### 12.4.8 SSE Event Types para Streaming

**Tipos de eventos SSE para implementar:**
```typescript
type SSEEventType =
  | { type: 'status'; data: { step: string; progress?: number } }
  | { type: 'thinking'; data: { content: string } }
  | { type: 'tool_call'; data: { name: string; input: any } }
  | { type: 'tool_result'; data: { name: string; result: any } }
  | { type: 'content'; data: { text: string; isPartial: boolean } }
  | { type: 'citation'; data: Citation }
  | { type: 'canvas_update'; data: { content: string; version: number } }
  | { type: 'follow_ups'; data: FollowUpSuggestion[] }
  | { type: 'complete'; data: { stepsCount: number; duration: number } }
  | { type: 'error'; data: { message: string; code: string } };
```

**Backend SSE Handler:**
```python
async def stream_response(
    agent_events: AsyncGenerator[AskEvent, None]
) -> StreamingResponse:
    async def generate():
        steps_count = 0
        start_time = time.time()

        async for event in agent_events:
            if event.type == "tool_call":
                steps_count += 1
                yield f"data: {json.dumps({'type': 'status', 'data': {'step': f'Using {event.tool_name}...'}})}\n\n"

            yield f"data: {json.dumps({'type': event.type, 'data': event.data})}\n\n"

        duration = time.time() - start_time
        yield f"data: {json.dumps({'type': 'complete', 'data': {'stepsCount': steps_count, 'duration': duration}})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )
```

---

## 13. Workflows Sugeridos para Iudex (BR)

Baseado nos workflows do Harvey, adaptados para o contexto jurídico brasileiro:

### Gerais
- [ ] Traduzir documento para outro idioma
- [ ] Revisar ortografia e gramática
- [ ] Gerar alerta para cliente
- [ ] Extrair cronograma de eventos-chave

### Contencioso
- [ ] Analisar depoimento para tópicos-chave
- [ ] Redigir memorando de pesquisa jurídica
- [ ] Resumir respostas e objeções de discovery
- [ ] Analisar petição adversária

### Transacional
- [ ] Resumir alterações materiais de redlines
- [ ] Extrair termos-chave de contratos
- [ ] Gerar checklist de due diligence
- [ ] Analisar cláusulas de change of control

### Jurisprudência BR
- [ ] Pesquisar precedentes no STJ/STF
- [ ] Verificar vigência de súmulas
- [ ] Comparar entendimentos entre tribunais
- [ ] Gerar memorial de jurisprudência

### Minutas
- [ ] Redigir petição inicial
- [ ] Redigir contestação
- [ ] Redigir recurso de apelação
- [ ] Redigir parecer jurídico

---

*Documento criado em: 2026-02-05*
*Atualizado em: 2026-02-05 (adicionado seção 12.4 - Streaming UI)*
*Autor: Claude (Assistente de Desenvolvimento)*
*Screenshots capturados: 21 imagens da UI do Harvey AI (12 estáticas + 9 de vídeos de streaming)*
