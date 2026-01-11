# Correção do Login de Teste

## Problema
O frontend estava tentando acessar `http://localhost:8000/auth/login-test` mas o endpoint correto é `http://localhost:8000/api/auth/login-test`.

## Causa
A variável de ambiente `NEXT_PUBLIC_API_URL` no arquivo `.env.local` estava configurada como `http://localhost:8000` (sem o `/api`).

## Solução
Atualizado o arquivo `apps/web/.env.local`:

```bash
# Antes
NEXT_PUBLIC_API_URL=http://localhost:8000

# Depois
NEXT_PUBLIC_API_URL=http://localhost:8000/api
```

Também mudei `NEXT_PUBLIC_MOCK_MODE=false` para usar o backend real.

## Como Testar

1. **Reinicie o servidor de desenvolvimento do frontend**:
   ```bash
   cd apps/web
   npm run dev
   # ou
   yarn dev
   ```

2. **Acesse** `http://localhost:3000/login`

3. **Clique no botão** "⚡ Entrar como Visitante (Teste)"

4. **Você será redirecionado** para `/dashboard` com o usuário de teste logado:
   - Email: `teste@iudex.ai`
   - Nome: "Usuário de Teste"
   - OAB: 999999/SP
   - Plano: PROFESSIONAL

## Observação
Os erros no console sobre "listener" e "translate-page" são de extensões do navegador (provavelmente tradutor) e não afetam o funcionamento do app.

