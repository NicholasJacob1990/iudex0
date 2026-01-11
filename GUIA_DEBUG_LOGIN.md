# 🔍 GUIA DE DEBUG - Login de Teste Não Funciona

## ✅ O que está funcionando:
- ✅ Backend está rodando (porta 8000)
- ✅ Endpoint `/api/auth/login-test` responde corretamente (testado com curl)
- ✅ Frontend está rodando (porta 3000)
- ✅ Configurações de URL estão corretas

## 🔍 Como debugar:

### 1. Abra o Console do Navegador (F12)

### 2. Clique no botão "⚡ Entrar como Visitante (Teste)"

### 3. Verifique os logs no Console:

Você deve ver:
```
[Login Page] Iniciando login de teste...
[Auth Store] loginTest chamado
[API Client] Login Test - Base URL: http://localhost:8000/api
[API Client] Login Test - Success: 200
[Auth Store] Resposta recebida: teste@iudex.ai
[Auth Store] Estado atualizado - isAuthenticated: true
[Login Page] Login de teste bem-sucedido!
```

### 4. Se houver erro, verifique:

**Aba Network (Rede):**
- Procure a requisição `login-test`
- Verifique a URL completa: deve ser `http://localhost:8000/api/auth/login-test`
- Verifique o Status: deve ser `200 OK`
- Se for `404`, o problema é a URL base
- Se for `CORS error`, precisa configurar CORS no backend

**Aba Application → Local Storage:**
- Procure `auth-storage`
- Deve conter:
  ```json
  {
    "state": {
      "user": {...},
      "isAuthenticated": true
    }
  }
  ```

### 5. Possíveis problemas e soluções:

#### Problema: Erro 404 na requisição
**Solução:** O frontend não foi reiniciado após mudanças no `.env.local` ou `next.config.js`
```bash
# Pare o servidor completamente
lsof -ti:3000 | xargs kill -9

# Limpe o cache
cd apps/web
rm -rf .next

# Reinicie
npm run dev
```

#### Problema: CORS Error
**Solução:** Adicionar CORS no backend
```python
# apps/api/app/main.py
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

#### Problema: Redirecionamento não funciona
**Solução:** Verificar se o estado está sendo persistido corretamente
- Abra o Console
- Digite: `localStorage.getItem('auth-storage')`
- Deve retornar um JSON com `isAuthenticated: true`

#### Problema: Página fica em branco após login
**Solução:** Verificar se o `DashboardLayout` está aguardando hidratação
- O layout deve mostrar um spinner primeiro
- Depois deve carregar o dashboard

## 📝 Próximos Passos:

1. **Abra o Console do Navegador (F12)**
2. **Clique no botão de teste**
3. **Copie TODOS os logs que aparecerem**
4. **Envie os logs para análise**

Os logs vão mostrar exatamente onde está o problema!



