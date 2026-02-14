# MCP Legal Server (Standalone)

Microserviço MCP para tools jurídicas do Iudex, com contratos operacionais:

- ACL por tenant
- rate limiting por tool
- cache com TTL
- auditoria de chamadas
- isolamento de segredos por tenant via variáveis de ambiente

## Execução local

```bash
cd apps/mcp-legal-server
PYTHONPATH=../api uvicorn main:app --reload --port 8123
```

## Endpoints

- `GET /health`
- `POST /rpc` (JSON-RPC 2.0, métodos `tools/list` e `tools/call`)

## Headers de contexto

- `X-Tenant-ID`
- `X-User-ID`
- `X-Session-ID`

## Variáveis de ambiente (contratos)

- `IUDEX_MCP_CONTRACTS_ENABLED=true|false`
- `IUDEX_MCP_ACL_JSON='{"default":{"allow":["legal.*"]}}'`
- `IUDEX_MCP_RATE_LIMIT_PER_MINUTE=60`
- `IUDEX_MCP_RATE_LIMIT_BY_TOOL_JSON='{"legal.buscar_publicacoes_djen":30}'`
- `IUDEX_MCP_CACHE_TTL_SECONDS=30`
- `IUDEX_MCP_CACHE_TTL_BY_TOOL_JSON='{"legal.consultar_processo_datajud":120}'`

Para segredos por tenant, o resolvedor de contratos aceita nomes no formato:

- `IUDEX_MCP_SECRET_{TENANT}_{SERVER}_TOKEN`
- `IUDEX_MCP_SECRET_{TENANT}_{SERVER}_HEADER_VALUE`
