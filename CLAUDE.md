# CLAUDE.md — Memória Persistente do Projeto Iudex

> Este arquivo é carregado automaticamente pelo Claude Code em cada sessão.
> Mantenha-o atualizado com decisões, convenções e lições aprendidas.

## Sobre o Projeto

**Iudex** é uma plataforma jurídica com IA multi-agente para análise de documentos, geração de minutas e assistência jurídica.

- **Arquitetura**: Monorepo com Turborepo
- **Apps**: `apps/api` (FastAPI/Python), `apps/web` (Next.js/React), `apps/storage`
- **Packages**: Compartilhados em `packages/*`

## Comandos Essenciais

```bash
# Desenvolvimento
pnpm dev              # Inicia todos os apps em modo dev
pnpm build            # Build de produção
pnpm lint             # Lint em todo o monorepo
pnpm type-check       # Verificação de tipos
pnpm test             # Roda testes

# Database (via apps/api)
pnpm db:migrate       # Roda migrações
pnpm db:seed          # Seed do banco
pnpm db:studio        # Interface do Prisma

# API Python (apps/api)
cd apps/api && uvicorn app.main:app --reload
pytest                # Testes Python
```

## Convenções de Código

### Frontend (apps/web)
- React com TypeScript estrito
- Componentes em `src/components/`
- Stores Zustand em `src/stores/`
- API calls via fetch com streaming SSE
- TailwindCSS para estilos
- shadcn/ui para componentes base

### Backend (apps/api)
- FastAPI com Python 3.11+
- Endpoints em `app/api/endpoints/`
- Services em `app/services/`
- Streaming via SSE para chat
- Suporte a múltiplos LLMs (OpenAI, Gemini, Claude)

## Regras de Verificação (OBRIGATÓRIO)

Após qualquer mudança de código:
1. `pnpm lint` — deve passar sem erros
2. `pnpm type-check` — tipos devem estar corretos
3. `pnpm test` — testes devem passar
4. Se falhar, corrija e repita

## Arquivos Importantes

- `@status.md` — Status vivo das implementações recentes
- `docs/AI_LOG.md` — Log de sessões do Claude Code
- `docs/LESSONS_LEARNED.md` — Lições aprendidas
- `.claude/rules/*.md` — Regras modulares por área

## Gotchas e Alertas

- **SSR/Hidratação**: TipTap requer `immediatelyRender: false` no `useEditor`
- **Next Image**: Sempre definir `sizes` quando usar `fill`
- **Streaming**: Gemini usa `thinking_mode=high` para streaming de thoughts

## Estrutura de Memória

```
.claude/
├── settings.json           # Permissões do Claude Code
├── settings.local.json     # Config local (não versionar)
└── rules/
    ├── testing.md          # Regras de testes
    ├── code-style.md       # Estilo de código
    ├── security.md         # Regras de segurança
    └── api.md              # Regras específicas da API

docs/
├── AI_LOG.md               # Histórico de sessões
└── LESSONS_LEARNED.md      # Lições consolidadas
```

## Workflow de Sessão (OBRIGATÓRIO)

### Ao iniciar
1. Claude Code carrega este arquivo automaticamente
2. Ler `docs/AI_LOG.md` para contexto das últimas sessões

### Durante o trabalho
1. Rodar `pnpm lint && pnpm type-check` após mudanças
2. **SEMPRE atualizar `docs/AI_LOG.md` após mudanças significativas**

### Ao encontrar erros/bugs
**SEMPRE documentar em `docs/LESSONS_LEARNED.md`:**
```markdown
## [DATA] — Título do Problema
### Problema
- O que aconteceu
### Causa Raiz
- Por que aconteceu
### Solução
- Como foi resolvido
### Prevenção
- Como evitar no futuro
```

### Ao finalizar sessão
1. Garantir que testes passam
2. Atualizar `docs/AI_LOG.md` com resumo da sessão
3. Usar `/compact` preservando contexto útil

### Continuar sessão anterior
```bash
claude --continue  # Retoma última sessão neste diretório
```

## Versionamento

- Commits devem seguir Conventional Commits
- PRs devem ter descrição clara do que foi alterado
- Este arquivo vai para o git (compartilhado com o time)
