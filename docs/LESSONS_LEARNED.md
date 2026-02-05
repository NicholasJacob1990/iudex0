# LESSONS_LEARNED.md — Lições Aprendidas

> Documente aqui erros, bugs sutis e soluções encontradas.
> Este arquivo serve como base de conhecimento para evitar repetir erros.

---

## 2026-02-04 — VAD não ajustava word timestamps ao pular silêncio inicial

### Problema
Quando o áudio tinha silêncio inicial > 30s, o VAD (Voice Activity Detection) pulava esse silêncio e transcrevia apenas a partir do início da fala. Os timestamps dos **segmentos** eram ajustados corretamente, mas os timestamps das **words** individuais não eram ajustados, causando dessincronização entre clique na palavra e posição do áudio.

### Causa Raiz
No código `_transcribe_with_vad()` em `mlx_vomo.py`, após pular o silêncio inicial:
```python
# ANTES (bug):
for seg in result["segments"]:
    seg["start"] += speech_start  # ✅ Segmento OK
    seg["end"] += speech_start    # ✅ Segmento OK
    # ⚠️ FALTAVA: ajustar words
```

### Solução
Adicionar ajuste de offset para words dentro de cada segmento (v2.34):
```python
for seg in result["segments"]:
    seg["start"] += speech_start
    seg["end"] += speech_start
    if seg.get("words"):
        for word in seg["words"]:
            word["start"] += speech_start  # ✅ Word OK
            word["end"] += speech_start    # ✅ Word OK
```

### Prevenção
- **Sempre ajustar segmentos E words** quando aplicar offset de tempo
- Verificar todos os lugares que ajustam timestamps de segmentos
- O padrão de ajuste de chunks (v2.33) já estava correto - usar como referência

### Arquivos Relacionados
- `mlx_vomo.py` — função `_transcribe_with_vad()`, linhas 6409-6421

---

## 2026-02-04 — LLM inventa numeros quando prompt nao fornece metricas pre-calculadas

### Problema
Na auditoria preventiva de fidelidade, o campo `observacoes_gerais` estava sendo gerado com numeros inventados. Exemplo:
- Metricas reais: `taxa_retencao: 1.081` (108.1% = expansao de 8%)
- Texto gerado: "Apesar da taxa de compressao parecer alta (43%)..."

A IA estava confundindo "taxa de compressao" com "taxa de retencao" e inventando porcentagens.

### Causa Raiz
1. O prompt pedia para a IA "calcular" a taxa de compressao baseada nos textos
2. O prompt nao fornecia as metricas ja calculadas de forma explicita
3. A IA, ao tentar estimar, gerava numeros incorretos
4. Nao havia instrucao clara sobre a diferenca entre "compressao" e "expansao"

### Solucao
1. Adicionar secao "METRICAS REAIS DO DOCUMENTO" no inicio do prompt com valores pre-calculados
2. Incluir interpretacao textual: "EXPANSAO de X%" ou "COMPRESSAO de X%"
3. Instruir explicitamente: "NAO invente ou estime outros valores. Use EXATAMENTE estes numeros"
4. Reescrever secao "ANALISE AUTOMATICA DE METRICAS" para enfatizar uso de valores fornecidos
5. Atualizar descricao do campo `observacoes_gerais` no schema JSON

### Prevencao
- **Sempre fornecer dados pre-calculados** quando o LLM precisa referencia-los no output
- **Nunca pedir para o LLM calcular** metricas que podem ser calculadas deterministicamente
- **Incluir interpretacao textual** de valores numericos para evitar confusao
- **Instruir explicitamente** sobre o que NAO fazer (nao inventar, nao estimar)
- Para valores criticos, incluir exemplos de formato correto no prompt

### Arquivos Relacionados
- `audit_fidelity_preventive.py` — linhas 38-282 (prompt), 748-777 (codigo)

---

## 2026-02-04 — Batch transcription sem tratamento de exceção perde arquivos longos

### Problema
Na transcrição em lote (batch), a Parte 1 de um arquivo de 5h22min ficou completamente vazia no resultado, enquanto a Parte 2 (15min) transcreveu normalmente.

### Causa Raiz
O código `process_batch_with_progress()` em `transcription_service.py`:
1. **Não tinha try/except** ao redor de `vomo.transcribe_file()`
2. **Não validava** se `transcription_text` estava vazio após a chamada
3. Se MLX-Whisper falhasse (timeout, memória, degradação), o texto ficava vazio
4. O código continuava normalmente, adicionando texto vazio à lista de partes

### Solução
1. Adicionar `try/except` ao redor da chamada de transcrição
2. Implementar fallback para AssemblyAI quando Whisper falhar
3. Validar que o resultado não está vazio (`len(text) < 50`)
4. Logar warnings e erros detalhados para debug

```python
try:
    transcription_text = await asyncio.to_thread(vomo.transcribe_file, ...)
except Exception as whisper_exc:
    logger.error(f"❌ Erro Whisper: {whisper_exc}")
    # Fallback para AssemblyAI
    if _fallback_aai_key:
        aai_result = await self._transcribe_assemblyai_with_progress(...)
        transcription_text = aai_result.get("text", "")
```

### Prevenção
- **Sempre validar** resultados de operações de longa duração
- **Sempre ter fallback** para operações críticas
- **Nunca assumir** que uma função externa retorna valor válido
- Para arquivos muito longos (> 3h), considerar usar AssemblyAI diretamente

### Arquivos Relacionados
- `apps/api/app/services/transcription_service.py` — linhas 4185-4231

---

## 2026-02-03 — MLX-Whisper degrada com áudios muito longos (> 3-4h)

### Problema
Transcrição de áudio de ~5.6h retornou apenas pontos (`. . . . .`) em vez de texto real. O arquivo `_RAW.txt` tinha timestamps corretos mas nenhum conteúdo de fala.

### Causa Raiz
O **MLX-Whisper silenciosamente degrada** quando processa arquivos muito longos de uma vez só. Não gera erro, apenas retorna tokens vazios/pontuação. Este é um problema conhecido com modelos Whisper em geral quando o buffer de contexto é excedido.

**Evidências:**
- Trechos individuais do mesmo arquivo transcritos perfeitamente
- Problema começa a partir de ~3-4h de áudio contínuo
- O cache de transcrição armazena o resultado degradado, perpetuando o problema

### Solução
Implementar **chunking automático** de áudios longos:
1. Detectar duração do áudio antes de transcrever
2. Se > 3h, dividir em chunks de 3h com 30s de overlap
3. Transcrever cada chunk separadamente
4. Ajustar timestamps e mesclar resultados
5. Remover duplicatas do overlap via fingerprinting de texto

### Prevenção
- Sempre verificar duração do áudio antes de processar
- Limite seguro: **3 horas por chunk** para MLX-Whisper
- Deletar cache (`*_ASR_*.json`) se transcrição falhou
- Para arquivos muito longos, considerar usar `faster-whisper` com CPU

### Arquivos Relacionados
- `mlx_vomo.py` — constantes `AUDIO_MAX_DURATION_SECONDS`, `AUDIO_CHUNK_OVERLAP_SECONDS`
- `scripts/transcribe_long_raw.py` — script standalone para reprocessar

---

## 2026-02-03 — LLM gera âncoras "fake" usando títulos em vez de citações verbatim

### Problema
Âncoras ABRE/FECHA no mapeamento de estrutura tinham 0% de cobertura — nenhuma era encontrada no texto da transcrição.

### Causa Raiz
O modelo (Vertex AI/Gemini) não seguia a instrução de copiar frases **literais** do texto. Gerava o **título do tópico** como âncora:
```
| ABRE: "O Credenciamento na Nova Lei de Licitações"  ← título, não citação
```
Quando deveria gerar:
```
| ABRE: "bom dia pessoal hoje vamos falar sobre o credenciamento"  ← frase real
```

### Solução
1. **Detectar âncoras fake**: Calcular similaridade (Jaccard) entre título e frase ABRE. Se > 60%, é fake.
2. **Fallback inteligente**: Buscar no texto real usando palavras-chave do título + frases de transição comuns.

### Prevenção
- Prompts pedindo "citação verbatim" nem sempre são seguidos por LLMs
- Sempre validar output do modelo contra o texto fonte
- Ter fallbacks para quando o modelo não segue instruções

### Arquivos Relacionados
- `mlx_vomo.py` — funções `_similaridade_palavras`, `_buscar_ancora_no_texto`

---

## 2026-02-03 — Chunk-based LLM analysis causes false positive hallucinations

### Problema
A auditoria de fidelidade reportava que "Nelson Rosenwald" era uma alucinação (conteúdo adicionado não presente no RAW), quando na verdade o nome existia no texto RAW original.

### Causa Raiz
Quando textos grandes são divididos em chunks para análise LLM:
1. RAW e formatado são divididos em chunks proporcionais (ex: chunk 1 = 0-100k chars do RAW vs 0-80k do formatado)
2. O LLM analisa cada par de chunks isoladamente
3. Se um nome aparece no chunk X do formatado mas o nome está no chunk Y do RAW (posição diferente), o LLM incorretamente reporta como alucinação
4. O LLM não tem visibilidade do documento completo, apenas do chunk atual

### Solução
Implementar filtro pós-processamento que verifica alucinações reportadas contra o texto RAW completo:
```python
def _filter_hallucination_false_positives(raw_text: str, alucinacoes: list) -> list:
    """Verifica se nomes/trechos reportados como alucinações existem no RAW completo."""
    raw_lower = raw_text.lower()
    raw_names = _extract_names_from_text(raw_text)

    for item in alucinacoes:
        trecho = item.get("trecho_formatado", "")
        trecho_names = _extract_names_from_text(trecho)

        # Se todos os nomes do trecho existem no RAW, é falso positivo
        if trecho_names and all(name in raw_names for name in trecho_names):
            continue  # Remove da lista
    return filtered_list
```

### Prevenção
1. Sempre validar claims do LLM contra o documento completo, não apenas chunks
2. Implementar overlap maior entre chunks para reduzir fragmentação de contexto
3. Considerar análise em duas passadas: chunks para detecção rápida, full-document para confirmação
4. Extrair entidades (nomes, leis, números) do documento completo antes da análise por chunks

### Arquivos Relacionados
- `audit_fidelity_preventive.py` — Adicionado `_filter_hallucination_false_positives()`

---

## 2026-02-03 — Axios com Content-Type padrão quebra upload de FormData

### Problema
Erro 422 "Unprocessable Entity" ao tentar fazer upload de arquivos via FormData. O backend FastAPI reportava "Field required" para o campo `files`.

### Causa Raiz
O cliente axios foi configurado com `Content-Type: application/json` como header padrão no construtor:
```typescript
this.axios = axios.create({
  baseURL: API_URL,
  headers: { 'Content-Type': 'application/json' },
});
```

Quando se envia FormData, o axios deveria automaticamente definir `Content-Type: multipart/form-data` com o boundary correto. Porém, o header padrão sobrescreve esse comportamento, fazendo o FormData ser enviado como JSON e corrompendo os dados.

### Solução
Definir explicitamente `Content-Type: undefined` em todas as chamadas que usam FormData:
```typescript
const response = await this.axios.post('/endpoint', formData, {
  headers: { 'Content-Type': undefined },
});
```

Isso remove o header padrão e permite que o axios/browser defina automaticamente o content-type correto com o boundary.

### Prevenção
1. Evitar definir `Content-Type` como header padrão no axios.create()
2. Sempre usar `headers: { 'Content-Type': undefined }` ao enviar FormData
3. Criar um método helper para upload de arquivos que já inclua essa configuração

### Arquivos Relacionados
- `apps/web/src/lib/api-client.ts`

---

## 2026-02-02 — Singleton sem lock em FastAPI causa race condition

### Problema
`legal_embeddings.py` usava singleton sem thread lock. Em FastAPI com uvicorn workers, multiplas requests podem chamar `get_legal_embeddings_service()` simultaneamente e criar instancias duplicadas.

### Causa Raiz
Padrão de singleton simples (`if _service is None: _service = ...`) sem proteção de concorrência. Outros singletons do projeto (embeddings.py, embedding_router.py, kanon_embeddings.py) já usavam `threading.Lock()` corretamente.

### Solução
Adicionado `threading.Lock()` com double-check locking pattern, consistente com o resto do codebase.

### Prevenção
Sempre usar double-check locking em singletons Python que rodam em FastAPI/uvicorn. Template:
```python
_lock = threading.Lock()
def get_singleton():
    global _instance
    if _instance is not None:
        return _instance
    with _lock:
        if _instance is None:
            _instance = MyClass()
    return _instance
```

### Arquivos Relacionados
- `apps/api/app/services/rag/legal_embeddings.py`

---

## 2026-02-02 — asyncio.get_event_loop() deprecado causa DeprecationWarning

### Problema
`legal_embeddings.py` e `core/embeddings.py` usavam `asyncio.get_event_loop()` que e deprecado desde Python 3.10 e emite DeprecationWarning em Python 3.12+.

### Causa Raiz
Padrão antigo para detectar se ha event loop rodando. O metodo `get_event_loop()` cria um novo loop se nao existir, o que nao e o comportamento desejado.

### Solução
Substituido por `asyncio.get_running_loop()` dentro de try/except RuntimeError. Se nao ha loop rodando, `get_running_loop()` levanta RuntimeError, e sabemos que podemos usar `asyncio.run()`.

### Prevenção
Nunca usar `asyncio.get_event_loop()`. Usar `asyncio.get_running_loop()` com try/except.

### Arquivos Relacionados
- `apps/api/app/services/rag/legal_embeddings.py`
- `apps/api/app/services/rag/core/embeddings.py`

---

## 2026-02-02 — SDK google.generativeai vs google.genai inconsistencia

### Problema
`jurisprudence_verifier.py` usava o SDK antigo `google.generativeai` (genai.configure + GenerativeModel), enquanto o resto do projeto usa `google.genai` (Client pattern).

### Causa Raiz
O SDK Gemini mudou a API entre versões. O arquivo foi criado usando exemplos do SDK antigo.

### Solução
Migrado para `from google import genai; client = genai.Client(); client.models.generate_content(model=..., contents=...)`.

### Prevenção
Sempre verificar qual SDK Gemini o projeto usa antes de criar novos arquivos. O padrão do Iudex é `google.genai` (novo SDK).

### Arquivos Relacionados
- `apps/api/app/services/jurisprudence_verifier.py`

---

## 2026-02-02 — Code Execution: 5 erros de implementação sem verificação de docs

### Problema
Implementação do code execution para 3 providers (OpenAI, Anthropic, Google) tinha múltiplos erros que só foram detectados ao verificar contra documentação oficial.

### Causa Raiz
Confiei em nomes de eventos/parâmetros "lógicos" sem verificar a API Reference oficial de cada provider.

### Solução
1. **OpenAI SDK desatualizado**: `openai==1.55.3` não tem `client.responses` (Responses API adicionada em v1.66.0). Atualizado para `>=1.66.0`
2. **OpenAI event names**: Naming convention usa underscore entre palavras compostas (`response.code_interpreter_call_code.delta`), não ponto (`response.code_interpreter_call.code.delta`)
3. **Anthropic effort**: O campo `effort` vai em `output_config` no body, NÃO dentro da tool definition. Requer beta header adicional `effort-2025-11-24`
4. **Anthropic effort model**: Só funciona com Claude Opus 4.5, não com todos os modelos
5. **Anthropic Vertex AI**: Code execution beta não é suportado no Vertex AI — precisa de fallback para client direto

### Prevenção
- SEMPRE verificar docs oficiais antes de implementar integração com API
- SEMPRE verificar versão do SDK antes de usar features novas
- Manter um test suite que valide event names/field paths contra mocks baseados nos docs

### Arquivos Relacionados
- `apps/api/requirements.txt`
- `apps/api/app/services/ai/agent_clients.py`
- `apps/api/app/services/ai/claude_agent/executor.py`

---

## 2026-02-02 — Agentes paralelos criam migrações Alembic conflitantes

### Problema
- Múltiplos agentes criaram migrações com revision IDs duplicados (`q7r8s9t0u1v2`, `r8s9t0u1v2w3`)
- Migração `d9a3f7e2c1b4` (guest_sessions) referenciava FK para `shared_spaces` que não existia naquela posição da cadeia

### Causa Raiz
- Agentes background rodando em paralelo escolheram IDs de revisão semelhantes
- Falta de coordenação: cada agente assumiu ser o HEAD da cadeia

### Solução
- Renomear migrações duplicadas com novos IDs únicos e re-encadear down_revisions
- Remover migração orphaned (`d9a3f7e2c1b4`) e criar substituta após shared_spaces existir

### Prevenção
- Nunca lançar agentes paralelos que criam migrações Alembic — fazer sequencialmente
- Verificar `alembic heads` após cada agente de migração
- Usar script para detectar forks: `grep -h "down_revision" *.py | sort | uniq -d`

### Arquivos Relacionados
- `apps/api/alembic/versions/` — toda a cadeia de migrações

---

## 2026-02-02 — Endpoints sem autenticação em produção

### Problema
- 39+ endpoints (transcription, advanced, chat threads, health reset) não exigiam autenticação
- `/auth/login-test` acessível em produção (deveria ser só dev)
- Webhooks sem validação de secret

### Causa Raiz
- Endpoints criados antes do sistema de auth estar maduro
- Falta de middleware global de auth — cada endpoint precisa adicionar `Depends(get_current_user)` manualmente

### Solução
- Adicionado `current_user: User = Depends(get_current_user)` a todos os endpoints
- Guard de ambiente em login-test
- Validação de webhook secret com `TRIBUNAIS_WEBHOOK_SECRET`

### Prevenção
- Considerar middleware global de auth (opt-out vs opt-in)
- Incluir auth check em code review checklist
- Lint rule para detectar endpoints sem Depends(get_current_user)

### Arquivos Relacionados
- `apps/api/app/api/endpoints/transcription.py`
- `apps/api/app/api/endpoints/advanced.py`
- `apps/api/app/api/endpoints/chat.py`
- `apps/api/app/api/endpoints/health.py`
- `apps/api/app/api/endpoints/webhooks.py`

---

## 2026-02-02 — Import errado em arquivo gerado por agente (marketplace.py)

### Problema
- API inteira crashava ao iniciar — nenhum endpoint respondia
- Login como visitante falhava

### Causa Raiz
- Agente background criou `marketplace.py` com `from app.api.deps import get_current_user`
- O módulo `app.api.deps` não existe no projeto — todos os outros endpoints usam `from app.core.security import get_current_user`
- Como o router é importado na inicialização, o ImportError derrubava toda a API

### Solução
- Corrigir import para `from app.core.security import get_current_user`
- Matar processo travado e reiniciar uvicorn

### Prevenção
- Agentes background devem receber contexto explícito dos imports padrão do projeto
- Validar que `python -c "import app.main"` funciona após criação de novos endpoints
- Incluir nas rules: "Sempre usar `from app.core.security import get_current_user`"

### Arquivos Relacionados
- `apps/api/app/api/endpoints/marketplace.py`
- `apps/api/app/core/security.py`

---

## 2026-02-02 — Migration Alembic não aplicada em SQLite dev

### Problema
- `POST /workflows` retornava 500 Internal Server Error
- `sqlite3.OperationalError: table workflows has no column named schedule_cron`

### Causa Raiz
- A tabela `workflows` já existia no SQLite dev (criada antes do Gap 1)
- Gap 1 adicionou campos de scheduling ao modelo mas a migration Alembic não foi executada
- SQLite não tem ALTER TABLE ADD COLUMN automático via Alembic em tabelas existentes

### Solução
- Executar ALTER TABLE manualmente para adicionar as 5 colunas faltantes em `workflows` e 1 em `workflow_runs`

### Prevenção
- Após criar migrations, sempre executar `alembic upgrade head` ou verificar schema com SELECT
- Em dev com SQLite, considerar `alembic stamp head` + recreate quando schema diverge

### Arquivos Relacionados
- `apps/api/app/models/workflow.py`
- `alembic/versions/h8i9j0k1l2m3_add_workflows_tables.py`

---

## 2026-02-01 — Gemini ThinkingConfig: setattr vs constructor + Vertex limitations

### Problema
- Gemini Flash retornava 400 "thinking_level is not supported by this model" via Vertex AI
- Respostas offline para todas as mensagens com thinking habilitado

### Causa Raiz
1. **setattr bypassa Pydantic**: `setattr(thinking_config, "thinking_level", "low")` armazena string raw sem converter para `ThinkingLevel` enum. O Pydantic serializa incorretamente.
2. **Case sensitivity**: SDK espera `"LOW"` (uppercase), código passava `"low"` (lowercase)
3. **Vertex não suporta thinking_level**: Mesmo com enum correto, `gemini-2.5-flash` via Vertex AI não aceita o campo `thinking_level`. Só aceita `include_thoughts: true`.

### Solução
1. Usar construtor: `ThinkingConfig(include_thoughts=True, thinking_level="LOW")` — Pydantic valida e converte
2. Normalizar para UPPERCASE na `_normalize_gemini_thinking()`
3. Para LOW/MINIMAL: usar apenas `ThinkingConfig(include_thoughts=True)` sem `thinking_level`
4. Para MEDIUM/HIGH: usar `ThinkingConfig(include_thoughts=True, thinking_level=...)` com fallback

### Prevenção
- Nunca usar `setattr` em objetos Pydantic — usar construtor ou `model_copy(update={...})`
- Testar integração real com Vertex AI, não só instanciação local
- Manter fallback para 400 errors em streaming (erro aparece na iteração, não na criação)

### Arquivos Relacionados
- `apps/api/app/services/ai/agent_clients.py` (linhas 2209-2240)

---

## 2026-02-01 — Bug de indentação no fallback do Gemini + credenciais

### Problema
- Bug de indentação no endpoint `send_message` (não-streaming): `ai_content = None` fora do bloco `except`, executando incondicionalmente
- `GEMINI_API_KEY` no `.env` era um token OAuth inválido (formato `AQ.Ab8R...`)
- `GOOGLE_API_KEY` com quota zero no free tier (billing desabilitado em todas as contas)

### Causa Raiz
- Indentação errada em `chats.py:1703` fazia o failsafe rodar mesmo em sucesso
- O Vertex AI funciona corretamente via service account (`GOOGLE_APPLICATION_CREDENTIALS`), mas o fallback para API direta falhava
- Diagnóstico confuso inicialmente porque `source .env` no bash não exporta `GOOGLE_APPLICATION_CREDENTIALS` como `python-dotenv` faz

### Solução
- Corrigida indentação do bloco failsafe para dentro do `except`
- Substituída `GEMINI_API_KEY` por key válida (projeto `gen-lang-client-0781186103`)

### Prevenção
- Sempre testar credenciais usando `python-dotenv` (como a API realmente roda), não `source .env`
- Validar formato de API keys: Gemini keys começam com `AIza...`

### Arquivos Relacionados
- `apps/api/app/api/endpoints/chats.py`
- `apps/api/.env`

---

## 2026-01-27 — OpenAI Reasoning Models nao suportam temperature

### Problema
- Chamadas ao OpenAI `o4-mini-deep-research` falhavam com 400: "Unsupported parameter: 'temperature' is not supported with this model"

### Causa Raiz
- `deep_research_service.py` passava `temperature=0.2` hardcoded em todas as chamadas OpenAI
- Modelos reasoning (o1, o3, o4) nao aceitam temperature

### Solucao
- Detectar modelo reasoning por prefixo (`o1`, `o3`, `o4`)
- Omitir `temperature` para esses modelos em ambos os paths (sync e streaming)

### Prevencao
- Sempre verificar compatibilidade de parametros por familia de modelo
- OpenAI reasoning models: sem temperature, sem top_p, effort minimo "medium"

### Arquivos Relacionados
- `apps/api/app/services/ai/deep_research_service.py` (linhas ~487, ~950)
- `apps/api/app/services/ai/deep_research_hard_service.py` (effort "low" -> "medium" para OpenAI)

---

## 2026-01-29 — Falsos positivos de “Tema XXXX” por erro de ASR (Whisper)

### Problema
- Auditoria/Qualidade geravam alerts do tipo `missing_julgado` para “Tema 234”/“Tema 1933”, que não faziam sentido (ou eram variantes erradas do ASR).
- Em alguns casos, a extração de referências não reconhecia `Tema 1.234` (com separador) e produzia diferenças artificiais RAW vs formatado.

### Causa Raiz
- O texto RAW pode conter números “Tema” inconsistentes por erro de ASR (ex.: perda do dígito inicial `234` vs `1234`, ou erro em um dígito `1933` vs `1033`).
- A comparação de referências era sensível à pontuação (`1.234` vs `1234`) e/ou não filtrava variações típicas de ASR.

### Solução
- Normalização de “Tema” na extração de referências (ex.: `Tema 1.234` → `tema 1234`) para comparar por dígitos.
- Filtro conservador em `missing_julgados` para não levantar alertas quando há evidência interna no formatado:
  - `234` é tratado como variante de `1234` se `1234` já aparece.
  - Um `tema` 4-dígitos é ignorado como “missing” quando existe outro tema 4-dígitos muito próximo (Hamming ≤ 1) no formatado.
- Sanitização final do markdown para remover/normalizar variantes erradas quando a forma canônica já está no documento.
- Normalização opcional no texto RAW (ASR) + overrides configuráveis.

### Prevenção
- Preferir normalização por dígitos (não por string literal) ao comparar referências numéricas.
- Para confusões conhecidas, usar overrides via:
  - `VOMO_ASR_NORMALIZE_TEMAS` (default: `true`)
  - `VOMO_ASR_TEMA_OVERRIDES` (ex.: `"1933=1033,234=1234"`)

### Arquivos Relacionados
- `mlx_vomo.py`
- `auto_fix_apostilas.py`
- `apps/api/app/services/quality_service.py`

---

## Template de Entrada

```markdown
## [DATA] — Título Curto do Problema

### Problema
- Descrição do erro/comportamento inesperado

### Causa Raiz
- O que estava causando o problema

### Solução
- Como foi resolvido

### Prevenção
- Como evitar no futuro

### Arquivos Relacionados
- `caminho/arquivo.ts`
```

---

## 2026-01-26 — load_dotenv timing bug desabilitava diarização

### Problema
- Diarização de áudio (pyannote) nunca executava apesar de estar instalada
- `HF_TOKEN` sempre era `None` mesmo com valor no `.env`

### Causa Raiz
- Variável `HF_TOKEN` era lida no nível de módulo (linha 195): `HF_TOKEN = os.getenv("HUGGING_FACE_TOKEN")`
- `load_dotenv()` só era chamado depois, dentro do `__init__` de uma classe (linha 4137)
- Quando o módulo é importado, o código no nível de módulo executa primeiro → `HF_TOKEN = None`
- Quando `__init__` chama `load_dotenv()`, já é tarde — a variável global já foi definida

### Solução
- Mover `load_dotenv()` para o início do módulo, antes de qualquer `os.getenv()`

### Prevenção
- **Regra**: Sempre chamar `load_dotenv()` no início absoluto do módulo, antes de qualquer `os.getenv()`
- Se uma variável de ambiente é usada no nível de módulo, garantir que `.env` já foi carregado
- Ou usar lazy loading: `HF_TOKEN = None` no módulo e `HF_TOKEN = HF_TOKEN or os.getenv(...)` quando precisar

### Arquivos Relacionados
- `mlx_vomo.py`

---

## 2026-01-20 — TipTap SSR Warning

### Problema
- Console alertava sobre SSR/hidratação no editor TipTap

### Causa Raiz
- `immediatelyRender` não estava definido no useEditor

### Solução
- Definir `immediatelyRender: false` no useEditor

### Prevenção
- Sempre configurar immediatelyRender em editores TipTap com Next.js

### Arquivos Relacionados
- `apps/web/src/components/editor/document-editor.tsx`

---

## 2026-01-20 — Next Image Sizes Warning

### Problema
- Logos com next/image em modo fill avisavam sobre ausência de sizes

### Causa Raiz
- Propriedade `sizes` obrigatória quando usando `fill`

### Solução
- Adicionar `sizes="16px"` (ou valor apropriado) nas imagens

### Prevenção
- Sempre definir sizes ao usar fill em next/image

### Arquivos Relacionados
- `apps/web/src/components/chat/model-selector.tsx`

---

## 2026-01-20 — Gemini Streaming Thoughts

### Problema
- Painel "Processo de raciocínio" não recebia streaming no Gemini Flash

### Causa Raiz
- `thinking_mode` precisava ser "high" para streaming de thoughts

### Solução
- Forçar `thinking_mode=high` para modelos Flash com reasoning_level médio/alto

### Prevenção
- Verificar configuração de thinking_mode ao integrar novos modelos

### Arquivos Relacionados
- `apps/api/app/api/endpoints/chats.py`
- `apps/api/app/services/chat_service.py`

---

## 2026-01-24 — TTL Cleanup Nunca Funcionou (Campo Errado)

### Problema
- TTL cleanup do RAG nunca deletava documentos antigos
- OpenSearch e Qdrant acumulavam dados indefinidamente

### Causa Raiz
- `ttl_cleanup.py` buscava campos `ingested_at`, `created_at`, `timestamp`
- OpenSearch e Qdrant usam `uploaded_at` como campo de timestamp na ingestão
- Query com `should` + `minimum_should_match: 1` retornava 0 resultados sempre

### Solução
- Alterar queries para usar `uploaded_at`:
  - OpenSearch: `{"range": {"uploaded_at": {"lt": cutoff_iso}}}`
  - Qdrant: `timestamp_fields = ["uploaded_at"]`

### Prevenção
- Ao criar jobs de cleanup/manutenção, verificar os campos reais gravados na ingestão
- Criar testes que validem os nomes dos campos usados nas queries
- Manter convenção única de timestamp (`uploaded_at`) em todo o sistema RAG

### Arquivos Relacionados
- `apps/api/app/services/rag/utils/ttl_cleanup.py` (cleanup)
- `apps/api/app/services/rag/storage/opensearch_service.py` (ingestão OS)
- `apps/api/app/services/rag/storage/qdrant_service.py` (ingestão Qdrant)

---

<!-- Novas entradas acima desta linha -->
