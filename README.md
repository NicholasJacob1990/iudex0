# Iudex - Plataforma Jurídica com IA Multi-Agente

## 🎯 Visão Geral

Iudex é uma plataforma jurídica avançada que utiliza múltiplos agentes de IA especializados (Claude Sonnet 4.5, Gemini 2.5 Pro, GPT-5) para produzir documentos jurídicos de alta qualidade, sem limitação de janela de contexto.

### ✨ Diferenciais

- **Multi-Agente IA**: Três agentes especializados revisando o trabalho uns dos outros
- **Contexto Ilimitado**: Sistema de divisão e unificação para documentos de qualquer tamanho
- **Interface Moderna**: UI/UX intuitiva inspirada nas melhores práticas do mercado
- **Recursos Avançados**: OCR, transcrição de audiências, geração de podcasts, diagramas visuais

## 🏗️ Arquitetura

```
Iudex/
├── apps/
│   ├── web/                 # Frontend Next.js
│   └── api/                 # Backend Node.js
├── packages/
│   ├── ui/                  # Componentes React compartilhados
│   ├── shared/              # Tipos e utils compartilhados
│   ├── ai-agents/           # Sistema de agentes IA
│   └── document-processor/  # Processamento de documentos
├── docs/                    # Documentação completa
└── status.md                # Status de implementação
```

## 🚀 Funcionalidades Principais

### Core
- ✅ Sistema de múltiplos agentes IA
- ✅ Processamento de documentos sem limite de contexto
- ✅ Compactação inteligente de tokens
- ✅ Editor de documentos com templates

### Abas de Contexto
- 📄 **Documentos**: Upload, OCR, importação de URLs, pastas
- 📋 **Modelos**: Templates DOCX personalizados
- ⚖️ **Legislação**: Busca e adição de artigos específicos
- ⚖️ **Jurisprudência**: Busca semântica em tribunais brasileiros
- 🌐 **Web**: Pesquisa automática na internet
- 📚 **Biblioteca**: Organização de recursos salvos
- 👥 **Bibliotecários**: Assistentes personalizados

### Recursos Avançados
- 🎙️ Transcrição de audiências com identificação de falantes
- 🎧 Geração de podcasts explicativos
- 📊 Diagramas visuais (mapas mentais)
- 🔗 Sistema de compartilhamento colaborativo
- 📰 Integração com DJEN (Diário da Justiça Eletrônico)
- 🏛️ Metadados CNJ

## 🛠️ Tecnologias

### Frontend
- Next.js 14+ (App Router)
- React 18+
- TypeScript
- Tailwind CSS
- Shadcn/ui
- TipTap (Editor WYSIWYG)
- React Query
- Zustand (State Management)

### Backend ⭐
- **Python 3.11+**
- **FastAPI** (framework moderno e rápido)
- **SQLAlchemy** (ORM async)
- **Alembic** (migrações)
- **PostgreSQL** (banco de dados)
- **Redis** (cache e sessões)
- **Celery** (processamento assíncrono)

### IA & ML ⭐ Sistema Multi-Agente
- **Claude Sonnet 4.5** (Anthropic) - Agente Gerador
- **Gemini 2.5 Pro** (Google) - Agente Revisor Legal
- **GPT-5** (OpenAI) - Agente Revisor Textual
- **LangChain** (orquestração)
- **Sentence Transformers** (embeddings)
- **Vector Database** (Pinecone/Qdrant/ChromaDB)
- **Whisper** (transcrição de áudio)

### Processamento ⭐
- **PyPDF** / **pdfplumber** (PDF)
- **python-docx** (DOCX)
- **pytesseract** (OCR)
- **Pillow** (processamento de imagem)
- **FFmpeg** + **pydub** (áudio/vídeo)
- **BeautifulSoup** (web scraping)
- **spaCy** / **NLTK** (NLP)

## 📦 Instalação

### Backend (Python/FastAPI)

```bash
cd apps/api

# Criar ambiente virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou venv\Scripts\activate no Windows

# Instalar dependências
pip install -r requirements.txt

# Configurar variáveis de ambiente
cp .env.example .env
# Editar .env com suas chaves de API

# Executar migrações
alembic upgrade head

# Iniciar servidor
python main.py
# API disponível em: http://localhost:8000
# Documentação: http://localhost:8000/docs
```

### Frontend (Next.js)

```bash
cd apps/web

# Instalar dependências
npm install

# Configurar variáveis de ambiente
cp .env.example .env.local

# Iniciar em modo desenvolvimento
npm run dev
# App disponível em: http://localhost:3000
```

## 🔧 Configuração

### Variáveis de Ambiente Essenciais

```env
# APIs de IA (OBRIGATÓRIAS) ⭐
OPENAI_API_KEY=sk-...           # GPT-5
ANTHROPIC_API_KEY=sk-ant-...    # Claude Sonnet 4.5
GOOGLE_API_KEY=...              # Gemini 2.5 Pro

# Banco de Dados
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/iudex
REDIS_URL=redis://localhost:6379/0

# Autenticação
JWT_SECRET_KEY=sua-chave-super-secreta
JWT_ALGORITHM=HS256

# Storage (opcional - use local em dev)
LOCAL_STORAGE_PATH=./storage
# Ou S3 em produção:
# S3_BUCKET=iudex-documents
# AWS_ACCESS_KEY_ID=...
# AWS_SECRET_ACCESS_KEY=...

# Features (opcional)
ENABLE_MULTI_AGENT=True
ENABLE_OCR=True
ENABLE_TRANSCRIPTION=True
```

## 📚 Documentação

- [Guia de Instalação](./docs/installation.md)
- [Arquitetura do Sistema](./docs/architecture.md)
- [API Reference](./docs/api-reference.md)
- [Sistema de Agentes IA](./docs/ai-agents.md)
- [Processamento de Documentos](./docs/document-processing.md)
- [Guia de Contribuição](./docs/contributing.md)

## 🔒 Segurança

- Autenticação JWT
- Criptografia end-to-end para documentos sensíveis
- Rate limiting
- Validação rigorosa de inputs
- Sanitização de dados

## 📈 Roadmap

### Fase 1: MVP (Em Progresso)
- [x] Estrutura base do projeto
- [ ] Sistema de autenticação
- [ ] Upload e processamento de documentos
- [ ] Integração com primeiro agente IA (Claude)
- [ ] Interface básica

### Fase 2: Multi-Agente
- [ ] Integração com Gemini e GPT
- [ ] Sistema de revisão cruzada
- [ ] Orquestração de agentes
- [ ] Sistema de votação/consenso

### Fase 3: Recursos Avançados
- [ ] OCR avançado
- [ ] Transcrição de audiências
- [ ] Geração de podcasts
- [ ] Diagramas visuais
- [ ] Busca de jurisprudência

### Fase 4: Colaboração
- [ ] Sistema de compartilhamento
- [ ] Grupos e permissões
- [ ] Bibliotecários compartilhados
- [ ] Notificações em tempo real

## 📄 Licença

MIT License - veja [LICENSE](./LICENSE) para mais detalhes.

## 📂 Arquivos Importantes

- **`QUICKSTART.md`** - Comece em 5 minutos ⚡
- **`BACKEND_COMPLETO.md`** - Documentação técnica completa 📖
- **`INTEGRACAO.md`** - Guia de integração frontend-backend 🔌
- **`RESUMO_FINAL.md`** - Visão geral do projeto entregue 🎉
- **`apps/api/README.md`** - Documentação da API 🐍
- **`apps/web/README.md`** - Documentação do frontend ⚛️

## 🤝 Contribuindo

Contribuições são bem-vindas! Por favor, leia o [Guia de Contribuição](./docs/contributing.md) antes de enviar um PR.

## 📞 Suporte

- Documentação: Veja os arquivos `.md` na raiz do projeto
- API Docs: http://localhost:8000/docs
- Exemplos: `apps/api/examples/`

---

**✨ Backend 100% Completo e Funcional ✅**  
**Desenvolvido com ❤️ e Python 🐍 para a comunidade jurídica brasileira**

