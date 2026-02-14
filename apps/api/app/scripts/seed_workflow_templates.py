"""
Seed de templates de workflow pré-configurados.

Uso:
    python -m app.scripts.seed_workflow_templates

Cria templates de workflow prontos para uso no catálogo.
Operação idempotente: verifica duplicatas pelo nome (Workflow.name + is_template=True).
"""

import asyncio
import uuid

from sqlalchemy import select
from loguru import logger

from app.core.database import AsyncSessionLocal
from app.models.user import User, UserRole
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

def _tpl(
    name: str,
    description: str,
    graph_json: dict,
    tags: list[str],
    category: str,
    output_type: str,
    practice_area: str | None = None,
) -> dict:
    """
    Alias para templates de workflows mais "app-like" (trigger/delivery).

    Mantemos como wrapper de _base para padronizar a intenção no arquivo.
    """
    return _base(
        name=name,
        description=description,
        graph_json=graph_json,
        tags=tags,
        category=category,
        output_type=output_type,
        practice_area=practice_area,
    )


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

    # ══════════════════════════════════════════════════════════════
    # Templates inspirados em Harvey AI
    # ══════════════════════════════════════════════════════════════

    # ── 13. Análise de Contrato com IA Agêntica ────────────────
    _base(
        name="Análise de Contrato com IA Agêntica",
        description=(
            "Agente autônomo analisa contrato identificando cláusulas-chave, "
            "riscos, obrigações e recomendações. Inspirado no Harvey Workflow Engine."
        ),
        tags=["contratos", "agente", "análise", "harvey"],
        category="contracts",
        output_type="report",
        practice_area="contratos",
        graph_json={
            "nodes": [
                {
                    "id": "file_upload_1",
                    "type": "file_upload",
                    "position": {"x": 300, "y": 50},
                    "data": {
                        "label": "Upload do Contrato",
                        "accepts": ".pdf,.docx,.txt",
                    },
                },
                {
                    "id": "claude_agent_1",
                    "type": "claude_agent",
                    "position": {"x": 300, "y": 200},
                    "data": {
                        "label": "Agente Analista de Contratos",
                        "model": "claude-4.5-sonnet",
                        "system_prompt": (
                            "Você é um advogado especialista em análise contratual. "
                            "Analise o contrato fornecido e produza um relatório estruturado com:\n\n"
                            "1. **Resumo Executivo** — tipo de contrato, partes, objeto, valor\n"
                            "2. **Cláusulas-Chave** — identifique e resuma as cláusulas mais importantes\n"
                            "3. **Obrigações das Partes** — tabela com obrigações de cada parte e prazos\n"
                            "4. **Riscos Identificados** — classifique como Alto/Médio/Baixo com justificativa\n"
                            "5. **Cláusulas Ausentes** — cláusulas padrão que deveriam constar mas não constam\n"
                            "6. **Recomendações** — sugestões de alteração priorizadas\n\n"
                            "Use ferramentas de pesquisa jurídica quando necessário para fundamentar riscos."
                        ),
                        "tool_names": ["legal_research", "rag_search"],
                        "max_iterations": 15,
                        "max_tokens": 8192,
                        "include_mcp": False,
                        "use_sdk": True,
                    },
                },
                {
                    "id": "human_review_1",
                    "type": "human_review",
                    "position": {"x": 300, "y": 380},
                    "data": {
                        "label": "Revisão do Advogado",
                        "instructions": "Revise a análise do agente. Aprove ou solicite ajustes.",
                    },
                },
                {
                    "id": "output_1",
                    "type": "output",
                    "position": {"x": 300, "y": 520},
                    "data": {"label": "Relatório de Análise Contratual", "show_all": True},
                },
            ],
            "edges": [
                {"id": "e1", "source": "file_upload_1", "target": "claude_agent_1", "animated": True},
                {"id": "e2", "source": "claude_agent_1", "target": "human_review_1", "animated": True},
                {"id": "e3", "source": "human_review_1", "target": "output_1", "animated": True},
            ],
        },
    ),

    # ── 14. Due Diligence Automatizada (Multi-Agente) ─────────
    _base(
        name="Due Diligence Automatizada",
        description=(
            "Múltiplos agentes especializados analisam aspectos simultâneos de uma empresa: "
            "corporativo, trabalhista, tributário e regulatório. Inspirado no Harvey Vault Workflows."
        ),
        tags=["due diligence", "paralelo", "multi-agente", "harvey"],
        category="due_diligence",
        output_type="report",
        practice_area="societário",
        graph_json={
            "nodes": [
                {
                    "id": "file_upload_1",
                    "type": "file_upload",
                    "position": {"x": 300, "y": 50},
                    "data": {
                        "label": "Documentos da Empresa",
                        "accepts": ".pdf,.docx,.zip",
                    },
                },
                {
                    "id": "user_input_1",
                    "type": "user_input",
                    "position": {"x": 600, "y": 50},
                    "data": {
                        "label": "Contexto da Operação",
                        "input_type": "text",
                        "collects": "contexto",
                        "placeholder": "Descreva a operação (M&A, investimento, parceria)...",
                    },
                },
                {
                    "id": "parallel_agents_1",
                    "type": "parallel_agents",
                    "position": {"x": 300, "y": 230},
                    "data": {
                        "label": "Análise Multi-Especialista",
                        "prompts": [
                            (
                                "Você é advogado societarista. Analise os documentos corporativos: "
                                "contrato social, atas, quadro societário, procurações. Identifique riscos "
                                "societários, pendências e recomendações.\n\n"
                                "Contexto: {{contexto}}\nDocumentos: {{file_upload_1}}"
                            ),
                            (
                                "Você é advogado trabalhista. Analise riscos trabalhistas: passivo, "
                                "contingências, conformidade com CLT/eSocial, acordos coletivos.\n\n"
                                "Contexto: {{contexto}}\nDocumentos: {{file_upload_1}}"
                            ),
                            (
                                "Você é advogado tributarista. Analise a situação fiscal: certidões, "
                                "regimes tributários, contingências fiscais, planejamento.\n\n"
                                "Contexto: {{contexto}}\nDocumentos: {{file_upload_1}}"
                            ),
                            (
                                "Você é advogado regulatório. Avalie licenças, autorizações, "
                                "compliance setorial (ANVISA/ANATEL/CVM etc.), LGPD.\n\n"
                                "Contexto: {{contexto}}\nDocumentos: {{file_upload_1}}"
                            ),
                        ],
                        "models": ["claude-4.5-sonnet", "gpt-5", "gemini-2.5-pro", "claude-4.5-sonnet"],
                        "tool_names": ["legal_research", "rag_search"],
                        "max_parallel": 4,
                        "aggregation_strategy": "merge",
                    },
                },
                {
                    "id": "prompt_1",
                    "type": "prompt",
                    "position": {"x": 300, "y": 430},
                    "data": {
                        "label": "Consolidar Relatório",
                        "model": "claude-4.5-sonnet",
                        "prompt": (
                            "Consolide os relatórios das 4 análises especializadas em um único "
                            "relatório de Due Diligence estruturado:\n\n"
                            "1. **Sumário Executivo** com visão geral e rating de risco\n"
                            "2. **Análise Societária**\n"
                            "3. **Análise Trabalhista**\n"
                            "4. **Análise Tributária**\n"
                            "5. **Análise Regulatória**\n"
                            "6. **Matriz de Riscos** — tabela consolidada\n"
                            "7. **Recomendações Prioritárias**\n\n"
                            "Relatórios:\n{{parallel_agents_1}}"
                        ),
                    },
                },
                {
                    "id": "output_1",
                    "type": "output",
                    "position": {"x": 300, "y": 600},
                    "data": {"label": "Relatório de Due Diligence", "show_all": True},
                },
            ],
            "edges": [
                {"id": "e1", "source": "file_upload_1", "target": "parallel_agents_1", "animated": True},
                {"id": "e2", "source": "user_input_1", "target": "parallel_agents_1", "animated": True},
                {"id": "e3", "source": "parallel_agents_1", "target": "prompt_1", "animated": True},
                {"id": "e4", "source": "prompt_1", "target": "output_1", "animated": True},
            ],
        },
    ),

    # ── 15. Extrair Dados Estruturados de Contrato ─────────────
    _base(
        name="Extrair Dados Estruturados de Contrato",
        description=(
            "Extrai campos-chave de contratos em formato tabular: partes, datas, "
            "valores, obrigações, garantias. Similar ao Harvey Vault One-Click Workflows."
        ),
        tags=["extração", "dados", "contrato", "tabela", "harvey"],
        category="contracts",
        output_type="table",
        practice_area="contratos",
        graph_json={
            "nodes": [
                {
                    "id": "file_upload_1",
                    "type": "file_upload",
                    "position": {"x": 300, "y": 50},
                    "data": {
                        "label": "Upload do(s) Contrato(s)",
                        "accepts": ".pdf,.docx",
                    },
                },
                {
                    "id": "review_table_1",
                    "type": "review_table",
                    "position": {"x": 300, "y": 220},
                    "data": {
                        "label": "Extrair Campos do Contrato",
                        "model": "claude-4.5-sonnet",
                        "prompt_prefix": (
                            "Extraia os seguintes campos de cada contrato. "
                            "Se um campo não estiver presente, indique 'N/A'."
                        ),
                        "columns": [
                            {"id": "col_1", "name": "Tipo de Contrato", "description": "Classificação (prestação de serviços, compra e venda, locação, etc.)"},
                            {"id": "col_2", "name": "Partes", "description": "Nome completo e CNPJ/CPF de todas as partes"},
                            {"id": "col_3", "name": "Objeto", "description": "Descrição do objeto contratual"},
                            {"id": "col_4", "name": "Valor Total", "description": "Valor total e forma de pagamento"},
                            {"id": "col_5", "name": "Vigência", "description": "Data início, data fim e possibilidade de renovação"},
                            {"id": "col_6", "name": "Garantias", "description": "Tipo de garantia exigida (fiança, seguro, caução)"},
                            {"id": "col_7", "name": "Multa Rescisória", "description": "Valor e condições de multa por rescisão antecipada"},
                            {"id": "col_8", "name": "Foro", "description": "Foro eleito para resolução de disputas"},
                            {"id": "col_9", "name": "Cláusulas Especiais", "description": "Cláusulas não-padrão ou que merecem atenção especial"},
                        ],
                    },
                },
                {
                    "id": "output_1",
                    "type": "output",
                    "position": {"x": 300, "y": 420},
                    "data": {"label": "Dados Extraídos", "show_all": True},
                },
            ],
            "edges": [
                {"id": "e1", "source": "file_upload_1", "target": "review_table_1", "animated": True},
                {"id": "e2", "source": "review_table_1", "target": "output_1", "animated": True},
            ],
        },
    ),

    # ── 16. Assistente de Audiência ────────────────────────────
    _base(
        name="Assistente de Audiência",
        description=(
            "Fluxo completo de preparação pós-audiência: analisa transcrição, "
            "extrai pontos-chave, identifica compromissos e gera relatório."
        ),
        tags=["audiência", "transcrição", "análise", "harvey"],
        category="litigation",
        output_type="report",
        practice_area="contencioso",
        graph_json={
            "nodes": [
                {
                    "id": "file_upload_1",
                    "type": "file_upload",
                    "position": {"x": 300, "y": 50},
                    "data": {
                        "label": "Transcrição da Audiência",
                        "accepts": ".pdf,.docx,.txt,.mp3,.mp4",
                    },
                },
                {
                    "id": "user_input_1",
                    "type": "user_input",
                    "position": {"x": 600, "y": 50},
                    "data": {
                        "label": "Parte Representada",
                        "input_type": "text",
                        "collects": "parte_representada",
                        "placeholder": "Nome da parte que você representa...",
                    },
                },
                {
                    "id": "prompt_1",
                    "type": "prompt",
                    "position": {"x": 300, "y": 230},
                    "data": {
                        "label": "Analisar Transcrição",
                        "model": "claude-4.5-sonnet",
                        "prompt": (
                            "Analise a transcrição da audiência abaixo. Represento a parte: "
                            "**{{parte_representada}}**.\n\n"
                            "Produza:\n"
                            "1. **Resumo da Audiência** — partes presentes, juiz, tipo de audiência, duração\n"
                            "2. **Pontos-Chave por Depoente** — para cada pessoa ouvida:\n"
                            "   - Principais declarações\n"
                            "   - Contradições identificadas\n"
                            "   - Pontos favoráveis ao nosso cliente\n"
                            "   - Pontos desfavoráveis ao nosso cliente\n"
                            "3. **Compromissos e Prazos** — determinações do juiz com datas\n"
                            "4. **Teses Fortalecidas/Enfraquecidas** — impacto na estratégia\n"
                            "5. **Próximos Passos Recomendados** — ações urgentes\n\n"
                            "Transcrição:\n{{file_upload_1}}"
                        ),
                    },
                },
                {
                    "id": "human_review_1",
                    "type": "human_review",
                    "position": {"x": 300, "y": 420},
                    "data": {
                        "label": "Revisão do Advogado",
                        "instructions": "Revise a análise e ajuste os pontos estratégicos.",
                    },
                },
                {
                    "id": "output_1",
                    "type": "output",
                    "position": {"x": 300, "y": 580},
                    "data": {"label": "Relatório de Audiência", "show_all": True},
                },
            ],
            "edges": [
                {"id": "e1", "source": "file_upload_1", "target": "prompt_1", "animated": True},
                {"id": "e2", "source": "user_input_1", "target": "prompt_1", "animated": True},
                {"id": "e3", "source": "prompt_1", "target": "human_review_1", "animated": True},
                {"id": "e4", "source": "human_review_1", "target": "output_1", "animated": True},
            ],
        },
    ),

    # ── 17. Revisão Multi-Agente de Peça Processual ────────────
    _base(
        name="Revisão Multi-Agente de Peça Processual",
        description=(
            "Múltiplos agentes com especialidades diferentes revisam a mesma peça processual "
            "e consolidam feedback. Inspirado no modelo de review do Harvey AI."
        ),
        tags=["revisão", "multi-agente", "peça processual", "harvey"],
        category="litigation",
        output_type="report",
        practice_area="contencioso",
        graph_json={
            "nodes": [
                {
                    "id": "file_upload_1",
                    "type": "file_upload",
                    "position": {"x": 300, "y": 50},
                    "data": {
                        "label": "Peça Processual para Revisão",
                        "accepts": ".pdf,.docx",
                    },
                },
                {
                    "id": "parallel_agents_1",
                    "type": "parallel_agents",
                    "position": {"x": 300, "y": 230},
                    "data": {
                        "label": "Revisores Especializados",
                        "prompts": [
                            (
                                "Você é um revisor de **fundamentação jurídica**. Analise a peça e avalie:\n"
                                "- As teses estão bem fundamentadas?\n"
                                "- A jurisprudência citada é pertinente e atualizada?\n"
                                "- Há lacunas na argumentação?\n"
                                "- Sugestões de melhoria\n\n"
                                "Peça:\n{{file_upload_1}}"
                            ),
                            (
                                "Você é um revisor de **forma e linguagem jurídica**. Analise:\n"
                                "- Clareza e coesão textual\n"
                                "- Adequação do vocabulário técnico\n"
                                "- Erros gramaticais ou de formatação\n"
                                "- Estrutura lógica dos argumentos\n"
                                "- Conformidade com normas de formatação do tribunal\n\n"
                                "Peça:\n{{file_upload_1}}"
                            ),
                            (
                                "Você é um revisor de **estratégia processual**. Avalie:\n"
                                "- A peça atende o objetivo estratégico?\n"
                                "- Há contra-argumentos não endereçados?\n"
                                "- Os pedidos são adequados e completos?\n"
                                "- Riscos de indeferimento ou improcedência\n"
                                "- Pontos fortes e fracos da tese adversária\n\n"
                                "Peça:\n{{file_upload_1}}"
                            ),
                        ],
                        "models": ["claude-4.5-sonnet", "gpt-5", "gemini-2.5-pro"],
                        "tool_names": ["legal_research", "rag_search"],
                        "max_parallel": 3,
                        "aggregation_strategy": "merge",
                    },
                },
                {
                    "id": "prompt_1",
                    "type": "prompt",
                    "position": {"x": 300, "y": 440},
                    "data": {
                        "label": "Consolidar Revisões",
                        "model": "claude-4.5-sonnet",
                        "prompt": (
                            "Consolide as 3 revisões especializadas em um único parecer de revisão:\n\n"
                            "1. **Pontos Fortes** — consenso entre revisores\n"
                            "2. **Problemas Críticos** — questões que múltiplos revisores apontaram\n"
                            "3. **Sugestões de Melhoria** — priorizadas por impacto\n"
                            "4. **Checklist Final** — itens a corrigir antes do protocolo\n\n"
                            "Revisões:\n{{parallel_agents_1}}"
                        ),
                    },
                },
                {
                    "id": "output_1",
                    "type": "output",
                    "position": {"x": 300, "y": 620},
                    "data": {"label": "Parecer de Revisão Consolidado", "show_all": True},
                },
            ],
            "edges": [
                {"id": "e1", "source": "file_upload_1", "target": "parallel_agents_1", "animated": True},
                {"id": "e2", "source": "parallel_agents_1", "target": "prompt_1", "animated": True},
                {"id": "e3", "source": "prompt_1", "target": "output_1", "animated": True},
            ],
        },
    ),
    # ------------------------------------------------------------------
    # 18. Apuração de Risco / Fraude
    # ------------------------------------------------------------------
    _base(
        name="Apuração de Risco e Fraude",
        description=(
            "Workflow de análise de risco e detecção de fraude em documentos "
            "jurídicos. Utiliza agentes paralelos para avaliação multidimensional "
            "(fidelidade, estrutural, cobertura, legal) e consolida um parecer de risco."
        ),
        tags=["risco", "fraude", "auditoria", "compliance", "agente"],
        category="compliance",
        output_type="parecer",
        practice_area="compliance",
        graph_json={
            "nodes": [
                {
                    "id": "file_upload_1",
                    "type": "file_upload",
                    "position": {"x": 300, "y": 0},
                    "data": {
                        "label": "Documento para Análise de Risco",
                        "accepted_types": ".pdf,.docx,.txt",
                    },
                },
                {
                    "id": "user_input_1",
                    "type": "user_input",
                    "position": {"x": 300, "y": 120},
                    "data": {
                        "label": "Contexto Adicional",
                        "placeholder": "Tipo de operação, partes envolvidas, valor em risco...",
                    },
                },
                {
                    "id": "parallel_agents_1",
                    "type": "parallel_agents",
                    "position": {"x": 300, "y": 260},
                    "data": {
                        "label": "Análise Multidimensional de Risco",
                        "prompts": [
                            (
                                "Você é um auditor de **fidelidade documental**. Analise:\n"
                                "- Consistência entre cláusulas e valores declarados\n"
                                "- Contradições internas no documento\n"
                                "- Referências cruzadas incorretas ou ausentes\n"
                                "- Indicadores de adulteração ou manipulação textual\n"
                                "- Score de confiança (VERY_HIGH / HIGH / MEDIUM / LOW / VERY_LOW)\n\n"
                                "Contexto: {{user_input_1}}\n"
                                "Documento:\n{{file_upload_1}}"
                            ),
                            (
                                "Você é um analista de **risco financeiro e operacional**. Avalie:\n"
                                "- Valores atípicos ou incompatíveis com o mercado\n"
                                "- Cláusulas que concentram risco excessivo em uma parte\n"
                                "- Ausência de garantias proporcionais ao risco\n"
                                "- Indicadores de lavagem de dinheiro ou evasão fiscal\n"
                                "- Perfil de risco geral (BAIXO / MÉDIO / ALTO / CRÍTICO)\n\n"
                                "Contexto: {{user_input_1}}\n"
                                "Documento:\n{{file_upload_1}}"
                            ),
                            (
                                "Você é um especialista em **compliance regulatório**. Verifique:\n"
                                "- Conformidade com LGPD, normas do BACEN, CVM e COAF\n"
                                "- Obrigações de KYC/AML atendidas\n"
                                "- Cláusulas obrigatórias presentes ou ausentes\n"
                                "- Exposição regulatória e multas potenciais\n"
                                "- Recomendações de adequação\n\n"
                                "Contexto: {{user_input_1}}\n"
                                "Documento:\n{{file_upload_1}}"
                            ),
                        ],
                        "models": ["claude-4.5-sonnet", "gpt-5", "gemini-2.5-pro"],
                        "tool_names": [
                            "search_legislacao",
                            "search_rag",
                            "verify_citation",
                            "validate_cpc_compliance",
                        ],
                        "max_parallel": 3,
                        "aggregation_strategy": "merge",
                    },
                },
                {
                    "id": "prompt_1",
                    "type": "prompt",
                    "position": {"x": 300, "y": 460},
                    "data": {
                        "label": "Parecer Consolidado de Risco",
                        "model": "claude-4.5-sonnet",
                        "prompt": (
                            "Consolide as 3 análises de risco em um **Parecer de Risco Unificado** com:\n\n"
                            "## 1. Resumo Executivo\n"
                            "Score geral de risco com justificativa.\n\n"
                            "## 2. Riscos Identificados\n"
                            "Tabela: | Risco | Severidade | Probabilidade | Impacto | Mitigação |\n\n"
                            "## 3. Red Flags\n"
                            "Indicadores de fraude ou irregularidade encontrados.\n\n"
                            "## 4. Conformidade Regulatória\n"
                            "Status de conformidade com normas aplicáveis.\n\n"
                            "## 5. Recomendações\n"
                            "Ações prioritárias ordenadas por urgência.\n\n"
                            "Análises:\n{{parallel_agents_1}}"
                        ),
                    },
                },
                {
                    "id": "human_review_1",
                    "type": "human_review",
                    "position": {"x": 300, "y": 640},
                    "data": {
                        "label": "Revisão do Compliance Officer",
                        "instructions": "Revise o parecer de risco e valide os scores atribuídos.",
                    },
                },
                {
                    "id": "output_1",
                    "type": "output",
                    "position": {"x": 300, "y": 800},
                    "data": {"label": "Parecer de Risco Final", "show_all": True},
                },
            ],
            "edges": [
                {"id": "e1", "source": "file_upload_1", "target": "user_input_1", "animated": True},
                {"id": "e2", "source": "user_input_1", "target": "parallel_agents_1", "animated": True},
                {"id": "e3", "source": "parallel_agents_1", "target": "prompt_1", "animated": True},
                {"id": "e4", "source": "prompt_1", "target": "human_review_1", "animated": True},
                {"id": "e5", "source": "human_review_1", "target": "output_1", "animated": True},
            ],
        },
    ),
    # ------------------------------------------------------------------
    # 19. Transcrição e Análise de Audiência / Depoimento
    # ------------------------------------------------------------------
    _base(
        name="Transcrição e Análise Completa",
        description=(
            "Workflow para transcrição de áudio/vídeo de audiências e depoimentos "
            "com análise automática: extração de pontos-chave, referências legais, "
            "identificação de participantes e geração de relatório estruturado."
        ),
        tags=["transcrição", "audiência", "depoimento", "análise", "áudio"],
        category="analise",
        output_type="relatorio",
        practice_area="processual",
        graph_json={
            "nodes": [
                {
                    "id": "file_upload_1",
                    "type": "file_upload",
                    "position": {"x": 300, "y": 0},
                    "data": {
                        "label": "Áudio/Vídeo da Audiência",
                        "accepted_types": ".mp3,.wav,.mp4,.m4a,.ogg,.webm",
                    },
                },
                {
                    "id": "user_input_1",
                    "type": "user_input",
                    "position": {"x": 300, "y": 120},
                    "data": {
                        "label": "Informações do Processo",
                        "placeholder": "Nº do processo, tipo de audiência, partes envolvidas, pontos a observar...",
                    },
                },
                {
                    "id": "claude_agent_1",
                    "type": "claude_agent",
                    "position": {"x": 300, "y": 260},
                    "data": {
                        "label": "Agente de Transcrição e Análise",
                        "agent_type": "claude-agent",
                        "model": "claude-4.5-sonnet",
                        "system_prompt": (
                            "Você é um assistente jurídico especializado em análise de audiências.\n\n"
                            "A partir da transcrição fornecida, produza:\n\n"
                            "## 1. Transcrição Formatada\n"
                            "Com identificação de falantes e timestamps.\n\n"
                            "## 2. Participantes Identificados\n"
                            "Nome, papel (juiz, advogado, parte, testemunha), observações.\n\n"
                            "## 3. Pontos-Chave\n"
                            "Declarações relevantes, admissões, contradições.\n\n"
                            "## 4. Referências Legais Mencionadas\n"
                            "Leis, artigos, jurisprudência citados durante a audiência.\n\n"
                            "## 5. Análise Estratégica\n"
                            "Pontos favoráveis e desfavoráveis para cada parte.\n\n"
                            "## 6. Próximos Passos Sugeridos\n"
                            "Ações recomendadas com base no que foi dito.\n\n"
                            "Informações do processo: {{user_input_1}}\n"
                            "Transcrição/Arquivo: {{file_upload_1}}"
                        ),
                        "tool_names": [
                            "search_jurisprudencia",
                            "search_legislacao",
                            "search_rag",
                            "verify_citation",
                        ],
                        "max_iterations": 10,
                        "max_tokens": 8192,
                        "include_mcp": False,
                        "use_sdk": True,
                        "enable_web_search": False,
                        "enable_deep_research": False,
                        "enable_code_execution": False,
                    },
                },
                {
                    "id": "human_review_1",
                    "type": "human_review",
                    "position": {"x": 300, "y": 440},
                    "data": {
                        "label": "Revisão do Advogado",
                        "instructions": (
                            "Revise a transcrição e análise. Corrija nomes, "
                            "valide pontos-chave e adicione observações."
                        ),
                    },
                },
                {
                    "id": "output_1",
                    "type": "output",
                    "position": {"x": 300, "y": 600},
                    "data": {"label": "Relatório da Audiência", "show_all": True},
                },
            ],
            "edges": [
                {"id": "e1", "source": "file_upload_1", "target": "user_input_1", "animated": True},
                {"id": "e2", "source": "user_input_1", "target": "claude_agent_1", "animated": True},
                {"id": "e3", "source": "claude_agent_1", "target": "human_review_1", "animated": True},
                {"id": "e4", "source": "human_review_1", "target": "output_1", "animated": True},
            ],
        },
    ),
    # ------------------------------------------------------------------
    # 20. Deep Research Jurídico
    # ------------------------------------------------------------------
    _base(
        name="Deep Research Jurídico",
        description=(
            "Pesquisa jurídica aprofundada com múltiplas fontes: bases internas (RAG), "
            "jurisprudência, legislação, web e grafo de conhecimento. "
            "Utiliza agente com deep research e web search habilitados."
        ),
        tags=["pesquisa", "deep-research", "web", "jurisprudência", "legislação", "agente"],
        category="pesquisa",
        output_type="parecer",
        practice_area=None,
        graph_json={
            "nodes": [
                {
                    "id": "user_input_1",
                    "type": "user_input",
                    "position": {"x": 300, "y": 0},
                    "data": {
                        "label": "Pergunta de Pesquisa",
                        "placeholder": "Descreva o tema jurídico a ser pesquisado em profundidade...",
                    },
                },
                {
                    "id": "claude_agent_1",
                    "type": "deep_research",
                    "position": {"x": 300, "y": 140},
                    "data": {
                        "label": "Hard Deep Research",
                        "mode": "hard",
                        "effort": "high",
                        "providers": ["gemini", "perplexity", "openai", "rag_global", "rag_local"],
                        "timeout_per_provider": 120,
                        "total_timeout": 300,
                        "include_sources": True,
                        "query": (
                            "Você é um pesquisador jurídico de elite. Conduza uma pesquisa "
                            "aprofundada e abrangente sobre o tema solicitado.\n\n"
                            "**Metodologia obrigatória:**\n"
                            "1. Busque jurisprudência relevante (STF, STJ, TRFs, TJs)\n"
                            "2. Identifique legislação aplicável (leis, decretos, regulamentos)\n"
                            "3. Consulte o grafo de conhecimento para conexões entre temas\n"
                            "4. Pesquise doutrina e artigos na web\n"
                            "5. Busque nas bases internas do escritório (RAG)\n\n"
                            "**Formato do relatório:**\n\n"
                            "## 1. Resumo da Pesquisa\n"
                            "Síntese dos achados principais.\n\n"
                            "## 2. Legislação Aplicável\n"
                            "Leis e normas vigentes com artigos relevantes.\n\n"
                            "## 3. Jurisprudência\n"
                            "Decisões relevantes organizadas por tribunal e posicionamento.\n\n"
                            "## 4. Doutrina e Referências\n"
                            "Autores, artigos e publicações relevantes.\n\n"
                            "## 5. Análise e Conclusão\n"
                            "Posicionamento predominante e tendências.\n\n"
                            "## 6. Fontes Consultadas\n"
                            "Lista completa com links e referências.\n\n"
                            "Tema: {{user_input_1}}"
                        ),
                    },
                },
                {
                    "id": "human_review_1",
                    "type": "human_review",
                    "position": {"x": 300, "y": 340},
                    "data": {
                        "label": "Revisão do Pesquisador",
                        "instructions": (
                            "Revise a pesquisa. Verifique se as citações estão corretas, "
                            "se a legislação está atualizada e se a análise é consistente."
                        ),
                    },
                },
                {
                    "id": "output_1",
                    "type": "output",
                    "position": {"x": 300, "y": 500},
                    "data": {"label": "Relatório de Pesquisa Aprofundada", "show_all": True},
                },
            ],
            "edges": [
                {"id": "e1", "source": "user_input_1", "target": "claude_agent_1", "animated": True},
                {"id": "e2", "source": "claude_agent_1", "target": "human_review_1", "animated": True},
                {"id": "e3", "source": "human_review_1", "target": "output_1", "animated": True},
            ],
        },
    ),
    # ------------------------------------------------------------------
    # 21. Análise de Grafo Jurídico (Graph Intelligence)
    # ------------------------------------------------------------------
    _base(
        name="Análise de Grafo Jurídico",
        description=(
            "Workflow de inteligência jurídica via grafo de conhecimento (Neo4j). "
            "Usa algoritmos de centralidade, detecção de comunidades, cadeias de precedentes, "
            "argument mining e detecção de sinais de fraude para análise profunda de temas jurídicos."
        ),
        tags=["grafo", "neo4j", "centralidade", "comunidades", "precedentes", "argument-mining", "agente"],
        category="pesquisa",
        output_type="relatorio",
        practice_area=None,
        graph_json={
            "nodes": [
                {
                    "id": "user_input_1",
                    "type": "user_input",
                    "position": {"x": 300, "y": 0},
                    "data": {
                        "label": "Tema / Entidade Jurídica",
                        "placeholder": "Ex: 'Responsabilidade civil por dano ambiental', 'Lei 14.133/2021, Art. 75'",
                    },
                },
                {
                    "id": "parallel_agents_1",
                    "type": "parallel_agents",
                    "position": {"x": 300, "y": 140},
                    "data": {
                        "label": "Análise Multi-Algoritmo do Grafo",
                        "prompts": [
                            (
                                "Você é um analista de **redes de precedentes judiciais**.\n"
                                "Use as ferramentas de grafo para:\n"
                                "1. Encontrar a cadeia de precedentes do tema\n"
                                "2. Identificar decisões mais citadas (PageRank)\n"
                                "3. Mapear a rede de tribunais que decidem sobre o tema\n"
                                "4. Verificar evolução temporal dos entendimentos\n\n"
                                "Formate como relatório com tabelas e referências.\n\n"
                                "Tema: {{user_input_1}}"
                            ),
                            (
                                "Você é um especialista em **análise argumentativa**.\n"
                                "Use as ferramentas de argument mining para:\n"
                                "1. Extrair claims (teses) principais sobre o tema\n"
                                "2. Mapear evidências que suportam/refutam cada tese\n"
                                "3. Construir contexto de debate (pró vs. contra)\n"
                                "4. Identificar lacunas argumentativas\n\n"
                                "Formate como mapa argumentativo estruturado.\n\n"
                                "Tema: {{user_input_1}}"
                            ),
                            (
                                "Você é um analista de **comunidades e conexões jurídicas**.\n"
                                "Use os algoritmos de grafo para:\n"
                                "1. Detectar comunidades temáticas relacionadas (Leiden)\n"
                                "2. Encontrar entidades centrais (centralidade)\n"
                                "3. Verificar co-ocorrências com outros temas\n"
                                "4. Identificar sinais de risco nas conexões\n\n"
                                "Formate como análise de rede com insights.\n\n"
                                "Tema: {{user_input_1}}"
                            ),
                        ],
                        "models": ["claude-4.5-sonnet", "gpt-5", "gemini-2.5-pro"],
                        "tool_names": [
                            "ask_graph",
                            "graph_path",
                            "graph_neighbors",
                            "graph_cooccurrence",
                            "graph_legal_chain",
                            "graph_precedent_network",
                            "graph_fraud_signals",
                            "graph_pagerank",
                            "graph_community_detection",
                            "graph_centrality",
                            "graph_argument_mining",
                            "graph_debate_context",
                            "graph_text2cypher",
                            "search_jurisprudencia",
                            "search_legislacao",
                        ],
                        "max_parallel": 3,
                        "aggregation_strategy": "merge",
                    },
                },
                {
                    "id": "prompt_1",
                    "type": "prompt",
                    "position": {"x": 300, "y": 340},
                    "data": {
                        "label": "Consolidar Inteligência do Grafo",
                        "model": "claude-4.5-sonnet",
                        "prompt": (
                            "Consolide as 3 análises de grafo em um **Relatório de Inteligência Jurídica**:\n\n"
                            "## 1. Mapa de Precedentes\n"
                            "Decisões mais influentes, cadeia de precedentes, evolução temporal.\n\n"
                            "## 2. Mapa Argumentativo\n"
                            "Teses principais (pró e contra), evidências, lacunas.\n\n"
                            "## 3. Análise de Rede\n"
                            "Comunidades temáticas, entidades centrais, co-ocorrências.\n\n"
                            "## 4. Sinais de Atenção\n"
                            "Riscos, inconsistências ou padrões incomuns detectados.\n\n"
                            "## 5. Recomendações Estratégicas\n"
                            "Baseadas na inteligência extraída do grafo.\n\n"
                            "Análises:\n{{parallel_agents_1}}"
                        ),
                    },
                },
                {
                    "id": "output_1",
                    "type": "output",
                    "position": {"x": 300, "y": 520},
                    "data": {"label": "Relatório de Inteligência do Grafo", "show_all": True},
                },
            ],
            "edges": [
                {"id": "e1", "source": "user_input_1", "target": "parallel_agents_1", "animated": True},
                {"id": "e2", "source": "parallel_agents_1", "target": "prompt_1", "animated": True},
                {"id": "e3", "source": "prompt_1", "target": "output_1", "animated": True},
            ],
        },
    ),

    # ── Template 22: Auto-Análise de Email (Outlook → Email Reply) ─────────
    _tpl(
        name="Auto-Análise de Email Jurídico",
        description="Trigger: email recebido no Outlook. Analisa conteúdo com IA e responde automaticamente com classificação, prazos e ações sugeridas.",
        tags=["async", "email", "outlook", "trigger", "auto-analysis"],
        category="general",
        output_type="document",
        graph_json={
            "nodes": [
                {
                    "id": "trigger_1",
                    "type": "trigger",
                    "position": {"x": 300, "y": 40},
                    "data": {
                        "label": "Email Recebido",
                        "trigger_type": "outlook_email",
                        "trigger_config": {"subject_contains": "", "sender_filter": "", "require_attachment": False},
                    },
                },
                {
                    "id": "claude_agent_1",
                    "type": "claude_agent",
                    "position": {"x": 300, "y": 180},
                    "data": {
                        "label": "Analisar Email",
                        "model": "claude-4.5-sonnet",
                        "system_prompt": "Você é um assistente jurídico. Analise o email recebido e retorne: 1) Classificação jurídica, 2) Partes envolvidas, 3) Prazos identificados, 4) Ações sugeridas. Seja conciso e direto.",
                        "prompt": "Analise o seguinte email:\n\nAssunto: @trigger_1.subject\nDe: @trigger_1.sender\n\nConteúdo:\n@trigger_1.body",
                        "tool_names": ["search_legislacao", "search_jurisprudencia", "verify_citation"],
                        "max_iterations": 5,
                        "use_sdk": True,
                    },
                },
                {
                    "id": "delivery_1",
                    "type": "delivery",
                    "position": {"x": 300, "y": 340},
                    "data": {
                        "label": "Responder Email",
                        "delivery_type": "outlook_reply",
                        "delivery_config": {"include_original": True},
                    },
                },
            ],
            "edges": [
                {"id": "e1", "source": "trigger_1", "target": "claude_agent_1", "animated": True},
                {"id": "e2", "source": "claude_agent_1", "target": "delivery_1", "animated": True},
            ],
        },
    ),

    # ── Template 23: Monitor DJEN → Relatório + Prazo no Calendário ────────
    _tpl(
        name="Monitor DJEN com Relatório e Prazo",
        description="Trigger: nova movimentação no DJEN/DataJud. Analisa a intimação, busca jurisprudência relevante e envia relatório por email + cria prazo no calendário.",
        tags=["async", "djen", "datajud", "trigger", "calendar", "email"],
        category="litigation",
        output_type="document",
        graph_json={
            "nodes": [
                {
                    "id": "trigger_1",
                    "type": "trigger",
                    "position": {"x": 300, "y": 40},
                    "data": {
                        "label": "Movimentação DJEN",
                        "trigger_type": "djen_movement",
                        "trigger_config": {"movement_types": ["intimacao", "despacho", "sentenca"]},
                    },
                },
                {
                    "id": "claude_agent_1",
                    "type": "claude_agent",
                    "position": {"x": 300, "y": 180},
                    "data": {
                        "label": "Analisar Intimação",
                        "model": "claude-4.5-sonnet",
                        "system_prompt": "Você é um assistente jurídico especializado em acompanhamento processual. Analise a movimentação e determine: 1) Tipo e urgência, 2) Prazo aplicável (com base legal), 3) Ações necessárias, 4) Jurisprudência relevante.",
                        "prompt": "Processo: @trigger_1.npu\nTipo: @trigger_1.tipo\nTribunal: @trigger_1.tribunal\n\nConteúdo da movimentação:\n@trigger_1.conteudo",
                        "tool_names": ["search_jurisprudencia", "search_legislacao", "search_rag", "consultar_processo_datajud"],
                        "max_iterations": 8,
                        "use_sdk": True,
                    },
                },
                {
                    "id": "delivery_email",
                    "type": "delivery",
                    "position": {"x": 150, "y": 360},
                    "data": {
                        "label": "Enviar Relatório",
                        "delivery_type": "email",
                        "delivery_config": {
                            "to": "",
                            "subject": "DJEN: Nova movimentação em {{trigger_event.npu}}",
                        },
                    },
                },
                {
                    "id": "delivery_calendar",
                    "type": "delivery",
                    "position": {"x": 450, "y": 360},
                    "data": {
                        "label": "Criar Prazo",
                        "delivery_type": "calendar_event",
                        "delivery_config": {
                            "subject": "Prazo: {{trigger_event.npu}}",
                            "duration_minutes": 60,
                            "reminder_minutes": 1440,
                        },
                    },
                },
            ],
            "edges": [
                {"id": "e1", "source": "trigger_1", "target": "claude_agent_1", "animated": True},
                {"id": "e2", "source": "claude_agent_1", "target": "delivery_email", "animated": True},
                {"id": "e3", "source": "claude_agent_1", "target": "delivery_calendar", "animated": True},
            ],
        },
    ),

    # ── Template 24: Minuta por Comando Teams ──────────────────────────────
    _tpl(
        name="Minuta por Comando no Teams",
        description="Trigger: comando /minutar no Teams. Gera minuta jurídica completa e envia o resultado de volta no Teams + por email.",
        tags=["async", "teams", "trigger", "minuta", "legal"],
        category="general",
        output_type="document",
        graph_json={
            "nodes": [
                {
                    "id": "trigger_1",
                    "type": "trigger",
                    "position": {"x": 300, "y": 40},
                    "data": {
                        "label": "Comando Teams",
                        "trigger_type": "teams_command",
                        "trigger_config": {"command": "/minutar"},
                    },
                },
                {
                    "id": "legal_workflow_1",
                    "type": "legal_workflow",
                    "position": {"x": 300, "y": 180},
                    "data": {
                        "label": "Gerar Minuta",
                        "mode": "minuta",
                        "models": ["claude-4.5-sonnet"],
                        "citation_style": "abnt",
                        "auto_approve": True,
                        "thinking_level": "medium",
                    },
                },
                {
                    "id": "delivery_teams",
                    "type": "delivery",
                    "position": {"x": 150, "y": 360},
                    "data": {
                        "label": "Enviar no Teams",
                        "delivery_type": "teams_message",
                        "delivery_config": {"format": "card"},
                    },
                },
                {
                    "id": "delivery_email",
                    "type": "delivery",
                    "position": {"x": 450, "y": 360},
                    "data": {
                        "label": "Enviar por Email",
                        "delivery_type": "email",
                        "delivery_config": {
                            "to": "",
                            "subject": "Minuta gerada: {{trigger_event.text}}",
                            "include_output_attachment": True,
                        },
                    },
                },
            ],
            "edges": [
                {"id": "e1", "source": "trigger_1", "target": "legal_workflow_1", "animated": True},
                {"id": "e2", "source": "legal_workflow_1", "target": "delivery_teams", "animated": True},
                {"id": "e3", "source": "legal_workflow_1", "target": "delivery_email", "animated": True},
            ],
        },
    ),

    # ── Template 25: Pesquisa Agendada Diária ──────────────────────────────
    _tpl(
        name="Relatório Jurídico Matinal",
        description="Trigger: agendamento diário (seg-sex 8h). Pesquisa jurisprudência, DJEN e web, consolida relatório e envia por email.",
        tags=["async", "schedule", "trigger", "research", "email"],
        category="general",
        output_type="document",
        graph_json={
            "nodes": [
                {
                    "id": "trigger_1",
                    "type": "trigger",
                    "position": {"x": 300, "y": 40},
                    "data": {
                        "label": "Agendamento Diário",
                        "trigger_type": "schedule",
                        "trigger_config": {"cron": "0 8 * * 1-5", "timezone": "America/Sao_Paulo"},
                    },
                },
                {
                    "id": "parallel_agents_1",
                    "type": "parallel_agents",
                    "position": {"x": 300, "y": 180},
                    "data": {
                        "label": "Pesquisa Paralela",
                        "prompts": [
                            "Pesquise as principais novidades jurisprudenciais do STF e STJ das últimas 24 horas.",
                            "Pesquise novas publicações legislativas e normas dos últimos 2 dias.",
                            "Pesquise notícias jurídicas relevantes na web das últimas 24 horas.",
                        ],
                        "models": ["claude-4.5-sonnet", "claude-4.5-sonnet", "claude-4.5-sonnet"],
                        "tool_names": ["search_jurisprudencia", "search_legislacao", "web_search", "search_rag"],
                        "max_parallel": 3,
                        "aggregation_strategy": "merge",
                    },
                },
                {
                    "id": "prompt_1",
                    "type": "prompt",
                    "position": {"x": 300, "y": 360},
                    "data": {
                        "label": "Consolidar Relatório",
                        "model": "claude-4.5-sonnet",
                        "prompt": "Com base nas pesquisas abaixo, crie um relatório matinal jurídico conciso e bem estruturado com seções:\n1. Jurisprudência (destaques STF/STJ)\n2. Legislação (novas normas)\n3. Notícias Jurídicas\n\nDados:\n@parallel_agents_1",
                    },
                },
                {
                    "id": "delivery_1",
                    "type": "delivery",
                    "position": {"x": 300, "y": 500},
                    "data": {
                        "label": "Enviar por Email",
                        "delivery_type": "email",
                        "delivery_config": {
                            "to": "",
                            "subject": "Relatório Jurídico Matinal — {{output.date}}",
                        },
                    },
                },
            ],
            "edges": [
                {"id": "e1", "source": "trigger_1", "target": "parallel_agents_1", "animated": True},
                {"id": "e2", "source": "parallel_agents_1", "target": "prompt_1", "animated": True},
                {"id": "e3", "source": "prompt_1", "target": "delivery_1", "animated": True},
            ],
        },
    ),

    # ── Template 26: Webhook de Integração ─────────────────────────────────
    _tpl(
        name="Análise de Documento via Webhook",
        description="Trigger: webhook recebe JSON com documento. Analisa com IA e retorna resultado via webhook de saída.",
        tags=["async", "webhook", "trigger", "api", "integration"],
        category="general",
        output_type="document",
        graph_json={
            "nodes": [
                {
                    "id": "trigger_1",
                    "type": "trigger",
                    "position": {"x": 300, "y": 40},
                    "data": {
                        "label": "Webhook Entrada",
                        "trigger_type": "webhook",
                        "trigger_config": {},
                    },
                },
                {
                    "id": "claude_agent_1",
                    "type": "claude_agent",
                    "position": {"x": 300, "y": 180},
                    "data": {
                        "label": "Analisar Documento",
                        "model": "claude-4.5-sonnet",
                        "system_prompt": "Você é um assistente jurídico especializado em análise documental. Analise o documento recebido e retorne uma análise estruturada em JSON.",
                        "prompt": "Analise o seguinte documento recebido via API:\n\n@trigger_1",
                        "tool_names": ["search_legislacao", "search_jurisprudencia", "search_rag"],
                        "max_iterations": 6,
                        "use_sdk": True,
                    },
                },
                {
                    "id": "delivery_1",
                    "type": "delivery",
                    "position": {"x": 300, "y": 340},
                    "data": {
                        "label": "Webhook Saída",
                        "delivery_type": "webhook_out",
                        "delivery_config": {
                            "url": "",
                            "method": "POST",
                        },
                    },
                },
            ],
            "edges": [
                {"id": "e1", "source": "trigger_1", "target": "claude_agent_1", "animated": True},
                {"id": "e2", "source": "claude_agent_1", "target": "delivery_1", "animated": True},
            ],
        },
    ),

    # ── Template 27: Minuta por Email Outlook (sem HIL) ────────────────────
    _tpl(
        name="Minuta Automática por Email (Outlook)",
        description="Trigger: email recebido no Outlook com filtro configurável. Gera minuta jurídica completa sem intervenção humana (auto_approve) e responde ao email original + envia cópia por email.",
        tags=["async", "outlook", "trigger", "minuta", "legal", "auto-approve"],
        category="general",
        output_type="document",
        graph_json={
            "nodes": [
                {
                    "id": "trigger_1",
                    "type": "trigger",
                    "position": {"x": 300, "y": 40},
                    "data": {
                        "label": "Email Recebido (Outlook)",
                        "trigger_type": "outlook_email",
                        "trigger_config": {
                            "subject_contains": "minuta",
                        },
                    },
                },
                {
                    "id": "legal_workflow_1",
                    "type": "legal_workflow",
                    "position": {"x": 300, "y": 200},
                    "data": {
                        "label": "Gerar Minuta",
                        "mode": "minuta",
                        "models": ["claude-4.5-sonnet"],
                        "citation_style": "abnt",
                        "auto_approve": True,
                        "thinking_level": "medium",
                    },
                },
                {
                    "id": "delivery_reply",
                    "type": "delivery",
                    "position": {"x": 150, "y": 400},
                    "data": {
                        "label": "Responder Email Original",
                        "delivery_type": "outlook_reply",
                        "delivery_config": {
                            "include_original_quote": True,
                            "include_output_attachment": True,
                            "forward_attachments": True,
                        },
                    },
                },
                {
                    "id": "delivery_email",
                    "type": "delivery",
                    "position": {"x": 450, "y": 400},
                    "data": {
                        "label": "Enviar Cópia por Email",
                        "delivery_type": "email",
                        "delivery_config": {
                            "to": "",
                            "subject": "Minuta gerada: {{trigger_event.subject}}",
                            "include_output_attachment": True,
                            "forward_attachments": True,
                        },
                    },
                },
            ],
            "edges": [
                {"id": "e1", "source": "trigger_1", "target": "legal_workflow_1", "animated": True},
                {"id": "e2", "source": "legal_workflow_1", "target": "delivery_reply", "animated": True},
                {"id": "e3", "source": "legal_workflow_1", "target": "delivery_email", "animated": True},
            ],
        },
    ),

    # ── Template 28: Comandos por Email ───────────────────────────────────
    # Três workflows que respondem a comandos estruturados via email:
    # "IUDEX: minutar <tema>" / "IUDEX: pesquisar <tema>" / "IUDEX: analisar"

    # 28a — Minutar por comando
    _tpl(
        name="Comando Email: Minutar (IUDEX: minutar)",
        description=(
            "Trigger: email com assunto 'IUDEX: minutar <tema>'. "
            "Gera minuta jurídica automaticamente e responde ao email com o resultado."
        ),
        tags=["async", "outlook", "trigger", "comando", "minuta", "email-command"],
        category="general",
        output_type="document",
        graph_json={
            "nodes": [
                {
                    "id": "trigger_1",
                    "type": "trigger",
                    "position": {"x": 300, "y": 40},
                    "data": {
                        "label": "Comando: minutar",
                        "trigger_type": "outlook_email",
                        "trigger_config": {
                            "command": "minutar",
                        },
                    },
                },
                {
                    "id": "legal_workflow_1",
                    "type": "legal_workflow",
                    "position": {"x": 300, "y": 200},
                    "data": {
                        "label": "Gerar Minuta",
                        "mode": "minuta",
                        "models": ["claude-4.5-sonnet"],
                        "citation_style": "abnt",
                        "auto_approve": True,
                        "thinking_level": "medium",
                    },
                },
                {
                    "id": "delivery_reply",
                    "type": "delivery",
                    "position": {"x": 300, "y": 400},
                    "data": {
                        "label": "Responder Email",
                        "delivery_type": "outlook_reply",
                        "delivery_config": {
                            "include_original_quote": True,
                            "include_output_attachment": True,
                            "forward_attachments": True,
                        },
                    },
                },
            ],
            "edges": [
                {"id": "e1", "source": "trigger_1", "target": "legal_workflow_1", "animated": True},
                {"id": "e2", "source": "legal_workflow_1", "target": "delivery_reply", "animated": True},
            ],
        },
    ),

    # 28b — Pesquisar por comando
    _tpl(
        name="Comando Email: Pesquisar (IUDEX: pesquisar)",
        description=(
            "Trigger: email com assunto 'IUDEX: pesquisar <tema>'. "
            "Pesquisa jurisprudencia e legislacao, responde ao email com relatório."
        ),
        tags=["async", "outlook", "trigger", "comando", "pesquisa", "email-command"],
        category="general",
        output_type="text",
        graph_json={
            "nodes": [
                {
                    "id": "trigger_1",
                    "type": "trigger",
                    "position": {"x": 300, "y": 40},
                    "data": {
                        "label": "Comando: pesquisar",
                        "trigger_type": "outlook_email",
                        "trigger_config": {
                            "command": "pesquisar",
                        },
                    },
                },
                {
                    "id": "agent_1",
                    "type": "claude_agent",
                    "position": {"x": 300, "y": 200},
                    "data": {
                        "label": "Pesquisa Juridica",
                        "system_prompt": (
                            "Voce e um pesquisador juridico. Recebeu um comando por email para pesquisar sobre o tema indicado. "
                            "Use as ferramentas de busca para encontrar jurisprudencia relevante, legislacao aplicavel e doutrina. "
                            "Produza um relatorio estruturado com: (1) Jurisprudencia encontrada, (2) Legislacao aplicavel, "
                            "(3) Analise e recomendacoes. O tema esta em: {{trigger_event.parsed_command.command_args}}"
                        ),
                        "models": ["claude-4.5-sonnet"],
                        "thinking_level": "medium",
                    },
                },
                {
                    "id": "delivery_reply",
                    "type": "delivery",
                    "position": {"x": 300, "y": 400},
                    "data": {
                        "label": "Responder Email",
                        "delivery_type": "outlook_reply",
                        "delivery_config": {
                            "include_original_quote": True,
                        },
                    },
                },
            ],
            "edges": [
                {"id": "e1", "source": "trigger_1", "target": "agent_1", "animated": True},
                {"id": "e2", "source": "agent_1", "target": "delivery_reply", "animated": True},
            ],
        },
    ),

    # 28c — Analisar documento por comando
    _tpl(
        name="Comando Email: Analisar (IUDEX: analisar)",
        description=(
            "Trigger: email com assunto 'IUDEX: analisar' e documento em anexo. "
            "Analisa o documento anexado e responde com parecer detalhado."
        ),
        tags=["async", "outlook", "trigger", "comando", "analise", "email-command"],
        category="general",
        output_type="text",
        graph_json={
            "nodes": [
                {
                    "id": "trigger_1",
                    "type": "trigger",
                    "position": {"x": 300, "y": 40},
                    "data": {
                        "label": "Comando: analisar",
                        "trigger_type": "outlook_email",
                        "trigger_config": {
                            "command": "analisar",
                            "require_attachment": True,
                        },
                    },
                },
                {
                    "id": "agent_1",
                    "type": "claude_agent",
                    "position": {"x": 300, "y": 200},
                    "data": {
                        "label": "Analisar Documento",
                        "system_prompt": (
                            "Voce e um analista juridico. Recebeu um documento por email para analise. "
                            "Analise o documento anexado e produza: (1) Resumo executivo, (2) Pontos criticos identificados, "
                            "(3) Riscos juridicos, (4) Recomendacoes. Se houver instrucoes adicionais no corpo do email, siga-as."
                        ),
                        "models": ["claude-4.5-sonnet"],
                        "thinking_level": "high",
                    },
                },
                {
                    "id": "delivery_reply",
                    "type": "delivery",
                    "position": {"x": 300, "y": 400},
                    "data": {
                        "label": "Responder Email",
                        "delivery_type": "outlook_reply",
                        "delivery_config": {
                            "include_original_quote": True,
                            "forward_attachments": True,
                        },
                    },
                },
            ],
            "edges": [
                {"id": "e1", "source": "trigger_1", "target": "agent_1", "animated": True},
                {"id": "e2", "source": "agent_1", "target": "delivery_reply", "animated": True},
            ],
        },
    ),

    # ── Template 31: Radar de Processo (CNJ + DJEN) ────────────────────────
    _tpl(
        name="Radar de Processo (CNJ + DJEN)",
        description=(
            "Informe um NPU e, opcionalmente, tribunal e recorte temporal. "
            "O agente consulta DataJud + DJEN e devolve um relatório com status, "
            "movimentações recentes, prazos prováveis e próximos passos."
        ),
        tags=["cnj", "datajud", "djen", "monitoramento", "processo"],
        category="litigation",
        output_type="document",
        graph_json={
            "nodes": [
                {
                    "id": "user_input_1",
                    "type": "user_input",
                    "position": {"x": 300, "y": 40},
                    "data": {
                        "label": "NPU + Contexto",
                        "collects": "input",
                        "input_type": "text",
                        "placeholder": "Ex: NPU 0001234-56.2024.8.26.0100 (TJSP). Últimos 30 dias. Objetivo: identificar prazo e providências.",
                    },
                },
                {
                    "id": "claude_agent_1",
                    "type": "claude_agent",
                    "position": {"x": 300, "y": 200},
                    "data": {
                        "label": "Consultar + Consolidar",
                        "model": "claude-4.5-sonnet",
                        "system_prompt": (
                            "Você é um advogado processualista e analista de acompanhamento. "
                            "Extraia do texto do usuário: NPU, tribunal (se houver), recorte temporal e objetivo. "
                            "Use as tools para obter metadados oficiais e publicações. "
                            "Ao final, entregue:\n"
                            "1) Status do processo (classe, assuntos, partes, órgão, valor)\n"
                            "2) Movimentações recentes e publicações DJEN (com datas)\n"
                            "3) Hipóteses de prazo/ponto de atenção (explique o porquê)\n"
                            "4) Próximas providências recomendadas (checklist)\n"
                            "5) Sugestão de evento de calendário (título + data) se aplicável.\n\n"
                            "Se algum dado estiver ausente, peça somente o mínimo necessário."
                        ),
                        "prompt": "Entrada do usuário:\n{input}",
                        "tool_names": [
                            "consultar_processo_datajud",
                            "buscar_publicacoes_djen",
                            "search_jurisprudencia",
                            "search_legislacao",
                        ],
                        "max_iterations": 10,
                        "max_tokens": 8192,
                        "include_mcp": False,
                        "use_sdk": True,
                    },
                },
                {
                    "id": "output_1",
                    "type": "output",
                    "position": {"x": 300, "y": 360},
                    "data": {"label": "Relatório (CNJ + DJEN)", "show_all": True},
                },
            ],
            "edges": [
                {"id": "e1", "source": "user_input_1", "target": "claude_agent_1", "animated": True},
                {"id": "e2", "source": "claude_agent_1", "target": "output_1", "animated": True},
            ],
        },
    ),

    # ── Template 32: Protocolo Assistido (PJe/e-Proc) ──────────────────────
    # Nota: a engine de workflow não injeta bytes de uploads automaticamente em tools.
    # Este template assume que o usuário fornecerá o PDF em base64 no input.
    _tpl(
        name="Protocolo Assistido (PJe/e-Proc) — Base64",
        description=(
            "Protocola um documento em processo eletrônico (PJe/e-Proc) via tool 'protocolar_documento'. "
            "Requer que o conteúdo do PDF seja fornecido em base64 no input (limitação atual da engine)."
        ),
        tags=["tribunais", "pje", "eproc", "protocolo", "peticionamento"],
        category="litigation",
        output_type="document",
        graph_json={
            "nodes": [
                {
                    "id": "user_input_1",
                    "type": "user_input",
                    "position": {"x": 300, "y": 40},
                    "data": {
                        "label": "Dados do Protocolo + PDF (base64)",
                        "collects": "input",
                        "input_type": "text",
                        "placeholder": (
                            "Informe:\n"
                            "NPU: ...\nTribunal: ...\nSistema: pje|eproc\n"
                            "Tipo_documento: ...\nDescricao: ...\n"
                            "Arquivo_base64: (cole aqui)\n"
                        ),
                    },
                },
                {
                    "id": "claude_agent_1",
                    "type": "claude_agent",
                    "position": {"x": 300, "y": 200},
                    "data": {
                        "label": "Preparar JSON de Protocolo",
                        "model": "claude-4.5-sonnet",
                        "system_prompt": (
                            "Extraia do input os campos: numero_processo (NPU), tribunal, sistema, "
                            "tipo_documento, descricao e arquivo_base64. "
                            "Retorne um JSON estrito com essas chaves para protocolo."
                        ),
                        "prompt": "{input}",
                        "tool_names": [],
                        "max_iterations": 3,
                        "max_tokens": 2048,
                        "include_mcp": False,
                        "use_sdk": True,
                    },
                },
                {
                    "id": "human_review_1",
                    "type": "human_review",
                    "position": {"x": 300, "y": 340},
                    "data": {
                        "label": "Confirmação",
                        "instructions": "Confira o JSON gerado e confirme se os campos estão corretos antes do protocolo.",
                    },
                },
                {
                    "id": "claude_agent_2",
                    "type": "claude_agent",
                    "position": {"x": 300, "y": 480},
                    "data": {
                        "label": "Protocolar Documento",
                        "model": "claude-4.5-sonnet",
                        "system_prompt": (
                            "Você vai executar um protocolo. "
                            "Leia o JSON a seguir e chame a tool protocolar_documento com os argumentos. "
                            "Depois, devolva um resumo com status, número/recibo e próximos passos.\n\n"
                            "JSON:\n{{claude_agent_1}}"
                        ),
                        "prompt": "Execute o protocolo com base no JSON acima.",
                        "tool_names": ["protocolar_documento"],
                        "max_iterations": 6,
                        "max_tokens": 4096,
                        "include_mcp": False,
                        "use_sdk": True,
                    },
                },
                {
                    "id": "output_1",
                    "type": "output",
                    "position": {"x": 300, "y": 640},
                    "data": {"label": "Resultado do Protocolo", "show_all": True},
                },
            ],
            "edges": [
                {"id": "e1", "source": "user_input_1", "target": "claude_agent_1", "animated": True},
                {"id": "e2", "source": "claude_agent_1", "target": "human_review_1", "animated": True},
                {"id": "e3", "source": "human_review_1", "target": "claude_agent_2", "animated": True},
                {"id": "e4", "source": "claude_agent_2", "target": "output_1", "animated": True},
            ],
        },
    ),

    # ── Template 33: Auditoria de Vínculo (Grafo Risk: Edge) ───────────────
    _tpl(
        name="Auditar Vínculo Suspeito (Grafo)",
        description=(
            "Audita a evidência entre duas entidades no grafo: aresta direta e co-menções em docs/chunks. "
            "Resolve IDs via busca no grafo quando necessário."
        ),
        tags=["grafo", "risco", "fraude", "auditoria", "evidência"],
        category="financial",
        output_type="document",
        graph_json={
            "nodes": [
                {
                    "id": "user_input_1",
                    "type": "user_input",
                    "position": {"x": 300, "y": 40},
                    "data": {
                        "label": "Entidades (IDs ou nomes) + objetivo",
                        "collects": "input",
                        "input_type": "text",
                        "placeholder": "Ex: 'Auditar ligação entre Empresa X e Pessoa Y (suspeita de conflito). Se não souber IDs, informe nomes completos.'",
                    },
                },
                {
                    "id": "claude_agent_1",
                    "type": "claude_agent",
                    "position": {"x": 300, "y": 200},
                    "data": {
                        "label": "Auditar Edge",
                        "model": "claude-4.5-sonnet",
                        "system_prompt": (
                            "Você é um analista de risco relacional. "
                            "Objetivo: auditar a relação entre duas entidades com evidência rastreável. "
                            "Se o usuário não forneceu IDs, use ask_graph(operation=search) para encontrar os entity_ids corretos. "
                            "Então use audit_graph_edge(source_id,target_id) e gere:\n"
                            "1) Resultado (tem aresta? tem co-menções?)\n"
                            "2) Evidências (docs/chunks amostrados)\n"
                            "3) Interpretação e riscos\n"
                            "4) Próximas verificações recomendadas.\n"
                        ),
                        "prompt": "{input}",
                        "tool_names": ["ask_graph", "audit_graph_edge"],
                        "max_iterations": 10,
                        "max_tokens": 8192,
                        "include_mcp": False,
                        "use_sdk": True,
                    },
                },
                {
                    "id": "output_1",
                    "type": "output",
                    "position": {"x": 300, "y": 360},
                    "data": {"label": "Auditoria (Edge)", "show_all": True},
                },
            ],
            "edges": [
                {"id": "e1", "source": "user_input_1", "target": "claude_agent_1", "animated": True},
                {"id": "e2", "source": "claude_agent_1", "target": "output_1", "animated": True},
            ],
        },
    ),

    # ── Template 34: Auditoria de Cadeia (Grafo Risk: Chain) ───────────────
    _tpl(
        name="Auditar Cadeia (Grafo) — Caminhos e Evidências",
        description=(
            "Encontra e audita cadeia(s) entre duas entidades (multi-hop) e explica o caminho com evidências quando disponíveis."
        ),
        tags=["grafo", "cadeia", "risk", "fraude", "multi-hop"],
        category="financial",
        output_type="document",
        graph_json={
            "nodes": [
                {
                    "id": "user_input_1",
                    "type": "user_input",
                    "position": {"x": 300, "y": 40},
                    "data": {
                        "label": "Entidades (IDs ou nomes) + restrições",
                        "collects": "input",
                        "input_type": "text",
                        "placeholder": "Ex: 'Cadeia entre Pessoa A e Empresa B. Max hops 4. Considerar apenas tenant (private).' ",
                    },
                },
                {
                    "id": "claude_agent_1",
                    "type": "claude_agent",
                    "position": {"x": 300, "y": 200},
                    "data": {
                        "label": "Auditar Chain",
                        "model": "claude-4.5-sonnet",
                        "system_prompt": (
                            "Você é um analista investigativo. "
                            "Se não houver IDs, resolva via ask_graph(search). "
                            "Use audit_graph_chain para obter caminhos. "
                            "Entregue: caminhos, interpretação, pontos de fragilidade e próximos passos.\n"
                            "Se o usuário pedir escopo, use scope=private/local e include_global conforme indicado."
                        ),
                        "prompt": "{input}",
                        "tool_names": ["ask_graph", "audit_graph_chain"],
                        "max_iterations": 10,
                        "max_tokens": 8192,
                        "include_mcp": False,
                        "use_sdk": True,
                    },
                },
                {
                    "id": "output_1",
                    "type": "output",
                    "position": {"x": 300, "y": 360},
                    "data": {"label": "Auditoria (Chain)", "show_all": True},
                },
            ],
            "edges": [
                {"id": "e1", "source": "user_input_1", "target": "claude_agent_1", "animated": True},
                {"id": "e2", "source": "claude_agent_1", "target": "output_1", "animated": True},
            ],
        },
    ),

    # ── Template 35: Scan de Risco/Fraude (GraphRisk) ──────────────────────
    _tpl(
        name="Scan de Risco/Fraude (Grafo) — Relatório",
        description=(
            "Executa scan determinístico de risco/fraude no grafo (multi-cenário) e gera relatório priorizado. "
            "Útil para varredura inicial ou monitoramento periódico."
        ),
        tags=["grafo", "risco", "fraude", "scan", "monitoramento"],
        category="financial",
        output_type="document",
        graph_json={
            "nodes": [
                {
                    "id": "user_input_1",
                    "type": "user_input",
                    "position": {"x": 300, "y": 40},
                    "data": {
                        "label": "Contexto e parâmetros (opcional)",
                        "collects": "input",
                        "input_type": "text",
                        "placeholder": "Ex: 'Perfil recall, focar em cenários de conflito de interesse. Escopo private. Top 50.'",
                        "optional": True,
                        "default_text": "Use profile=balanced, scope=private, limit=30 e inclua recomendações de mitigação.",
                    },
                },
                {
                    "id": "claude_agent_1",
                    "type": "claude_agent",
                    "position": {"x": 300, "y": 200},
                    "data": {
                        "label": "Executar Scan + Resumir",
                        "model": "claude-4.5-sonnet",
                        "system_prompt": (
                            "Você é um auditor de risco. "
                            "Interprete os parâmetros do usuário (profile, scenarios, limit, scope, include_global). "
                            "Execute scan_graph_risk com os melhores defaults quando não especificado. "
                            "Produza um relatório com: top sinais, entidades foco, evidências resumidas, "
                            "nível de confiança e ações recomendadas."
                        ),
                        "prompt": "{input}",
                        "tool_names": ["scan_graph_risk"],
                        "max_iterations": 8,
                        "max_tokens": 8192,
                        "include_mcp": False,
                        "use_sdk": True,
                    },
                },
                {
                    "id": "output_1",
                    "type": "output",
                    "position": {"x": 300, "y": 360},
                    "data": {"label": "Relatório de Risco/Fraude", "show_all": True},
                },
            ],
            "edges": [
                {"id": "e1", "source": "user_input_1", "target": "claude_agent_1", "animated": True},
                {"id": "e2", "source": "claude_agent_1", "target": "output_1", "animated": True},
            ],
        },
    ),

    # ── Template 36: DJEN em Lote (manual) ─────────────────────────────────
    _tpl(
        name="DJEN em Lote — Varredura de Publicações",
        description=(
            "Recebe uma lista de NPUs e varre publicações no DJEN por processo, "
            "gerando tabela de intimações/despachos/sentenças com ações sugeridas."
        ),
        tags=["djen", "lote", "publicações", "processos", "monitoramento"],
        category="litigation",
        output_type="table",
        graph_json={
            "nodes": [
                {
                    "id": "user_input_1",
                    "type": "user_input",
                    "position": {"x": 300, "y": 40},
                    "data": {
                        "label": "Lista de NPUs + filtros",
                        "collects": "input",
                        "input_type": "text",
                        "placeholder": "Cole NPUs (um por linha). Opcional: tribunal e período (data_inicio/data_fim).",
                    },
                },
                {
                    "id": "claude_agent_1",
                    "type": "claude_agent",
                    "position": {"x": 300, "y": 200},
                    "data": {
                        "label": "Buscar no DJEN",
                        "model": "claude-4.5-sonnet",
                        "system_prompt": (
                            "Você vai varrer NPUs no DJEN. "
                            "Extraia os NPUs do texto (um por linha) e quaisquer filtros (tribunal, data_inicio, data_fim). "
                            "Para cada NPU, chame buscar_publicacoes_djen e consolide os resultados em tabela:\n"
                            "NPU | Data | Tipo | Trecho/Resumo | Ação sugerida | Urgência.\n"
                            "Se não houver publicações, indique 'sem publicações' por NPU."
                        ),
                        "prompt": "{input}",
                        "tool_names": ["buscar_publicacoes_djen"],
                        "max_iterations": 12,
                        "max_tokens": 8192,
                        "include_mcp": False,
                        "use_sdk": True,
                    },
                },
                {
                    "id": "output_1",
                    "type": "output",
                    "position": {"x": 300, "y": 360},
                    "data": {"label": "Tabela DJEN (lote)", "show_all": True},
                },
            ],
            "edges": [
                {"id": "e1", "source": "user_input_1", "target": "claude_agent_1", "animated": True},
                {"id": "e2", "source": "claude_agent_1", "target": "output_1", "animated": True},
            ],
        },
    ),

    # ── Template 37: QA de Peça (CPC + Citações) ───────────────────────────
    _tpl(
        name="QA de Peça (CPC + Citações) — Checklist",
        description=(
            "Revisa uma peça com checks determinísticos do CPC e verificação de citações. "
            "Entrega checklist de conformidade, alertas e recomendações de melhoria."
        ),
        tags=["qa", "cpc", "citações", "revisão", "peça"],
        category="litigation",
        output_type="document",
        graph_json={
            "nodes": [
                {
                    "id": "user_input_1",
                    "type": "user_input",
                    "position": {"x": 300, "y": 40},
                    "data": {
                        "label": "Cole o texto da peça",
                        "collects": "input",
                        "input_type": "text",
                        "placeholder": "Cole aqui a peça completa (petição/contestação/recurso).",
                    },
                },
                {
                    "id": "claude_agent_1",
                    "type": "claude_agent",
                    "position": {"x": 300, "y": 200},
                    "data": {
                        "label": "Auditar CPC + Citações",
                        "model": "claude-4.5-sonnet",
                        "system_prompt": (
                            "Você é um revisor jurídico. "
                            "1) Execute validate_cpc_compliance(document_text, document_type=auto). "
                            "2) Extraia as principais citações (jurisprudência/leis) e use verify_citation nos itens críticos. "
                            "3) Se necessário, consulte search_legislacao/search_jurisprudencia para contextualizar.\n\n"
                            "Entregue:\n"
                            "- Checklist CPC (pass/warn/fail)\n"
                            "- Lista de citações verificadas (ok/duvidosa) + recomendações\n"
                            "- Melhorias de estrutura e estratégia (curto, direto)\n"
                            "- Riscos de indeferimento/inépcia quando aplicável."
                        ),
                        "prompt": "{input}",
                        "tool_names": ["validate_cpc_compliance", "verify_citation", "search_legislacao", "search_jurisprudencia"],
                        "max_iterations": 12,
                        "max_tokens": 8192,
                        "include_mcp": False,
                        "use_sdk": True,
                    },
                },
                {
                    "id": "output_1",
                    "type": "output",
                    "position": {"x": 300, "y": 360},
                    "data": {"label": "Relatório QA", "show_all": True},
                },
            ],
            "edges": [
                {"id": "e1", "source": "user_input_1", "target": "claude_agent_1", "animated": True},
                {"id": "e2", "source": "claude_agent_1", "target": "output_1", "animated": True},
            ],
        },
    ),

    # ── Template 38: Mini-KG (extração manual + escrita opcional) ──────────
    _tpl(
        name="Mini-KG: Extrair Entidades e (Opcional) Escrever no Grafo",
        description=(
            "Extrai entidades e relações de um texto/documento e, após revisão humana, "
            "tenta escrever essas relações no grafo via ask_graph(operation=link_entities). "
            "Use com cuidado (write-path)."
        ),
        tags=["kg", "grafo", "entidades", "relações", "beta"],
        category="general",
        output_type="document",
        graph_json={
            "nodes": [
                {
                    "id": "user_input_1",
                    "type": "user_input",
                    "position": {"x": 300, "y": 40},
                    "data": {
                        "label": "Texto base (ou resumo do documento)",
                        "collects": "input",
                        "input_type": "text",
                        "placeholder": "Cole um trecho/relatório/peça a partir do qual extrair entidades e relações.",
                    },
                },
                {
                    "id": "claude_agent_1",
                    "type": "claude_agent",
                    "position": {"x": 300, "y": 200},
                    "data": {
                        "label": "Extrair Entidades + Relações (JSON)",
                        "model": "claude-4.5-sonnet",
                        "system_prompt": (
                            "Extraia entidades e relações do texto. Retorne JSON estrito no formato:\n"
                            "{\n"
                            "  \"entities\": [{\"name\": \"...\", \"entity_type\": \"...\", \"external_id\": \"\"}],\n"
                            "  \"edges\": [{\"source\": \"<entity name>\", \"target\": \"<entity name>\", \"rel_type\": \"...\", \"evidence\": \"...\"}]\n"
                            "}\n"
                            "Use entity_type coerente (pessoa, empresa, tribunal, lei, artigo, processo, fato)."
                        ),
                        "prompt": "{input}",
                        "tool_names": [],
                        "max_iterations": 4,
                        "max_tokens": 4096,
                        "include_mcp": False,
                        "use_sdk": True,
                    },
                },
                {
                    "id": "human_review_1",
                    "type": "human_review",
                    "position": {"x": 300, "y": 340},
                    "data": {
                        "label": "Revisão (antes de escrever no grafo)",
                        "instructions": "Revise o JSON. Se estiver OK, aprove para tentar escrever no grafo. Se não quiser escrever, rejeite e use apenas o relatório.",
                    },
                },
                {
                    "id": "claude_agent_2",
                    "type": "claude_agent",
                    "position": {"x": 300, "y": 480},
                    "data": {
                        "label": "Escrever no Grafo (opcional)",
                        "model": "claude-4.5-sonnet",
                        "system_prompt": (
                            "Tente escrever as entidades/arestas no grafo.\n"
                            "Use ask_graph com operation=link_entities e params contendo entities/edges.\n"
                            "Se falhar por permissão/validação, apenas explique como ajustar o JSON.\n\n"
                            "JSON:\n{{claude_agent_1}}"
                        ),
                        "prompt": "Execute link_entities com base no JSON acima.",
                        "tool_names": ["ask_graph"],
                        "max_iterations": 6,
                        "max_tokens": 4096,
                        "include_mcp": False,
                        "use_sdk": True,
                    },
                },
                {
                    "id": "output_1",
                    "type": "output",
                    "position": {"x": 300, "y": 640},
                    "data": {"label": "Relatório + (se aplicável) Resultado de Escrita", "show_all": True},
                },
            ],
            "edges": [
                {"id": "e1", "source": "user_input_1", "target": "claude_agent_1", "animated": True},
                {"id": "e2", "source": "claude_agent_1", "target": "human_review_1", "animated": True},
                {"id": "e3", "source": "human_review_1", "target": "claude_agent_2", "animated": True},
                {"id": "e4", "source": "claude_agent_2", "target": "output_1", "animated": True},
            ],
        },
    ),

    # ── Template 39: POC Aura Agent Parity (manual) ────────────────────────
    _tpl(
        name="POC Aura Agent — Comparação (manual)",
        description=(
            "Template operacional para comparar resultados de consultas do grafo (Iudex) vs Aura Agent (manual). "
            "Cole os dois outputs e gere um diff estruturado."
        ),
        tags=["aura", "poc", "grafo", "comparação", "manual"],
        category="general",
        output_type="document",
        graph_json={
            "nodes": [
                {
                    "id": "user_input_1",
                    "type": "user_input",
                    "position": {"x": 300, "y": 40},
                    "data": {
                        "label": "Cole outputs (Iudex vs Aura)",
                        "collects": "input",
                        "input_type": "text",
                        "placeholder": "Cole aqui: (1) resultado do Iudex, (2) resultado do Aura. Ideal: JSON ou tabelas.",
                    },
                },
                {
                    "id": "prompt_1",
                    "type": "prompt",
                    "position": {"x": 300, "y": 200},
                    "data": {
                        "label": "Gerar Diff",
                        "model": "claude-4.5-sonnet",
                        "prompt": (
                            "Você é um engenheiro de avaliação. Compare os dois outputs colados.\n\n"
                            "Retorne um relatório com:\n"
                            "- Overlap (itens comuns)\n"
                            "- Divergências (itens presentes em um e ausentes no outro)\n"
                            "- Erros aparentes / alucinações\n"
                            "- Recomendações de guardrails, allowlists e métricas de paridade.\n\n"
                            "Dados:\n{input}"
                        ),
                    },
                },
                {
                    "id": "output_1",
                    "type": "output",
                    "position": {"x": 300, "y": 360},
                    "data": {"label": "Relatório de Paridade", "show_all": True},
                },
            ],
            "edges": [
                {"id": "e1", "source": "user_input_1", "target": "prompt_1", "animated": True},
                {"id": "e2", "source": "prompt_1", "target": "output_1", "animated": True},
            ],
        },
    ),

    # ── Template 40: Alerta ao Cliente (legislação/jurisprudência/web) ─────
    _tpl(
        name="Alerta ao Cliente — Mudanças Normativas e Jurisprudenciais",
        description=(
            "Gera um alerta (newsletter) a partir de pesquisa em legislação, jurisprudência e web. "
            "Pode ser usado manualmente ou acoplado a schedule trigger após instalação."
        ),
        tags=["newsletter", "cliente", "alerta", "jurisprudência", "legislação", "web"],
        category="general",
        output_type="document",
        graph_json={
            "nodes": [
                {
                    "id": "user_input_1",
                    "type": "user_input",
                    "position": {"x": 300, "y": 40},
                    "data": {
                        "label": "Tema + público + recorte",
                        "collects": "input",
                        "input_type": "text",
                        "placeholder": "Ex: 'DORA e cibersegurança. Público: diretoria. Últimos 7 dias. Jurisdição: Brasil/UE.'",
                    },
                },
                {
                    "id": "parallel_agents_1",
                    "type": "parallel_agents",
                    "position": {"x": 300, "y": 200},
                    "data": {
                        "label": "Pesquisa Paralela",
                        "prompts": [
                            "Pesquise jurisprudência relevante (STF/STJ e tribunais) sobre o tema: {input}",
                            "Pesquise legislação/normas recentes e vigentes relacionadas ao tema: {input}",
                            "Pesquise na web notícias e comunicados oficiais sobre o tema: {input}",
                        ],
                        "models": ["claude-4.5-sonnet", "claude-4.5-sonnet", "claude-4.5-sonnet"],
                        "tool_names": ["search_jurisprudencia", "search_legislacao", "web_search"],
                        "max_parallel": 3,
                        "aggregation_strategy": "concat",
                        "use_sdk": True,
                    },
                },
                {
                    "id": "prompt_1",
                    "type": "prompt",
                    "position": {"x": 300, "y": 360},
                    "data": {
                        "label": "Escrever Alerta",
                        "model": "claude-4.5-sonnet",
                        "prompt": (
                            "Com base nas pesquisas abaixo, escreva um alerta ao cliente com:\n"
                            "1) O que mudou\n2) Impacto prático\n3) Recomendações\n4) Fontes consultadas\n\n"
                            "Pesquisas:\n{{parallel_agents_1}}"
                        ),
                    },
                },
                {
                    "id": "output_1",
                    "type": "output",
                    "position": {"x": 300, "y": 520},
                    "data": {"label": "Alerta ao Cliente", "show_all": True},
                },
            ],
            "edges": [
                {"id": "e1", "source": "user_input_1", "target": "parallel_agents_1", "animated": True},
                {"id": "e2", "source": "parallel_agents_1", "target": "prompt_1", "animated": True},
                {"id": "e3", "source": "prompt_1", "target": "output_1", "animated": True},
            ],
        },
    ),

    # ── Template 41: Matriz de Cláusulas (contratos) ───────────────────────
    _tpl(
        name="Matriz de Cláusulas — Contratos (Tabela)",
        description=(
            "Extrai campos-chave de um contrato e organiza em tabela (partes, objeto, vigência, "
            "rescisão, multa, garantias, foro, reajuste, limitação)."
        ),
        tags=["contratos", "tabela", "cláusulas", "extração"],
        category="transactional",
        output_type="table",
        graph_json={
            "nodes": [
                {
                    "id": "file_upload_1",
                    "type": "file_upload",
                    "position": {"x": 300, "y": 40},
                    "data": {"label": "Upload do Contrato", "accepts": ".pdf,.docx,.txt"},
                },
                {
                    "id": "review_table_1",
                    "type": "review_table",
                    "position": {"x": 300, "y": 200},
                    "data": {
                        "label": "Extrair Campos",
                        "model": "claude-4.5-sonnet",
                        "columns": [
                            {"id": "partes", "name": "Partes", "description": "Quem são as partes e qualificações."},
                            {"id": "objeto", "name": "Objeto", "description": "Objeto do contrato."},
                            {"id": "valor", "name": "Valor", "description": "Preço/valor e forma de pagamento."},
                            {"id": "vigencia", "name": "Vigência", "description": "Prazo, renovação e início."},
                            {"id": "rescisao", "name": "Rescisão", "description": "Hipóteses e avisos."},
                            {"id": "multa", "name": "Multa", "description": "Multas e penalidades."},
                            {"id": "garantias", "name": "Garantias", "description": "Garantias e responsabilidades."},
                            {"id": "foro", "name": "Foro", "description": "Foro e jurisdição."},
                            {"id": "reajuste", "name": "Reajuste", "description": "Índice e periodicidade."},
                            {"id": "limitacao", "name": "Limitação", "description": "Limitação de responsabilidade."},
                        ],
                        "prompt_prefix": "Extraia com precisão do contrato. Se não houver, retorne vazio.",
                    },
                },
                {
                    "id": "output_1",
                    "type": "output",
                    "position": {"x": 300, "y": 360},
                    "data": {"label": "Matriz de Cláusulas", "show_all": True},
                },
            ],
            "edges": [
                {"id": "e1", "source": "file_upload_1", "target": "review_table_1", "animated": True},
                {"id": "e2", "source": "review_table_1", "target": "output_1", "animated": True},
            ],
        },
    ),

    # ── Template 42: Triage de Inbox Jurídico (Outlook) ────────────────────
    _tpl(
        name="Triage de Inbox Jurídico (Outlook) — Reply + Prazo",
        description=(
            "Trigger: email recebido no Outlook. Classifica urgência, identifica pedido, sugere prazo e responde ao email. "
            "Opcionalmente cria evento de calendário."
        ),
        tags=["async", "outlook", "triage", "prazos", "email"],
        category="general",
        output_type="document",
        graph_json={
            "nodes": [
                {
                    "id": "trigger_1",
                    "type": "trigger",
                    "position": {"x": 300, "y": 40},
                    "data": {
                        "label": "Email Recebido",
                        "trigger_type": "outlook_email",
                        "trigger_config": {"subject_contains": "", "sender_filter": "", "require_attachment": False},
                    },
                },
                {
                    "id": "claude_agent_1",
                    "type": "claude_agent",
                    "position": {"x": 300, "y": 200},
                    "data": {
                        "label": "Classificar + Sugerir Ações",
                        "model": "claude-4.5-sonnet",
                        "system_prompt": (
                            "Você é um assistente jurídico de triagem de inbox. "
                            "Classifique: (1) Tipo de demanda, (2) Urgência, (3) Prazo provável, "
                            "(4) Informações faltantes, (5) Próximas ações. "
                            "Produza uma resposta curta e profissional ao remetente."
                        ),
                        "prompt": (
                            "Assunto: {{trigger_1.subject}}\n"
                            "Remetente: {{trigger_1.sender}}\n"
                            "Corpo (preview): {{trigger_1.body}}\n\n"
                            "Gere a resposta e um checklist interno."
                        ),
                        "tool_names": ["search_legislacao", "search_jurisprudencia"],
                        "max_iterations": 6,
                        "max_tokens": 4096,
                        "include_mcp": False,
                        "use_sdk": True,
                    },
                },
                {
                    "id": "delivery_reply",
                    "type": "delivery",
                    "position": {"x": 220, "y": 380},
                    "data": {
                        "label": "Responder Email",
                        "delivery_type": "outlook_reply",
                        "delivery_config": {"include_original_quote": True},
                    },
                },
                {
                    "id": "delivery_calendar",
                    "type": "delivery",
                    "position": {"x": 420, "y": 380},
                    "data": {
                        "label": "Criar Evento (manual ajuste)",
                        "delivery_type": "calendar_event",
                        "delivery_config": {
                            "subject": "Follow-up: {{trigger_event.subject}}",
                            "duration_minutes": 30,
                            "reminder_minutes": 60,
                        },
                    },
                },
            ],
            "edges": [
                {"id": "e1", "source": "trigger_1", "target": "claude_agent_1", "animated": True},
                {"id": "e2", "source": "claude_agent_1", "target": "delivery_reply", "animated": True},
                {"id": "e3", "source": "claude_agent_1", "target": "delivery_calendar", "animated": True},
            ],
        },
    ),

    # ── Template 43: Pipeline de Audiência (sem transcrição automática) ────
    _tpl(
        name="Audiência: Analisar Transcrição (manual) + Checklist",
        description=(
            "Cole a transcrição (ou ata) e gere: resumo, linha do tempo, inconsistências, pontos fortes/fracos e checklist de providências. "
            "Não realiza transcrição de áudio automaticamente (use a aba Transcrição para isso)."
        ),
        tags=["audiência", "transcrição", "checklist", "manual"],
        category="litigation",
        output_type="document",
        graph_json={
            "nodes": [
                {
                    "id": "user_input_1",
                    "type": "user_input",
                    "position": {"x": 300, "y": 40},
                    "data": {
                        "label": "Cole a transcrição/ata",
                        "collects": "input",
                        "input_type": "text",
                        "placeholder": "Cole aqui a transcrição completa da audiência/reunião.",
                    },
                },
                {
                    "id": "prompt_1",
                    "type": "prompt",
                    "position": {"x": 300, "y": 200},
                    "data": {
                        "label": "Gerar Checklist e Análise",
                        "model": "claude-4.5-sonnet",
                        "prompt": (
                            "Você é um advogado sênior. Analise a transcrição e entregue:\n"
                            "1) Resumo executivo\n"
                            "2) Linha do tempo (timestamps se existirem)\n"
                            "3) Pontos controvertidos e contradições\n"
                            "4) Provas citadas e lacunas\n"
                            "5) Checklist de providências e próximos passos\n\n"
                            "Transcrição:\n{input}"
                        ),
                    },
                },
                {
                    "id": "human_review_1",
                    "type": "human_review",
                    "position": {"x": 300, "y": 340},
                    "data": {"label": "Revisão", "instructions": "Revise e ajuste antes de enviar/arquivar."},
                },
                {
                    "id": "output_1",
                    "type": "output",
                    "position": {"x": 300, "y": 500},
                    "data": {"label": "Análise de Audiência", "show_all": True},
                },
            ],
            "edges": [
                {"id": "e1", "source": "user_input_1", "target": "prompt_1", "animated": True},
                {"id": "e2", "source": "prompt_1", "target": "human_review_1", "animated": True},
                {"id": "e3", "source": "human_review_1", "target": "output_1", "animated": True},
            ],
        },
    ),
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def _pick_seed_user(session) -> User:
    # Workflows.user_id é FK (não pode ser "system" se não existir um usuário).
    # Preferimos um ADMIN; se não houver, usamos o usuário mais antigo.
    seed_user = None
    try:
        result = await session.execute(
            select(User).where(User.role == UserRole.ADMIN).order_by(User.created_at.asc()).limit(1)
        )
        seed_user = result.scalar_one_or_none()
    except Exception:
        seed_user = None
    if not seed_user:
        result = await session.execute(select(User).order_by(User.created_at.asc()).limit(1))
        seed_user = result.scalar_one_or_none()
    if not seed_user:
        raise RuntimeError("Não há usuários no banco para atribuir ownership aos templates (crie um usuário primeiro).")
    return seed_user


async def seed(seed_user_id: str | None = None) -> dict:
    """Insere templates de workflow no banco, pulando os que já existem.

    Retorna contadores para uso por endpoints/admin UI.
    """
    logger.info("Iniciando seed de workflow templates...")
    async with AsyncSessionLocal() as session:
        if seed_user_id:
            seed_user = await session.get(User, seed_user_id)
            if not seed_user:
                seed_user = await _pick_seed_user(session)
        else:
            seed_user = await _pick_seed_user(session)

        inserted = 0
        skipped = 0

        for template_data in TEMPLATES:
            name = template_data["name"]
            stmt = select(Workflow).where(
                Workflow.name == name,
                Workflow.is_template.is_(True),
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing:
                skipped += 1
                continue

            data = dict(template_data)
            data["user_id"] = str(seed_user.id)
            workflow = Workflow(**data)
            session.add(workflow)
            inserted += 1

        await session.commit()

    logger.info(
        f"Seed concluído: {inserted} inseridos, {skipped} já existiam. "
        f"Total de templates: {len(TEMPLATES)}."
    )
    return {"inserted": inserted, "skipped": skipped, "total": len(TEMPLATES)}


async def main() -> None:
    await seed(None)


if __name__ == "__main__":
    asyncio.run(main())
