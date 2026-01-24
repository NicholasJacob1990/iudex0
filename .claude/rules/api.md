---
paths:
  - apps/api/**
---

# Regras da API (apps/api)

> Estas regras aplicam-se apenas a arquivos em `apps/api/`

## Estrutura de Endpoints

```python
@router.post("/resource", response_model=ResourceResponse)
async def create_resource(
    request: ResourceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> ResourceResponse:
    """Docstring descrevendo o endpoint."""
    ...
```

## Streaming SSE

- Usar `StreamingResponse` com `media_type="text/event-stream"`
- Formato: `data: {json}\n\n`
- Eventos: `thinking`, `content`, `done`, `error`
- Sempre enviar `done` ao finalizar

## LLMs

- Suporte a múltiplos providers: OpenAI, Gemini, Claude
- Configurar via variáveis de ambiente
- Fallback quando provider falhar
- Log de tokens usados para billing

## Database

- Usar SQLAlchemy async
- Transações para operações múltiplas
- Índices para queries frequentes
- Migrations via Alembic

## Tratamento de Erros

- HTTPException com status codes corretos
- Mensagens de erro úteis (mas sem expor internals)
- Log de erros com contexto suficiente
