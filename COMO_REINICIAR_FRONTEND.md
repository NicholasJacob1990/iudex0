# 🔧 Como Reiniciar o Frontend Corretamente

## ⚠️ IMPORTANTE: Variáveis de Ambiente no Next.js

O Next.js **NÃO recarrega** variáveis de ambiente automaticamente com hot reload. Você precisa **parar completamente** o servidor e iniciá-lo novamente.

## 📋 Passos para Reiniciar

### Opção 1: Se o servidor está rodando no terminal
1. Vá até o terminal onde o `npm run dev` está rodando
2. Pressione `Ctrl + C` para parar
3. Execute novamente:
   ```bash
   npm run dev
   ```

### Opção 2: Se não encontrar o terminal
1. Mate o processo manualmente:
   ```bash
   # No terminal, execute:
   lsof -ti:3000 | xargs kill -9
   ```

2. Inicie o servidor novamente:
   ```bash
   cd apps/web
   npm run dev
   ```

### Opção 3: Reinício Completo (Recomendado)
```bash
# 1. Parar o servidor (se estiver rodando)
lsof -ti:3000 | xargs kill -9

# 2. Limpar cache do Next.js
cd apps/web
rm -rf .next

# 3. Iniciar novamente
npm run dev
```

## ✅ Como Verificar se Funcionou

1. Após reiniciar, abra o console do navegador (F12)
2. Na aba "Console", digite:
   ```javascript
   console.log(process.env.NEXT_PUBLIC_API_URL)
   ```
3. Deve mostrar: `http://localhost:8000/api`

4. Ou verifique na aba "Network" (Rede):
   - Clique no botão de login de teste
   - Procure a requisição `login-test`
   - A URL deve ser: `http://localhost:8000/api/auth/login-test`

## 🐛 Se Ainda Não Funcionar

Verifique se o arquivo `.env.local` está correto:
```bash
cat apps/web/.env.local
```

Deve conter:
```
NEXT_PUBLIC_API_URL=http://localhost:8000/api
```

**Nota:** O `/api` no final é essencial!

