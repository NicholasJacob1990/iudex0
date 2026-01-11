"""
Base Formatter - Shared logic for all LLM formatters
Includes: Chunking, Validation, Audit Reports
"""
import os
import re
import time
from abc import ABC, abstractmethod
from colorama import Fore, init

init(autoreset=True)

class BaseFormatter(ABC):
    """
    Abstract base class for transcript formatters.
    Provides shared chunking, validation, and audit functionality.
    """
    
    def __init__(self, model_name="Base"):
        self.model_name = model_name
        self.metrics = {
            "tokens_used": 0,
            "api_calls": 0,
            "start_time": None,
            "end_time": None,
            "cost_usd": 0.0
        }
    
    # =================================================================
    # CHUNKING
    # =================================================================
    
    def _smart_chunk_overlapping(self, text, max_size=25000, overlap=3000):
        """
        Divide texto em chunks com sobreposição para preservar contexto.
        
        Args:
            text: Texto completo
            max_size: Tamanho máximo do chunk (chars)
            overlap: Sobreposição entre chunks (chars)
            
        Returns:
            Lista de chunks
        """
        if len(text) <= max_size:
            return [text]
        
        chunks = []
        start = 0
        
        while start < len(text):
            end = min(start + max_size, len(text))
            
            # Se não é o último chunk, tenta cortar em quebra de linha
            if end < len(text):
                last_newline = text.rfind('\n', start, end)
                if last_newline > start + max_size // 2:
                    end = last_newline
            
            chunks.append(text[start:end])
            start = end - overlap
            
            if start >= len(text):
                break
        
        return chunks
    
    # =================================================================
    # VALIDATION - HEURÍSTICA
    # =================================================================
    
    def _validate_preservation_heuristics(self, original_text, formatted_text):
        """
        Validação rápida baseada em regras (sem LLM).
        Retorna (passou: bool, issues: list)
        """
        issues = []
        
        # 1. Contagem de Referências Legais
        legal_patterns = [
            r'Art\.\s*\d+',
            r'Lei nº\s*[\d.]+',
            r'Súmula\s+\d+',
            r'CF/\d{2}',
        ]
        
        for pattern in legal_patterns:
            count_orig = len(re.findall(pattern, original_text, re.I))
            count_fmt = len(re.findall(pattern, formatted_text, re.I))
            
            if count_fmt < count_orig * 0.9:  # Tolerância de 10%
                issues.append(f"⚠️ Possível perda de referências: {pattern} ({count_orig}→{count_fmt})")
        
        # 2. Contagem de Autores (nomes próprios após palavras-chave)
        author_keywords = ['professor', 'autor', 'segundo', 'conforme']
        author_count_orig = 0
        author_count_fmt = 0
        
        for kw in author_keywords:
            author_count_orig += len(re.findall(f'{kw}\\s+[A-Z][a-zà-ú]+', original_text))
            author_count_fmt += len(re.findall(f'{kw}\\s+[A-Z][a-zà-ú]+', formatted_text))
        
        if author_count_fmt < author_count_orig * 0.8:
            issues.append(f"⚠️ Possível perda de autores ({author_count_orig}→{author_count_fmt})")
        
        # 3. Dicas de Prova
        tip_keywords = ['cai muito', 'atenção', 'pegadinha', 'importante']
        tip_count_orig = sum(len(re.findall(kw, original_text, re.I)) for kw in tip_keywords)
        tip_count_fmt = sum(len(re.findall(kw, formatted_text, re.I)) for kw in tip_keywords)
        
        if tip_count_fmt < tip_count_orig * 0.9:
            issues.append(f"⚠️ Possível perda de dicas ({tip_count_orig}→{tip_count_fmt})")
        
        # 4. Redução de tamanho excessiva
        size_ratio = len(formatted_text) / max(len(original_text), 1)
        if size_ratio < 0.6:
            issues.append(f"⚠️ Texto muito reduzido ({size_ratio:.1%} do original)")
        
        # 5. Frases truncadas (terminam sem pontuação)
        truncated = re.findall(r'[a-zà-ú]\s*$', formatted_text, re.MULTILINE)
        if len(truncated) > 5:
            issues.append(f"⚠️ Possíveis {len(truncated)} frases truncadas")
        
        passed = len(issues) == 0
        return passed, issues
    
    # =================================================================
    # AUDIT REPORT
    # =================================================================
    
    def _generate_audit_report(self, video_name, heuristic_issues, llm_issues):
        """Gera relatório de auditoria em Markdown"""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        
        report = f"""# Relatório de Auditoria - {video_name}
**Modelo:** {self.model_name}  
**Data:** {timestamp}

## 📊 Métricas de Processamento
- **Tokens Usados:** {self.metrics['tokens_used']:,}
- **Chamadas à API:** {self.metrics['api_calls']}
- **Tempo Total:** {self.metrics.get('duration', 0):.1f}s
- **Custo Estimado:** ${self.metrics['cost_usd']:.4f}

## 🔍 Validação Heurística (Automática)
"""
        if not heuristic_issues:
            report += "✅ **PASSOU** - Nenhuma anomalia detectada\n\n"
        else:
            report += "❌ **PROBLEMAS DETECTADOS:**\n"
            for issue in heuristic_issues:
                report += f"- {issue}\n"
            report += "\n"
        
        report += "## 🤖 Validação LLM (Amostragem Estratégica)\n"
        
        if not llm_issues:
            report += "✅ **PASSOU** - Nenhuma omissão detectada nas janelas analisadas\n\n"
        else:
            report += "⚠️ **OMISSÕES DETECTADAS:**\n"
            for issue in llm_issues:
                report += f"- {issue}\n"
            report += "\n"
        
        report += "---\n"
        report += "_Relatório gerado automaticamente pelo sistema de validação_\n"
        
        return report
    
    # =================================================================
    # ABSTRACT METHODS (implementados por subclasses)
    # =================================================================
    
    @abstractmethod
    async def format_transcription(self, transcription, video_name):
        """
        Método principal de formatação.
        Deve ser implementado por cada formatter específico.
        
        Returns:
            str: Texto formatado em Markdown
        """
        pass
    
    @abstractmethod
    async def _format_chunk_async(self, chunk, chunk_idx, system_prompt):
        """
        Formata um chunk individual usando o modelo LLM.
        
        Returns:
            str: Chunk formatado
        """
        pass
