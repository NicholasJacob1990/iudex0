# 🌐 Frontend Next.js - Documentação Completa

**Status**: 100% Implementado ✅  
**Data**: 18 de novembro de 2025

## 📖 Sumário

1. [Visão Geral](#visão-geral)
2. [Tecnologias Utilizadas](#tecnologias-utilizadas)
3. [Estrutura do Projeto](#estrutura-do-projeto)
4. [Configuração](#configuração)
5. [Componentes Principais](#componentes-principais)
6. [State Management](#state-management)
7. [Rotas e Páginas](#rotas-e-páginas)
8. [Integração com API](#integração-com-api)
9. [Como Executar](#como-executar)

---

## 🎯 Visão Geral

Frontend moderno e responsivo construído com Next.js 14, utilizando App Router, TypeScript, Tailwind CSS e Shadcn/ui. Interface completa para interagir com o backend FastAPI e sistema multi-agente de IA.

### Principais Funcionalidades

✅ **Autenticação Completa**
- Login e registro de usuários
- JWT authentication
- Protected routes
- Persistência de sessão

✅ **Dashboard Intuitivo**
- Estatísticas em tempo real
- Ações rápidas
- Documentos recentes
- Interface responsiva

✅ **Editor de Documentos**
- TipTap WYSIWYG editor
- Formatação completa (negrito, itálico, sublinhado, etc.)
- Alinhamento de texto
- Listas (ordenadas e não-ordenadas)
- Tabelas
- Undo/Redo

✅ **Chat com IA**
- Interface de conversa fluida
- Mensagens em tempo real
- Histórico de conversas
- Loading states

✅ **Upload de Arquivos**
- Drag & drop
- Múltiplos formatos (PDF, DOCX, DOC, TXT, ODT)
- Validação de tamanho (até 100MB)
- Preview de arquivos
- Status de upload

✅ **Sistema de Abas**
- Navegação por tabs
- Sidebar com menu
- Tema claro/escuro
- Responsivo (mobile-first)

---

## 🛠 Tecnologias Utilizadas

### Core
- **Next.js 14.1** - Framework React com App Router
- **React 18.2** - Biblioteca UI
- **TypeScript 5.3** - Type safety

### Styling
- **Tailwind CSS 3.4** - Utility-first CSS
- **Shadcn/ui** - Componentes UI modernos
- **next-themes** - Tema claro/escuro
- **Lucide React** - Ícones

### State & Data
- **Zustand 4.4** - State management
- **React Query 5.17** - Data fetching e cache
- **Axios 1.6** - HTTP client

### Editor & Forms
- **TipTap 2.1** - Rich text editor
- **React Hook Form 7.49** - Gerenciamento de formulários
- **Zod 3.22** - Validação de schemas
- **React Dropzone 14.2** - Upload de arquivos

### UX
- **Sonner 1.3** - Toast notifications
- **class-variance-authority** - Variants CSS
- **tailwind-merge** - Merge de classes

---

## 📁 Estrutura do Projeto

```
apps/web/
├── src/
│   ├── app/                      # Next.js App Router
│   │   ├── (auth)/              # Rotas de autenticação
│   │   │   ├── login/           # Página de login
│   │   │   └── register/        # Página de registro
│   │   │
│   │   ├── (dashboard)/         # Rotas protegidas
│   │   │   ├── dashboard/       # Dashboard principal
│   │   │   ├── minuta/          # Geração de minutas
│   │   │   ├── documents/       # Gerenciamento de docs
│   │   │   ├── models/          # Modelos salvos
│   │   │   ├── legislation/     # Busca de legislação
│   │   │   ├── jurisprudence/   # Busca de jurisprudência
│   │   │   ├── library/         # Biblioteca
│   │   │   ├── settings/        # Configurações
│   │   │   └── layout.tsx       # Layout do dashboard
│   │   │
│   │   ├── layout.tsx           # Layout raiz
│   │   └── page.tsx             # Página inicial (redirect)
│   │
│   ├── components/              # Componentes React
│   │   ├── ui/                 # Componentes base
│   │   │   ├── button.tsx      # Botão
│   │   │   ├── input.tsx       # Input
│   │   │   ├── card.tsx        # Card
│   │   │   ├── label.tsx       # Label
│   │   │   └── index.ts        # Exports
│   │   │
│   │   ├── layout/             # Componentes de layout
│   │   │   ├── dashboard-nav.tsx    # Navbar
│   │   │   ├── dashboard-sidebar.tsx # Sidebar
│   │   │   └── index.ts
│   │   │
│   │   ├── editor/             # Editor de documentos
│   │   │   ├── document-editor.tsx   # Editor TipTap
│   │   │   ├── editor-toolbar.tsx    # Toolbar
│   │   │   └── index.ts
│   │   │
│   │   ├── chat/               # Interface de chat
│   │   │   ├── chat-interface.tsx    # Wrapper do chat
│   │   │   ├── chat-message.tsx      # Mensagem
│   │   │   ├── chat-input.tsx        # Input de mensagem
│   │   │   └── index.ts
│   │   │
│   │   ├── upload/             # Upload de arquivos
│   │   │   ├── file-upload.tsx       # Componente de upload
│   │   │   └── index.ts
│   │   │
│   │   ├── providers/          # Context providers
│   │   │   └── theme-provider.tsx    # Tema
│   │   │
│   │   └── index.ts            # Exports gerais
│   │
│   ├── stores/                 # Zustand stores
│   │   ├── auth-store.ts       # Autenticação
│   │   ├── chat-store.ts       # Chat e IA
│   │   ├── document-store.ts   # Documentos
│   │   ├── ui-store.ts         # UI state
│   │   └── index.ts
│   │
│   ├── lib/                    # Utilidades
│   │   ├── api-client.ts       # Cliente HTTP
│   │   ├── query-client.ts     # React Query config
│   │   ├── utils.ts            # Funções helper
│   │   └── index.ts
│   │
│   └── styles/                 # Estilos
│       └── globals.css         # CSS global + Tailwind
│
├── package.json                # Dependências
├── tsconfig.json              # TypeScript config
├── tailwind.config.ts         # Tailwind config
├── postcss.config.js          # PostCSS config
├── next.config.js             # Next.js config
├── .eslintrc.json            # ESLint config
├── .gitignore                # Git ignore
├── .env.example              # Variáveis de ambiente
└── README.md                 # Documentação
```

**Total**: 42 arquivos TypeScript/React

---

## ⚙️ Configuração

### 1. Variáveis de Ambiente

Crie `.env.local`:

```env
# API Backend
NEXT_PUBLIC_API_URL=http://localhost:8000

# App Info
NEXT_PUBLIC_APP_NAME=Iudex
NEXT_PUBLIC_APP_VERSION=1.0.0

# Feature Flags
NEXT_PUBLIC_ENABLE_OCR=true
NEXT_PUBLIC_ENABLE_TRANSCRIPTION=true
NEXT_PUBLIC_ENABLE_PODCAST=true
NEXT_PUBLIC_ENABLE_DIAGRAMS=true
```

### 2. Instalação

```bash
cd apps/web
npm install
```

### 3. Executar

```bash
# Desenvolvimento
npm run dev

# Build
npm run build

# Produção
npm start
```

Acesse: **http://localhost:3000**

---

## 🧩 Componentes Principais

### 1. DocumentEditor (TipTap)

Editor WYSIWYG completo com todas as funcionalidades.

```tsx
import { DocumentEditor } from '@/components/editor';

<DocumentEditor
  content={content}
  onChange={setContent}
  editable={true}
  placeholder="Digite aqui..."
/>
```

**Funcionalidades**:
- Formatação: negrito, itálico, sublinhado, tachado
- Alinhamento: esquerda, centro, direita, justificado
- Listas: ordenadas e não-ordenadas
- Tabelas com redimensionamento
- Undo/Redo
- Placeholder customizável

### 2. ChatInterface

Interface de chat para conversar com IA.

```tsx
import { ChatInterface } from '@/components/chat';

<ChatInterface chatId={chatId} />
```

**Funcionalidades**:
- Exibição de mensagens
- Scroll automático
- Loading states
- Diferenciação visual (usuário/IA)
- Timestamp em cada mensagem

### 3. FileUpload

Componente de upload com drag & drop.

```tsx
import { FileUpload } from '@/components/upload';

<FileUpload
  onUploadComplete={(id) => console.log('Uploaded:', id)}
  acceptedFormats={['.pdf', '.docx', '.doc']}
/>
```

**Funcionalidades**:
- Drag & drop
- Múltiplos arquivos
- Validação de tipo e tamanho
- Preview de arquivos
- Feedback visual
- Arquivos aceitos/rejeitados

### 4. UI Components (Shadcn)

Componentes base reutilizáveis:

```tsx
import { Button, Input, Card, Label } from '@/components/ui';

// Button
<Button variant="default" size="lg">Clique aqui</Button>

// Input
<Input type="email" placeholder="seu@email.com" />

// Card
<Card>
  <CardHeader>
    <CardTitle>Título</CardTitle>
    <CardDescription>Descrição</CardDescription>
  </CardHeader>
  <CardContent>Conteúdo</CardContent>
</Card>
```

**Variants disponíveis**:
- Button: default, destructive, outline, secondary, ghost, link
- Sizes: default, sm, lg, icon

---

## 🗄️ State Management

### Auth Store

Gerencia autenticação e perfil do usuário.

```tsx
import { useAuthStore } from '@/stores';

const { user, isAuthenticated, login, logout, register } = useAuthStore();

// Login
await login('email@example.com', 'senha123');

// Logout
logout();

// Verificar autenticação
if (isAuthenticated) {
  console.log('User:', user);
}
```

### Chat Store

Gerencia conversas e geração de documentos com IA.

```tsx
import { useChatStore } from '@/stores';

const {
  chats,
  currentChat,
  createChat,
  sendMessage,
  generateDocument
} = useChatStore();

// Criar chat
const chat = await createChat('Nova Minuta');

// Enviar mensagem
await sendMessage('Preciso de uma petição inicial...');

// Gerar documento
const result = await generateDocument({
  prompt: 'Elabore uma petição...',
  effort_level: 5,
  document_type: 'minuta'
});
```

### Document Store

Gerencia upload e documentos.

```tsx
import { useDocumentStore } from '@/stores';

const {
  documents,
  uploadDocument,
  deleteDocument,
  processDocument
} = useDocumentStore();

// Upload
const doc = await uploadDocument(file, { type: 'pdf' });

// Processar
await processDocument(doc.id, { ocr: true });

// Deletar
await deleteDocument(doc.id);
```

### UI Store

Gerencia estado da interface.

```tsx
import { useUIStore } from '@/stores';

const {
  activeTab,
  sidebarOpen,
  theme,
  setActiveTab,
  toggleSidebar,
  setTheme
} = useUIStore();

// Mudar tab
setActiveTab('minuta');

// Toggle sidebar
toggleSidebar();

// Mudar tema
setTheme('dark');
```

---

## 🛣️ Rotas e Páginas

### Rotas Públicas

| Rota | Página | Descrição |
|------|--------|-----------|
| `/` | Home | Redirect para `/dashboard` |
| `/login` | Login | Autenticação |
| `/register` | Registro | Criar conta |

### Rotas Protegidas (Dashboard)

| Rota | Página | Descrição |
|------|--------|-----------|
| `/dashboard` | Dashboard | Visão geral |
| `/minuta` | Nova Minuta | Geração de documentos com IA |
| `/documents` | Documentos | Upload e gerenciamento |
| `/models` | Modelos | Templates salvos |
| `/legislation` | Legislação | Busca de leis |
| `/jurisprudence` | Jurisprudência | Busca de decisões |
| `/library` | Biblioteca | Organização de recursos |
| `/settings` | Configurações | Perfil e preferências |

### Proteção de Rotas

O layout `(dashboard)/layout.tsx` verifica autenticação:

```tsx
if (!isAuthenticated) {
  router.push('/login');
}
```

---

## 🔌 Integração com API

### API Client

Cliente HTTP centralizado com interceptors.

```tsx
import apiClient from '@/lib/api-client';

// Login
const response = await apiClient.login(email, password);

// Upload documento
const doc = await apiClient.uploadDocument(file);

// Gerar com IA
const result = await apiClient.generateDocument(chatId, {
  prompt: 'Gerar documento...',
  effort_level: 5
});

// Requisição customizada
const data = await apiClient.request('GET', '/custom/endpoint');
```

### Interceptors

**Request**:
- Adiciona token JWT automaticamente
- Configura headers

**Response**:
- Trata erros 401 (logout automático)
- Exibe toast de erro
- Log de erros

### React Query

Cache e sincronização de dados:

```tsx
import { useQuery, useMutation } from '@tanstack/react-query';

// Query
const { data, isLoading } = useQuery({
  queryKey: ['documents'],
  queryFn: () => apiClient.getDocuments()
});

// Mutation
const mutation = useMutation({
  mutationFn: (file: File) => apiClient.uploadDocument(file),
  onSuccess: () => {
    queryClient.invalidateQueries(['documents']);
  }
});
```

---

## 🚀 Como Executar

### Desenvolvimento

```bash
cd apps/web
npm install
cp .env.example .env.local
npm run dev
```

Abra: **http://localhost:3000**

### Build de Produção

```bash
npm run build
npm start
```

### Linting

```bash
npm run lint
npm run type-check
```

---

## 🎨 Customização

### Tema

Edite `tailwind.config.ts` para customizar cores:

```ts
theme: {
  extend: {
    colors: {
      primary: 'hsl(221, 83%, 53%)',
      // ...
    }
  }
}
```

### Componentes

Adicione novos componentes em `src/components/`.

Siga o padrão:
1. Crie o componente
2. Adicione ao `index.ts`
3. Use TypeScript estrito
4. Documente props

---

## 📊 Estatísticas

- **42 arquivos** TypeScript/React criados
- **8 páginas** principais implementadas
- **4 stores** Zustand
- **15+ componentes** UI
- **3 componentes** principais (Editor, Chat, Upload)
- **100% TypeScript** com type safety
- **Responsivo** (mobile-first)
- **Tema claro/escuro** completo
- **Acessibilidade** (aria-labels, keyboard nav)

---

## ✅ Checklist de Funcionalidades

### Autenticação
- [x] Login
- [x] Registro
- [x] Logout
- [x] Persistência de sessão
- [x] Protected routes
- [x] JWT handling

### Dashboard
- [x] Estatísticas
- [x] Ações rápidas
- [x] Documentos recentes
- [x] Cards informativos

### Editor
- [x] TipTap integrado
- [x] Toolbar completo
- [x] Formatação de texto
- [x] Alinhamento
- [x] Listas
- [x] Tabelas
- [x] Undo/Redo

### Chat
- [x] Interface de mensagens
- [x] Envio de mensagens
- [x] Loading states
- [x] Scroll automático
- [x] Timestamps

### Documentos
- [x] Upload drag & drop
- [x] Lista de documentos
- [x] Visualização
- [x] Exclusão
- [x] Status (pendente/processando/completo)

### UI/UX
- [x] Tema claro/escuro
- [x] Toast notifications
- [x] Loading states
- [x] Error handling
- [x] Responsivo
- [x] Sidebar colapsável

---

## 🔜 Próximos Passos

- [ ] Testes unitários (Jest + React Testing Library)
- [ ] Testes E2E (Playwright)
- [ ] Storybook para componentes
- [ ] PWA (Progressive Web App)
- [ ] Internacionalização (i18n)
- [ ] Analytics integration
- [ ] Error monitoring (Sentry)

---

**Frontend 100% Implementado e Pronto para Uso! ✅**

Para mais informações, consulte:
- `apps/web/README.md` - Guia específico do frontend
- `INTEGRACAO.md` - Guia de integração frontend-backend
- `PROXIMOS_PASSOS.md` - Próximas implementações

