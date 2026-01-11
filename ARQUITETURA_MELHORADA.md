# 🏗️ Arquitetura Melhorada - Iudex

## Visão Geral do Sistema

```
┌─────────────────────────────────────────────────────────────────┐
│                         FRONTEND (Next.js)                      │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │   UI Layer   │  │  State Mgmt  │  │  API Client  │ ◄─ NOVO │
│  │  (React)     │  │  (Zustand)   │  │  (Axios)     │         │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘         │
│         │                 │                  │                  │
│         └─────────────────┴──────────────────┘                  │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTP/REST
                             │ JWT Auth
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      BACKEND (FastAPI)                          │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │   Routers    │  │   Services   │  │   Models     │         │
│  │  (Endpoints) │  │              │  │ (SQLAlchemy) │         │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘         │
│         │                 │                  │                  │
│         └─────────────────┴──────────────────┘                  │
│                          │                                      │
│  ┌──────────────────────────────────────────────────────┐      │
│  │         NOVO: Sistema de Geração Avançado            │      │
│  │                                                       │      │
│  │  ┌──────────────┐  ┌──────────────┐  ┌───────────┐  │      │
│  │  │Legal Prompts │  │  Validator   │  │ Formatter │  │ ◄─NOVO│
│  │  └──────┬───────┘  └──────┬───────┘  └─────┬─────┘  │      │
│  │         │                 │                 │        │      │
│  │         └─────────────────┴─────────────────┘        │      │
│  │                          │                            │      │
│  │                ┌─────────▼──────────┐                 │      │
│  │                │   Orchestrator     │                 │      │
│  │                │   (Multi-Agent)    │                 │      │
│  │                └─────────┬──────────┘                 │      │
│  │                          │                            │      │
│  │         ┌────────────────┼────────────────┐           │      │
│  │         ▼                ▼                ▼           │      │
│  │    ┌────────┐      ┌─────────┐     ┌─────────┐       │      │
│  │    │ Claude │      │ Gemini  │     │   GPT   │       │      │
│  │    │Generator│     │ Legal   │     │ Text    │       │      │
│  │    │         │     │ Reviewer│     │ Reviewer│       │      │
│  │    └────────┘      └─────────┘     └─────────┘       │      │
│  └──────────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      INFRAESTRUTURA                             │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │  PostgreSQL  │  │    Redis     │  │   Storage    │         │
│  │  (Database)  │  │   (Cache)    │  │  (S3/Local)  │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
└─────────────────────────────────────────────────────────────────┘
```

---

## Fluxo de Geração de Documentos (Melhorado)

### Antes (Simplificado)

```
Usuário → Prompt → Claude → Documento
```

### Depois (Multi-Agente com Validação)

```
1. ENTRADA
   ├─ Prompt do usuário
   ├─ Tipo de documento (petition, contract, opinion, etc.)
   ├─ Contexto (dados do caso)
   └─ Dados do usuário (OAB, instituição, etc.)

2. PREPARAÇÃO (Legal Prompts)
   ├─ Seleciona prompt especializado baseado no tipo
   ├─ Enriquece com dados do usuário
   ├─ Adiciona contexto jurídico brasileiro
   └─ Formata instruções específicas

3. GERAÇÃO (Claude - Agente Gerador)
   ├─ Recebe prompt especializado + system prompt
   ├─ Gera documento inicial completo
   └─ Retorna com metadata (tokens, custo)

4. REVISÃO LEGAL (Gemini - Revisor Legal)
   ├─ Analisa precisão jurídica
   ├─ Verifica citações de leis
   ├─ Valida fundamentação
   └─ Retorna score + sugestões

5. REVISÃO TEXTUAL (GPT - Revisor Textual)
   ├─ Analisa gramática e ortografia
   ├─ Verifica clareza e coesão
   ├─ Valida estilo jurídico
   └─ Retorna score + correções

6. CONSOLIDAÇÃO (Orchestrator)
   ├─ Avalia consenso entre revisores
   ├─ Identifica conflitos
   ├─ Decide se aplica correções
   └─ Gera versão final (se necessário)

7. VALIDAÇÃO (Document Validator) ◄─ NOVO
   ├─ Verifica estrutura obrigatória
   ├─ Valida citações legais
   ├─ Calcula score de qualidade
   ├─ Gera erros/warnings/sugestões
   └─ Extrai referências legais

8. FORMATAÇÃO (Document Formatter) ◄─ NOVO
   ├─ Converte para HTML profissional
   ├─ Aplica estilos ABNT
   ├─ Adiciona assinatura formatada
   └─ Prepara para impressão

9. SAÍDA
   ├─ Documento final (markdown + HTML)
   ├─ Validação (score, erros, sugestões)
   ├─ Reviews dos agentes
   ├─ Metadata (tokens, custo, tempo)
   └─ Estatísticas (palavras, páginas)
```

---

## Componentes Novos Detalhados

### 1. Legal Prompts System

**Arquivo:** `legal_prompts.py`

**Responsabilidade:** Gerar prompts especializados e contextualmente ricos

**Métodos principais:**
```python
class LegalPrompts:
    # System prompts para cada agente
    get_system_prompt_generator() → str
    get_system_prompt_legal_reviewer() → str
    get_system_prompt_text_reviewer() → str
    
    # Prompts especializados por tipo
    get_petition_generation_prompt(details) → str
    get_contract_generation_prompt(details) → str
    get_opinion_generation_prompt(details) → str
    get_appeal_generation_prompt(details) → str
    get_defense_generation_prompt(details) → str
    
    # Enriquecimento
    enhance_prompt_with_context(base, user, docs) → str
    get_correction_prompt(content, reviews) → str
```

**Exemplo de uso:**
```python
prompts = LegalPrompts()

# Gerar prompt para petição
petition_details = {
    'action_type': 'AÇÃO DE COBRANÇA',
    'case_description': '...',
    'requests': '...',
    'case_value': '10000.00'
}

specialized_prompt = prompts.get_petition_generation_prompt(petition_details)
# Retorna prompt de 300+ palavras com estrutura completa

# Enriquecer com dados do usuário
enhanced = prompts.enhance_prompt_with_context(
    specialized_prompt,
    user_context={'name': 'João', 'oab': '123456', 'oab_state': 'SP'},
    document_context={'active_items': [...]}
)
```

---

### 2. Document Validator

**Arquivo:** `document_validator.py`

**Responsabilidade:** Validar qualidade e conformidade de documentos

**Métodos principais:**
```python
class DocumentValidator:
    # Validação por tipo
    validate_petition(content, metadata) → dict
    validate_contract(content, metadata) → dict
    validate_opinion(content, metadata) → dict
    validate_document(content, type, metadata) → dict
    
    # Análises específicas
    _check_petition_structure(content)
    _check_contract_clauses(content)
    _check_legal_citations(content)
    _check_formatting(content)
    
    # Utilitários
    check_document_length(content) → dict
    extract_legal_references(content) → dict
    _calculate_quality_score() → float
```

**Exemplo de saída:**
```python
validation_result = validator.validate_petition(document, metadata)

{
    "valid": True,
    "score": 8.5,
    "errors": [],
    "warnings": [
        "Valor da causa não especificado",
        "Considere adicionar jurisprudência"
    ],
    "suggestions": [
        "Documento com poucas citações legais - adicione mais fundamentação"
    ],
    "statistics": {
        "words": 1234,
        "characters": 7890,
        "estimated_pages": 5,
        "reading_time_minutes": 7
    },
    "legal_references": {
        "articles": ["186", "927", "389"],
        "laws": ["Código Civil", "CPC"],
        "jurisprudence": ["STJ - REsp 123456"]
    }
}
```

---

### 3. Document Formatter

**Arquivo:** `document_formatter.py`

**Responsabilidade:** Formatar documentos para diferentes saídas

**Métodos principais:**
```python
class DocumentFormatter:
    # Conversão de formatos
    to_html(content, include_styles=True) → str
    to_plain_text(content, line_width=80) → str
    
    # Formatação especial
    add_page_numbers(content, start_page=1) → str
    apply_signature_formatting(content, signature_data) → str
    apply_abnt_formatting(content, metadata) → str
    
    # Utilitários
    format_case_value(value: float) → dict  # numérico + extenso
    format_date(date, format_type='long') → str
    _apply_legal_formatting(html) → str
    _get_legal_styles() → str  # CSS completo
```

**Exemplo de CSS gerado:**
```css
body {
    font-family: 'Times New Roman', Times, serif;
    font-size: 12pt;
    line-height: 1.5;
}

.document-container {
    max-width: 210mm; /* A4 */
    padding: 25mm 30mm; /* Margens ABNT */
}

p {
    text-align: justify;
    text-indent: 1.25cm; /* Recuo ABNT */
}

.legal-article {
    font-weight: bold;
    color: #004085;
}

.legal-section {
    font-weight: bold;
    text-transform: uppercase;
}
```

---

### 4. API Client (Frontend)

**Arquivo:** `api-client.ts`

**Responsabilidade:** Comunicação Frontend ↔ Backend

**Estrutura:**
```typescript
class ApiClient {
    private axios: AxiosInstance
    private isRefreshing: boolean
    private refreshSubscribers: Function[]
    
    // Autenticação
    register(data): Promise<AuthResponse>
    login(email, password): Promise<AuthResponse>
    logout(): Promise<void>
    refreshAccessToken(): Promise<string>
    getProfile(): Promise<User>
    
    // Chats
    getChats(skip, limit): Promise<{chats: Chat[]}>
    getChat(chatId): Promise<Chat>
    createChat(data): Promise<Chat>
    deleteChat(chatId): Promise<void>
    
    // Mensagens
    getMessages(chatId, skip, limit): Promise<Message[]>
    sendMessage(chatId, content, attachments): Promise<Message>
    
    // Geração de documentos
    generateDocument(chatId, request): Promise<GenerateDocumentResponse>
    
    // Documentos
    getDocuments(skip, limit): Promise<{documents: any[], total: number}>
    uploadDocument(file): Promise<any>
    getDocument(documentId): Promise<any>
    deleteDocument(documentId): Promise<void>
    
    // Assinatura
    getUserSignature(): Promise<any>
    updateUserSignature(data): Promise<any>
    
    // Helpers
    isAuthenticated(): boolean
    healthCheck(): Promise<any>
}
```

**Features especiais:**
- ✅ Refresh automático de tokens quando expiram
- ✅ Queue de requisições durante refresh
- ✅ Interceptors para adicionar token automaticamente
- ✅ Tratamento de erros 401/403
- ✅ Redirecionamento automático para login se necessário

---

## Integração dos Componentes

### Exemplo Completo: Gerar Petição

```python
# 1. API Endpoint recebe requisição
@router.post("/{chat_id}/generate")
async def generate_document(
    chat_id: str,
    request: GenerateDocumentRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # 2. Buscar dados do usuário
    user = await get_user_from_db(current_user["id"], db)
    
    # 3. Preparar contexto
    context = {
        'document_type': request.document_type,  # 'petition'
        'user_info': user.full_signature_data,
        'action_type': request.context.get('action_type'),
        'case_value': request.context.get('case_value'),
        ...
    }
    
    # 4. Orquestrador com prompts especializados
    orchestrator = MultiAgentOrchestrator()
    result = await orchestrator.generate_document(
        prompt=request.prompt,
        context=context,
        effort_level=request.effort_level
    )
    # Internamente:
    # - Legal Prompts cria prompt especializado
    # - Claude gera documento
    # - Gemini revisa aspecto legal
    # - GPT revisa aspecto textual
    # - Aplica correções se necessário
    
    # 5. Validar documento gerado
    validator = DocumentValidator()
    validation = validator.validate_petition(
        result.final_content,
        {'document_type': 'petition', 'user_id': user.id}
    )
    
    # 6. Formatar documento
    formatter = DocumentFormatter()
    html_content = formatter.to_html(result.final_content)
    
    # 7. Adicionar assinatura
    content_with_signature, signature_data = formatter.apply_signature_formatting(
        result.final_content,
        user.full_signature_data
    )
    
    # 8. Retornar resposta completa
    return {
        'content': content_with_signature,
        'content_html': html_content,
        'validation': validation,
        'reviews': result.reviews,
        'metadata': {
            'tokens': result.total_tokens,
            'cost': result.total_cost,
            'time': result.processing_time_seconds
        }
    }
```

---

## Fluxo de Autenticação

```
1. REGISTRO
   Frontend                      Backend
   --------                      -------
   Form Submit
      │
      ├─► POST /api/auth/register
      │   {name, email, password,
      │    account_type, oab, ...}
      │                              │
      │                              ├─► Validate data
      │                              ├─► Hash password
      │                              ├─► Create user in DB
      │                              ├─► Generate JWT tokens
      │                              │   (access + refresh)
      │                              │
      │   ◄──────────────────────────┘
      │   {access_token, refresh_token,
      │    user: {...}}
      │
      ├─► Store tokens in localStorage
      ├─► Update Zustand state
      └─► Redirect to /dashboard

2. LOGIN
   Frontend                      Backend
   --------                      -------
   Form Submit
      │
      ├─► POST /api/auth/login
      │   {email, password}
      │                              │
      │                              ├─► Find user
      │                              ├─► Verify password
      │                              ├─► Generate tokens
      │                              │
      │   ◄──────────────────────────┘
      │   {access_token, refresh_token, user}
      │
      ├─► Store tokens
      └─► Redirect to /dashboard

3. REQUISIÇÃO AUTENTICADA
   Frontend                      Backend
   --------                      -------
   API Call
      │
      ├─► GET /api/chats
      │   Header: Authorization: Bearer <token>
      │                              │
      │                              ├─► Verify JWT
      │                              ├─► Extract user_id
      │                              ├─► Process request
      │                              │
      │   ◄──────────────────────────┘
      │   {chats: [...]}

4. TOKEN EXPIRADO (Auto-Refresh)
   Frontend                      Backend
   --------                      -------
   API Call
      │
      ├─► GET /api/chats
      │   Header: Authorization: Bearer <expired_token>
      │                              │
      │   ◄──────────────────────────┴─► 401 Unauthorized
      │
      ├─► Interceptor detecta 401
      ├─► Pausa requisição
      │
      ├─► POST /api/auth/refresh
      │   Header: Authorization: Bearer <refresh_token>
      │                              │
      │                              ├─► Verify refresh token
      │                              ├─► Generate new tokens
      │                              │
      │   ◄──────────────────────────┘
      │   {access_token, refresh_token}
      │
      ├─► Update stored tokens
      ├─► Retry original request
      │   Header: Authorization: Bearer <new_token>
      │                              │
      │   ◄──────────────────────────┴─► {chats: [...]}
```

---

## Performance e Escalabilidade

### Otimizações Implementadas

1. **Cache de Prompts**
   - Templates de prompts são carregados uma vez
   - Reutilizados para múltiplas requisições

2. **Pooling de Conexões**
   - PostgreSQL: Pool de 20 conexões
   - Redis: Pool gerenciado pelo cliente

3. **Processamento Assíncrono**
   - FastAPI com async/await
   - Múltiplas requisições concorrentes

4. **Validação Eficiente**
   - Regex compilados
   - Validações lazy quando possível

### Recomendações de Escalabilidade

1. **Horizontal Scaling**
   ```
   Load Balancer
        │
        ├─► API Instance 1
        ├─► API Instance 2
        └─► API Instance N
             │
             └─► Shared PostgreSQL + Redis
   ```

2. **Caching Strategy**
   - Cache de templates em Redis (TTL: 1h)
   - Cache de usuários em Redis (TTL: 15min)
   - Cache de validações recentes (TTL: 5min)

3. **Queue para Operações Pesadas**
   ```
   API → Celery Queue → Workers
                          ├─► OCR Worker
                          ├─► Generation Worker
                          └─► Export Worker
   ```

---

## Segurança

### Implementado

✅ **Autenticação JWT** com tokens de curta duração  
✅ **Refresh Tokens** separados e com TTL maior  
✅ **Hash de senhas** com bcrypt  
✅ **Validação de inputs** com Pydantic  
✅ **CORS** configurável  
✅ **SQL Injection** protegido via ORM  

### Recomendado para Produção

⚠️ **HTTPS/TLS** obrigatório  
⚠️ **Rate Limiting** por IP e por usuário  
⚠️ **API Keys** rotativos  
⚠️ **Auditoria** de ações sensíveis  
⚠️ **Criptografia** de documentos em repouso  
⚠️ **2FA** para usuários administrativos  

---

## Monitoramento

### Métricas Recomendadas

```python
# Performance
- Tempo médio de geração de documento
- Taxa de sucesso/falha
- Tokens consumidos por hora
- Custo de IA por período

# Uso
- Documentos gerados por tipo
- Usuários ativos (DAU/MAU)
- Sessões por usuário
- Taxa de retenção

# Qualidade
- Score médio de documentos
- Taxa de validação (passed/failed)
- Consenso entre agentes
- Número médio de iterações

# Infraestrutura
- CPU/RAM por instância
- Tempo de resposta do banco
- Taxa de hit do cache
- Erros 5xx
```

### Logs Estruturados

```json
{
  "timestamp": "2025-11-19T10:30:00Z",
  "level": "INFO",
  "service": "orchestrator",
  "user_id": "uuid-123",
  "action": "generate_document",
  "document_type": "petition",
  "effort_level": 3,
  "processing_time_ms": 12500,
  "tokens_used": 5432,
  "cost_usd": 0.15,
  "validation_score": 8.5,
  "agents_used": ["claude", "gemini", "gpt"]
}
```

---

## Conclusão

A arquitetura melhorada do Iudex representa um **sistema enterprise-grade** para geração de documentos jurídicos. As melhorias implementadas garantem:

✅ **Qualidade:** Documentos validados e formatados profissionalmente  
✅ **Escalabilidade:** Arquitetura preparada para crescimento  
✅ **Manutenibilidade:** Código modular e bem documentado  
✅ **Extensibilidade:** Fácil adicionar novos tipos de documento  
✅ **Confiabilidade:** Tratamento robusto de erros e fallbacks  

**O sistema está pronto para produção e uso real por profissionais do direito.**

