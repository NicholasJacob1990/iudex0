"""
RAG Indexer - Script de Indexação em Lote para Documentos Jurídicos (v1.0)

Este script permite indexar documentos de várias fontes:
- PDFs de legislação
- PDFs/TXTs de jurisprudência
- Documentos SEI (internos)
- Modelos de peças jurídicas

Uso:
    python rag_indexer.py --type lei --input ./leis/
    python rag_indexer.py --type juris --input ./jurisprudencia/ --tribunal STJ
    python rag_indexer.py --type sei --input ./sei/ --orgao PGFN --tenant-id PGFN
    python rag_indexer.py --type pecas --input ./modelos/ --area tributario

Requires: pip install chromadb sentence-transformers rank_bm25 PyPDF2 python-docx
"""

import os
import sys
import argparse
import json
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
import logging

# Third-party imports
try:
    from PyPDF2 import PdfReader
except ImportError:
    PdfReader = None
    print("⚠️ PyPDF2 não instalado. Instale: pip install PyPDF2")

try:
    from docx import Document as DocxDocument
except ImportError:
    DocxDocument = None
    print("⚠️ python-docx não instalado. Instale: pip install python-docx")

from colorama import Fore, Style, init
init(autoreset=True)

# Import RAG Module
from rag_module import (
    RAGManager,
    LegislacaoMetadata,
    JurisprudenciaMetadata,
    SEIMetadata,
    PecaModeloMetadata,
    create_rag_manager
)

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("RAGIndexer")

# =============================================================================
# FILE READERS
# =============================================================================

def read_pdf(file_path: str) -> str:
    """Lê conteúdo de PDF"""
    if not PdfReader:
        raise ImportError("PyPDF2 não instalado. Instale: pip install PyPDF2")
    
    reader = PdfReader(file_path)
    text = ""
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + "\n"
    return text.strip()

def read_docx(file_path: str) -> str:
    """Lê conteúdo de DOCX"""
    if not DocxDocument:
        raise ImportError("python-docx não instalado. Instale: pip install python-docx")
    
    doc = DocxDocument(file_path)
    text = "\n".join([p.text for p in doc.paragraphs])
    return text.strip()

def read_txt(file_path: str) -> str:
    """Lê conteúdo de TXT"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read().strip()

def read_file(file_path: str) -> str:
    """Lê arquivo baseado na extensão"""
    ext = Path(file_path).suffix.lower()
    
    if ext == '.pdf':
        return read_pdf(file_path)
    elif ext == '.docx':
        return read_docx(file_path)
    elif ext in ['.txt', '.md', '.text']:
        return read_txt(file_path)
    else:
        logger.warning(f"Extensão não suportada: {ext} ({file_path})")
        return ""

def find_files(input_path: str, extensions: List[str] = None) -> List[str]:
    """Encontra arquivos recursivamente"""
    extensions = extensions or ['.pdf', '.txt', '.docx', '.md']
    
    if os.path.isfile(input_path):
        return [input_path]
    
    files = []
    for root, dirs, filenames in os.walk(input_path):
        for filename in filenames:
            if any(filename.lower().endswith(ext) for ext in extensions):
                files.append(os.path.join(root, filename))
    
    return sorted(files)

# =============================================================================
# METADATA EXTRACTORS
# =============================================================================

def extract_legislacao_metadata(text: str, filename: str) -> LegislacaoMetadata:
    """Extrai metadados de legislação a partir do texto e nome do arquivo (Robust Regex)"""
    filename_clean = Path(filename).stem.upper().replace("_", " ").replace("-", " ")
    text_start = text[:1000].upper()
    
    tipo = "lei"
    numero = ""
    ano = datetime.now().year
    
    # Mapeamento de Tipos
    tipos_map = {
        "DECRETO LEI": "decreto_lei",
        "DECRETO": "decreto",
        "LEI COMPLEMENTAR": "lei_complementar",
        "LEI ORDINARIA": "lei",
        "LEI": "lei",
        "RESOLUCAO": "resolucao",
        "PORTARIA": "portaria",
        "INSTRUCAO NORMATIVA": "instrucao_normativa",
        "CONSTITUICAO": "constituicao",
        "MEDIDA PROVISORIA": "medida_provisoria",
        "EMENDA": "emenda_constitucional",
        "SUMULA": "sumula"
    }

    # 1. Detectar Tipo (Filename > Text Content)
    detected_type = None
    for k, v in tipos_map.items():
        if k in filename_clean:
            detected_type = v
            break # Match longest first logic if sorted, but here heuristic
    
    if not detected_type:
        for k, v in tipos_map.items():
            if k in text_start:
                detected_type = v
                break
    
    tipo = detected_type or "lei"
    
    # 2. Extrair Número
    # Patterns: "Lei 12.345", "Nº 12.345", "12345/2010"
    num_match = re.search(r'(?:N[ºo°]?\s*|LEI\s+|DECRETO\s+|NR\.?\s*)(\d+[\d\.]*)', filename_clean)
    if not num_match:
         num_match = re.search(r'(?:N[ºo°]?\s*|LEI\s+|DECRETO\s+|NR\.?\s*)(\d+[\d\.]*)', text_start)
    
    if num_match:
        numero = num_match.group(1).replace(".", "")
    
    # 3. Extrair Ano
    ano_match = re.search(r'(?:/|\s|DE\s)(\d{4})', filename_clean)
    if not ano_match:
        ano_match = re.search(r'DE\s+\d{1,2}\s+DE\s+[A-Z]+\s+DE\s+(\d{4})', text_start) # Data extensa
    
    if ano_match:
        try:
            extracted_year = int(ano_match.group(1))
            if 1900 <= extracted_year <= datetime.now().year:
                ano = extracted_year
        except:
            pass

    # 4. Extrair Artigo (se for fragmento)
    artigo = None
    art_match = re.search(r'(?:^|\n)(ART\.?\s*\d+[ºo]?\s*[A-Z]?)', text[:500], re.IGNORECASE)
    if art_match:
        artigo = art_match.group(1).title()
    
    return LegislacaoMetadata(
        tipo=tipo,
        numero=numero,
        ano=ano,
        jurisdicao="BR",
        artigo=artigo,
        vigencia="vigente",
        data_atualizacao=datetime.now().strftime("%Y-%m-%d")
    )

def extract_jurisprudencia_metadata(
    text: str, 
    filename: str,
    tribunal: str = "STJ",
    orgao: str = "Turma"
) -> JurisprudenciaMetadata:
    """Extrai metadados de jurisprudência (Enhanced)"""
    filename_clean = Path(filename).stem.upper().replace("_", " ")
    header_text = text[:2000] # Look deeper for jurisprudence
    
    # Detectar tipo de decisão
    tipo_decisao = "acordao"
    if "SUMULA" in filename_clean or "SÚMULA" in header_text:
        tipo_decisao = "sumula"
    elif "MONOCRATICA" in filename_clean or "DECISÃO MONOCRÁTICA" in header_text.upper():
        tipo_decisao = "decisao_monocratica"
    elif "REPERCUSSAO GERAL" in header_text.upper() or "REPETITIVO" in header_text.upper():
        tipo_decisao = "tema_repetitivo"
    
    # Extrair número do processo
    numero = ""
    # Matches: "REsp 1.234.567", "HC 123456", "AgInt no REsp 123"
    proc_match = re.search(r'((?:[A-Z][a-zA-Z]+(?:\s+no)?\s+)?[A-Z]+\s*n?º?\s*\d+(?:\.\d+)*)', filename_clean)
    if not proc_match:
        # Try finding in text header, commonly "RECURSO ESPECIAL Nº 1.234.567"
        proc_match = re.search(r'(RECURSO\s+[A-Z]+\s+N[º°]\s*[\d\.]+)', header_text, re.IGNORECASE)
        
    if proc_match:
        numero = proc_match.group(1).upper()
    
    # Extrair relator
    relator = None
    # Patterns found in headers
    rel_patterns = [
        r'Relator(?:a)?\s*:?\s*(?:Min(?:istra|istro)?\.?)?\s*([A-ZÀ-Ú][A-ZÀ-Ú\s]+)(?:$|\n|-|;)',
        r'Rel\.:\s*Min\.\s*([A-ZÀ-Ú][A-ZÀ-Ú\s]+)',
    ]
    for pat in rel_patterns:
        m = re.search(pat, header_text, re.IGNORECASE | re.MULTILINE)
        if m:
            relator = f"Min. {m.group(1).strip().title()}"
            break

    # Extrair data de julgamento
    data = None
    # Standard formats DD/MM/YYYY or YYYY-MM-DD
    date_patterns = [
        r'Julgado em\s*:?\s*(\d{1,2})[/\.](\d{1,2})[/\.](\d{4})',
        r'Data d[oa] Julgamento\s*:?\s*(\d{1,2})[/\.](\d{1,2})[/\.](\d{4})',
        r'(\d{1,2})\s+de\s+([a-z]+)\s+de\s+(\d{4})' # Data extensa
    ]
    
    for pat in date_patterns:
        dm = re.search(pat, header_text, re.IGNORECASE)
        if dm:
            try:
                # Handle textual months if needed, assuming numeric for now for simplicity of regex 1 & 2
                if len(dm.groups()) == 3:
                    d, m, y = dm.groups()
                    if m.isalpha():
                         # Map months if needed, skipping complex implementation for now
                         pass
                    else:
                        data = f"{y}-{m.zfill(2)}-{d.zfill(2)}"
                        break
            except:
                continue

    # Extrair Tema/Súmula number explicitly if Súmula type
    tema = None
    if tipo_decisao == "sumula":
        sum_match = re.search(r'S[uú]mula\s+(\d+)', filename_clean + " " + header_text, re.IGNORECASE)
        if sum_match:
            numero = f"Súmula {sum_match.group(1)}"
            
    return JurisprudenciaMetadata(
        tribunal=tribunal,
        orgao=orgao,
        tipo_decisao=tipo_decisao,
        numero=numero or "N/I",
        relator=relator,
        data_julgamento=data,
        tema=tema,
        assuntos=[]
    )

def extract_sei_metadata(
    text: str,
    filename: str,
    orgao: str = "ORGAO",
    unidade: str = "UNIDADE",
    tenant_id: str = "default",
    sigilo: str = "publico"
) -> SEIMetadata:
    """Extrai metadados de documento SEI"""
    filename_clean = Path(filename).stem
    
    # Detectar tipo de documento
    tipo_documento = "documento"
    if "PARECER" in filename_clean.upper():
        tipo_documento = "parecer"
    elif "NOTA" in filename_clean.upper():
        tipo_documento = "nota_tecnica"
    elif "OFICIO" in filename_clean.upper():
        tipo_documento = "oficio"
    elif "DESPACHO" in filename_clean.upper():
        tipo_documento = "despacho"
    elif "MEMORANDO" in filename_clean.upper():
        tipo_documento = "memorando"
    
    # Extrair número de processo SEI
    processo_sei = ""
    sei_match = re.search(r'(\d{5}\.\d+/\d{4}-\d{2})', text)
    if sei_match:
        processo_sei = sei_match.group(1)
    else:
        # Tentar do nome do arquivo
        num_match = re.search(r'(\d+)', filename_clean)
        if num_match:
            processo_sei = num_match.group(1)
    
    return SEIMetadata(
        processo_sei=processo_sei,
        tipo_documento=tipo_documento,
        orgao=orgao,
        unidade=unidade,
        data_criacao=datetime.now().strftime("%Y-%m-%d"),
        sigilo=sigilo,
        tenant_id=tenant_id,
        responsavel_id=None,
        allowed_users=[]
    )

def extract_peca_metadata(
    text: str,
    filename: str,
    tipo_peca: str = "parecer",
    area: str = "geral",
    rito: str = "ordinario"
) -> PecaModeloMetadata:
    """Extrai metadados de modelo de peça"""
    filename_clean = Path(filename).stem.upper()
    
    # Detectar tipo de peça do nome
    if "PETICAO" in filename_clean or "INICIAL" in filename_clean:
        tipo_peca = "peticao_inicial"
    elif "CONTEST" in filename_clean:
        tipo_peca = "contestacao"
    elif "RECURSO" in filename_clean or "APELACAO" in filename_clean:
        tipo_peca = "recurso"
    elif "PARECER" in filename_clean:
        tipo_peca = "parecer"
    elif "CONTRATO" in filename_clean:
        tipo_peca = "contrato"
    elif "SENTENCA" in filename_clean:
        tipo_peca = "sentenca"
    
    # Detectar área do nome
    areas_keywords = {
        "tributario": ["TRIBUT", "FISCAL", "IMPOSTO", "ICMS", "IR", "PIS", "COFINS"],
        "civil": ["CIVIL", "CONTRATO", "DANOS", "INDENIZA"],
        "trabalhista": ["TRABALH", "CLT", "EMPREGO"],
        "administrativo": ["ADMIN", "LICIT", "SERVIDOR", "PAD"],
        "penal": ["PENAL", "CRIME", "HC"],
        "ambiental": ["AMBIENT", "IBAMA", "LICENC"],
        "previdenciario": ["PREVID", "INSS", "APOSENTAD"],
    }
    
    for area_name, keywords in areas_keywords.items():
        if any(kw in filename_clean for kw in keywords):
            area = area_name
            break
    
    return PecaModeloMetadata(
        tipo_peca=tipo_peca,
        area=area,
        rito=rito,
        tribunal_destino=None,
        tese=None,
        resultado=None,
        data_criacao=datetime.now().strftime("%Y-%m-%d"),
        versao="v1",
        aprovado=True
    )

# Import GenAI for LLM extraction
from google import genai
from google.genai import types

# Import ClauseMetadata for Clause Bank (v2.0)
from rag_module import ClauseMetadata

# Initialize client (will be set in main)
genai_client = None
GENAI_MODEL = "gemini-2.0-flash"

# =============================================================================
# CLAUSE BANK: BLOCK PARSER (v2.0)
# =============================================================================

CLAUSE_PATTERNS = {
    # Preliminares
    "preliminar": {
        "regex": r"(?:^|\n)((?:I+\s*[-–.]?\s*)?D[AOEAS]*\s*PRELIMINAR|PRELIMINARMENTE|DAS\s+QUESTÕES\s+PRELIMINARES)",
        "subtipos": {
            "ilegitimidade_passiva": r"ilegitimidade\s+passiva|ilegitimidade\s+ad\s+causam",
            "inepcid": r"inépcia|inepta",
            "litispendencia": r"litispendência|coisa\s+julgada",
            "falta_interesse": r"falta\s+de\s+interesse|carência\s+de\s+ação",
            "incompetencia": r"incompetência",
            "conexao": r"conexão|continência",
        }
    },
    # Prejudicial de Mérito
    "prejudicial": {
        "regex": r"(?:^|\n)(PREJUDICIAL\s+DE\s+MÉRITO|D[AO]\s+PRESCRIÇÃO|D[AO]\s+DECADÊNCIA)",
        "subtipos": {
            "prescricao": r"prescrição|prescricional",
            "decadencia": r"decadência|decadencial",
        }
    },
    # Fatos
    "fatos": {
        "regex": r"(?:^|\n)(D[AOEAS]*\s*FATOS?|SÍNTESE\s+DA\s+INICIAL|BREVE\s+RELATO|RELATÓRIO)",
        "subtipos": {}
    },
    # Mérito / Fundamentação
    "merito": {
        "regex": r"(?:^|\n)(D[OA]\s*DIREITO|D[OA]\s*MÉRITO|FUNDAMENTAÇÃO|D[AO]\s*TESE)",
        "subtipos": {
            "dano_moral": r"dano\s+moral|danos\s+morais",
            "dano_material": r"dano\s+material|lucros\s+cessantes",
            "responsabilidade_objetiva": r"responsabilidade\s+objetiva",
            "responsabilidade_subjetiva": r"responsabilidade\s+subjetiva|culpa",
            "boa_fe": r"boa[- ]fé",
            "abuso_direito": r"abuso\s+de\s+direito",
        }
    },
    # Tutela de Urgência
    "tutela": {
        "regex": r"(?:^|\n)(D[AO]\s*TUTELA|TUTELA\s+DE\s+URGÊNCIA|LIMINAR|ANTECIPAÇÃO\s+DE\s+TUTELA|EFEITO\s+SUSPENSIVO)",
        "subtipos": {}
    },
    # Pedidos
    "pedido": {
        "regex": r"(?:^|\n)(D[AOEAS]*\s*PEDIDOS?|REQUER(?:IMENTOS)?|ANTE\s+O\s+EXPOSTO|DIANTE\s+DO\s+EXPOSTO|EX\s+POSITIS)",
        "subtipos": {}
    },
    # Honorários
    "honorarios": {
        "regex": r"(?:^|\n)(D[OAES]*\s*HONORÁRIOS|SUCUMBÊNCIA)",
        "subtipos": {}
    },
    # Provas
    "provas": {
        "regex": r"(?:^|\n)(D[AOS]*\s*PROVAS?\s+(A\s+PRODUZIR)?|REQUERIMENTO\s+DE\s+PROVAS)",
        "subtipos": {}
    },
    # v2.1: Contratos e Escrituras
    "clausula_contrato": {
        "regex": r"(?:^|\n)(CLÁUSULA\s+(?:PRIMEIRA|SEGUNDA|TERCEIRA|QUARTA|QUINTA|SEXTA|SÉTIMA|OITAVA|NONA|DÉCIMA|[1-9][0-9]*[ªaºo]?)|(?:DA\s+)?(?:DO\s+)?OBJETO|(?:DO\s+)?PREÇO|(?:DA\s+)?FORMA\s+DE\s+PAGAMENTO|(?:DO\s+)?PRAZO|(?:DAS\s+)?OBRIGAÇÕES|(?:DA\s+)?RESCISÃO|(?:DO\s+)?FORO)",
        "subtipos": {
            "objeto": r"objeto",
            "preco": r"preço|valor|pagamento",
            "obrigacoes": r"obrigaç(?:ões|ão)|deveres|responsabilidad",
            "rescisao": r"rescisão|extinção|resolução",
            "foro": r"foro|eleição",
            "confidencialidade": r"confidencial|sigilo",
            "lgpd": r"proteção\s+de\s+dados|lgpd|dados\s+pessoais",
        }
    },
    "escritura_notas": {
        "regex": r"(?:^|\n)((?:OS?|A)\s+(?:OUTORGANTE|OUTORGADO|VENDEDOR|COMPRADOR|DOADOR|DONATÁRIO)S?|DAS?\s+DECLARAÇÕES|DA\s+TRANSMISSÃO|DAS?\s+NOTAS?\s+(?:DE\s+)?TABELIA(?:O|Ã))",
        "subtipos": {
            "qualificacao": r"outorgante|cônjuge|residente",
            "transmissao": r"transmissão|passagem|domínio",
            "imovel": r"imóvel|descrição|matrícula",
        }
    }
}

def parse_peca_em_blocos(texto: str, tipo_peca: str = "peticao", area: str = "geral", tribunal: str = "TJRJ") -> List[Dict]:
    """
    Identifica e extrai blocos lógicos de uma peça jurídica para Clause Bank.
    
    Args:
        texto: Texto completo da peça
        tipo_peca: Tipo de documento (peticao, contestacao, etc.)
        area: Área jurídica (civil, tributario, etc.)
        tribunal: Tribunal de destino
        
    Returns:
        Lista de dicionários com {tipo_bloco, subtipo, texto, linha_inicio, linha_fim, metadata}
    """
    blocos = []
    linhas = texto.split('\n')
    texto_lower = texto.lower()
    
    # Encontrar posições de cada tipo de bloco
    matches = []
    for tipo_bloco, config in CLAUSE_PATTERNS.items():
        for match in re.finditer(config["regex"], texto, re.IGNORECASE | re.MULTILINE):
            # Encontrar linha de início
            pos_inicio = match.start()
            linha_inicio = texto[:pos_inicio].count('\n')
            matches.append({
                "tipo_bloco": tipo_bloco,
                "config": config,
                "pos_inicio": pos_inicio,
                "linha_inicio": linha_inicio,
                "header": match.group(1).strip()
            })
    
    # Ordenar por posição no texto
    matches.sort(key=lambda x: x["pos_inicio"])
    
    # Extrair texto entre cada bloco
    for i, m in enumerate(matches):
        # Determinar fim do bloco
        if i + 1 < len(matches):
            pos_fim = matches[i + 1]["pos_inicio"]
            linha_fim = matches[i + 1]["linha_inicio"] - 1
        else:
            pos_fim = len(texto)
            linha_fim = len(linhas) - 1
        
        bloco_texto = texto[m["pos_inicio"]:pos_fim].strip()
        
        # Detectar subtipo
        subtipo = "geral"
        for sub_nome, sub_regex in m["config"].get("subtipos", {}).items():
            if re.search(sub_regex, bloco_texto, re.IGNORECASE):
                subtipo = sub_nome
                break
        
        # Criar metadata
        metadata = ClauseMetadata(
            tipo_bloco=m["tipo_bloco"],
            subtipo=subtipo,
            tipo_peca=tipo_peca,
            area=area,
            tribunal=tribunal,
            status="aprovado",
            aprovador=None,
            data_aprovacao=datetime.now().strftime("%Y-%m-%d"),
            sucesso=False,
            versao="v1",
            data_uso=None
        )
        
        blocos.append({
            "tipo_bloco": m["tipo_bloco"],
            "subtipo": subtipo,
            "texto": bloco_texto,
            "linha_inicio": m["linha_inicio"],
            "linha_fim": linha_fim,
            "header": m["header"],
            "metadata": metadata
        })
    
    # Se não encontrou blocos, retornar texto inteiro como "geral"
    if not blocos:
        blocos.append({
            "tipo_bloco": "geral",
            "subtipo": "documento_completo",
            "texto": texto,
            "linha_inicio": 0,
            "linha_fim": len(linhas) - 1,
            "header": "",
            "metadata": ClauseMetadata(
                tipo_bloco="geral",
                subtipo="documento_completo",
                tipo_peca=tipo_peca,
                area=area,
                tribunal=tribunal,
            )
        })
    
    logger.info(f"📦 Extrai {len(blocos)} blocos lógicos: {[b['tipo_bloco'] for b in blocos]}")
    return blocos

# =============================================================================
# LLM METADATA EXTRACTOR
# =============================================================================

def extract_metadata_with_llm(text: str, doc_type: str) -> Dict:
    """Usa o Gemini para extrair metadados precisos do texto"""
    if not genai_client:
        return {}
    
    # Pegamos apenas o começo do texto para extrair metadados
    text_peek = text[:4000]
    
    prompts = {
        "lei": """Extraia metadados desta LEGISLAÇÃO. Responda APENAS em JSON.
            Campos: tipo (lei, decreto, etc), numero, ano (int), jurisdicao (BR, SP, etc), artigo_principal.
            Texto: {text}""",
        "juris": """Extraia metadados desta JURISPRUDÊNCIA. Responda APENAS em JSON.
            Campos: tribunal, orgao, tipo_decisao (acordao, sumula, etc), numero, relator, data_julgamento (YYYY-MM-DD), tema.
            Texto: {text}""",
        "sei": """Extraia metadados deste documento administrativo. Responda APENAS em JSON.
            Campos: processo_sei, tipo_documento, orgao, unidade.
            Texto: {text}""",
        "pecas": """Extraia metadados deste modelo de peça jurídica. Responda APENAS em JSON.
            Campos: tipo_peca, area, rito.
            Texto: {text}"""
    }
    
    prompt = prompts.get(doc_type, prompts["lei"]).format(text=text_peek)
    
    try:
        response = genai_client.models.generate_content(
            model=GENAI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1
            )
        )
        if response.text:
            return json.loads(response.text)
    except Exception as e:
        logger.warning(f"⚠️ Erro na extração LLM: {e}")
    return {}

# =============================================================================
# INDEXING FUNCTIONS (UPDATED)
# =============================================================================

def index_legislacao(rag: RAGManager, input_path: str, chunk: bool = True, use_llm: bool = False) -> int:
    """Indexa arquivos de legislação"""
    files = find_files(input_path)
    total_indexed = 0
    
    print(f"\n{Fore.CYAN}📜 Indexando LEGISLAÇÃO...")
    print(f"   Arquivos encontrados: {len(files)}\n")
    
    for filepath in files:
        try:
            print(f"   📄 {Path(filepath).name}...", end=" ")
            text = read_file(filepath)
            
            if not text or len(text) < 50:
                print(f"{Fore.YELLOW}(vazio/muito curto)")
                continue
            
            # Metadata merge: LLM + Regex
            metadata = extract_legislacao_metadata(text, filepath)
            if use_llm:
                llm_meta = extract_metadata_with_llm(text, "lei")
                if llm_meta:
                    metadata.tipo = llm_meta.get("tipo", metadata.tipo)
                    metadata.numero = str(llm_meta.get("numero", metadata.numero))
                    metadata.ano = int(llm_meta.get("ano", metadata.ano))
                    metadata.artigo = llm_meta.get("artigo_principal", metadata.artigo)

            count = rag.add_legislacao(text, metadata, chunk=chunk)
            total_indexed += count
            print(f"{Fore.GREEN}✅ {count} chunks")
            
        except Exception as e:
            print(f"{Fore.RED}❌ Erro: {e}")
    
    return total_indexed

def index_jurisprudencia(
    rag: RAGManager, 
    input_path: str,
    tribunal: str = "STJ",
    orgao: str = "Turma",
    chunk: bool = True,
    use_llm: bool = False
) -> int:
    """Indexa arquivos de jurisprudência"""
    files = find_files(input_path)
    total_indexed = 0
    
    print(f"\n{Fore.CYAN}⚖️ Indexando JURISPRUDÊNCIA ({tribunal})...")
    print(f"   Arquivos encontrados: {len(files)}\n")
    
    for filepath in files:
        try:
            print(f"   📄 {Path(filepath).name}...", end=" ")
            text = read_file(filepath)
            
            if not text or len(text) < 50:
                print(f"{Fore.YELLOW}(vazio/muito curto)")
                continue
            
            metadata = extract_jurisprudencia_metadata(text, filepath, tribunal, orgao)
            if use_llm:
                llm_meta = extract_metadata_with_llm(text, "juris")
                if llm_meta:
                    metadata.tribunal = llm_meta.get("tribunal", metadata.tribunal)
                    metadata.numero = str(llm_meta.get("numero", metadata.numero))
                    metadata.relator = llm_meta.get("relator", metadata.relator)
                    metadata.tipo_decisao = llm_meta.get("tipo_decisao", metadata.tipo_decisao)
                    metadata.data_julgamento = llm_meta.get("data_julgamento", metadata.data_julgamento)

            count = rag.add_jurisprudencia(text, metadata, chunk=chunk)
            total_indexed += count
            print(f"{Fore.GREEN}✅ {count} chunks")
            
        except Exception as e:
            print(f"{Fore.RED}❌ Erro: {e}")
    
    return total_indexed

def index_sei(
    rag: RAGManager,
    input_path: str,
    orgao: str = "ORGAO",
    unidade: str = "UNIDADE",
    tenant_id: str = "default",
    sigilo: str = "publico",
    chunk: bool = True,
    use_llm: bool = False
) -> int:
    """Indexa documentos SEI (internos)"""
    files = find_files(input_path)
    total_indexed = 0
    
    print(f"\n{Fore.CYAN}📁 Indexando SEI ({orgao} - {tenant_id})...")
    print(f"   Arquivos encontrados: {len(files)}\n")
    
    for filepath in files:
        try:
            print(f"   📄 {Path(filepath).name}...", end=" ")
            text = read_file(filepath)
            
            if not text or len(text) < 50:
                print(f"{Fore.YELLOW}(vazio/muito curto)")
                continue
            
            metadata = extract_sei_metadata(text, filepath, orgao, unidade, tenant_id, sigilo)
            if use_llm:
                llm_meta = extract_metadata_with_llm(text, "sei")
                if llm_meta:
                    metadata.processo_sei = str(llm_meta.get("processo_sei", metadata.processo_sei))
                    metadata.tipo_documento = llm_meta.get("tipo_documento", metadata.tipo_documento)
                    metadata.orgao = llm_meta.get("orgao", metadata.orgao)

            count = rag.add_sei(text, metadata, chunk=chunk)
            total_indexed += count
            print(f"{Fore.GREEN}✅ {count} chunks")
            
        except Exception as e:
            print(f"{Fore.RED}❌ Erro: {e}")
    
    return total_indexed

def index_pecas(
    rag: RAGManager,
    input_path: str,
    tipo_peca: str = "parecer",
    area: str = "geral",
    rito: str = "ordinario",
    chunk: bool = True,
    use_llm: bool = False
) -> int:
    """Indexa modelos de peças jurídicas"""
    files = find_files(input_path)
    total_indexed = 0
    
    print(f"\n{Fore.CYAN}📝 Indexando MODELOS DE PEÇAS ({area})...")
    print(f"   Arquivos encontrados: {len(files)}\n")
    
    for filepath in files:
        try:
            print(f"   📄 {Path(filepath).name}...", end=" ")
            text = read_file(filepath)
            
            if not text or len(text) < 50:
                print(f"{Fore.YELLOW}(vazio/muito curto)")
                continue
            
            metadata = extract_peca_metadata(text, filepath, tipo_peca, area, rito)
            if use_llm:
                llm_meta = extract_metadata_with_llm(text, "pecas")
                if llm_meta:
                    metadata.tipo_peca = llm_meta.get("tipo_peca", metadata.tipo_peca)
                    metadata.area = llm_meta.get("area", metadata.area)
                    metadata.rito = llm_meta.get("rito", metadata.rito)

            count = rag.add_peca_modelo(text, metadata, chunk=chunk)
            total_indexed += count
            print(f"{Fore.GREEN}✅ {count} chunks")
            
        except Exception as e:
            print(f"{Fore.RED}❌ Erro: {e}")
    
    return total_indexed

def index_pecas_clause_bank(
    rag: RAGManager,
    input_path: str,
    tipo_peca: str = "peticao",
    area: str = "geral",
    tribunal: str = "TJRJ"
) -> int:
    """
    Indexa modelos de peças jurídicas por BLOCO LÓGICO (Clause Bank v2.0).
    Cada seção da peça (Preliminares, Mérito, Pedidos, etc.) é indexada separadamente.
    """
    files = find_files(input_path)
    total_indexed = 0
    
    print(f"\n{Fore.CYAN}📝 Indexando CLAUSE BANK ({area})...")
    print(f"   Arquivos encontrados: {len(files)}\n")
    
    for filepath in files:
        try:
            print(f"   📄 {Path(filepath).name}...")
            text = read_file(filepath)
            
            if not text or len(text) < 50:
                print(f"{Fore.YELLOW}      (vazio/muito curto)")
                continue
            
            # Parse into logical blocks
            blocos = parse_peca_em_blocos(text, tipo_peca, area, tribunal)
            
            for bloco in blocos:
                # Create metadata dict from ClauseMetadata
                meta = bloco["metadata"]
                meta_dict = {
                    "tipo_bloco": meta.tipo_bloco,
                    "subtipo": meta.subtipo,
                    "tipo_peca": meta.tipo_peca,
                    "area": meta.area,
                    "tribunal": meta.tribunal,
                    "status": meta.status,
                    "aprovador": meta.aprovador or "",
                    "data_aprovacao": meta.data_aprovacao or "",
                    "sucesso": str(meta.sucesso),
                    "versao": meta.versao,
                    "source_type": "clause_bank"
                }
                
                # Index block (no further chunking - block IS the chunk)
                import hashlib as hl
                bloco_id = hl.md5(bloco["texto"].encode()).hexdigest()
                embedding = rag.embedding_model.encode(bloco["texto"]).tolist()
                
                rag.collections["pecas_modelo"].add(
                    ids=[bloco_id],
                    embeddings=[embedding],
                    documents=[bloco["texto"]],
                    metadatas=[meta_dict]
                )
                total_indexed += 1
                print(f"      ✅ Bloco: {bloco['tipo_bloco']}/{bloco['subtipo']}")
            
        except Exception as e:
            print(f"{Fore.RED}❌ Erro: {e}")
            import traceback
            traceback.print_exc()
    
    # Rebuild BM25 index
    rag._bm25_indices.pop("pecas_modelo", None)
    
    return total_indexed

# =============================================================================
# MAIN (UPDATED)
# =============================================================================

def main():
    global genai_client
    
    parser = argparse.ArgumentParser(
        description="Indexador RAG para Documentos Jurídicos",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument("--type", required=True, 
                        choices=["lei", "juris", "sei", "pecas"],
                        help="Tipo de documento: lei, juris, sei, pecas")
    parser.add_argument("--input", required=True,
                        help="Caminho para arquivo ou pasta de arquivos")
    parser.add_argument("--db-path", default="./chroma_db",
                        help="Caminho para o banco ChromaDB (default: ./chroma_db)")
    
    # Nova Flag: LLM Meta
    parser.add_argument("--llm-meta", action="store_true",
                        help="Usar Gemini Flash para extração de metadados precisa")
    
    # Opções para jurisprudência
    parser.add_argument("--tribunal", default="STJ",
                        help="Tribunal (para juris): STF, STJ, TJSP, TRF1, etc")
    parser.add_argument("--orgao", default="Turma",
                        help="Órgão julgador: Pleno, 1ª Turma, etc")
    
    # Opções para SEI
    parser.add_argument("--unidade", default="UNIDADE",
                        help="Unidade organizacional (para SEI)")
    parser.add_argument("--tenant-id", default="default",
                        help="Tenant ID para multi-tenancy (para SEI)")
    parser.add_argument("--sigilo", default="publico",
                        choices=["publico", "restrito", "sigiloso"],
                        help="Nível de sigilo (para SEI)")
    
    # Opções para peças
    parser.add_argument("--area", default="geral",
                        help="Área do direito: civil, tributario, trabalhista, etc")
    parser.add_argument("--rito", default="ordinario",
                        help="Rito processual: ordinario, sumario, especial")
    parser.add_argument("--tipo-peca", default="parecer",
                        help="Tipo de peça: peticao_inicial, contestacao, parecer, etc")
    
    # Outras opções
    parser.add_argument("--no-chunk", action="store_true",
                        help="Não dividir em chunks (indexar documento inteiro)")
    parser.add_argument("--clear", action="store_true",
                        help="Limpar coleção antes de indexar")
    parser.add_argument("--stats", action="store_true",
                        help="Mostrar estatísticas e sair")
    
    # v2.0: Clause Bank
    parser.add_argument("--clause-mode", action="store_true",
                        help="Indexar por bloco lógico (Clause Bank v2.0)")
    parser.add_argument("--tribunal-destino", default="TJRJ",
                        help="Tribunal de destino (para --clause-mode)")
    
    args = parser.parse_args()
    
    # Initialize RAG
    print(f"\n{Fore.CYAN}{'='*60}")
    print(f"📚 RAG INDEXER - Documentos Jurídicos")
    print(f"{'='*60}{Style.RESET_ALL}\n")
    
    rag = create_rag_manager(persist_dir=args.db_path)
    
    # Stats only
    if args.stats:
        stats = rag.get_stats()
        print(f"📊 Estatísticas das Coleções:\n")
        for collection, count in stats.items():
            print(f"   {collection}: {count} documentos")
        return
    
    # Initialize LLM if requested
    if args.llm_meta:
        print(f"{Fore.MAGENTA}🧠 Inicializando Gemini para extração de metadados...")
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            print(f"{Fore.RED}❌ GEMINI_API_KEY não encontrada no ambiente!")
            sys.exit(1)
        genai_client = genai.Client(api_key=api_key)

    # Validate input
    if not os.path.exists(args.input):
        print(f"{Fore.RED}❌ Caminho não encontrado: {args.input}")
        sys.exit(1)
    
    # Clear if requested
    if args.clear:
        rag.clear_collection(args.type if args.type != "pecas" else "pecas_modelo")
        print(f"{Fore.YELLOW}🗑️ Coleção limpa.")
    
    # Index based on type
    chunk = not args.no_chunk
    
    if args.type == "lei":
        total = index_legislacao(rag, args.input, chunk=chunk, use_llm=args.llm_meta)
    
    elif args.type == "juris":
        total = index_jurisprudencia(
            rag, args.input,
            tribunal=args.tribunal,
            orgao=args.orgao,
            chunk=chunk,
            use_llm=args.llm_meta
        )
    
    elif args.type == "sei":
        total = index_sei(
            rag, args.input,
            orgao=args.orgao,
            unidade=args.unidade,
            tenant_id=args.tenant_id,
            sigilo=args.sigilo,
            chunk=chunk,
            use_llm=args.llm_meta
        )
    
    elif args.type == "pecas":
        if args.clause_mode:
            # v2.0: Clause Bank - Index by logical block
            print(f"{Fore.MAGENTA}📦 Modo Clause Bank: Indexando por bloco lógico{Style.RESET_ALL}")
            total = index_pecas_clause_bank(
                rag, args.input,
                tipo_peca=args.tipo_peca,
                area=args.area,
                tribunal=args.tribunal_destino
            )
        else:
            total = index_pecas(
                rag, args.input,
                tipo_peca=args.tipo_peca,
                area=args.area,
                rito=args.rito,
                chunk=chunk,
                use_llm=args.llm_meta
            )
    
    # Final stats
    print(f"\n{Fore.GREEN}{'='*60}")
    print(f"✅ INDEXAÇÃO CONCLUÍDA")
    print(f"   Total de chunks indexados: {total}")
    print(f"{'='*60}{Style.RESET_ALL}\n")
    
    # Show updated stats
    stats = rag.get_stats()
    print(f"📊 Estatísticas Atualizadas:")
    for collection, count in stats.items():
        print(f"   {collection}: {count} documentos")

if __name__ == "__main__":
    main()
