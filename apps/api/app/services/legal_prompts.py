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

