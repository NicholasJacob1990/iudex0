# LESSONS_LEARNED.md — Lições Aprendidas

> Documente aqui erros, bugs sutis e soluções encontradas.
> Este arquivo serve como base de conhecimento para evitar repetir erros.

---

## 2026-02-14 — whisperx 3.8.0 requer pyannote-audio>=4.0.0

### Problema
Docker build falhou com `ResolutionImpossible`: conflito entre `pyannote.audio>=3.1.0,<4.0.0` (nosso pin) e `whisperx 3.8.0` que requer `pyannote-audio>=4.0.0`.

### Causa Raiz
Ao escrever o `requirements.txt`, usamos o pin `pyannote.audio>=3.1.0,<4.0.0` baseado na versão que conhecíamos, mas o whisperx (instalado via git) já tinha atualizado para depender do pyannote 4.x.

### Solução
Remover o pin explícito do pyannote — deixar o whisperx gerenciar como dependência transitiva:
```
whisperx @ git+https://github.com/m-bain/whisperX.git@main
torch>=2.1.0
torchaudio>=2.1.0
```

### Prevenção
- Sempre verificar dependências transitivas ao pinar versões
- Rodar `pip install --dry-run` ou `pip check` antes de commitar requirements

### Arquivos Relacionados
- `apps/runpod-worker/requirements.txt`

---

## 2026-02-12 — RunPod worker retorna output=None quando payload tem campos extras

### Problema
RunPod jobs completavam em ~20-44ms com `output=None`. O Iudex reportava: "RunPod completou sem output".

### Causa Raiz
O `submit_job()` enviava 7 aliases de URL (`audio`, `audio_url`, `audio_file`, `input`, `url`, `file`, `audio_path`) via `_with_audio_aliases()` + campo `"transcription": "plain_text"`. O worker (faster-whisper) não processava o áudio porque os campos extras confundiam o handler, que completava sem produzir output.

### Solução
Simplificar payload para apenas os campos que o worker espera:
```python
input_data = {"audio": audio_url.strip(), "model": "turbo", "language": language, "word_timestamps": True, "enable_vad": True}
```

### Prevenção
- Testar payload manualmente com `curl` antes de integrar no código
- Executar teste de ponta a ponta com cada mudança no payload
- `executionTime` < 100ms em job "COMPLETED" = worker não processou nada (red flag)

### Arquivos Relacionados
- `apps/api/app/services/runpod_transcription.py`

---

## 2026-02-12 — HMAC vs hashlib.sha256 para tokens de áudio

### Problema
Tokens gerados manualmente com `hashlib.sha256()` retornavam 403 no endpoint `serve_audio_for_runpod`.

### Causa Raiz
O código usa `hmac.new(secret, msg, hashlib.sha256)` (HMAC-SHA256), não `hashlib.sha256(msg)` puro. Além disso, o `secret` vem de `settings.SECRET_KEY` (Pydantic Settings = `dev-secret-key-123`), não do fallback `os.getenv("SECRET_KEY", "dev-secret-key")`.

### Solução
Usar a mesma função HMAC com o mesmo secret:
```python
hmac.new(settings.SECRET_KEY.encode(), f"{job_id}:{ts}".encode(), hashlib.sha256).hexdigest()[:32]
```

### Prevenção
- Sempre verificar qual função de hash o código realmente usa (HMAC ≠ hash puro)
- Verificar de onde o secret é lido (Pydantic settings vs os.getenv têm defaults diferentes)

### Arquivos Relacionados
- `apps/api/app/api/endpoints/transcription.py` (linhas 3071-3088)

---

## 2026-02-12 — uvicorn --reload mata jobs de transcrição em andamento

### Problema
Editar `transcription_service.py` enquanto jobs estavam rodando causou reload automático do uvicorn. Todas as threads de processamento foram mortas instantaneamente, deixando jobs "travados" no registry (status=running mas sem progresso).

### Causa Raiz
`uvicorn --reload` monitora mudanças em `.py` e reinicia o processo. Threads de transcrição (CPU-bound + async I/O) são destruídas sem cleanup.

### Solução
Cancelar jobs zombies manualmente e resubmeter. Futuramente, não editar arquivos do backend enquanto há jobs ativos.

### Prevenção
- **NUNCA editar arquivos do backend com jobs em andamento** — o auto-reload destrói threads
- Verificar `GET /api/transcription/jobs` antes de editar `transcription_service.py` ou `transcription.py`
- Considerar usar Celery workers separados para transcrição (processo isolado do uvicorn)

### Arquivos Relacionados
- `apps/api/app/services/transcription_service.py`
- `apps/api/app/api/endpoints/transcription.py`

---

## 2026-02-12 — Cache AAI não funciona quando arquivo tem hash diferente

### Problema
Ao submeter `17_Tributario_Eduardo_Sobral.mp3` (215MB) via UI, o sistema re-enviava para AssemblyAI em vez de usar a transcrição já existente.

### Causa Raiz
O cache AAI é indexado por SHA-256 do arquivo. O arquivo `temp_cloud_fabc5f0d.mp3` (122MB) tinha hash diferente do arquivo original PGM_RJ (215MB) — mesma aula, encoding diferente. Cache entries existiam apenas para o hash do temp_cloud.

### Solução
Criar cache entries para os hashes SHA-256 dos arquivos reais (MP3 + MP4) com o `transcript_id` da transcrição AAI correspondente e o `config_hash` correto (APOSTILA = `2e2fcadd`).

### Prevenção
- Ao importar transcrições externas, criar cache entries para TODOS os formatos conhecidos do áudio
- Config hash depende do modo: APOSTILA=`2e2fcadd`, FIDELIDADE=`b7b040f5`, default=`2068ccbf`

### Arquivos Relacionados
- `apps/api/app/services/transcription_service.py` (cache check ~linha 6559)
- `apps/api/storage/aai_transcripts/`

---

## 2026-02-11 — MagicMock + hasattr causa bypass inesperado de fallback chains

### Problema
`MagicMock()` faz `hasattr(client, "query_points")` retornar True mesmo quando o mock deveria simular um client sem esse método. Isso fez os testes de QdrantService usar o path de `query_points` em vez de `search`, retornando MagicMock vazio.

### Causa Raiz
MagicMock gera atributos sob demanda. O service faz `if hasattr(self.client, "query_points"): ...` e entra no branch errado.

### Solução
Criar bridge no mock que converte `query_points` → `search`, passando kwargs adaptados e sempre chamando o mock original de `search`.

### Prevenção
- Ao mockar clients com fallback chains baseadas em `hasattr`, definir `spec=` no MagicMock ou criar bridge explícita
- Verificar `qdrant_sparse_enabled` explicitamente como `False` no mock de config

---

## 2026-02-11 — `import os` em bloco finally cria scoping local que sombreia global

### Problema
`import os` dentro de `finally:` faz Python tratar `os` como variável local em todo o scope do bloco, causando `UnboundLocalError` para `os.getenv()` em linhas anteriores.

### Solução
Remover `import os` redundante quando já existe no topo do arquivo.

### Prevenção
Nunca usar `import` dentro de blocos `try/except/finally` se o módulo já é importado no topo.

---

## 2026-02-11 — asyncio.to_thread muda assinatura de chamada (positional vs keyword)

### Problema
`asyncio.to_thread(self._get_vomo, model_selection, thinking_level)` passa args posicionais, mas lambdas de monkeypatch `lambda **kwargs: fake` não aceitam posicionais.

### Solução
Usar `lambda *args, **kwargs: fake` para aceitar qualquer forma de chamada.

### Prevenção
Ao monkeypatchar métodos que são chamados via `asyncio.to_thread`, sempre aceitar `*args, **kwargs`.

---

## 2026-02-10 — Pydantic extra="ignore" silenciosamente descarta campos necessários para round-trip

### Problema
- Issues de auditoria estrutural (duplicate_paragraph, heading_semantic_mismatch, etc.) eram detectadas corretamente, mas ao tentar aplicar as correções, nada acontecia — 0 fixes applied.

### Causa Raiz
- `UnifiedAuditIssue` (Pydantic BaseModel) descartava silenciosamente campos extras (`heading_line`, `old_title`, `title`, `line_index`, `table_heading`, etc.) porque Pydantic por padrão usa `extra="ignore"`
- Esses campos são necessários pelo `apply_approved_fixes()` para localizar e aplicar cada fix
- O round-trip frontend→backend→frontend→backend perdia dados a cada serialização
- Adicionalmente, o campo `action` era preenchido com `action_summary` (texto descritivo), mas o legacy fallback esperava `"INSERT"` ou `"REPLACE"` como verbo

### Solução
- `model_config = ConfigDict(extra="allow")` no modelo Pydantic
- Spread dos campos extras originais (`**extra_fields`) na criação dos issues
- Derivação de `action=INSERT/REPLACE` a partir do conteúdo do `patch`, não do `action_summary`

### Prevenção
- Sempre usar `extra="allow"` em modelos Pydantic que precisam fazer round-trip (frontend↔backend)
- Testar o ciclo completo: criar issue → serializar → deserializar → aplicar
- Adicionar logging de "skipped fixes" para tornar falhas visíveis

### Arquivos Relacionados
- `apps/api/app/schemas/audit_unified.py`
- `apps/api/app/api/endpoints/audit_unified.py`
- `apps/api/app/services/quality_service.py` (apply_unified_hil_fixes)

---

## 2026-02-10 — Comparação CLI vs UI usou modos diferentes (APOSTILA vs FIDELIDADE)

### Problema
- Uma sessão anterior comparou a transcrição da CLI com a da UI e concluiu que a CLI era "melhor" (mais conteúdo, tabelas maiores, mais bullet points)
- O diagnóstico incorreto foi que `legal_prompts.py` e `lib/prompts.ts` tinham prompts desatualizados em relação ao `mlx_vomo.py`

### Causa Raiz
- **Comparação de modos diferentes**: A CLI rodou em modo **APOSTILA** (arquivo de saída: `_APOSTILA.md`), enquanto a UI rodou em modo **FIDELIDADE** — são filosofias de formatação completamente diferentes
  - APOSTILA: 3ª pessoa/impessoal, formatação generosa, tabelas de 5 colunas obrigatórias, bullet points permitidos
  - FIDELIDADE: 1ª pessoa preservada, formatação moderada, retenção 95-115% do tamanho original
- **Fix aplicado no lugar errado**: `legal_prompts.py` NÃO é usado no pipeline de transcrição — grep confirmou zero referências em `transcription_service.py`. Ambos CLI e UI usam os prompts de `mlx_vomo.py` via `VomoMLX._build_system_prompt()`
- `lib/prompts.ts` era dead code (não importado por nenhum componente) — já deletado

### Solução
- Nenhuma correção de prompt era necessária — os prompts de transcrição já eram idênticos entre CLI e UI (ambos em `mlx_vomo.py`)
- Dead code removido: `apps/web/src/lib/prompts.ts` deletado, import morto de `LegalPrompts` em `orchestrator.py` removido
- Esta entrada corrigida com o diagnóstico real

### Prevenção
- **Ao comparar outputs, verificar se o MODO é o mesmo** — o nome do arquivo de saída indica o modo (`_APOSTILA.md`, `_FIDELIDADE.md`)
- `legal_prompts.py` é usado apenas por `document_generator.py` e `langgraph_workflow.py` (geração de documentos jurídicos), NÃO por transcrição
- **Single source of truth**: Todos os prompts de transcrição vivem em `mlx_vomo.py` na classe `VomoMLX`

### Arquivos Relacionados
- `mlx_vomo.py` — fonte única de prompts de transcrição (CLI e UI)
- `apps/api/app/services/transcription_service.py` — importa `VomoMLX` de `mlx_vomo.py`
- `apps/api/app/services/legal_prompts.py` — usado APENAS por document_generator (irrelevante para transcrição)
- `apps/web/src/lib/prompts.ts` — **deletado** (era dead code)

---

## 2026-02-10 — Validadores ausentes para alucinações e contexto no false_positive_prevention

### Problema
- `validate_hil_issue()` não tinha tratamento para tipos `alucinacao` e `referencia_ambigua`
- Ambos caíam no `else` genérico com confidence 0.70 automática — sem verificação contra RAW
- Resultado: alucinações e problemas de contexto eram aceitos sem validação

### Causa Raiz
- Quando novos tipos de issues foram adicionados ao pipeline de auditoria, os validadores correspondentes não foram criados
- O fallback genérico mascarava o problema (confidence 0.70 = MEDIUM, passava o threshold de 0.50)

### Solução
- `_validate_hallucination()`: Extrai fragmentos factuais (nomes, leis, datas) e verifica contra RAW. Se 70%+ dos fragmentos existem no RAW → falso positivo
- `_validate_context_issue()`: Verifica se ambiguidade existe no RAW (então não é erro de formatação), detecta marcadores de ambiguidade, valida correção sugerida
- `_extract_factual_fragments()`: Helper para extrair nomes próprios, referências legais, datas e números

### Prevenção
- Quando adicionar um novo tipo de issue ao pipeline de auditoria, SEMPRE criar o validador correspondente em `false_positive_prevention.py`
- O fallback genérico deve logar um warning, não silenciosamente aceitar

### Arquivos Relacionados
- `apps/api/app/services/false_positive_prevention.py`
- `apps/api/app/services/quality_service.py`

---

## 2026-02-10 — Stale closure em React: setReportPaths + fetchPreventiveAudit

### Problema
- `handleRecomputePreventiveAudit` chamava `setReportPaths(newPaths)` e depois `await fetchPreventiveAudit(true)` no mesmo handler
- `fetchPreventiveAudit` capturava `reportPaths` via closure, mas o state update ainda não havia sido flushed pelo React
- Resultado: fetch usava paths antigos → exit early sem carregar dados

### Causa Raiz
- `useState` setter é async — o novo valor só é visível no próximo render cycle
- `useCallback` captura o valor de `reportPaths` no momento da criação do closure
- Chamar uma função que depende de state imediatamente após settar esse state é uma race condition clássica em React

### Solução
- Bypass o `fetchPreventiveAudit` e fazer o download direto usando `downloadTranscriptionReport(jobId, key)`
- O backend resolve o path pelo key, não depende do state local
- Fallback com `setTimeout(100ms)` + `fetchPreventiveAudit(true)` se download direto falhar
- `finally { setPreventiveAuditLoading(false) }` garante que loading sempre é limpo

### Prevenção
- Quando um handler precisa usar dados que acabou de setar via setState, extrair os dados da fonte original (response da API) em vez de depender do state
- Ou usar um ref (`useRef`) para valores que precisam ser lidos imediatamente após serem setados
- SEMPRE usar `finally` para resetar flags de loading em handlers async

### Arquivos Relacionados
- `apps/web/src/app/(dashboard)/transcription/page.tsx` — `handleRecomputePreventiveAudit`, `fetchPreventiveAudit`

---

## 2026-02-10 — Botão oculto + Conversão incompleta de issues Quality → HIL

### Problema
- Usuário não conseguia converter omissões/distorções da aba Qualidade em issues para correção
- Botão "Validação Completa" estava escondido por `!isDashboardVariant`
- API só convertia omissões + distorções + estruturais — alucinações e contexto eram ignorados

### Causa Raiz
- `{!isDashboardVariant && ( <toolbar> )}` → funcionalidade crítica excluída do variant dashboard
- `ConvertToHilRequest` e `convert_to_hil_issues` não aceitavam `hallucinations` e `context_issues`
- Frontend não passava esses campos para a API

### Solução
- Botão "Detectar Problemas" adicionado na toolbar do dashboard
- Em dashboard mode, issues vão direto para aba Correções via `onConvertContentAlerts`
- Backend expandido: `convert_to_hil_issues` agora converte alucinações (type="alucinacao") e contexto (type=ctx_type)
- Frontend passa todos os campos do relatório para a API

### Prevenção
- Ao adicionar ações em componentes com múltiplos variants, verificar TODOS os variants
- Quando adicionar novos tipos de problemas ao relatório de qualidade, lembrar de adicioná-los também ao pipeline de conversão HIL

### Arquivos Relacionados
- `apps/web/src/components/dashboard/quality-panel.tsx`
- `apps/web/src/lib/api-client.ts`
- `apps/api/app/api/endpoints/quality_control.py`
- `apps/api/app/services/quality_service.py`

---

## 2026-02-10 — _build_compat_report omitia alucinações e contexto → score inexplicavelmente baixo

### Problema
- Após aplicar correções HIL num job, a nota de fidelidade caiu de 9.2 para 3.05
- O relatório de validação mostrava 0 omissões, 0 distorções, observações positivas — mas nota 3.05
- Usuário não conseguia entender por que a nota baixou

### Causa Raiz
- `_build_compat_report` em `audit_fidelity_preventive.py` convertia o resultado do LLM para formato compatível com o endpoint `/quality/validate`
- A função omitia 3 campos críticos: `alucinacoes`, `problemas_contexto` e `recomendacao_hil.pausar_para_revisao`
- O score raw do LLM (3.05) só é promovido para 9.2 quando `should_pass=True`
- `should_pass` requer `no_critical` (sem omissões, distorções OU alucinações) E `not pausar`
- Sem expor esses campos, o frontend via o score baixo sem explicação

### Solução
1. `_build_compat_report` agora inclui `alucinacoes`, `problemas_contexto`, `pausar_para_revisao`, `motivo_pausa`
2. `quality_service.py` → `validate_document` retorna `hallucinations`, `context_issues`, `pause_reason`
3. `quality_control.py` → `ValidateResponse` Pydantic model com novos campos
4. `quality-panel.tsx` → Accordion sections para alucinações (roxo) e problemas de contexto (azul), banner de pausa (vermelho)

### Prevenção
- Ao criar funções de compatibilidade/adapter, SEMPRE verificar que TODOS os campos do modelo original são mapeados
- Testar com cenários onde alucinações existem mas omissões/distorções não
- O score de fidelidade sem os campos que o compõem é inútil — sempre expor os componentes

### Arquivos Relacionados
- `audit_fidelity_preventive.py` — `_build_compat_report`
- `apps/api/app/services/quality_service.py` — `validate_document`
- `apps/api/app/api/endpoints/quality_control.py` — `ValidateResponse`
- `apps/web/src/components/dashboard/quality-panel.tsx`

---

## 2026-02-10 — Alembic: 3 migrações com ID duplicado x6y7z8a9b0c1

### Problema
- `alembic upgrade head` falhava com "table already exists" e "Multiple head revisions"
- 3 arquivos de migração tinham o mesmo revision ID: `x6y7z8a9b0c1`
  - `add_dynamic_columns_cell_extractions`
  - `add_extraction_jobs_tables`
  - `add_table_chat_messages`

### Causa Raiz
- Quando múltiplas migrações são geradas no mesmo dia sem rodar `upgrade` entre elas, os IDs manuais podem colidir se seguem um padrão sequencial sem verificação de unicidade

### Solução
1. Renomeei os duplicados para IDs únicos: `c1` → `c2` → `c3`
2. Encadeei: `w5...b0` → `c1` (dynamic_columns) → `c2` (extraction_jobs) → `c3` (table_chat) → `y7...d2` (graph_risk)
3. Atualizei tanto os headers (docstring) quanto as variáveis `revision`/`down_revision`
4. Renomeei os arquivos para refletir os novos IDs

### Prevenção
- Sempre usar `alembic revision --autogenerate` em vez de IDs manuais
- Rodar `alembic heads` antes de criar nova migração para detectar branches
- Nunca copiar IDs de migrations existentes

### Arquivos Relacionados
- `apps/api/alembic/versions/x6y7z8a9b0c2_add_extraction_jobs_tables.py`
- `apps/api/alembic/versions/x6y7z8a9b0c3_add_table_chat_messages.py`
- `apps/api/alembic/versions/y7z8a9b0c1d2_add_graph_risk_reports.py`

---

## 2026-02-09 — Operações GDS Fase 3 não incluídas na lista de dispatch

### Problema
- `test_dispatcher_calls_adamic_adar` falhava: handler nunca era chamado
- Operações `adamic_adar`, `node2vec`, `all_pairs_shortest_path`, `harmonic_centrality` tinham handlers implementados mas não executavam

### Causa Raiz
- `gds_operations` list em `graph_ask_service.py` (linha ~817) incluía operações das Fases 1 e 2, mas não da Fase 3
- Sem estar na lista, o fluxo não entrava no bloco `if operation in gds_operations:` e não fazia dispatch para os handlers

### Solução
- Adicionadas as 4 operações da Fase 3 à lista `gds_operations`

### Prevenção
- Ao adicionar novos handlers GDS, **sempre** incluir na lista `gds_operations` além de:
  1. Enum `GraphOperation`
  2. Template ou handler
  3. Bloco `elif` de dispatch
  4. **`gds_operations` list** ← este foi esquecido

### Arquivos Relacionados
- `apps/api/app/services/graph_ask_service.py`
- `apps/api/tests/test_graph_gds_phase3.py`

---

## 2026-02-08 — Extração agressiva sem evidence obrigatória prejudica auditabilidade legal

### Problema
Ao relaxar o prompt de extração KG para "Prefira EXTRAIR a omitir" com evidence opcional, o grafo ficaria mais denso mas sem rastreabilidade — impossível auditar por que uma relação existe.

### Causa Raiz
O v2 standalone (ingest_v2.py) usava extração agressiva por design (otimizar densidade do grafo). Para um RAG jurídico com transparência como requisito, essa filosofia é inadequada — o usuário precisa ver a justificativa textual de cada relação.

### Solução
Manter extração strict em ambos os sistemas (Iudex e v2):
- REGRA 0: "Extraia SOMENTE relações EXPLÍCITAS" + "Se não puder citar evidence, NÃO crie a relação"
- REGRA 0.1: evidence obrigatória (max 160 chars)
- REGRA 9: "Na dúvida, OMITA a relação"
- Compensar grafo esparso com: regex layer automático, PERTENCE_A para cada Artigo, chunk overlap

### Prevenção
- Antes de relaxar regras de extração, perguntar: "o usuário precisa auditar cada relação?"
- Se sim → strict. Se não (ex: exploração, recomendação) → agressiva pode funcionar.

### Arquivos Relacionados
- `apps/api/app/services/rag/core/kg_builder/legal_graphrag_prompt.py`
- `/Users/nicholasjacob/Documents/neo4j-ingestor/ingest_v2.py`

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
