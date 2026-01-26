# Serviço de Tribunais - Iudex

Serviço de automação de tribunais brasileiros (PJe, e-SAJ, eproc) para o Iudex.

## Arquitetura

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              IUDEX                                          │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────────────────────┐ │
│  │ Frontend     │────▶│ Backend      │────▶│ Serviço de Tribunais         │ │
│  │ (Next.js)    │     │ (FastAPI)    │     │ (Node.js)                    │ │
│  └──────────────┘     └──────────────┘     │                              │ │
│                                            │  ┌──────────┐  ┌───────────┐ │ │
│                                            │  │ API HTTP │  │ WebSocket │ │ │
│                                            │  │ :3100    │  │ :3101     │ │ │
│                                            │  └────┬─────┘  └─────┬─────┘ │ │
│                                            │       │              │       │ │
│                                            │  ┌────▼──────────────▼─────┐ │ │
│                                            │  │    Fila (BullMQ/Redis)  │ │ │
│                                            │  └────────────┬────────────┘ │ │
│                                            │               │              │ │
│                                            │  ┌────────────▼────────────┐ │ │
│                                            │  │       Worker            │ │ │
│                                            │  │  (tribunais-playwright) │ │ │
│                                            │  └─────────────────────────┘ │ │
│                                            └──────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                                          │
                    ┌─────────────────────────────────────┼─────────────────┐
                    │                                     │                 │
             ┌──────▼──────┐                      ┌───────▼───────┐  ┌──────▼──────┐
             │ Cert A1     │                      │ Extensão      │  │ Desktop     │
             │ (servidor)  │                      │ Chrome (A3)   │  │ Agent (A3)  │
             └─────────────┘                      └───────────────┘  └─────────────┘
                   │                                     │                 │
                   │                                     │                 │
             100% automático                    Usuário aprova      Usuário instala
             (upload .pfx)                      no navegador        app local
```

## Modos de Autenticação

### 1. Certificado A1 (Recomendado)
- Usuário faz upload do arquivo .pfx
- 100% automático, sem interação
- Funciona em servidor headless

### 2. Certificado A3 Físico (Token USB)
- Usuário instala extensão Chrome
- Extensão se conecta via WebSocket
- Operações executadas no browser do usuário

### 3. Certificado A3 Nuvem (Certisign/Serasa)
- Similar ao A3 físico
- Usuário aprova no app mobile

## API Endpoints

### Credenciais

```bash
# Salvar login com senha
POST /api/credentials/password
{
  "userId": "user123",
  "tribunal": "pje",
  "tribunalUrl": "https://pje.trf1.jus.br",
  "name": "PJe TRF1 - Dr. Silva",
  "cpf": "12345678901",
  "password": "senha123"
}

# Upload certificado A1
POST /api/credentials/certificate-a1
{
  "userId": "user123",
  "tribunal": "eproc",
  "tribunalUrl": "https://eproc.tjmg.jus.br",
  "name": "eproc TJMG - Cert A1",
  "pfxBase64": "MIIJ...",
  "pfxPassword": "senha-do-pfx",
  "expiresAt": "2026-12-31T23:59:59Z"
}

# Registrar certificado A3 nuvem
POST /api/credentials/certificate-a3-cloud
{
  "userId": "user123",
  "tribunal": "pje",
  "tribunalUrl": "https://pje.trf2.jus.br",
  "name": "PJe TRF2 - Certisign",
  "provider": "certisign"
}

# Listar credenciais
GET /api/credentials/{userId}

# Remover credencial
DELETE /api/credentials/{credentialId}
```

### Consultas (Síncronas)

```bash
# Consultar processo
GET /api/processo/{credentialId}/{numeroProcesso}

# Listar documentos
GET /api/processo/{credentialId}/{numeroProcesso}/documentos

# Listar movimentações
GET /api/processo/{credentialId}/{numeroProcesso}/movimentacoes
```

### Operações Genéricas

```bash
# Operação síncrona (consultas rápidas)
POST /api/operations/sync
{
  "credentialId": "cred123",
  "operation": "consultar_processo",
  "params": { "processo": "0001234-56.2024.8.13.0001" }
}

# Operação assíncrona (fila)
POST /api/operations/async
{
  "userId": "user123",
  "credentialId": "cred123",
  "operation": "baixar_processo",
  "params": { "processo": "0001234-56.2024.8.13.0001" },
  "webhookUrl": "https://iudex.com/api/webhook/tribunal"
}

# Consultar status de operação
GET /api/operations/{jobId}
```

### Peticionamento

```bash
# Protocolar petição (sempre assíncrono)
POST /api/peticionar
{
  "userId": "user123",
  "credentialId": "cred123",
  "processo": "0001234-56.2024.8.13.0001",
  "tipo": "peticao_intermediaria",
  "arquivos": [
    {
      "name": "peticao.pdf",
      "base64": "JVBERi0...",
      "mimeType": "application/pdf",
      "tipoDocumento": "Petição"
    }
  ],
  "webhookUrl": "https://iudex.com/api/webhook/peticao"
}
```

## Variáveis de Ambiente

```env
# API
API_PORT=3100

# WebSocket para extensões
WS_PORT=3101

# Redis (fila)
REDIS_URL=redis://localhost:6379

# Chave de criptografia (32 caracteres)
ENCRYPTION_KEY=your-32-character-encryption-key!

# CORS
CORS_ORIGINS=http://localhost:3000,https://iudex.com

# Logs
LOG_LEVEL=info
NODE_ENV=development
```

## Execução

```bash
# Instalar dependências
npm install

# Desenvolvimento
npm run dev

# Worker separado (produção)
npm run worker

# Build
npm run build

# Produção
npm start
```

## Integração com Backend Python (FastAPI)

```python
import httpx

TRIBUNAIS_URL = "http://localhost:3100/api"

async def consultar_processo(credential_id: str, numero: str):
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{TRIBUNAIS_URL}/processo/{credential_id}/{numero}"
        )
        return response.json()

async def peticionar(user_id: str, credential_id: str, processo: str, arquivos: list):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{TRIBUNAIS_URL}/peticionar",
            json={
                "userId": user_id,
                "credentialId": credential_id,
                "processo": processo,
                "tipo": "peticao_intermediaria",
                "arquivos": arquivos,
                "webhookUrl": "https://iudex.com/api/webhook/peticao"
            }
        )
        return response.json()
```

## Extensão Chrome

Para certificados A3, o usuário precisa instalar a extensão:

1. Acesse `chrome://extensions`
2. Ative "Modo de desenvolvedor"
3. Clique em "Carregar sem compactação"
4. Selecione a pasta `extension/`

A extensão se conecta automaticamente ao WebSocket e executa operações no navegador do usuário.
