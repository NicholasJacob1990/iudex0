# Regras de Estilo de Código

## TypeScript/JavaScript

- Usar TypeScript estrito (`strict: true`)
- Preferir `const` sobre `let`, nunca usar `var`
- Nomes descritivos: `getUserById` não `getUser`
- Interfaces para tipos de objetos, types para unions
- Async/await sobre .then()

## React

- Componentes funcionais com hooks
- Custom hooks para lógica reutilizável
- Evitar prop drilling — usar stores Zustand
- Memoização só quando necessário (medir primeiro)

## Python

- Type hints em todas as funções públicas
- Docstrings para funções complexas
- f-strings para formatação
- Async def para operações I/O

## Formatação

- Prettier para TS/JS (já configurado)
- Black para Python
- Rodar `pnpm format` antes de commitar

## Imports

- Ordenar: externos, internos, relativos
- Usar aliases de path (`@/components/...`)
- Evitar imports circulares
