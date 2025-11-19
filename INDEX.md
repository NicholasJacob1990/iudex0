# 📖 Índice de Documentação - Iudex

Guia completo para navegar em toda a documentação do projeto.

---

## 🚀 Para Começar

### Novos no Projeto?
1. **`README.md`** ← Comece aqui! Visão geral completa
2. **`RESUMO_FINAL.md`** ← O que foi entregue
3. **`QUICKSTART.md`** ← Rode em 5 minutos

### Quer Testar Agora?
1. **`QUICKSTART.md`** - Setup em 5 minutos
2. **`apps/api/examples/usage_example.py`** - Exemplo prático

---

## 📚 Documentação Técnica

### Backend (Python/FastAPI)
- **`BACKEND_COMPLETO.md`** - Documentação completa do backend ⭐
- **`apps/api/README.md`** - Guia da API
- **`apps/api/.env.example`** - Variáveis de ambiente
- **`apps/api/alembic.ini`** - Configuração de migrações

### Frontend (Next.js)
- **`apps/web/README.md`** - Documentação do frontend
- **`INTEGRACAO.md`** - Como integrar frontend-backend ⭐

### Shared (TypeScript)
- **`packages/shared/`** - Tipos compartilhados

---

## 🎯 Guias Específicos

### Desenvolvimento
- **`QUICKSTART.md`** - Setup rápido
- **`INTEGRACAO.md`** - Integração frontend-backend
- **`PROXIMOS_PASSOS.md`** - O que implementar a seguir ⭐

### Arquitetura
- **`BACKEND_COMPLETO.md`** - Arquitetura detalhada
- **`IMPLEMENTACAO.md`** - Resumo da implementação

### Status
- **`status.md`** - Acompanhamento de progresso
- **`RESUMO_FINAL.md`** - Resumo executivo ⭐

---

## 🤖 Sistema Multi-Agente IA

### Conceitos
- **`BACKEND_COMPLETO.md`** → Seção "Sistema Multi-Agente"
- **`apps/api/app/services/ai/`** → Código fonte

### Como Usar
```python
# Ver: apps/api/examples/usage_example.py
from app.services.ai.orchestrator import MultiAgentOrchestrator

orchestrator = MultiAgentOrchestrator()
result = await orchestrator.generate_document(
    prompt="Elabore uma petição inicial...",
    context={...},
    effort_level=5  # Máximo esforço
)
```

### Arquivos Importantes
- `apps/api/app/services/ai/orchestrator.py` - Coordenador
- `apps/api/app/services/ai/agents.py` - Agentes (Claude, Gemini, GPT)
- `apps/api/app/services/ai/base_agent.py` - Classe base

---

## 📄 Processamento de Documentos

### Contexto Ilimitado
- **`BACKEND_COMPLETO.md`** → Seção "Processamento"
- **`apps/api/app/services/document_processor.py`** → Implementação

### Estratégias
1. **Map-Reduce** - Paralelo
2. **Hierarchical** - Níveis
3. **Rolling Window** - Janela deslizante

### Código
```python
from app.services.document_processor import UnlimitedContextProcessor

processor = UnlimitedContextProcessor()
result = await processor.process_large_document(
    text=huge_document,
    task="Resumir",
    strategy="map-reduce"
)
```

---

## 🔍 Busca Semântica

### Conceitos
- **`BACKEND_COMPLETO.md`** → Seção "Busca Semântica"
- **`apps/api/app/services/embedding_service.py`** → Implementação

### Uso
```python
from app.services.embedding_service import SemanticSearchService

search = SemanticSearchService()
results = await search.search(
    query="danos morais por negativação",
    top_k=10
)
```

---

## 🔌 API REST

### Documentação Interativa
- **http://localhost:8000/docs** - Swagger UI
- **http://localhost:8000/redoc** - ReDoc

### Endpoints Principais
```
/api/auth/*          - Autenticação
/api/users/*         - Usuários
/api/documents/*     - Documentos
/api/chats/*         - Chat e Minutas
/api/library/*       - Biblioteca
```

### Referência Completa
- **`apps/api/README.md`** → Seção "Endpoints"

---

## ⚙️ Workers Celery

### Documentação
- **`BACKEND_COMPLETO.md`** → Seção "Workers"
- **`apps/api/app/workers/`** → Código fonte

### Tasks Disponíveis
```python
# Processamento de documento
process_document.delay(document_id, user_id, file_path)

# OCR
ocr_document.delay(document_id, file_path)

# Transcrição
transcribe_audio.delay(document_id, audio_path)

# Geração com IA
generate_document.delay(chat_id, prompt, context)
```

### Iniciar Workers
```bash
celery -A app.workers.celery_app worker --loglevel=info
celery -A app.workers.celery_app flower  # Monitor
```

---

## 🎨 Frontend

### Setup
- **`apps/web/README.md`** - Guia completo
- **`apps/web/package.json`** - Dependências

### Integração com Backend
- **`INTEGRACAO.md`** - Guia detalhado ⭐

### Stack
- Next.js 14
- React 18 + TypeScript
- Tailwind CSS + Shadcn/ui
- TipTap (editor)
- React Query + Zustand

---

## 📋 Próximos Passos

### O Que Falta Implementar
- **`PROXIMOS_PASSOS.md`** - Roadmap detalhado ⭐

### Ordem Recomendada
1. Extração real de PDF/DOCX
2. Embeddings e vector store
3. Setup frontend Next.js
4. Autenticação
5. Editor e chat
6. OCR e transcrição
7. Integrações externas

---

## 🐛 Troubleshooting

### Problemas Comuns
- **`QUICKSTART.md`** → Seção "Problemas Comuns"

### Logs
```bash
# API logs
tail -f logs/iudex-api.log

# Worker logs
celery -A app.workers.celery_app inspect active
```

---

## 📊 Estrutura do Projeto

```
Iudex/
├── apps/
│   ├── api/           # Backend Python/FastAPI ✅
│   │   ├── app/
│   │   │   ├── api/           # Endpoints
│   │   │   ├── core/          # Config, DB, Security
│   │   │   ├── models/        # SQLAlchemy models
│   │   │   ├── schemas/       # Pydantic schemas
│   │   │   ├── services/      # Lógica de negócio
│   │   │   │   ├── ai/        # Multi-Agente ⭐
│   │   │   │   ├── document_processor.py
│   │   │   │   └── embedding_service.py
│   │   │   ├── workers/       # Celery tasks
│   │   │   └── utils/         # Utilitários
│   │   ├── examples/          # Exemplos de uso
│   │   └── README.md          # Docs da API
│   │
│   └── web/           # Frontend Next.js 📋
│       ├── src/
│       │   ├── app/           # Next.js App Router
│       │   ├── components/    # React components
│       │   ├── lib/           # API client, hooks
│       │   └── stores/        # Zustand stores
│       └── README.md          # Docs do frontend
│
├── packages/
│   └── shared/        # Tipos TypeScript compartilhados ✅
│
├── docs/              # Documentação adicional
│
├── README.md          # Visão geral ⭐
├── QUICKSTART.md      # Setup rápido ⭐
├── BACKEND_COMPLETO.md    # Docs técnicas backend ⭐
├── INTEGRACAO.md      # Frontend-Backend ⭐
├── PROXIMOS_PASSOS.md # Roadmap ⭐
├── RESUMO_FINAL.md    # Resumo executivo ⭐
├── IMPLEMENTACAO.md   # Resumo da implementação
├── status.md          # Status do projeto
├── LICENSE            # MIT License
└── INDEX.md           # Este arquivo
```

---

## 🔗 Links Rápidos

### Desenvolvimento
- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [Next.js Docs](https://nextjs.org/docs)
- [React Query](https://tanstack.com/query/latest)
- [Shadcn/ui](https://ui.shadcn.com/)

### IA/ML
- [LangChain](https://python.langchain.com/)
- [Sentence Transformers](https://www.sbert.net/)
- [OpenAI API](https://platform.openai.com/docs)
- [Anthropic Claude](https://docs.anthropic.com/)

### Infraestrutura
- [PostgreSQL](https://www.postgresql.org/docs/)
- [Redis](https://redis.io/docs/)
- [Celery](https://docs.celeryq.dev/)
- [Docker](https://docs.docker.com/)

---

## 📞 Suporte

### Documentação
- Leia os arquivos `.md` na raiz do projeto
- API Docs: http://localhost:8000/docs
- Exemplos: `apps/api/examples/`

### Código
- Backend: `apps/api/app/`
- Frontend: `apps/web/src/`
- Shared: `packages/shared/src/`

---

## ⭐ Arquivos Mais Importantes

Para diferentes necessidades:

**Quero começar agora:**
→ `QUICKSTART.md`

**Quero entender a arquitetura:**
→ `BACKEND_COMPLETO.md`

**Quero integrar frontend:**
→ `INTEGRACAO.md`

**Quero continuar o desenvolvimento:**
→ `PROXIMOS_PASSOS.md`

**Quero ver o que foi entregue:**
→ `RESUMO_FINAL.md`

**Quero usar o sistema multi-agente:**
→ `apps/api/examples/usage_example.py`

---

**✨ Use este índice como mapa de navegação do projeto!**

**Status**: Documentação 100% completa ✅

