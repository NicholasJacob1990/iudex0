# Integração com Iudex (FastAPI)

## Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│                          IUDEX                               │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │                    Next.js Frontend                     │ │
│  │  • Dashboard de notificações SEI                        │ │
│  │  • Configuração de alertas por usuário                  │ │
│  │  • Download de documentos                               │ │
│  └────────────────────────────────────────────────────────┘ │
│                            │                                 │
│                            ▼                                 │
│  ┌────────────────────────────────────────────────────────┐ │
│  │                    FastAPI Backend                      │ │
│  │                                                         │ │
│  │  @router.post("/sei/users")                            │ │
│  │  @router.get("/sei/notifications")                      │ │
│  │  @router.post("/sei/users/{id}/start")                  │ │
│  │                                                         │ │
│  └─────────────────────┬──────────────────────────────────┘ │
│                        │                                     │
│                        │ HTTP (localhost:3001)               │
│                        ▼                                     │
│  ┌────────────────────────────────────────────────────────┐ │
│  │               SEI Service (Node.js)                     │ │
│  │                                                         │ │
│  │  • Gerenciamento de credenciais (criptografadas)        │ │
│  │  • Watcher com polling (SOAP/Playwright)               │ │
│  │  • Envio de emails com teor e prazos                   │ │
│  │  • Download de documentos                               │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## 1. Configuração do SEI Service

### docker-compose.yml
```yaml
version: '3.8'

services:
  iudex-api:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - SEI_SERVICE_URL=http://sei-service:3001
      - SEI_API_KEY=${SEI_API_KEY}
    depends_on:
      - sei-service
      - postgres

  sei-service:
    build: ./sei-service
    ports:
      - "3001:3001"
    environment:
      - MASTER_PASSWORD=${SEI_MASTER_PASSWORD}
      - API_KEY=${SEI_API_KEY}
      - SMTP_HOST=${SMTP_HOST}
      - SMTP_PORT=${SMTP_PORT}
      - SMTP_USER=${SMTP_USER}
      - SMTP_PASS=${SMTP_PASS}
      - SMTP_FROM=${SMTP_FROM}
    volumes:
      - sei-data:/app/data

  postgres:
    image: postgres:15
    environment:
      - POSTGRES_DB=iudex
      - POSTGRES_USER=${DB_USER}
      - POSTGRES_PASSWORD=${DB_PASS}
    volumes:
      - postgres-data:/var/lib/postgresql/data

volumes:
  sei-data:
  postgres-data:
```

### sei-service/Dockerfile
```dockerfile
FROM mcr.microsoft.com/playwright:v1.48.0-jammy

WORKDIR /app

# Copiar package.json
COPY package.json pnpm-lock.yaml ./
RUN corepack enable && pnpm install --frozen-lockfile

# Copiar código
COPY . .
RUN pnpm build

# Iniciar serviço
CMD ["node", "dist/examples/service-standalone.js"]
```

## 2. Integração FastAPI

### backend/app/services/sei.py
```python
import httpx
from typing import Optional, List
from pydantic import BaseModel

class SEICredentials(BaseModel):
    usuario: str
    senha: str

class SEIUser(BaseModel):
    id: str
    nome: str
    email: str
    seiUrl: str
    orgao: Optional[str] = None
    credentials: SEICredentials
    notifications: Optional[dict] = None

class SEIService:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self.api_key = api_key
        self.headers = {"X-API-Key": api_key}

    async def get_status(self) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/status",
                headers=self.headers
            )
            resp.raise_for_status()
            return resp.json()

    async def list_users(self) -> List[dict]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/users",
                headers=self.headers
            )
            resp.raise_for_status()
            return resp.json()["users"]

    async def add_user(self, user: SEIUser) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/users",
                headers=self.headers,
                json=user.model_dump()
            )
            resp.raise_for_status()
            return resp.json()

    async def get_user(self, user_id: str) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/users/{user_id}",
                headers=self.headers
            )
            resp.raise_for_status()
            return resp.json()

    async def update_user(self, user_id: str, updates: dict) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.put(
                f"{self.base_url}/users/{user_id}",
                headers=self.headers,
                json=updates
            )
            resp.raise_for_status()
            return resp.json()

    async def delete_user(self, user_id: str) -> None:
        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                f"{self.base_url}/users/{user_id}",
                headers=self.headers
            )
            resp.raise_for_status()

    async def start_monitoring(self, user_id: str) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/users/{user_id}/start",
                headers=self.headers
            )
            resp.raise_for_status()
            return resp.json()

    async def stop_monitoring(self, user_id: str) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/users/{user_id}/stop",
                headers=self.headers
            )
            resp.raise_for_status()
            return resp.json()

    async def start_all(self) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/start",
                headers=self.headers
            )
            resp.raise_for_status()
            return resp.json()

    async def stop_all(self) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/stop",
                headers=self.headers
            )
            resp.raise_for_status()
            return resp.json()
```

### backend/app/routers/sei.py
```python
from fastapi import APIRouter, Depends, HTTPException
from app.services.sei import SEIService, SEIUser
from app.core.config import settings
from app.core.auth import get_current_user

router = APIRouter(prefix="/sei", tags=["SEI"])

def get_sei_service() -> SEIService:
    return SEIService(
        base_url=settings.SEI_SERVICE_URL,
        api_key=settings.SEI_API_KEY
    )

@router.get("/status")
async def get_status(
    sei: SEIService = Depends(get_sei_service),
    current_user = Depends(get_current_user)
):
    """Status do serviço SEI"""
    return await sei.get_status()

@router.get("/users")
async def list_users(
    sei: SEIService = Depends(get_sei_service),
    current_user = Depends(get_current_user)
):
    """Lista usuários SEI cadastrados"""
    return await sei.list_users()

@router.post("/users")
async def add_user(
    user: SEIUser,
    sei: SEIService = Depends(get_sei_service),
    current_user = Depends(get_current_user)
):
    """Cadastra novo usuário SEI"""
    try:
        return await sei.add_user(user)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))

@router.get("/users/{user_id}")
async def get_user(
    user_id: str,
    sei: SEIService = Depends(get_sei_service),
    current_user = Depends(get_current_user)
):
    """Obtém usuário SEI"""
    try:
        return await sei.get_user(user_id)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

@router.post("/users/{user_id}/start")
async def start_monitoring(
    user_id: str,
    sei: SEIService = Depends(get_sei_service),
    current_user = Depends(get_current_user)
):
    """Inicia monitoramento de usuário"""
    return await sei.start_monitoring(user_id)

@router.post("/users/{user_id}/stop")
async def stop_monitoring(
    user_id: str,
    sei: SEIService = Depends(get_sei_service),
    current_user = Depends(get_current_user)
):
    """Para monitoramento de usuário"""
    return await sei.stop_monitoring(user_id)

@router.post("/start-all")
async def start_all(
    sei: SEIService = Depends(get_sei_service),
    current_user = Depends(get_current_user)
):
    """Inicia monitoramento de todos os usuários"""
    return await sei.start_all()
```

## 3. Frontend (Next.js)

### pages/sei/notifications.tsx
```tsx
import { useState, useEffect } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { api } from '@/lib/api';

export default function SEINotifications() {
  const { data: status } = useQuery(['sei-status'], () =>
    api.get('/sei/status').then(r => r.data)
  );

  const { data: users } = useQuery(['sei-users'], () =>
    api.get('/sei/users').then(r => r.data)
  );

  const startAll = useMutation(() => api.post('/sei/start-all'));

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-6">Monitoramento SEI</h1>

      {/* Status */}
      <div className="bg-white rounded-lg shadow p-4 mb-6">
        <h2 className="font-semibold mb-2">Status do Serviço</h2>
        <div className="flex items-center gap-2">
          <span className={`w-3 h-3 rounded-full ${status?.running ? 'bg-green-500' : 'bg-red-500'}`} />
          <span>{status?.running ? 'Ativo' : 'Inativo'}</span>
        </div>
        <p className="text-sm text-gray-600 mt-2">
          {status?.activeSessions?.length ?? 0} sessões ativas
        </p>
        {!status?.running && (
          <button
            onClick={() => startAll.mutate()}
            className="mt-4 px-4 py-2 bg-blue-600 text-white rounded"
          >
            Iniciar Monitoramento
          </button>
        )}
      </div>

      {/* Usuários */}
      <div className="bg-white rounded-lg shadow">
        <h2 className="font-semibold p-4 border-b">Usuários Cadastrados</h2>
        <div className="divide-y">
          {users?.map((user: any) => (
            <div key={user.id} className="p-4 flex justify-between items-center">
              <div>
                <p className="font-medium">{user.nome}</p>
                <p className="text-sm text-gray-600">{user.email}</p>
              </div>
              <span className={`px-2 py-1 rounded text-sm ${user.active ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-600'}`}>
                {user.active ? 'Ativo' : 'Inativo'}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
```

## 4. Configurações de Notificação

### Opções disponíveis por usuário:

```typescript
interface NotificationConfig {
  // Canais
  email: boolean;           // Enviar email
  push: boolean;            // Enviar webhook
  webhookUrl?: string;      // URL do webhook

  // Eventos para notificar
  events: {
    processos_recebidos: boolean;  // Novos processos
    blocos_assinatura: boolean;    // Blocos pendentes
    prazos: boolean;               // Alertas de prazo
    retornos_programados: boolean; // Retornos
  };

  // Conteúdo do email
  includeContent: boolean;    // Incluir teor do documento
  attachDocuments: boolean;   // Anexar documentos ao email
  downloadProcess: boolean;   // Baixar processo completo
}
```

## 5. Exemplo de Email Gerado

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📥 Novos Processos Recebidos
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Olá, João Silva!

Você recebeu 2 novos processos no SEI.

────────────────────────────────────────────
📋 5030.01.0002527/2025-32           URGENTE
────────────────────────────────────────────
📤 Remetente: CODEMGE/JURÍDICO
📅 Recebido em: 24/01/2026
📋 Tipo: Parecer Jurídico

Teor:
Encaminho para análise o presente parecer
jurídico sobre a alienação de bens...

⏰ Prazo: 28/01/2026
   Dias restantes: 4 (úteis)

📄 Documentos:
   • Parecer Jurídico 29/2026 (24/01/2026)
   • Anexo I - Documentação (24/01/2026)

[Abrir no SEI]

────────────────────────────────────────────
📋 5030.01.0002530/2025-35
────────────────────────────────────────────
📤 Remetente: CODEMGE/GENSU
📅 Recebido em: 24/01/2026
📋 Tipo: Comunicação Interna

Teor:
Solicito manifestação quanto ao pedido
de férias do servidor...

📄 Documentos:
   • CI 15/2026 (24/01/2026)

[Abrir no SEI]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Esta notificação foi enviada automaticamente pelo sistema Iudex.
SEI: https://sei.mg.gov.br
```

## 6. Variáveis de Ambiente

```bash
# .env

# SEI Service
SEI_MASTER_PASSWORD=sua-senha-mestre-muito-segura-aqui
SEI_API_KEY=chave-api-segura

# Email (SMTP)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_SECURE=false
SMTP_USER=seu-email@gmail.com
SMTP_PASS=sua-senha-de-app
SMTP_FROM=noreply@iudex.com

# Iudex
SEI_SERVICE_URL=http://localhost:3001
```
