"""
Quality Service - Apostila Validation and Correction Service

Wraps CLI scripts (auto_fix_apostilas.py, mlx_vomo.py) into a service layer
for use by the API.
"""

import os
import sys
import json
import hashlib
import re
import tempfile
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from enum import Enum
from loguru import logger

# Add CLI scripts to path (they are at the project root)
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class FixType(str, Enum):
    STRUCTURAL = "structural"
    SEMANTIC = "semantic"


class QualityService:
    """
    Service for document quality validation and automated corrections.
    """

    def __init__(self):
        self._vomo = None  # Lazy-loaded
        self._auto_fix_module = None

    def _get_vomo(self):
        """Lazy load VomoMLX to avoid slow startup."""
        if self._vomo is None:
            try:
                from mlx_vomo import VomoMLX
                self._vomo = VomoMLX()
            except Exception as e:
                logger.error(f"Failed to initialize VomoMLX: {e}")
                raise RuntimeError(f"MLX initialization failed: {e}")
        return self._vomo

    def _get_auto_fix(self):
        """Lazy load auto_fix_apostilas functions."""
        if self._auto_fix_module is None:
            try:
                import auto_fix_apostilas
                self._auto_fix_module = auto_fix_apostilas
            except Exception as e:
                logger.error(f"Failed to import auto_fix_apostilas: {e}")
                raise RuntimeError(f"Auto-fix module import failed: {e}")
        return self._auto_fix_module

    async def validate_document(
        self,
        raw_content: str,
        formatted_content: str,
        document_name: str
    ) -> Dict[str, Any]:
        """
        Validates a formatted document against its raw source.
        Returns validation report with score, omissions, and issues.
        """
        logger.info(f"🔍 Starting validation for: {document_name}")

        try:
            vomo = self._get_vomo()
            
            # Run validation in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: vomo.validate_completeness_full(
                    raw_content,
                    formatted_content,
                    document_name
                )
            )

            # Normalize keys
            report = {
                "document_name": document_name,
                "validated_at": datetime.now().isoformat(),
                "approved": result.get("aprovado", True),
                "score": result.get("nota_fidelidade", result.get("nota", 0)),
                "omissions": result.get("omissoes_graves", result.get("omissoes", [])),
                "distortions": result.get("distorcoes", []),
                "structural_issues": result.get("problemas_estrutura", []),
                "observations": result.get("observacoes", ""),
            }

            logger.info(f"✅ Validation complete: {document_name} - Score: {report['score']}/10")
            return report

        except Exception as e:
            logger.error(f"❌ Validation failed for {document_name}: {e}")
            return {
                "document_name": document_name,
                "validated_at": datetime.now().isoformat(),
                "approved": False,
                "score": 0,
                "error": str(e),
                "omissions": [],
                "distortions": [],
                "structural_issues": [],
            }

    async def analyze_structural_issues(self, content: str, document_name: str, raw_content: str = None) -> Dict[str, Any]:
        """
        Analyzes content for structural AND content issues WITHOUT applying fixes (HIL Mode).
        Returns list of pending fixes for user approval plus content validation alerts.
        """
        logger.info(f"🔍 Analyzing structural + content issues for: {document_name}")

        try:
            auto_fix = self._get_auto_fix()
            
            # Save content to temp file for analysis (auto_fix works with files)
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
                f.write(content)
                temp_path = f.name
            
            raw_temp_path = None
            if raw_content:
                with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
                    f.write(raw_content)
                    raw_temp_path = f.name
            
            try:
                # Use the updated analyze_structural_issues which includes content validation
                issues = auto_fix.analyze_structural_issues(temp_path, raw_temp_path)
                
                # Convert to HIL format with pending_fixes
                pending_fixes = []
                
                for dup in issues.get('duplicate_sections', []):
                    pending_fixes.append({
                        'id': f"dup_section_{len(pending_fixes)}",
                        'type': 'duplicate_section',
                        'description': f"Seção duplicada: '{dup.get('title', '')}' similar a '{dup.get('similar_to', '')}'",
                        'action': 'MERGE',
                        'severity': 'medium'
                    })
                
                for dup in issues.get('duplicate_paragraphs', []):
                    pending_fixes.append({
                        'id': f"dup_para_{dup.get('fingerprint', '')}",
                        'type': 'duplicate_paragraph',
                        'description': f"Parágrafo duplicado: '{dup.get('preview', '')[:60]}...'",
                        'action': 'REMOVE',
                        'severity': 'low',
                        'fingerprint': dup.get('fingerprint')
                    })

                if issues.get('heading_numbering_issues'):
                    pending_fixes.append({
                        'id': 'heading_numbering',
                        'type': 'heading_numbering',
                        'description': issues['heading_numbering_issues'][0].get(
                            'description',
                            "Numeração de títulos H2 fora de sequência ou ausente."
                        ),
                        'action': 'RENUMBER',
                        'severity': 'low'
                    })
                
                return {
                    "document_name": document_name,
                    "analyzed_at": datetime.now().isoformat(),
                    "total_issues": len(pending_fixes),
                    "pending_fixes": pending_fixes,
                    "requires_approval": len(pending_fixes) > 0,
                    # v4.0 Content Validation Fields
                    "compression_ratio": issues.get('compression_ratio'),
                    "compression_warning": issues.get('compression_warning'),
                    "missing_laws": issues.get('missing_laws', []),
                    "missing_sumulas": issues.get('missing_sumulas', []),
                    "missing_decretos": issues.get('missing_decretos', []),
                    "missing_julgados": issues.get('missing_julgados', []),
                    "total_content_issues": issues.get('total_content_issues', 0)
                }
            finally:
                # Cleanup temp files
                import os
                os.unlink(temp_path)
                if raw_temp_path:
                    os.unlink(raw_temp_path)

        except Exception as e:
            logger.error(f"❌ Analysis failed: {e}")
            return {
                "document_name": document_name,
                "error": str(e),
                "pending_fixes": [],
                "requires_approval": False
            }

    async def apply_approved_fixes(
        self,
        content: str,
        approved_fix_ids: List[str]
    ) -> Dict[str, Any]:
        """
        Applies only the user-approved fixes to the content.
        Returns the modified content.
        """
        logger.info(f"✅ Applying {len(approved_fix_ids)} approved fixes...")

        try:
            fixed_content = content
            applied = []
            
            # Re-analyze to get fix details
            paragraphs = content.split('\n\n')
            
            # Remove approved duplicate paragraphs
            import hashlib
            seen_fps = set()
            new_paragraphs = []
            
            for para in paragraphs:
                if len(para.strip()) < 50:
                    new_paragraphs.append(para)
                    continue
                    
                fp = hashlib.md5(para.lower().strip().encode()).hexdigest()[:12]
                fix_id = f"dup_para_{fp}"
                
                if fix_id in approved_fix_ids and fp in seen_fps:
                    applied.append(f"Removed duplicate paragraph (fp: {fp})")
                    continue
                    
                new_paragraphs.append(para)
                seen_fps.add(fp)
            
            fixed_content = '\n\n'.join(new_paragraphs)

            if "heading_numbering" in approved_fix_ids:
                def _renumber_h2_headings(text: str) -> str:
                    lines = text.splitlines()
                    counter = 0
                    for idx, line in enumerate(lines):
                        match = re.match(r'^(##)\s+(?:(\d+)\.?\s+)?(.+)$', line.strip())
                        if match:
                            counter += 1
                            title = match.group(3).strip()
                            lines[idx] = f"## {counter}. {title}"
                    return "\n".join(lines)

                renumbered = _renumber_h2_headings(fixed_content)
                if renumbered != fixed_content:
                    fixed_content = renumbered
                    applied.append("Renumbered H2 headings")
            
            return {
                "success": True,
                "fixed_content": fixed_content,
                "original_size": len(content),
                "fixed_size": len(fixed_content),
                "size_reduction": f"{100 * (1 - len(fixed_content) / len(content)):.1f}%",
                "fixes_applied": applied,
            }

        except Exception as e:
            logger.error(f"❌ Apply fixes failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "fixed_content": content,
                "fixes_applied": [],
            }

    async def apply_structural_fix(self, content: str) -> Dict[str, Any]:
        """
        Applies fixes using auto_fix logic (requires saving to temp file first).
        """
        auto_fix = self._get_auto_fix()
        if not auto_fix:
             return {"error": "module unavailable"}
             
        import tempfile
        import os # Import os for os.unlink
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.md', delete=False, encoding='utf-8') as tmp: # Added encoding
            tmp.write(content)
            tmp_path = tmp.name
            
        try:
            # 1. Analyze
            suggestions = await asyncio.to_thread(auto_fix.analyze_structural_issues, tmp_path)
            
            # 2. Apply
            if suggestions.get('total_issues', 0) > 0:
                result = await asyncio.to_thread(
                    auto_fix.apply_structural_fixes_to_file, 
                    tmp_path, 
                    suggestions
                )
                
                # Read back
                with open(tmp_path, 'r', encoding='utf-8') as f: # Added encoding
                    new_content = f.read()
                    
                return {
                    "content": new_content, 
                    "fixes": result.get('fixes_applied', []),
                    "stats": result
                }
            return {"content": content, "fixes": [], "stats": {}}
            
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    async def apply_structural_fixes_from_issues(
        self,
        content: str,
        approved_issues: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Applies approved structural fixes using auto_fix_apostilas.apply_structural_fixes_to_file.
        """
        auto_fix = self._get_auto_fix()
        if not auto_fix:
            return {"content": content, "fixes": [], "stats": {}, "error": "module unavailable"}

        duplicate_paragraphs = []
        duplicate_sections = []
        renumber_headings = False
        for issue in approved_issues:
            if issue.get("type") == "duplicate_paragraph" and issue.get("fingerprint"):
                duplicate_paragraphs.append({
                    "fingerprint": issue.get("fingerprint"),
                    "action": "REMOVE_RECOMMENDED",
                })
            if issue.get("type") == "duplicate_section" and issue.get("title"):
                duplicate_sections.append({
                    "title": issue.get("title"),
                    "action": "MERGE_RECOMMENDED",
                })
            if issue.get("type") == "heading_numbering":
                renumber_headings = True

        suggestions = {
            "duplicate_paragraphs": duplicate_paragraphs,
            "duplicate_sections": duplicate_sections,
        }
        if renumber_headings:
            suggestions["renumber_headings"] = True

        import tempfile
        import os
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".md", delete=False, encoding="utf-8") as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            result = await asyncio.to_thread(auto_fix.apply_structural_fixes_to_file, tmp_path, suggestions)
            with open(tmp_path, "r", encoding="utf-8") as f:
                new_content = f.read()
            return {
                "content": new_content,
                "fixes": result.get("fixes_applied", []),
                "stats": result,
            }
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
                
    async def validate_document_hil(self, content: str, filename: str) -> Dict[str, Any]:
        """
        DEPRECATED: Use analyze_structural_issues + apply_approved_fixes instead.
        This method now just analyzes and returns suggestions.
        """
        analysis = await self.analyze_structural_issues(content, "document")
        return {
            "success": False,
            "message": "Auto-apply disabled. Use HIL flow instead.",
            "pending_fixes": analysis.get("pending_fixes", []),
            "requires_approval": True,
            "fixed_content": content,
            "fixes_applied": [],
        }

    async def validate_document_full(
        self,
        raw_content: str,
        formatted_content: str,
        document_name: str
    ) -> Dict[str, Any]:
        """
        Full fidelity validation using VomoMLX.validate_completeness_full.
        """
        logger.info(f"🔍 Full validation (CLI parity) for: {document_name}")
        try:
            vomo = self._get_vomo()
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: vomo.validate_completeness_full(
                    raw_content,
                    formatted_content,
                    document_name
                )
            )
            return {
                "document_name": document_name,
                "validated_at": datetime.now().isoformat(),
                "approved": result.get("aprovado", True),
                "score": result.get("nota_fidelidade", result.get("nota", 0)),
                "omissions": result.get("omissoes_graves", result.get("omissoes", [])),
                "distortions": result.get("distorcoes", []),
                "structural_issues": result.get("problemas_estrutura", []),
                "observations": result.get("observacoes", ""),
            }
        except Exception as e:
            logger.error(f"❌ Full validation failed for {document_name}: {e}")
            return {
                "document_name": document_name,
                "validated_at": datetime.now().isoformat(),
                "approved": False,
                "score": 0,
                "error": str(e),
                "omissions": [],
                "distortions": [],
                "structural_issues": [],
                "observations": "",
            }

    async def generate_semantic_suggestions(
        self,
        document_name: str,
        issues: List[str]
    ) -> Dict[str, Any]:
        """
        Generates AI-powered suggestions to fix content issues.
        Returns markdown-formatted patch suggestions.
        """
        if not issues:
            return {"suggestions": "", "has_suggestions": False}

        logger.info(f"✨ Generating semantic suggestions for {document_name}...")

        try:
            vomo = self._get_vomo()
            
            omissions_text = "\n".join([f"- {o}" for o in issues])

            prompt = f"""
            VOCÊ É UM ASSISTENTE JURÍDICO DE ELITE.
            
            **Contexto:**
            Revisando apostila de Direito ({document_name}) gerada por IA.
            Problemas detectados:
            
            {omissions_text}
            
            **Tarefa:**
            Gere um "TEXTO DE CORREÇÃO" (Patch) para suprir as lacunas.
            
            **Diretrizes:**
            1. Seja direto. Forneça o parágrafo exato a adicionar/modificar.
            2. Use linguagem formal jurídica.
            3. Se houver dúvida sobre dados, coloque: "[VERIFICAR NO ÁUDIO]".
            4. Indique ONDE inserir (ex: "Após Tópico X").
            
            **Saída:**
            Apenas o markdown do patch.
            """

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: vomo.client.models.generate_content(
                    model=vomo.llm_model,
                    contents=prompt
                )
            )

            suggestion = response.text

            return {
                "document_name": document_name,
                "issues_addressed": issues,
                "suggestions": suggestion,
                "has_suggestions": True,
                "generated_at": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"❌ Suggestion generation failed: {e}")
            return {
                "document_name": document_name,
                "error": str(e),
                "suggestions": "",
                "has_suggestions": False,
            }

    async def regenerate_word_document(
        self,
        content: str,
        document_name: str,
        output_dir: str
    ) -> Dict[str, Any]:
        """
        Regenerates a Word document from markdown content.
        """
        logger.info(f"📄 Regenerating Word document: {document_name}")

        try:
            vomo = self._get_vomo()

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: vomo.save_as_word(content, document_name, output_dir)
            )

            output_path = os.path.join(output_dir, f"{document_name}.docx")

            return {
                "success": True,
                "output_path": output_path,
                "document_name": document_name,
            }

        except Exception as e:
            logger.error(f"❌ Word generation failed: {e}")
            return {
                "success": False,
                "error": str(e),
            }


# Singleton instance
quality_service = QualityService()
