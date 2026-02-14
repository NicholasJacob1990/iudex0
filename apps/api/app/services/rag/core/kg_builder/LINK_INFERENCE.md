# Sistema de Inferência Automática de Links

Sistema em **3 fases** para descoberta automática de relacionamentos no grafo de conhecimento legal.

---

## 🎯 Visão Geral

O sistema descobre relações **implícitas** entre entidades do grafo usando:

1. **Fase 1 — Inferência Estrutural** (determinística, sem custo)
   - Fechamento transitivo (A→B→C implica A→C)
   - Co-citação (decisões que interpretam mesmos artigos)
   - Herança hierárquica (inciso herda remissões do artigo-pai)
   - Simetria (decisões que aplicam mesma súmula)
   - Clustering de jurisprudência (temas repetitivos)

2. **Fase 2 — Similaridade por Embeddings** (usa embeddings existentes, sem custo extra)
   - Link prediction via cosine similarity
   - Descobre decisões/súmulas/doutrinas semanticamente similares

3. **Fase 3 — Validação via LLM** (custo moderado, alta precisão)
   - LLM valida relações sugeridas pelas fases anteriores
   - Propõe tipos específicos (CITA, CONFIRMA, SUPERA, DISTINGUE)

---

## ⚙️ Configuração via Env Vars

### **Fase 1 — Estrutural**

```bash
# Habilitar inferência estrutural
KG_BUILDER_INFER_LINKS_STRUCTURAL=true

# Default: false (desabilitado)
```

**Regras executadas**:
- ✅ Fechamento transitivo para `REMETE_A` (depth 2)
- ✅ Fechamento transitivo para `CITA` (precedentes indiretos)
- ✅ Co-citação implícita (min 3 artigos compartilhados)
- ✅ Herança de artigos-pai (via `SUBDISPOSITIVO_DE`)
- ✅ Simetria via súmulas (decisões que aplicam mesma súmula)
- ✅ Clustering de jurisprudência (decisões sobre mesmo tema)

**Custo**: Zero (apenas Cypher)
**Segurança**: Todas as arestas têm `derived=true` e `confidence < 1.0`

---

### **Fase 2 — Embeddings**

```bash
# Habilitar inferência por embeddings
KG_BUILDER_INFER_LINKS_EMBEDDING=true

# Thresholds de similaridade (0-1)
KG_BUILDER_EMBEDDING_THRESHOLD_DECISAO=0.85     # Default: 0.85
KG_BUILDER_EMBEDDING_THRESHOLD_SUMULA=0.88      # Default: 0.88 (mais estrito)
KG_BUILDER_EMBEDDING_THRESHOLD_DOUTRINA=0.82    # Default: 0.82

# Default: false (desabilitado)
```

**Algoritmo**:
1. Busca nós com embeddings (`d.embedding IS NOT NULL`)
2. Calcula matriz de similaridade cosseno (batch)
3. Identifica pares com similaridade >= threshold
4. Cria links apenas se **não existir** relação prévia

**Tipos de link criados**:
- `Decisao -CITA-> Decisao`
- `Sumula -COMPLEMENTA-> Sumula`
- `Doutrina -CITA-> Doutrina`

**Custo**: Zero (usa embeddings já computados)
**Limitações**: Max 2000 Decisões, 1000 Súmulas, 1000 Doutrinas por execução

### **Melhoria: Adaptive Thresholds (Recomendado)**

```bash
# Habilitar thresholds adaptativos (calcula via percentis)
KG_BUILDER_USE_ADAPTIVE_THRESHOLDS=true          # Default: true
```

**Problema com thresholds fixos**:
- `Artigo×Artigo` tem alta baseline similarity (vocabulário compartilhado: "lei", "artigo", etc.)
- Pares cross-layer (`Decisao×Artigo`) têm baixa baseline
- Um threshold único (0.85) gera muitos falsos positivos em Artigo×Artigo e falsos negativos em cross-layer

**Solução: Thresholds adaptativos via percentis**:
1. Amostra 200 entidades de cada tipo
2. Calcula matriz de similaridade (amostra × amostra)
3. Determina threshold como percentil configurado:
   - `p99 = top 1%` (conservador)
   - `p99.7 = top 0.3%` (muito conservador)

**Configuração por par** (em `link_predictor.py`):
```python
TYPE_PAIR_CONFIG = {
    ("Decisao", "Decisao"): {"percentile": 99.0, "min_topk": 3},
    ("Sumula", "Sumula"): {"percentile": 99.7, "min_topk": 2},
    ("Doutrina", "Doutrina"): {"percentile": 99.0, "min_topk": 3},
}
```

**Vantagens**:
- ✅ Threshold ajustado à distribuição real de cada par
- ✅ Robusto para distribuições não-normais (percentil > μ + kσ)
- ✅ Evita viés de vocabulário compartilhado

### **Melhoria: Budget Allocation Não Circular**

```bash
# Habilitar budget allocation baseado no potencial
KG_BUILDER_USE_BUDGET_ALLOCATION=true            # Default: true
KG_BUILDER_EMBEDDING_TOTAL_BUDGET=10000          # Budget total de links
```

**Problema com alocação circular**:
- Usar os próprios links existentes para decidir quantos links criar
- Viés: pares com mais links históricos recebem mais budget

**Solução: Budget allocation não circular**:
1. Conta `n_entities` de cada tipo (`N_decisao`, `N_sumula`, etc.)
2. Calcula **potencial** = `N_a × N_b` (ou `N×(N-1)/2` se mesmo tipo)
3. Garante `min_topk` por nó (budget fixo da config)
4. Distribui budget restante **proporcionalmente ao potencial**

**Exemplo**:
```
N_decisao = 1000  → Potencial = 1000×999/2 = 499,500
N_sumula = 100    → Potencial = 100×99/2   = 4,950

Budget total = 10,000
Budget reservado (min_topk):
  - Decisao: 3 × 1000 = 3,000
  - Sumula: 2 × 100 = 200
  Total reservado = 3,200

Budget restante = 10,000 - 3,200 = 6,800
Distribuição proporcional:
  - Decisao: 6,800 × (499,500 / 504,450) = 6,733 → total = 9,733 links
  - Sumula: 6,800 × (4,950 / 504,450) = 67 → total = 267 links

Max per node:
  - Decisao: 9,733 / 1,000 ≈ 10 links/node
  - Sumula: 267 / 100 ≈ 3 links/node
```

**Vantagens**:
- ✅ Aloca mais budget para pares com maior potencial
- ✅ Garante mínimo (`min_topk`) para todos os pares
- ✅ Não depende de links existentes (não circular)

---

### **Fase 3 — LLM Validation**

```bash
# Habilitar validação via LLM
KG_BUILDER_INFER_LINKS_LLM=true

# Configuração do LLM
KG_BUILDER_LLM_PROVIDER=openai              # Default: openai
KG_BUILDER_LLM_MODEL=gpt-4o-mini            # Default: gpt-4o-mini
KG_BUILDER_LLM_MIN_CONFIDENCE=0.75          # Default: 0.75

# Limites de avaliação (controla custo)
KG_BUILDER_LLM_MAX_DECISAO_PAIRS=50         # Default: 50
KG_BUILDER_LLM_MAX_DOUTRINA_PAIRS=30        # Default: 30

# Default: false (desabilitado)
```

**Algoritmo**:
1. Seleciona pares candidatos (com contexto compartilhado)
2. Envia prompt ao LLM pedindo análise da relação
3. LLM retorna: `has_relationship`, `relationship_type`, `confidence`, `reasoning`
4. Cria link apenas se `confidence >= min_confidence`

**Tipos de link sugeridos**:
- `CITA` — citação direta
- `CONFIRMA` — ratifica entendimento
- `SUPERA` — muda entendimento (overruling)
- `DISTINGUE` — distinguishing (casos diferentes)
- `COMPLEMENTA` — complementação (Doutrina)

**Custo**: **~$0.001 por par avaliado** (gpt-4o-mini)
- 50 pares de Decisão + 30 de Doutrina = 80 API calls = **~$0.08 por execução**

---

## 📊 Exemplo de Configuração por Ambiente

### **Desenvolvimento** (exploração)

```bash
# Habilitar todas as fases
KG_BUILDER_INFER_LINKS_STRUCTURAL=true
KG_BUILDER_INFER_LINKS_EMBEDDING=true
KG_BUILDER_INFER_LINKS_LLM=true

# Usar thresholds adaptativos e budget allocation
KG_BUILDER_USE_ADAPTIVE_THRESHOLDS=true
KG_BUILDER_USE_BUDGET_ALLOCATION=true
KG_BUILDER_EMBEDDING_TOTAL_BUDGET=5000           # Baixo para controlar custo

# LLM com baixo limite para controlar custo
KG_BUILDER_LLM_MAX_DECISAO_PAIRS=20
KG_BUILDER_LLM_MAX_DOUTRINA_PAIRS=10
```

### **Staging** (validação)

```bash
# Somente estrutural + embeddings (sem custo LLM)
KG_BUILDER_INFER_LINKS_STRUCTURAL=true
KG_BUILDER_INFER_LINKS_EMBEDDING=true
KG_BUILDER_INFER_LINKS_LLM=false

# Usar thresholds adaptativos (recomendado)
KG_BUILDER_USE_ADAPTIVE_THRESHOLDS=true
KG_BUILDER_USE_BUDGET_ALLOCATION=true
KG_BUILDER_EMBEDDING_TOTAL_BUDGET=10000

# Alternativa: thresholds fixos mais conservadores (se adaptive=false)
# KG_BUILDER_USE_ADAPTIVE_THRESHOLDS=false
# KG_BUILDER_EMBEDDING_THRESHOLD_DECISAO=0.88
# KG_BUILDER_EMBEDDING_THRESHOLD_SUMULA=0.90
```

### **Produção** (conservador)

```bash
# Somente estrutural (zero custo, alta confiança)
KG_BUILDER_INFER_LINKS_STRUCTURAL=true
KG_BUILDER_INFER_LINKS_EMBEDDING=false
KG_BUILDER_INFER_LINKS_LLM=false

# Se habilitar embeddings, usar adaptive thresholds
# KG_BUILDER_INFER_LINKS_EMBEDDING=true
# KG_BUILDER_USE_ADAPTIVE_THRESHOLDS=true
# KG_BUILDER_USE_BUDGET_ALLOCATION=true
```

---

## 🔍 Metadados das Arestas Inferidas

Todas as arestas criadas automaticamente têm:

```cypher
{
  source: "transitive_closure" | "co_citation" | "embedding_similarity" | "llm_validation",
  derived: true,  // Indica que foi inferida (não extraída)
  confidence: 0.5-1.0,  // Confiança da inferência
  created_at: datetime(),
  dimension: "remissiva" | "horizontal" | "doutrinaria",

  // Metadados específicos
  bridge_count: 2,  // (transitive) quantos nós intermediários
  shared_entities: 5,  // (co-citation) quantas entidades compartilhadas
  similarity_score: 0.87,  // (embedding) score de similaridade
  llm_reasoning: "...",  // (LLM) justificativa do LLM
}
```

---

## 📈 Estatísticas Retornadas

O post-processor retorna estatísticas detalhadas:

```python
@dataclass
class LegalPostProcessStats:
    # Phase 1: Structural
    transitive_remete_a_inferred: int = 0
    transitive_cita_inferred: int = 0
    co_citation_links_inferred: int = 0
    parent_inheritance_links_inferred: int = 0
    symmetric_cita_inferred: int = 0
    jurisprudence_cluster_links_inferred: int = 0

    # Phase 2: Embedding
    embedding_decisao_links_inferred: int = 0
    embedding_sumula_links_inferred: int = 0
    embedding_doutrina_links_inferred: int = 0

    # Phase 3: LLM
    llm_links_suggested: int = 0
    llm_links_created: int = 0
    llm_api_calls: int = 0
```

---

## 🛡️ Segurança e Qualidade

### **Garantias**

1. ✅ **Nunca sobrescreve** links explícitos (extraídos do texto)
2. ✅ **Todas as arestas inferidas** têm `derived=true`
3. ✅ **Nenhuma aresta duplicada** (verifica existência antes de criar)
4. ✅ **Confiança sempre < 1.0** (links explícitos = 1.0)
5. ✅ **Self-loops são ignorados** (A → A)

### **Validação Manual**

Para revisar links inferidos:

```cypher
// Ver todos os links derivados
MATCH ()-[r {derived: true}]->()
RETURN type(r) AS rel_type,
       r.source AS inference_method,
       r.confidence AS confidence,
       count(*) AS total
ORDER BY total DESC

// Ver links com baixa confiança
MATCH (a)-[r {derived: true}]->(b)
WHERE r.confidence < 0.7
RETURN a.name, type(r), b.name, r.confidence, r.source
LIMIT 50
```

### **Rollback de Inferências**

Para remover links inferidos:

```cypher
// Remover todos os links derivados
MATCH ()-[r {derived: true}]->()
DELETE r

// Remover apenas de uma fase específica
MATCH ()-[r {source: 'embedding_similarity'}]->()
DELETE r
```

---

## 🧪 Testes Recomendados

### **1. Validar Transitividade**

```cypher
// Criar cadeia A → B → C manualmente
CREATE (a:Artigo {name: 'Art. 100 do CTN'})
CREATE (b:Artigo {name: 'Art. 101 do CTN'})
CREATE (c:Artigo {name: 'Art. 102 do CTN'})
CREATE (a)-[:REMETE_A {evidence: 'teste'}]->(b)
CREATE (b)-[:REMETE_A {evidence: 'teste'}]->(c)

// Executar post-processor com KG_BUILDER_INFER_LINKS_STRUCTURAL=true

// Verificar se A → C foi criada
MATCH (a:Artigo {name: 'Art. 100 do CTN'})-[r:REMETE_A]->(c:Artigo {name: 'Art. 102 do CTN'})
RETURN r.derived, r.source, r.confidence
// Esperado: derived=true, source='transitive_closure', confidence≈0.6
```

### **2. Validar Co-citação**

```cypher
// Criar 2 decisões interpretando mesmos artigos
CREATE (d1:Decisao {name: 'REsp 100.000'}), (d2:Decisao {name: 'REsp 200.000'})
CREATE (a1:Artigo {name: 'Art. 100'}), (a2:Artigo {name: 'Art. 101'}), (a3:Artigo {name: 'Art. 102'})
CREATE (d1)-[:INTERPRETA]->(a1), (d1)-[:INTERPRETA]->(a2), (d1)-[:INTERPRETA]->(a3)
CREATE (d2)-[:INTERPRETA]->(a1), (d2)-[:INTERPRETA]->(a2), (d2)-[:INTERPRETA]->(a3)

// Executar post-processor

// Verificar se d1 → d2 foi criada
MATCH (d1)-[r:CITA]->(d2)
WHERE r.derived = true
RETURN r.source, r.shared_entities
// Esperado: source='co_citation', shared_entities=3
```

---

## 📚 Arquivos do Sistema

```
apps/api/app/services/rag/core/kg_builder/
├── link_inference.py          # Fase 1: Inferência estrutural
├── link_predictor.py          # Fase 2: Similaridade por embeddings
├── llm_link_suggester.py      # Fase 3: Validação via LLM
├── legal_postprocessor.py     # Integração (chama as 3 fases)
└── LINK_INFERENCE.md          # Esta documentação
```

---

## 🚀 Próximos Passos

### **Melhorias Futuras**

1. **Graph Neural Networks** (GDS):
   ```cypher
   // Link prediction com FastRP + Random Forest
   CALL gds.beta.pipeline.linkPrediction.train(...)
   ```

2. **Active Learning**:
   - Permitir que usuários marquem links como "corretos" ou "incorretos"
   - Re-treinar thresholds baseado no feedback

3. **Temporal Awareness**:
   - Considerar data de publicação (decisão antiga não cita decisão futura)
   - Peso maior para precedentes cronologicamente anteriores

4. **Multi-hop Reasoning**:
   - Cadeias mais longas (A→B→C→D→E)
   - Algoritmos de caminho mínimo com peso por confiança

---

## ❓ FAQ

**Q: Os links inferidos aparecem nas queries normais?**
A: Sim, a menos que você filtre por `derived = false`.

**Q: Qual o impacto de performance?**
A: **Fase 1**: ~5-10s em 100k nós. **Fase 2**: ~30-60s em 2k nós. **Fase 3**: ~2-5 min (depende de API latency).

**Q: Posso rodar apenas uma fase?**
A: Sim! As env vars permitem habilitar/desabilitar cada fase independentemente.

**Q: Como reverter uma inferência ruim?**
A: `MATCH ()-[r {source: 'nome_do_método'}]->() DELETE r`

**Q: A Fase 3 funciona com Gemini/Claude?**
A: Sim! Basta configurar `KG_BUILDER_LLM_PROVIDER=gemini` ou `anthropic`.
