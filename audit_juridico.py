import os
import sys
import logging
import json
import re
from typing import List, Optional, Dict, Any
from google import genai
from google.genai import types

# Configuração de Logger
logger = logging.getLogger("AuditJuridico")
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S')

PROMPT_AUDITORIA_JURIDICA = """
ATUE COMO UM AUDITOR JURÍDICO SÊNIOR (DESEMBARGADOR APOSENTADO).

**DATA DE REFERÊNCIA: {data_atual}**

Sua tarefa é REVISAR MINUCIOSAMENTE a peça jurídica fornecida.
Você deve ser IMPLACÁVEL com erros processuais, citações inexistentes e falhas lógicas.

---
## CHECKLIST DE AUDITORIA

### 1. 🔴 REQUISITOS PROCESSUAIS (CPC/CPP)
*   **Se for Petição Inicial (Art. 319 CPC):** Faltou qualificação, causa de pedir, pedido, valor da causa, opção por audiência?
*   **Se for Contestação (Art. 337 CPC):** Faltou arguir preliminares óbvias (inépcia, ilegitimidade)? Houve impugnação específica dos fatos?
*   **Se for Recurso:** Há tópico de tempestividade e preparo?

### 2. 🔴 ALUCINAÇÃO DE PRECEDENTES (GRAVÍSSIMO)
*   Verifique cada Súmula, REsp ou AI citado.
*   **O número existe? O teor condiz com a citação?**
*   Se o texto cita "Súmula 1234 do STF" e ela não existe, APONTE O ERRO.

### 3. 🔴 VIGÊNCIA LEGAL
*   Citações de artigos revogados (ex: CPC/73, CC/16) sem contexto histórico.
*   Interpretação superada por Súmula Vinculante.

### 4. 🟡 COESÃO E LÓGICA
*   O pedido decorre logicamente da causa de pedir? (Silogismo válido?)
*   Existem contradições (ex: pede gratuidade mas anexa comprovante de renda alta)?

---
## SAÍDA ESPERADA

Gere um RELATÓRIO DE AUDITORIA FORMAL em Markdown:

# ⚖️ Relatório de Conformidade Jurídica

## 1. Veredito Geral
(Aprovado / Aprovado com Ressalvas / Reprovado)
**Confiabilidade Técnica:** (0/10)

## 2. Falhas Processuais (Art. 319/337 CPC)
* [ ] (Liste itens faltantes ou "Nenhum vício processual detectado")

## 3. Auditoria de Citações (Alucinações)
* 🟢 (Válidas)
* 🔴 (Citações Suspeitas/Inexistentes - Liste com destaque)

## 4. Sugestões de Melhoria
(Recomendações de técnica redacional ou estratégia)

---
<peca_analisada>
{texto}
</peca_analisada>
"""

def normalize_law_number(raw_num: str) -> str:
    """Normalize law numbers to standard format (e.g., 866693 -> 8666/93)."""
    raw_num = raw_num.replace('.', '').replace('/', '').strip()
    if not raw_num.isdigit():
        return raw_num
    
    n = int(raw_num)
    if len(raw_num) >= 6:
        # Try to split: last 2 digits as year
        potential_year = int(raw_num[-2:])
        potential_law = raw_num[:-2]
        if (90 <= potential_year <= 99) or (0 <= potential_year <= 30):
            year_full = 1900 + potential_year if potential_year >= 90 else 2000 + potential_year
            return f"{potential_law}/{potential_year:02d}"
            
    if 1000 <= n <= 99999:
        return raw_num
    return raw_num

def is_valid_law_ref(law_num: str) -> bool:
    """Validate if a law reference is plausible."""
    clean = law_num.replace('.', '').replace('/', '').strip()
    if len(clean) < 3: return False
    try:
        if int(clean.split('/')[0]) < 100: return False
    except: return False
    return True

def extract_citations_with_context(text: str) -> List[Dict]:
    """Extrai citações e o parágrafo onde elas aparecem (HIL v4.2 Port)."""
    # Dividir por parágrafos
    paragraphs = [p.strip() for p in text.split('\n') if len(p.strip()) > 20]
    
    # Padrões v4.2 do HIL (Expandido)
    patterns = {
        'LEI': r'[Ll]ei\s*(?:n[º°]?\s*)?(\d{3,8}(?:\.\d{3})?(?:/\d{2,4})?)',
        'SUMULA': r'[Ss]úmula\s*(?:[Vv]inculante\s*)?(?:n[º°]?\s*)?(\d{1,4})',
        'ARTIGO': r'[Aa]rt(?:igo)?\.?\s*(\d{1,4})',
        'DECRETO': r'[Dd]ecreto\s*(?:Rio\s*)?(?:n[º°]?\s*)?(\d{3,6}(?:\.\d{3})?(?:/\d{2,4})?)',
        'JULGADO': [
            r'(?:REsp|RE|RMS|Ag(?:Rg)?|RCL|EDcl|AI|AC)\s*(?:n[º°]?\s*)?[\d\./-]+',
            r'(?:HC|MS|MI|HD)\s*(?:n[º°]?\s*)?[\d\./-]+',
            r'(?:ADI|ADPF|ADC|ADO)\s*(?:n[º°]?\s*)?\d+',
            r'Acórdão\s*(?:TCU|TCE[/-]?\w*)?\s*(?:n[º°]?\s*)?[\d\./-]+',
            r'Parecer\s*(?:AGU|PGE|PGM|PGFN)?\s*(?:n[º°]?\s*)?[\d\./-]+',
            r'(?:Tema|RG)\s*(?:n[º°]?\s*)?\d+\s*(?:STF|STJ)?',
            r'Tese\s*(?:STF|STJ)\s*(?:n[º°]?\s*)?\d+',
            r'Informativo\s*(?:STF|STJ)?\s*(?:n[º°]?\s*)?\d+',
            r'Súmula\s*(?:TJ[A-Z]{2}|TRF\d?)\s*(?:n[º°]?\s*)?\d+',
        ]
    }
    
    results = []
    seen = set()
    
    for para in paragraphs:
        # Leis (com normalização)
        for m in re.finditer(patterns['LEI'], para):
            raw = m.group(1)
            norm = normalize_law_number(raw)
            if is_valid_law_ref(norm):
                full_citation = f"Lei {norm}"
                if full_citation.lower() not in seen:
                    results.append({"citation": full_citation, "context": para})
                    seen.add(full_citation.lower())

        # Súmulas
        for m in re.finditer(patterns['SUMULA'], para):
            full_citation = f"Súmula {m.group(1)}" # Simplified logic for audit
            if full_citation.lower() not in seen:
                results.append({"citation": full_citation, "context": para})
                seen.add(full_citation.lower())

        # Julgados (Lista de regexes)
        for pat in patterns['JULGADO']:
            for m in re.finditer(pat, para, re.IGNORECASE):
                citation = m.group(0).strip()
                citation = re.sub(r'\s+', ' ', citation)
                if len(citation) > 3 and citation.lower() not in seen:
                    results.append({"citation": citation, "context": para})
                    seen.add(citation.lower())
                    
        # Artigos (sem normalização complexa)
        for m in re.finditer(patterns['ARTIGO'], para):
             citation = f"Art. {m.group(1)}"
             if citation.lower() not in seen:
                results.append({"citation": citation, "context": para})
                seen.add(citation.lower())

    return results

def verify_semantic_interpretation(client, model_name, citation: str, context: str, foundation: str) -> Dict:
    """Usa LLM para verificar se a interpretação da citação na peça está correta"""
    prompt = f"""
    Como um Auditor Juridico Senior, verifique se a interpretação da fonte citada está correta.

    Fonte Citada: {citation}
    Texto da Peça: "...{context}..."
    Fundamento Real (RAG): "{foundation[:2000]}..."

    Tarefa:
    1. A citação existe na realidade (baseado no fundamento RAG)?
    2. A interpretação dada na peça condiz com o fundamento? (Ex: o advogado não distorceu o sentido?)

    Responda em JSON:
    {{
        "existe": bool,
        "interpretacao_correta": bool,
        "analise_curta": "string max 15 palavras",
        "score_confianca": float (0-1)
    }}
    """
    try:
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1
            )
        )
        if response.text:
            return json.loads(response.text)
    except:
        pass
    return {}

def analyze_citations(text: str, rag_manager, client=None, model_name=None) -> List[Dict]:
    """
    Analisa citações retornando lista estruturada com status de alucinação/interpretação.
    """
    citation_items = extract_citations_with_context(text)
    if not citation_items:
        return []

    analyzed_citations = []
    
    for item in citation_items:
        citation = item['citation']
        context = item['context']
        
        # Busca exata ou híbrida
        results = rag_manager.hybrid_search(citation, top_k=1)
        
        citation_data = {
            "citation": citation,
            "context_snippet": context[:200],
            "status": "not_found",
            "score": 0.0,
            "foundation": "",
            "message": "Não encontrada na base RAG"
        }

        if not results:
            # Tenta Web Search antes de desistir
            if client and model_name:
                logger.info(f"🌐 Nenhum resultado local para '{citation}'. Acionando Web Search...")
                web_verdict = verify_online_grounding(client, model_name, citation)
                if web_verdict.get('existe', False):
                    citation_data["status"] = "valid_online"
                    citation_data["message"] = f"Validado via Web: {web_verdict.get('summary', '')}"
                    urls_list = [u.get('uri', u) if isinstance(u, dict) else u for u in web_verdict.get('urls', [])][:3]
                    urls_str = ', '.join(urls_list) or 'Google Search'
                    citation_data["foundation"] = web_verdict.get('summary', '') + f"\nFontes: {urls_str}"
                    citation_data["score"] = 0.9
                else:
                    citation_data["status"] = "hallucination"
                    citation_data["message"] = "Não encontrada (Local + Web)"
            analyzed_citations.append(citation_data)
            continue
            
        best = results[0]
        score = best['final_score']
        bm25_score = best.get('bm25_score', 0)
        foundation_text = best.get('text', "")
        
        citation_data["score"] = score
        citation_data["foundation"] = foundation_text
        
        status_icon = "valid"
        extra_info = ""
        
        # Se o score for alto o suficiente, fazemos o Reranking Semântico
        if client and model_name and (score > 0.4 or bm25_score > 0.3):
            verdict = verify_semantic_interpretation(client, model_name, citation, context, foundation_text)
            if verdict:
                if not verdict.get('interpretacao_correta', True):
                    status_icon = "suspicious"
                    extra_info = verdict.get('analise_curta', 'Interpretação suspeita')
                elif not verdict.get('existe', True):
                    status_icon = "hallucination"
                    extra_info = "Alucinação Provável"
                else:
                    extra_info = "Validação Semântica OK"
        
        # Fallback para scores baixos (Web Search via Google Grounding)
        elif client and model_name and (score < 0.4):
             logger.info(f"🌐 Score local baixo ({score:.2f}) para '{citation}'. Acionando Web Search...")
             web_verdict = verify_online_grounding(client, model_name, citation)
             
             if web_verdict.get('existe', False):
                 status_icon = "valid_online" # Novo status
                 extra_info = f"Validado via Web Search: {web_verdict.get('summary', '')}"
                 # Atualiza dados com info da web
                 urls_list = [u.get('uri', u) if isinstance(u, dict) else u for u in web_verdict.get('urls', [])][:3]
                 urls_str = ', '.join(urls_list) or 'Google Search'
                 citation_data["foundation"] = web_verdict.get('summary', '') + f"\nFontes: {urls_str}"
                 citation_data["score"] = 0.9 # Confiança artificial para online
             else:
                 status_icon = "not_found"
                 extra_info = "Não encontrada na base local nem na Web"

        # Fallback para scores médios
        elif status_icon == "valid" and (score < 0.65 and bm25_score < 0.5):
            status_icon = "warning"
            extra_info = "Baixa similaridade base"
            
        citation_data["status"] = status_icon
        citation_data["message"] = extra_info
        analyzed_citations.append(citation_data)
        
    return analyzed_citations

# =============================================================================
# CITATION CACHE (v1.0)
# =============================================================================

CITATION_CACHE_PATH = os.path.expanduser("~/.iudex/citation_cache.json")

def _load_citation_cache() -> Dict:
    """Carrega cache de citações verificadas do disco."""
    try:
        if os.path.exists(CITATION_CACHE_PATH):
            with open(CITATION_CACHE_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"⚠️ Erro ao carregar cache: {e}")
    return {}

def _save_citation_cache(cache: Dict):
    """Salva cache de citações no disco."""
    try:
        os.makedirs(os.path.dirname(CITATION_CACHE_PATH), exist_ok=True)
        with open(CITATION_CACHE_PATH, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"⚠️ Erro ao salvar cache: {e}")

def verify_online_grounding(client, model_name, citation: str) -> Dict:
    """
    Usa Google Search Grounding para verificar existência de citação na web.
    
    v2.0: Extrai URLs diretamente do groundingMetadata ao invés de pedir para a LLM.
    
    Features:
    - Cache persistente em disco (~/.iudex/citation_cache.json)
    - Extrai URLs reais dos groundingChunks
    - Retorna snippets/evidências dos groundingSupports
    """
    # Normalizar chave de cache
    cache_key = citation.lower().strip()
    
    # Verificar cache
    cache = _load_citation_cache()
    if cache_key in cache:
        logger.info(f"💾 Cache hit para '{citation}'")
        return cache[cache_key]
    
    logger.info(f"🌐 Buscando na web: '{citation}'...")
    
    # Prompt simplificado - a LLM só precisa interpretar se existe ou não
    prompt = f"""
    A seguinte fonte jurídica brasileira existe e é válida?
    "{citation}"
    
    Responda em JSON apenas com:
    {{
        "existe": true/false,
        "summary": "resumo de 1 linha do que é",
        "tribunal": "STF/STJ/TJ se aplicável",
        "data": "data se encontrada"
    }}
    """
    
    result = {
        "existe": False, 
        "summary": "Não encontrada", 
        "urls": [],                   # URLs reais de grounding_chunks
        "response_segments": [],      # Trechos da resposta com suporte (grounding_supports)
        "tribunal": "", 
        "data": "",
        "search_queries": []          # Queries executadas pelo Gemini
    }
    
    try:
        # Configuração para Google Search Tool
        tools = [types.Tool(google_search=types.GoogleSearch())]
        
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=tools,
                response_mime_type="application/json",
                temperature=0.0
            )
        )
        
        # === EXTRAIR GROUNDING METADATA (v2.0) ===
        if hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]
            
            # Extrair grounding_metadata
            if hasattr(candidate, 'grounding_metadata') and candidate.grounding_metadata:
                gm = candidate.grounding_metadata
                
                # Web Search Queries executadas
                if hasattr(gm, 'web_search_queries') and gm.web_search_queries:
                    result["search_queries"] = list(gm.web_search_queries)
                
                # Grounding Chunks (fontes com URI e título)
                if hasattr(gm, 'grounding_chunks') and gm.grounding_chunks:
                    for chunk in gm.grounding_chunks:
                        if hasattr(chunk, 'web') and chunk.web:
                            url_info = {
                                "uri": getattr(chunk.web, 'uri', ''),
                                "title": getattr(chunk.web, 'title', '')
                            }
                            if url_info["uri"]:
                                result["urls"].append(url_info)
                
                # Grounding Supports (evidências/snippets)
                if hasattr(gm, 'grounding_supports') and gm.grounding_supports:
                    for support in gm.grounding_supports:
                        if hasattr(support, 'segment') and support.segment:
                            snippet = getattr(support.segment, 'text', '')
                            if snippet:
                                result["response_segments"].append(snippet)
                
                # Se encontrou URLs, provavelmente existe
                if result["urls"]:
                    result["existe"] = True
        
        # Complementar com resposta textual da LLM
        if response.text:
            try:
                data = json.loads(response.text)
                # Mesclar dados da LLM (summary, tribunal, data)
                result["summary"] = data.get("summary", result["summary"])
                result["tribunal"] = data.get("tribunal", result["tribunal"])
                result["data"] = data.get("data", result["data"])
                # Se a LLM disse que existe MAS não temos URLs, confiar na LLM também
                if data.get("existe") and not result["existe"]:
                    result["existe"] = True
            except:
                # Fallback se vier markdown
                match = re.search(r'\{.*\}', response.text, re.DOTALL)
                if match:
                    try:
                        data = json.loads(match.group(0))
                        result["summary"] = data.get("summary", result["summary"])
                        result["tribunal"] = data.get("tribunal", result["tribunal"])
                        result["data"] = data.get("data", result["data"])
                    except:
                        pass
                        
    except Exception as e:
        logger.warning(f"⚠️ Erro no Web Search Fallback: {e}")
        result["summary"] = f"Erro: {str(e)}"
    
    # Salvar no cache
    # Converter urls para formato serializável
    result["urls"] = [u if isinstance(u, dict) else {"uri": u, "title": ""} for u in result["urls"]]
    cache[cache_key] = result
    _save_citation_cache(cache)
    
    logger.info(f"   📊 Resultado: existe={result['existe']}, {len(result['urls'])} URLs, {len(result['response_segments'])} segments")
    
    return result


# =============================================================================
# MULTI-PROVIDER WEB SEARCH (v3.0)
# =============================================================================

def _verify_via_openai(citation: str, model_name: str = "gpt-5.2-chat-latest") -> Dict:
    """
    Verifica citação usando OpenAI Responses API com Web Search.
    
    Requer: pip install openai
    Requer: OPENAI_API_KEY no ambiente
    """
    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        
        prompt = f"""
        A seguinte fonte jurídica brasileira existe e é válida?
        "{citation}"
        
        Pesquise na web e responda em JSON:
        {{
            "existe": true/false,
            "summary": "resumo de 1 linha",
            "tribunal": "STF/STJ/TJ se aplicável",
            "data": "data se encontrada"
        }}
        """
        
        resp = client.responses.create(
            model=model_name,
            tools=[{"type": "web_search_preview"}],
            tool_choice={"type": "web_search_preview"},
            input=prompt
        )
        
        result = {
            "existe": False,
            "summary": "Não encontrada",
            "urls": [],
            "response_segments": [],
            "tribunal": "",
            "data": "",
            "search_queries": [],
            "provider": "openai"
        }
        
        # Extrair texto da resposta
        if hasattr(resp, 'output_text') and resp.output_text:
            try:
                data = json.loads(resp.output_text)
                result["existe"] = data.get("existe", False)
                result["summary"] = data.get("summary", "")
                result["tribunal"] = data.get("tribunal", "")
                result["data"] = data.get("data", "")
            except:
                # Tentar extrair JSON do texto
                match = re.search(r'\{.*\}', resp.output_text, re.DOTALL)
                if match:
                    try:
                        data = json.loads(match.group(0))
                        result["existe"] = data.get("existe", False)
                        result["summary"] = data.get("summary", "")
                    except:
                        pass
                        
        # Extrair URLs do output (web_search_call items)
        if hasattr(resp, 'output'):
            for item in resp.output:
                if hasattr(item, 'type') and item.type == 'web_search_call':
                    # OpenAI retorna metadados da busca
                    if hasattr(item, 'results'):
                        for r in item.results:
                            result["urls"].append({
                                "uri": getattr(r, 'url', ''),
                                "title": getattr(r, 'title', '')
                            })
                            
        logger.info(f"   📊 [OpenAI] existe={result['existe']}, {len(result['urls'])} URLs")
        return result
        
    except ImportError:
        logger.warning("⚠️ OpenAI SDK não instalado. Use: pip install openai")
        return {"existe": False, "summary": "OpenAI SDK não disponível", "urls": [], "provider": "openai"}
    except Exception as e:
        logger.warning(f"⚠️ Erro no Web Search (OpenAI): {e}")
        return {"existe": False, "summary": f"Erro: {str(e)}", "urls": [], "provider": "openai"}


def _verify_via_claude(citation: str, model_name: str = "claude-sonnet-4-5") -> Dict:
    """
    Verifica citação usando Anthropic Claude com Web Search.
    
    Requer: pip install anthropic
    Requer: ANTHROPIC_API_KEY no ambiente
    """
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        
        prompt = f"""
        A seguinte fonte jurídica brasileira existe e é válida?
        "{citation}"
        
        Pesquise na internet e responda em JSON:
        {{
            "existe": true/false,
            "summary": "resumo de 1 linha",
            "tribunal": "STF/STJ/TJ se aplicável",
            "data": "data se encontrada"
        }}
        
        Inclua links das fontes encontradas.
        """
        
        resp = client.messages.create(
            model=model_name,
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
            tools=[{
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": 3,
                "allowed_domains": ["gov.br", "stf.jus.br", "stj.jus.br", "jusbrasil.com.br", "planalto.gov.br"]
            }]
        )
        
        result = {
            "existe": False,
            "summary": "Não encontrada",
            "urls": [],
            "response_segments": [],
            "tribunal": "",
            "data": "",
            "search_queries": [],
            "provider": "claude"
        }
        
        # Extrair texto da resposta
        if resp.content:
            for block in resp.content:
                if hasattr(block, 'type'):
                    if block.type == 'text':
                        text = getattr(block, 'text', '')
                        # Tentar extrair JSON
                        match = re.search(r'\{.*\}', text, re.DOTALL)
                        if match:
                            try:
                                data = json.loads(match.group(0))
                                result["existe"] = data.get("existe", False)
                                result["summary"] = data.get("summary", "")
                                result["tribunal"] = data.get("tribunal", "")
                                result["data"] = data.get("data", "")
                            except:
                                pass
                    elif block.type == 'tool_use' and getattr(block, 'name', '') == 'web_search':
                        # Claude retorna resultados da busca
                        if hasattr(block, 'input'):
                            result["search_queries"].append(block.input)
                            
        # Extrair URLs de citações no texto (Claude inclui inline)
        if resp.content:
            full_text = ' '.join([getattr(b, 'text', '') for b in resp.content if hasattr(b, 'text')])
            url_matches = re.findall(r'https?://[^\s\)\]]+', full_text)
            for url in url_matches[:5]:
                result["urls"].append({"uri": url, "title": ""})
                
        logger.info(f"   📊 [Claude] existe={result['existe']}, {len(result['urls'])} URLs")
        return result
        
    except ImportError:
        logger.warning("⚠️ Anthropic SDK não instalado. Use: pip install anthropic")
        return {"existe": False, "summary": "Anthropic SDK não disponível", "urls": [], "provider": "claude"}
    except Exception as e:
        logger.warning(f"⚠️ Erro no Web Search (Claude): {e}")
        return {"existe": False, "summary": f"Erro: {str(e)}", "urls": [], "provider": "claude"}


def verify_citation_online(citation: str, provider: str = "gemini", client=None, model_name: str = None) -> Dict:
    """
    Função unificada para verificação de citação via Web Search.
    
    Args:
        citation: Texto da citação (ex: "REsp 1.234.567")
        provider: "gemini", "openai", ou "claude"
        client: Cliente Gemini (se provider="gemini")
        model_name: Nome do modelo a usar
        
    Returns:
        Dict com existe, summary, urls, etc.
    """
    # Checar cache primeiro (independente do provider)
    cache_key = citation.lower().strip()
    cache = _load_citation_cache()
    if cache_key in cache:
        logger.info(f"💾 Cache hit para '{citation}'")
        return cache[cache_key]
    
    # Executar verificação pelo provider apropriado
    if provider == "gemini" and client:
        result = verify_online_grounding(client, model_name or "gemini-3-flash-preview", citation)
    elif provider == "openai":
        result = _verify_via_openai(citation, model_name or "gpt-5.2-chat-latest")
        # Salvar no cache
        cache[cache_key] = result
        _save_citation_cache(cache)
    elif provider == "claude":
        result = _verify_via_claude(citation, model_name or "claude-sonnet-4-5")
        # Salvar no cache
        cache[cache_key] = result
        _save_citation_cache(cache)
    else:
        result = {"existe": False, "summary": f"Provider '{provider}' não suportado", "urls": []}
    
    return result


def check_hallucinations(text: str, rag_manager, client=None, model_name=None) -> str:
    """Verifica citações e retorna relatório em Markdown (Legacy)"""
    analyzed = analyze_citations(text, rag_manager, client, model_name)
    if not analyzed:
        return ""
    
    report = "\n\n## 🕵️‍♂️ Verificação Avançada de Fontes (RAG + Reranking)\n"
    
    icon_map = {
        "valid": "🟢",
        "valid_online": "🔵", # New icon for web sources
        "suspicious": "🟠",
        "hallucination": "🔴",
        "warning": "⚠️",
        "not_found": "❓"
    }
    
    for item in analyzed:
        icon = icon_map.get(item["status"], "❓")
        report += f"* {icon} **{item['citation']}**: {item['message']} (Score: {item['score']:.2f})\n"
            
    return report

def auditar_peca(client, model_name, texto_completo, output_path, rag_manager=None):
    """
    Executa a auditoria jurídica.
    Se 'rag_manager' for fornecido, executa checagem de alucinação.
    """
    logger.info("⚖️ Iniciando Auditoria Jurídica...")
    
    from datetime import datetime
    data_atual = datetime.now().strftime("%d/%m/%Y")
    
    rag_report = ""
    if rag_manager:
        logger.info("🕵️‍♂️ Executando verificação de alucinação (RAG + Reranking)...")
        rag_report = check_hallucinations(texto_completo, rag_manager, client=client, model_name=model_name)
    
    prompt = PROMPT_AUDITORIA_JURIDICA.format(texto=texto_completo, data_atual=data_atual)
    
    try:
        # Adaptando para a API do google-genai v1/v2
        if isinstance(client, genai.GenerativeModel):
             response = client.generate_content(prompt)
        else:
             # v3.0: Usando ThinkingConfig HIGH para auditoria (raciocínio profundo)
             response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=16000,
                    thinking_config=types.ThinkingConfig(
                        include_thoughts=False,
                        thinking_level="HIGH"  # Auditoria requer raciocínio profundo
                    ),
                    safety_settings=[
                        types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
                        types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
                        types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
                        types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
                    ]
                )
             )

        if response.text:
            relatorio = response.text
            full_content = f"<!-- Auditoria: {data_atual} -->\n\n{relatorio}"
            
            # Adicionar relatório RAG se houver
            if rag_report:
                full_content += rag_report
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(full_content)
                
            logger.info(f"✅ Relatório Salvo: {output_path}")
            return True
        else:
            logger.warning("⚠️ Auditoria vazia.")
            return False

    except Exception as e:
        logger.error(f"❌ Erro na auditoria: {e}")
        return False

def audit_document_text(client, model_name: str, text: str, rag_manager=None) -> Dict[str, Any]:
    """
    Gera metadados de auditoria completos (Relatório + Citações) sem efeitos colaterais (IO).
    Ideal para uso via API/Orchestrator.
    """
    from datetime import datetime
    data_atual = datetime.now().strftime("%d/%m/%Y")
    
    # 1. Gerar Relatório de Auditoria (LLM)
    prompt = PROMPT_AUDITORIA_JURIDICA.format(texto=text, data_atual=data_atual)
    audit_report = ""
    
    try:
        # Detectar tipo de cliente e ajustar chamada
        if hasattr(client, 'models'): # google-genai v1+
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=16000,
                    thinking_config=types.ThinkingConfig(include_thoughts=False, thinking_level="HIGH"),
                    safety_settings=[
                        types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
                        types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
                        types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
                        types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
                    ]
                )
            )
        else: # Legacy
            response = client.generate_content(prompt)
            
        audit_report = response.text if response and response.text else "Auditoria não gerou texto."
        
    except Exception as e:
        logger.error(f"Erro na geração do relatório de auditoria: {e}")
        audit_report = f"Erro técnico na auditoria: {str(e)}"

    # 2. Analisar Citações (Se houver RAG Manager)
    citations_data = []
    if rag_manager:
        try:
            citations_data = analyze_citations(text, rag_manager, client, model_name)
        except Exception as e:
            logger.error(f"Erro na análise de citações: {e}")
            citations_data = [{"error": str(e)}]
            
    return {
        "audit_report_markdown": audit_report,
        "citations": citations_data,
        "audit_date": data_atual
    }

# CLI Wrapper
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("file", help="Arquivo Markdown/Text para auditar")
    args = parser.parse_args()
    
    if not os.path.exists(args.file):
        print("Arquivo não encontrado.")
        sys.exit(1)
        
    with open(args.file, 'r', encoding='utf-8') as f:
        text = f.read()
    
    # Init simple client
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("API Key não encontrada.")
        sys.exit(1)
        
    client = genai.Client(api_key=api_key)
    out_path = os.path.splitext(args.file)[0] + "_AUDITORIA_LEGAL.md"
    
    auditar_peca(client, "gemini-3-flash-preview", text, out_path)
