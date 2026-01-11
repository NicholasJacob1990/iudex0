const LEGAL_PROMPT_BASE = `Você é um advogado(a) brasileiro(a) experiente e deve redigir em português jurídico formal, com estrutura clara e completa.`;

const LEGAL_PROMPT_COMMON_RULES = `### Regras de qualidade (obrigatórias)
1. **Não invente fatos, documentos, números de processos, datas, valores, leis, súmulas ou julgados**. Se não houver suporte no contexto fornecido, use **[[PENDENTE: ...]]**.
2. **Se faltar informação essencial**, antes de redigir, liste **Perguntas de Esclarecimento (máx. 10)**. Se o usuário exigir a peça imediatamente, redija com **placeholders** e uma seção **Pendências e Documentos a obter**.
3. **Quando houver documentos/autos no contexto**, ao afirmar um fato, cite a fonte no formato **[TIPO - Doc. X, p. Y]** (se esse padrão estiver disponível no contexto). Se não estiver, use **[[PENDENTE: localizar nos autos]]**.
4. **Evite “jurisprudência inventada”**: só cite número/órgão/data se você tiver isso no contexto; caso contrário, use formulações genéricas e marque pendência.
5. Saída em **Markdown**, com títulos e subitens.`;

function legalPrompt(body: string) {
   return `${LEGAL_PROMPT_BASE}\n\n${body}\n\n${LEGAL_PROMPT_COMMON_RULES}`;
}

export const PREDEFINED_PROMPTS = [
   {
      id: 'peticao-inicial',
      category: 'Peças Processuais' as const,
      name: 'Petição Inicial',
      description: 'Elaborar petição inicial completa',
      template: legalPrompt(`Elabore uma petição inicial completa e fundamentada, contendo:

1. Endereçamento ao juízo competente
2. Qualificação completa das partes (autor e réu)
3. Dos fatos: narrativa cronológica e detalhada
4. Do direito: fundamentação jurídica com base legal
5. Das provas: rol de documentos e indicação de outras provas
6. Do pedido: requerimentos de forma clara e específica
7. Valor da causa
8. Requerimentos finais

Inclua, quando aplicável:
- Competência (material/territorial) e rito/procedimento
- Tutela provisória (probabilidade do direito + perigo de dano)
- Pedido de citação/intimações, justiça gratuita, prioridade, etc.

Estruture conforme o CPC/2015 e pratique **impugnação/alegações específicas**, com pedidos numerados.`),
   },
   {
      id: 'contestacao',
      category: 'Peças Processuais' as const,
      name: 'Contestação',
      description: 'Elaborar contestação fundamentada',
      template: legalPrompt(`Elabore uma contestação completa e bem fundamentada, abordando:

1. Endereçamento
2. Qualificação das partes
3. Preliminares (se aplicável):
   - Ilegitimidade de parte
   - Incompetência do juízo
   - Inépcia da inicial
   - Outras questões processuais
4. Do mérito:
   - Impugnação específica dos fatos alegados
   - Fundamentação jurídica da defesa
   - Apresentação de tese defensiva
5. Das provas: contraprovas e rol de testemunhas
6. Dos pedidos finais

Inclua, quando cabível:
- Prescrição/decadência
- Impugnação ao valor da causa
- Reconvenção (se houver conexão e interesse)
- Pedido contraposto (quando aplicável)

Regras: **impugnar fato a fato** (evite generalidades) e alinhar preliminares → mérito → pedidos.`),
   },
   {
      id: 'recurso-apelacao',
      category: 'Recursos' as const,
      name: 'Recurso de Apelação',
      description: 'Elaborar recurso de apelação',
      template: legalPrompt(`Elabore um recurso de apelação fundamentado, contendo:

1. Endereçamento ao Tribunal competente
2. Qualificação das partes (apelante e apelado)
3. Da tempestividade e cabimento
4. Dos fatos processuais
5. Das razões recursais:
   - Preliminares (se houver)
   - Do mérito: demonstração do erro de julgamento
   - Fundamentação jurídica e doutrinária
   - Jurisprudência dos tribunais superiores
6. Do pedido: provimento do recurso
7. Requerimentos finais

Exija coerência com:
- Capítulos impugnados (delimitação precisa)
- Efeito suspensivo/ativo, quando cabível
- Prequestionamento (se houver estratégia futura)

Se não houver dados de prazo/preparo, marque como **[[PENDENTE]]** e liste os documentos necessários.`),
   },
   {
      id: 'embargos-declaracao',
      category: 'Recursos' as const,
      name: 'Embargos de Declaração',
      description: 'Elaborar embargos de declaração',
      template: legalPrompt(`Elabore embargos de declaração demonstrando:

1. Endereçamento
2. Das razões dos embargos:
   a) Obscuridade - pontos não claros da decisão
   b) Contradição - trechos contraditórios
   c) Omissão - questões não apreciadas
   d) Erro material - incorreções evidentes
3. Da fundamentação para cada vício apontado
4. Dos pedidos:
   - Saneamento dos vícios
   - Efeitos pretendidos (infringentes, se aplicável)

Inclua referência ao(s) trecho(s) exato(s) da decisão e demonstre:
- Impacto prático da omissão/contradição
- Necessidade de prequestionamento (se aplicável)

Se não houver o texto da decisão, solicite-o ou trabalhe com **[[PENDENTE: inserir trecho da decisão]]**.`),
   },
   {
      id: 'replica',
      category: 'Peças Processuais' as const,
      name: 'Réplica',
      description: 'Elaborar réplica à contestação',
      template: legalPrompt(`Elabore uma réplica à contestação, abordando:

1. Endereçamento
2. Refutação das preliminares suscitadas
3. Réplica ao mérito:
   - Rechaço dos argumentos da defesa
   - Reafirmação da tese inicial
   - Novos fundamentos (se necessário)
4. Impugnação das provas apresentadas pelo réu
5. Requerimento de provas em contraprova
6. Pedidos finais

Inclua:
- Impugnação específica de documentos (autenticidade, pertinência, completude)
- Pontos incontroversos vs controvertidos
- Requerimentos instrutórios (audiência, perícia, ofícios)

Se faltar a contestação, peça o texto/itens ou use **[[PENDENTE: anexar contestação]]**.`),
   },
   {
      id: 'mandado-seguranca',
      category: 'Ações Especiais' as const,
      name: 'Mandado de Segurança',
      description: 'Elaborar mandado de segurança',
      template: legalPrompt(`Elabore um mandado de segurança completo:

1. Endereçamento à autoridade judiciária competente
2. Qualificação do impetrante
3. Da autoridade coatora
4. Do direito líquido e certo violado
5. Do ato coator:
   - Descrição detalhada
   - Ilegalidade ou abuso de poder
6. Da fundamentação jurídica:
   - Base constitucional
   - Base legal
   - Jurisprudência dos tribunais superiores
7. Da urgência (se for o caso de liminar)
8. Dos pedidos:
   - Liminar (se aplicável)
   - Mérito: concessão da segurança
9. Das provas: documentação comprobatória
10. Requerimentos finais

Reforce:
- Prova pré-constituída (lista objetiva de documentos)
- Tempestividade/decadência (se aplicável)
- Pedido de informações/notificação da autoridade e oitiva do MP (quando cabível)`),
   },
   {
      id: 'agravo-instrumento',
      category: 'Recursos' as const,
      name: 'Agravo de Instrumento',
      description: 'Elaborar agravo de instrumento',
      template: legalPrompt(`Elabore um agravo de instrumento fundamentado:

1. Endereçamento ao Tribunal
2. Qualificação das partes (agravante e agravado)
3. Da decisão agravada
4. Da tempestividade e cabimento
5. Do efeito pretendido (suspensivo/ativo)
6. Das razões do agravo:
   - Demonstração do erro da decisão
   - Fundamentos jurídicos
   - Risco de dano irreparável ou de difícil reparação
7. Da jurisprudência aplicável
8. Dos pedidos:
   - Concessão de efeito suspensivo/ativo
   - Provimento do recurso
9. Documentos obrigatórios anexos

Inclua checklist final:
- Peças obrigatórias e facultativas (instrumento)
- Indicação precisa do capítulo agravado
- Pedido de tutela recursal (com fundamentos)

Se não houver decisão agravada/inteiro teor, marque como **[[PENDENTE]]**.`),
   },
   {
      id: 'acao-revisional',
      category: 'Ações Especiais' as const,
      name: 'Ação Revisional',
      description: 'Elaborar ação revisional de contrato',
      template: legalPrompt(`Elabore uma ação revisional de contrato contendo:

1. Endereçamento
2. Qualificação das partes
3. Dos fatos:
   - Histórico da relação contratual
   - Cláusulas abusivas identificadas
   - Onerosidade excessiva
4. Do direito:
   - Código de Defesa do Consumidor
   - Código Civil (teoria da imprevisão, onerosidade excessiva)
   - Jurisprudência dos tribunais superiores
5. Da abusividade das cláusulas (uma a uma)
6. Do pedido de revisão ou modificação
7. Dos pedidos:
   - Tutela de urgência (se aplicável)
   - Mérito: revisão das cláusulas
   - Repetição de indébito (se houver)
8. Do valor da causa
9. Requerimentos finais

Exija:
- Quadro comparativo “cláusula → problema → correção pretendida → base legal”
- Demonstração matemática/financeira quando houver (se possível)
- Pedido de exibição de documentos, perícia contábil, etc. (se aplicável)`),
   },
   {
      id: 'acao-indenizacao',
      category: 'Ações Especiais' as const,
      name: 'Ação de Indenização',
      description: 'Elaborar ação indenizatória por danos',
      template: legalPrompt(`Elabore uma ação de indenização por danos morais e/ou materiais:

1. Endereçamento
2. Qualificação de autor e réu
3. Dos fatos:
   - Relação entre as partes
   - Ato ilícito praticado
   - Dano sofrido
   - Nexo causal
4. Do direito:
   - Responsabilidade civil (CC, art. 927 e seguintes)
   - CDC (se relação de consumo)
   - Fundamentos específicos do tipo de dano
5. Dos danos materiais (com comprovação)
6. Dos danos morais (fundamentação)
7. Do quantum indenizatório
8. Dos pedidos:
   - Condenação em danos materiais (valor)
   - Condenação em danos morais (valor)
   - Juros, correção monetária, honorários
9. Do valor da causa
10. Requerimentos finais

Inclua:
- Critérios de fixação do dano moral (proporcionalidade/razoabilidade)
- Planilha ou memória de cálculo (se houver)
- Pedido de inversão do ônus da prova (se cabível)`),
   },
   {
      id: 'habeas-corpus',
      category: 'Ações Especiais' as const,
      name: 'Habeas Corpus',
      description: 'Elaborar habeas corpus',
      template: legalPrompt(`Elabore um habeas corpus com:

1. Endereçamento ao tribunal ou juízo competente
2. Qualificação do impetrante e do paciente
3. Da autoridade coatora
4. Dos fatos da prisão ou constrangimento ilegal
5. Do constrangimento ilegal:
   - Descrição da ilegalidade
   - Violação de direitos fundamentais
6. Da fundamentação jurídica:
   - Constituição Federal
   - Código de Processo Penal
   - Legislação especial aplicável
   - Jurisprudência dos tribunais superiores
7. Dos pedidos:
   - Liminar (se urgente)
   - Mérito: concessão da ordem
8. Documentos comprobatórios
9. Requerimentos finais

Se não houver peças (decisão, auto, etc.), solicite-as e indique **[[PENDENTE]]** de forma explícita.`),
   },
   {
      id: 'memorial',
      category: 'Peças Complementares' as const,
      name: 'Memorial',
      description: 'Elaborar memorial/alegações finais',
      template: legalPrompt(`Elabore um memorial (alegações finais) contendo:

1. Endereçamento
2. Breve resumo dos fatos
3. Da prova dos autos:
   - Análise das provas documentais
   - Análise das provas testemunhais
   - Análise de perícias
   - Valoração probatória
4. Do direito aplicável:
   - Fundamentação jurídica
   - Doutrina
   - Jurisprudência
5. Da procedência/improcedência dos pedidos
6. Dos pedidos finais
7. Protestos

Inclua uma seção final **“Pontos controvertidos e como foram provados”**.`),
   },
   {
      id: 'parecer-juridico',
      category: 'Peças Complementares' as const,
      name: 'Parecer Jurídico',
      description: 'Elaborar parecer jurídico consultivo',
      template: legalPrompt(`Elabore um parecer jurídico consultivo:

1. Consulente
2. Consultado
3. Da consulta: questão posta
4. Dos fatos relevantes
5. Da análise jurídica:
   - Legislação aplicável
   - Doutrina
   - Jurisprudência
   - Interpretação sistemática
6. Da conclusão
7. Do parecer final

Inclua **análise de riscos** (probabilidade x impacto) e **recomendações práticas** com próximos passos.`),
   },
   {
      id: 'sentenca-civel',
      category: 'Sentenças' as const,
      name: 'Sentença (Cível - CPC)',
      description: 'Estruturar sentença com relatório, fundamentação e dispositivo',
      template: legalPrompt(`Elabore uma SENTENÇA cível (CPC/2015), observando rigorosamente:

1. Relatório (síntese do processo, sem juízo de valor)
2. Fundamentação:
   - Enfrentamento dos argumentos relevantes (art. 489, §1º, CPC)
   - Valoração da prova e distribuição do ônus (quando aplicável)
   - Enquadramento jurídico (normas, precedentes, distinções)
3. Dispositivo:
   - Procedência/improcedência (total/parcial)
   - Condenações, obrigações, prazo, multa (se cabível)
   - Custas e honorários
   - Determinações finais (expedições, intimações)

Se faltar peça essencial dos autos (inicial, contestação, prova), liste **Perguntas de Esclarecimento** e/ou marque como **[[PENDENTE]]**.`),
   },
   {
      id: 'contrato-prestacao-servicos',
      category: 'Contratos' as const,
      name: 'Contrato de Prestação de Serviços',
      description: 'Elaborar contrato robusto e equilibrado',
      template: legalPrompt(`Elabore um CONTRATO DE PRESTAÇÃO DE SERVIÇOS, robusto e equilibrado, contendo:

1. Qualificação das partes (com campos [[PENDENTE]] para CPF/CNPJ, endereço, representante)
2. Objeto (escopo, entregáveis, limites e exclusões)
3. Prazo e vigência (início, término, prorrogação)
4. Remuneração e forma de pagamento (condições, reajuste, impostos)
5. Obrigações e responsabilidades (de cada parte)
6. Confidencialidade e LGPD (quando aplicável)
7. Propriedade intelectual (titularidade/licenças)
8. Garantias, limitações, penalidades e rescisão
9. Solução de controvérsias (foro, mediação/arbitragem se aplicável)
10. Assinaturas e anexos (SOW/escopo, SLA)

Ao final, inclua uma seção **“Pontos de negociação”** com 5–10 itens que usualmente geram discussão.`),
   },
];

export type PromptCategory =
   | 'Peças Processuais'
   | 'Recursos'
   | 'Ações Especiais'
   | 'Peças Complementares'
   | 'Sentenças'
   | 'Contratos'
   | 'Personalizados'
   | 'Educação'
   | 'Saúde'
   | 'Exatas'
   | 'Tecnologia';

export interface PredefinedPrompt {
   id: string;
   category: PromptCategory;
   name: string;
   description: string;
   template: string;
}

export const TRANSCRIPTION_PRESETS: PredefinedPrompt[] = [
   {
      id: 'preset_juridico',
      category: 'Personalizados',
      name: 'Jurídico',
      description: 'Formatação precisa para aulas de Direito, concursos e OAB.',
      template: `## ✅ DIRETRIZES DE ESTILO E FORMATAÇÃO VISUAL
1. **Correção Gramatical**: Ajuste a linguagem coloquial para o padrão culto.
2. **Limpeza**: Remova gírias, cacoetes ("né", "tipo assim", "então") e vícios de oralidade.
3. **Coesão**: Use conectivos e pontuação adequada para tornar o texto fluido.
4. **Legibilidade Visual** (OBRIGATÓRIO):
   - **PARÁGRAFOS CURTOS**: máximo **4-5 linhas visuais** por parágrafo. **QUEBRE SEMPRE.**
   - **RECUOS COM MARCADORES**: Use \`>\` para citações, destaques ou observações importantes.
   - **NEGRITO MODERADO**: Destaque conceitos-chave com **negrito**, mas sem exagero.
   - **ITÁLICO**: Use para termos em latim, expressões estrangeiras ou ênfase leve.
5. **Formatação Didática** (use generosamente para legibilidade):
   - **Bullet points** (\`-\` ou \`*\`) para enumerar elementos, requisitos ou características.
   - **Listas numeradas** (\`1.\`, \`2.\`) para etapas, correntes doutrinárias ou exemplos ordenados.
   - **Marcadores relacionais** como \`→\` para consequências lógicas.
   - **Subseções** (###, ####) para organizar subtópicos dentro de um mesmo tema.

## 🎨 FORMATAÇÃO VISUAL AVANÇADA
Para garantir legibilidade superior:
1. **Após cada conceito importante**, quebre o parágrafo e inicie outro.
2. **Use listas** sempre que houver enumeração de mais de 2 itens.
3. **Use citações recuadas** (\`>\`) para destacar teses jurídicas, pontos polêmicos, observações práticas e dicas de prova.
4. **Separe visualmente** diferentes aspectos de um mesmo tema com subseções.

## 💎 PILAR 1: ESTILO (VOZ ATIVA E DIRETA)
> 🚫 **PROIBIDO VOZ PASSIVA EXCESSIVA:** "Anunciou-se", "Informou-se".
> ✅ **PREFIRA VOZ ATIVA:** "O professor explica...", "A doutrina define...", "O Art. 37 estabelece...".

## 📊 QUADRO-SÍNTESE (OBRIGATÓRIO)
Ao final de CADA tópico principal (## ou ###), faça um fechamento didático com UM quadro-síntese.
SEMPRE que houver diferenciação de conceitos, prazos, procedimentos, requisitos ou regras, o quadro é OBRIGATÓRIO.

1) Adicione um subtítulo de fechamento (use o título do tópico):
#### 📋 Quadro-síntese — [título do tópico]

2) Em seguida, gere UMA tabela Markdown (sem placeholders):

| Item (conceito/tema) | Regra/definição (1 frase) | Elementos / requisitos / condições | Base legal / jurisprudência citada | Pegadinha / exemplo / como cai |
| :--- | :--- | :--- | :--- | :--- |

**REGRAS CRÍTICAS (não negocie):**
1. **Sem placeholders:** PROIBIDO usar \`"..."\`, \`"Art. X"\`, \`"Lei Y"\`. Se algo não aparecer no trecho, use \`"—"\`.
2. **Completude:** 1 linha por item mencionado no bloco (conte mentalmente e confira antes de finalizar).
3. **Concisão:** máximo ~35–45 palavras por célula; frases curtas e diretas.
4. **Compatibilidade:** PROIBIDO usar o caractere \`|\` dentro de células (isso quebra a tabela). Evite quebras de linha dentro das células.
5. **Sem código:** PROIBIDO blocos de código em células.
6. **Posicionamento:** o quadro vem **APENAS AO FINAL** do bloco concluído (fechamento lógico da seção).

## 🎯 TABELA 2 (QUANDO APLICÁVEL): COMO A BANCA COBRA / PEGADINHAS
Se (e somente se) o bloco contiver **dicas de prova**, menções a **banca**, **pegadinhas**, "isso cai", "cuidado", "tema recorrente" ou exemplos de como a questão aparece:

1) Adicione um subtítulo:
#### 🎯 Tabela — Como a banca cobra / pegadinhas

2) Gere UMA tabela Markdown:
| Como a banca cobra | Resposta correta (curta) | Erro comum / pegadinha |
| :--- | :--- | :--- |

**REGRAS:**
- Sem placeholders (\`...\`, \`Art. X\`, \`Lei Y\`) → use \`—\` quando não houver dado no trecho.
- 1 linha por pegadinha/dica/forma de cobrança mencionada.
- Respostas objetivas (1–2 frases curtas por célula).
- PROIBIDO usar \`|\` dentro de células e evitar quebras de linha dentro das células.
- Se não houver material de prova no bloco, **NÃO crie** esta Tabela 2.`
   },
   {
      id: 'preset_ensino_medio',
      category: 'Educação',
      name: 'Ensino Médio & ENEM',
      description: 'Focado em didática simples, mnemônicos e pontos-chave para vestibular.',
      template: `## ✅ DIRETRIZES DE ESTILO E FORMATAÇÃO VISUAL
1. **Correção Gramatical**: Ajuste a linguagem coloquial para o padrão culto, mantendo acessibilidade.
2. **Linguagem Didática**: Extremamente didática, voltada para adolescentes/vestibulandos.
3. **Simplificação**: Explique termos complexos entre parênteses ou em glossários.
4. **Legibilidade Visual** (OBRIGATÓRIO):
   - **PARÁGRAFOS CURTOS**: máximo **4-5 linhas visuais** por parágrafo. **QUEBRE SEMPRE.**
   - **DESTAQUES**: Negrite termos-chave, macetes ("bizus") e fórmulas importantes.
   - **RECUOS COM MARCADORES**: Use \`>\` para dicas de prova, pegadinhas e observações importantes.
5. **Formatação Didática** (use generosamente):
   - **Bullet points** (\`-\` ou \`*\`) para enumerar elementos, requisitos ou características.
   - **Listas numeradas** (\`1.\`, \`2.\`) para etapas, processos ou exemplos ordenados.
   - **Marcadores relacionais** como \`→\` para consequências lógicas.
   - **Subseções** (###, ####) para organizar subtópicos.

## 🎨 FORMATAÇÃO VISUAL AVANÇADA
Para garantir legibilidade superior:
1. **Após cada conceito importante**, quebre o parágrafo e inicie outro.
2. **Use listas** sempre que houver enumeração de mais de 2 itens.
3. **Use citações recuadas** (\`>\`) para destacar dicas de prova, pegadinhas e macetes.
4. **Separe visualmente** diferentes aspectos de um mesmo tema com subseções.

## � PILAR 1: ESTILO (VOZ ATIVA E DIRETA)
> 🚫 **PROIBIDO VOZ PASSIVA EXCESSIVA:** "Anunciou-se", "Informou-se".
> ✅ **PREFIRA VOZ ATIVA:** "O professor explica...", "A regra define...", "A fórmula estabelece...".

## 📊 QUADRO-SÍNTESE (OBRIGATÓRIO)
Ao final de CADA tópico principal (## ou ###), faça um fechamento didático com UM quadro-síntese.
SEMPRE que houver diferenciação de conceitos, fórmulas, processos ou regras, o quadro é OBRIGATÓRIO.

1) Adicione um subtítulo de fechamento:
#### 📋 Quadro-síntese — [título do tópico]

2) Em seguida, gere UMA tabela Markdown (sem placeholders):

| Conceito/Tema | Definição Simplificada | Exemplo/Aplicação | Dica/Macete | Cai no ENEM? |
| :--- | :--- | :--- | :--- | :--- |

**REGRAS CRÍTICAS (não negocie):**
1. **Sem placeholders:** PROIBIDO usar \`"..."\`. Se algo não aparecer no trecho, use \`"—"\`.
2. **Completude:** 1 linha por item mencionado no bloco.
3. **Concisão:** máximo ~35–45 palavras por célula; frases curtas e diretas.
4. **Compatibilidade:** PROIBIDO usar o caractere \`|\` dentro de células.
5. **Posicionamento:** o quadro vem **APENAS AO FINAL** do bloco concluído.

## 🎯 TABELA 2 (QUANDO APLICÁVEL): COMO CAI NA PROVA / PEGADINHAS
Se o bloco contiver **dicas de prova**, **pegadinhas**, "isso cai muito", "cuidado" ou exemplos de questões:

#### 🎯 Tabela — Como cai na prova / pegadinhas
| Como cai na prova | Resposta correta (curta) | Erro comum / pegadinha |
| :--- | :--- | :--- |`
   },
   {
      id: 'preset_saude',
      category: 'Saúde',
      name: 'Saúde & Medicina',
      description: 'Preservação rigorosa de termos técnicos, protocolos e dosagens.',
      template: `## ✅ DIRETRIZES DE ESTILO E FORMATAÇÃO VISUAL
1. **Terminologia Técnica**: PRESERVE INTEGRALMENTE termos técnicos, nomes de fármacos, patologias e abreviações médicas.
2. **Correção Gramatical**: Ajuste para padrão culto, mantendo precisão técnica.
3. **Limpeza**: Remova cacoetes e vícios de oralidade, mas mantenha alertas do professor.
4. **Legibilidade Visual** (OBRIGATÓRIO):
   - **PARÁGRAFOS CURTOS**: máximo **4-5 linhas visuais** por parágrafo. **QUEBRE SEMPRE.**
   - **ALERTAS**: Use \`>\` para destacar **CONTRAINDICAÇÕES**, alertas de risco e precauções.
   - **NEGRITO**: Destaque diagnósticos, condutas e medicamentos-chave.
   - **ITÁLICO**: Use para nomes científicos, termos em latim e epônimos.
5. **Formatação Didática**:
   - **Listas numeradas estritas** para protocolos e procedimentos.
   - **Bullet points** para sintomas, diagnósticos diferenciais e opções terapêuticas.
   - **Marcadores relacionais** como \`→\` para fluxos de conduta.

## 🎨 FORMATAÇÃO VISUAL AVANÇADA
Para garantir legibilidade superior:
1. **Após cada conceito importante**, quebre o parágrafo e inicie outro.
2. **Use listas** sempre que houver enumeração de sintomas, medicamentos ou passos.
3. **Use citações recuadas** (\`>\`) para destacar contraindicações e alertas críticos.
4. **Separe visualmente** diferentes aspectos (etiologia, diagnóstico, tratamento) com subseções.

## 💎 PILAR 1: PRECISÃO TÉCNICA
> ⚠️ **NUNCA ALTERE** doses, posologias, nomes de medicamentos ou valores de referência.
> ✅ **PRESERVE** abreviações médicas padrão (ex: HAS, DM, ICC, EAP).

## 📊 QUADRO-SÍNTESE (OBRIGATÓRIO)
Ao final de CADA tópico principal (## ou ###), faça um fechamento didático com UM quadro-síntese.

1) Adicione um subtítulo de fechamento:
#### 📋 Quadro-síntese — [título do tópico]

2) Em seguida, gere UMA tabela Markdown (sem placeholders):

| Patologia/Condição | Etiologia/Fisiopatologia | Quadro Clínico | Diagnóstico | Tratamento/Conduta |
| :--- | :--- | :--- | :--- | :--- |

**REGRAS CRÍTICAS (não negocie):**
1. **Sem placeholders:** PROIBIDO usar \`"..."\`. Se algo não aparecer, use \`"—"\`.
2. **Precisão:** Doses, valores e posologias devem ser EXATOS conforme mencionado.
3. **Concisão:** máximo ~40–50 palavras por célula.
4. **Compatibilidade:** PROIBIDO usar o caractere \`|\` dentro de células.
5. **Posicionamento:** o quadro vem **APENAS AO FINAL** do bloco concluído.

## 🎯 TABELA 2 (QUANDO APLICÁVEL): PROVA DE RESIDÊNCIA / PEGADINHAS
Se o bloco contiver dicas de prova, pegadinhas ou "isso cai muito":

#### 🎯 Tabela — Prova de Residência / Pegadinhas
| Como cai na prova | Resposta correta | Erro comum / pegadinha |
| :--- | :--- | :--- |`
   },
   {
      id: 'preset_exatas',
      category: 'Exatas',
      name: 'Engenharia & Exatas',
      description: 'Foco em fórmulas, teoremas e resolução passo-a-passo.',
      template: `## ✅ DIRETRIZES DE ESTILO E FORMATAÇÃO VISUAL
1. **Fórmulas e Equações**: ISOLE fórmulas em linhas separadas. Use notação clara e padronizada.
2. **Correção**: Ajuste linguagem coloquial, mantendo rigor matemático.
3. **Precisão**: NUNCA altere valores numéricos, constantes ou unidades de medida.
4. **Legibilidade Visual** (OBRIGATÓRIO):
   - **PARÁGRAFOS CURTOS**: máximo **4-5 linhas visuais** por parágrafo.
   - **FÓRMULAS DESTACADAS**: Use blocos de código ou linhas isoladas para equações.
   - **NEGRITO**: Destaque teoremas, leis e constantes importantes.
   - **ITÁLICO**: Use para variáveis e grandezas físicas.
5. **Formatação Didática**:
   - **Listas numeradas** para resolução passo-a-passo de problemas.
   - **Bullet points** para propriedades, condições e hipóteses.
   - **Marcadores relacionais** como \`→\` ou \`⇒\` para implicações lógicas.

## 🎨 FORMATAÇÃO VISUAL AVANÇADA
Para garantir legibilidade superior:
1. **Após cada definição ou teorema**, quebre o parágrafo.
2. **Use listas numeradas** para demonstrações e resoluções de exercícios.
3. **Use citações recuadas** (\`>\`) para destacar dicas de prova e observações importantes.
4. **Separe visualmente** teoria, exemplos e exercícios com subseções.

## 💎 PILAR 1: RIGOR MATEMÁTICO
> ⚠️ **NUNCA ALTERE** valores, constantes, unidades ou resultados numéricos.
> ✅ **PRESERVE** notação padrão (ex: π, Σ, ∫, ∂, lim).

## 📊 QUADRO-SÍNTESE (OBRIGATÓRIO)
Ao final de CADA tópico principal (## ou ###), faça um fechamento didático com UM quadro-síntese.

1) Adicione um subtítulo de fechamento:
#### 📋 Quadro-síntese — [título do tópico]

2) Em seguida, gere UMA tabela Markdown (sem placeholders):

| Grandeza/Teorema | Fórmula/Definição | Unidade (SI) | Condições de Aplicação | Aplicação Prática |
| :--- | :--- | :--- | :--- | :--- |

**REGRAS CRÍTICAS (não negocie):**
1. **Sem placeholders:** PROIBIDO usar \`"..."\`. Se algo não aparecer, use \`"—"\`.
2. **Precisão:** Fórmulas e unidades devem ser EXATAS.
3. **Concisão:** máximo ~35–45 palavras por célula.
4. **Compatibilidade:** PROIBIDO usar o caractere \`|\` dentro de células.
5. **Posicionamento:** o quadro vem **APENAS AO FINAL** do bloco concluído.

## 🎯 TABELA 2 (QUANDO APLICÁVEL): COMO CAI NA PROVA
Se o bloco contiver dicas de prova, pegadinhas ou exercícios típicos:

#### 🎯 Tabela — Como cai na prova / Exercícios típicos
| Tipo de questão | Abordagem de resolução | Erro comum / pegadinha |
| :--- | :--- | :--- |`
   },
   {
      id: 'preset_ti',
      category: 'Tecnologia',
      name: 'Programação & TI',
      description: 'Formatação otimizada para código, arquitetura e comandos.',
      template: `## ✅ DIRETRIZES DE ESTILO E FORMATAÇÃO VISUAL
1. **Código**: Use blocos de código (\\\`\\\`\\\`) para snippets, comandos de terminal e nomes de arquivos.
2. **Terminologia**: Mantenha termos em inglês (ex: "deploy", "build", "commit") se for padrão da área.
3. **Correção**: Ajuste linguagem coloquial, mantendo precisão técnica.
4. **Legibilidade Visual** (OBRIGATÓRIO):
   - **PARÁGRAFOS CURTOS**: máximo **4-5 linhas visuais** por parágrafo.
   - **BLOCOS DE CÓDIGO**: Use para comandos, configurações e snippets.
   - **NEGRITO**: Destaque conceitos-chave, padrões e boas práticas.
   - **INLINE CODE** (\\\`backticks\\\`): Use para nomes de funções, variáveis, arquivos e comandos inline.
5. **Formatação Didática**:
   - **Listas numeradas** para tutoriais e passos de configuração.
   - **Bullet points** para features, requisitos e opções.
   - **Marcadores relacionais** como \`→\` para fluxos de dados e arquitetura.

## 🎨 FORMATAÇÃO VISUAL AVANÇADA
Para garantir legibilidade superior:
1. **Após cada conceito**, quebre o parágrafo.
2. **Use listas numeradas** para tutoriais e configurações.
3. **Use citações recuadas** (\`>\`) para destacar boas práticas, warnings e dicas.
4. **Separe visualmente** conceitos, exemplos de código e exercícios com subseções.

## � PILAR 1: PRECISÃO TÉCNICA
> ⚠️ **NUNCA ALTERE** comandos, sintaxe, nomes de funções ou configurações.
> ✅ **PRESERVE** termos técnicos em inglês quando for o padrão.

## 📊 QUADRO-SÍNTESE (OBRIGATÓRIO)
Ao final de CADA tópico principal (## ou ###), faça um fechamento didático com UM quadro-síntese.

1) Adicione um subtítulo de fechamento:
#### 📋 Quadro-síntese — [título do tópico]

2) Em seguida, gere UMA tabela Markdown (sem placeholders):

| Comando/Conceito | Função/Definição | Sintaxe/Exemplo | Quando usar | Observações |
| :--- | :--- | :--- | :--- | :--- |

**REGRAS CRÍTICAS (não negocie):**
1. **Sem placeholders:** PROIBIDO usar \`"..."\`. Se algo não aparecer, use \`"—"\`.
2. **Precisão:** Comandos e sintaxe devem ser EXATOS.
3. **Concisão:** máximo ~35–45 palavras por célula.
4. **Compatibilidade:** PROIBIDO usar o caractere \`|\` dentro de células.
5. **Posicionamento:** o quadro vem **APENAS AO FINAL** do bloco concluído.

## 🎯 TABELA 2 (QUANDO APLICÁVEL): CERTIFICAÇÃO / ENTREVISTA
Se o bloco contiver dicas de certificação, entrevista técnica ou "isso cai muito":

#### 🎯 Tabela — Certificação / Entrevista técnica
| Pergunta típica | Resposta correta | Erro comum / pegadinha |
| :--- | :--- | :--- |`
   }
];
