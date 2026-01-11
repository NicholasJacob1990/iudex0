# ⚡ Guia Rápido - Iudex

**Tempo estimado**: 10 minutos

---

## 🚀 Instalação Rápida

### Pré-requisitos
- Python 3.11+
- Node.js 18+
- PostgreSQL 15+
- Redis 7+

### 1. Clone e Setup

```bash
# Clone o repositório
git clone <repo-url>
cd Iudex

# Copie este guia como referência
```

### 2. Backend (Python/FastAPI)

```bash
cd apps/api

# Crie ambiente virtual
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Instale dependências
pip install -r requirements.txt

# Configure variáveis de ambiente
cat > .env << EOF
# Mínimo necessário para começar
SECRET_KEY=sua-chave-secreta-minimo-32-caracteres-aqui
JWT_SECRET_KEY=sua-chave-jwt-minimo-32-caracteres-aqui

# Banco de dados local
DATABASE_URL=postgresql+asyncpg://iudex:iudex123@localhost:5432/iudex

# Redis local
REDIS_URL=redis://localhost:6379/0

# Chaves de IA (obtenha gratuitamente)
OPENAI_API_KEY=sk-sua-chave-openai
ANTHROPIC_API_KEY=sk-ant-sua-chave-anthropic
GOOGLE_API_KEY=sua-chave-google
EOF

# Execute migrações
alembic upgrade head

# Inicie o servidor
python main.py
```

**Backend rodando em**: http://localhost:8000
**Documentação API**: http://localhost:8000/docs

### 3. Frontend (Next.js)

```bash
cd apps/web

# Instale dependências
npm install

# Configure variáveis de ambiente
cat > .env.local << EOF
NEXT_PUBLIC_API_URL=http://localhost:8000/api
EOF

# Inicie em desenvolvimento
npm run dev
```

**Frontend rodando em**: http://localhost:3000

---

## 🎯 Uso Rápido

### 1. Primeiro Acesso

1. Acesse: http://localhost:3000
2. Clique em "Cadastrar"
3. Escolha seu tipo de conta:
   - **Individual**: Para advogados autônomos (requer OAB)
   - **Institucional**: Para escritórios (requer CNPJ)

### 2. Dados de Teste

**Usuário Individual**:
```
Nome: Dr. João Silva
Email: joao@teste.com
Senha: Teste@123456
OAB: 123456
Estado: SP
CPF: 123.456.789-09 (use um CPF válido)
```

**Usuário Institucional**:
```
Nome: Maria Santos
Email: maria@escritorio.com
Senha: Teste@123456
Instituição: Silva & Advogados
CNPJ: 12.345.678/0001-90 (use um CNPJ válido)
Cargo: Sócia
Equipe: 10
```

### 3. Login

1. Use email e senha cadastrados
2. Token JWT será armazenado automaticamente
3. Refresh automático quando expirar

### 4. Gerar Documento Jurídico

#### Opção A: Com Template

```bash
# Via API diretamente
curl -X POST http://localhost:8000/api/templates/render \
  -H "Authorization: Bearer SEU_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "template_id": "peticao_inicial_civel",
    "variables": {
      "juizo": "1ª Vara Cível",
      "comarca": "São Paulo",
      "autor_nome": "João Silva",
      "reu_nome": "Maria Santos",
      "tipo_acao": "AÇÃO DE COBRANÇA",
      "causa_pedir": "O autor prestou serviços...",
      "fundamentacao_juridica": "Conforme art. 389 do CC...",
      "pedidos": "a) Condenação...",
      "valor_causa": "R$ 10.000,00"
    }
  }'
```

#### Opção B: Com IA Multi-Agente

1. Crie um chat
2. Envie prompt: "Criar petição inicial de ação de cobrança contra Maria Santos..."
3. Escolha nível de esforço:
   - **1-2**: Rápido (só Claude, ~10s)
   - **3**: Balanceado (Claude + 1 revisão, ~20s)
   - **4-5**: Qualidade máxima (multi-agente completo, ~40s)
4. Documento será gerado com assinatura automática

### 5. Upload de Documento

```bash
# Via API
curl -X POST http://localhost:8000/api/documents/upload \
  -H "Authorization: Bearer SEU_TOKEN" \
  -F "file=@documento.pdf"

# Suportados: PDF, DOCX, TXT, JPG, PNG
# OCR automático para imagens
```

---

## 🔑 Obter Chaves de API (Grátis)

### OpenAI (GPT)
1. Acesse: https://platform.openai.com/api-keys
2. Faça login/cadastro
3. Crie nova chave de API
4. **Grátis**: $5 de créditos iniciais
5. Copie: `sk-...`

### Anthropic (Claude)
1. Acesse: https://console.anthropic.com/
2. Faça login/cadastro
3. Crie nova chave de API
4. **Grátis**: $5 de créditos iniciais
5. Copie: `sk-ant-...`

### Google (Gemini)
1. Acesse: https://makersuite.google.com/app/apikey
2. Faça login com conta Google
3. Crie nova chave de API
4. **Grátis**: Cota generosa
5. Copie chave

---

## 🐳 Docker (Opcional)

### Serviços Essenciais

```bash
# PostgreSQL
docker run --name iudex-postgres \
  -e POSTGRES_USER=iudex \
  -e POSTGRES_PASSWORD=iudex123 \
  -e POSTGRES_DB=iudex \
  -p 5432:5432 \
  -d postgres:15

# Redis
docker run --name iudex-redis \
  -p 6379:6379 \
  -d redis:7-alpine

# Qdrant (Vector DB - opcional)
docker run --name iudex-qdrant \
  -p 6333:6333 \
  -d qdrant/qdrant
```

---

## 🧪 Testar

### Backend

```bash
cd apps/api

# Todos os testes
pytest

# Com cobertura
pytest --cov=app --cov-report=html

# Teste específico
pytest tests/test_auth.py -v

# Ver cobertura
open htmlcov/index.html
```

### Frontend

```bash
cd apps/web

# Build de produção
npm run build

# Verificar erros
npm run lint
```

---

## 📚 Exemplos de Uso

### 1. Validar CPF

```python
from app.utils.validators import InputValidator

validator = InputValidator()
valid = validator.validate_cpf("123.456.789-09")
# True ou False
```

### 2. Listar Templates

```python
from app.services.legal_templates import legal_template_library

templates = legal_template_library.list_templates()
for t in templates:
    print(f"{t.id}: {t.name}")
```

### 3. Extrair Texto de PDF

```python
from app.services.document_processor import extract_text_from_file

result = await extract_text_from_file("documento.pdf")
texto = result["text"]
metadados = result["metadata"]
```

### 4. Aplicar Rate Limit

```python
from app.core.rate_limiter import rate_limiter

@router.post("/endpoint")
@rate_limiter.limit(max_requests=10, window_seconds=60)
async def meu_endpoint(request: Request):
    return {"message": "Protegido!"}
```

---

## 🔧 Troubleshooting

### Erro: "Redis connection refused"
```bash
# Instale e inicie Redis
# Ubuntu/Debian
sudo apt install redis-server
sudo systemctl start redis

# macOS
brew install redis
brew services start redis

# Ou use Docker (ver acima)
```

### Erro: "Database connection failed"
```bash
# Certifique-se de que PostgreSQL está rodando
# Ubuntu/Debian
sudo systemctl start postgresql

# macOS
brew services start postgresql

# Crie o banco
createdb iudex

# Ou use Docker (ver acima)
```

### Erro: "Tesseract not found" (OCR)
```bash
# Ubuntu/Debian
sudo apt install tesseract-ocr tesseract-ocr-por

# macOS
brew install tesseract tesseract-lang

# Windows
# Baixe de: https://github.com/UB-Mannheim/tesseract/wiki
```

### Erro: Frontend não encontra API
```bash
# Verifique CORS no backend (.env)
CORS_ORIGINS=http://localhost:3000

# Reinicie o backend após alterar .env
```

---

## 📊 Endpoints Principais

### Autenticação
- `POST /api/auth/register` - Registro
- `POST /api/auth/login` - Login
- `POST /api/auth/logout` - Logout
- `GET /api/auth/me` - Perfil atual
- `POST /api/auth/refresh` - Refresh token

### Chats
- `GET /api/chats` - Listar chats
- `POST /api/chats` - Criar chat
- `GET /api/chats/{id}` - Detalhes do chat
- `GET /api/chats/{id}/messages` - Mensagens
- `POST /api/chats/{id}/messages` - Enviar mensagem
- `POST /api/chats/{id}/generate` - Gerar documento

### Documentos
- `POST /api/documents/upload` - Upload
- `GET /api/documents` - Listar
- `GET /api/documents/{id}` - Detalhes
- `DELETE /api/documents/{id}` - Excluir

### Templates
- `GET /api/templates` - Listar templates
- `GET /api/templates/{id}` - Info do template
- `POST /api/templates/render` - Renderizar

---

## 🎯 Verificação Rápida

```bash
# Backend está rodando?
curl http://localhost:8000/health

# Documentação está acessível?
open http://localhost:8000/docs

# Frontend está rodando?
open http://localhost:3000

# Pode fazer login?
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "teste@teste.com", "password": "Teste@123"}'
```

---

## 📖 Documentação Completa

- **Revisão Completa**: `REVISAO_COMPLETA.md`
- **Status**: `status.md`
- **Implementação**: `IMPLEMENTACAO.md`
- **Próximos Passos**: `PROXIMOS_PASSOS.md`
- **README**: `README.md`

---

## 💡 Dicas

1. **Desenvolvimento Local**:
   - Use nível de esforço 1-2 para testes rápidos
   - Ative cache agressivo no Redis
   - Use logs para debug

2. **Performance**:
   - Mantenha connection pooling em 20
   - Use Redis para cache
   - Configure workers adequadamente

3. **Segurança**:
   - Nunca comite `.env`
   - Use senhas fortes
   - Mantenha rate limits ativos

4. **Produção**:
   - Use HTTPS
   - Configure CORS corretamente
   - Ative monitoramento
   - Faça backups regulares

---

**🎉 Pronto! Sistema rodando e gerando documentos jurídicos! 🎉**

Para dúvidas, consulte a documentação completa ou abra uma issue.

