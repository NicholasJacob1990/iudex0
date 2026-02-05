# Ask Components

Componentes da interface de consulta do Iudex.

## AskModeToggle

Toggle segmentado para alternar entre 3 modos de consulta ao Claude.

### Uso

```tsx
import { AskModeToggle, type QueryMode } from '@/components/ask';

function MyComponent() {
  const [mode, setMode] = useState<QueryMode>('auto');

  return (
    <AskModeToggle
      mode={mode}
      onChange={setMode}
    />
  );
}
```

### Props

| Prop | Tipo | Descrição |
|------|------|-----------|
| `mode` | `QueryMode` | Modo atual selecionado (`'auto' \| 'edit' \| 'answer'`) |
| `onChange` | `(mode: QueryMode) => void` | Callback chamado quando o modo muda |

### Modos

- **Auto (Automático)**: Claude decide automaticamente se deve editar ou responder
  - Ícone: Sparkles
  - Uso recomendado: Quando não há certeza da melhor abordagem

- **Edit (Editar)**: Edita diretamente o documento no canvas
  - Ícone: Edit3
  - Uso recomendado: Quando você quer modificações diretas no documento

- **Answer (Responder)**: Responde com análise sem editar
  - Ícone: MessageSquare
  - Uso recomendado: Quando você quer apenas análise ou sugestões

### Features

- Estilo segmented control (similar ao padrão Tabs do shadcn/ui)
- Tooltips explicativos em cada opção
- Responsivo: labels aparecem apenas em telas ≥ `sm` (640px)
- Acessibilidade: roles ARIA e navegação por teclado
- Integrado com theme system (dark/light mode)

### Exemplo Completo

Veja `ask-mode-toggle.example.tsx` para um exemplo interativo completo.
