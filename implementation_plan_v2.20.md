# Plano de Melhorias Futuras - Formatação Adaptativa (v2.20+)

Este plano documenta melhorias identificadas para tornar o sistema de formatação mais inteligente e adaptativo ao tipo de conteúdo.

---

## Proposta 1: Propagação do Tipo de Aula para Formatação

### Problema
O `PROMPT_MAPEAMENTO` detecta o tipo de aula (`SIMULADO`, `EXPOSITIVA`, `REVISÃO`), mas essa informação é usada apenas para gerar o esqueleto estrutural e depois descartada. Os prompts de formatação são genéricos.

### Solução
1. Extrair o `[TIPO: ...]` do resultado de `map_structure`.
2. Armazenar como `self.detected_class_type`.
3. Injetar seção condicional no prompt de formatação:

```python
# Em format_transcription_async, após map_structure:
tipo_match = re.search(r'\[TIPO:\s*(\w+)', global_structure)
self.detected_class_type = tipo_match.group(1) if tipo_match else "EXPOSITIVA"

# Em process_chunk_async, adicionar ao system_prompt:
if self.detected_class_type == "SIMULADO":
    system_prompt += INSTRUCOES_SIMULADO
elif self.detected_class_type == "REVISAO":
    system_prompt += INSTRUCOES_REVISAO
```

### Instruções Específicas por Tipo

| Tipo | Instruções Adicionais |
|------|----------------------|
| SIMULADO | Preservar enunciados íntegros, destacar gabaritos em negrito, manter numeração de questões |
| REVISÃO | Priorizar bullet points e tabelas comparativas, condensar explicações |
| CORREÇÃO | Destacar alternativas certas/erradas, manter referência a itens |

---

## Proposta 2: Janela de Contexto Adaptativa

### Problema
A janela fixa de 15% pode ser excessiva para aulas curtas (poucos chunks) ou insuficiente para aulas muito longas.

### Solução
Tornar o tamanho da janela proporcional ao número de chunks:

```python
# Substituir:
window_size = max(4, int(len(itens_estrutura) * 0.15))

# Por:
if total_segments <= 5:
    window_size = 2  # Apenas anterior + próximo
elif total_segments <= 15:
    window_size = max(3, int(len(itens_estrutura) * 0.10))
else:
    window_size = max(4, min(int(len(itens_estrutura) * 0.15), 8))
```

---

## Proposta 3: Atualizar implementation_plan.txt

Sincronizar o plano original com a implementação real (v2.18 usa 15%, não "anterior + próximo").

---

## Arquivos a Modificar

| Arquivo | Mudança |
|---------|---------|
| `mlx_vomo.py` | Extrair tipo, injetar instruções condicionais, janela adaptativa |
| `implementation_plan.txt` | Atualizar documentação para refletir v2.18+ |

---

## Prioridade

1. **Alta**: Proposta 1 (Tipo → Prompt) — Impacto direto na qualidade de simulados
2. **Média**: Proposta 2 (Janela Adaptativa) — Otimização
3. **Baixa**: Proposta 3 (Documentação)

---

## Verificação

- Processar um simulado e verificar se questões mantêm enunciado íntegro
- Processar aula expositiva longa e confirmar janela de contexto adequada
- Comparar output antes/depois da mudança
