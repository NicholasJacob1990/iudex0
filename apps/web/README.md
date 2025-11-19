# 🌐 Iudex Web Frontend

Frontend moderno em Next.js 14 para a plataforma Iudex de IA jurídica.

## 🚀 Tecnologias

- **Next.js 14** - Framework React com App Router
- **TypeScript** - Type safety
- **Tailwind CSS** - Utility-first CSS
- **Shadcn/ui** - Componentes UI
- **TipTap** - Editor WYSIWYG
- **React Query** - Data fetching
- **Zustand** - State management
- **Axios** - HTTP client
- **Sonner** - Toast notifications

## 📦 Instalação

```bash
# Instalar dependências
npm install

# Copiar e configurar variáveis de ambiente
cp .env.example .env.local
```

## ⚙️ Configuração

Edite `.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## 🏃 Executar

```bash
# Desenvolvimento
npm run dev

# Build
npm run build

# Produção
npm start

# Lint
npm run lint

# Type check
npm run type-check
```

Acesse: **http://localhost:3000**

## 📁 Estrutura

```
src/
├── app/              # Next.js App Router
│   ├── (auth)/      # Rotas de autenticação
│   ├── (dashboard)/ # Rotas protegidas
│   ├── layout.tsx   # Layout raiz
│   └── page.tsx     # Página inicial
│
├── components/      # Componentes React
│   ├── ui/         # Componentes base (Shadcn)
│   ├── layout/     # Layout components
│   ├── editor/     # Editor TipTap
│   ├── chat/       # Interface de chat
│   ├── upload/     # Upload de arquivos
│   └── providers/  # Context providers
│
├── lib/            # Utilidades
│   ├── api-client.ts   # Cliente HTTP
│   ├── query-client.ts # React Query config
│   └── utils.ts        # Funções helper
│
├── stores/         # Zustand stores
│   ├── auth-store.ts
│   ├── chat-store.ts
│   ├── document-store.ts
│   └── ui-store.ts
│
└── styles/         # Estilos globais
    └── globals.css
```

## 🎨 Componentes Principais

### Autenticação

```tsx
// Login
/login

// Registro
/register
```

### Dashboard

```tsx
// Dashboard principal
/dashboard

// Nova minuta com IA
/minuta

// Gerenciar documentos
/documents

// Modelos
/models

// Legislação
/legislation

// Jurisprudência
/jurisprudence

// Biblioteca
/library

// Configurações
/settings
```

### Editor TipTap

```tsx
import { DocumentEditor } from '@/components/editor';

<DocumentEditor
  content={content}
  onChange={setContent}
  placeholder="Digite aqui..."
/>
```

### Chat com IA

```tsx
import { ChatInterface } from '@/components/chat';

<ChatInterface chatId={chatId} />
```

### Upload de Arquivos

```tsx
import { FileUpload } from '@/components/upload';

<FileUpload
  onUploadComplete={(id) => console.log(id)}
  acceptedFormats={['.pdf', '.docx']}
/>
```

## 🔄 State Management (Zustand)

### Auth Store

```tsx
import { useAuthStore } from '@/stores';

const { user, login, logout, isAuthenticated } = useAuthStore();
```

### Chat Store

```tsx
import { useChatStore } from '@/stores';

const { chats, currentChat, sendMessage, generateDocument } = useChatStore();
```

### Document Store

```tsx
import { useDocumentStore } from '@/stores';

const { documents, uploadDocument, deleteDocument } = useDocumentStore();
```

## 🌐 API Client

```tsx
import apiClient from '@/lib/api-client';

// Login
await apiClient.login(email, password);

// Upload documento
await apiClient.uploadDocument(file);

// Gerar minuta
await apiClient.generateDocument(chatId, {
  prompt: 'Elabore uma petição...',
  effort_level: 5
});
```

## 🎨 Tema e Estilos

O app suporta modo claro/escuro:

```tsx
import { useTheme } from 'next-themes';

const { theme, setTheme } = useTheme();
```

## 📝 Formulários

Usando React Hook Form + Zod:

```tsx
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';

const schema = z.object({
  email: z.string().email(),
  password: z.string().min(8),
});

const { register, handleSubmit } = useForm({
  resolver: zodResolver(schema),
});
```

## 🔔 Notificações

Usando Sonner:

```tsx
import { toast } from 'sonner';

toast.success('Sucesso!');
toast.error('Erro!');
toast.info('Info');
toast.warning('Aviso');
```

## 🚀 Deploy

### Vercel (Recomendado)

```bash
npm install -g vercel
vercel
```

### Docker

```dockerfile
FROM node:18-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build
CMD ["npm", "start"]
```

## 🧪 Testes

```bash
# TODO: Adicionar testes
npm test
```

## 📚 Recursos

- [Next.js Docs](https://nextjs.org/docs)
- [Tailwind CSS](https://tailwindcss.com/docs)
- [Shadcn/ui](https://ui.shadcn.com/)
- [TipTap](https://tiptap.dev/)
- [React Query](https://tanstack.com/query)
- [Zustand](https://zustand-demo.pmnd.rs/)

## 🤝 Contribuindo

Este é um projeto proprietário. Entre em contato para contribuições.

## 📄 Licença

Propriedade de Iudex © 2025
