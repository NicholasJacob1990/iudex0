"""
Serviço de integração DJEN (Diário de Justiça Eletrônico Nacional)
Arquitetura: Gatilho DataJud + Crawler Comunica

Referência: https://comunicaapi.pje.jus.br/swagger/index.html (Swagger v1.0.3)
"""

import asyncio
import logging
import re
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple, Union
from dataclasses import dataclass

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# =============================================================================
# Constantes e Configuração
# =============================================================================

# DataJud (CNJ) - Gatilho de movimentações
DEFAULT_DATAJUD_BASE_URL = "https://api-publica.datajud.cnj.jus.br"

# Comunica (PJe) - Crawler de publicações DJEN
DEFAULT_COMUNICA_BASE_URL = "https://comunicaapi.pje.jus.br/api/v1"

# Rate limit config
RATE_LIMIT_WAIT_SECONDS = 60
DEFAULT_TIMEOUT = 30.0

# Paginação (conforme Swagger: itensPorPagina aceita 5 ou 100)
ITEMS_PER_PAGE = 100
MAX_RESULTS_LIMIT = 10000
DEFAULT_MAX_PAGES = 100


# =============================================================================
# Helpers
# =============================================================================

def normalize_npu(npu: str) -> str:
    """
    Remove pontuação do NPU para formato apenas dígitos.
    Exemplo: 1234567-12.2024.8.13.0000 → 12345671220248130000
    """
    return re.sub(r"\D", "", npu or "")


def get_datajud_alias(tribunal_sigla: str) -> str:
    """
    Mapeia sigla do tribunal para alias do DataJud (lowercase).
    Exemplo: TJMG → tjmg, TRF1 → trf1
    """
    return tribunal_sigla.lower()


def extract_tribunal_from_npu(npu: str) -> Optional[str]:
    """
    Extrai código do tribunal do NPU.
    Formato: NNNNNNN-DD.AAAA.J.TR.OOOO
    J.TR = Justiça e Tribunal (ex: 8.13 = TJMG)
    
    Mapeamento básico de códigos:
    - 8.xx = Justiça Estadual (TJs)
    - 4.xx = Justiça Federal (TRFs)
    - 5.xx = Justiça do Trabalho (TRTs)
    """
    clean = normalize_npu(npu)
    if len(clean) < 20:
        return None
    
    # Posições 13-14 (justiça) e 15-16 (tribunal)
    justica = clean[13:14]
    tribunal = clean[14:16]
    
    # Mapeamento simplificado
    mapping = {
        # Justica Estadual (TJs)
        ("8", "01"): "TJAC",
        ("8", "02"): "TJAL",
        ("8", "03"): "TJAP",
        ("8", "04"): "TJAM",
        ("8", "05"): "TJBA",
        ("8", "06"): "TJCE",
        ("8", "07"): "TJDFT",
        ("8", "08"): "TJES",
        ("8", "09"): "TJGO",
        ("8", "10"): "TJMA",
        ("8", "11"): "TJMT",
        ("8", "12"): "TJMS",
        ("8", "13"): "TJMG",
        ("8", "14"): "TJPA",
        ("8", "15"): "TJPB",
        ("8", "16"): "TJPR",
        ("8", "17"): "TJPE",
        ("8", "18"): "TJPI",
        ("8", "19"): "TJRJ",
        ("8", "20"): "TJRN",
        ("8", "21"): "TJRO",
        ("8", "22"): "TJRR",
        ("8", "23"): "TJRS",
        ("8", "24"): "TJSC",
        ("8", "25"): "TJSE",
        ("8", "26"): "TJSP",
        ("8", "27"): "TJTO",
        # Justica Federal (TRFs)
        ("4", "01"): "TRF1",
        ("4", "02"): "TRF2",
        ("4", "03"): "TRF3",
        ("4", "04"): "TRF4",
        ("4", "05"): "TRF5",
        ("4", "06"): "TRF6",
        # Justica do Trabalho (TRTs)
        ("5", "01"): "TRT1",
        ("5", "02"): "TRT2",
        ("5", "03"): "TRT3",
        ("5", "04"): "TRT4",
        ("5", "05"): "TRT5",
        ("5", "06"): "TRT6",
        ("5", "07"): "TRT7",
        ("5", "08"): "TRT8",
        ("5", "09"): "TRT9",
        ("5", "10"): "TRT10",
        ("5", "11"): "TRT11",
        ("5", "12"): "TRT12",
        ("5", "13"): "TRT13",
        ("5", "14"): "TRT14",
        ("5", "15"): "TRT15",
        ("5", "16"): "TRT16",
        ("5", "17"): "TRT17",
        ("5", "18"): "TRT18",
        ("5", "19"): "TRT19",
        ("5", "20"): "TRT20",
        ("5", "21"): "TRT21",
        ("5", "22"): "TRT22",
        ("5", "23"): "TRT23",
        ("5", "24"): "TRT24",
    }
    
    return mapping.get((justica, tribunal))


@dataclass
class DjenIntimationData:
    """Dados de uma intimação do DJEN"""
    id: int
    hash: str
    numero_processo: str
    numero_processo_mascara: str
    tribunal_sigla: str
    tipo_comunicacao: str
    nome_orgao: str
    texto: str
    data_disponibilizacao: str
    meio: str
    link: str
    tipo_documento: str
    nome_classe: str
    numero_comunicacao: int
    ativo: bool
    destinatarios: List[Dict[str, Any]]
    advogados: List[Dict[str, Any]]


@dataclass
class DatajudMovementData:
    """Movimento retornado pelo DataJud"""
    nome: Optional[str]
    data_hora: Optional[str]
    codigo: Optional[str]


@dataclass
class DatajudProcessData:
    """Resumo de processo retornado pelo DataJud"""
    numero_processo: str
    tribunal_sigla: str
    classe: Optional[str]
    orgao_julgador: Optional[str]
    sistema: Optional[str]
    formato: Optional[str]
    grau: Optional[str]
    nivel_sigilo: Optional[str]
    data_ajuizamento: Optional[str]
    data_ultima_atualizacao: Optional[str]
    assuntos: List[str]
    ultimo_movimento: Optional[DatajudMovementData]
    movimentos: List[DatajudMovementData]


# =============================================================================
# DataJud Client (Gatilho)
# =============================================================================

class DataJudClient:
    """
    Cliente para API Pública do DataJud (CNJ).
    Usado como gatilho para detectar movimentações em processos.
    
    Endpoint: POST /api_publica_{tribunal}/_search
    Auth: Header Authorization: APIKey {key}
    """
    
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or settings.CNJ_API_KEY or ""
        self.base_url = base_url or settings.CNJ_API_URL or DEFAULT_DATAJUD_BASE_URL
    
    async def check_updates(
        self,
        npu: str,
        tribunal_sigla: str,
        last_seen: Optional[str] = None
    ) -> Optional[str]:
        """
        Verifica se houve movimentação nova no processo.
        
        Args:
            npu: Número do processo (pode ter pontuação)
            tribunal_sigla: Sigla do tribunal (ex: TJMG)
            last_seen: Data/hora da última movimentação vista (ISO format)
        
        Returns:
            Data/hora completa da movimentação (ISO) se houver novidade, None caso contrário
        """
        alias = get_datajud_alias(tribunal_sigla)
        url = f"{self.base_url}/api_publica_{alias}/_search"
        
        npu_clean = normalize_npu(npu)
        
        payload = {
            "query": {"match": {"numeroProcesso": npu_clean}},
            "sort": [{"movimentos.dataHora": {"order": "desc"}}],
            "size": 1
        }
        
        headers = {
            "Authorization": f"APIKey {self.api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                response = await client.post(url, json=payload, headers=headers)
                
                if response.status_code == 401:
                    logger.error("DataJud: API Key inválida ou expirada")
                    return None
                
                response.raise_for_status()
                data = response.json()
                
                hits = data.get("hits", {}).get("hits", [])
                if not hits:
                    logger.debug(f"DataJud: Processo {npu} não encontrado")
                    return None
                
                source = hits[0].get("_source", {})
                movimentos = source.get("movimentos", [])
                
                if not movimentos:
                    return None
                
                ultimo_mov = movimentos[0]
                data_mov = ultimo_mov.get("dataHora", "")
                if not data_mov:
                    return None
                
                # Se não temos histórico ou se a data é diferente
                if not last_seen or data_mov != last_seen:
                    logger.info(f"DataJud: Novidade em {npu} - {ultimo_mov.get('nome', 'N/A')}")
                    return data_mov
                
                return None
                
        except httpx.HTTPStatusError as e:
            logger.error(f"DataJud HTTP Error: {e.response.status_code}")
            return None
        except Exception as e:
            logger.error(f"DataJud Error: {e}")
            return None

    async def search_process(
        self,
        npu: str,
        tribunal_sigla: str,
        size: int = 5
    ) -> List[DatajudProcessData]:
        """
        Busca metadados do processo no DataJud.
        """
        alias = get_datajud_alias(tribunal_sigla)
        url = f"{self.base_url}/api_publica_{alias}/_search"
        npu_clean = normalize_npu(npu)

        payload = {
            "query": {"match": {"numeroProcesso": npu_clean}},
            "size": size
        }

        headers = {
            "Authorization": f"APIKey {self.api_key}",
            "Content-Type": "application/json"
        }

        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                response = await client.post(url, json=payload, headers=headers)
                if response.status_code == 401:
                    logger.error("DataJud: API Key inválida ou expirada")
                    return []
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"DataJud HTTP Error: {e.response.status_code}")
            return []
        except Exception as e:
            logger.error(f"DataJud Error: {e}")
            return []

        hits = data.get("hits", {}).get("hits", [])
        results: List[DatajudProcessData] = []
        for hit in hits:
            source = hit.get("_source", {}) if isinstance(hit, dict) else {}
            numero = source.get("numeroProcesso") or npu_clean
            classe = (source.get("classe") or {}).get("nome")
            orgao = (source.get("orgaoJulgador") or {}).get("nome")
            sistema = (source.get("sistema") or {}).get("nome")
            formato = (source.get("formato") or {}).get("nome")
            grau = source.get("grau")
            nivel_sigilo = str(source.get("nivelSigilo")) if source.get("nivelSigilo") is not None else None
            data_ajuizamento = source.get("dataAjuizamento")
            data_ultima_atualizacao = source.get("dataHoraUltimaAtualizacao")
            assuntos_raw = source.get("assuntos") or []
            assuntos = [
                item.get("nome")
                for item in assuntos_raw
                if isinstance(item, dict) and item.get("nome")
            ]
            movimentos = source.get("movimentos") or []
            movimentos_full: List[DatajudMovementData] = []
            for movimento in movimentos:
                if not isinstance(movimento, dict):
                    continue
                movimentos_full.append(
                    DatajudMovementData(
                        nome=movimento.get("nome"),
                        data_hora=movimento.get("dataHora"),
                        codigo=str(movimento.get("codigo")) if movimento.get("codigo") is not None else None
                    )
                )
            ultimo_mov = movimentos[0] if movimentos else {}
            ultimo_movimento = None
            if isinstance(ultimo_mov, dict) and ultimo_mov:
                ultimo_movimento = DatajudMovementData(
                    nome=ultimo_mov.get("nome"),
                    data_hora=ultimo_mov.get("dataHora"),
                    codigo=str(ultimo_mov.get("codigo")) if ultimo_mov.get("codigo") is not None else None
                )

            results.append(
                DatajudProcessData(
                    numero_processo=numero,
                    tribunal_sigla=tribunal_sigla.upper(),
                    classe=classe,
                    orgao_julgador=orgao,
                    sistema=sistema,
                    formato=formato,
                    grau=grau,
                    nivel_sigilo=nivel_sigilo,
                    data_ajuizamento=data_ajuizamento,
                    data_ultima_atualizacao=data_ultima_atualizacao,
                    assuntos=assuntos,
                    ultimo_movimento=ultimo_movimento,
                    movimentos=movimentos_full
                )
            )

        return results


# =============================================================================
# Comunica Client (Crawler DJEN)
# =============================================================================

class ComunicaClient:
    """
    Cliente para API Comunica (comunicaapi.pje.jus.br).
    Usado para buscar publicações do DJEN.
    
    Endpoint: GET /api/v1/comunicacao
    Rate Limit: x-ratelimit-remaining, Retry-After, erro 429 → aguardar 60s
    Paginação: itensPorPagina (5 ou 100), pagina (1-based)
    Limite: 10.000 resultados por busca textual
    """
    
    def __init__(self, base_url: Optional[str] = None):
        self.base_url = base_url or settings.DJEN_API_URL or DEFAULT_COMUNICA_BASE_URL
    
    async def search(
        self,
        sigla_tribunal: Optional[str] = None,
        numero_oab: Optional[str] = None,
        uf_oab: Optional[str] = None,
        nome_advogado: Optional[str] = None,
        nome_parte: Optional[str] = None,
        texto: Optional[str] = None,
        numero_processo: Optional[str] = None,
        data_inicio: Optional[str] = None,
        data_fim: Optional[str] = None,
        meio: str = "D",
        itens_por_pagina: Optional[int] = None,
        max_pages: int = DEFAULT_MAX_PAGES,
        include_meta: bool = False
    ) -> Union[List[DjenIntimationData], Tuple[List[DjenIntimationData], Optional[int], int]]:
        """
        Busca publicações no DJEN.
        
        Args:
            sigla_tribunal: Ex: TJMG, TRF1 (obrigatório se não usar outros filtros)
            numero_oab: Apenas números
            uf_oab: Sigla UF (MG, SP)
            nome_advogado: Busca textual parcial
            nome_parte: Busca textual parcial
            numero_processo: Apenas dígitos
            texto: Busca textual
            data_inicio: YYYY-MM-DD
            data_fim: YYYY-MM-DD
            meio: D (Diário) ou E (Edital)
            max_pages: Limite de páginas para evitar loop infinito
        
        Returns:
            Lista de intimações encontradas
        """
        # Validar filtro obrigatório
        has_filter = any([
            sigla_tribunal,
            nome_parte,
            nome_advogado,
            numero_oab,
            numero_processo,
            texto
        ])
        
        if not has_filter:
            logger.error("Comunica: Pelo menos um filtro obrigatório é necessário")
            return []
        
        # Construir parâmetros
        items_per_page = ITEMS_PER_PAGE
        if itens_por_pagina in (5, 100):
            items_per_page = itens_por_pagina

        params: Dict[str, Any] = {
            "itensPorPagina": items_per_page,
            "pagina": 1,
            "meio": meio
        }
        
        if sigla_tribunal:
            params["siglaTribunal"] = sigla_tribunal
        if numero_oab:
            params["numeroOab"] = numero_oab.replace(".", "").replace("-", "")
        if uf_oab:
            params["ufOab"] = uf_oab.upper()
        if nome_advogado:
            params["nomeAdvogado"] = nome_advogado
        if nome_parte:
            params["nomeParte"] = nome_parte
        if texto:
            params["texto"] = texto
        if numero_processo:
            params["numeroProcesso"] = normalize_npu(numero_processo)
        if data_inicio:
            params["dataDisponibilizacaoInicio"] = data_inicio
        if data_fim:
            params["dataDisponibilizacaoFim"] = data_fim
        
        headers = {
            "User-Agent": "Iudex/1.0 (legal-tech-app)",
            "Accept": "application/json"
        }
        
        results: List[DjenIntimationData] = []
        total_count: Optional[int] = None
        
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            page = 1
            while page <= max_pages:
                params["pagina"] = page
                
                try:
                    response = await client.get(
                        f"{self.base_url}/comunicacao",
                        params=params,
                        headers=headers
                    )
                    
                    rate_remaining = response.headers.get("x-ratelimit-remaining")
                    rate_remaining_int = int(rate_remaining) if rate_remaining and rate_remaining.isdigit() else None
                    if rate_remaining_int is not None and rate_remaining_int < 5:
                        logger.warning(f"Comunica: Rate limit baixo ({rate_remaining_int} restantes)")
                    
                    # Tratar erro 429 (Rate Limit)
                    if response.status_code == 429:
                        retry_after = response.headers.get("Retry-After", RATE_LIMIT_WAIT_SECONDS)
                        wait_time = int(retry_after) if str(retry_after).isdigit() else RATE_LIMIT_WAIT_SECONDS
                        logger.warning(f"Comunica: Rate limit (429). Aguardando {wait_time}s...")
                        await asyncio.sleep(wait_time)
                        continue  # Tenta a mesma página novamente
                    
                    response.raise_for_status()
                    data = response.json()
                    if total_count is None:
                        total_count = data.get("count")
                    
                    items = data.get("items", [])
                    if not items:
                        break
                    
                    # Converter para dataclass
                    for item in items:
                        try:
                            intimation = DjenIntimationData(
                                id=item.get("id", 0),
                                hash=item.get("hash", ""),
                                numero_processo=item.get("numero_processo", ""),
                                numero_processo_mascara=item.get("numeroprocessocommascara", ""),
                                tribunal_sigla=item.get("siglaTribunal", ""),
                                tipo_comunicacao=item.get("tipoComunicacao", ""),
                                nome_orgao=item.get("nomeOrgao", ""),
                                texto=item.get("texto", ""),
                                data_disponibilizacao=item.get("data_disponibilizacao", ""),
                                meio=item.get("meio", ""),
                                link=item.get("link", ""),
                                tipo_documento=item.get("tipoDocumento", ""),
                                nome_classe=item.get("nomeClasse", ""),
                                numero_comunicacao=item.get("numeroComunicacao", 0),
                                ativo=item.get("ativo", True),
                                destinatarios=item.get("destinatarios", []),
                                advogados=item.get("destinatarioadvogados", [])
                            )
                            results.append(intimation)
                        except Exception as e:
                            logger.warning(f"Comunica: Erro ao parsear item: {e}")
                    
                    logger.info(f"Comunica: Página {page} - {len(items)} itens")
                    
                    # Critérios de parada
                    if len(items) < items_per_page:
                        break
                    if len(results) >= MAX_RESULTS_LIMIT:
                        logger.warning(f"Comunica: Limite de {MAX_RESULTS_LIMIT} resultados atingido")
                        break
                    
                    # Pausa ética entre páginas (respeita rate limit)
                    if rate_remaining_int is not None and rate_remaining_int <= 0:
                        await asyncio.sleep(RATE_LIMIT_WAIT_SECONDS)
                    else:
                        await asyncio.sleep(1)
                    
                    page += 1
                    
                except httpx.HTTPStatusError as e:
                    logger.error(f"Comunica HTTP Error: {e.response.status_code}")
                    break
                except Exception as e:
                    logger.error(f"Comunica Error: {e}")
                    break
        
        logger.info(f"Comunica: Total de {len(results)} intimações encontradas")
        if include_meta:
            return results, total_count, items_per_page
        return results
    
    async def fetch_by_process(
        self,
        npu: str,
        tribunal_sigla: str,
        data_alvo: str,
        meio: str = "D"
    ) -> List[DjenIntimationData]:
        """
        Busca intimações para um processo específico em uma data.
        Usado após gatilho do DataJud.
        
        Args:
            npu: Número do processo
            tribunal_sigla: Sigla do tribunal
            data_alvo: Data da publicação (YYYY-MM-DD)
            meio: D (Diário) ou E (Edital)
        """
        return await self.search(
            sigla_tribunal=tribunal_sigla,
            numero_processo=npu,
            data_inicio=data_alvo,
            data_fim=data_alvo,
            meio=meio,
            max_pages=10  # Limitar para busca pontual
        )


# =============================================================================
# DjenService - Orquestrador
# =============================================================================

class DjenService:
    """
    Serviço principal de integração DJEN.
    Orquestra DataJud (gatilho) + Comunica (crawler).
    """
    
    def __init__(self):
        self.datajud = DataJudClient()
        self.comunica = ComunicaClient()

    async def fetch_metadata(
        self,
        npu: str,
        tribunal_sigla: str
    ) -> List[DatajudProcessData]:
        """
        Busca metadados do processo no DataJud.
        """
        return await self.datajud.search_process(npu, tribunal_sigla)
    
    async def check_and_fetch(
        self,
        npu: str,
        tribunal_sigla: str,
        last_seen: Optional[str] = None
    ) -> Tuple[Optional[str], List[DjenIntimationData]]:
        """
        Fluxo completo: verifica DataJud → se novidade → busca Comunica.
        
        Args:
            npu: Número do processo
            tribunal_sigla: Sigla do tribunal (ex: TJMG)
            last_seen: Última movimentação vista (ISO datetime)
        
        Returns:
            Tupla com data/hora da movimentação e lista de intimações (vazia se não houver novidade)
        """
        # 1. Verificar gatilho no DataJud
        data_mov = await self.datajud.check_updates(npu, tribunal_sigla, last_seen)
        
        if not data_mov:
            return None, []
        
        # 2. Buscar teor no Comunica
        data_alvo = data_mov.split("T")[0]
        logger.info(f"DJEN: Novidade detectada em {npu} ({data_mov}). Buscando teor...")
        intimations = await self.comunica.fetch_by_process(npu, tribunal_sigla, data_alvo)
        return data_mov, intimations
    
    async def search_by_oab(
        self,
        numero_oab: str,
        uf_oab: str,
        tribunal_sigla: Optional[str] = None,
        data_inicio: Optional[str] = None,
        data_fim: Optional[str] = None,
        meio: str = "D",
        max_pages: int = DEFAULT_MAX_PAGES
    ) -> List[DjenIntimationData]:
        """
        Busca por OAB (modo descoberta).
        """
        return await self.comunica.search(
            sigla_tribunal=tribunal_sigla,
            numero_oab=numero_oab,
            uf_oab=uf_oab,
            data_inicio=data_inicio,
            data_fim=data_fim,
            meio=meio,
            max_pages=max_pages
        )
    
    async def search_by_name(
        self,
        nome_parte: Optional[str] = None,
        nome_advogado: Optional[str] = None,
        tribunal_sigla: Optional[str] = None,
        data_inicio: Optional[str] = None,
        data_fim: Optional[str] = None
    ) -> List[DjenIntimationData]:
        """
        Busca por nome (modo descoberta).
        """
        return await self.comunica.search(
            sigla_tribunal=tribunal_sigla,
            nome_parte=nome_parte,
            nome_advogado=nome_advogado,
            data_inicio=data_inicio,
            data_fim=data_fim
        )
    
    async def search_by_process(
        self,
        numero_processo: str,
        tribunal_sigla: Optional[str] = None,
        data_inicio: Optional[str] = None,
        data_fim: Optional[str] = None,
        meio: str = "D",
        max_pages: int = DEFAULT_MAX_PAGES
    ) -> List[DjenIntimationData]:
        """
        Busca direta por número do processo.
        """
        # Tentar extrair tribunal do NPU se não informado
        if not tribunal_sigla:
            tribunal_sigla = extract_tribunal_from_npu(numero_processo)
        
        return await self.comunica.search(
            sigla_tribunal=tribunal_sigla,
            numero_processo=numero_processo,
            data_inicio=data_inicio,
            data_fim=data_fim,
            meio=meio,
            max_pages=max_pages
        )


# =============================================================================
# Factory
# =============================================================================

def get_djen_service() -> DjenService:
    """Factory para injeção de dependência."""
    return DjenService()
