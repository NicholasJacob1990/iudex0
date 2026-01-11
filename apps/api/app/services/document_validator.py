"""
Validador de Documentos Jurídicos

Valida estrutura, conteúdo e conformidade de documentos jurídicos
"""

from typing import Dict, List, Any, Optional, Tuple
import re
from datetime import datetime
from loguru import logger


class DocumentValidator:
    """
    Validador que verifica conformidade e qualidade de documentos jurídicos
    """
    
    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.suggestions: List[str] = []
    
    def validate_petition(self, content: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Valida petição inicial
        
        Returns:
            Dict com status de validação, erros, warnings e sugestões
        """
        self._reset()
        
        logger.info("Validando petição inicial...")
        
        # Validações estruturais
        self._check_petition_structure(content)
        
        # Validações de conteúdo
        self._check_legal_citations(content)
        self._check_formatting(content)
        self._check_required_elements_petition(content)
        
        # Validações de metadados
        self._validate_metadata(metadata)
        
        is_valid = len(self.errors) == 0
        
        return {
            "valid": is_valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "suggestions": self.suggestions,
            "score": self._calculate_quality_score()
        }
    
    def validate_contract(self, content: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Valida contrato"""
        self._reset()
        
        logger.info("Validando contrato...")
        
        # Validações estruturais de contrato
        self._check_contract_structure(content)
        self._check_contract_clauses(content)
        self._check_parties_identification(content)
        
        # Validações gerais
        self._check_formatting(content)
        
        is_valid = len(self.errors) == 0
        
        return {
            "valid": is_valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "suggestions": self.suggestions,
            "score": self._calculate_quality_score()
        }
    
    def validate_opinion(self, content: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Valida parecer jurídico"""
        self._reset()
        
        logger.info("Validando parecer jurídico...")
        
        self._check_opinion_structure(content)
        self._check_legal_citations(content)
        self._check_formatting(content)
        
        is_valid = len(self.errors) == 0
        
        return {
            "valid": is_valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "suggestions": self.suggestions,
            "score": self._calculate_quality_score()
        }
    
    def _reset(self):
        """Reseta listas de validação"""
        self.errors = []
        self.warnings = []
        self.suggestions = []
    
    def _check_petition_structure(self, content: str):
        """Verifica estrutura básica de petição"""
        content_upper = content.upper()
        
        # Verificar endereçamento
        if not re.search(r'EXCELENTÍSSIMO.*JUIZ', content_upper, re.IGNORECASE):
            self.warnings.append("Endereçamento ao juízo não encontrado ou incompleto")
        
        # Verificar seções essenciais
        required_sections = [
            (r'DOS FATOS', "Seção 'DOS FATOS' não encontrada"),
            (r'DO DIREITO', "Seção 'DO DIREITO' não encontrada"),
            (r'DO[S]? PEDIDO[S]?', "Seção 'DOS PEDIDOS' não encontrada"),
        ]
        
        for pattern, error_msg in required_sections:
            if not re.search(pattern, content_upper):
                self.errors.append(error_msg)
        
        # Verificar valor da causa
        if not re.search(r'VALOR DA CAUSA|ATRIBUI.*À CAUSA', content_upper):
            self.warnings.append("Valor da causa não especificado")
        
        # Verificar fechamento
        if not re.search(r'TERMOS EM QUE|NESTES TERMOS', content_upper):
            self.warnings.append("Fechamento padrão não encontrado")
        
        if not re.search(r'PEDE DEFERIMENTO', content_upper):
            self.warnings.append("'Pede deferimento' não encontrado no fechamento")
    
    def _check_contract_structure(self, content: str):
        """Verifica estrutura básica de contrato"""
        content_upper = content.upper()
        
        # Verificar título
        if not re.search(r'^.*CONTRATO', content_upper):
            self.warnings.append("Título do contrato não identificado claramente")
        
        # Verificar identificação das partes
        if 'CONTRATANTE' not in content_upper:
            self.errors.append("Identificação do CONTRATANTE não encontrada")
        
        if 'CONTRATADO' not in content_upper and 'CONTRATADA' not in content_upper:
            self.errors.append("Identificação do CONTRATADO não encontrada")
        
        # Verificar cláusulas essenciais
        essential_clauses = [
            ('OBJETO', "Cláusula de OBJETO não encontrada"),
            ('PRAZO|VIGÊNCIA', "Cláusula de PRAZO/VIGÊNCIA não encontrada"),
            ('PAGAMENTO|VALOR', "Cláusula de PAGAMENTO não encontrada"),
            ('RESCISÃO|RESILIÇÃO', "Cláusula de RESCISÃO não encontrada"),
            ('FORO', "Cláusula de eleição de FORO não encontrada"),
        ]
        
        for pattern, error_msg in essential_clauses:
            if not re.search(pattern, content_upper):
                self.warnings.append(error_msg)
    
    def _check_contract_clauses(self, content: str):
        """Verifica numeração e estrutura de cláusulas"""
        # Verificar se há cláusulas numeradas
        clauses = re.findall(r'CLÁUSULA\s+([A-Z]+|\d+)', content, re.IGNORECASE)
        
        if not clauses:
            self.warnings.append("Nenhuma cláusula numerada identificada")
            return
        
        # Verificar ordem das cláusulas
        # (Simplificado - em produção, fazer verificação mais robusta)
        if len(clauses) < 3:
            self.warnings.append("Contrato com poucas cláusulas - verifique se está completo")
    
    def _check_parties_identification(self, content: str):
        """Verifica identificação completa das partes"""
        content_lower = content.lower()
        
        # Verificar CPF/CNPJ
        if not re.search(r'\d{3}\.\d{3}\.\d{3}-\d{2}|\d{11}', content):
            if not re.search(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|\d{14}', content):
                self.warnings.append("CPF ou CNPJ das partes não encontrado")
        
        # Verificar endereço
        if 'endereço' not in content_lower and 'residência' not in content_lower:
            self.warnings.append("Endereço das partes não especificado")
    
    def _check_opinion_structure(self, content: str):
        """Verifica estrutura de parecer jurídico"""
        content_upper = content.upper()
        
        # Verificar seções
        if 'CONSULTA' not in content_upper and 'QUESTÃO' not in content_upper:
            self.errors.append("Seção de CONSULTA/QUESTÃO não encontrada")
        
        if 'ANÁLISE' not in content_upper:
            self.errors.append("Seção de ANÁLISE não encontrada")
        
        if 'CONCLUSÃO' not in content_upper and 'PARECER' not in content_upper:
            self.errors.append("Seção de CONCLUSÃO não encontrada")
        
        # Verificar fechamento característico
        if 'S.M.J' not in content_upper and 'SALVO MELHOR JUÍZO' not in content_upper:
            self.suggestions.append("Considere adicionar 's.m.j.' (salvo melhor juízo) ao final")
    
    def _check_legal_citations(self, content: str):
        """Verifica citações legais"""
        
        # Procurar por artigos de lei
        articles = re.findall(r'art(?:igo|\.)?\s*\d+', content, re.IGNORECASE)
        
        if not articles:
            self.warnings.append("Nenhuma citação legal (artigo de lei) encontrada")
        
        # Verificar se há menção a código/lei
        laws = re.findall(
            r'(código civil|código penal|cpc|cpp|clt|constituição federal|cf)',
            content,
            re.IGNORECASE
        )
        
        if articles and not laws:
            self.warnings.append("Artigos citados sem menção explícita à lei/código de origem")
        
        # Verificar jurisprudência
        jurisprudence = re.findall(
            r'(stf|stj|tst|tjsp|tjrj|tribunal|súmula)',
            content,
            re.IGNORECASE
        )
        
        if not jurisprudence:
            self.suggestions.append("Considere adicionar jurisprudência para fortalecer argumentação")
    
    def _check_formatting(self, content: str):
        """Verifica formatação básica"""
        
        # Verificar se há estrutura de seções
        sections = re.findall(r'^#{1,3}\s+.*$|^[A-Z\s]+$', content, re.MULTILINE)
        
        if len(sections) < 2:
            self.warnings.append("Documento parece ter poucas seções/divisões")
        
        # Verificar tamanho mínimo
        if len(content) < 500:
            self.warnings.append("Documento muito curto - verifique se está completo")
        
        # Verificar parágrafos muito longos
        paragraphs = content.split('\n\n')
        long_paragraphs = [p for p in paragraphs if len(p) > 1000]
        
        if long_paragraphs:
            self.suggestions.append(
                f"Há {len(long_paragraphs)} parágrafo(s) muito longo(s) - "
                "considere dividir para melhor legibilidade"
            )
    
    def _check_required_elements_petition(self, content: str):
        """Verifica elementos obrigatórios de petição"""
        
        # Verificar qualificação das partes
        if not re.search(r'(cpf|cnpj|rg)', content, re.IGNORECASE):
            self.warnings.append("Qualificação das partes parece incompleta (falta CPF/CNPJ)")
        
        # Verificar pedidos específicos
        content_upper = content.upper()
        if 'PEDIDOS' in content_upper or 'PEDIDO' in content_upper:
            # Verificar se há requerimentos após a seção de pedidos
            pedidos_section = content_upper.split('PEDIDO')[1] if 'PEDIDO' in content_upper else ""
            
            if 'REQUER' not in pedidos_section and 'REQUER-SE' not in pedidos_section:
                self.warnings.append("Seção de pedidos sem 'requer' explícito")
    
    def _validate_metadata(self, metadata: Dict[str, Any]):
        """Valida metadados do documento"""
        
        if not metadata.get('document_type'):
            self.warnings.append("Tipo de documento não especificado nos metadados")
        
        if not metadata.get('user_id'):
            self.errors.append("Usuário autor não identificado")
    
    def _calculate_quality_score(self) -> float:
        """
        Calcula score de qualidade baseado em erros e warnings
        
        Returns:
            Score de 0.0 a 10.0
        """
        # Começar com 10
        score = 10.0
        
        # Deduzir por erros (mais grave)
        score -= len(self.errors) * 2.0
        
        # Deduzir por warnings (menos grave)
        score -= len(self.warnings) * 0.5
        
        # Sugestões não afetam score mas são consideradas para melhoria
        
        # Garantir que score está entre 0 e 10
        return max(0.0, min(10.0, score))
    
    def validate_document(
        self,
        content: str,
        document_type: str,
        metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Valida documento de acordo com seu tipo
        
        Args:
            content: Conteúdo do documento
            document_type: Tipo do documento (petition, contract, opinion, etc.)
            metadata: Metadados do documento
        
        Returns:
            Resultado da validação com erros, warnings e score
        """
        
        if document_type.lower() in ['petition', 'petição', 'ação']:
            return self.validate_petition(content, metadata)
        
        elif document_type.lower() in ['contract', 'contrato']:
            return self.validate_contract(content, metadata)
        
        elif document_type.lower() in ['opinion', 'parecer']:
            return self.validate_opinion(content, metadata)
        
        else:
            # Validação genérica
            self._reset()
            self._check_formatting(content)
            self._check_legal_citations(content)
            
            return {
                "valid": len(self.errors) == 0,
                "errors": self.errors,
                "warnings": self.warnings,
                "suggestions": self.suggestions,
                "score": self._calculate_quality_score()
            }
    
    @staticmethod
    def check_document_length(content: str) -> Dict[str, Any]:
        """Calcula estatísticas de tamanho do documento"""
        words = len(content.split())
        chars = len(content)
        chars_no_spaces = len(content.replace(" ", ""))
        lines = len(content.split("\n"))
        paragraphs = len([p for p in content.split("\n\n") if p.strip()])
        
        # Páginas estimadas (250 palavras por página A4)
        estimated_pages = max(1, words // 250)
        
        return {
            "words": words,
            "characters": chars,
            "characters_no_spaces": chars_no_spaces,
            "lines": lines,
            "paragraphs": paragraphs,
            "estimated_pages": estimated_pages,
            "reading_time_minutes": max(1, words // 200)  # ~200 palavras/min
        }
    
    @staticmethod
    def extract_legal_references(content: str) -> Dict[str, List[str]]:
        """Extrai referências legais do documento"""
        
        # Artigos de lei
        articles = re.findall(
            r'art(?:igo|\.)?\s*(\d+(?:º|°)?)[,\s]*(inciso\s+[IVX]+)?[,\s]*(§\s*\d+)?',
            content,
            re.IGNORECASE
        )
        
        # Leis e códigos
        laws = re.findall(
            r'(lei\s+n?º?\s*[\d\.]+/\d+|código\s+\w+|cf/\d+|cpc|cpp|cc)',
            content,
            re.IGNORECASE
        )
        
        # Jurisprudência
        jurisprudence = re.findall(
            r'((?:stf|stj|tst|trf|tj[a-z]{2})\s+[-–]\s*\w+.*?(?:\d+|\n))',
            content,
            re.IGNORECASE
        )
        
        return {
            "articles": [str(a[0]) for a in articles] if articles else [],
            "laws": list(set(laws)),
            "jurisprudence": list(set(jurisprudence))
        }

