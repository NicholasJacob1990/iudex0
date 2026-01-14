"""
Audit Service
Port of audit_juridico.py for API integration.
"""

import os
import logging
import json
import re
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from app.services.docs_utils import save_as_word_juridico
from app.services.ai.genai_utils import extract_genai_text

# Logger precisa existir antes de qualquer try/except que o use
logger = logging.getLogger("AuditService")

# Import the core audit module from root
import sys
from pathlib import Path
root_path = str(Path(__file__).parent.parent.parent.parent.parent.parent)
if root_path not in sys.path:
    sys.path.append(root_path)

try:
    from audit_juridico import audit_document_text
except ImportError:
    logger.warning("⚠️ Não foi possível importar audit_juridico da raiz. Usando lógica de fallback.")
    audit_document_text = None

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

class AuditService:
    def __init__(self):
        self.client = self._init_client()
        self.model_name = "gemini-1.5-pro-002"
        
    def _init_client(self):
        try:
            from google import genai
            api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
            return genai.Client(api_key=api_key) if api_key else None
        except Exception as e:
            logger.error(f"Erro ao init client audit: {e}")
            return None

    def _get_client(self):
        """Returns the Gemini client for external use."""
        if not self.client:
            self.client = self._init_client()
        return self.client

    def _get_model_name(self) -> str:
        """Returns the model name for external use."""
        return self.model_name

    def audit_document(self, text: str, model_name: Optional[str] = None, rag_manager=None) -> Dict:
        """
        Public method used by Orchestrator.
        Uses audit_juridico.py logic if available.
        """
        if audit_document_text:
            return audit_document_text(
                client=self.client,
                model_name=model_name or self.model_name,
                text=text,
                rag_manager=rag_manager
            )
        
        # Fallback to internal logic if import failed
        logger.warning("Using fallback audit logic")
        # Return a structure matching what orchestrator expects
        return {
            "audit_report_markdown": "Auditoria Básica (Fallback)\n\nRelatório não disponível (falha no módulo)",
            "citations": []
        }

    async def verificar_citacoes_rapido(self, text: str) -> Dict:
        """
        Quick citation verification for inline Bubble Menu.
        Returns status and any found citations with their validity.
        """
        if not self.client:
            return {"status": "unknown", "message": "Cliente de auditoria não configurado."}
        
        # Regex patterns for common legal citations
        citation_patterns = [
            r"S[úu]mula\s*(?:Vinculante\s*)?n?[º°.]?\s*(\d+)",
            r"REsp\s*(?:n[º°.]?\s*)?[\d.]+(?:/[A-Z]{2})?",
            r"RE\s*(?:n[º°.]?\s*)?[\d.]+(?:/[A-Z]{2})?",
            r"HC\s*(?:n[º°.]?\s*)?[\d.]+(?:/[A-Z]{2})?",
            r"ADI\s*(?:n[º°.]?\s*)?[\d.]+",
            r"ADPF\s*(?:n[º°.]?\s*)?[\d.]+",
            r"Art(?:igo)?\.?\s*\d+[,\s]*(?:§§?\s*\d+)?.*?(?:C(?:ódigo\s*)?(?:C|P|T|PC)|Lei\s*n?[º°.]?\s*[\d.]+)",
        ]
        
        import re
        found_citations = []
        for pattern in citation_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            found_citations.extend(matches)
        
        if not found_citations:
            # No citations found, do a quick AI check
            prompt = f"""Analise brevemente o trecho abaixo e verifique se há citações jurídicas.
Se houver, liste-as e indique se parecem corretas ou suspeitas.
Responda em JSON: {{"status": "valid|suspicious|not_found", "message": "...", "citations": [...]}}

Trecho: "{text[:500]}"
"""
            try:
                from google.genai import types
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.1,
                        max_output_tokens=500
                    )
                )
                
                text = extract_genai_text(response)
                if text:
                    # Try to parse JSON from response
                    import json
                    try:
                        # Extract JSON from response
                        json_match = re.search(r'\{.*\}', text, re.DOTALL)
                        if json_match:
                            return json.loads(json_match.group())
                    except json.JSONDecodeError:
                        pass
                    
                    # Fallback: return raw analysis
                    return {
                        "status": "analyzed",
                        "message": text[:300],
                        "citations": []
                    }
            except Exception as e:
                logger.error(f"Erro na verificação rápida: {e}")
                return {"status": "error", "message": str(e), "citations": []}
        
        # Found citations via regex, return for AI verification
        return {
            "status": "found",
            "message": f"Encontradas {len(found_citations)} citações. Verificação manual recomendada.",
            "citations": found_citations[:10],  # Limit to 10
            "suggestions": ["Verifique a numeração das súmulas", "Confirme a existência dos julgados"]
        }

    # ... Helper methods reused from audit_juridico.py ...
    # Simplified here for brevity, assuming RAG is optional
    
    async def auditar_peca(
        self, 
        texto_completo: str, 
        output_folder: str, 
        filename_base: str,
        rag_manager=None
    ) -> Dict[str, str]:
        """
        Executa auditoria e salva relatórios (.md e .docx)
        Returns: Dict com paths dos arquivos gerados
        """
        logger.info("⚖️ Iniciando Auditoria Jurídica (API Service)...")
        data_atual = datetime.now().strftime("%d/%m/%Y")
        
        # 1. Check Hallucinations (if RAG available)
        rag_report = ""
        # TODO: Implement RAG integration from shared module if available
        
        # 2. Generate Audit Report
        if not self.client:
            return {"error": "Client Gemini not configured"}
            
        prompt = PROMPT_AUDITORIA_JURIDICA.format(texto=texto_completo, data_atual=data_atual)
        
        from google.genai import types
        try:
             # Sync call in thread or assum async wrapper availability?
             # For simplicity, using simple sync call here, but in prod should be async wrapper.
             # Assuming orchestrator runs in threadpool or fast enough.
             
             response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=8192
                )
             )
             
             relatorio = extract_genai_text(response)
             if not relatorio:
                 return {"error": "Empty response from Audit Model"}
                 
             full_content = f"<!-- Auditoria: {data_atual} -->\n\n{relatorio}"
             if rag_report:
                 full_content += rag_report
                 
             # 3. Save Markdown
             md_filename = f"{filename_base}_AUDIT.md"
             md_path = os.path.join(output_folder, md_filename)
             with open(md_path, 'w', encoding='utf-8') as f:
                 f.write(full_content)
                 
             # 4. Save DOCX
             docx_filename = f"{filename_base}_AUDIT.docx"
             docx_path = save_as_word_juridico(full_content, docx_filename, output_folder, modo="AUDITORIA")
             
             return {
                 "markdown_path": md_path,
                 "docx_path": docx_path,
                 "content": full_content
             }
             
        except Exception as e:
            logger.error(f"❌ Erro na auditoria: {e}")
            raise e

    async def verify_citation(self, citation: str, provider: str = "gemini") -> Dict:
        """
        Wraps verify_citation_online from audit_juridico.
        """
        try:
             # Try importing from module if available
             from audit_juridico import verify_citation_online
             return verify_citation_online(
                 citation=citation, 
                 provider=provider, 
                 client=self.client, 
                 model_name=self.model_name
             )
        except ImportError:
            return {"error": "audit_juridico module not available"}
        except Exception as e:
            logger.error(f"Error checking citation: {e}")
            return {"error": str(e)}

audit_service = AuditService()
