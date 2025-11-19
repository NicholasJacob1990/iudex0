# 🚀 Iudex - Guia Rápido de Início

## ⚡ Início Rápido (5 minutos)

### 1. Pré-requisitos

```bash
# Verifique as versões
python --version  # Precisa 3.11+
psql --version    # PostgreSQL 14+
redis-cli ping    # Redis funcionando
```

### 2. Clone e Configure

```bash
# Clone o repositório
git clone https://github.com/seu-usuario/iudex.git
cd iudex/apps/api

# Crie ambiente virtual Python
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou: venv\Scripts\activate  # Windows
```

### 3. Instale Dependências

```bash
# Instalar todas as bibliotecas
pip install -r requirements.txt
```

### 4. Configure as Variáveis de Ambiente

```bash
# Copie o arquivo de exemplo
cp .env.example .env

# Edite o .env e adicione suas chaves:
nano .env
```

**Mínimo necessário:**
```env
# APIs de IA (OBRIGATÓRIAS)
OPENAI_API_KEY=sk-proj-...
ANTHROPIC_API_KEY=sk-ant-api03-...
GOOGLE_API_KEY=AIza...

# Banco de Dados
DATABASE_URL=postgresql+asyncpg://postgres:senha@localhost:5432/iudex

# Redis
REDIS_URL=redis://localhost:6379/0

# JWT
JWT_SECRET_KEY=minha-chave-super-secreta-123
SECRET_KEY=outra-chave-secreta-456
```

### 5. Configure o Banco de Dados

```bash
# Criar banco de dados
createdb iudex

# Executar migrações
alembic upgrade head
```

### 6. Inicie o Servidor! 🎉

```bash
python main.py
```

Pronto! Acesse:
- **API**: http://localhost:8000
- **Documentação**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

## 🧪 Teste o Sistema Multi-Agente

### Teste via Swagger UI

1. Acesse http://localhost:8000/docs
2. Explore os endpoints disponíveis
3. Teste `/health` primeiro

### Teste via Python

```python
import httpx
import asyncio

async def test_multi_agent():
    async with httpx.AsyncClient() as client:
        # Exemplo de geração com múltiplos agentes
        response = await client.post(
            "http://localhost:8000/api/chats/test/generate",
            json={
                "prompt": "Elabore uma petição inicial de ação de indenização por danos morais",
                "effort_level": 5,  # Usar todos os agentes
                "context": {
                    "user_instructions": "Foco em dano moral por negativação indevida"
                }
            }
        )
        print(response.json())

asyncio.run(test_multi_agent())
```

## 📊 Entendendo os Níveis de Esforço

| Nível | Agentes Usados | Tempo Estimado | Custo | Qualidade |
|-------|----------------|----------------|-------|-----------|
| 1-2   | Apenas Claude  | ~10s           | Baixo | Boa       |
| 3     | Claude + 1 revisor | ~20s       | Médio | Muito Boa |
| 4-5   | Claude + Gemini + GPT | ~40s   | Alto  | Excelente |

**Quando usar cada nível:**
- **Nível 1-2**: Rascunhos rápidos, chats informais
- **Nível 3**: Documentos padrão, uso cotidiano
- **Nível 4-5**: Documentos críticos, petições importantes

## 🐛 Problemas Comuns

### Erro: "ModuleNotFoundError"
```bash
# Certifique-se que o venv está ativado
source venv/bin/activate
pip install -r requirements.txt
```

### Erro: "Connection refused" (PostgreSQL)
```bash
# Inicie o PostgreSQL
sudo service postgresql start  # Linux
brew services start postgresql  # Mac
```

### Erro: "Connection refused" (Redis)
```bash
# Inicie o Redis
sudo service redis-server start  # Linux
brew services start redis  # Mac
redis-server  # Ou manualmente
```

### Erro: "Invalid API Key"
- Verifique se as chaves estão corretas no `.env`
- Confirme que as chaves têm permissões adequadas
- **Claude**: Precisa de acesso ao Claude 4
- **OpenAI**: Precisa de acesso ao GPT-4/GPT-5
- **Google**: Precisa de acesso ao Gemini API

## 📚 Próximos Passos

1. **Explore a documentação**: http://localhost:8000/docs
2. **Leia o README do backend**: `apps/api/README.md`
3. **Configure o frontend**: `apps/web/` (em breve)
4. **Teste os agentes**: Experimente diferentes níveis de esforço
5. **Monitore custos**: Cada requisição mostra custo estimado

## 💡 Dicas Úteis

### Desenvolvimento

```bash
# Modo debug com reload automático
uvicorn app.main:app --reload --log-level debug

# Ver logs em tempo real
tail -f logs/iudex-api.log
```

### Produção

```bash
# Com Gunicorn para múltiplos workers
gunicorn app.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000
```

### Monitoramento de Custos

Cada resposta da API inclui:
```json
{
  "content": "...",
  "metadata": {
    "tokens_used": 5000,
    "cost": 0.0825,
    "agents_used": ["claude", "gemini", "gpt"]
  }
}
```

## 🎯 Recursos Disponíveis

✅ **Funcionando agora:**
- Sistema Multi-Agente IA
- Autenticação JWT
- Upload de documentos
- Chat básico

🚧 **Em desenvolvimento:**
- OCR avançado
- Transcrição de audiências
- Busca de jurisprudência
- Geração de podcasts
- Interface web (Next.js)

## 🆘 Precisa de Ajuda?

1. Verifique os logs: `logs/iudex-api.log`
2. Teste o health check: `curl http://localhost:8000/health`
3. Consulte a documentação interativa: http://localhost:8000/docs
4. Abra uma issue no GitHub

## 🎉 Pronto para Usar!

Seu backend Iudex está configurado e pronto! 

Agora você tem uma plataforma jurídica com IA multi-agente usando:
- 🧠 Claude Sonnet 4.5 para geração
- ⚖️ Gemini 2.5 Pro para revisão jurídica
- ✍️ GPT-5 para revisão textual

**Comece a criar documentos jurídicos de alta qualidade!**

---

**Desenvolvido com ❤️ e Python 🐍**

