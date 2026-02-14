# Teams Bot

Os endpoints do bot do Teams ficam no backend FastAPI.

**Arquivo principal:** `apps/api/app/api/endpoints/teams_bot.py`

Este diretorio existe apenas como referencia na estrutura do Teams App.
O bot e registrado no manifest.json e as requisicoes do Bot Framework
sao roteadas diretamente para a API FastAPI.

## Fluxo

1. Teams envia atividades para `POST /api/teams/messages`
2. O endpoint FastAPI processa via Bot Framework SDK (Python)
3. Respostas sao enviadas de volta ao Teams via `turn_context.send_activity()`

## Comandos disponíveis

| Comando      | Descricao                          |
|--------------|-------------------------------------|
| pesquisar    | Pesquisar no corpus juridico        |
| analisar     | Analisar texto com IA juridica      |
| workflow     | Iniciar um workflow juridico        |
| status       | Ver status de um workflow           |
| ajuda        | Ver comandos disponiveis            |
