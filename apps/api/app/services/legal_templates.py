"""
Templates de Documentos Jurídicos Brasileiros
Sistema extensível para geração de peças jurídicas padronizadas
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum
from loguru import logger


class DocumentType(str, Enum):
    """Tipos de documentos jurídicos"""
    MANDADO_SEGURANCA = "mandado_seguranca"
    HABEAS_CORPUS = "habeas_corpus"
    RECLAMACAO_TRABALHISTA = "reclamacao_trabalhista"
    DIVORCIO = "divorcio"
    PETICAO_INICIAL = "peticao_inicial"
    CONTESTACAO = "contestacao"
    RECURSO_APELACAO = "recurso_apelacao"
    RECURSO_ESPECIAL = "recurso_especial"
    RECURSO_EXTRAORDINARIO = "recurso_extraordinario"
    AGRAVO_INSTRUMENTO = "agravo_instrumento"
    EMBARGOS_DECLARACAO = "embargos_declaracao"
    PARECER_JURIDICO = "parecer_juridico"
    CONTRATO = "contrato"
    PROCURACAO = "procuracao"
    MEMORANDO = "memorando"
    PETICAO_INTERMEDIARIA = "peticao_intermediaria"
    DEFESA_PREVIA = "defesa_previa"
    ALEGACOES_FINAIS = "alegacoes_finais"
    RAZOES_RECURSAIS = "razoes_recursais"
    CONTRARRAZOES = "contrarrazoes"


class CourtType(str, Enum):
    """Tipos de tribunais"""
    STF = "Supremo Tribunal Federal"
    STJ = "Superior Tribunal de Justiça"
    TST = "Tribunal Superior do Trabalho"
    TSE = "Tribunal Superior Eleitoral"
    STM = "Superior Tribunal Militar"
    TRF = "Tribunal Regional Federal"
    TJ = "Tribunal de Justiça"
    TRT = "Tribunal Regional do Trabalho"
    TRE = "Tribunal Regional Eleitoral"
    VARA = "Vara Judicial"


@dataclass
class TemplateVariable:
    """Variável de template"""
    name: str
    description: str
    required: bool = True
    default: Optional[str] = None
    type: str = "string"  # string, date, number, currency, text


@dataclass
class LegalTemplate:
    """Template de documento jurídico"""
    id: str
    name: str
    document_type: DocumentType
    description: str
    variables: List[TemplateVariable] = field(default_factory=list)
    structure: str = ""
    instructions: str = ""
    example: str = ""
    
    def get_variable_names(self) -> List[str]:
        """Retorna lista de nomes de variáveis"""
        return [v.name for v in self.variables]
    
    def get_required_variables(self) -> List[str]:
        """Retorna variáveis obrigatórias"""
        return [v.name for v in self.variables if v.required]


class LegalTemplateLibrary:
    """
    Biblioteca de templates de documentos jurídicos
    """
    
    def __init__(self):
        self.templates: Dict[str, LegalTemplate] = {}
        self._initialize_templates()
        logger.info(f"Biblioteca de templates inicializada com {len(self.templates)} templates")
    
    def _initialize_templates(self):
        """Inicializa templates padrão"""
        
        # Template: Petição Inicial Cível
        self.templates["peticao_inicial_civel"] = LegalTemplate(
            id="peticao_inicial_civel",
            name="Petição Inicial - Ação Cível",
            document_type=DocumentType.PETICAO_INICIAL,
            description="Template para petição inicial de ação cível",
            variables=[
                TemplateVariable("juizo", "Juízo competente", required=True),
                TemplateVariable("comarca", "Comarca", required=True),
                TemplateVariable("autor_nome", "Nome do autor", required=True),
                TemplateVariable("autor_nacionalidade", "Nacionalidade do autor"),
                TemplateVariable("autor_estado_civil", "Estado civil do autor"),
                TemplateVariable("autor_profissao", "Profissão do autor"),
                TemplateVariable("autor_cpf", "CPF do autor"),
                TemplateVariable("autor_endereco", "Endereço do autor", required=True),
                TemplateVariable("reu_nome", "Nome do réu", required=True),
                TemplateVariable("reu_endereco", "Endereço do réu", required=True),
                TemplateVariable("tipo_acao", "Tipo de ação", required=True),
                TemplateVariable("causa_pedir", "Causa de pedir", required=True, type="text"),
                TemplateVariable("fundamentacao_juridica", "Fundamentação jurídica", required=True, type="text"),
                TemplateVariable("pedidos", "Pedidos", required=True, type="text"),
                TemplateVariable("valor_causa", "Valor da causa", required=True, type="currency"),
            ],
            structure="""
# EXCELENTÍSSIMO SENHOR DOUTOR JUIZ DE DIREITO DA {juizo} DA COMARCA DE {comarca}

{autor_nome}, {autor_nacionalidade}, {autor_estado_civil}, {autor_profissao}, inscrito no CPF sob o nº {autor_cpf}, residente e domiciliado na {autor_endereco}, vem, por meio de seu advogado que esta subscreve, com escritório na {advogado_endereco}, onde recebe intimações, propor

## {tipo_acao}

em face de {reu_nome}, com endereço na {reu_endereco}, pelos fatos e fundamentos a seguir expostos:

## I - DOS FATOS

{causa_pedir}

## II - DO DIREITO

{fundamentacao_juridica}

## III - DOS PEDIDOS

Diante do exposto, requer-se:

{pedidos}

## IV - DO VALOR DA CAUSA

Para os devidos fins, atribui-se à presente causa o valor de {valor_causa}.

Termos em que,
Pede deferimento.

{local}, {data}.

{advogado_nome}
OAB/{advogado_oab_estado} {advogado_oab}
""",
            instructions="""
Instruções para preenchimento:
1. Identifique corretamente o juízo competente
2. Qualifique completamente autor e réu
3. Narre os fatos de forma clara e cronológica
4. Fundamente juridicamente com citação de leis
5. Formule pedidos claros e possíveis
6. Calcule corretamente o valor da causa
""",
            example="Ver documentação para exemplo completo"
        )
        
        # Template: Contestação
        self.templates["contestacao"] = LegalTemplate(
            id="contestacao",
            name="Contestação",
            document_type=DocumentType.CONTESTACAO,
            description="Template para contestação em ação cível",
            variables=[
                TemplateVariable("processo_numero", "Número do processo", required=True),
                TemplateVariable("reu_nome", "Nome do réu", required=True),
                TemplateVariable("autor_nome", "Nome do autor", required=True),
                TemplateVariable("preliminares", "Preliminares", type="text"),
                TemplateVariable("merito", "Mérito da defesa", required=True, type="text"),
                TemplateVariable("provas", "Provas requeridas", type="text"),
            ],
            structure="""
# CONTESTAÇÃO

**Processo nº:** {processo_numero}

**Contestante:** {reu_nome}

**Contestado:** {autor_nome}

## I - PRELIMINARES

{preliminares}

## II - DO MÉRITO

{merito}

## III - DAS PROVAS

{provas}

## IV - DOS PEDIDOS

Ante o exposto, requer-se:

a) O acolhimento das preliminares, com extinção do processo;
b) No mérito, a improcedência total dos pedidos;
c) A condenação do autor ao pagamento de custas e honorários advocatícios.

Termos em que,
Pede deferimento.

{local}, {data}.

{advogado_nome}
OAB/{advogado_oab_estado} {advogado_oab}
"""
        )
        
        # Template: Recurso de Apelação
        self.templates["recurso_apelacao"] = LegalTemplate(
            id="recurso_apelacao",
            name="Recurso de Apelação",
            document_type=DocumentType.RECURSO_APELACAO,
            description="Template para recurso de apelação",
            variables=[
                TemplateVariable("processo_numero", "Número do processo", required=True),
                TemplateVariable("apelante", "Nome do apelante", required=True),
                TemplateVariable("apelado", "Nome do apelado", required=True),
                TemplateVariable("decisao_data", "Data da decisão recorrida", required=True, type="date"),
                TemplateVariable("razoes", "Razões do recurso", required=True, type="text"),
                TemplateVariable("pedido_reforma", "Pedido de reforma", required=True, type="text"),
            ],
            structure="""
# RECURSO DE APELAÇÃO

**Processo nº:** {processo_numero}

**Apelante:** {apelante}

**Apelado:** {apelado}

Inconformado com a r. sentença proferida em {decisao_data}, o apelante vem, tempestivamente, interpor o presente

## RECURSO DE APELAÇÃO

pelos fundamentos de fato e de direito a seguir expostos:

## I - DO CABIMENTO

O presente recurso é tempestivo e se encontra amparado pelo artigo 1.009 do Código de Processo Civil.

## II - DAS RAZÕES DO RECURSO

{razoes}

## III - DO PEDIDO

Diante do exposto, requer-se:

{pedido_reforma}

Termos em que,
Pede provimento.

{local}, {data}.

{advogado_nome}
OAB/{advogado_oab_estado} {advogado_oab}
"""
        )
        
        # Template: Parecer Jurídico
        self.templates["parecer_juridico"] = LegalTemplate(
            id="parecer_juridico",
            name="Parecer Jurídico",
            document_type=DocumentType.PARECER_JURIDICO,
            description="Template para parecer jurídico",
            variables=[
                TemplateVariable("consulente", "Nome do consulente", required=True),
                TemplateVariable("assunto", "Assunto do parecer", required=True),
                TemplateVariable("relatorio", "Relatório dos fatos", required=True, type="text"),
                TemplateVariable("fundamentacao", "Fundamentação jurídica", required=True, type="text"),
                TemplateVariable("conclusao", "Conclusão", required=True, type="text"),
            ],
            structure="""
# PARECER JURÍDICO

**Consulente:** {consulente}

**Assunto:** {assunto}

## I - RELATÓRIO

{relatorio}

## II - FUNDAMENTAÇÃO

{fundamentacao}

## III - CONCLUSÃO

{conclusao}

É o parecer, s.m.j.

{local}, {data}.

{advogado_nome}
OAB/{advogado_oab_estado} {advogado_oab}
"""
        )
        
        # Template: Procuração
        self.templates["procuracao"] = LegalTemplate(
            id="procuracao",
            name="Procuração Ad Judicia",
            document_type=DocumentType.PROCURACAO,
            description="Template para procuração judicial",
            variables=[
                TemplateVariable("outorgante_nome", "Nome do outorgante", required=True),
                TemplateVariable("outorgante_cpf", "CPF do outorgante", required=True),
                TemplateVariable("outorgante_endereco", "Endereço do outorgante", required=True),
                TemplateVariable("outorgado_nome", "Nome do advogado", required=True),
                TemplateVariable("outorgado_oab", "OAB do advogado", required=True),
                TemplateVariable("poderes", "Poderes conferidos", type="text"),
            ],
            structure="""
# PROCURAÇÃO AD JUDICIA

**Outorgante:** {outorgante_nome}, inscrito no CPF sob o nº {outorgante_cpf}, residente e domiciliado na {outorgante_endereco}.

**Outorgado:** {outorgado_nome}, advogado inscrito na OAB/{advogado_oab_estado} sob o nº {outorgado_oab}.

**Poderes:** O(A) outorgante confere ao(à) outorgado(a) poderes para o foro em geral, com as cláusulas ad judicia, podendo propor as ações competentes e defendê-lo nas contrárias, seguindo umas e outras até final decisão, conferindo-lhe, ainda, poderes especiais para {poderes}.

{local}, {data}.

_________________________
{outorgante_nome}
Outorgante
"""
        )
        
        # Template: Contrato de Prestação de Serviços
        self.templates["contrato_prestacao_servicos"] = LegalTemplate(
            id="contrato_prestacao_servicos",
            name="Contrato de Prestação de Serviços",
            document_type=DocumentType.CONTRATO,
            description="Template para contrato de prestação de serviços",
            variables=[
                TemplateVariable("contratante_nome", "Nome do contratante", required=True),
                TemplateVariable("contratante_cpf_cnpj", "CPF/CNPJ do contratante", required=True),
                TemplateVariable("contratante_endereco", "Endereço do contratante", required=True),
                TemplateVariable("contratado_nome", "Nome do contratado", required=True),
                TemplateVariable("contratado_cpf_cnpj", "CPF/CNPJ do contratado", required=True),
                TemplateVariable("contratado_endereco", "Endereço do contratado", required=True),
                TemplateVariable("objeto", "Objeto do contrato", required=True, type="text"),
                TemplateVariable("valor", "Valor do contrato", required=True, type="currency"),
                TemplateVariable("prazo", "Prazo de vigência", required=True),
                TemplateVariable("forma_pagamento", "Forma de pagamento", required=True),
            ],
            structure="""
# CONTRATO DE PRESTAÇÃO DE SERVIÇOS

**CONTRATANTE:** {contratante_nome}, inscrito no CPF/CNPJ sob o nº {contratante_cpf_cnpj}, com endereço na {contratante_endereco}.

**CONTRATADO:** {contratado_nome}, inscrito no CPF/CNPJ sob o nº {contratado_cpf_cnpj}, com endereço na {contratado_endereco}.

As partes acima identificadas têm, entre si, justo e acertado o presente Contrato de Prestação de Serviços, que se regerá pelas cláusulas seguintes:

## CLÁUSULA PRIMEIRA - DO OBJETO

{objeto}

## CLÁUSULA SEGUNDA - DO VALOR

O contratante pagará ao contratado o valor total de {valor} pelos serviços prestados.

## CLÁUSULA TERCEIRA - DO PAGAMENTO

{forma_pagamento}

## CLÁUSULA QUARTA - DO PRAZO

O presente contrato terá vigência de {prazo}, a contar da data de sua assinatura.

## CLÁUSULA QUINTA - DAS OBRIGAÇÕES DO CONTRATADO

São obrigações do contratado:
a) Executar os serviços com qualidade e no prazo estabelecido;
b) Responsabilizar-se por todos os encargos trabalhistas e fiscais;
c) Manter sigilo sobre informações confidenciais.

## CLÁUSULA SEXTA - DAS OBRIGAÇÕES DO CONTRATANTE

São obrigações do contratante:
a) Efetuar o pagamento nos termos pactuados;
b) Fornecer as informações necessárias para execução dos serviços;
c) Comunicar eventuais irregularidades na prestação dos serviços.

## CLÁUSULA SÉTIMA - DA RESCISÃO

O presente contrato poderá ser rescindido por qualquer das partes mediante comunicação prévia de 30 (trinta) dias.

## CLÁUSULA OITAVA - DO FORO

Fica eleito o foro da Comarca de {comarca} para dirimir quaisquer dúvidas ou controvérsias oriundas do presente contrato.

E, por estarem justas e contratadas, as partes assinam o presente instrumento em 2 (duas) vias de igual teor e forma.

{local}, {data}.

_________________________          _________________________
{contratante_nome}                 {contratado_nome}
Contratante                        Contratado

Testemunhas:

_________________________          _________________________
Nome:                              Nome:
CPF:                               CPF:
"""
        )

        # Template: Mandado de Segurança
        self.templates["mandado_seguranca"] = LegalTemplate(
            id="mandado_seguranca",
            name="Mandado de Segurança",
            document_type=DocumentType.MANDADO_SEGURANCA,
            description="Template para Mandado de Segurança Individual (Lei 12.016/09)",
            variables=[
                TemplateVariable("juizo", "Juízo competente", required=True),
                TemplateVariable("impetrante", "Nome do impetrante", required=True),
                TemplateVariable("impetrante_qualificacao", "Qualificação do impetrante", required=True),
                TemplateVariable("autoridade_coatora", "Autoridade Coatora", required=True),
                TemplateVariable("pessoa_juridica", "Pessoa Jurídica a que se vincula", required=True),
                TemplateVariable("ato_coator", "Ato ilegal impugnado", required=True, type="text"),
                TemplateVariable("direito_liquido", "Fundamentação do Direito Líquido e Certo", required=True, type="text"),
                TemplateVariable("liminar", "Fundamentos da Liminar", required=False, type="text"),
                TemplateVariable("pedidos", "Pedidos", required=True, type="text"),
                TemplateVariable("valor_causa", "Valor da causa", required=True, type="currency"),
            ],
            structure="""
# EXCELENTÍSSIMO SENHOR DOUTOR JUIZ DE DIREITO DA {juizo}

**IMPETRANTE:** {impetrante}, {impetrante_qualificacao}, por seu advogado infra-assinado, vem, respeitosamente, à presença de Vossa Excelência, impetrar

## MANDADO DE SEGURANÇA COM PEDIDO LIMINAR

contra ato ilegal praticado pelo **{autoridade_coatora}**, vinculado à {pessoa_juridica}, pelos fatos e fundamentos a seguir:

## I - DOS FATOS E DO ATO COATOR

{ato_coator}

## II - DO DIREITO LÍQUIDO E CERTO

{direito_liquido}

## III - DO CABIMENTO DA MEDIDA LIMINAR

{liminar}

## IV - DOS PEDIDOS

Diante do exposto, requer:

1. A concessão da medida liminar para suspender o ato coator;
2. A notificação da autoridade coatora para prestar informações;
3. A ciência do órgão de representação judicial da pessoa jurídica interessada;
4. A oitiva do Ministério Público;
5. Ao final, a concessão definitiva da segurança.

Dá-se à causa o valor de {valor_causa}.

Termos em que,
Pede deferimento.

{local}, {data}.

{advogado_nome}
OAB/{advogado_oab_estado} {advogado_oab}
"""
        )

        # Template: Habeas Corpus
        self.templates["habeas_corpus"] = LegalTemplate(
            id="habeas_corpus",
            name="Habeas Corpus",
            document_type=DocumentType.HABEAS_CORPUS,
            description="Template para Habeas Corpus Liberatório",
            variables=[
                TemplateVariable("tribunal", "Tribunal competente", required=True),
                TemplateVariable("impetrante", "Nome do impetrante (advogado)", required=True),
                TemplateVariable("paciente", "Nome do paciente", required=True),
                TemplateVariable("autoridade_coatora", "Autoridade Coatora", required=True),
                TemplateVariable("fatos", "Narrativa da coação ilegal", required=True, type="text"),
                TemplateVariable("fundamentacao", "Fundamentação jurídica", required=True, type="text"),
                TemplateVariable("liminar", "Fundamentos da Liminar", required=False, type="text"),
            ],
            structure="""
# EXCELENTÍSSIMO SENHOR DESEMBARGADOR PRESIDENTE DO {tribunal}

**IMPETRANTE:** {impetrante}, advogado, inscrito na OAB sob o nº {advogado_oab}, vem, respeitosamente, impetrar a presente ordem de

## HABEAS CORPUS COM PEDIDO LIMINAR

em favor de **{paciente}**, qualificado nos autos, contra ato ilegal praticado pelo {autoridade_coatora}, pelas razões a seguir:

## I - DOS FATOS

{fatos}

## II - DO DIREITO E DA COAÇÃO ILEGAL

{fundamentacao}

## III - DA LIMINAR

{liminar}

## IV - DOS PEDIDOS

Ante o exposto, requer:

1. O deferimento da medida liminar para imediata soltura do paciente;
2. A notificação da autoridade coatora para informações;
3. A concessão definitiva da ordem de Habeas Corpus.

Termos em que,
Pede deferimento.

{local}, {data}.

{advogado_nome}
OAB/{advogado_oab_estado} {advogado_oab}
"""
        )

        # Template: Reclamação Trabalhista
        self.templates["reclamacao_trabalhista"] = LegalTemplate(
            id="reclamacao_trabalhista",
            name="Reclamação Trabalhista",
            document_type=DocumentType.RECLAMACAO_TRABALHISTA,
            description="Template para Reclamação Trabalhista (CLT)",
            variables=[
                TemplateVariable("vara", "Vara do Trabalho", required=True),
                TemplateVariable("reclamante", "Nome do Reclamante", required=True),
                TemplateVariable("reclamante_qualificacao", "Qualificação completa", required=True),
                TemplateVariable("reclamada", "Nome da Reclamada", required=True),
                TemplateVariable("reclamada_endereco", "Endereço da Reclamada", required=True),
                TemplateVariable("contrato", "Dados do Contrato (Admissão, Demissão, Salário)", required=True, type="text"),
                TemplateVariable("fatos_direitos", "Fatos e Fundamentos", required=True, type="text"),
                TemplateVariable("pedidos_liquidos", "Pedidos Liquidados", required=True, type="text"),
                TemplateVariable("valor_causa", "Valor da Causa", required=True, type="currency"),
            ],
            structure="""
# EXCELENTÍSSIMO SENHOR DOUTOR JUIZ DA {vara} VARA DO TRABALHO DE {comarca}

**RECLAMANTE:** {reclamante}, {reclamante_qualificacao}, por seu advogado, vem propor

## RECLAMAÇÃO TRABALHISTA

em face de **{reclamada}**, com endereço na {reclamada_endereco}, pelos motivos a seguir:

## I - DO CONTRATO DE TRABALHO

{contrato}

## II - DO DIREITO

{fatos_direitos}

## III - DOS PEDIDOS

Diante do exposto, requer a condenação da Reclamada ao pagamento das seguintes verbas:

{pedidos_liquidos}

Requer ainda os benefícios da Justiça Gratuita e honorários advocatícios.

Dá-se à causa o valor de {valor_causa}.

Termos em que,
Pede deferimento.

{local}, {data}.

{advogado_nome}
OAB/{advogado_oab_estado} {advogado_oab}
"""
        )

        # Template: Divórcio Consensual
        self.templates["divorcio_consensual"] = LegalTemplate(
            id="divorcio_consensual",
            name="Divórcio Consensual",
            document_type=DocumentType.DIVORCIO,
            description="Template para Divórcio Consensual Judicial",
            variables=[
                TemplateVariable("juizo", "Vara de Família", required=True),
                TemplateVariable("conjuge1", "Nome do Cônjuge 1", required=True),
                TemplateVariable("conjuge2", "Nome do Cônjuge 2", required=True),
                TemplateVariable("casamento", "Dados do Casamento", required=True),
                TemplateVariable("filhos", "Filhos e Guarda", required=True, type="text"),
                TemplateVariable("bens", "Partilha de Bens", required=True, type="text"),
                TemplateVariable("alimentos", "Pensão Alimentícia", required=True, type="text"),
            ],
            structure="""
# EXCELENTÍSSIMO SENHOR DOUTOR JUIZ DE DIREITO DA {juizo} VARA DE FAMÍLIA DA COMARCA DE {comarca}

**{conjuge1}**, qualificação completa, e
**{conjuge2}**, qualificação completa,

vêm, por seu advogado comum, requerer a homologação de

## DIVÓRCIO CONSENSUAL

nos termos a seguir:

## I - DO CASAMENTO

{casamento}

## II - DOS FILHOS E DA GUARDA

{filhos}

## III - DOS ALIMENTOS

{alimentos}

## IV - DA PARTILHA DE BENS

{bens}

## V - DOS PEDIDOS

Ante o exposto, requerem:

1. A concessão da gratuidade de justiça;
2. A intimação do Ministério Público;
3. A homologação do presente acordo de divórcio em todos os seus termos;
4. A expedição de mandado de averbação ao Cartório de Registro Civil.

Dá-se à causa o valor de R$ 1.000,00 (para efeitos fiscais).

Termos em que,
Pedem deferimento.

{local}, {data}.

{advogado_nome}
OAB/{advogado_oab_estado} {advogado_oab}

_____________________
{conjuge1}

_____________________
{conjuge2}
"""
        )
    
    def get_template(self, template_id: str) -> Optional[LegalTemplate]:
        """Obtém template por ID"""
        return self.templates.get(template_id)
    
    def list_templates(
        self,
        document_type: Optional[DocumentType] = None
    ) -> List[LegalTemplate]:
        """Lista templates disponíveis, opcionalmente filtrados por tipo"""
        templates = list(self.templates.values())
        
        if document_type:
            templates = [t for t in templates if t.document_type == document_type]
        
        return templates
    
    def render_template(
        self,
        template_id: str,
        variables: Dict[str, Any],
        validate: bool = True
    ) -> str:
        """
        Renderiza template com variáveis fornecidas
        
        Args:
            template_id: ID do template
            variables: Dicionário com valores das variáveis
            validate: Se deve validar variáveis obrigatórias
        
        Returns:
            Documento renderizado
        """
        template = self.get_template(template_id)
        
        if not template:
            raise ValueError(f"Template não encontrado: {template_id}")
        
        # Validar variáveis obrigatórias
        if validate:
            missing = []
            for var in template.variables:
                if var.required and var.name not in variables:
                    # Usar valor padrão se disponível
                    if var.default:
                        variables[var.name] = var.default
                    else:
                        missing.append(var.name)
            
            if missing:
                raise ValueError(f"Variáveis obrigatórias faltando: {', '.join(missing)}")
        
        # Renderizar template
        try:
            rendered = template.structure.format(**variables)
            return rendered
        except KeyError as e:
            raise ValueError(f"Variável não fornecida: {e}")
    
    def get_template_info(self, template_id: str) -> Dict[str, Any]:
        """Retorna informações completas sobre um template"""
        template = self.get_template(template_id)
        
        if not template:
            raise ValueError(f"Template não encontrado: {template_id}")
        
        return {
            "id": template.id,
            "name": template.name,
            "document_type": template.document_type.value,
            "description": template.description,
            "variables": [
                {
                    "name": v.name,
                    "description": v.description,
                    "required": v.required,
                    "type": v.type,
                    "default": v.default
                }
                for v in template.variables
            ],
            "instructions": template.instructions,
            "example": template.example
        }


# Instância global da biblioteca
legal_template_library = LegalTemplateLibrary()

