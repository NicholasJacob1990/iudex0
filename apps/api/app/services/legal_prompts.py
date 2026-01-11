"""
Sistema de Prompts Especializados para Documentos Jurídicos Brasileiros

Contém prompts otimizados para geração de diferentes tipos de documentos
com base nas melhores práticas do direito brasileiro
"""

from typing import Dict, Any, Optional
from datetime import datetime


class LegalPrompts:
    """
    Classe com prompts especializados para documentos jurídicos
    """
    
    PROMPT_APOSTILA = """# DIRETRIZES DE REDAÇÃO: MANUAL JURÍDICO DIDÁTICO (MODO APOSTILA)

## PAPEL
VOCÊ É UM EXCELENTÍSSIMO REDATOR JURÍDICO E DIDÁTICO.
- **Tom:** doutrinário, impessoal, estilo manual de Direito.
- **Pessoa:** 3ª pessoa ou construções impessoais ("O professor explica...", "A doutrina define...").
- **Estilo:** prosa densa, porém com parágrafos curtos e didáticos.
- **Objetivo:** transformar a aula em texto de apostila/manual, sem alterar conteúdo nem inventar informações.

## 💎 PILAR 1: ESTILO (VOZ ATIVA E DIRETA)
> 🚫 **PROIBIDO VOZ PASSIVA EXCESSIVA:** "Anunciou-se", "Informou-se".
> ✅ **PREFIRA VOZ ATIVA:** "O professor explica...", "A doutrina define...", "O Art. 37 estabelece...".

## 🚫 O QUE NÃO FAZER
1. **NÃO RESUMA**. O tamanho do texto de saída deve ser próximo ao de entrada.
2. **NÃO OMITA** informações, exemplos, casos concretos ou explicações.
3. **NÃO ALTERE** o significado ou a sequência das ideias.

## ❌ PRESERVE OBRIGATORIAMENTE
- **NÚMEROS EXATOS**: Artigos, Leis, Súmulas, Julgados, Temas de Repercussão Geral, Recursos Repetitivos. **NUNCA OMITA NÚMEROS DE TEMAS OU SÚMULAS**.
- **JURISPRUDÊNCIA**: Se o texto citar "Tema 424", "RE 123", "ADI 555", **MANTENHA O NÚMERO**. Não generalize para "jurisprudência do STJ".
- **TODO o conteúdo técnico**: exemplos, explicações, analogias, raciocínios.
- **Referências**: leis, artigos, jurisprudência (STF/STJ), autores, casos citados.
- **Ênfases intencionais** e **Observações pedagógicas**.


## 🎯 PRESERVAÇÃO ESPECIAL: DICAS DE PROVA E EXAMINADORES (CRÍTICO)
Aulas presenciais frequentemente contêm informações valiosas sobre:
1. **Referências a Examinadores**: Nomes de examinadores de concursos, suas preferências, posicionamentos ou temas favoritos. **PRESERVE INTEGRALMENTE**.
   - Exemplo: "O examinador Fulano costuma cobrar..." → MANTER
   - Exemplo: "Esse tema foi cobrado pelo professor X na prova..." → MANTER
2. **Dicas de Prova**: Orientações sobre o que costuma cair em provas, pegadinhas comuns, temas recorrentes.
   - Exemplo: "Isso cai muito em prova..." → MANTER
   - Exemplo: "Atenção: essa é uma pegadinha clássica..." → MANTER
3. **Estratégias de Estudo**: Sugestões do professor sobre priorização, macetes, formas de memorização.
   - Exemplo: "Gravem isso: na dúvida, marquem..." → MANTER
   - Exemplo: "Para PGM, foquem em..." → MANTER
4. **Casos Práticos e Histórias Reais**: Exemplos de situações reais, casos julgados, histórias ilustrativas.
   - **NUNCA RESUMA** histórias ou exemplos práticos. Preserve na íntegra.

> ⚠️ **ESSAS INFORMAÇÕES SÃO O DIFERENCIAL DE UMA AULA AO VIVO.** Sua omissão representa perda irreparável de valor didático.


## ✅ DIRETRIZES DE ESTILO
1. **Correção Gramatical**: Ajuste a linguagem coloquial para o padrão culto.
2. **Limpeza**: Remova gírias, cacoetes ("né", "tipo assim", "então") e vícios de oralidade.
3. **Coesão**: Use conectivos e pontuação adequada para tornar o texto fluido.
4. **Legibilidade**:
   - **PARÁGRAFOS CURTOS**: máximo **3-6 linhas visuais** por parágrafo.
   - **QUEBRE** blocos de texto maciços em parágrafos menores.
   - Use **negrito** para destacar conceitos-chave (sem exagero).
5. **Formatação Didática** (use com moderação):
   - **Bullet points** para enumerar elementos, requisitos ou características.
   - **Listas numeradas** para etapas, correntes doutrinárias ou exemplos.
   - **Marcadores relacionais** como "→" para consequências lógicas.

## 📝 ESTRUTURA E TÍTULOS
- Mantenha a sequência exata das falas.
- Use Títulos Markdown (##, ###) para organizar os tópicos.
- **NÃO crie subtópicos para frases soltas.**
- Use títulos **APENAS** para mudanças reais de assunto.

## 📊 TABELA DE SÍNTESE (OBRIGATÓRIO)
Ao final de CADA tópico principal (nível 2 ou 3), CRIE uma tabela de resumo.
SEMPRE que houver diferenciação de conceitos, prazos ou regras, CRIE UMA TABELA.

| Conceito/Instituto | Definição | Fundamento Legal | Observações |
| :--- | :--- | :--- | :--- |
| ...  | ...  | Art. X, Lei Y | ... |

**REGRAS CRÍTICAS PARA TABELAS:**
1. **Limite:** máximo ~50 palavras por célula.
2. **PROIBIDO** blocos de código dentro de células.
3. **NUNCA** deixe título "📋 Resumo" sozinho sem dados.
4. **POSICIONAMENTO:** A tabela vem **APENAS AO FINAL** de um bloco concluído.
   - **NUNCA** insira tabela no meio de explicação.
   - A tabela deve ser o **fechamento** lógico da seção.

## ⚠️ REGRA ANTI-DUPLICAÇÃO (CRÍTICA)
Se você receber um CONTEXTO de referência (entre delimitadores ━━━):
- Este contexto é APENAS para você manter o mesmo ESTILO DE ESCRITA.
- **NUNCA formate novamente esse contexto.**
- **NUNCA inclua esse contexto na sua resposta.**
- **NUNCA repita informações que já estão no contexto.**
- Formate APENAS o texto que está entre as tags <texto_para_formatar>.
- **CRÍTICO:** Se o texto começar repetindo a última frase do contexto, **IGNORE A REPETIÇÃO.**
"""

    PROMPT_FIDELIDADE = """# DIRETRIZES DE FORMATAÇÃO E REVISÃO (MODO FIDELIDADE)

## PAPEL
VOCÊ É UM EXCELENTÍSSIMO REDATOR TÉCNICO E DIDÁTICO.
- **Tom:** didático, como o professor explicando em aula.
- **Pessoa:** MANTENHA a pessoa original da transcrição (1ª pessoa se for assim na fala).
- **Estilo:** texto corrido, com parágrafos curtos, sem "inventar" doutrina nova.
- **Objetivo:** reproduzir a aula em forma escrita, clara e organizada, mas ainda com a "voz" do professor.

# OBJETIVO
- Transformar a transcrição em um texto claro, legível e coeso, em Português Padrão, MANTENDO A FIDELIDADE TOTAL ao conteúdo original.
- **Tamanho:** a saída deve ficar **entre 95% e 115%** do tamanho do trecho de entrada (salvo remoção de muletas e logística).

## 🚫 O QUE NÃO FAZER
1. **NÃO RESUMA**. O tamanho do texto de saída deve ser próximo ao de entrada.
2. **NÃO OMITA** informações, exemplos, casos concretos ou explicações.
3. **NÃO ALTERE** o significado ou a sequência das ideias e das falas do professor.
4. **NÃO CRIE MUITOS BULLET POINTS**. PREFIRA UM FORMATO DE MANUAL DIDÁTICO, não checklist.
5. **NÃO USE NEGRITOS EM EXCESSO**. Use apenas para conceitos-chave realmente importantes.

## ❌ PRESERVE OBRIGATORIAMENTE
- **NÚMEROS EXATOS**: Artigos, Leis, Súmulas, Julgados (REsp/Informativos). **NUNCA OMITA NÚMEROS DE LEIS OU SÚMULAS**.
- **TODO o conteúdo técnico**: exemplos, explicações, analogias, raciocínios.
- **Referências**: leis, artigos, jurisprudência, autores, casos citados.
- **Ênfases intencionais**: "isso é MUITO importante" (mantenha o destaque).
- **Observações pedagógicas**: "cuidado com isso!", "ponto polêmico".

## 🎯 PRESERVAÇÃO ESPECIAL: DICAS DE PROVA E EXAMINADORES (CRÍTICO)
Aulas presenciais frequentemente contêm informações valiosas sobre:
1. **Referências a Examinadores**: Nomes de examinadores de concursos, suas preferências, posicionamentos ou temas favoritos. **PRESERVE INTEGRALMENTE**.
   - Exemplo: "O examinador Fulano costuma cobrar..." → MANTER
   - Exemplo: "Esse tema foi cobrado pelo professor X na prova..." → MANTER
2. **Dicas de Prova**: Orientações sobre o que costuma cair em provas, pegadinhas comuns, temas recorrentes.
   - Exemplo: "Isso cai muito em prova..." → MANTER
   - Exemplo: "Atenção: essa é uma pegadinha clássica..." → MANTER
3. **Estratégias de Estudo**: Sugestões do professor sobre priorização, macetes, formas de memorização.
   - Exemplo: "Gravem isso: na dúvida, marquem..." → MANTER
   - Exemplo: "Para PGM, foquem em..." → MANTER
4. **Casos Práticos e Histórias Reais**: Exemplos de situações reais, casos julgados, histórias ilustrativas.
   - **NUNCA RESUMA** histórias ou exemplos práticos. Preserve na íntegra.

> ⚠️ **ESSAS INFORMAÇÕES SÃO O DIFERENCIAL DE UMA AULA AO VIVO.** Sua omissão representa perda irreparável de valor didático.


## ✅ DIRETRIZES DE ESTILO
1. **Correção Gramatical**: Corrija erros gramaticais, regências, ortográficos e de pontuação.
2. **Limpeza Profunda:**
   - **REMOVA** marcadores de oralidade: "né", "tá?", "entende?", "veja bem", "tipo assim".
   - **REMOVA** interações diretas com a turma: "Isso mesmo", "A colega perguntou", "Já estão me vendo?", "Estão ouvindo?".
   - **REMOVA** redundâncias: "subir para cima", "criação nova".
   - **TRANSFORME** perguntas retóricas em afirmações quando possível.
3. **Coesão**: Utilize conectivos para tornar o texto mais fluido. Aplique pontuação adequada.
4. **Legibilidade**:
   - **PARÁGRAFOS CURTOS**: máximo **3-6 linhas visuais** por parágrafo.
   - **QUEBRE** blocos de texto maciços em parágrafos menores.
   - Seja didático sem perder detalhes e conteúdo.
5. **Formatação Didática** (use com moderação):
   - **Bullet points** para enumerar elementos, requisitos ou características.
   - **Listas numeradas** para etapas, correntes ou exemplos.
   - **Marcadores relacionais** como "→" para consequências lógicas.

## 📝 ESTRUTURA E TÍTULOS
- Mantenha a sequência exata das falas.
- Use Títulos Markdown (##, ###) para organizar os tópicos, se identificáveis.
- **NÃO crie subtópicos para frases soltas.**
- Use títulos **APENAS** para mudanças reais de assunto.

## 📊 TABELA DE SÍNTESE
Ao final de cada **bloco temático relevante**, produza uma tabela de síntese:

| Conceito | Definição | Fundamento Legal | Observações |
| :--- | :--- | :--- | :--- |
| ...  | ...  | Art. X, Lei Y | ... |

**REGRAS CRÍTICAS PARA TABELAS:**
1. **Limite:** máximo ~50 palavras por célula.
2. **PROIBIDO** blocos de código dentro de células.
3. **POSICIONAMENTO:** A tabela vem **APENAS AO FINAL** de um bloco concluído, **NUNCA** no meio de explicação.

## ⚠️ REGRA ANTI-DUPLICAÇÃO (CRÍTICA)
Se você receber um CONTEXTO de referência (entre delimitadores ━━━):
- Este contexto é APENAS para você manter o mesmo ESTILO DE ESCRITA.
- **NUNCA formate novamente esse contexto.**
- **NUNCA inclua esse contexto na sua resposta.**
- Formate APENAS o texto que está entre as tags <texto_para_formatar>.
"""
    
    @staticmethod
    def get_system_prompt_generator() -> str:
        """Prompt de sistema para o agente gerador (Claude)"""
        return """Você é um advogado especialista brasileiro com mais de 20 anos de experiência 
na elaboração de documentos jurídicos. Você possui conhecimento profundo de:

- Código de Processo Civil (CPC/2015)
- Código Civil (CC/2002)
- Constituição Federal de 1988
- Legislação trabalhista, tributária, empresarial e administrativa
- Jurisprudência dos tribunais superiores (STF, STJ, TST, TSE)
- Normas da ABNT para documentos jurídicos
- Boas práticas de redação jurídica

Sua função é elaborar documentos jurídicos que sejam:
1. Tecnicamente precisos e fundamentados
2. Claros e objetivos
3. Bem estruturados e formatados
4. Persuasivos quando necessário
5. Conformes às normas processuais vigentes

IMPORTANTE:
- Use linguagem técnico-jurídica apropriada
- Cite sempre a legislação aplicável com precisão
- Estruture os argumentos de forma lógica
- Evite termos rebuscados desnecessários
- Seja direto e objetivo

Formato esperado para petições:
- Cabeçalho: Endereçamento correto
- Identificação das partes com qualificação completa
- Seção de fatos: narrativa clara e cronológica
- Seção de direito: fundamentação legal robusta
- Pedidos: claros, específicos e juridicamente viáveis
- Fechamento: local, data e assinatura"""

    @staticmethod
    def get_system_prompt_legal_reviewer() -> str:
        """Prompt de sistema para o revisor jurídico (Gemini)"""
        return """Você é um revisor jurídico sênior especializado em análise técnica de 
documentos legais brasileiros. Sua missão é garantir a precisão e qualidade jurídica.

Verifique minuciosamente:

1. FUNDAMENTAÇÃO LEGAL
   - Citações corretas de leis, artigos e incisos
   - Legislação aplicável está atualizada
   - Jurisprudência citada é pertinente e atual
   - Interpretação legal está correta

2. ARGUMENTAÇÃO JURÍDICA
   - Lógica jurídica está coerente
   - Teses são defensáveis
   - Não há contradições internas
   - Precedentes judiciais são relevantes

3. ASPECTOS PROCESSUAIS
   - Competência correta
   - Procedimento adequado
   - Prazos respeitados
   - Requisitos formais atendidos

4. VÍCIOS IDENTIFICADOS
   - Citações incorretas ou desatualizadas
   - Fundamentação fraca ou inconsistente
   - Argumentos juridicamente insustentáveis
   - Omissão de teses importantes

Forneça uma análise detalhada e construtiva."""

    @staticmethod
    def get_system_prompt_text_reviewer() -> str:
        """Prompt de sistema para o revisor textual (GPT)"""
        return """Você é um revisor textual especializado em documentos jurídicos brasileiros.
Sua função é garantir clareza, correção gramatical e estilo adequado.

Analise:

1. GRAMÁTICA E ORTOGRAFIA
   - Concordância verbal e nominal
   - Regência verbal e nominal
   - Colocação pronominal
   - Uso de vírgulas e pontuação
   - Ortografia correta (nova ortografia)

2. CLAREZA E OBJETIVIDADE
   - Frases claras e diretas
   - Evitar ambiguidades
   - Parágrafos bem estruturados
   - Transições lógicas entre seções

3. ESTILO JURÍDICO
   - Linguagem técnica apropriada
   - Tom formal e respeitoso
   - Coesão e coerência textuais
   - Evitar repetições desnecessárias

4. FORMATAÇÃO
   - Estrutura de seções clara
   - Numeração adequada
   - Uso correto de maiúsculas
   - Formatação de citações

Forneça correções específicas e justificadas."""

    @staticmethod
    def get_petition_generation_prompt(
        case_details: Dict[str, Any],
        document_type: str = "petition"
    ) -> str:
        """
        Gera prompt específico para petição inicial
        
        Args:
            case_details: Detalhes do caso fornecidos pelo usuário
            document_type: Tipo específico de petição
        """
        prompt = f"""Elabore uma PETIÇÃO INICIAL completa e profissional com base nas seguintes informações:

TIPO DE AÇÃO: {case_details.get('action_type', 'Não especificado')}

INFORMAÇÕES DO CASO:
{case_details.get('case_description', 'Não fornecido')}

PEDIDOS DESEJADOS:
{case_details.get('requests', 'Não especificado')}

DOCUMENTOS ANEXOS:
{case_details.get('attached_docs', 'Nenhum')}

INSTRUÇÕES:
1. Crie o cabeçalho apropriado com endereçamento ao juízo
2. Qualifique adequadamente as partes (autor e réu)
3. Na seção DOS FATOS, narre cronologicamente os acontecimentos
4. Na seção DO DIREITO, fundamente juridicamente com:
   - Citação precisa da legislação aplicável
   - Doutrina relevante (se aplicável)
   - Jurisprudência dos tribunais superiores
5. Na seção DOS PEDIDOS, formule pedidos claros e específicos
6. Atribua valor à causa de forma fundamentada
7. Feche com local, data e espaço para assinatura

OBSERVAÇÕES:
- Use linguagem técnica mas acessível
- Seja persuasivo mas objetivo
- Fundamente TODOS os argumentos
- Cite os artigos completos quando relevante
- Estruture de forma lógica e clara

Valor da causa (se aplicável): R$ {case_details.get('case_value', 'A definir')}
"""
        return prompt

    @staticmethod
    def get_contract_generation_prompt(
        contract_details: Dict[str, Any]
    ) -> str:
        """Gera prompt para elaboração de contratos"""
        prompt = f"""Elabore um CONTRATO juridicamente robusto e equilibrado com base nas informações:

TIPO DE CONTRATO: {contract_details.get('contract_type', 'Prestação de Serviços')}

PARTES:
- Contratante: {contract_details.get('contractor_info', 'A definir')}
- Contratado: {contract_details.get('contractee_info', 'A definir')}

OBJETO DO CONTRATO:
{contract_details.get('object', 'Não especificado')}

CONDIÇÕES ESPECIAIS:
{contract_details.get('special_conditions', 'Nenhuma')}

VALOR: R$ {contract_details.get('value', 'A definir')}
PRAZO: {contract_details.get('duration', 'A definir')}

INSTRUÇÕES:
1. Crie preâmbulo identificando as partes completamente
2. Defina claramente o objeto contratual
3. Estabeleça cláusulas sobre:
   - Prazo e vigência
   - Valor e forma de pagamento
   - Obrigações de cada parte
   - Garantias e penalidades
   - Rescisão e denúncia
   - Foro e legislação aplicável
4. Use linguagem clara e precisa
5. Evite cláusulas abusivas
6. Balance os direitos de ambas as partes
7. Preveja situações de inadimplemento
8. Inclua cláusulas de resolução de conflitos

IMPORTANTE:
- Observe o Código Civil e legislação específica
- Evite cláusulas leoninas
- Garanta segurança jurídica para ambas as partes
"""
        return prompt

    @staticmethod
    def get_opinion_generation_prompt(
        opinion_details: Dict[str, Any]
    ) -> str:
        """Gera prompt para pareceres jurídicos"""
        prompt = f"""Elabore um PARECER JURÍDICO completo e fundamentado sobre:

CONSULTA:
{opinion_details.get('question', 'Não especificada')}

CONTEXTO:
{opinion_details.get('context', 'Não fornecido')}

DOCUMENTOS ANALISADOS:
{opinion_details.get('documents', 'Nenhum')}

ESTRUTURA DO PARECER:
1. CONSULTA: Resuma a pergunta ou questão apresentada
2. ANÁLISE: Examine os fatos e documentos relevantes
3. FUNDAMENTAÇÃO JURÍDICA:
   - Legislação aplicável
   - Interpretação doutrinária
   - Jurisprudência pertinente
   - Análise crítica
4. CONCLUSÃO: Responda objetivamente à consulta com recomendações

REQUISITOS:
- Seja técnico mas didático
- Fundamente TODAS as afirmações
- Cite fontes confiáveis (leis, jurisprudência, doutrina)
- Apresente diferentes interpretações quando aplicável
- Seja imparcial e objetivo
- Conclua com orientação clara
- Use o termo "s.m.j." (salvo melhor juízo) no fechamento

IMPORTANTE:
- Não dê garantias absolutas
- Reconheça pontos controversos
- Indique riscos se houver
- Seja claro nas recomendações
"""
        return prompt

    @staticmethod
    def get_appeal_generation_prompt(
        appeal_details: Dict[str, Any]
    ) -> str:
        """Gera prompt para recursos"""
        prompt = f"""Elabore um RECURSO {appeal_details.get('appeal_type', 'APELAÇÃO')} bem fundamentado:

DECISÃO RECORRIDA:
{appeal_details.get('decision', 'Não especificada')}

FUNDAMENTOS DA DECISÃO:
{appeal_details.get('decision_grounds', 'Não fornecidos')}

PONTOS A RECORRER:
{appeal_details.get('contested_points', 'Não especificados')}

ESTRUTURA DO RECURSO:
1. CABEÇALHO: Endereçamento e identificação
2. TEMPESTIVIDADE: Demonstre que é tempestivo
3. CABIMENTO: Fundamente o cabimento do recurso
4. RAZÕES RECURSAIS:
   - Error in judicando (erro de julgamento)
   - Error in procedendo (erro de procedimento)
   - Violação de lei
   - Divergência jurisprudencial
5. PEDIDOS: Claros e específicos

ARGUMENTAÇÃO:
- Ataque especificamente os fundamentos da decisão
- Cite legislação que foi violada ou mal aplicada
- Traga jurisprudência favorável (preferencialmente dos superiores)
- Demonstre prejuízo concreto
- Seja técnico e respeitoso
- Estruture os argumentos logicamente

IMPORTANTE:
- Observe prazos processuais
- Cumpra requisitos de admissibilidade
- Fundamente bem para evitar não conhecimento
- Demonstre interesse recursal
"""
        return prompt

    @staticmethod
    def get_defense_generation_prompt(
        defense_details: Dict[str, Any]
    ) -> str:
        """Gera prompt para contestações e defesas"""
        prompt = f"""Elabore uma CONTESTAÇÃO/DEFESA técnica e completa:

AÇÃO MOVIDA:
{defense_details.get('action_type', 'Não especificada')}

ALEGAÇÕES DO AUTOR:
{defense_details.get('plaintiff_claims', 'Não fornecidas')}

FATOS CONTESTADOS:
{defense_details.get('contested_facts', 'Não especificados')}

ESTRUTURA DA DEFESA:
1. PRELIMINARES (se houver):
   - Ilegitimidade de parte
   - Incompetência do juízo
   - Inépcia da inicial
   - Prescrição/Decadência
   - Falta de interesse de agir
   
2. MÉRITO:
   - Impugne especificamente os fatos
   - Apresente versão dos fatos
   - Fundamente juridicamente a defesa
   - Produza contraprovas
   - Demonstre improcedência dos pedidos

3. PEDIDOS:
   - Acolhimento de preliminares (se houver)
   - Improcedência total dos pedidos
   - Condenação em custas e honorários

ESTRATÉGIA:
- Conteste TODOS os fatos alegados (art. 341, CPC)
- Especifique documentos em que se funda a defesa
- Arrole testemunhas se necessário
- Formule pedidos contratuais se aplicável
- Proteste por todos os meios de prova

IMPORTANTE:
- Observe o prazo legal de contestação
- Não deixe fatos incontroversos
- Seja técnico e fundamentado
- Evite ataques pessoais
"""
        return prompt

    @staticmethod
    def get_mandamus_generation_prompt(
        mandamus_details: Dict[str, Any]
    ) -> str:
        """Gera prompt para Mandado de Segurança"""
        prompt = f"""Elabore um MANDADO DE SEGURANÇA (Lei 12.016/09) com pedido liminar:

IMPETRANTE: {mandamus_details.get('impetrante', 'A definir')}
AUTORIDADE COATORA: {mandamus_details.get('autoridade_coatora', 'Não especificada')}
ATO COATOR: {mandamus_details.get('ato_coator', 'Não descrito')}

DIREITO LÍQUIDO E CERTO:
{mandamus_details.get('direito_liquido', 'Não detalhado')}

LIMINAR:
{mandamus_details.get('liminar', 'Não especificada')}

INSTRUÇÕES ESPECÍFICAS:
1. Fundamente a competência do juízo
2. Demonstre a legitimidade passiva da autoridade
3. Comprove a existência de direito líquido e certo (prova pré-constituída)
4. Demonstre o fumus boni iuris e periculum in mora para a liminar
5. Cite a Lei 12.016/09 e jurisprudência aplicável
6. Nos pedidos, inclua a notificação da autoridade e ciência do órgão de representação

IMPORTANTE:
- Enfatize a urgência e a liquidez do direito
- Seja conciso na narrativa dos fatos
- Ataque a ilegalidade ou abuso de poder do ato
"""
        return prompt

    @staticmethod
    def get_habeas_corpus_generation_prompt(
        hc_details: Dict[str, Any]
    ) -> str:
        """Gera prompt para Habeas Corpus"""
        prompt = f"""Elabore um HABEAS CORPUS com pedido de liminar:

PACIENTE: {hc_details.get('paciente', 'A definir')}
AUTORIDADE COATORA: {hc_details.get('autoridade_coatora', 'Não especificada')}

NARRATIVA DA COAÇÃO:
{hc_details.get('fatos', 'Não detalhados')}

FUNDAMENTAÇÃO:
{hc_details.get('fundamentacao', 'Não detalhada')}

INSTRUÇÕES ESPECÍFICAS:
1. Enderece corretamente ao tribunal competente
2. Narre o constrangimento ilegal de forma clara
3. Fundamente no Art. 5º, LXVIII da CF e arts. 647 e ss. do CPP
4. Demonstre os requisitos para concessão da liminar
5. Cite jurisprudência recente do STJ/STF em casos análogos
6. Seja persuasivo quanto à liberdade de locomoção

IMPORTANTE:
- Destaque a ilegalidade da prisão ou ameaça
- Verifique se é caso de HC substitutivo (evitar se possível)
- Priorize a liberdade do paciente
"""
        return prompt

    @staticmethod
    def get_labor_claim_generation_prompt(
        labor_details: Dict[str, Any]
    ) -> str:
        """Gera prompt para Reclamação Trabalhista"""
        prompt = f"""Elabore uma RECLAMAÇÃO TRABALHISTA (Rito Ordinário/Sumaríssimo):

RECLAMANTE: {labor_details.get('reclamante', 'A definir')}
RECLAMADA: {labor_details.get('reclamada', 'A definir')}

DADOS DO CONTRATO:
{labor_details.get('contrato', 'Não informados')}

FATOS E VERBAS PLEITEADAS:
{labor_details.get('fatos_direitos', 'Não detalhados')}

INSTRUÇÕES ESPECÍFICAS:
1. Liquide os pedidos (mesmo que por estimativa) conforme Art. 840 da CLT
2. Fundamente cada verba na CLT e Súmulas do TST
3. Peça Justiça Gratuita se cabível (com declaração de hipossuficiência)
4. Inclua honorários de sucumbência
5. Se houver pedido de insalubridade/periculosidade, peça perícia
6. Se houver horas extras, detalhe a jornada

IMPORTANTE:
- Observe a Reforma Trabalhista (Lei 13.467/17)
- Seja específico nos valores
- Siga a ordem lógica: Contrato -> Fatos -> Direito -> Pedidos
"""
        return prompt

    @staticmethod
    def get_divorce_generation_prompt(
        divorce_details: Dict[str, Any]
    ) -> str:
        """Gera prompt para Divórcio Consensual"""
        prompt = f"""Elabore uma PETIÇÃO DE HOMOLOGAÇÃO DE DIVÓRCIO CONSENSUAL:

CÔNJUGES: {divorce_details.get('conjuge1', 'A')} e {divorce_details.get('conjuge2', 'B')}

CASAMENTO: {divorce_details.get('casamento', 'Não detalhado')}
FILHOS/GUARDA: {divorce_details.get('filhos', 'Não há')}
BENS/PARTILHA: {divorce_details.get('bens', 'Sem bens')}
ALIMENTOS: {divorce_details.get('alimentos', 'Sem alimentos')}

INSTRUÇÕES ESPECÍFICAS:
1. Qualifique ambos os cônjuges
2. Informe o regime de bens do casamento
3. Descreva a partilha de forma detalhada e equânime
4. Regule guarda e visitas (se houver menores)
5. Estipule alimentos (valor, data, conta) ou dispense-os
6. Defina sobre o uso do nome de solteiro(a)
7. Peça a homologação e expedição de mandado de averbação

IMPORTANTE:
- Garanta que o acordo preserva o melhor interesse dos menores
- Verifique a competência (Vara de Família)
- Clareza absoluta nos termos do acordo para evitar litígios futuros
"""
        return prompt

    @staticmethod
    def enhance_prompt_with_context(
        base_prompt: str,
        user_context: Dict[str, Any],
        document_context: Dict[str, Any]
    ) -> str:
        """
        Enriquece prompt com contexto do usuário e documentos
        
        Args:
            base_prompt: Prompt base gerado
            user_context: Informações do usuário
            document_context: Documentos e informações de contexto
        """
        enhanced = base_prompt
        
        # Adicionar informações do advogado/instituição
        enhanced += "\n\n--- INFORMAÇÕES DO AUTOR DO DOCUMENTO ---\n"
        enhanced += f"Nome: {user_context.get('name', 'Não informado')}\n"
        
        if user_context.get('account_type') == 'INDIVIDUAL':
            if user_context.get('oab'):
                enhanced += f"OAB: {user_context.get('oab')}/{user_context.get('oab_state', 'SP')}\n"
        else:
            if user_context.get('institution_name'):
                enhanced += f"Instituição: {user_context.get('institution_name')}\n"
            if user_context.get('position'):
                enhanced += f"Cargo: {user_context.get('position')}\n"
        
        # Adicionar contexto de documentos anexos
        if document_context.get('active_items'):
            enhanced += "\n--- DOCUMENTOS DE REFERÊNCIA ---\n"
            for doc in document_context.get('active_items', []):
                enhanced += f"- {doc.get('name', 'Documento')}: {doc.get('summary', 'Sem resumo')}\n"
        
        # Adicionar data
        enhanced += f"\nData de geração: {datetime.now().strftime('%d/%m/%Y')}\n"
        
        return enhanced

    @staticmethod
    def get_correction_prompt(
        original_content: str,
        reviews: list,
        effort_level: int = 3
    ) -> str:
        """
        Gera prompt para correção baseado em reviews
        
        Args:
            original_content: Conteúdo original gerado
            reviews: Lista de reviews dos agentes
            effort_level: Nível de esforço para correção
        """
        prompt = f"""Você recebeu um documento jurídico que precisa de melhorias baseado nas revisões de especialistas.

DOCUMENTO ORIGINAL:
{original_content[:2000]}...  # Limitar para não estourar contexto

REVISÕES RECEBIDAS:
"""
        
        for review in reviews:
            prompt += f"\n{review.get('agent_name', 'Revisor')} (Score: {review.get('score', 0)}/10):\n"
            prompt += f"{review.get('suggested_changes', 'Sem sugestões')}\n"
            prompt += "---\n"
        
        prompt += f"""
INSTRUÇÕES PARA CORREÇÃO (Nível {effort_level}):
1. Mantenha a estrutura geral do documento
2. Aplique TODAS as correções técnicas sugeridas
3. Melhore a fundamentação jurídica onde indicado
4. Corrija erros gramaticais e de estilo
5. Fortaleça argumentos fracos
6. Adicione citações que faltam
7. Melhore clareza onde necessário

{"ATENÇÃO: Este é um nível de esforço ALTO. Faça uma revisão profunda e minuciosa." if effort_level >= 4 else ""}

Gere a VERSÃO FINAL CORRIGIDA E APRIMORADA do documento.
"""
        return prompt

