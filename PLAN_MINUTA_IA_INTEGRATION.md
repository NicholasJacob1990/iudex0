# Plano de Integração: Funcionalidades "Minuta IA"

## 1. Análise de Competidores ("Minuta IA" e Similares)

A análise de mercado de ferramentas como "Minuta IA", Jusbrasil, LegalOne e outras revela as seguintes funcionalidades chave que definem uma ferramenta de "Estado da Arte" em Direito:

| Funcionalidade | Descrição | Status no Iudex | Ação Necessária |
|---|---|---|---|
| **Geração Automatizada** | Criação de peças via chat/prompts. | ✅ Completo | Manter e refinar. |
| **Templates Inteligentes** | Biblioteca de modelos pré-formatados (ex: Habeas Corpus, Divórcio). | ⚠️ Básico | **Expandir biblioteca** com modelos de alta demanda. |
| **Pesquisa de Jurisprudência** | Busca em tempo real de julgados (STJ, TJs) para citar na peça. | ❌ Ausente | **Criar Agente Pesquisador** (integração com search API). |
| **Análise de Documentos (OCR)** | Ler PDF/Docs e extrair dados para a peça. | ✅ Completo | Garantir que o orquestrador use esses dados corretamente. |
| **Integração com PJe/Tribunais** | Protocolo automático ou exportação formatada. | ❌ Ausente | Fora do escopo atual (requer credenciais de advogado), mas podemos melhorar a **Exportação**. |
| **Gestão de Casos** | Salvar rascunhos e associar a clientes. | ✅ Parcial | Refinar UX de "Meus Chats/Minutas". |

## 2. Roadmap de Implementação

Para transformar o Iudex em um concorrente direto, implementaremos as funcionalidades em 3 fases:

### Fase 1: Conteúdo e Especialização (IMEDIATO)
Foco em aumentar a "inteligência jurídica" estática da ferramenta.
- [x] **Expansão de Templates**: Adicionar Habeas Corpus, Mandado de Segurança, Reclamação Trabalhista e Divórcio.
- [x] **Prompts Especializados**: Ensinar a IA a estruturar essas peças especificamente.
- [ ] **Validação de Citações**: Melhorar o `GeminiAgent` para verificar se a lei citada ainda existe (mesmo sem internet, usando base de conhecimento).

### Fase 2: Agente Pesquisador (CURTO PRAZO)
Dar à IA a capacidade de buscar fatos e leis novas.
- [ ] **Tool de Search**: Integrar Tavily/Google Search ao Orchestrator.
- [ ] **Agente de Jurisprudência**: Um passo no pipeline que busca 3-5 julgados relevantes antes de escrever.

### Fase 3: Fluxo de Trabalho (MÉDIO PRAZO)
- [ ] **Batch Processing**: "Gerar 10 defesas para estes 10 PDFs".
- [ ] **Integração de Agenda**: Controle de prazos (usando a data da citação no PDF).

## 3. Detalhamento da Implementação Atual (Fase 1)

### Novos Templates
Adicionaremos ao `LegalTemplateLibrary`:
1.  `habeas_corpus`: Criminal (urgente).
2.  `mandado_seguranca`: Direito Líquido e Certo.
3.  `reclamacao_trabalhista`: CLT.
4.  `divorcio_consensual`: Família.

### Novos Prompts
Atualizaremos `LegalPrompts` para incluir instruções específicas para:
- Requisitos do Art. 840 da CLT (Reclamação).
- Requisitos da Lei 12.016/09 (Mandado de Segurança).
- Requisitos do CPP para HC.

---
**Autor**: Iudex AI Assistant
**Data**: 20/11/2025

