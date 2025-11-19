# 🔌 Guia de Integração Frontend-Backend

## Visão Geral

Este guia mostra como integrar o frontend Next.js com o backend Python/FastAPI do Iudex.

## 🎯 Arquitetura de Comunicação

```
┌─────────────────┐      HTTP/REST      ┌─────────────────┐
│   Next.js Web   │ ◄─────────────────► │  FastAPI Backend│
│  (Port 3000)    │                     │  (Port 8000)    │
└─────────────────┘                     └─────────────────┘
        │                                         │
        │                                         │
        ▼                                         ▼
   React Query                              PostgreSQL
   Zustand State                            Redis Cache
   Axios Client                             Vector DB
```

## 🚀 Setup Inicial

### 1. Iniciar Backend

```bash
# Terminal 1: API
cd apps/api
source venv/bin/activate
python main.py

# Terminal 2: Celery Worker
cd apps/api
source venv/bin/activate
celery -A app.workers.celery_app worker --loglevel=info
```

### 2. Iniciar Frontend

```bash
# Terminal 3: Next.js
cd apps/web
npm install
npm run dev
```

### 3. Verificar Conexão

```bash
# Testar API
curl http://localhost:8000/health

# Acessar Frontend
open http://localhost:3000
```

## 📡 Cliente API (Frontend)

### Criar Cliente Axios

```typescript
// apps/web/src/lib/api.ts
import axios, { AxiosInstance, AxiosRequestConfig } from 'axios';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

class ApiClient {
  private client: AxiosInstance;

  constructor() {
    this.client = axios.create({
      baseURL: API_URL,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    // Interceptor para adicionar token
    this.client.interceptors.request.use((config) => {
      const token = localStorage.getItem('access_token');
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
      return config;
    });

    // Interceptor para tratar erros
    this.client.interceptors.response.use(
      (response) => response,
      async (error) => {
        if (error.response?.status === 401) {
          // Token expirado - fazer logout
          localStorage.removeItem('access_token');
          window.location.href = '/login';
        }
        return Promise.reject(error);
      }
    );
  }

  // Métodos de autenticação
  async login(email: string, password: string) {
    const response = await this.client.post('/api/auth/login', {
      email,
      password,
    });
    return response.data;
  }

  async register(data: { email: string; password: string; name: string }) {
    const response = await this.client.post('/api/auth/register', data);
    return response.data;
  }

  async getCurrentUser() {
    const response = await this.client.get('/api/auth/me');
    return response.data;
  }

  // Documentos
  async uploadDocument(file: File, metadata: any) {
    const formData = new FormData();
    formData.append('file', file);
    Object.keys(metadata).forEach((key) => {
      formData.append(key, metadata[key]);
    });

    const response = await this.client.post('/api/documents/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  }

  async getDocuments() {
    const response = await this.client.get('/api/documents');
    return response.data;
  }

  // Chat e Geração
  async createChat(data: { title: string; mode: string }) {
    const response = await this.client.post('/api/chats', data);
    return response.data;
  }

  async generateDocument(chatId: string, data: {
    prompt: string;
    effort_level: number;
    context: any;
  }) {
    const response = await this.client.post(
      `/api/chats/${chatId}/generate`,
      data
    );
    return response.data;
  }

  async getChats() {
    const response = await this.client.get('/api/chats');
    return response.data;
  }
}

export const api = new ApiClient();
```

## 🎣 React Query Hooks

### Setup do Query Client

```typescript
// apps/web/src/lib/query-client.ts
import { QueryClient } from '@tanstack/react-query';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60 * 1000, // 1 minuto
      retry: 1,
    },
  },
});
```

### Hooks Customizados

```typescript
// apps/web/src/lib/hooks/use-documents.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../api';

export function useDocuments() {
  return useQuery({
    queryKey: ['documents'],
    queryFn: () => api.getDocuments(),
  });
}

export function useUploadDocument() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: ({ file, metadata }: { file: File; metadata: any }) =>
      api.uploadDocument(file, metadata),
    onSuccess: () => {
      // Invalidar cache de documentos
      queryClient.invalidateQueries({ queryKey: ['documents'] });
    },
  });
}
```

```typescript
// apps/web/src/lib/hooks/use-generate.ts
import { useMutation } from '@tanstack/react-query';
import { api } from '../api';

export function useGenerateDocument(chatId: string) {
  return useMutation({
    mutationFn: (data: {
      prompt: string;
      effort_level: number;
      context: any;
    }) => api.generateDocument(chatId, data),
    onSuccess: (data) => {
      console.log('Documento gerado:', data);
    },
  });
}
```

## 🗄️ Zustand Stores

```typescript
// apps/web/src/stores/auth.ts
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface AuthState {
  user: any | null;
  token: string | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      token: null,
      login: async (email, password) => {
        const data = await api.login(email, password);
        set({ user: data.user, token: data.access_token });
        localStorage.setItem('access_token', data.access_token);
      },
      logout: () => {
        set({ user: null, token: null });
        localStorage.removeItem('access_token');
      },
    }),
    {
      name: 'auth-storage',
    }
  )
);
```

## 💬 Exemplo: Geração de Documento

### Frontend Component

```typescript
// apps/web/src/components/generate-document.tsx
'use client';

import { useState } from 'react';
import { useGenerateDocument } from '@/lib/hooks/use-generate';

export function GenerateDocumentForm({ chatId }: { chatId: string }) {
  const [prompt, setPrompt] = useState('');
  const [effortLevel, setEffortLevel] = useState(3);
  
  const { mutate, isPending, data } = useGenerateDocument(chatId);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    
    mutate({
      prompt,
      effort_level: effortLevel,
      context: {
        // Adicionar documentos, jurisprudência, etc.
      },
    });
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label>Prompt</label>
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          className="w-full border rounded p-2"
          rows={10}
          placeholder="Descreva o documento que deseja gerar..."
        />
      </div>

      <div>
        <label>Nível de Esforço: {effortLevel}</label>
        <input
          type="range"
          min={1}
          max={5}
          value={effortLevel}
          onChange={(e) => setEffortLevel(parseInt(e.target.value))}
          className="w-full"
        />
        <p className="text-sm text-gray-500">
          {effortLevel <= 2 && 'Rápido (apenas Claude)'}
          {effortLevel === 3 && 'Balanceado (Claude + revisor)'}
          {effortLevel >= 4 && 'Máximo (todos os agentes)'}
        </p>
      </div>

      <button
        type="submit"
        disabled={isPending}
        className="bg-blue-600 text-white px-4 py-2 rounded"
      >
        {isPending ? 'Gerando...' : 'Gerar Documento'}
      </button>

      {data && (
        <div className="mt-4 p-4 bg-gray-100 rounded">
          <h3>Resultado:</h3>
          <p>Tokens: {data.total_tokens}</p>
          <p>Custo: R$ {data.total_cost.toFixed(4)}</p>
          <p>Tempo: {data.processing_time.toFixed(1)}s</p>
          <div className="mt-2">
            <pre className="whitespace-pre-wrap">
              {data.content}
            </pre>
          </div>
        </div>
      )}
    </form>
  );
}
```

## 🔄 Fluxo Completo de Integração

### 1. Usuário Faz Login

```typescript
// Frontend
const { login } = useAuthStore();
await login('user@example.com', 'password');

// Backend recebe
POST /api/auth/login
→ Valida credenciais
→ Gera JWT
→ Retorna token + dados do usuário
```

### 2. Upload de Documento

```typescript
// Frontend
const { mutate } = useUploadDocument();
mutate({ file, metadata: { category: 'PROCESSO' } });

// Backend recebe
POST /api/documents/upload
→ Salva arquivo
→ Adiciona à fila de processamento (Celery)
→ Retorna ID do documento

// Worker processa
→ Extrai texto
→ Gera chunks
→ Cria embeddings
→ Indexa no vector store
```

### 3. Geração com Multi-Agente

```typescript
// Frontend
const { mutate } = useGenerateDocument(chatId);
mutate({ prompt, effort_level: 5, context });

// Backend recebe
POST /api/chats/{id}/generate
→ Adiciona à fila de IA (Celery)
→ Retorna job_id

// Worker Multi-Agente
→ Claude gera documento
→ Gemini revisa (legal)
→ GPT revisa (textual)
→ Orquestrador consolida
→ Salva resultado

// Frontend recebe notificação
→ WebSocket/Polling
→ Exibe documento gerado
```

## ⚡ Otimizações

### 1. Cache Agressivo

```typescript
// Cache de 5 minutos para documentos
useQuery({
  queryKey: ['documents'],
  queryFn: getDocuments,
  staleTime: 5 * 60 * 1000,
});
```

### 2. Prefetching

```typescript
// Prefetch ao hover
const queryClient = useQueryClient();

<DocumentCard
  onMouseEnter={() => {
    queryClient.prefetchQuery({
      queryKey: ['document', id],
      queryFn: () => getDocument(id),
    });
  }}
/>
```

### 3. Otimistic Updates

```typescript
useMutation({
  mutationFn: updateDocument,
  onMutate: async (newData) => {
    // Cancelar queries em andamento
    await queryClient.cancelQueries({ queryKey: ['documents'] });
    
    // Snapshot do estado anterior
    const previous = queryClient.getQueryData(['documents']);
    
    // Atualizar otimisticamente
    queryClient.setQueryData(['documents'], (old) => [...old, newData]);
    
    return { previous };
  },
  onError: (err, newData, context) => {
    // Reverter em caso de erro
    queryClient.setQueryData(['documents'], context.previous);
  },
});
```

## 🚨 Tratamento de Erros

```typescript
// apps/web/src/lib/error-handler.ts
export function handleApiError(error: any) {
  if (error.response) {
    // Erro da API
    const status = error.response.status;
    const message = error.response.data?.message || 'Erro desconhecido';
    
    switch (status) {
      case 401:
        return 'Sessão expirada. Faça login novamente.';
      case 403:
        return 'Você não tem permissão para esta ação.';
      case 404:
        return 'Recurso não encontrado.';
      case 429:
        return 'Muitas requisições. Aguarde um momento.';
      case 500:
        return 'Erro no servidor. Tente novamente mais tarde.';
      default:
        return message;
    }
  } else if (error.request) {
    // Sem resposta
    return 'Não foi possível conectar ao servidor.';
  } else {
    return 'Erro inesperado.';
  }
}
```

## ✅ Checklist de Integração

- [ ] Cliente API configurado
- [ ] React Query setup
- [ ] Zustand stores criados
- [ ] Autenticação funcionando
- [ ] Upload de documentos OK
- [ ] Chat interface conectada
- [ ] Geração Multi-Agente testada
- [ ] Tratamento de erros implementado
- [ ] Loading states adicionados
- [ ] Cache configurado

## 📚 Recursos Adicionais

- [Documentação FastAPI](https://fastapi.tiangolo.com/)
- [Next.js Docs](https://nextjs.org/docs)
- [React Query](https://tanstack.com/query/latest)
- [Zustand](https://github.com/pmndrs/zustand)

---

**Status**: Guia completo de integração  
**Próximo**: Implementar frontend Next.js

