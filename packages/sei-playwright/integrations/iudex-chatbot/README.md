# SEI Tools Integration para Iudex Chat

Ferramentas SEI para integrar no chat multi-provider do Iudex.

## Arquitetura

```
┌─────────────────────┐
│  Chat Iudex         │  (GPT / Claude / Gemini)
│  (multi-provider)   │
└──────────┬──────────┘
           │ tool_call
           ▼
┌─────────────────────┐
│  POST /api/sei/     │  FastAPI Router
│  execute            │
└──────────┬──────────┘
           │ HTTP
           ▼
┌─────────────────────┐
│  sei-playwright     │  Node.js API
│  API                │
└──────────┬──────────┘
           │ Playwright
           ▼
┌─────────────────────┐
│  Sistema SEI        │
└─────────────────────┘
```

## Setup

### 1. Iniciar a API sei-playwright

```bash
cd ~/Documents/Aplicativos/sei-playwright
pnpm install && pnpm build
node dist/api.js
# API rodando em http://localhost:3001
```

### 2. Configurar variáveis de ambiente

```bash
# .env do Iudex
SEI_API_URL=http://localhost:3001
SEI_API_KEY=  # opcional
```

### 3. Integrar no backend Iudex

```python
# main.py
from fastapi import FastAPI
from integrations.sei_tools import router as sei_router

app = FastAPI()
app.include_router(sei_router, prefix="/api/sei")
```

### 4. Registrar tools no chat do Iudex

```python
from integrations.sei_tools import SEI_TOOLS, SEI_SYSTEM_PROMPT

# No seu chat service
class ChatService:
    def __init__(self):
        # Carregar tools SEI
        self.sei_tools = SEI_TOOLS

    def get_tools_for_chat(self):
        # Retorna tools no formato do provider
        return self.sei_tools

    def get_system_prompt(self):
        return f"{self.base_prompt}\n\n{SEI_SYSTEM_PROMPT}"
```

### 5. Executar tool calls

```python
import httpx

async def handle_tool_call(user_id: str, tool_call):
    """Chamado quando o LLM decide usar uma ferramenta SEI"""

    if tool_call.function.name.startswith("sei_"):
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "http://localhost:8000/api/sei/execute",
                json={
                    "user_id": user_id,
                    "function_name": tool_call.function.name,
                    "arguments": tool_call.function.arguments
                }
            )
            return response.json()
```

## Endpoints

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/api/sei/tools` | Lista tools (formato universal) |
| GET | `/api/sei/tools/openai` | Lista tools (formato OpenAI functions) |
| POST | `/api/sei/execute` | Executa uma tool |
| GET | `/api/sei/session/{user_id}` | Verifica sessão ativa |
| DELETE | `/api/sei/session/{user_id}` | Encerra sessão |

## Formato do Execute

```json
POST /api/sei/execute
{
    "user_id": "user123",
    "function_name": "sei_tramitar_processo",
    "arguments": {
        "numeroProcesso": "5030.01.0001234/2025-00",
        "unidadesDestino": ["GENSU"]
    }
}

Response:
{
    "success": true,
    "data": { ... },
    "error": null
}
```

## Tools Disponíveis (23)

### Autenticação
- `sei_login` - Login no SEI
- `sei_logout` - Logout

### Processos
- `sei_criar_processo` - Criar processo
- `sei_consultar_processo` - Consultar
- `sei_tramitar_processo` - Tramitar
- `sei_concluir_processo` - Concluir
- `sei_reabrir_processo` - Reabrir
- `sei_anexar_processo` - Anexar
- `sei_relacionar_processos` - Relacionar
- `sei_atribuir_processo` - Atribuir

### Documentos
- `sei_listar_documentos` - Listar
- `sei_criar_documento` - Criar
- `sei_upload_documento` - Upload
- `sei_assinar_documento` - Assinar
- `sei_cancelar_documento` - Cancelar

### Blocos
- `sei_listar_blocos` - Listar
- `sei_criar_bloco` - Criar
- `sei_adicionar_documento_bloco` - Add documento
- `sei_disponibilizar_bloco` - Disponibilizar

### Consultas
- `sei_consultar_andamentos` - Andamentos
- `sei_listar_tipos_processo` - Tipos processo
- `sei_listar_tipos_documento` - Tipos documento
- `sei_listar_unidades` - Unidades

## Exemplo Completo no Chat

```python
# Usuário: "tramite o processo 5030.01.0001234/2025-00 para a GENSU"

# 1. Chat envia para o LLM com as tools
response = await openai.chat.completions.create(
    model="gpt-4o",
    messages=messages,
    tools=SEI_TOOLS
)

# 2. LLM retorna tool_call
# tool_call.function.name = "sei_tramitar_processo"
# tool_call.function.arguments = {
#     "numeroProcesso": "5030.01.0001234/2025-00",
#     "unidadesDestino": ["GENSU"]
# }

# 3. Iudex executa via API
result = await execute_sei_tool(user_id, tool_call)

# 4. Retorna resultado para o LLM continuar a conversa
messages.append({
    "role": "tool",
    "tool_call_id": tool_call.id,
    "content": json.dumps(result)
})
```

## Arquivos

```
integrations/iudex-chatbot/
├── __init__.py           # Exports
├── sei_tools.py          # SEIToolExecutor + SEI_TOOLS
├── router.py             # FastAPI endpoints
├── openai-functions.json # Definições das 23 funções
├── requirements.txt      # Dependências
└── README.md
```
