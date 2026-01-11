# 🔧 CORREÇÃO: Erro "Method Not Allowed"

## ✅ Diagnóstico

O endpoint `/api/auth/login-test` funciona corretamente quando testado com `curl`:
```bash
curl -X POST http://localhost:8000/api/auth/login-test
# Retorna: {"access_token": "...", "refresh_token": "...", "user": {...}}
```

Mas retorna `{"detail":"Method Not Allowed"}` quando chamado do frontend.

## 🔍 Possíveis Causas

### 1. Servidor Backend não foi reiniciado após adicionar a rota
**Solução:** Reinicie o servidor backend

```bash
# Pare o servidor backend
# No terminal onde está rodando, pressione Ctrl + C
# OU mate o processo:
lsof -ti:8000 | xargs kill -9

# Reinicie
cd apps/api
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Frontend está usando método errado
**Verificação:** Abra o Console do navegador (F12) → Aba Network → Veja a requisição `login-test`:
- **Method** deve ser: `POST` ✅
- Se for `GET` ou `OPTIONS` ❌ → problema no código

### 3. Interceptor do axios está modificando a requisição
**Verificação:** Os logs no console devem mostrar:
```
[API Client] Login Test - Base URL: http://localhost:8000/api
```

## 🚨 AÇÃO IMEDIATA

### Passo 1: Reinicie o Backend
```bash
cd apps/api
# Pare o servidor (Ctrl + C)
# Reinicie
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Passo 2: Verifique se a rota está registrada
Abra no navegador: `http://localhost:8000/docs`

Procure por `/api/auth/login-test` na documentação Swagger.

### Passo 3: Teste diretamente no navegador
Abra o Console do navegador (F12) e execute:
```javascript
fetch('http://localhost:8000/api/auth/login-test', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json'
  }
})
.then(r => r.json())
.then(console.log)
.catch(console.error)
```

Se funcionar aqui, o problema é no código do frontend.

## 📝 Checklist

- [ ] Backend foi reiniciado após adicionar a rota `/login-test`
- [ ] Rota aparece em `http://localhost:8000/docs`
- [ ] Teste direto no console do navegador funciona
- [ ] Frontend está usando método POST (verificar na aba Network)
- [ ] URL base está correta: `http://localhost:8000/api`

## 🔍 Debug no Console

Após reiniciar o backend, abra o Console do navegador e clique no botão de teste. Você deve ver:

```
[API Client] Login Test - Base URL: http://localhost:8000/api
[API Client] Login Test - Full URL: http://localhost:8000/api/auth/login-test
```

Se aparecer erro, os logs vão mostrar exatamente o problema!



