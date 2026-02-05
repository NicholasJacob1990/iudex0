"""
Templates pre-construidos de Review Table para o direito brasileiro.

Cada template define colunas de extracao com prompts especializados.
Sao carregados como seed no banco com is_system=True.

Templates disponiveis:
1. Contrato de Trabalho (trabalhista) — 15 colunas
2. Contrato de Locacao (imobiliario) — 14 colunas
3. Contrato de Prestacao de Servicos (civil) — 12 colunas
4. Contrato de Compra e Venda (civil) — 13 colunas
5. Contratos de Prestacao de Servicos de TI (ti) — 9 colunas
6. Due Diligence — Sociedades (societario) — 7 colunas
7. Contratos de Franquia (empresarial) — 7 colunas
"""

from typing import Any, Dict, List


TEMPLATES: List[Dict[str, Any]] = [
    # -----------------------------------------------------------------------
    # 1. Contrato de Trabalho
    # -----------------------------------------------------------------------
    {
        "name": "Contrato de Trabalho",
        "description": (
            "Extrai informacoes completas de contratos individuais de trabalho: "
            "partes, identificacao, cargo, remuneracao, jornada, prazo, beneficios "
            "e clausulas restritivas. Ideal para analise em massa de contratos CLT."
        ),
        "area": "trabalhista",
        "columns": [
            {
                "name": "Empregador",
                "type": "text",
                "extraction_prompt": (
                    "Extraia o nome completo da empresa empregadora (razao social "
                    "ou nome fantasia) conforme consta no contrato de trabalho. "
                    "Se houver razao social e nome fantasia, prefira a razao social."
                ),
            },
            {
                "name": "Empregado",
                "type": "text",
                "extraction_prompt": (
                    "Extraia o nome completo do empregado/colaborador contratado "
                    "conforme consta no contrato de trabalho."
                ),
            },
            {
                "name": "CNPJ",
                "type": "text",
                "extraction_prompt": (
                    "Extraia o numero do CNPJ da empresa empregadora. "
                    "Formato esperado: XX.XXX.XXX/XXXX-XX. "
                    "Se nao houver CNPJ, indique 'Nao encontrado'."
                ),
            },
            {
                "name": "CPF",
                "type": "text",
                "extraction_prompt": (
                    "Extraia o numero do CPF do empregado. "
                    "Formato esperado: XXX.XXX.XXX-XX. "
                    "Se nao houver CPF, indique 'Nao encontrado'."
                ),
            },
            {
                "name": "Cargo/Funcao",
                "type": "text",
                "extraction_prompt": (
                    "Extraia o cargo, funcao ou posicao do empregado conforme "
                    "descrito no contrato de trabalho. Inclua o departamento ou "
                    "setor se mencionado."
                ),
            },
            {
                "name": "Remuneracao",
                "type": "currency",
                "extraction_prompt": (
                    "Extraia o valor da remuneracao mensal em reais (R$). "
                    "Inclua salario base. Se houver composicao variavel "
                    "(base + comissao + gratificacao), extraia o valor total "
                    "mensal previsto ou o valor base se o total nao for claro."
                ),
            },
            {
                "name": "Jornada de Trabalho",
                "type": "text",
                "extraction_prompt": (
                    "Extraia a jornada de trabalho conforme definida no contrato: "
                    "carga horaria semanal (ex: 44h), horario diario "
                    "(ex: 8h as 17h), dias da semana, regime de escala "
                    "(ex: 12x36), e se ha previsao de hora extra ou banco de horas."
                ),
            },
            {
                "name": "Data de Inicio",
                "type": "date",
                "extraction_prompt": (
                    "Extraia a data de inicio do contrato de trabalho, tambem "
                    "referida como data de admissao ou data de inicio da prestacao "
                    "de servicos. Formato: DD/MM/AAAA."
                ),
            },
            {
                "name": "Prazo",
                "type": "text",
                "extraction_prompt": (
                    "Identifique se o contrato de trabalho e por prazo determinado "
                    "ou indeterminado. Se determinado, extraia o prazo exato "
                    "(ex: 90 dias, 12 meses) e a data de termino prevista."
                ),
            },
            {
                "name": "Periodo de Experiencia",
                "type": "text",
                "extraction_prompt": (
                    "Extraia o periodo de experiencia previsto no contrato. "
                    "Informe a duracao (ex: 45 dias, 90 dias) e se ha previsao "
                    "de prorrogacao. Se nao houver clausula de experiencia, "
                    "indique 'Nao previsto'."
                ),
            },
            {
                "name": "Beneficios",
                "type": "verbatim",
                "extraction_prompt": (
                    "Extraia a lista completa de beneficios oferecidos ao empregado "
                    "conforme consta no contrato: vale-transporte, vale-refeicao, "
                    "vale-alimentacao, plano de saude, plano odontologico, "
                    "seguro de vida, PLR, auxilio-creche, auxilio-educacao, etc. "
                    "Transcreva literalmente como mencionado no documento."
                ),
            },
            {
                "name": "Clausula de Nao-Concorrencia",
                "type": "boolean",
                "extraction_prompt": (
                    "O contrato possui clausula de nao-concorrencia, "
                    "nao-competicao ou restricao de atividades apos o termino "
                    "do vinculo? Responda 'Sim' ou 'Nao'. "
                    "Considere clausulas que restrinjam o empregado de trabalhar "
                    "em empresas concorrentes apos a rescisao."
                ),
            },
            {
                "name": "Clausula de Confidencialidade",
                "type": "boolean",
                "extraction_prompt": (
                    "O contrato possui clausula de confidencialidade, sigilo "
                    "ou NDA (non-disclosure agreement)? Responda 'Sim' ou 'Nao'. "
                    "Considere clausulas que obriguem o empregado a manter "
                    "sigilo sobre informacoes da empresa."
                ),
            },
            {
                "name": "Foro",
                "type": "text",
                "extraction_prompt": (
                    "Extraia o foro de eleicao para resolucao de disputas "
                    "conforme clausula de foro do contrato. Normalmente "
                    "corresponde a comarca da prestacao dos servicos ou "
                    "da sede da empresa."
                ),
            },
            {
                "name": "Multa Rescisoria",
                "type": "text",
                "extraction_prompt": (
                    "Extraia informacoes sobre multa rescisoria ou penalidade "
                    "por rescisao antecipada prevista no contrato. Inclua "
                    "valor, percentual ou base de calculo. Se nao houver, "
                    "indique 'Nao prevista'."
                ),
            },
        ],
    },
    # -----------------------------------------------------------------------
    # 2. Contrato de Locacao
    # -----------------------------------------------------------------------
    {
        "name": "Contrato de Locacao",
        "description": (
            "Extrai dados completos de contratos de locacao de imoveis: "
            "partes, imovel, valor, reajuste, prazo, garantias, finalidade "
            "e responsabilidades. Aplicavel a locacoes residenciais e comerciais."
        ),
        "area": "imobiliario",
        "columns": [
            {
                "name": "Locador",
                "type": "text",
                "extraction_prompt": (
                    "Extraia o nome completo do locador (proprietario do imovel "
                    "ou quem o representa). Se pessoa juridica, extraia a razao "
                    "social. Se houver mais de um locador, liste todos."
                ),
            },
            {
                "name": "Locatario",
                "type": "text",
                "extraction_prompt": (
                    "Extraia o nome completo do locatario (inquilino). "
                    "Se pessoa juridica, extraia a razao social. "
                    "Se houver mais de um locatario, liste todos."
                ),
            },
            {
                "name": "Endereco do Imovel",
                "type": "text",
                "extraction_prompt": (
                    "Extraia o endereco completo do imovel objeto da locacao: "
                    "rua/avenida, numero, complemento, bairro, cidade, estado "
                    "e CEP. Inclua matricula do imovel se mencionada."
                ),
            },
            {
                "name": "Valor do Aluguel",
                "type": "currency",
                "extraction_prompt": (
                    "Extraia o valor mensal do aluguel em reais (R$). "
                    "Se houver valores diferentes para periodos distintos "
                    "(ex: carencia, escalonamento), extraia o valor principal "
                    "e mencione a variacao."
                ),
            },
            {
                "name": "Indice de Reajuste",
                "type": "text",
                "extraction_prompt": (
                    "Extraia o indice de correcao monetaria/reajuste anual "
                    "do aluguel. Indices comuns: IGP-M, IPCA, INPC, IPC-FIPE. "
                    "Informe tambem se ha clausula de reajuste alternativo."
                ),
            },
            {
                "name": "Periodicidade do Reajuste",
                "type": "text",
                "extraction_prompt": (
                    "Extraia a periodicidade do reajuste do aluguel "
                    "(ex: anual, a cada 12 meses). Informe a data-base "
                    "do reajuste se mencionada."
                ),
            },
            {
                "name": "Prazo da Locacao",
                "type": "text",
                "extraction_prompt": (
                    "Extraia o prazo total de vigencia do contrato de locacao "
                    "(ex: 30 meses, 36 meses, 5 anos). Informe tambem se ha "
                    "clausula de renovacao automatica."
                ),
            },
            {
                "name": "Data de Inicio",
                "type": "date",
                "extraction_prompt": (
                    "Extraia a data de inicio da locacao. Pode ser referida "
                    "como data de inicio da vigencia, data de entrega das "
                    "chaves ou inicio do contrato. Formato: DD/MM/AAAA."
                ),
            },
            {
                "name": "Caucao/Garantia",
                "type": "text",
                "extraction_prompt": (
                    "Extraia informacoes sobre a garantia locaticia: tipo "
                    "(caucao em dinheiro, fianca, seguro-fianca, titulo de "
                    "capitalizacao, cessao fiduciaria), valor ou quantidade "
                    "de alugueis dados como garantia."
                ),
            },
            {
                "name": "Tipo de Garantia",
                "type": "text",
                "extraction_prompt": (
                    "Identifique especificamente o tipo de garantia locaticia "
                    "utilizada: 'Caucao em dinheiro', 'Fianca', "
                    "'Seguro-fianca', 'Titulo de capitalizacao' ou "
                    "'Cessao fiduciaria'. Se nao houver garantia, "
                    "indique 'Sem garantia'."
                ),
            },
            {
                "name": "Finalidade",
                "type": "text",
                "extraction_prompt": (
                    "Extraia a finalidade ou destinacao do imovel conforme "
                    "previsto no contrato. Classifique como: 'Residencial', "
                    "'Comercial', 'Industrial', 'Misto' ou outra finalidade "
                    "especifica mencionada (ex: escritorio, clinica, loja)."
                ),
            },
            {
                "name": "Responsavel por IPTU",
                "type": "text",
                "extraction_prompt": (
                    "Identifique quem e o responsavel pelo pagamento do IPTU "
                    "(Imposto Predial e Territorial Urbano) conforme previsto "
                    "no contrato: 'Locador', 'Locatario' ou 'Proporcional'. "
                    "Mencione se ha rateio ou isencao."
                ),
            },
            {
                "name": "Responsavel por Condominio",
                "type": "text",
                "extraction_prompt": (
                    "Identifique quem e o responsavel pelo pagamento das "
                    "despesas condominiais: 'Locador', 'Locatario' ou "
                    "'Proporcional'. Diferencie entre taxa ordinaria e "
                    "extraordinaria de condominio se mencionado."
                ),
            },
            {
                "name": "Foro",
                "type": "text",
                "extraction_prompt": (
                    "Extraia o foro de eleicao para resolucao de disputas "
                    "decorrentes do contrato de locacao. Normalmente e a "
                    "comarca onde se situa o imovel."
                ),
            },
        ],
    },
    # -----------------------------------------------------------------------
    # 3. Contrato de Prestacao de Servicos
    # -----------------------------------------------------------------------
    {
        "name": "Contrato de Prestacao de Servicos",
        "description": (
            "Extrai dados-chave de contratos de prestacao de servicos em geral: "
            "partes, objeto, valores, prazos, penalidades e clausulas especiais. "
            "Aplicavel a servicos profissionais, consultorias e terceirizacao."
        ),
        "area": "civil",
        "columns": [
            {
                "name": "Contratante",
                "type": "text",
                "extraction_prompt": (
                    "Extraia o nome completo do contratante (tomador dos "
                    "servicos). Se pessoa juridica, extraia a razao social. "
                    "Se pessoa fisica, extraia o nome completo."
                ),
            },
            {
                "name": "Contratado",
                "type": "text",
                "extraction_prompt": (
                    "Extraia o nome completo do contratado (prestador dos "
                    "servicos). Se pessoa juridica, extraia a razao social. "
                    "Se pessoa fisica, extraia o nome completo."
                ),
            },
            {
                "name": "CNPJ/CPF",
                "type": "text",
                "extraction_prompt": (
                    "Extraia o CNPJ ou CPF do contratado (prestador dos "
                    "servicos). Formato CNPJ: XX.XXX.XXX/XXXX-XX. "
                    "Formato CPF: XXX.XXX.XXX-XX. Se ambas as partes "
                    "tiverem documentos, extraia do contratado."
                ),
            },
            {
                "name": "Objeto do Servico",
                "type": "verbatim",
                "extraction_prompt": (
                    "Extraia a descricao completa do objeto do contrato, "
                    "ou seja, quais servicos serao prestados. Transcreva "
                    "literalmente a clausula de objeto ou escopo dos servicos "
                    "como consta no documento."
                ),
            },
            {
                "name": "Valor Total",
                "type": "currency",
                "extraction_prompt": (
                    "Extraia o valor total do contrato em reais (R$). "
                    "Se o valor for mensal/por hora, extraia o valor unitario "
                    "e indique a periodicidade. Se houver valor global, "
                    "prefira o valor total do contrato."
                ),
            },
            {
                "name": "Forma de Pagamento",
                "type": "text",
                "extraction_prompt": (
                    "Extraia a forma de pagamento prevista no contrato: "
                    "parcela unica, parcelas mensais, por entrega/milestone, "
                    "por hora trabalhada, etc. Inclua prazo para pagamento "
                    "(ex: ate o dia 10 de cada mes, 30 dias apos emissao da NF)."
                ),
            },
            {
                "name": "Prazo de Execucao",
                "type": "text",
                "extraction_prompt": (
                    "Extraia o prazo de execucao ou vigencia do contrato "
                    "(ex: 6 meses, 12 meses, por projeto). Informe data "
                    "de inicio e termino se mencionadas. Indique se ha "
                    "clausula de renovacao automatica."
                ),
            },
            {
                "name": "Multa por Atraso",
                "type": "text",
                "extraction_prompt": (
                    "Extraia informacoes sobre multa ou penalidade por atraso "
                    "na execucao dos servicos ou no pagamento. Inclua "
                    "percentual, valor fixo ou base de calculo. "
                    "Se nao houver, indique 'Nao prevista'."
                ),
            },
            {
                "name": "Clausula de Rescisao",
                "type": "verbatim",
                "extraction_prompt": (
                    "Extraia o conteudo da clausula de rescisao do contrato. "
                    "Inclua: hipoteses de rescisao (por conveniencia, por "
                    "justa causa), aviso previo necessario, penalidades "
                    "por rescisao antecipada. Transcreva literalmente."
                ),
            },
            {
                "name": "Confidencialidade",
                "type": "boolean",
                "extraction_prompt": (
                    "O contrato possui clausula de confidencialidade, sigilo "
                    "ou NDA? Responda 'Sim' ou 'Nao'. Considere clausulas "
                    "que obriguem qualquer das partes a manter sigilo sobre "
                    "informacoes obtidas durante a prestacao dos servicos."
                ),
            },
            {
                "name": "Propriedade Intelectual",
                "type": "text",
                "extraction_prompt": (
                    "Extraia informacoes sobre a clausula de propriedade "
                    "intelectual: a quem pertencem os direitos sobre "
                    "trabalhos, criações, softwares ou documentos produzidos "
                    "durante a prestacao dos servicos. Se nao houver clausula "
                    "especifica, indique 'Nao prevista'."
                ),
            },
            {
                "name": "Foro",
                "type": "text",
                "extraction_prompt": (
                    "Extraia o foro de eleicao para resolucao de disputas "
                    "conforme clausula de foro do contrato. Inclua se ha "
                    "previsao de arbitragem ou mediacao."
                ),
            },
        ],
    },
    # -----------------------------------------------------------------------
    # 4. Contrato de Compra e Venda
    # -----------------------------------------------------------------------
    {
        "name": "Contrato de Compra e Venda",
        "description": (
            "Extrai dados completos de contratos de compra e venda: partes, "
            "objeto, valor, condicoes de pagamento, prazos, garantias e "
            "clausulas especiais. Aplicavel a bens moveis e imoveis."
        ),
        "area": "civil",
        "columns": [
            {
                "name": "Vendedor",
                "type": "text",
                "extraction_prompt": (
                    "Extraia o nome completo do vendedor. Se pessoa juridica, "
                    "extraia a razao social. Se houver mais de um vendedor, "
                    "liste todos os nomes."
                ),
            },
            {
                "name": "Comprador",
                "type": "text",
                "extraction_prompt": (
                    "Extraia o nome completo do comprador. Se pessoa juridica, "
                    "extraia a razao social. Se houver mais de um comprador, "
                    "liste todos os nomes."
                ),
            },
            {
                "name": "Objeto da Venda",
                "type": "verbatim",
                "extraction_prompt": (
                    "Extraia a descricao completa do bem objeto da compra e "
                    "venda. Para imoveis: endereco, matricula, area. Para "
                    "bens moveis: descricao, quantidade, especificacoes. "
                    "Transcreva como consta no contrato."
                ),
            },
            {
                "name": "Valor Total",
                "type": "currency",
                "extraction_prompt": (
                    "Extraia o valor total da compra e venda em reais (R$). "
                    "Se houver parcelas, extraia o valor total do negocio, "
                    "nao apenas uma parcela individual."
                ),
            },
            {
                "name": "Condicoes de Pagamento",
                "type": "text",
                "extraction_prompt": (
                    "Extraia as condicoes de pagamento: a vista, parcelado "
                    "(numero de parcelas, valor de cada parcela), "
                    "financiamento, permuta, entrada + saldo. Inclua "
                    "datas de vencimento se mencionadas."
                ),
            },
            {
                "name": "Prazo de Entrega",
                "type": "text",
                "extraction_prompt": (
                    "Extraia o prazo para entrega do bem ou transferencia "
                    "de posse/propriedade. Informe data especifica ou "
                    "prazo em dias/meses apos assinatura. Se nao houver "
                    "prazo explicito, indique 'Nao especificado'."
                ),
            },
            {
                "name": "Garantia",
                "type": "text",
                "extraction_prompt": (
                    "Extraia informacoes sobre garantia do bem vendido: "
                    "prazo de garantia, o que esta coberto, exclusoes. "
                    "Se nao houver clausula de garantia, indique "
                    "'Nao prevista'."
                ),
            },
            {
                "name": "Vicios Redibitorios",
                "type": "text",
                "extraction_prompt": (
                    "Extraia informacoes sobre clausula de vicios "
                    "redibitorios (defeitos ocultos): prazo para reclamacao, "
                    "responsabilidade do vendedor, condicoes de devolucao. "
                    "Se nao houver clausula especifica, indique "
                    "'Nao prevista'."
                ),
            },
            {
                "name": "Clausula Penal",
                "type": "text",
                "extraction_prompt": (
                    "Extraia o conteudo da clausula penal ou multa "
                    "contratual: percentual ou valor da multa por "
                    "inadimplemento, juros de mora, correcao monetaria. "
                    "Se nao houver, indique 'Nao prevista'."
                ),
            },
            {
                "name": "Foro",
                "type": "text",
                "extraction_prompt": (
                    "Extraia o foro de eleicao para resolucao de disputas "
                    "decorrentes do contrato de compra e venda."
                ),
            },
            {
                "name": "Data de Assinatura",
                "type": "date",
                "extraction_prompt": (
                    "Extraia a data de assinatura do contrato de compra e "
                    "venda. Pode estar no cabecalho, no preambulo ou na "
                    "clausula final. Formato: DD/MM/AAAA."
                ),
            },
            {
                "name": "Testemunhas",
                "type": "text",
                "extraction_prompt": (
                    "Extraia os nomes das testemunhas que assinaram o "
                    "contrato. Se houver CPF das testemunhas, inclua-os. "
                    "Se nao houver testemunhas, indique 'Nao constam'."
                ),
            },
            {
                "name": "Clausula de Arrependimento",
                "type": "text",
                "extraction_prompt": (
                    "Extraia informacoes sobre clausula de arrependimento "
                    "ou direito de desistencia: prazo para exercicio, "
                    "penalidades, condicoes de devolucao de valores. "
                    "Se nao houver, indique 'Nao prevista'."
                ),
            },
        ],
    },
    # -----------------------------------------------------------------------
    # 5. Contratos de Prestacao de Servicos de TI
    # -----------------------------------------------------------------------
    {
        "name": "Contratos de Prestacao de Servicos de TI",
        "description": (
            "Extrai dados-chave de contratos de TI: partes, objeto, SLA, "
            "valores, vigencia, clausulas de LGPD e rescisao."
        ),
        "area": "ti",
        "columns": [
            {
                "name": "Contratante",
                "type": "text",
                "extraction_prompt": (
                    "Extraia o nome completo (razao social) da empresa contratante "
                    "dos servicos de TI."
                ),
            },
            {
                "name": "Contratada",
                "type": "text",
                "extraction_prompt": (
                    "Extraia o nome completo (razao social) da empresa prestadora "
                    "dos servicos de TI."
                ),
            },
            {
                "name": "Objeto",
                "type": "verbatim",
                "extraction_prompt": (
                    "Extraia a descricao do objeto do contrato — os servicos "
                    "de TI contratados. Transcreva como consta no contrato."
                ),
            },
            {
                "name": "Valor Mensal",
                "type": "currency",
                "extraction_prompt": (
                    "Extraia o valor mensal do contrato em reais (R$). "
                    "Se houver valor anual, divida por 12."
                ),
            },
            {
                "name": "SLA Uptime",
                "type": "text",
                "extraction_prompt": (
                    "Extraia o nivel de SLA de disponibilidade (uptime) "
                    "comprometido no contrato (ex: 99.5%, 99.9%)."
                ),
            },
            {
                "name": "Multa por Rescisao",
                "type": "currency",
                "extraction_prompt": (
                    "Extraia o valor ou percentual da multa por rescisao antecipada "
                    "do contrato. Se em percentual, informe o percentual."
                ),
            },
            {
                "name": "Vigencia",
                "type": "text",
                "extraction_prompt": (
                    "Extraia o prazo de vigencia do contrato (ex: 12 meses, "
                    "24 meses, prazo indeterminado)."
                ),
            },
            {
                "name": "Foro",
                "type": "text",
                "extraction_prompt": (
                    "Extraia o foro de eleicao para resolucao de disputas "
                    "conforme clausula de foro do contrato."
                ),
            },
            {
                "name": "LGPD",
                "type": "boolean",
                "extraction_prompt": (
                    "O contrato possui clausula de protecao de dados pessoais / LGPD? "
                    "Responda 'Sim' ou 'Nao'."
                ),
            },
        ],
    },
    # -----------------------------------------------------------------------
    # 6. Due Diligence — Sociedades
    # -----------------------------------------------------------------------
    {
        "name": "Due Diligence — Sociedades",
        "description": (
            "Extrai informacoes societarias para due diligence: razao social, "
            "CNPJ, capital social, quadro de socios, objeto social."
        ),
        "area": "societario",
        "columns": [
            {
                "name": "Razao Social",
                "type": "text",
                "extraction_prompt": (
                    "Extraia a razao social completa da empresa/sociedade."
                ),
            },
            {
                "name": "CNPJ",
                "type": "text",
                "extraction_prompt": (
                    "Extraia o numero do CNPJ da empresa. "
                    "Formato: XX.XXX.XXX/XXXX-XX."
                ),
            },
            {
                "name": "Capital Social",
                "type": "currency",
                "extraction_prompt": (
                    "Extraia o valor do capital social da sociedade em reais (R$)."
                ),
            },
            {
                "name": "Socios",
                "type": "verbatim",
                "extraction_prompt": (
                    "Extraia a lista de socios/quotistas com suas respectivas "
                    "participacoes percentuais no capital social."
                ),
            },
            {
                "name": "Administrador",
                "type": "text",
                "extraction_prompt": (
                    "Extraia o nome do administrador, diretor ou representante legal "
                    "da sociedade."
                ),
            },
            {
                "name": "Data de Constituicao",
                "type": "date",
                "extraction_prompt": (
                    "Extraia a data de constituicao/registro da sociedade. "
                    "Formato: DD/MM/AAAA."
                ),
            },
            {
                "name": "Atividade Principal",
                "type": "text",
                "extraction_prompt": (
                    "Extraia o objeto social ou atividade principal da empresa "
                    "conforme consta no contrato social ou estatuto."
                ),
            },
        ],
    },
    # -----------------------------------------------------------------------
    # 7. Contratos de Franquia
    # -----------------------------------------------------------------------
    {
        "name": "Contratos de Franquia",
        "description": (
            "Extrai dados de COFs e contratos de franquia: partes, taxas, "
            "territorio, prazo, obrigacoes."
        ),
        "area": "empresarial",
        "columns": [
            {
                "name": "Franqueador",
                "type": "text",
                "extraction_prompt": (
                    "Extraia o nome completo (razao social) do franqueador."
                ),
            },
            {
                "name": "Franqueado",
                "type": "text",
                "extraction_prompt": (
                    "Extraia o nome completo do franqueado."
                ),
            },
            {
                "name": "Taxa de Franquia",
                "type": "currency",
                "extraction_prompt": (
                    "Extraia o valor da taxa inicial de franquia em reais (R$)."
                ),
            },
            {
                "name": "Royalties",
                "type": "text",
                "extraction_prompt": (
                    "Extraia o percentual ou valor de royalties mensais."
                ),
            },
            {
                "name": "Territorio",
                "type": "text",
                "extraction_prompt": (
                    "Extraia a definicao do territorio exclusivo do franqueado."
                ),
            },
            {
                "name": "Prazo",
                "type": "text",
                "extraction_prompt": (
                    "Extraia o prazo de vigencia do contrato de franquia."
                ),
            },
            {
                "name": "Fundo de Propaganda",
                "type": "text",
                "extraction_prompt": (
                    "Extraia o percentual ou valor de contribuicao para o "
                    "fundo de propaganda/marketing."
                ),
            },
        ],
    },
]
