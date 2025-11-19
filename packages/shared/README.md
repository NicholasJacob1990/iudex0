# @iudex/shared

Package compartilhado contendo tipos, constantes e utilitários usados em todo o monorepo do Iudex.

## Estrutura

```
src/
├── types/           # Definições de tipos TypeScript
│   ├── user.ts
│   ├── document.ts
│   ├── ai.ts
│   ├── chat.ts
│   ├── jurisprudence.ts
│   ├── legislation.ts
│   └── library.ts
├── constants/       # Constantes da aplicação
│   └── index.ts
└── utils/           # Funções utilitárias
    ├── format.ts
    ├── validation.ts
    ├── crypto.ts
    └── file.ts
```

## Uso

```typescript
import { User, Document, formatBytes, isValidEmail } from '@iudex/shared';
```

## Build

```bash
npm run build
```

## Desenvolvimento

```bash
npm run dev
```

