# Regras de Testes

## Obrigatório Antes de Commitar

- Rodar `pnpm test` e garantir que todos passam
- Se criar nova funcionalidade, criar teste correspondente
- Testes de integração para endpoints da API

## Frontend (apps/web)

- Testes com Jest + React Testing Library
- Testar comportamento, não implementação
- Mock de API calls com MSW quando necessário

## Backend (apps/api)

- Testes com pytest
- Fixtures em `tests/conftest.py`
- Testar casos de sucesso e erro
- Usar `pytest -v` para output detalhado

## Cobertura

- Mínimo 70% de cobertura em código novo
- Rodar `pytest --cov` para verificar cobertura

## Quando Testes Falham

1. Não ignorar falhas
2. Investigar causa raiz
3. Documentar em `docs/LESSONS_LEARNED.md` se for bug sutil
4. Corrigir e rodar novamente
