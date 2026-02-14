# RunPod no Iudex: guia de teste local e deploy

## Objetivo
Permitir uso do provider `runpod` antes do deploy completo, sem cair no problema de `localhost`.

## Problema principal
O worker do RunPod precisa baixar o áudio via URL HTTP pública.  
Se a API gerar URL com `http://localhost:8000`, o RunPod não consegue acessar.

## Solução implementada
O backend agora resolve a base URL do áudio nesta ordem:
1. `IUDEX_RUNPOD_PUBLIC_BASE_URL` (recomendado)
2. `IUDEX_PUBLIC_BASE_URL` (alias legado)
3. `IUDEX_BASE_URL`
4. `http://localhost:8000` (fallback)

Também valida host local/privado para RunPod e retorna erro explícito quando a URL não é pública.

## Teste local sem deploy (recomendado)
### 1) Subir API local
```bash
cd apps/api
.venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 2) Abrir túnel público
```bash
./apps/api/scripts/runpod-local-tunnel.sh 8000
```

O script detecta `cloudflared` (ou `ngrok`) e imprime:
```bash
export IUDEX_RUNPOD_PUBLIC_BASE_URL=https://....trycloudflare.com
```

### 3) Configurar variáveis
No shell onde a API roda (ou em `apps/api/.env`):
```bash
RUNPOD_API_KEY=...
RUNPOD_ENDPOINT_ID=...
IUDEX_RUNPOD_PUBLIC_BASE_URL=https://....trycloudflare.com
```

### 4) Rodar transcrição com engine `runpod`
No frontend/API, selecione `transcription_engine=runpod`.

## Deploy (produção)
Em produção, normalmente não precisa de túnel:
```bash
IUDEX_BASE_URL=https://api.seudominio.com
# opcional manter explícito:
IUDEX_RUNPOD_PUBLIC_BASE_URL=https://api.seudominio.com
```

## Observações importantes
- Se houver múltiplas instâncias da API, use storage compartilhado para os arquivos de job.
- `SECRET_KEY` deve ser estável para validar o token HMAC da rota de áudio.
- `IUDEX_ALLOW_PRIVATE_BASE_URL_FOR_RUNPOD=true` só deve ser usado em cenários especiais de rede privada.

## Checklist rápido de diagnóstico
1. `GET https://api.runpod.ai/v2/$RUNPOD_ENDPOINT_ID/health` deve mostrar worker `ready`/`running`.
2. Job local não deve ficar preso em fallback para Whisper.
3. URL gerada para `/api/transcription/audio/{job_id}` deve ser de host público, nunca `localhost`.
