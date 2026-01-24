"""
Fidelity Matcher - Matching fuzzy para referências legais.
Resolve falsos positivos em auditorias de fidelidade.

O problema central: o sistema de auditoria detectava como "ausentes" referências
que estavam presentes no texto formatado, mas com formatação diferente:
- "tema 1070" (RAW) vs "Tema 1.070" (formatado)
- "artigo 345" (RAW) vs "Art. 345" (formatado)
- "ADPF 1063" (RAW) vs "ADPF 1.063" (formatado)

Este módulo resolve isso através de matching fuzzy baseado em:
1. Extração de dígitos (ignora formatação)
2. Padrões regex flexíveis para cada tipo de referência
3. Validação cruzada RAW vs Formatado
"""
import re
import logging
from typing import List, Optional, Tuple, Dict, Any

logger = logging.getLogger(__name__)


class FidelityMatcher:
    """Verifica presença de referências legais com tolerância a formatação."""
    
    # Mapeamento de tipos para padrões regex
    # {digits} será substituído pelos dígitos escapados
    # {fuzzy_digits} será substituído por padrão com separadores opcionais
    PATTERNS = {
        "tema": [
            r'\b[Tt]ema\s*{digits}\b',
            r'\b[Tt]ema\s*{fuzzy_digits}\b',
            r'\b[Tt]ema\s+de\s+[Rr]epercuss[ãa]o\s+[Gg]eral\s*{fuzzy_digits}\b',
        ],
        "artigo": [
            r'\b[Aa]rt(?:igo)?\.?\s*{digits}\b',
            r'\b[Aa]rt(?:igo)?\.?\s*{fuzzy_digits}\b',
            r'\b[Aa]rt\.?\s*{digits}\s*(?:,|do|da|dos|das)\b',
        ],
        "adpf": [
            r'\b[Aa][Dd][Pp][Ff]\s*{digits}\b',
            r'\b[Aa][Dd][Pp][Ff]\s*{fuzzy_digits}\b',
        ],
        "adi": [
            r'\b[Aa][Dd][Ii]\s*{digits}\b',
            r'\b[Aa][Dd][Ii]\s*{fuzzy_digits}\b',
        ],
        "re": [
            r'\b[Rr][Ee]\s*{digits}\b',
            r'\b[Rr]ecurso\s+[Ee]xtraordin[áa]rio\s*{fuzzy_digits}\b',
        ],
        "lei": [
            r'\b[Ll]ei\s*(?:n[º°]?\s*)?{digits}\b',
            r'\b[Ll]ei\s*(?:n[º°]?\s*)?{fuzzy_digits}\b',
            r'\b[Ll]ei\s+[Cc]omplementar\s*(?:n[º°]?\s*)?{fuzzy_digits}\b',
            r'\bLC\s*{fuzzy_digits}\b',
        ],
        "sumula": [
            r'\b[Ss](?:ú|u)mula\s*(?:vinculante\s*)?(?:n[º°]?\s*)?{digits}\b',
            r'\b[Ss](?:ú|u)mula\s*(?:vinculante\s*)?(?:n[º°]?\s*)?{fuzzy_digits}\b',
            r'\bSV\s*{digits}\b',
        ],
        "decreto": [
            r'\b[Dd]ecreto\s*(?:n[º°]?\s*)?{digits}\b',
            r'\b[Dd]ecreto\s*(?:n[º°]?\s*)?{fuzzy_digits}\b',
        ],
    }
    
    @staticmethod
    def extract_digits(reference: str) -> str:
        """Extrai apenas dígitos de uma referência."""
        return re.sub(r'\D+', '', reference or '')
    
    @staticmethod
    def build_fuzzy_pattern(digits: str) -> str:
        r"""
        Cria padrão que aceita separadores entre dígitos.
        Exemplo: "1070" -> "1[\s\./-]*0[\s\./-]*7[\s\./-]*0"
        Isso permite match de: 1070, 1.070, 1 070, 1-070
        """
        sep = r'[\s\./-]*'
        return sep.join(list(digits))
    
    @staticmethod
    def normalize_text(text: str) -> str:
        """Normaliza texto para comparação."""
        if not text:
            return ""
        # Remove pontuação de números (1.070 -> 1070)
        text = re.sub(r'(\d)\.(\d)', r'\1\2', text)
        # Normaliza espaços
        text = re.sub(r'\s+', ' ', text)
        return text.lower().strip()
    
    @classmethod
    def detect_reference_type(cls, reference: str) -> str:
        """Detecta automaticamente o tipo de referência legal."""
        ref_lower = reference.lower()
        
        if "tema" in ref_lower:
            return "tema"
        if "artigo" in ref_lower or "art." in ref_lower or "art " in ref_lower:
            return "artigo"
        if "adpf" in ref_lower:
            return "adpf"
        if "adi" in ref_lower and "adicional" not in ref_lower:
            return "adi"
        if ref_lower.startswith("re ") or "recurso extraordinário" in ref_lower:
            return "re"
        if "lei" in ref_lower or ref_lower.startswith("lc "):
            return "lei"
        if "súmula" in ref_lower or "sumula" in ref_lower or ref_lower.startswith("sv "):
            return "sumula"
        if "decreto" in ref_lower:
            return "decreto"
        
        return "generico"
    
    @classmethod
    def exists_in_text(
        cls, 
        reference: str, 
        text: str, 
        ref_type: str = "auto"
    ) -> Tuple[bool, Optional[str]]:
        """
        Verifica se referência existe no texto com matching fuzzy.
        
        Args:
            reference: A referência a procurar (ex: "tema 1070")
            text: O texto onde procurar
            ref_type: Tipo de referência ("tema", "artigo", etc.) ou "auto"
        
        Returns:
            Tuple[exists: bool, matched_text: Optional[str]]
        """
        if not reference or not text:
            return False, None
        
        digits = cls.extract_digits(reference)
        if not digits:
            # Se não tem dígitos, tenta match exato
            try:
                pattern = rf'\b{re.escape(reference)}\b'
                match = re.search(pattern, text, flags=re.IGNORECASE)
                if match:
                    return True, match.group(0)
            except re.error:
                pass
            return False, None
        
        fuzzy_digits = cls.build_fuzzy_pattern(digits)
        
        # Detecta tipo automaticamente se não especificado
        if ref_type == "auto":
            ref_type = cls.detect_reference_type(reference)
        
        patterns = cls.PATTERNS.get(ref_type, [])
        
        # Adiciona padrões genéricos de fallback
        fallback_patterns = [
            rf'\b{re.escape(reference)}\b',
            rf'\b{digits}\b',
            rf'\b{fuzzy_digits}\b',
        ]
        
        all_patterns = list(patterns) + fallback_patterns
        
        for pattern_template in all_patterns:
            try:
                # Substitui placeholders
                pattern = pattern_template
                if '{digits}' in pattern:
                    pattern = pattern.replace('{digits}', re.escape(digits))
                if '{fuzzy_digits}' in pattern:
                    pattern = pattern.replace('{fuzzy_digits}', fuzzy_digits)
                
                match = re.search(pattern, text, flags=re.IGNORECASE)
                if match:
                    return True, match.group(0)
            except re.error as e:
                logger.debug(f"Regex error for pattern '{pattern_template}': {e}")
                continue
        
        return False, None
    
    @classmethod
    def validate_issue(
        cls, 
        issue: Dict[str, Any], 
        raw_text: str, 
        formatted_text: str
    ) -> Dict[str, Any]:
        """
        Valida se uma issue de auditoria é real ou falso positivo.
        
        Adiciona campos ao issue:
        - is_false_positive: bool - True se a referência existe no formatado
        - validation_evidence: str - Explicação da validação
        - confidence: str - "high", "medium", "low"
        
        Args:
            issue: Dicionário da issue a validar
            raw_text: Texto RAW original
            formatted_text: Texto formatado
        
        Returns:
            Issue atualizado com campos de validação
        """
        reference = issue.get("reference", "")
        issue_type = issue.get("type", "")
        description = issue.get("description", "")
        
        # Se não tem referência, tenta extrair do description
        if not reference and description:
            # Tenta extrair referência do final da descrição
            parts = description.split(":")
            if len(parts) > 1:
                reference = parts[-1].strip()
        
        if not reference:
            issue["is_false_positive"] = False
            issue["validation_evidence"] = "Sem referência para validar"
            issue["confidence"] = "low"
            return issue
        
        # Determina tipo de referência
        ref_type = "auto"
        if "julgado" in issue_type or "tema" in issue_type.lower():
            ref_type = "tema"
        elif "lei" in issue_type or "law" in issue_type:
            ref_type = "lei"
        elif "sumula" in issue_type:
            ref_type = "sumula"
        elif "decreto" in issue_type:
            ref_type = "decreto"
        elif "artigo" in issue_type:
            ref_type = "artigo"
        
        # Verifica presença no formatado
        exists_formatted, matched_formatted = cls.exists_in_text(
            reference, formatted_text, ref_type
        )
        
        if exists_formatted:
            issue["is_false_positive"] = True
            issue["validation_evidence"] = f"✅ Encontrado no formatado: '{matched_formatted}'"
            issue["confidence"] = "high"
            logger.debug(f"FALSO POSITIVO: '{reference}' encontrado como '{matched_formatted}'")
        else:
            # Verifica se está no RAW (para confirmar que é omissão real)
            exists_raw, matched_raw = cls.exists_in_text(reference, raw_text, ref_type)
            
            if exists_raw:
                issue["is_false_positive"] = False
                issue["validation_evidence"] = (
                    f"⚠️ Presente no RAW: '{matched_raw}', "
                    f"ausente no formatado"
                )
                issue["confidence"] = "high"
            else:
                # Não está nem no RAW nem no formatado
                # Pode ser um erro da análise inicial
                issue["is_false_positive"] = True
                issue["validation_evidence"] = (
                    "❓ Não encontrado nem no RAW nem no formatado - "
                    "possível erro de detecção"
                )
                issue["confidence"] = "medium"
        
        return issue
    
    @classmethod
    def filter_false_positives(
        cls,
        issues: List[Dict[str, Any]],
        raw_text: str,
        formatted_text: str
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Filtra issues removendo falsos positivos.
        
        Returns:
            Tuple[real_issues, false_positives]
        """
        real_issues = []
        false_positives = []
        
        for issue in issues:
            validated = cls.validate_issue(issue.copy(), raw_text, formatted_text)
            
            if validated.get("is_false_positive"):
                false_positives.append(validated)
                logger.info(
                    f"⏭️ Falso positivo removido: {validated.get('reference', '')} - "
                    f"{validated.get('validation_evidence', '')}"
                )
            else:
                real_issues.append(validated)
        
        return real_issues, false_positives
    
    @classmethod
    def extract_evidence_snippets(
        cls,
        reference: str,
        raw_text: str,
        formatted_text: str,
        ref_type: str = "auto",
        window_chars: int = 300,
        max_snippets: int = 3
    ) -> Dict[str, Any]:
        """
        Extrai snippets (trechos) do RAW e formatado onde a referência aparece.
        
        Retorna um dicionário com:
        - raw_snippets: Lista de trechos do RAW
        - formatted_snippets: Lista de trechos do formatado
        - found_in_raw: bool
        - found_in_formatted: bool
        
        Args:
            reference: Referência a buscar (ex: "tema 1070")
            raw_text: Texto RAW original
            formatted_text: Texto formatado
            ref_type: Tipo de referência ou "auto"
            window_chars: Tamanho da janela de contexto (caracteres antes/depois)
            max_snippets: Máximo de snippets por texto
        """
        result = {
            "raw_snippets": [],
            "formatted_snippets": [],
            "found_in_raw": False,
            "found_in_formatted": False,
        }
        
        if not reference:
            return result
        
        # Detecta tipo se necessário
        if ref_type == "auto":
            ref_type = cls.detect_reference_type(reference)
        
        # Extrai dígitos para busca fuzzy
        digits = cls.extract_digits(reference)
        if not digits:
            # Sem dígitos, usa referência completa
            patterns = [re.escape(reference)]
        else:
            fuzzy_digits = cls.build_fuzzy_pattern(digits)
            patterns = cls.PATTERNS.get(ref_type, [])
            
            # Formata padrões
            formatted_patterns = []
            for pattern_template in patterns:
                try:
                    pattern = pattern_template.replace('{digits}', re.escape(digits))
                    pattern = pattern.replace('{fuzzy_digits}', fuzzy_digits)
                    formatted_patterns.append(pattern)
                except Exception:
                    continue
            
            # Adiciona fallbacks
            formatted_patterns.extend([
                re.escape(reference),
                rf'\b{digits}\b',
                rf'\b{fuzzy_digits}\b',
            ])
            
            patterns = formatted_patterns
        
        # Extrai snippets do RAW
        for pattern in patterns:
            try:
                for match in re.finditer(pattern, raw_text, flags=re.IGNORECASE):
                    if len(result["raw_snippets"]) >= max_snippets:
                        break
                    
                    start, end = match.span()
                    snippet_start = max(0, start - window_chars)
                    snippet_end = min(len(raw_text), end + window_chars)
                    snippet = raw_text[snippet_start:snippet_end].strip()
                    
                    # Evita duplicatas
                    if snippet not in [s["snippet"] for s in result["raw_snippets"]]:
                        result["raw_snippets"].append({
                            "snippet": snippet,
                            "match": match.group(0),
                            "start": start,
                            "end": end,
                        })
                        result["found_in_raw"] = True
                
                if result["raw_snippets"]:
                    break  # Encontrou com este padrão, não precisa tentar outros
            except re.error:
                continue
        
        # Extrai snippets do formatado
        for pattern in patterns:
            try:
                for match in re.finditer(pattern, formatted_text, flags=re.IGNORECASE):
                    if len(result["formatted_snippets"]) >= max_snippets:
                        break
                    
                    start, end = match.span()
                    snippet_start = max(0, start - window_chars)
                    snippet_end = min(len(formatted_text), end + window_chars)
                    snippet = formatted_text[snippet_start:snippet_end].strip()
                    
                    # Evita duplicatas
                    if snippet not in [s["snippet"] for s in result["formatted_snippets"]]:
                        result["formatted_snippets"].append({
                            "snippet": snippet,
                            "match": match.group(0),
                            "start": start,
                            "end": end,
                        })
                        result["found_in_formatted"] = True
                
                if result["formatted_snippets"]:
                    break
            except re.error:
                continue
        
        return result
    
    @classmethod
    def enrich_issue_with_evidence(
        cls,
        issue: Dict[str, Any],
        raw_text: str,
        formatted_text: str
    ) -> Dict[str, Any]:
        """
        Enriquece uma issue com evidências do RAW e formatado.
        
        Adiciona/atualiza campos:
        - raw_evidence: Lista de evidências do RAW (formato esperado pelo frontend)
        - evidence_formatted: Primeira evidência do formatado (string)
        - has_evidence: bool indicando se encontrou evidências
        """
        reference = issue.get("reference", "")
        
        # Se não tem referência, tenta extrair do description
        if not reference:
            description = issue.get("description", "")
            # Tenta extrair referência comum patterns
            patterns_map = [
                (r'tema\s+(\d+)', 'tema'),
                (r'art\.?\s+(\d+)', 'art.'),
                (r'lei\s+n?[º°]?\s*(\d+)', 'lei'),
                (r'súmula\s+(\d+)', 'sum'),
                (r'decreto\s+(\d+)', 'decreto'),
                (r'adpf\s+(\d+)', 'adpf'),
            ]
            for pattern, prefix in patterns_map:
                match = re.search(pattern, description, re.IGNORECASE)
                if match:
                    # Reconstrói referência
                    reference = f"{prefix} {match.group(1)}"
                    break
        
        if not reference:
            # Sem referência clara, retorna issue inalterada
            return issue
        
        # Extrai evidências
        evidence = cls.extract_evidence_snippets(
            reference, raw_text, formatted_text, ref_type="auto"
        )
        
        # Formata para o padrão esperado pelo frontend
        if evidence["raw_snippets"]:
            # Frontend espera lista de objetos ou strings
            issue["raw_evidence"] = [
                {
                    "snippet": snip["snippet"],
                    "match": snip["match"],
                    "text": snip["snippet"],  # Alias para compatibilidade
                }
                for snip in evidence["raw_snippets"]
            ]
        
        if evidence["formatted_snippets"]:
            # Frontend espera string para evidence_formatted
            issue["evidence_formatted"] = evidence["formatted_snippets"][0]["snippet"]
        
        issue["has_evidence"] = evidence["found_in_raw"] or evidence["found_in_formatted"]
        
        return issue


def validate_issues_batch(
    issues: List[Dict[str, Any]],
    raw_text: str,
    formatted_text: str,
    remove_false_positives: bool = True
) -> Dict[str, Any]:
    """
    Função utilitária para validar um lote de issues.
    
    Returns:
        Dict com:
        - issues: Lista de issues validadas (sem ou com falsos positivos)
        - total_original: Contagem original
        - total_real: Contagem de issues reais
        - total_false_positives: Contagem de falsos positivos
        - false_positives: Lista de falsos positivos (para debug)
    """
    real_issues, false_positives = FidelityMatcher.filter_false_positives(
        issues, raw_text, formatted_text
    )
    
    return {
        "issues": real_issues if remove_false_positives else (real_issues + false_positives),
        "total_original": len(issues),
        "total_real": len(real_issues),
        "total_false_positives": len(false_positives),
        "false_positives": false_positives,
    }
