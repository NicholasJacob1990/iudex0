# 🚨 SOLUÇÃO: Erro "Method Not Allowed"

## ✅ Diagnóstico Completo

O erro `{"detail":"Method Not Allowed"}` acontece porque **o servidor backend não foi reiniciado** após adicionar a nova rota `/api/auth/login-test`.

### Evidências:
- ✅ Endpoint funciona via `curl POST` (testado)
- ✅ CORS está configurado corretamente
- ✅ Código da rota está correto
- ❌ Servidor não reconhece a rota (precisa reiniciar)

## 🔴 SOLUÇÃO: Reiniciar o Backend

### Opção 1: Manual (Recomendado)

1. **Vá até o terminal onde o backend está rodando**
2. **Pressione `Ctrl + C`** para parar
3. **Reinicie:**
   ```bash
   cd apps/api
   python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

### Opção 2: Script Automático

Execute o script que criei:
```bash
./restart-backend.sh
```

### Opção 3: Matar Processo e Reiniciar

```bash
# Matar processo na porta 8000
lsof -ti:8000 | xargs kill -9

# Aguardar 2 segundos
sleep 2

# Reiniciar
cd apps/api
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## ✅ Como Verificar se Funcionou

### 1. Verifique se o servidor está rodando:
```bash
curl http://localhost:8000/health
```
Deve retornar: `{"status":"ok",...}`

### 2. Verifique se a rota está disponível:
Abra no navegador: `http://localhost:8000/docs`

Procure por `/api/auth/login-test` na lista de endpoints.

### 3. Teste o endpoint:
```bash
curl -X POST http://localhost:8000/api/auth/login-test
```
Deve retornar tokens e dados do usuário.

### 4. Teste no Frontend:
1. Abra `http://localhost:3000/login`
2. Abra o Console (F12)
3. Clique em "⚡ Entrar como Visitante (Teste)"
4. Deve funcionar! ✅

## 🔍 Se Ainda Não Funcionar

Verifique os logs do backend no terminal. Você deve ver algo como:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete.
```

Se não aparecer "Application startup complete", há um erro no código que precisa ser corrigido.

## 📝 Checklist Final

- [ ] Backend foi completamente parado
- [ ] Backend foi reiniciado com `--reload`
- [ ] Rota aparece em `http://localhost:8000/docs`
- [ ] Teste com curl funciona
- [ ] Frontend foi reiniciado também (para garantir)
- [ ] Teste no navegador funciona

## 🆘 Ainda com Problemas?

Envie:
1. Output completo do terminal do backend ao iniciar
2. Logs do console do navegador ao clicar no botão
3. Resultado de: `curl -X POST http://localhost:8000/api/auth/login-test`



