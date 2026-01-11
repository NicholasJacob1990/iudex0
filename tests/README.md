# Test Suite for LLM Strategy Comparison

Este diretório contém scripts de teste para comparar diferentes estratégias de formatação de transcrições usando diferentes modelos LLM.

## 🎯 Estratégias Testadas

1. **Gemini 2.5 Flash (100%)** - Baseline de custo ($0.30/M tokens)
2. **Claude Sonnet 4.5 (100%)** - Baseline de qualidade ($3.00/M tokens)  
3. **Híbrido (Gemini + Claude)** - Roteamento inteligente baseado em criticidade

## 🚀 Como Usar

### 1. Configuração

```bash
# Instalar dependências
pip install -r requirements.txt

# Configurar API key do OpenRouter
cp .env.example .env
# Edite .env e adicione sua chave: OPENROUTER_API_KEY=sk-or-v1-...
```

### 2. Executar Teste

```bash
python test_runner.py ../Aulas_PGM_RJ/04_Ubanistico_constitucional.txt
```

### 3. Resultados

Os resultados serão salvos em `test_results/`:
- `output_*.md` - Textos formatados por cada estratégia
- `audit_*.md` - Relatórios de validação de cada estratégia
- `comparison_report.md` - Comparação completa com métricas

## 📊 Métricas Coletadas

- **Custo**: Calculado com base em tokens usados
- **Tempo**: Duração total do processamento
- **Qualidade**: Validação heurística (leis, autores, dicas preservadas)
- **Tamanho**: Caracteres do output final
- **Distribuição (Híbrido)**: % de chunks processados por Claude vs Gemini

## 🧠 Lógica do Híbrido

O formatador híbrido usa heurísticas para decidir qual modelo usar:

**Claude (qualidade máxima) para:**
- Chunks com 20+ referências técnicas (leis, súmulas, dicas)
- Chunks narrativos (exemplos, histórias, casos)

**Gemini (economia) para:**
- Chunks expositivos simples (definições, conceitos básicos)

## 💰 Custos Estimados

Para transcrição típica de 50k chars (~100k tokens):

| Estratégia | Custo Estimado |
|------------|----------------|
| Gemini 100% | $0.03 |
| Claude 100% | $0.30 |
| Híbrido (60% Claude) | $0.15 |

## 📝 Próximos Passos

Após analisar os resultados:

1. Compare os textos lado-a-lado (abra os 3 `.md` files)
2. Leia `comparison_report.md` para ver métricas
3. Decida qual estratégia usar em produção
4. Atualize `format_only.py` ou `mlx_vomo.py` conforme escolhido
