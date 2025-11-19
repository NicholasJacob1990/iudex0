# 🚀 Guia Rápido de Teste - Iudex

## Verificação Rápida do Sistema

### 1. Backend API (Python/FastAPI)

#### Iniciar o Backend

```bash
cd apps/api

# Ativar ambiente virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou venv\Scripts\activate no Windows

# Instalar dependências
pip install -r requirements.txt

# Criar arquivo .env (copie de .env.example e configure)
cp .env.example .env

# Editar .env com suas configurações mínimas:
# - SECRET_KEY
# - JWT_SECRET_KEY
# - DATABASE_URL
# - OPENAI_API_KEY (ou deixar vazio para modo fallback)
# - ANTHROPIC_API_KEY (ou deixar vazio para modo fallback)
# - GOOGLE_API_KEY (ou deixar vazio para modo fallback)

# Iniciar servidor
python main.py
```

#### Verificar Health Check

```bash
curl http://localhost:8000/health
```

Resposta esperada:
```json
{
  "status": "ok",
  "version": "0.1.0",
  "environment": "development"
}
```

#### Acessar Documentação Interativa

Abra no navegador: http://localhost:8000/docs

---

### 2. Frontend Web (Next.js)

#### Iniciar o Frontend

```bash
cd apps/web

# Instalar dependências
npm install

# Iniciar em modo desenvolvimento
npm run dev
```

Acesse: http://localhost:3000

---

## 🧪 Testes dos Fluxos Principais

### Fluxo 1: Autenticação

#### 1.1 Registro de Usuário Individual

**Via Interface Web:**
1. Acesse http://localhost:3000/register-type
2. Clique em "Cadastro Individual"
3. Preencha o formulário:
   - Nome: João Silva
   - Email: joao@teste.com
   - Senha: teste1234
   - OAB: 123456
   - UF: SP
4. Clique em "Cadastrar"
5. Você deve ser redirecionado para o dashboard

**Via API (cURL):**
```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "João Silva",
    "email": "joao@teste.com",
    "password": "teste1234",
    "account_type": "INDIVIDUAL",
    "oab": "123456",
    "oab_state": "SP"
  }'
```

Resposta esperada:
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 1800,
  "user": {
    "id": "...",
    "email": "joao@teste.com",
    "name": "João Silva",
    ...
  }
}
```

#### 1.2 Login

**Via Interface Web:**
1. Acesse http://localhost:3000/login
2. Email: joao@teste.com
3. Senha: teste1234
4. Clique em "Entrar"

**Via API:**
```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "joao@teste.com",
    "password": "teste1234"
  }'
```

#### 1.3 Obter Perfil do Usuário

```bash
# Substitua SEU_TOKEN pelo access_token recebido
curl -X GET http://localhost:8000/api/auth/me \
  -H "Authorization: Bearer SEU_TOKEN"
```

---

### Fluxo 2: Criar Chat e Enviar Mensagem

#### 2.1 Criar Novo Chat

**Via Interface Web:**
1. No dashboard, clique em "Nova Conversa"
2. Digite um título (opcional)

**Via API:**
```bash
curl -X POST http://localhost:8000/api/chats \
  -H "Authorization: Bearer SEU_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Minha Petição",
    "mode": "DOCUMENT"
  }'
```

Resposta esperada:
```json
{
  "id": "chat-uuid",
  "title": "Minha Petição",
  "mode": "DOCUMENT",
  "created_at": "2025-11-19T...",
  "updated_at": "2025-11-19T..."
}
```

#### 2.2 Enviar Mensagem no Chat

```bash
# Substitua CHAT_ID pelo ID recebido
curl -X POST http://localhost:8000/api/chats/CHAT_ID/messages \
  -H "Authorization: Bearer SEU_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Olá! Preciso de ajuda com um documento."
  }'
```

---

### Fluxo 3: Geração de Documento Jurídico

#### 3.1 Gerar Petição Inicial (Modo Completo)

**Via Interface Web:**
1. No dashboard, clique em "Gerador"
2. Selecione "Petição Inicial"
3. Preencha os campos:
   - Tipo de ação: "Ação de Cobrança"
   - Descrição do caso: "Cliente prestou serviços no valor de R$ 10.000,00 e não foi pago"
   - Pedidos: "Condenação do réu ao pagamento"
4. Clique em "Gerar Documento"
5. Aguarde o processamento multi-agente
6. Revise o documento gerado

**Via API:**
```bash
curl -X POST http://localhost:8000/api/chats/CHAT_ID/generate \
  -H "Authorization: Bearer SEU_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Elabore uma petição inicial de ação de cobrança. O autor prestou serviços de consultoria no valor de R$ 10.000,00 para o réu em março de 2024, mas não recebeu o pagamento. Possui contrato assinado e notas fiscais.",
    "document_type": "petition",
    "effort_level": 3,
    "use_profile": "full",
    "context": {
      "action_type": "AÇÃO DE COBRANÇA",
      "case_value": "10000.00",
      "requests": "Condenação do réu ao pagamento de R$ 10.000,00 acrescido de juros e correção monetária"
    }
  }'
```

Resposta esperada:
```json
{
  "content": "EXCELENTÍSSIMO SENHOR DOUTOR JUIZ...\n\n[Documento completo gerado]",
  "reviews": [
    {
      "agent_name": "Gemini (Revisor Legal)",
      "score": 8.5,
      "approved": true,
      "comments": ["Fundamentação adequada..."]
    },
    {
      "agent_name": "GPT (Revisor Textual)",
      "score": 9.0,
      "approved": true,
      "comments": ["Texto claro e objetivo..."]
    }
  ],
  "consensus": true,
  "total_tokens": 5432,
  "total_cost": 0.15,
  "processing_time": 12.5
}
```

#### 3.2 Gerar Contrato (Modo Rápido)

```bash
curl -X POST http://localhost:8000/api/chats/CHAT_ID/generate \
  -H "Authorization: Bearer SEU_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Contrato de prestação de serviços de consultoria jurídica, prazo de 6 meses, valor de R$ 5.000,00 mensais.",
    "document_type": "contract",
    "effort_level": 2,
    "context": {
      "contract_type": "Prestação de Serviços",
      "duration": "6 meses",
      "value": "30000.00"
    }
  }'
```

#### 3.3 Gerar Parecer Jurídico

```bash
curl -X POST http://localhost:8000/api/chats/CHAT_ID/generate \
  -H "Authorization: Bearer SEU_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Cliente quer saber se pode rescindir contrato de aluguel antes do prazo em razão de problemas estruturais no imóvel.",
    "document_type": "opinion",
    "effort_level": 3
  }'
```

---

## 📊 Verificar Resultados

### Listar Chats do Usuário

```bash
curl -X GET http://localhost:8000/api/chats \
  -H "Authorization: Bearer SEU_TOKEN"
```

### Obter Mensagens de um Chat

```bash
curl -X GET http://localhost:8000/api/chats/CHAT_ID/messages \
  -H "Authorization: Bearer SEU_TOKEN"
```

---

## 🔍 Modo Fallback (Sem API Keys)

Se você não tiver as chaves de API configuradas, o sistema ainda funciona em **modo fallback**:

1. A geração de documentos retornará templates simulados
2. As revisões serão simuladas com scores fixos
3. Você verá uma mensagem indicando "Modo Offline" ou "Fallback"

Isso permite testar toda a interface e fluxo sem custo de API!

---

## ⚡ Teste Rápido Completo (Script)

Salve este script como `test_flow.sh`:

```bash
#!/bin/bash

API_URL="http://localhost:8000/api"

echo "1. Registrando usuário..."
REGISTER_RESPONSE=$(curl -s -X POST $API_URL/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Teste Silva",
    "email": "teste@example.com",
    "password": "teste1234",
    "account_type": "INDIVIDUAL",
    "oab": "999999",
    "oab_state": "SP"
  }')

TOKEN=$(echo $REGISTER_RESPONSE | jq -r '.access_token')
echo "Token obtido: ${TOKEN:0:20}..."

echo "\n2. Criando chat..."
CHAT_RESPONSE=$(curl -s -X POST $API_URL/chats \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title": "Teste Automático"}')

CHAT_ID=$(echo $CHAT_RESPONSE | jq -r '.id')
echo "Chat criado: $CHAT_ID"

echo "\n3. Gerando documento..."
curl -s -X POST $API_URL/chats/$CHAT_ID/generate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Petição de ação de cobrança de R$ 5.000,00",
    "document_type": "petition",
    "effort_level": 2
  }' | jq '.content' | head -20

echo "\n✅ Teste completo!"
```

Execute com:
```bash
chmod +x test_flow.sh
./test_flow.sh
```

---

## 🐛 Troubleshooting

### Erro de Conexão com Banco de Dados

```
SQLALCHEMY_DATABASE_URL not found
```

**Solução:** Configure `DATABASE_URL` no `.env`:
```env
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/iudex
```

Ou use SQLite para testes:
```env
DATABASE_URL=sqlite+aiosqlite:///./iudex.db
```

### Erro de Token

```
401 Unauthorized
```

**Solução:** 
1. Verifique se o token foi incluído no header `Authorization: Bearer TOKEN`
2. Faça login novamente para obter novo token
3. Verifique se `JWT_SECRET_KEY` está configurado no `.env`

### Erro nas APIs de IA

```
API Key not found
```

**Solução:** 
1. O sistema continuará funcionando em modo fallback
2. Para usar IA real, configure as chaves no `.env`:
```env
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=...
```

---

## ✅ Checklist de Testes

- [ ] Backend inicializa sem erros
- [ ] Health check retorna OK
- [ ] Documentação Swagger acessível
- [ ] Registro de usuário funciona
- [ ] Login funciona
- [ ] Criação de chat funciona
- [ ] Envio de mensagem funciona
- [ ] Geração de documento funciona (mesmo em fallback)
- [ ] Frontend carrega sem erros
- [ ] Integração frontend-backend funciona
- [ ] Assinatura de documentos é aplicada
- [ ] Validação de documentos retorna resultados

---

## 📝 Próximos Passos

Após verificar que tudo funciona:

1. Configure as API Keys reais para usar IA multi-agente
2. Configure banco de dados PostgreSQL para produção
3. Configure Redis para cache
4. Execute testes de carga
5. Configure CI/CD
6. Prepare para deploy

---

**Dúvidas?** Consulte:
- `README.md` - Visão geral
- `BACKEND_COMPLETO.md` - Documentação técnica backend
- `INTEGRACAO.md` - Guia de integração
- `status.md` - Status atual do projeto

