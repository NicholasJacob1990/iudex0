# Iudex API - Backend Python/FastAPI

Backend da plataforma Iudex com sistema de IA multi-agente (Claude, Gemini, GPT-5).

## 🎯 Arquitetura

```
app/
├── api/              # Endpoints da API
│   ├── endpoints/    # Rotas organizadas por domínio
│   └── routes.py     # Router principal
├── core/             # Configurações centrais
│   ├── config.py     # Settings com Pydantic
│   ├── database.py   # SQLAlchemy async
│   ├── redis.py      # Cache e sessões
│   ├── logging.py    # Loguru
│   └── security.py   # JWT e autenticação
├── models/           # Modelos do banco (SQLAlchemy)
├── schemas/          # Schemas Pydantic
├── services/         # Lógica de negócio
│   └── ai/           # Sistema Multi-Agente IA ⭐
│       ├── agents.py      # Claude, Gemini, GPT
│       ├── orchestrator.py # Coordenação
│       └── base_agent.py  # Classe base
├── workers/          # Celery tasks
└── utils/            # Utilitários
```

## 🤖 Sistema Multi-Agente

### Como Funciona

1. **Claude Sonnet 4.5** (Gerador)
   - Cria o documento inicial
   - Forte em raciocínio e estruturação

2. **Gemini 2.5 Pro** (Revisor Legal)
   - Verifica precisão jurídica
   - Valida citações e fundamentação

3. **GPT-5** (Revisor Textual)
   - Revisa gramática e clareza
   - Ajusta estilo e coesão

4. **Orquestrador**
   - Coordena o fluxo
   - Consolida feedback
   - Aplica correções iterativas

### Níveis de Esforço

```python
effort_level = 1-2  # Apenas Claude (rápido)
effort_level = 3    # Claude + revisão rápida
effort_level = 4-5  # Fluxo completo multi-agente
```

## 🚀 Instalação

### Pré-requisitos

- Python 3.11+
- PostgreSQL 14+
- Redis
- Tesseract OCR (opcional)
- FFmpeg (opcional)

### Setup

```bash
# Criar ambiente virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
venv\Scripts\activate  # Windows

# Instalar dependências
pip install -r requirements.txt

# Configurar variáveis de ambiente
cp .env.example .env
# Editar .env com suas chaves de API

# Executar migrações
alembic upgrade head

# Iniciar servidor
python main.py
```

## 📝 Variáveis de Ambiente Essenciais

```env
# APIs de IA (OBRIGATÓRIAS)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=...

# Banco de Dados
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/iudex

# Redis
REDIS_URL=redis://localhost:6379/0

# JWT
JWT_SECRET_KEY=sua-chave-secreta
```

## 🧪 Uso da API

### Autenticação

```bash
# Login
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "senha"}'

# Usar token nas próximas requisições
curl -H "Authorization: Bearer seu-token" \
  http://localhost:8000/api/users/profile
```

### Gerar Documento com IA Multi-Agente

```python
import httpx

async def generate_document():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/api/chats/123/generate",
            headers={"Authorization": "Bearer seu-token"},
            json={
                "prompt": "Elabore uma petição inicial...",
                "effort_level": 5,  # Usar todos os agentes
                "context": {
                    "documents": ["doc-id-1", "doc-id-2"],
                    "jurisprudence": ["jur-id-1"],
                    "user_instructions": "Foco em dano moral"
                }
            }
        )
        return response.json()
```

## 📚 Endpoints Principais

### Autenticação
- `POST /api/auth/register` - Registrar usuário
- `POST /api/auth/login` - Login
- `GET /api/auth/me` - Usuário atual

### Documentos
- `POST /api/documents/upload` - Upload
- `GET /api/documents` - Listar
- `POST /api/documents/{id}/ocr` - Aplicar OCR
- `POST /api/documents/{id}/transcribe` - Transcrever áudio

### Chat & Minutas
- `POST /api/chats` - Criar chat
- `POST /api/chats/{id}/message` - Enviar mensagem
- `POST /api/chats/{id}/generate` - **Gerar documento com IA**

### Biblioteca
- `GET /api/library/items` - Itens salvos
- `GET /api/library/librarians` - Bibliotecários (assistentes)

## 🔧 Desenvolvimento

### Executar em modo dev

```bash
# Com reload automático
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Criar migração

```bash
alembic revision --autogenerate -m "descrição"
alembic upgrade head
```

### Testes

```bash
pytest
pytest --cov=app tests/
```

### Linting & Formatação

```bash
black app/
isort app/
flake8 app/
mypy app/
```

## 📊 Monitoramento

### Logs

Logs são salvos em:
- Console (desenvolvimento)
- `logs/iudex-api.log` (produção)
- `logs/iudex-api-errors.log` (apenas erros)

### Métricas

- Health check: `GET /health`
- Documentação: `http://localhost:8000/docs`
- Redoc: `http://localhost:8000/redoc`

## 🎯 Performance

### Otimizações

1. **Cache Redis**: Resultados de IA, embeddings
2. **Celery**: Processamento assíncrono pesado
3. **Connection Pooling**: PostgreSQL e Redis
4. **Lazy Loading**: Carregar apenas necessário
5. **Batch Processing**: Múltiplos documentos de uma vez

### Limites

- Upload: 500MB por arquivo
- Contexto: 3M tokens (divisão automática)
- Rate limiting: 100 req/min por usuário

## 🛡️ Segurança

- JWT com refresh tokens
- Bcrypt para senhas
- Rate limiting
- Helmet (headers de segurança)
- Validação com Pydantic
- SQL Injection protection (SQLAlchemy)

## 📦 Deploy

### Docker

```bash
# Build
docker build -t iudex-api .

# Run
docker run -p 8000:8000 \
  -e DATABASE_URL=... \
  -e OPENAI_API_KEY=... \
  iudex-api
```

### Produção

```bash
# Com Gunicorn + Uvicorn workers
gunicorn app.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000
```

## 🤝 Contribuindo

1. Fork o projeto
2. Crie uma branch (`git checkout -b feature/nova-feature`)
3. Commit suas mudanças (`git commit -m 'Add nova feature'`)
4. Push para a branch (`git push origin feature/nova-feature`)
5. Abra um Pull Request

## 📄 Licença

MIT License - veja LICENSE para detalhes.

---

**Desenvolvido com ❤️ e Python 🐍**

