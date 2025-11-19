"""
Templates de documentos jurídicos predefinidos
"""

from typing import List, Dict, Any
from datetime import datetime


class DocumentTemplates:
    """
    Biblioteca de templates de documentos jurídicos
    com campos dinâmicos e substituição automática
    """
    
    @staticmethod
    def get_petition_template() -> Dict[str, Any]:
        """Template de petição inicial"""
        return {
            "id": "petition_001",
            "name": "Petição Inicial - Modelo Geral",
            "document_type": "petition",
            "description": "Modelo genérico de petição inicial",
            "content_template": """EXCELENTÍSSIMO SENHOR DOUTOR JUIZ DE DIREITO DA {{vara}} VARA {{comarca}}

{{client_name}}, {{client_qualification}}, residente e domiciliado(a) na {{client_address}}, por intermédio de seu advogado que esta subscreve (doc. anexo), com escritório profissional na {{lawyer_address}}, onde recebe intimações, vem, respeitosamente, à presença de Vossa Excelência, propor

**{{action_type}}**

em face de {{defendant_name}}, {{defendant_qualification}}, com endereço na {{defendant_address}}, pelos fatos e fundamentos jurídicos a seguir expostos:

## I - DOS FATOS

{{facts}}

## II - DO DIREITO

{{legal_basis}}

## III - DO PEDIDO

Diante do exposto, requer-se:

{{requests}}

Atribui-se à causa o valor de R$ {{value}} ({{value_written}}).

Termos em que,
Pede deferimento.

{{city}}, {{date}}.

{{user_name}}
{{user_oab}}
""",
            "variables": [
                {
                    "name": "vara",
                    "type": "text",
                    "label": "Número da Vara",
                    "required": True
                },
                {
                    "name": "comarca",
                    "type": "text",
                    "label": "Comarca",
                    "required": True
                },
                {
                    "name": "client_name",
                    "type": "text",
                    "label": "Nome do Cliente",
                    "required": True
                },
                {
                    "name": "client_qualification",
                    "type": "text",
                    "label": "Qualificação do Cliente",
                    "required": True
                },
                {
                    "name": "client_address",
                    "type": "text",
                    "label": "Endereço do Cliente",
                    "required": True
                },
                {
                    "name": "lawyer_address",
                    "type": "user_field",
                    "label": "Endereço do Advogado",
                    "user_field_mapping": "address",
                    "required": False
                },
                {
                    "name": "action_type",
                    "type": "select",
                    "label": "Tipo de Ação",
                    "options": [
                        "AÇÃO DE COBRANÇA",
                        "AÇÃO DE INDENIZAÇÃO",
                        "AÇÃO DE DESPEJO",
                        "AÇÃO REVISIONAL",
                        "AÇÃO DECLARATÓRIA"
                    ],
                    "required": True
                },
                {
                    "name": "defendant_name",
                    "type": "text",
                    "label": "Nome do Réu",
                    "required": True
                },
                {
                    "name": "defendant_qualification",
                    "type": "text",
                    "label": "Qualificação do Réu",
                    "required": True
                },
                {
                    "name": "defendant_address",
                    "type": "text",
                    "label": "Endereço do Réu",
                    "required": True
                },
                {
                    "name": "facts",
                    "type": "text",
                    "label": "Fatos (deixe em branco para geração por IA)",
                    "required": False
                },
                {
                    "name": "legal_basis",
                    "type": "text",
                    "label": "Fundamentos Jurídicos (deixe em branco para geração por IA)",
                    "required": False
                },
                {
                    "name": "requests",
                    "type": "text",
                    "label": "Pedidos",
                    "required": True
                },
                {
                    "name": "value",
                    "type": "number",
                    "label": "Valor da Causa",
                    "required": True
                },
                {
                    "name": "value_written",
                    "type": "text",
                    "label": "Valor por Extenso",
                    "required": True
                },
                {
                    "name": "city",
                    "type": "text",
                    "label": "Cidade",
                    "required": True
                },
                {
                    "name": "date",
                    "type": "date",
                    "label": "Data",
                    "default_value": datetime.now().strftime("%d de %B de %Y"),
                    "required": True
                },
                {
                    "name": "user_name",
                    "type": "user_field",
                    "label": "Nome do Advogado",
                    "user_field_mapping": "name",
                    "required": True
                },
                {
                    "name": "user_oab",
                    "type": "user_field",
                    "label": "OAB",
                    "user_field_mapping": "oab_full",
                    "required": True
                }
            ],
            "require_signature": True
        }
    
    @staticmethod
    def get_contract_template() -> Dict[str, Any]:
        """Template de contrato"""
        return {
            "id": "contract_001",
            "name": "Contrato de Prestação de Serviços",
            "document_type": "contract",
            "description": "Modelo de contrato de prestação de serviços",
            "content_template": """**CONTRATO DE PRESTAÇÃO DE SERVIÇOS**

Por este instrumento particular de contrato, de um lado:

**CONTRATANTE**: {{client_name}}, {{client_type}}, inscrito(a) no {{client_doc_type}} sob o nº {{client_doc}}, com sede/residência em {{client_address}}, doravante denominado(a) CONTRATANTE;

**CONTRATADO**: {{contractor_name}}, {{contractor_type}}, inscrito(a) no {{contractor_doc_type}} sob o nº {{contractor_doc}}, com sede/residência em {{contractor_address}}, doravante denominado(a) CONTRATADO;

As partes acima identificadas têm, entre si, justo e acertado o presente Contrato de Prestação de Serviços, que se regerá pelas cláusulas seguintes e pelas condições descritas no presente.

## CLÁUSULA PRIMEIRA - DO OBJETO

O presente contrato tem como objeto a prestação de serviços de {{service_description}}.

## CLÁUSULA SEGUNDA - DO PRAZO

O prazo de vigência do presente contrato é de {{contract_duration}}, com início em {{start_date}} e término em {{end_date}}.

## CLÁUSULA TERCEIRA - DO VALOR E FORMA DE PAGAMENTO

Pelos serviços prestados, o CONTRATANTE pagará ao CONTRATADO o valor total de R$ {{value}} ({{value_written}}), que será pago da seguinte forma: {{payment_terms}}.

## CLÁUSULA QUARTA - DAS OBRIGAÇÕES DO CONTRATADO

São obrigações do CONTRATADO:
{{contractor_obligations}}

## CLÁUSULA QUINTA - DAS OBRIGAÇÕES DO CONTRATANTE

São obrigações do CONTRATANTE:
{{client_obligations}}

## CLÁUSULA SEXTA - DA RESCISÃO

O presente contrato poderá ser rescindido por qualquer das partes, mediante comunicação prévia de {{notice_days}} dias.

## CLÁUSULA SÉTIMA - DO FORO

Fica eleito o foro da Comarca de {{jurisdiction}} para dirimir quaisquer questões oriundas do presente contrato.

E, por estarem assim justos e contratados, firmam o presente instrumento em 2 (duas) vias de igual teor, na presença das testemunhas abaixo.

{{city}}, {{date}}.

_____________________________
{{client_name}}
CONTRATANTE

_____________________________
{{contractor_name}}
CONTRATADO

**TESTEMUNHAS:**

1. _____________________________
   Nome:
   CPF:

2. _____________________________
   Nome:
   CPF:
""",
            "variables": [
                {
                    "name": "client_name",
                    "type": "text",
                    "label": "Nome do Contratante",
                    "required": True
                },
                {
                    "name": "client_type",
                    "type": "select",
                    "label": "Tipo do Contratante",
                    "options": ["pessoa física", "pessoa jurídica"],
                    "required": True
                },
                {
                    "name": "client_doc_type",
                    "type": "select",
                    "label": "Documento do Contratante",
                    "options": ["CPF", "CNPJ"],
                    "required": True
                },
                {
                    "name": "client_doc",
                    "type": "text",
                    "label": "Número do Documento",
                    "required": True
                },
                {
                    "name": "client_address",
                    "type": "text",
                    "label": "Endereço do Contratante",
                    "required": True
                },
                {
                    "name": "contractor_name",
                    "type": "user_field",
                    "label": "Nome do Contratado",
                    "user_field_mapping": "name",
                    "required": True
                },
                {
                    "name": "contractor_type",
                    "type": "text",
                    "label": "Tipo do Contratado",
                    "default_value": "pessoa física",
                    "required": True
                },
                {
                    "name": "contractor_doc_type",
                    "type": "text",
                    "label": "Documento do Contratado",
                    "default_value": "CPF",
                    "required": True
                },
                {
                    "name": "contractor_doc",
                    "type": "user_field",
                    "label": "CPF do Contratado",
                    "user_field_mapping": "cpf",
                    "required": False
                },
                {
                    "name": "contractor_address",
                    "type": "text",
                    "label": "Endereço do Contratado",
                    "required": True
                },
                {
                    "name": "service_description",
                    "type": "text",
                    "label": "Descrição dos Serviços",
                    "required": True
                },
                {
                    "name": "contract_duration",
                    "type": "text",
                    "label": "Duração do Contrato",
                    "required": True
                },
                {
                    "name": "start_date",
                    "type": "date",
                    "label": "Data de Início",
                    "required": True
                },
                {
                    "name": "end_date",
                    "type": "date",
                    "label": "Data de Término",
                    "required": True
                },
                {
                    "name": "value",
                    "type": "number",
                    "label": "Valor Total",
                    "required": True
                },
                {
                    "name": "value_written",
                    "type": "text",
                    "label": "Valor por Extenso",
                    "required": True
                },
                {
                    "name": "payment_terms",
                    "type": "text",
                    "label": "Forma de Pagamento",
                    "required": True
                },
                {
                    "name": "contractor_obligations",
                    "type": "text",
                    "label": "Obrigações do Contratado",
                    "required": True
                },
                {
                    "name": "client_obligations",
                    "type": "text",
                    "label": "Obrigações do Contratante",
                    "required": True
                },
                {
                    "name": "notice_days",
                    "type": "number",
                    "label": "Dias de Aviso Prévio",
                    "default_value": 30,
                    "required": True
                },
                {
                    "name": "jurisdiction",
                    "type": "text",
                    "label": "Foro/Comarca",
                    "required": True
                },
                {
                    "name": "city",
                    "type": "text",
                    "label": "Cidade",
                    "required": True
                },
                {
                    "name": "date",
                    "type": "date",
                    "label": "Data",
                    "default_value": datetime.now().strftime("%d de %B de %Y"),
                    "required": True
                }
            ],
            "require_signature": True
        }
    
    @staticmethod
    def get_opinion_template() -> Dict[str, Any]:
        """Template de parecer jurídico"""
        return {
            "id": "opinion_001",
            "name": "Parecer Jurídico",
            "document_type": "opinion",
            "description": "Modelo de parecer jurídico",
            "content_template": """**PARECER JURÍDICO**

**Interessado**: {{client_name}}
**Assunto**: {{subject}}
**Data**: {{date}}

## I - CONSULTA

{{consultation}}

## II - ANÁLISE

{{analysis}}

## III - FUNDAMENTAÇÃO JURÍDICA

{{legal_basis}}

## IV - CONCLUSÃO

{{conclusion}}

É o parecer, s.m.j.

{{city}}, {{date}}.

{{user_name}}
{{user_oab}}
""",
            "variables": [
                {
                    "name": "client_name",
                    "type": "text",
                    "label": "Nome do Interessado",
                    "required": True
                },
                {
                    "name": "subject",
                    "type": "text",
                    "label": "Assunto",
                    "required": True
                },
                {
                    "name": "consultation",
                    "type": "text",
                    "label": "Consulta (deixe em branco para IA)",
                    "required": False
                },
                {
                    "name": "analysis",
                    "type": "text",
                    "label": "Análise (deixe em branco para IA)",
                    "required": False
                },
                {
                    "name": "legal_basis",
                    "type": "text",
                    "label": "Fundamentação (deixe em branco para IA)",
                    "required": False
                },
                {
                    "name": "conclusion",
                    "type": "text",
                    "label": "Conclusão (deixe em branco para IA)",
                    "required": False
                },
                {
                    "name": "city",
                    "type": "text",
                    "label": "Cidade",
                    "required": True
                },
                {
                    "name": "date",
                    "type": "date",
                    "label": "Data",
                    "default_value": datetime.now().strftime("%d de %B de %Y"),
                    "required": True
                },
                {
                    "name": "user_name",
                    "type": "user_field",
                    "label": "Nome",
                    "user_field_mapping": "name",
                    "required": True
                },
                {
                    "name": "user_oab",
                    "type": "user_field",
                    "label": "OAB",
                    "user_field_mapping": "oab_full",
                    "required": True
                }
            ],
            "require_signature": True
        }
    
    @staticmethod
    def list_all_templates() -> List[Dict[str, Any]]:
        """Retorna lista de todos os templates disponíveis"""
        return [
            DocumentTemplates.get_petition_template(),
            DocumentTemplates.get_contract_template(),
            DocumentTemplates.get_opinion_template(),
        ]
    
    @staticmethod
    def get_template_by_id(template_id: str) -> Dict[str, Any]:
        """Busca template por ID"""
        templates = DocumentTemplates.list_all_templates()
        for template in templates:
            if template["id"] == template_id:
                return template
        return None

