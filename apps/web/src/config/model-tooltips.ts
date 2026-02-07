import type { ModelId } from "@/config/models";

export const MODEL_DESCRIPTIONS: Partial<Record<ModelId, string>> = {
  "sonar-deep-research":
    "Sonar Deep Research (Perplexity) é focado em pesquisa multi‑etapas: busca, leitura, avaliação e síntese de fontes. Ideal para tópicos complexos e relatórios; contexto ~128k.",
  "sonar-pro":
    "Sonar Pro (Perplexity) aprimora a busca conectada à web com mais profundidade e janela de contexto maior. Indicado para consultas complexas; contexto ~200k (saída máx. ~8k).",
  "sonar":
    "Sonar (Perplexity) é um modelo web‑grounded com citações e resultados conectados à web em tempo real. Indicado para respostas atualizadas; contexto ~127k.",
  "sonar-reasoning-pro":
    "Modelo web-grounded com enfase em raciocinio. Bom para respostas analiticas com fontes.",
  "gemini-3-pro":
    "Gemini 3 Pro é um modelo de última geração para matemática, programação, uso de computador e tarefas de agente de longo prazo, entregando resultados de referência superiores, incluindo 23,4% no MathArena Apex (acima de 1,6%), SOTA no tau-bench, um Elo de 2.439 no LiveCodeBench Pro (vs. 2.234), 72,7% no ScreenSpot Pro (~2x o melhor anterior), e um patrimônio líquido médio superior no Vending Bench 2 (R$ 5.478 vs. R$ 3.838). Possui uma janela de contexto de entrada de 1 milhão e um máximo de 64 mil tokens de saída. Parâmetros opcionais: para instruir o bot a usar mais esforço de pensamento, selecione entre 'Low' ou 'High'. Para ativar a pesquisa na web e atualização de informações em tempo real, ative 'habilitar pesquisa web' (desativado por padrão).",
  "gemini-3-flash":
    "Modelo rapido e economico para alto volume e respostas curtas; bom para tarefas auxiliares e fluxos de alta demanda.",
  "gemini-2.5-pro":
    "Modelo robusto para raciocinio e tarefas longas, com janela de contexto ampla.",
  "gemini-2.5-flash":
    "Modelo rapido e economico da familia 2.5, indicado para alto volume e respostas curtas.",
  "gpt-5.2":
    "GPT-5.2 é um modelo de IA de última geração da OpenAI projetado para trabalho real em redação, análise, programação e resolução de problemas. Ele lida melhor com contextos longos e tarefas de múltiplas etapas do que as versões anteriores, e está ajustado para fornecer respostas precisas com menos erros. Suporta 400 mil tokens de contexto e visão nativa. Parâmetros opcionais: para instruir o bot a usar mais esforço de raciocínio, adicione --reasoning_effort ao final da sua mensagem com uma das opções 'low', 'medium', 'high' ou 'Xhigh' (padrão: 'None'). Use --web_search true para ativar a busca na web e o acesso a informações em tempo real (desativado por padrão). Use --verbosity para controlar os detalhes da resposta com uma das opções 'low', 'medium', 'high' (padrão: medium).",
  "gpt-5.2-instant":
    "GPT-5.2-Instant é um modelo conversacional rápido e consistente, desenvolvido para uso diário. Ele gerencia conversas longas sem perder o foco, mantém o contexto claro e responde de maneira direta. Ideal para planejamento, reescrita, resumos e auxílio técnico rápido. Suporta 400 mil tokens de contexto e visão nativa. Parâmetros opcionais: use --web_search true para ativar a busca na web e acesso a informações em tempo real (desativado por padrão).",
  "gpt-5":
    "GPT-5 é o modelo mais avançado da OpenAI com habilidades de programação significativamente melhoradas, contexto longo (400 mil tokens) e melhor seguimento de instruções. Suporta visão nativa e geralmente tem mais inteligência que o GPT-4.1. Fornece 90% de desconto no cache do histórico de chat. Para instruir o bot a usar mais esforço de raciocínio, adicione --reasoning_effort ao final da sua mensagem com uma das opções 'minimal', 'low', 'medium' ou 'high'. Use --web_search true para ativar a busca na web e acesso a informações em tempo real (desativado por padrão).",
  "gpt-5-mini":
    "Modelo rapido e barato, ideal para passos curtos (planner, HyDE e tarefas auxiliares).",
  "gpt-4o":
    "Modelo multimodal equilibrado para chat, visao e codigo.",
  "claude-4.6-opus":
    "Claude Opus 4.6 com foco em tarefas agenticas complexas e raciocinio profundo, com janela de contexto ampla.",
  "claude-4.5-opus":
    "Claude Opus 4.5 da Anthropic suporta orçamento de pensamento personalizável (até 64 mil tokens) e janela de contexto de 200 mil. Para instruir o bot a usar mais esforço de pensamento, adicione --thinking_budget e um número entre 0 e 63999 ao final da sua mensagem.",
  "claude-4.5-sonnet":
    "Claude Sonnet 4.5 representa um grande avanço na capacidade e alinhamento da IA. É o modelo mais avançado lançado pela Anthropic até o momento, distinguindo-se por melhorias dramáticas em raciocínio, matemática e programação no mundo real. Suporta 1 milhão de tokens de contexto. Para instruir o bot a usar mais esforço de pensamento, adicione --thinking_budget e um número entre 0 e 31999 ao final da sua mensagem. Use --web_search true para ativar a busca na web e atualização de informações em tempo real (desativado por padrão).",
  "claude-4.5-haiku":
    "Modelo rapido e economico para respostas curtas.",
  "grok-4":
    "Modelo focado em raciocinio e agentes, com boa performance em tarefas dificeis.",
  "grok-4-fast":
    "Variante mais rapida para alto volume, mantendo foco em raciocinio.",
  "grok-4.1-fast":
    "Variante rapida e atualizada para alto volume.",
  "grok-4.1":
    "Grok 4.1 (xAI) é focado em chamadas de ferramentas e raciocínio analítico avançado. Contexto ~2M.",
  "llama-4":
    "Modelo open-weights (via OpenRouter) com bom custo-beneficio para chat e analise.",
  "llama-4-maverick-t":
    "Llama 4 Maverick T (via OpenRouter/Meta) é multimodal (MoE 128 especialistas), com contexto ~500k e custo fixo por mensagem.",
  "internal-rag":
    "Agente RAG para responder a partir do material do caso (RAG interno + anexos), com foco em fundamentacao e citacoes. Roda sobre Gemini 3 Flash (Vertex).",
};

export function getModelDescription(modelId: ModelId): string {
  return MODEL_DESCRIPTIONS[modelId] || "Modelo de IA para chat e tarefas assistidas.";
}
