"""
Seed de templates de workflow pré-configurados.

Uso:
    python -m app.scripts.seed_workflow_templates

Cria 12 templates de workflow prontos para uso no catálogo.
Verifica duplicatas pelo nome antes de inserir.
"""

import asyncio
import uuid

from sqlalchemy import select
from loguru import logger

from app.core.database import AsyncSessionLocal
from app.models.workflow import Workflow


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _id() -> str:
    return str(uuid.uuid4())


def _base(
    name: str,
    description: str,
    graph_json: dict,
    tags: list[str],
    category: str,
    output_type: str,
    practice_area: str | None = None,
) -> dict:
    """Retorna dict com campos comuns a todos os templates."""
    return {
        "id": _id(),
        "user_id": "system",
        "organization_id": None,
        "name": name,
        "description": description,
        "graph_json": graph_json,
        "is_template": True,
        "is_active": True,
        "status": "published",
        "tags": tags,
        "category": category,
        "output_type": output_type,
        "practice_area": practice_area,
        "embedded_files": [],
    }


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

TEMPLATES: list[dict] = [
    # ── 1. Traduzir Documento ──────────────────────────────────
    _base(
        name="Traduzir Documento",
        description="Traduz um documento para o idioma selecionado, preservando formatação e terminologia jurídica.",
        tags=["tradução", "idiomas", "documento"],
        category="general",
        output_type="document",
        graph_json={
            "nodes": [
                {
                    "id": "file_upload_1",
                    "type": "file_upload",
                    "position": {"x": 150, "y": 50},
                    "data": {
                        "label": "Upload Documento",
                        "accepts": ".pdf,.docx,.txt",
                    },
                },
                {
                    "id": "selection_1",
                    "type": "selection",
                    "position": {"x": 450, "y": 50},
                    "data": {
                        "label": "Idioma de Destino",
                        "collects": "idioma_destino",
                        "options": ["Inglês", "Espanhol", "Francês", "Alemão"],
                    },
                },
                {
                    "id": "prompt_1",
                    "type": "prompt",
                    "position": {"x": 300, "y": 200},
                    "data": {
                        "label": "Traduzir",
                        "model": "claude-4.5-sonnet",
                        "prompt": (
                            "Você é um tradutor jurídico profissional. Traduza o documento a seguir "
                            "para o idioma {{idioma_destino}}.\n\n"
                            "Instruções:\n"
                            "1. Preserve a estrutura e formatação original do documento (títulos, "
                            "parágrafos, listas numeradas, etc.).\n"
                            "2. Mantenha termos jurídicos técnicos com tradução precisa — quando não "
                            "houver equivalente direto, inclua o termo original entre parênteses.\n"
                            "3. Preserve nomes próprios, datas, valores monetários e referências "
                            "legislativas no formato original.\n"
                            "4. Use registro formal adequado ao contexto jurídico.\n"
                            "5. Ao final, inclua um glossário breve com os termos técnicos traduzidos "
                            "e seus equivalentes no idioma original.\n\n"
                            "Documento para tradução:\n{{file_upload_1}}"
                        ),
                    },
                },
                {
                    "id": "output_1",
                    "type": "output",
                    "position": {"x": 300, "y": 350},
                    "data": {"label": "Documento Traduzido", "show_all": True},
                },
            ],
            "edges": [
                {"id": "e1", "source": "file_upload_1", "target": "prompt_1", "animated": True},
                {"id": "e2", "source": "selection_1", "target": "prompt_1", "animated": True},
                {"id": "e3", "source": "prompt_1", "target": "output_1", "animated": True},
            ],
        },
    ),

    # ── 2. Revisar Ortografia e Gramática ──────────────────────
    _base(
        name="Revisar Ortografia e Gramática",
        description="Revisa ortografia, gramática e estilo de um documento jurídico, sugerindo correções.",
        tags=["revisão", "gramática", "ortografia", "documento"],
        category="general",
        output_type="document",
        graph_json={
            "nodes": [
                {
                    "id": "file_upload_1",
                    "type": "file_upload",
                    "position": {"x": 300, "y": 50},
                    "data": {
                        "label": "Upload Documento",
                        "accepts": ".pdf,.docx,.txt",
                    },
                },
                {
                    "id": "prompt_1",
                    "type": "prompt",
                    "position": {"x": 300, "y": 200},
                    "data": {
                        "label": "Revisar Ortografia e Gramática",
                        "model": "claude-4.5-sonnet",
                        "prompt": (
                            "Você é um revisor linguístico especializado em textos jurídicos em "
                            "português brasileiro. Revise o documento a seguir de forma minuciosa.\n\n"
                            "Analise e corrija:\n"
                            "1. **Ortografia**: erros de digitação, acentuação, hifenização.\n"
                            "2. **Gramática**: concordância verbal e nominal, regência, crase, "
                            "pronomes, conjugação.\n"
                            "3. **Pontuação**: vírgulas, pontos, dois-pontos, ponto e vírgula.\n"
                            "4. **Estilo jurídico**: adequação ao registro formal, clareza, "
                            "concisão, eliminação de redundâncias.\n"
                            "5. **Coesão e coerência**: conectivos, referências internas, "
                            "organização lógica dos argumentos.\n\n"
                            "Para cada correção, apresente:\n"
                            "- O trecho original\n"
                            "- A correção sugerida\n"
                            "- Breve justificativa da mudança\n\n"
                            "Ao final, forneça o documento completo com todas as correções aplicadas.\n\n"
                            "Documento para revisão:\n{{file_upload_1}}"
                        ),
                    },
                },
                {
                    "id": "output_1",
                    "type": "output",
                    "position": {"x": 300, "y": 350},
                    "data": {"label": "Documento Revisado", "show_all": True},
                },
            ],
            "edges": [
                {"id": "e1", "source": "file_upload_1", "target": "prompt_1", "animated": True},
                {"id": "e2", "source": "prompt_1", "target": "output_1", "animated": True},
            ],
        },
    ),

    # ── 3. Extrair Linha do Tempo ──────────────────────────────
    _base(
        name="Extrair Linha do Tempo",
        description="Extrai uma cronologia detalhada de eventos a partir de documentos jurídicos.",
        tags=["cronologia", "timeline", "eventos", "datas"],
        category="general",
        output_type="timeline",
        graph_json={
            "nodes": [
                {
                    "id": "file_upload_1",
                    "type": "file_upload",
                    "position": {"x": 300, "y": 50},
                    "data": {
                        "label": "Upload Documento(s)",
                        "accepts": ".pdf,.docx,.txt",
                    },
                },
                {
                    "id": "prompt_1",
                    "type": "prompt",
                    "position": {"x": 300, "y": 200},
                    "data": {
                        "label": "Extrair Cronologia",
                        "model": "claude-4.5-sonnet",
                        "prompt": (
                            "Você é um analista jurídico especializado em organização cronológica "
                            "de fatos. Analise o(s) documento(s) a seguir e extraia uma linha do "
                            "tempo completa e ordenada.\n\n"
                            "Para cada evento identificado, forneça:\n"
                            "1. **Data**: no formato DD/MM/AAAA (se disponível; caso contrário, "
                            "indique período aproximado).\n"
                            "2. **Evento**: descrição concisa do fato ocorrido.\n"
                            "3. **Partes envolvidas**: quem participou ou foi afetado.\n"
                            "4. **Referência**: página ou trecho do documento onde consta a "
                            "informação.\n"
                            "5. **Relevância**: Alta / Média / Baixa para o caso.\n\n"
                            "Organize os eventos em ordem cronológica (do mais antigo ao mais "
                            "recente). Se houver datas incertas, posicione-as com nota explicativa.\n\n"
                            "Ao final, inclua um resumo de 3-5 linhas destacando os marcos "
                            "temporais mais relevantes.\n\n"
                            "Documento(s) para análise:\n{{file_upload_1}}"
                        ),
                    },
                },
                {
                    "id": "output_1",
                    "type": "output",
                    "position": {"x": 300, "y": 350},
                    "data": {"label": "Linha do Tempo", "show_all": True},
                },
            ],
            "edges": [
                {"id": "e1", "source": "file_upload_1", "target": "prompt_1", "animated": True},
                {"id": "e2", "source": "prompt_1", "target": "output_1", "animated": True},
            ],
        },
    ),

    # ── 4. Rascunhar Alerta ao Cliente ─────────────────────────
    _base(
        name="Rascunhar Alerta ao Cliente",
        description="Gera um memorando / alerta ao cliente sobre um tema jurídico relevante com base em fontes fornecidas.",
        tags=["alerta", "cliente", "memo", "comunicação"],
        category="general",
        output_type="memo",
        graph_json={
            "nodes": [
                {
                    "id": "user_input_1",
                    "type": "user_input",
                    "position": {"x": 150, "y": 50},
                    "data": {
                        "label": "Tema do Alerta",
                        "input_type": "text",
                        "collects": "tema_alerta",
                    },
                },
                {
                    "id": "file_upload_1",
                    "type": "file_upload",
                    "position": {"x": 450, "y": 50},
                    "data": {
                        "label": "Fonte(s) de Referência",
                        "accepts": ".pdf,.docx,.txt,.html",
                    },
                },
                {
                    "id": "prompt_1",
                    "type": "prompt",
                    "position": {"x": 300, "y": 200},
                    "data": {
                        "label": "Rascunhar Alerta",
                        "model": "claude-4.5-sonnet",
                        "prompt": (
                            "Você é um advogado sênior redigindo um alerta / client alert para "
                            "clientes do escritório. O tema é: **{{tema_alerta}}**.\n\n"
                            "Com base nas fontes fornecidas, redija um alerta profissional com a "
                            "seguinte estrutura:\n\n"
                            "1. **Título**: claro e direto, refletindo a mudança ou novidade.\n"
                            "2. **Resumo Executivo** (2-3 parágrafos): o que mudou, por que importa "
                            "e o que o cliente precisa saber imediatamente.\n"
                            "3. **Contexto**: breve histórico ou panorama regulatório.\n"
                            "4. **Análise**: pontos-chave, impactos práticos, riscos e "
                            "oportunidades.\n"
                            "5. **Ações Recomendadas**: lista de passos concretos que o cliente "
                            "deve considerar.\n"
                            "6. **Próximos Passos / Datas Importantes**: prazos ou marcos "
                            "relevantes.\n\n"
                            "Tom: profissional mas acessível. Evite jargão desnecessário. "
                            "O alerta deve ser compreensível para executivos não-juristas.\n\n"
                            "Fontes de referência:\n{{file_upload_1}}"
                        ),
                    },
                },
                {
                    "id": "output_1",
                    "type": "output",
                    "position": {"x": 300, "y": 350},
                    "data": {"label": "Alerta ao Cliente", "show_all": True},
                },
            ],
            "edges": [
                {"id": "e1", "source": "user_input_1", "target": "prompt_1", "animated": True},
                {"id": "e2", "source": "file_upload_1", "target": "prompt_1", "animated": True},
                {"id": "e3", "source": "prompt_1", "target": "output_1", "animated": True},
            ],
        },
    ),

    # ── 5. Resumir Alterações de Redline ───────────────────────
    _base(
        name="Resumir Alterações de Redline",
        description="Analisa um documento com marcações de redline e resume todas as alterações em formato tabular.",
        tags=["redline", "alterações", "contrato", "tabela"],
        category="transactional",
        output_type="table",
        practice_area="Direito Contratual",
        graph_json={
            "nodes": [
                {
                    "id": "file_upload_1",
                    "type": "file_upload",
                    "position": {"x": 300, "y": 50},
                    "data": {
                        "label": "Upload Redline",
                        "accepts": ".pdf,.docx",
                    },
                },
                {
                    "id": "prompt_1",
                    "type": "prompt",
                    "position": {"x": 300, "y": 200},
                    "data": {
                        "label": "Resumir Alterações",
                        "model": "claude-4.5-sonnet",
                        "prompt": (
                            "Você é um advogado contratualista experiente. Analise o documento "
                            "redline (com marcações de alteração) a seguir e produza um resumo "
                            "estruturado de todas as mudanças.\n\n"
                            "Para cada alteração identificada, forneça em formato de tabela:\n\n"
                            "| # | Cláusula/Seção | Texto Original | Texto Alterado | Tipo de "
                            "Alteração | Impacto | Risco |\n\n"
                            "Tipos de alteração: Inclusão, Exclusão, Modificação, Reordenação.\n"
                            "Impacto: Alto / Médio / Baixo.\n"
                            "Risco: descreva brevemente o risco jurídico ou comercial da mudança.\n\n"
                            "Ao final da tabela, inclua:\n"
                            "1. **Resumo geral**: quantas alterações, distribuição por tipo e "
                            "impacto.\n"
                            "2. **Alertas críticos**: alterações de alto impacto que merecem "
                            "atenção imediata da equipe.\n"
                            "3. **Recomendações**: sugestões de resposta ou negociação para as "
                            "alterações mais relevantes.\n\n"
                            "Documento redline:\n{{file_upload_1}}"
                        ),
                    },
                },
                {
                    "id": "output_1",
                    "type": "output",
                    "position": {"x": 300, "y": 350},
                    "data": {"label": "Tabela de Alterações", "show_all": True},
                },
            ],
            "edges": [
                {"id": "e1", "source": "file_upload_1", "target": "prompt_1", "animated": True},
                {"id": "e2", "source": "prompt_1", "target": "output_1", "animated": True},
            ],
        },
    ),

    # ── 6. Comparar Contrato vs Modelo ─────────────────────────
    _base(
        name="Comparar Contrato vs Modelo",
        description="Compara um contrato recebido com o modelo padrão do escritório, destacando divergências.",
        tags=["comparação", "contrato", "modelo", "tabela", "due diligence"],
        category="transactional",
        output_type="table",
        practice_area="Direito Contratual",
        graph_json={
            "nodes": [
                {
                    "id": "file_upload_1",
                    "type": "file_upload",
                    "position": {"x": 150, "y": 50},
                    "data": {
                        "label": "Upload Modelo Padrão",
                        "accepts": ".pdf,.docx",
                    },
                },
                {
                    "id": "file_upload_2",
                    "type": "file_upload",
                    "position": {"x": 450, "y": 50},
                    "data": {
                        "label": "Upload Contrato Recebido",
                        "accepts": ".pdf,.docx",
                    },
                },
                {
                    "id": "prompt_1",
                    "type": "prompt",
                    "position": {"x": 300, "y": 200},
                    "data": {
                        "label": "Comparar Documentos",
                        "model": "claude-4.5-sonnet",
                        "prompt": (
                            "Você é um advogado contratualista sênior. Compare o contrato recebido "
                            "com o modelo padrão do escritório e identifique todas as divergências.\n\n"
                            "**Modelo Padrão:**\n{{file_upload_1}}\n\n"
                            "**Contrato Recebido:**\n{{file_upload_2}}\n\n"
                            "Produza uma tabela comparativa detalhada:\n\n"
                            "| # | Cláusula | Modelo Padrão | Contrato Recebido | Divergência | "
                            "Risco | Recomendação |\n\n"
                            "Para cada divergência, classifique:\n"
                            "- **Risco**: Crítico / Alto / Médio / Baixo / Aceitável\n"
                            "- **Recomendação**: Rejeitar / Negociar / Aceitar com ressalvas / Aceitar\n\n"
                            "Ao final, inclua:\n"
                            "1. **Resumo executivo**: visão geral das divergências encontradas.\n"
                            "2. **Cláusulas ausentes**: cláusulas do modelo que não constam no "
                            "contrato recebido.\n"
                            "3. **Cláusulas adicionais**: cláusulas no contrato recebido que não "
                            "constam no modelo.\n"
                            "4. **Top 5 pontos de negociação**: as divergências mais críticas que "
                            "devem ser priorizadas."
                        ),
                    },
                },
                {
                    "id": "output_1",
                    "type": "output",
                    "position": {"x": 300, "y": 350},
                    "data": {"label": "Comparativo", "show_all": True},
                },
            ],
            "edges": [
                {"id": "e1", "source": "file_upload_1", "target": "prompt_1", "animated": True},
                {"id": "e2", "source": "file_upload_2", "target": "prompt_1", "animated": True},
                {"id": "e3", "source": "prompt_1", "target": "output_1", "animated": True},
            ],
        },
    ),

    # ── 7. Cronograma Pós-Fechamento ───────────────────────────
    _base(
        name="Cronograma Pós-Fechamento",
        description="Extrai obrigações e prazos pós-fechamento de contratos de M&A ou transações societárias.",
        tags=["pós-fechamento", "cronograma", "M&A", "obrigações"],
        category="transactional",
        output_type="timeline",
        practice_area="Direito Societário",
        graph_json={
            "nodes": [
                {
                    "id": "file_upload_1",
                    "type": "file_upload",
                    "position": {"x": 300, "y": 50},
                    "data": {
                        "label": "Upload Contrato",
                        "accepts": ".pdf,.docx",
                    },
                },
                {
                    "id": "prompt_1",
                    "type": "prompt",
                    "position": {"x": 300, "y": 200},
                    "data": {
                        "label": "Extrair Cronograma Pós-Fechamento",
                        "model": "claude-4.5-sonnet",
                        "prompt": (
                            "Você é um advogado especializado em M&A e operações societárias. "
                            "Analise o contrato a seguir e extraia todas as obrigações "
                            "pós-fechamento (post-closing obligations).\n\n"
                            "Para cada obrigação, organize em formato de cronograma:\n\n"
                            "| # | Prazo | Obrigação | Parte Responsável | Cláusula | "
                            "Consequência do Descumprimento | Status |\n\n"
                            "Instruções:\n"
                            "1. Ordene cronologicamente (da mais próxima à mais distante).\n"
                            "2. Para prazos relativos (ex.: '30 dias após o fechamento'), calcule "
                            "a data estimada considerando a data de fechamento indicada no contrato.\n"
                            "3. Identifique obrigações recorrentes (ex.: relatórios trimestrais) "
                            "e indique a periodicidade.\n"
                            "4. Destaque penalidades, multas ou condições resolutivas vinculadas "
                            "ao descumprimento.\n"
                            "5. Inclua obrigações de não-competição, earn-out, indenizações "
                            "pendentes e ajustes de preço.\n\n"
                            "Ao final, forneça:\n"
                            "- **Marcos críticos**: os 5 prazos mais importantes.\n"
                            "- **Alertas**: obrigações com prazos curtos ou penalidades severas.\n"
                            "- **Checklist de acompanhamento**: lista de verificação para "
                            "monitoramento.\n\n"
                            "Contrato:\n{{file_upload_1}}"
                        ),
                    },
                },
                {
                    "id": "output_1",
                    "type": "output",
                    "position": {"x": 300, "y": 350},
                    "data": {"label": "Cronograma Pós-Fechamento", "show_all": True},
                },
            ],
            "edges": [
                {"id": "e1", "source": "file_upload_1", "target": "prompt_1", "animated": True},
                {"id": "e2", "source": "prompt_1", "target": "output_1", "animated": True},
            ],
        },
    ),

    # ── 8. Analisar Transcrição de Depoimento ──────────────────
    _base(
        name="Analisar Transcrição de Depoimento",
        description="Analisa transcrição de depoimento, identificando pontos-chave, contradições e trechos relevantes.",
        tags=["depoimento", "transcrição", "litígio", "análise"],
        category="litigation",
        output_type="table",
        practice_area="Direito Processual",
        graph_json={
            "nodes": [
                {
                    "id": "file_upload_1",
                    "type": "file_upload",
                    "position": {"x": 300, "y": 50},
                    "data": {
                        "label": "Upload Transcrição",
                        "accepts": ".pdf,.docx,.txt",
                    },
                },
                {
                    "id": "prompt_1",
                    "type": "prompt",
                    "position": {"x": 300, "y": 200},
                    "data": {
                        "label": "Analisar Depoimento",
                        "model": "claude-4.5-sonnet",
                        "prompt": (
                            "Você é um advogado litigante experiente. Analise a transcrição de "
                            "depoimento a seguir de forma estratégica.\n\n"
                            "Produza a análise nos seguintes formatos:\n\n"
                            "**1. Resumo do Depoimento**\n"
                            "- Depoente, data, contexto processual (se identificável).\n"
                            "- Resumo em 5-10 linhas dos principais pontos abordados.\n\n"
                            "**2. Tabela de Pontos-Chave**\n"
                            "| # | Tema | Afirmação do Depoente | Página/Trecho | Favorável? | "
                            "Observação |\n\n"
                            "**3. Contradições e Inconsistências**\n"
                            "- Liste contradições internas no depoimento.\n"
                            "- Identifique afirmações vagas ou evasivas.\n"
                            "- Aponte respostas que podem ser exploradas em contra-interrogatório.\n\n"
                            "**4. Admissões Relevantes**\n"
                            "- Fatos admitidos pelo depoente que favorecem a parte contrária.\n\n"
                            "**5. Sugestões para Próximos Passos**\n"
                            "- Perguntas adicionais para follow-up.\n"
                            "- Documentos que devem ser solicitados para corroborar ou contradizer.\n"
                            "- Estratégia sugerida com base no depoimento.\n\n"
                            "Transcrição:\n{{file_upload_1}}"
                        ),
                    },
                },
                {
                    "id": "output_1",
                    "type": "output",
                    "position": {"x": 300, "y": 350},
                    "data": {"label": "Análise do Depoimento", "show_all": True},
                },
            ],
            "edges": [
                {"id": "e1", "source": "file_upload_1", "target": "prompt_1", "animated": True},
                {"id": "e2", "source": "prompt_1", "target": "output_1", "animated": True},
            ],
        },
    ),

    # ── 9. Resumir Respostas de Discovery ──────────────────────
    _base(
        name="Resumir Respostas de Discovery",
        description="Resume respostas a interrogatórios ou requisições de documentos em formato tabular.",
        tags=["discovery", "interrogatório", "litígio", "tabela"],
        category="litigation",
        output_type="table",
        practice_area="Direito Processual",
        graph_json={
            "nodes": [
                {
                    "id": "file_upload_1",
                    "type": "file_upload",
                    "position": {"x": 300, "y": 50},
                    "data": {
                        "label": "Upload Respostas de Discovery",
                        "accepts": ".pdf,.docx,.txt",
                    },
                },
                {
                    "id": "prompt_1",
                    "type": "prompt",
                    "position": {"x": 300, "y": 200},
                    "data": {
                        "label": "Resumir Respostas",
                        "model": "claude-4.5-sonnet",
                        "prompt": (
                            "Você é um advogado litigante especializado em discovery / fase "
                            "instrutória. Analise as respostas a seguir e produza um resumo "
                            "estruturado.\n\n"
                            "Organize em tabela:\n\n"
                            "| # | Pergunta/Requisição | Resumo da Resposta | Respondido "
                            "Integralmente? | Documentos Referenciados | Objeções Levantadas | "
                            "Follow-up Necessário |\n\n"
                            "Classifique cada resposta como:\n"
                            "- ✅ Completa: respondeu integralmente.\n"
                            "- ⚠️ Parcial: respondeu de forma incompleta ou evasiva.\n"
                            "- ❌ Não respondida: objetou sem responder ou ignorou.\n\n"
                            "Ao final, forneça:\n"
                            "1. **Estatísticas**: total de perguntas, % respondidas integralmente, "
                            "% parciais, % não respondidas.\n"
                            "2. **Objeções recorrentes**: padrões de objeção utilizados.\n"
                            "3. **Lacunas críticas**: informações não obtidas que são essenciais.\n"
                            "4. **Recomendações**: ações para obter as informações faltantes "
                            "(moções para compelir, novas requisições, etc.).\n\n"
                            "Respostas para análise:\n{{file_upload_1}}"
                        ),
                    },
                },
                {
                    "id": "output_1",
                    "type": "output",
                    "position": {"x": 300, "y": 350},
                    "data": {"label": "Resumo de Discovery", "show_all": True},
                },
            ],
            "edges": [
                {"id": "e1", "source": "file_upload_1", "target": "prompt_1", "animated": True},
                {"id": "e2", "source": "prompt_1", "target": "output_1", "animated": True},
            ],
        },
    ),

    # ── 10. Cronologia + Teses + Provas ────────────────────────
    _base(
        name="Cronologia + Teses + Provas",
        description="Analisa peças processuais para gerar cronologia de fatos, mapear teses jurídicas e correlacionar provas.",
        tags=["cronologia", "teses", "provas", "litígio", "estratégia"],
        category="litigation",
        output_type="table",
        practice_area="Direito Processual",
        graph_json={
            "nodes": [
                {
                    "id": "file_upload_1",
                    "type": "file_upload",
                    "position": {"x": 150, "y": 50},
                    "data": {
                        "label": "Upload Peças Processuais",
                        "accepts": ".pdf,.docx",
                    },
                },
                {
                    "id": "user_input_1",
                    "type": "user_input",
                    "position": {"x": 450, "y": 50},
                    "data": {
                        "label": "Objetivo da Análise",
                        "input_type": "text",
                        "collects": "objetivo_analise",
                    },
                },
                {
                    "id": "condition_1",
                    "type": "condition",
                    "position": {"x": 300, "y": 200},
                    "data": {
                        "label": "Tipo de Análise",
                        "condition_field": "objetivo_analise",
                        "branches": {
                            "defesa": "prompt_1",
                            "acusação": "prompt_1",
                            "default": "prompt_1",
                        },
                    },
                },
                {
                    "id": "prompt_1",
                    "type": "prompt",
                    "position": {"x": 300, "y": 350},
                    "data": {
                        "label": "Gerar Cronologia e Teses",
                        "model": "claude-4.5-sonnet",
                        "prompt": (
                            "Você é um advogado litigante sênior. Analise as peças processuais "
                            "fornecidas com o seguinte objetivo: **{{objetivo_analise}}**.\n\n"
                            "Produza três análises integradas:\n\n"
                            "**PARTE 1 — CRONOLOGIA DOS FATOS**\n"
                            "| Data | Fato | Fonte (documento/página) | Relevância |\n"
                            "Ordene cronologicamente. Destaque fatos controversos.\n\n"
                            "**PARTE 2 — MAPEAMENTO DE TESES JURÍDICAS**\n"
                            "Para cada tese identificada nas peças:\n"
                            "| # | Tese | Parte que Sustenta | Fundamento Legal | Jurisprudência "
                            "Citada | Força (1-5) |\n\n"
                            "Avalie a força de cada tese de 1 (fraca) a 5 (muito forte) com "
                            "justificativa.\n\n"
                            "**PARTE 3 — MATRIZ DE PROVAS**\n"
                            "| # | Prova | Tipo | Fato que Comprova | Tese que Sustenta | "
                            "Produzida? | Observação |\n\n"
                            "Tipos: Documental, Testemunhal, Pericial, Indiciária.\n\n"
                            "Ao final, forneça:\n"
                            "- **Análise estratégica**: pontos fortes e fracos de cada lado.\n"
                            "- **Provas faltantes**: o que precisa ser produzido.\n"
                            "- **Recomendações táticas**: próximos passos sugeridos.\n\n"
                            "Peças processuais:\n{{file_upload_1}}"
                        ),
                    },
                },
                {
                    "id": "prompt_2",
                    "type": "prompt",
                    "position": {"x": 300, "y": 500},
                    "data": {
                        "label": "Consolidar Análise",
                        "model": "claude-4.5-sonnet",
                        "prompt": (
                            "Com base na análise anterior, produza um resumo executivo consolidado "
                            "para apresentação à equipe jurídica.\n\n"
                            "Estrutura do resumo:\n"
                            "1. **Visão Geral do Caso** (3-5 linhas)\n"
                            "2. **Top 5 Fatos Mais Relevantes**\n"
                            "3. **Teses Principais (Autor vs Réu)**\n"
                            "4. **Estado da Prova**: o que já foi produzido e o que falta.\n"
                            "5. **Avaliação de Risco**: probabilidade de êxito (alta/média/baixa) "
                            "com justificativa.\n"
                            "6. **Plano de Ação**: 5-7 ações concretas priorizadas.\n\n"
                            "Análise anterior:\n{{prompt_1}}"
                        ),
                    },
                },
                {
                    "id": "output_1",
                    "type": "output",
                    "position": {"x": 300, "y": 650},
                    "data": {"label": "Análise Completa", "show_all": True},
                },
            ],
            "edges": [
                {"id": "e1", "source": "file_upload_1", "target": "condition_1", "animated": True},
                {"id": "e2", "source": "user_input_1", "target": "condition_1", "animated": True},
                {"id": "e3", "source": "condition_1", "target": "prompt_1", "animated": True},
                {"id": "e4", "source": "prompt_1", "target": "prompt_2", "animated": True},
                {"id": "e5", "source": "prompt_2", "target": "output_1", "animated": True},
            ],
        },
    ),

    # ── 11. Due Diligence de Fornecedor ────────────────────────
    _base(
        name="Due Diligence de Fornecedor",
        description="Avalia fornecedores quanto à conformidade com LGPD e proteção de dados, gerando checklist de adequação.",
        tags=["LGPD", "fornecedor", "due diligence", "dados pessoais", "checklist"],
        category="administrative",
        output_type="checklist",
        practice_area="Direito Digital",
        graph_json={
            "nodes": [
                {
                    "id": "user_input_1",
                    "type": "user_input",
                    "position": {"x": 100, "y": 50},
                    "data": {
                        "label": "Nome do Fornecedor",
                        "input_type": "text",
                        "collects": "nome_fornecedor",
                    },
                },
                {
                    "id": "selection_1",
                    "type": "selection",
                    "position": {"x": 300, "y": 50},
                    "data": {
                        "label": "Tipo de Dados Tratados",
                        "collects": "tipo_dados",
                        "options": ["Dados Pessoais", "Dados Sensíveis", "Dados Financeiros"],
                    },
                },
                {
                    "id": "file_upload_1",
                    "type": "file_upload",
                    "position": {"x": 500, "y": 50},
                    "data": {
                        "label": "Upload DPA / Contrato",
                        "accepts": ".pdf,.docx",
                    },
                },
                {
                    "id": "condition_1",
                    "type": "condition",
                    "position": {"x": 300, "y": 200},
                    "data": {
                        "label": "Dados Sensíveis?",
                        "condition_field": "tipo_dados",
                        "branches": {
                            "Dados Sensíveis": "prompt_1",
                            "default": "prompt_1",
                        },
                    },
                },
                {
                    "id": "prompt_1",
                    "type": "prompt",
                    "position": {"x": 300, "y": 350},
                    "data": {
                        "label": "Análise de Conformidade",
                        "model": "claude-4.5-sonnet",
                        "prompt": (
                            "Você é um advogado especializado em proteção de dados e LGPD. Realize "
                            "uma due diligence do fornecedor **{{nome_fornecedor}}** que trata "
                            "**{{tipo_dados}}**.\n\n"
                            "Analise o DPA / contrato fornecido e avalie:\n\n"
                            "**1. Análise Contratual**\n"
                            "| Requisito LGPD | Presente? | Cláusula | Adequado? | Observação |\n\n"
                            "Requisitos a verificar:\n"
                            "- Definição de papéis (controlador/operador)\n"
                            "- Finalidade do tratamento\n"
                            "- Base legal aplicável\n"
                            "- Medidas de segurança (art. 46)\n"
                            "- Suboperadores e transferência internacional\n"
                            "- Notificação de incidentes\n"
                            "- Direitos dos titulares\n"
                            "- Retenção e eliminação de dados\n"
                            "- Auditoria e fiscalização\n"
                            "- Responsabilidade e indenização\n\n"
                            "**2. Avaliação de Risco**\n"
                            "- Risco geral: Crítico / Alto / Médio / Baixo\n"
                            "- Justificativa detalhada\n\n"
                            "DPA / Contrato:\n{{file_upload_1}}"
                        ),
                    },
                },
                {
                    "id": "prompt_2",
                    "type": "prompt",
                    "position": {"x": 300, "y": 500},
                    "data": {
                        "label": "Gerar Checklist",
                        "model": "claude-4.5-sonnet",
                        "prompt": (
                            "Com base na análise de conformidade do fornecedor "
                            "**{{nome_fornecedor}}**, gere um checklist acionável.\n\n"
                            "**CHECKLIST DE ADEQUAÇÃO — {{nome_fornecedor}}**\n\n"
                            "Para cada item, indique:\n"
                            "- [ ] ou [x]: pendente ou conforme\n"
                            "- Prioridade: P1 (urgente), P2 (importante), P3 (desejável)\n"
                            "- Ação necessária: o que deve ser feito\n"
                            "- Responsável sugerido: jurídico, TI, compliance, fornecedor\n\n"
                            "Categorias do checklist:\n"
                            "1. Adequação contratual\n"
                            "2. Medidas técnicas de segurança\n"
                            "3. Medidas organizacionais\n"
                            "4. Gestão de incidentes\n"
                            "5. Transferência internacional (se aplicável)\n"
                            "6. Direitos dos titulares\n"
                            "7. Documentação e registros\n\n"
                            "Inclua prazos sugeridos e uma nota final com parecer "
                            "recomendando aprovação, aprovação condicionada ou reprovação "
                            "do fornecedor.\n\n"
                            "Análise anterior:\n{{prompt_1}}"
                        ),
                    },
                },
                {
                    "id": "output_1",
                    "type": "output",
                    "position": {"x": 300, "y": 650},
                    "data": {"label": "Checklist de Due Diligence", "show_all": True},
                },
            ],
            "edges": [
                {"id": "e1", "source": "user_input_1", "target": "condition_1", "animated": True},
                {"id": "e2", "source": "selection_1", "target": "condition_1", "animated": True},
                {"id": "e3", "source": "file_upload_1", "target": "condition_1", "animated": True},
                {"id": "e4", "source": "condition_1", "target": "prompt_1", "animated": True},
                {"id": "e5", "source": "prompt_1", "target": "prompt_2", "animated": True},
                {"id": "e6", "source": "prompt_2", "target": "output_1", "animated": True},
            ],
        },
    ),

    # ── 12. Revisão de Política de Privacidade ─────────────────
    _base(
        name="Revisão de Política de Privacidade",
        description="Analisa uma política de privacidade à luz da legislação selecionada (LGPD, GDPR ou CCPA).",
        tags=["privacidade", "LGPD", "GDPR", "CCPA", "política", "compliance"],
        category="administrative",
        output_type="memo",
        practice_area="Direito Digital",
        graph_json={
            "nodes": [
                {
                    "id": "file_upload_1",
                    "type": "file_upload",
                    "position": {"x": 150, "y": 50},
                    "data": {
                        "label": "Upload Política de Privacidade",
                        "accepts": ".pdf,.docx,.txt,.html",
                    },
                },
                {
                    "id": "selection_1",
                    "type": "selection",
                    "position": {"x": 450, "y": 50},
                    "data": {
                        "label": "Jurisdição Aplicável",
                        "collects": "jurisdicao",
                        "options": ["Brasil LGPD", "Europa GDPR", "EUA CCPA"],
                    },
                },
                {
                    "id": "prompt_1",
                    "type": "prompt",
                    "position": {"x": 300, "y": 200},
                    "data": {
                        "label": "Analisar Política de Privacidade",
                        "model": "claude-4.5-sonnet",
                        "prompt": (
                            "Você é um advogado especializado em proteção de dados. Analise a "
                            "política de privacidade fornecida à luz da legislação "
                            "**{{jurisdicao}}**.\n\n"
                            "Realize uma análise completa nos seguintes aspectos:\n\n"
                            "**1. Conformidade Regulatória**\n"
                            "| Requisito Legal | Artigo/Seção | Presente na Política? | Adequado? "
                            "| Observação |\n\n"
                            "Requisitos mínimos a verificar:\n"
                            "- Identificação do controlador/responsável\n"
                            "- Dados pessoais coletados e finalidades\n"
                            "- Bases legais para cada tratamento\n"
                            "- Compartilhamento com terceiros\n"
                            "- Transferência internacional de dados\n"
                            "- Direitos dos titulares e como exercê-los\n"
                            "- Período de retenção dos dados\n"
                            "- Medidas de segurança adotadas\n"
                            "- Uso de cookies e tecnologias de rastreamento\n"
                            "- Dados de menores (se aplicável)\n"
                            "- Canal de contato do DPO / Encarregado\n"
                            "- Procedimento para incidentes de segurança\n\n"
                            "**2. Análise de Linguagem**\n"
                            "- A política é clara e acessível ao público leigo?\n"
                            "- Há termos ambíguos ou excessivamente genéricos?\n"
                            "- O formato facilita a leitura (seções, índice, etc.)?\n\n"
                            "**3. Gaps e Recomendações**\n"
                            "Para cada lacuna encontrada:\n"
                            "- Descrição do gap\n"
                            "- Risco regulatório associado\n"
                            "- Redação sugerida para correção\n\n"
                            "**4. Parecer Final**\n"
                            "- Nível de conformidade: Conforme / Parcialmente Conforme / "
                            "Não Conforme\n"
                            "- Prioridades de adequação\n"
                            "- Prazo recomendado para correções\n\n"
                            "Política de Privacidade:\n{{file_upload_1}}"
                        ),
                    },
                },
                {
                    "id": "output_1",
                    "type": "output",
                    "position": {"x": 300, "y": 350},
                    "data": {"label": "Parecer sobre Política", "show_all": True},
                },
            ],
            "edges": [
                {"id": "e1", "source": "file_upload_1", "target": "prompt_1", "animated": True},
                {"id": "e2", "source": "selection_1", "target": "prompt_1", "animated": True},
                {"id": "e3", "source": "prompt_1", "target": "output_1", "animated": True},
            ],
        },
    ),
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    """Insere templates de workflow no banco, pulando os que já existem."""
    logger.info("Iniciando seed de workflow templates...")

    async with AsyncSessionLocal() as session:
        inserted = 0
        skipped = 0

        for template_data in TEMPLATES:
            name = template_data["name"]

            # Verificar se já existe
            stmt = select(Workflow).where(
                Workflow.name == name,
                Workflow.is_template.is_(True),
                Workflow.user_id == "system",
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                logger.info(f"  ⏭  Template já existe: '{name}' (id={existing.id})")
                skipped += 1
                continue

            workflow = Workflow(**template_data)
            session.add(workflow)
            logger.info(f"  ✅ Template inserido: '{name}' (id={workflow.id})")
            inserted += 1

        await session.commit()

    logger.info(
        f"Seed concluído: {inserted} inseridos, {skipped} já existiam. "
        f"Total de templates: {len(TEMPLATES)}."
    )


if __name__ == "__main__":
    asyncio.run(main())
