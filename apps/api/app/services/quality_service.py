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
from app.services.api_call_tracker import record_api_call
from app.services.false_positive_prevention import (
    FalsePositivePrevention,
    ValidationThresholds,
    false_positive_prevention,
)

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
            except SystemExit as e:
                logger.error(f"Failed to initialize VomoMLX (SystemExit): {e}")
                raise RuntimeError(f"MLX initialization failed: {e}") from e
            except Exception as e:
                logger.error(f"Failed to initialize VomoMLX: {e}")
                raise RuntimeError(f"MLX initialization failed: {e}") from e
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
        document_name: str,
        mode: str = "APOSTILA",
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
                lambda: vomo.validate_fidelity_primary(
                    raw_content,
                    formatted_content,
                    document_name,
                    modo=mode,
                    include_sources=False,
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
                raw_issues = auto_fix.analyze_structural_issues(temp_path, raw_temp_path)

                # Convert to HIL format with pending_fixes
                pending_fixes = []

                for idx, dup in enumerate(raw_issues.get('duplicate_sections', [])):
                    pending_fixes.append({
                        'id': f"dup_section_{idx}",
                        'type': 'duplicate_section',
                        'title': dup.get('title', ''),
                        'description': f"Seção duplicada: '{dup.get('title', '')}' similar a '{dup.get('similar_to', '')}'",
                        'action': 'MERGE',
                        'severity': 'medium'
                    })
                
                for dup in raw_issues.get('duplicate_paragraphs', []):
                    pending_fixes.append({
                        'id': f"dup_para_{dup.get('fingerprint', '')}",
                        'type': 'duplicate_paragraph',
                        'description': f"Parágrafo duplicado: '{dup.get('preview', '')[:60]}...'",
                        'action': 'REMOVE',
                        'severity': 'low',
                        'fingerprint': dup.get('fingerprint')
                    })

                if raw_issues.get('heading_numbering_issues'):
                    pending_fixes.append({
                        'id': 'heading_numbering',
                        'type': 'heading_numbering',
                        'description': raw_issues['heading_numbering_issues'][0].get(
                            'description',
                            "Numeração de títulos H2 fora de sequência ou ausente."
                        ),
                        'action': 'RENUMBER',
                        'severity': 'low'
                    })

                return {
                    "document_name": document_name,
                    "analyzed_at": datetime.now().isoformat(),
                    "total_issues": raw_issues.get("total_issues", len(pending_fixes)),
                    "pending_fixes": pending_fixes,
                    "requires_approval": len(pending_fixes) > 0,
                    # Raw issues (CLI parity)
                    "duplicate_sections": raw_issues.get("duplicate_sections", []),
                    "duplicate_paragraphs": raw_issues.get("duplicate_paragraphs", []),
                    "heading_numbering_issues": raw_issues.get("heading_numbering_issues", []),
                    # v4.0 Content Validation Fields
                    "compression_ratio": raw_issues.get('compression_ratio'),
                    "compression_warning": raw_issues.get('compression_warning'),
                    "missing_laws": raw_issues.get('missing_laws', []),
                    "missing_sumulas": raw_issues.get('missing_sumulas', []),
                    "missing_decretos": raw_issues.get('missing_decretos', []),
                    "missing_julgados": raw_issues.get('missing_julgados', []),
                    "total_content_issues": raw_issues.get('total_content_issues', 0),
                    "cli_issues": raw_issues,
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
        approved_fix_ids: List[str],
        approved_fixes: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Applies only the user-approved fixes to the content.
        Uses the same structural fix engine as mlx_vomo (auto_fix_apostilas).
        """
        logger.info(f"✅ Applying {len(approved_fix_ids)} approved fixes...")

        try:
            auto_fix = self._get_auto_fix()
            if not auto_fix:
                return {
                    "success": False,
                    "error": "module unavailable",
                    "fixed_content": content,
                    "fixes_applied": [],
                }

            import tempfile
            import os

            with tempfile.NamedTemporaryFile(mode="w+", suffix=".md", delete=False, encoding="utf-8") as tmp:
                tmp.write(content)
                tmp_path = tmp.name

            try:
                issues = await asyncio.to_thread(auto_fix.analyze_structural_issues, tmp_path)
                logger.info(
                    "🔍 Re-analyzed issues from temp file: "
                    f"duplicate_paragraphs={len(issues.get('duplicate_paragraphs', []))}, "
                    f"duplicate_sections={len(issues.get('duplicate_sections', []))}"
                )

                suggestions: Dict[str, Any] = {
                    "duplicate_paragraphs": [],
                    "duplicate_sections": [],
                }

                if approved_fixes:
                    logger.info(f"🔧 Processing {len(approved_fixes)} approved_fixes objects...")
                    for issue in approved_fixes:
                        issue_type = (issue.get("type") or "").lower()
                        if issue_type == "duplicate_section":
                            title = issue.get("title") or ""
                            if title:
                                suggestions["duplicate_sections"].append({"title": title})
                        elif issue_type == "duplicate_paragraph":
                            fingerprint = issue.get("fingerprint") or ""
                            if fingerprint:
                                suggestions["duplicate_paragraphs"].append({"fingerprint": fingerprint})
                        elif issue_type == "heading_numbering":
                            suggestions["renumber_headings"] = True

                logger.info(
                    "📊 Suggestions after approved_fixes processing: "
                    f"paragraphs={len(suggestions['duplicate_paragraphs'])}, "
                    f"sections={len(suggestions['duplicate_sections'])}, "
                    f"renumber={suggestions.get('renumber_headings')}"
                )

                if not (
                    suggestions["duplicate_paragraphs"]
                    or suggestions["duplicate_sections"]
                    or suggestions.get("renumber_headings")
                ):
                    logger.info("🔄 Falling back to approved_fix_ids matching...")
                    for idx, dup in enumerate(issues.get("duplicate_sections", [])):
                        fix_id = f"dup_section_{idx}"
                        if fix_id in approved_fix_ids:
                            suggestions["duplicate_sections"].append(dup)

                    for dup in issues.get("duplicate_paragraphs", []):
                        fp = dup.get("fingerprint") or ""
                        fix_id = f"dup_para_{fp}"
                        if fix_id in approved_fix_ids:
                            suggestions["duplicate_paragraphs"].append(dup)

                    if "heading_numbering" in approved_fix_ids and issues.get("heading_numbering_issues"):
                        suggestions["renumber_headings"] = True

                logger.info(
                    "📊 Final suggestions: "
                    f"paragraphs={len(suggestions['duplicate_paragraphs'])}, "
                    f"sections={len(suggestions['duplicate_sections'])}, "
                    f"renumber={suggestions.get('renumber_headings')}"
                )

                if not (
                    suggestions["duplicate_paragraphs"]
                    or suggestions["duplicate_sections"]
                    or suggestions.get("renumber_headings")
                ):
                    logger.warning("⚠️ No suggestions to apply - returning unchanged content")
                    return {
                        "success": True,
                        "fixed_content": content,
                        "original_size": len(content),
                        "fixed_size": len(content),
                        "size_reduction": "0.0%",
                        "fixes_applied": [],
                    }

                result = await asyncio.to_thread(
                    auto_fix.apply_structural_fixes_to_file, tmp_path, suggestions
                )
                logger.info(f"🧩 Fixes applied: {result.get('fixes_applied', [])}")
                
                clean_fixes = result.get('fixes_applied')
                if clean_fixes:
                    with open(tmp_path, "r", encoding="utf-8") as f:
                        fixed_content = f.read()
                else:
                    fixed_content = content

                # CRITICAL: Never return empty content - fallback to original
                if not fixed_content or not fixed_content.strip():
                    logger.warning("⚠️ apply_approved_fixes: resultado vazio, retornando original")
                    return {
                        "success": True,
                        "fixed_content": content,
                        "original_size": len(content),
                        "fixed_size": len(content),
                        "size_reduction": "0.0%",
                        "fixes_applied": [],
                        "warning": "Resultado vazio - original preservado"
                    }

                return {
                    "success": True,
                    "fixed_content": fixed_content,
                    "original_size": len(content),
                    "fixed_size": len(fixed_content),
                    "size_reduction": f"{100 * (1 - len(fixed_content) / len(content)):.1f}%",
                    "fixes_applied": result.get("fixes_applied", []),
                }
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)

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
            
            clean_fixes = result.get('fixes_applied')
            if clean_fixes:
                with open(tmp_path, "r", encoding="utf-8") as f:
                    new_content = f.read()
            else:
                new_content = content
            
            # CRITICAL: Never return empty content - fallback to original
            if not new_content or not new_content.strip():
                logger.warning("apply_structural_fixes_from_issues: resultado vazio, retornando original")
                return {
                    "content": content,
                    "fixes": [],
                    "stats": result,
                    "error": "Resultado vazio - original preservado"
                }
            
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
        document_name: str,
        mode: str = "APOSTILA",
    ) -> Dict[str, Any]:
        """
        Full fidelity validation using the primary fidelity audit.
        """
        logger.info(f"🔍 Full validation (CLI parity) for: {document_name}")
        try:
            vomo = self._get_vomo()
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: vomo.validate_fidelity_primary(
                    raw_content,
                    formatted_content,
                    document_name,
                    modo=mode,
                    include_sources=False,
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

    async def find_cross_file_duplicates(self, file_paths: List[str]) -> Dict[str, Any]:
        """
        Analyzes multiple files for cross-reference duplicates using fingerprinting.
        Wraps auto_fix_apostilas.find_cross_file_duplicates.
        """
        logger.info(f"🔍 Starting cross-file analysis for {len(file_paths)} files")
        
        try:
            auto_fix = self._get_auto_fix()
            
            # Run in thread pool as it performs IO and heavy computation
            loop = asyncio.get_event_loop()
            
            def _analyze():
                index = auto_fix.build_global_fingerprint_index(file_paths)
                duplicates = auto_fix.find_cross_file_duplicates(index)
                return duplicates
                
            duplicates = await loop.run_in_executor(None, _analyze)
            
            return {
                "analyzed_files": len(file_paths),
                "total_duplicates": len(duplicates),
                "duplicates": duplicates
            }
            
        except Exception as e:
            logger.error(f"❌ Cross-file analysis failed: {e}")
            return {
                "analyzed_files": len(file_paths),
                "total_duplicates": 0,
                "duplicates": [],
                "error": str(e)
            }


    async def fix_content_issues_with_llm(
        self,
        content: str,
        raw_content: str,
        issues: List[Dict[str, Any]],
        model_selection: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Fix content issues (missing laws, omissions) using LLM.
        
        Uses direct Gemini or OpenAI API calls instead of VomoMLX
        to avoid complex initialization issues.
        
        Args:
            content: Current formatted content
            raw_content: Original raw transcription
            issues: List of content issues to fix
            model_selection: Model to use (gemini-* or gpt-*)
        
        Returns:
            Dict with fixed_content and applied fixes
        """
        if not issues:
            return {"content": content, "fixes": [], "error": None}

        def _is_legal_audit(issue: Dict[str, Any]) -> bool:
            return issue.get("source") == "legal_audit" or issue.get("type") == "legal_audit"

        legal_issues = [issue for issue in issues if _is_legal_audit(issue)]
        other_issues = [issue for issue in issues if not _is_legal_audit(issue)]

        if other_issues and not raw_content:
            return {"content": content, "fixes": [], "error": "raw_content nao fornecido para correcoes de conteudo"}

        def _get_issue_section(issue: Dict[str, Any]) -> Optional[str]:
            value = issue.get("suggested_section")
            if isinstance(value, str) and value.strip():
                return value.strip()
            hint = issue.get("location_hint")
            if isinstance(hint, dict):
                title = hint.get("section_title")
                if isinstance(title, str) and title.strip():
                    return title.strip()
            return None

        def _get_issue_reference(issue: Dict[str, Any]) -> Optional[str]:
            value = issue.get("reference")
            if isinstance(value, str) and value.strip():
                return value.strip()
            return None

        def _infer_issue_reference(issue: Dict[str, Any]) -> Optional[str]:
            desc = issue.get("description")
            if not isinstance(desc, str) or not desc.strip():
                return None
            if ":" in desc:
                candidate = desc.split(":", 1)[1].strip()
                return candidate or None
            return None

        def _digits_only(value: str) -> str:
            return re.sub(r"\D+", "", value or "")

        def _build_fuzzy_digits_pattern(digits: str) -> str:
            sep = r"[\s\./-]*"
            return sep.join(list(digits))

        def _extract_snippets(pattern: str, max_hits: int = 2, window: int = 260) -> List[str]:
            if not raw_content or not pattern:
                return []
            snippets: List[str] = []
            try:
                for match in re.finditer(pattern, raw_content, flags=re.IGNORECASE):
                    start, end = match.span()
                    snippet_start = max(0, start - window)
                    snippet_end = min(len(raw_content), end + window)
                    snippet = raw_content[snippet_start:snippet_end].strip()
                    if snippet:
                        snippets.append(snippet)
                    if len(snippets) >= max_hits:
                        break
            except re.error:
                return []
            return snippets

        def _get_issue_evidence_snippets(issue: Dict[str, Any], max_snippets: int = 2) -> List[str]:
            evidence = issue.get("raw_evidence") or issue.get("evidence") or []
            snippets: List[str] = []
            if isinstance(evidence, list):
                for item in evidence:
                    snippet = None
                    if isinstance(item, dict):
                        snippet = item.get("snippet") or item.get("text")
                    elif isinstance(item, str):
                        snippet = item
                    if isinstance(snippet, str):
                        cleaned = snippet.strip()
                        if cleaned:
                            snippets.append(cleaned)
                    if len(snippets) >= max_snippets:
                        break
            if snippets:
                return snippets

            # Best-effort fallback: derive evidence from raw_content for known issue types.
            if not raw_content:
                return []

            issue_type = issue.get("type")
            reference = _get_issue_reference(issue) or _infer_issue_reference(issue) or ""

            if issue_type in {"missing_law", "missing_decreto"}:
                digits = _digits_only(reference)
                if not digits:
                    digits = _digits_only(str(issue.get("description") or ""))
                if not digits:
                    return []
                keyword = "lei" if issue_type == "missing_law" else "decreto"
                pattern = rf"\b{keyword}\s*(?:rio\s*)?(?:n[º°]?\s*)?{_build_fuzzy_digits_pattern(digits)}"
                return _extract_snippets(pattern, max_hits=max_snippets)

            if issue_type == "missing_sumula":
                num = _digits_only(reference)
                if not num:
                    num = _digits_only(str(issue.get("description") or ""))
                if not num:
                    return []
                pattern = rf"\b[Ss](?:ú|u)mula\s*(?:vinculante\s*)?(?:n[º°]?\s*)?{re.escape(num)}\b"
                return _extract_snippets(pattern, max_hits=max_snippets)

            if issue_type == "missing_julgado":
                if not reference:
                    reference = str(issue.get("description") or "")
                if not reference:
                    return []
                escaped = re.escape(reference)
                pattern = re.sub(r"\\\s+", r"\\s+", escaped)
                return _extract_snippets(pattern, max_hits=max_snippets)

            return []

        def _build_raw_context(target_issues: List[Dict[str, Any]]) -> str:
            chunks: List[str] = []
            for issue in target_issues:
                chunks.extend(_get_issue_evidence_snippets(issue, max_snippets=2))
            # De-duplicate while preserving order
            seen = set()
            unique: List[str] = []
            for chunk in chunks:
                key = chunk[:240]
                if key in seen:
                    continue
                seen.add(key)
                unique.append(chunk)
            if unique:
                return "\n\n---\n\n".join(unique)[:80000]
            return (raw_content or "")[:50000]

        def _build_issues_description(target_issues: List[Dict[str, Any]]) -> str:
            blocks: List[str] = []
            for issue in target_issues:
                desc = issue.get("description")
                if not isinstance(desc, str) or not desc.strip():
                    continue
                issue_id = issue.get("id")
                header = f"- [{issue_id}] {desc.strip()}" if issue_id else f"- {desc.strip()}"
                extra_lines: List[str] = []
                reference = _get_issue_reference(issue)
                if reference:
                    extra_lines.append(f"  Referência: {reference}")
                section = _get_issue_section(issue)
                if section:
                    extra_lines.append(f"  Seção sugerida: {section}")
                user_instruction = issue.get("user_instruction") or issue.get("instruction")
                if isinstance(user_instruction, str) and user_instruction.strip():
                    extra_lines.append(f"  Instrução do usuário: {user_instruction.strip()[:800]}")
                formatted_context = issue.get("formatted_context")
                if isinstance(formatted_context, str) and formatted_context.strip():
                    snippet = formatted_context.strip()
                    snippet = (snippet[:3500] + "…") if len(snippet) > 3500 else snippet
                    extra_lines.append("  Contexto do texto (formato atual):")
                    extra_lines.append("  ```")
                    extra_lines.append(snippet)
                    extra_lines.append("  ```")
                evidence_snippets = _get_issue_evidence_snippets(issue, max_snippets=1)
                if evidence_snippets:
                    snippet = evidence_snippets[0]
                    snippet = (snippet[:2000] + "…") if len(snippet) > 2000 else snippet
                    extra_lines.append("  Evidência RAW:")
                    extra_lines.append("  ```")
                    extra_lines.append(snippet)
                    extra_lines.append("  ```")
                if extra_lines:
                    blocks.append(header + "\n" + "\n".join(extra_lines))
                else:
                    blocks.append(header)
            return "\n".join(blocks)

        def _build_content_snapshot(value: str) -> str:
            if not value:
                return ""
            max_chars = int(os.getenv("IUDEX_HIL_PROMPT_DOC_CHARS", "160000"))
            head_ratio = float(os.getenv("IUDEX_HIL_PROMPT_HEAD_RATIO", "0.65"))
            head_ratio = min(max(head_ratio, 0.2), 0.8)
            if len(value) <= max_chars:
                return value
            head_len = int(max_chars * head_ratio)
            tail_len = max_chars - head_len
            head = value[:head_len]
            tail = value[-tail_len:] if tail_len > 0 else ""
            return f"{head}\n\n[... documento truncado: inicio + final ...]\n\n{tail}"

        def _normalize_table_text(text: str) -> str:
            return re.sub(r"\s+", " ", (text or "").strip()).lower()

        def _looks_like_table_row(line: str) -> bool:
            if not line or "|" not in line:
                return False
            cells = [cell.strip() for cell in line.split("|")]
            non_empty = [cell for cell in cells if cell]
            return len(non_empty) >= 2

        def _looks_like_table_separator(line: str) -> bool:
            if not line:
                return False
            pattern = r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*$"
            return re.match(pattern, line.strip()) is not None

        def _extract_markdown_tables(text: str) -> List[Dict[str, Any]]:
            tables: List[Dict[str, Any]] = []
            if not text:
                return tables
            lines = text.splitlines()
            i = 0
            while i < len(lines) - 1:
                if _looks_like_table_row(lines[i]) and _looks_like_table_separator(lines[i + 1]):
                    start = i
                    i += 2
                    while i < len(lines) and _looks_like_table_row(lines[i]):
                        i += 1
                    end = i
                    tables.append({
                        "type": "markdown",
                        "start": start,
                        "end": end,
                        "text": "\n".join(lines[start:end]),
                    })
                    continue
                i += 1
            return tables

        def _extract_html_tables(text: str) -> List[Dict[str, Any]]:
            tables: List[Dict[str, Any]] = []
            if not text:
                return tables
            pattern = re.compile(r"<table\\b[\\s\\S]*?</table>", re.IGNORECASE)
            for match in pattern.finditer(text):
                table_text = match.group(0)
                start_line = text[:match.start()].count("\n")
                end_line = text[:match.end()].count("\n") + 1
                tables.append({
                    "type": "html",
                    "start": start_line,
                    "end": end_line,
                    "text": table_text,
                })
            return tables

        def _attach_table_anchors(tables: List[Dict[str, Any]], lines: List[str]) -> None:
            for table in tables:
                start = max(0, int(table.get("start", 0)))
                end = max(0, int(table.get("end", 0)))
                prev_anchor = None
                next_anchor = None
                for idx in range(start - 1, -1, -1):
                    if lines[idx].strip():
                        prev_anchor = lines[idx]
                        break
                for idx in range(end, len(lines)):
                    if lines[idx].strip():
                        next_anchor = lines[idx]
                        break
                table["prev_anchor"] = prev_anchor
                table["next_anchor"] = next_anchor

        def _extract_tables(text: str) -> List[Dict[str, Any]]:
            if not text:
                return []
            lines = text.splitlines()
            tables = _extract_markdown_tables(text)
            tables.extend(_extract_html_tables(text))
            _attach_table_anchors(tables, lines)
            return tables

        def _restore_missing_tables(original_text: str, fixed_text: str) -> tuple[str, int]:
            if not original_text or not fixed_text:
                return fixed_text, 0
            original_tables = _extract_tables(original_text)
            if not original_tables:
                return fixed_text, 0
            fixed_normalized = _normalize_table_text(fixed_text)
            missing = []
            for table in original_tables:
                norm = _normalize_table_text(table.get("text", ""))
                if norm and norm not in fixed_normalized:
                    missing.append(table)
            if not missing:
                return fixed_text, 0
            lines = fixed_text.splitlines()
            restored = 0
            for table in missing:
                table_text = (table.get("text") or "").strip("\n")
                if not table_text:
                    continue
                table_lines = table_text.splitlines()
                inserted = False
                prev_anchor = table.get("prev_anchor")
                if prev_anchor:
                    for idx, line in enumerate(lines):
                        if line.strip() == prev_anchor.strip():
                            insert_at = idx + 1
                            lines = lines[:insert_at] + [""] + table_lines + [""] + lines[insert_at:]
                            inserted = True
                            break
                if not inserted:
                    next_anchor = table.get("next_anchor")
                    if next_anchor:
                        for idx, line in enumerate(lines):
                            if line.strip() == next_anchor.strip():
                                insert_at = idx
                                lines = lines[:insert_at] + [""] + table_lines + [""] + lines[insert_at:]
                                inserted = True
                                break
                if not inserted:
                    lines.extend([""] + table_lines)
                restored += 1
            return "\n".join(lines), restored

        # Determine provider
        model = (model_selection or "gemini-2.0-flash").strip().lower()
        use_openai = model.startswith("gpt")

        current_content = content
        fixes: List[str] = []
        errors: List[str] = []

        if legal_issues:
            issues_description = _build_issues_description(legal_issues)
            if issues_description.strip():
                raw_context = _build_raw_context(legal_issues)
                content_snapshot = _build_content_snapshot(current_content)
                legal_prompt = f"""# TAREFA: CORRIGIR PONTOS DA AUDITORIA JURIDICA

## PROBLEMAS DETECTADOS:
{issues_description}

## INSTRUCOES:
1. Corrija o TEXTO FORMATADO com base nos problemas acima.
2. Preserve toda a estrutura e formatacao Markdown existente.
3. Evite inserir informacoes que nao estejam presentes no texto.
4. Se a auditoria indicar citacao suspeita, corrija ou sinalize conforme necessario.
5. Mantenha o texto coeso e juridicamente consistente.

## EVIDENCIAS DA TRANSCRICAO BRUTA (trechos relevantes):
{raw_context if raw_context else "(nao fornecida)"}

## TEXTO FORMATADO ATUAL:
{content_snapshot}

## RESPOSTA:
Retorne o texto formatado corrigido, preservando a formatacao Markdown."""

                try:
                    if use_openai:
                        fixed_content = await self._call_openai(legal_prompt, model)
                    else:
                        fixed_content = await self._call_gemini(legal_prompt, model)
                    fixed_str = (fixed_content or "").strip()
                    current_str = (current_content or "").strip()
                    if not fixed_str:
                        errors.append("Resposta vazia do LLM ao corrigir auditoria juridica")
                    elif fixed_str == current_str:
                        errors.append("LLM não aplicou mudanças na auditoria juridica (texto idêntico)")
                    elif len(fixed_str) > len(current_content) * 0.5:
                        current_content = fixed_content
                        fixes.extend([issue.get("id") for issue in legal_issues])
                    else:
                        errors.append("Resposta do LLM muito curta ao corrigir auditoria juridica")
                except Exception as e:
                    errors.append(str(e))
            else:
                errors.append("Sem descricoes para auditoria juridica")

        if other_issues:
            issues_description = _build_issues_description(other_issues)
            if not issues_description.strip():
                errors.append("Sem descricoes para omissoes")
            else:
                raw_context = _build_raw_context(other_issues)
                content_snapshot = _build_content_snapshot(current_content)
                prompt = f"""# TAREFA: CORRIGIR OMISSOES NO TEXTO FORMATADO

## PROBLEMAS DETECTADOS:
{issues_description}

## INSTRUCOES CRITICAS:
1. Use as EVIDENCIAS DO RAW abaixo (trechos relevantes) para localizar o conteudo faltante.
2. Insira o conteudo encontrado no local apropriado do TEXTO FORMATADO (use a "Seção sugerida" quando existir).
3. Mantenha toda a formatacao Markdown existente.
4. Use tom didatico e formal (3a pessoa).
5. **NAO remova, altere ou omita NADA do texto original** - apenas ADICIONE o que esta faltando.
6. **PRESERVE TODAS AS TABELAS** - copie tabelas integralmente, incluindo tabelas ao final do documento.
7. Se uma lei/sumula/decreto/julgado esta mencionado no RAW mas nao no texto, adicione a referencia no ponto correto.
8. Evite inventar: use somente o que estiver suportado pelas evidencias.
9. **RETORNE O DOCUMENTO COMPLETO** - do inicio ao fim, sem truncar.

## EVIDENCIAS DA TRANSCRICAO BRUTA (trechos relevantes):
{raw_context}

## TEXTO FORMATADO ATUAL:
{content_snapshot}

## RESPOSTA:
Retorne o texto formatado corrigido COMPLETO, com as omissoes inseridas nos locais apropriados.
Mantenha TODA a formatacao Markdown, incluindo TODAS as tabelas."""

                try:
                    if use_openai:
                        fixed_content = await self._call_openai(prompt, model)
                    else:
                        fixed_content = await self._call_gemini(prompt, model)
                    fixed_str = (fixed_content or "").strip()
                    current_str = (current_content or "").strip()
                    if not fixed_str:
                        errors.append("Resposta vazia do LLM ao corrigir omissoes")
                    elif fixed_str == current_str:
                        errors.append("LLM não aplicou mudanças nas omissões (texto idêntico)")
                    elif len(fixed_str) > len(current_content) * 0.5:
                        restored_content, restored_count = _restore_missing_tables(
                            current_content,
                            fixed_content,
                        )
                        if restored_count > 0:
                            logger.warning(f"⚠️ Tabelas recuperadas automaticamente: {restored_count}")
                            fixed_content = restored_content

                        current_content = fixed_content
                        fixes.extend([issue.get("id") for issue in other_issues])
                    else:
                        errors.append("Resposta do LLM muito curta ao corrigir omissoes")
                except Exception as e:
                    errors.append(str(e))

        error_message = "; ".join([err for err in errors if err]) or None
        return {
            "content": current_content,
            "fixes": fixes,
            "error": error_message
        }
    
    async def _call_gemini(self, prompt: str, model: str = "gemini-2.0-flash") -> Optional[str]:
        """Direct Gemini API call using google-genai client."""
        try:
            from google import genai
            from google.genai import types
            from google.oauth2 import service_account
            
            # Initialize client with Vertex AI
            project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "gen-lang-client-0727883752")
            timeout_ms = int(os.getenv("IUDEx_GEMINI_TIMEOUT_MS", "240000"))

            credentials = None
            if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
                try:
                    candidates = sorted(PROJECT_ROOT.glob("gen-lang-client-*.json"))
                    if candidates:
                        credentials = service_account.Credentials.from_service_account_file(str(candidates[0]))
                except Exception as creds_error:
                    logger.warning(f"Gemini credentials auto-load failed: {creds_error}")

            client = genai.Client(
                vertexai=True,
                credentials=credentials,
                project=project_id,
                location="global"
                ,
                http_options=types.HttpOptions(timeout=timeout_ms),
            )
            
            # Map common model names and set appropriate max tokens
            model_name = model
            max_tokens = 8192  # Default for gemini-2.0-flash
            
            if model in ("gemini", "gemini-flash", "gemini-2.0-flash"):
                model_name = "gemini-2.0-flash"
                max_tokens = 8192
            elif model in ("gemini-3-flash", "gemini-3-flash-preview"):
                model_name = "gemini-3-flash-preview"
                max_tokens = 65536  # Gemini 3 supports more
            elif model in ("gemini-2.5-pro", "gemini-2.5-pro-preview"):
                model_name = "gemini-2.5-pro-preview-05-06"
                max_tokens = 65536
            
            def call():
                return client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        max_output_tokens=max_tokens,
                        temperature=0.3,
                    )
                )
            
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, call)
            usage = getattr(response, "usage_metadata", None)
            tokens_in = getattr(usage, "prompt_token_count", None)
            tokens_out = getattr(usage, "candidates_token_count", None)
            cached_tokens = getattr(usage, "cached_content_token_count", None)
            meta = {}
            if tokens_in is not None:
                meta["tokens_in"] = int(tokens_in)
                meta["context_tokens"] = int(tokens_in)
            if tokens_out is not None:
                meta["tokens_out"] = int(tokens_out)
            if cached_tokens is not None:
                meta["cached_tokens_in"] = int(cached_tokens)
            if meta:
                record_api_call(
                    kind="llm",
                    provider="vertex-gemini",
                    model=model_name,
                    success=True,
                    meta=meta,
                )
            return response.text
            
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            raise
    
    async def _call_openai(self, prompt: str, model: str = "gpt-4o-mini") -> Optional[str]:
        """Direct OpenAI API call."""
        try:
            from openai import AsyncOpenAI

            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise RuntimeError("OPENAI_API_KEY não configurada")

            timeout_seconds = float(os.getenv("IUDEx_OPENAI_TIMEOUT_SECONDS", "240"))
            
            client = AsyncOpenAI(api_key=api_key, timeout=timeout_seconds, max_retries=1)
            
            # Map common model names and set appropriate max tokens
            model_name = model
            max_tokens = 16384  # Default for gpt-4o-mini
            
            if model in ("gpt", "gpt-4", "gpt-4o"):
                model_name = "gpt-4o"
                max_tokens = 16384
            elif model in ("gpt-4o-mini", "gpt-mini"):
                model_name = "gpt-4o-mini"
                max_tokens = 16384
            elif model.startswith("gpt-5"):
                model_name = "gpt-5-mini-2025-08-07"
                max_tokens = 32768
            
            response = await client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": "Você é um editor de textos jurídicos didáticos. Corrija omissões mantendo a formatação."},
                    {"role": "user", "content": prompt}
                ],
                max_completion_tokens=max_tokens,
                temperature=0.3
            )
            usage = getattr(response, "usage", None)
            tokens_in = getattr(usage, "prompt_tokens", None)
            tokens_out = getattr(usage, "completion_tokens", None)
            details = getattr(usage, "prompt_tokens_details", None)
            cached_tokens = getattr(details, "cached_tokens", None) if details else None
            meta = {}
            if tokens_in is not None:
                meta["tokens_in"] = int(tokens_in)
                meta["context_tokens"] = int(tokens_in)
            if tokens_out is not None:
                meta["tokens_out"] = int(tokens_out)
            if cached_tokens is not None:
                meta["cached_tokens_in"] = int(cached_tokens)
            if meta:
                record_api_call(
                    kind="llm",
                    provider="openai",
                    model=model_name,
                    success=True,
                    meta=meta,
                )
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise

    # =========================================================================
    # UNIFIED HIL METHODS (Structural + Semantic)
    # =========================================================================

    async def convert_to_hil_issues(
        self,
        raw_content: str,
        formatted_content: str,
        document_name: str,
        omissions: List[str],
        distortions: List[str],
        include_structural: bool = True,
        model_selection: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Converts validation results into unified HIL issues with patches.

        1. Optionally runs structural analysis (duplicates, numbering)
        2. Generates AI patches for omissions/distortions
        3. Returns unified list of HilIssue for review
        """
        logger.info(f"🔄 Converting to HIL issues for: {document_name}")
        logger.info(f"   Omissions: {len(omissions)}, Distortions: {len(distortions)}, Include structural: {include_structural}")

        hil_issues: List[Dict[str, Any]] = []
        structural_count = 0
        semantic_count = 0

        try:
            # 1. Structural analysis (if requested)
            if include_structural:
                structural_result = await self.analyze_structural_issues(
                    content=formatted_content,
                    document_name=document_name,
                    raw_content=raw_content,
                )
                for fix in structural_result.get("pending_fixes", []):
                    fix["source"] = "structural_audit"
                    hil_issues.append(fix)
                    structural_count += 1

            # 2. Convert omissions to HIL issues with patches
            for idx, omission in enumerate(omissions):
                patch = await self._generate_semantic_patch(
                    raw_content=raw_content,
                    formatted_content=formatted_content,
                    issue_type="omission",
                    issue_description=omission,
                    model_selection=model_selection,
                )
                hil_issues.append({
                    "id": f"omission_{idx}",
                    "type": "omission",
                    "description": omission,
                    "action": "INSERT",
                    "severity": "high",
                    "source": "fidelity_audit",
                    "patch": patch,
                    "evidence": patch.get("evidence", []) if patch else [],
                })
                semantic_count += 1

            # 3. Convert distortions to HIL issues with patches
            for idx, distortion in enumerate(distortions):
                patch = await self._generate_semantic_patch(
                    raw_content=raw_content,
                    formatted_content=formatted_content,
                    issue_type="distortion",
                    issue_description=distortion,
                    model_selection=model_selection,
                )
                hil_issues.append({
                    "id": f"distortion_{idx}",
                    "type": "distortion",
                    "description": distortion,
                    "action": "REPLACE",
                    "severity": "high",
                    "source": "fidelity_audit",
                    "patch": patch,
                    "evidence": patch.get("evidence", []) if patch else [],
                })
                semantic_count += 1

            # 4. Validate all issues against raw content to prevent false positives
            logger.info(f"🔍 Validando {len(hil_issues)} issues contra RAW para prevenir falsos positivos...")
            validated_issues = false_positive_prevention.validate_all_issues(
                issues=hil_issues,
                raw_content=raw_content,
                formatted_content=formatted_content,
            )

            # 5. Analyze compression ratio
            compression_analysis = false_positive_prevention.analyze_compression(
                raw_content=raw_content,
                formatted_content=formatted_content,
            )

            filtered_count = len(hil_issues) - len(validated_issues)
            if filtered_count > 0:
                logger.info(f"🚫 {filtered_count} issues filtrados por baixa confiança")

            # Recalculate counts after filtering
            structural_count = sum(1 for i in validated_issues if i.get("source") == "structural_audit")
            semantic_count = sum(1 for i in validated_issues if i.get("source") == "fidelity_audit")

            return {
                "document_name": document_name,
                "converted_at": datetime.now().isoformat(),
                "total_issues": len(validated_issues),
                "hil_issues": validated_issues,
                "structural_count": structural_count,
                "semantic_count": semantic_count,
                "requires_approval": len(validated_issues) > 0,
                "filtered_false_positives": filtered_count,
                "compression_analysis": compression_analysis,
            }

        except Exception as e:
            logger.error(f"❌ Convert to HIL failed: {e}")
            return {
                "document_name": document_name,
                "converted_at": datetime.now().isoformat(),
                "total_issues": 0,
                "hil_issues": [],
                "structural_count": 0,
                "semantic_count": 0,
                "requires_approval": False,
                "filtered_false_positives": 0,
                "error": str(e),
            }

    async def _generate_semantic_patch(
        self,
        raw_content: str,
        formatted_content: str,
        issue_type: str,
        issue_description: str,
        model_selection: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Generates a semantic patch for an omission or distortion using AI.

        Returns:
            {
                "anchor_text": "text to locate insertion point",
                "old_text": "text to replace (for distortions)",
                "new_text": "corrected/new content",
                "evidence": ["raw content snippets"]
            }
        """
        logger.info(f"🔧 Generating semantic patch for {issue_type}: {issue_description[:80]}...")

        # Find evidence in raw content
        evidence = self._find_evidence_in_raw(raw_content, issue_description)

        if issue_type == "omission":
            prompt = f"""# TAREFA: GERAR PATCH PARA OMISSÃO

## PROBLEMA DETECTADO:
{issue_description}

## EVIDÊNCIA DO RAW (transcrição original):
{chr(10).join(evidence) if evidence else "(buscar no conteúdo completo)"}

## TEXTO FORMATADO ATUAL (trecho relevante):
{formatted_content[:8000]}

## INSTRUÇÕES:
1. Localize onde o conteúdo omitido deveria estar no texto formatado
2. Gere o texto que deve ser INSERIDO
3. Identifique uma âncora (frase existente após a qual inserir)

## RESPOSTA (JSON):
Retorne APENAS um JSON válido no formato:
{{
    "anchor_text": "frase existente no texto após a qual inserir (50-100 chars)",
    "new_text": "conteúdo a ser inserido (parágrafo completo)",
    "confidence": "high|medium|low"
}}
"""
        else:  # distortion
            prompt = f"""# TAREFA: GERAR PATCH PARA DISTORÇÃO

## PROBLEMA DETECTADO:
{issue_description}

## EVIDÊNCIA DO RAW (transcrição original):
{chr(10).join(evidence) if evidence else "(buscar no conteúdo completo)"}

## TEXTO FORMATADO ATUAL (trecho relevante):
{formatted_content[:8000]}

## INSTRUÇÕES:
1. Identifique o texto incorreto no documento formatado
2. Gere a correção baseada na evidência do raw
3. Retorne o texto original e o corrigido

## RESPOSTA (JSON):
Retorne APENAS um JSON válido no formato:
{{
    "old_text": "texto incorreto atual (exato como aparece)",
    "new_text": "texto corrigido",
    "confidence": "high|medium|low"
}}
"""

        try:
            model = model_selection or "gemini-2.0-flash"
            if model.startswith("gpt"):
                response = await self._call_openai(prompt, model)
            else:
                response = await self._call_gemini(prompt, model)

            if not response:
                return {"new_text": "", "evidence": evidence, "confidence": "low", "validated": False}

            # Parse JSON response
            import json
            # Clean response - remove markdown code blocks if present
            clean_response = response.strip()
            if clean_response.startswith("```"):
                lines = clean_response.split("\n")
                clean_response = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

            try:
                patch_data = json.loads(clean_response)
            except json.JSONDecodeError:
                # Try to extract JSON from response
                json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
                if json_match:
                    patch_data = json.loads(json_match.group())
                else:
                    logger.warning(f"Could not parse patch response as JSON: {response[:200]}")
                    patch_data = {"new_text": response}

            patch_data["evidence"] = evidence

            # === VALIDATE PATCH AGAINST RAW (SOURCE OF TRUTH) ===
            new_text = patch_data.get("new_text", "")
            validation_notes = []
            confidence_score = 0.50  # Base

            if new_text and raw_content:
                # 1. Check if new_text content exists in raw
                new_text_normalized = re.sub(r'\s+', ' ', new_text.lower().strip())
                raw_normalized = re.sub(r'\s+', ' ', raw_content.lower())

                # Direct substring check
                if new_text_normalized[:100] in raw_normalized:
                    confidence_score += 0.25
                    validation_notes.append("✓ Conteúdo do patch encontrado no RAW")
                else:
                    # Fuzzy check - look for key terms
                    key_terms = [t for t in new_text.split() if len(t) > 5][:5]
                    terms_found = sum(1 for t in key_terms if t.lower() in raw_normalized)
                    if terms_found >= len(key_terms) * 0.6:
                        confidence_score += 0.15
                        validation_notes.append(f"✓ {terms_found}/{len(key_terms)} termos-chave encontrados no RAW")
                    else:
                        confidence_score -= 0.15
                        validation_notes.append("⚠️ Conteúdo do patch não confirmado no RAW")

                # 2. Check for legal references in patch vs raw
                legal_refs_patch = re.findall(r'[Ll]ei\s*[\d.]+|[Aa]rt\.?\s*\d+|[Ss]úmula\s*\d+', new_text)
                if legal_refs_patch:
                    refs_in_raw = sum(1 for ref in legal_refs_patch if ref.lower() in raw_normalized)
                    if refs_in_raw == len(legal_refs_patch):
                        confidence_score += 0.15
                        validation_notes.append("✓ Referências legais validadas no RAW")
                    elif refs_in_raw > 0:
                        confidence_score += 0.05
                        validation_notes.append(f"⚠️ {refs_in_raw}/{len(legal_refs_patch)} refs legais no RAW")
                    else:
                        confidence_score -= 0.20
                        validation_notes.append("⚠️ Referências legais NÃO encontradas no RAW - possível alucinação")

                # 3. For distortions, check if old_text exists in formatted
                old_text = patch_data.get("old_text", "")
                if issue_type == "distortion" and old_text:
                    if old_text in formatted_content:
                        confidence_score += 0.10
                        validation_notes.append("✓ Texto original encontrado no formatado")
                    else:
                        # Fuzzy search
                        old_normalized = re.sub(r'\s+', ' ', old_text.lower().strip())
                        formatted_normalized = re.sub(r'\s+', ' ', formatted_content.lower())
                        if old_normalized in formatted_normalized:
                            confidence_score += 0.05
                            validation_notes.append("✓ Texto original encontrado (normalizado)")
                        else:
                            confidence_score -= 0.10
                            validation_notes.append("⚠️ Texto original não encontrado no formatado")

            # Clamp confidence
            confidence_score = max(0.0, min(1.0, confidence_score))

            # Map to confidence level
            if confidence_score >= 0.85:
                confidence_level = "high"
            elif confidence_score >= 0.65:
                confidence_level = "medium"
            else:
                confidence_level = "low"

            patch_data["confidence"] = confidence_level
            patch_data["confidence_score"] = confidence_score
            patch_data["validation_notes"] = validation_notes
            patch_data["validated_against_raw"] = True

            logger.info(f"   Patch confidence: {confidence_level} ({confidence_score:.2f}) - {validation_notes}")

            return patch_data

        except Exception as e:
            logger.error(f"❌ Patch generation failed: {e}")
            return {"new_text": "", "evidence": evidence, "error": str(e), "confidence": "low", "validated": False}

    def _find_evidence_in_raw(self, raw_content: str, issue_description: str, max_snippets: int = 3) -> List[str]:
        """
        Finds relevant snippets in raw content based on issue description.
        """
        if not raw_content:
            return []

        snippets = []
        window = 300

        # Extract potential keywords from issue description
        # Look for legal references, numbers, specific terms
        keywords = []

        # Extract law references (Lei X, Art. X, etc.)
        law_patterns = [
            r'[Ll]ei\s*(?:n[º°]?\s*)?([\d.]+)',
            r'[Aa]rt(?:igo)?\.?\s*(\d+)',
            r'[Ss]úmula\s*(?:vinculante\s*)?(?:n[º°]?\s*)?(\d+)',
            r'[Dd]ecreto\s*(?:n[º°]?\s*)?([\d.]+)',
        ]

        for pattern in law_patterns:
            matches = re.findall(pattern, issue_description)
            keywords.extend(matches)

        # Also extract quoted terms
        quoted = re.findall(r'"([^"]+)"', issue_description)
        keywords.extend(quoted)

        # Search for each keyword in raw content
        for keyword in keywords[:5]:  # Limit to avoid too many searches
            pattern = re.escape(str(keyword))
            for match in re.finditer(pattern, raw_content, re.IGNORECASE):
                start = max(0, match.start() - window)
                end = min(len(raw_content), match.end() + window)
                snippet = raw_content[start:end].strip()
                if snippet and snippet not in snippets:
                    snippets.append(f"...{snippet}...")
                    if len(snippets) >= max_snippets:
                        break
            if len(snippets) >= max_snippets:
                break

        return snippets

    async def apply_unified_hil_fixes(
        self,
        content: str,
        raw_content: Optional[str],
        approved_fixes: List[Dict[str, Any]],
        model_selection: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Applies unified HIL fixes to content.

        Handles both:
        - Structural fixes (deterministic): REMOVE, MERGE, RENUMBER
        - Semantic fixes (patches): INSERT, REPLACE
        """
        logger.info(f"✅ Applying {len(approved_fixes)} unified HIL fixes...")

        structural_types = {"duplicate_paragraph", "duplicate_section", "heading_numbering"}
        semantic_types = {"omission", "distortion"}

        structural_fixes = [f for f in approved_fixes if f.get("type") in structural_types]
        semantic_fixes = [f for f in approved_fixes if f.get("type") in semantic_types]

        logger.info(f"   Structural: {len(structural_fixes)}, Semantic: {len(semantic_fixes)}")

        current_content = content
        fixes_applied = []
        structural_applied = 0
        semantic_applied = 0

        try:
            # 1. Apply structural fixes first (deterministic)
            if structural_fixes:
                structural_result = await self.apply_approved_fixes(
                    content=current_content,
                    approved_fix_ids=[f.get("id") for f in structural_fixes],
                    approved_fixes=structural_fixes,
                )
                if structural_result.get("success") and structural_result.get("fixed_content"):
                    current_content = structural_result["fixed_content"]
                    fixes_applied.extend(structural_result.get("fixes_applied", []))
                    structural_applied = len(structural_result.get("fixes_applied", []))

            # 2. Apply semantic fixes (patches) with validation
            skipped_fixes = []
            for fix in semantic_fixes:
                patch = fix.get("patch") or {}
                fix_type = fix.get("type")
                action = fix.get("action")

                # Check confidence before applying
                confidence_score = patch.get("confidence_score", 0.50)
                confidence = patch.get("confidence", "medium")

                # Skip low confidence patches unless explicitly approved
                if confidence_score < 0.50 and not fix.get("force_apply"):
                    skipped_fixes.append(f"SKIPPED (baixa confiança {confidence_score:.2f}): {fix.get('description', '')[:50]}...")
                    logger.warning(f"⏭️ Skipping low confidence fix: {fix.get('id')} ({confidence_score:.2f})")
                    continue

                if action == "INSERT" and patch.get("new_text"):
                    anchor = patch.get("anchor_text", "")
                    new_text = patch.get("new_text", "")

                    # Try exact match first
                    if anchor and anchor in current_content:
                        insert_pos = current_content.find(anchor) + len(anchor)
                        current_content = (
                            current_content[:insert_pos]
                            + "\n\n"
                            + new_text
                            + current_content[insert_pos:]
                        )
                        fixes_applied.append(f"INSERT: {fix.get('description', '')[:50]}...")
                        semantic_applied += 1
                    elif anchor:
                        # Try fuzzy anchor matching
                        fuzzy_pos = self._fuzzy_find_position(anchor, current_content)
                        if fuzzy_pos >= 0:
                            current_content = (
                                current_content[:fuzzy_pos]
                                + "\n\n"
                                + new_text
                                + current_content[fuzzy_pos:]
                            )
                            fixes_applied.append(f"INSERT (fuzzy anchor): {fix.get('description', '')[:50]}...")
                            semantic_applied += 1
                        elif new_text:
                            # Last resort: append
                            current_content = current_content + "\n\n" + new_text
                            fixes_applied.append(f"INSERT (appended): {fix.get('description', '')[:50]}...")
                            semantic_applied += 1
                    elif new_text:
                        current_content = current_content + "\n\n" + new_text
                        fixes_applied.append(f"INSERT (appended): {fix.get('description', '')[:50]}...")
                        semantic_applied += 1

                elif action == "REPLACE" and patch.get("old_text") and patch.get("new_text"):
                    old_text = patch.get("old_text", "")
                    new_text = patch.get("new_text", "")

                    # Validate against raw before applying
                    if raw_content:
                        # Check if new_text is grounded in raw
                        new_text_lower = new_text.lower()[:100]
                        raw_lower = raw_content.lower()
                        if not any(term in raw_lower for term in new_text_lower.split()[:5] if len(term) > 4):
                            logger.warning(f"⚠️ REPLACE new_text not found in raw, skipping: {new_text[:50]}...")
                            skipped_fixes.append(f"SKIPPED (não confirmado no RAW): {fix.get('description', '')[:50]}...")
                            continue

                    if old_text in current_content:
                        current_content = current_content.replace(old_text, new_text, 1)
                        fixes_applied.append(f"REPLACE: {fix.get('description', '')[:50]}...")
                        semantic_applied += 1
                    else:
                        # Try fuzzy match for old_text
                        fuzzy_match = self._fuzzy_find_text(old_text, current_content)
                        if fuzzy_match:
                            current_content = current_content.replace(fuzzy_match, new_text, 1)
                            fixes_applied.append(f"REPLACE (fuzzy): {fix.get('description', '')[:50]}...")
                            semantic_applied += 1
                        else:
                            skipped_fixes.append(f"SKIPPED (texto não encontrado): {fix.get('description', '')[:50]}...")
                            logger.warning(f"Could not find match for REPLACE: {old_text[:50]}...")

            # Calculate size reduction
            original_len = len(content)
            fixed_len = len(current_content)
            if original_len > 0:
                size_change = (fixed_len - original_len) / original_len * 100
                size_reduction = f"{size_change:+.1f}%"
            else:
                size_reduction = "0.0%"

            if skipped_fixes:
                logger.info(f"⏭️ {len(skipped_fixes)} fixes skipped due to validation")

            return {
                "success": True,
                "fixed_content": current_content,
                "fixes_applied": fixes_applied,
                "skipped_fixes": skipped_fixes,
                "structural_applied": structural_applied,
                "semantic_applied": semantic_applied,
                "size_reduction": size_reduction,
            }

        except Exception as e:
            logger.error(f"❌ Apply unified HIL failed: {e}")
            return {
                "success": False,
                "fixed_content": content,
                "fixes_applied": fixes_applied,
                "skipped_fixes": skipped_fixes if 'skipped_fixes' in dir() else [],
                "structural_applied": structural_applied,
                "semantic_applied": semantic_applied,
                "error": str(e),
            }

    def _fuzzy_find_position(self, needle: str, haystack: str, threshold: float = 0.80) -> int:
        """
        Finds the position to insert after a fuzzy-matched anchor.
        Returns -1 if not found.
        """
        if not needle or not haystack:
            return -1

        from difflib import SequenceMatcher

        needle_norm = re.sub(r'\s+', ' ', needle.lower().strip())
        haystack_norm = re.sub(r'\s+', ' ', haystack.lower())
        needle_len = len(needle_norm)

        best_pos = -1
        best_ratio = 0.0

        # Sliding window search
        step = max(1, needle_len // 4)
        for i in range(0, len(haystack_norm) - needle_len + 1, step):
            window = haystack_norm[i:i + needle_len]
            ratio = SequenceMatcher(None, needle_norm, window).ratio()

            if ratio > best_ratio:
                best_ratio = ratio
                best_pos = i + needle_len

        if best_ratio >= threshold:
            return best_pos

        return -1

    def _fuzzy_find_text(self, needle: str, haystack: str, threshold: float = 0.85) -> Optional[str]:
        """
        Finds text in haystack with fuzzy matching.
        Returns the matched text or None.
        """
        if not needle or not haystack:
            return None

        from difflib import SequenceMatcher

        needle_norm = re.sub(r'\s+', ' ', needle.lower().strip())
        needle_len = len(needle_norm)

        best_match = None
        best_ratio = 0.0

        # Sliding window
        step = max(1, needle_len // 4)
        for i in range(0, len(haystack) - needle_len + 1, step):
            # Get window in original case
            window_original = haystack[i:i + needle_len + 20][:needle_len]
            window_norm = re.sub(r'\s+', ' ', window_original.lower().strip())

            ratio = SequenceMatcher(None, needle_norm, window_norm).ratio()

            if ratio > best_ratio:
                best_ratio = ratio
                best_match = window_original

        if best_ratio >= threshold:
            return best_match

        return None

    # =========================================================================
    # HEARING/MEETING QUALITY METHODS
    # =========================================================================

    async def validate_hearing_segments(
        self,
        segments: List[Dict[str, Any]],
        speakers: List[Dict[str, Any]],
        formatted_content: str,
        raw_content: str,
        document_name: str = "hearing",
        mode: str = "AUDIENCIA",
    ) -> Dict[str, Any]:
        """
        Validates a hearing/meeting transcription.

        Checks:
        - Completude de falas (% without [inaudível])
        - Identificação de falantes
        - Coerência cronológica
        - Detecção de contradições

        Returns validation result with score and issues.
        """
        from datetime import datetime

        logger.info(f"🔍 Validating hearing: {document_name}, mode={mode}")

        issues: List[Dict] = []
        critical_areas: List[str] = []

        # 1. Check completude (inaudível markers)
        completude = self._check_hearing_completude(segments, formatted_content)
        if not completude["approved"]:
            critical_areas.append("completude_falas")

        # 2. Check speaker identification
        speaker_id = self._check_speaker_identification(segments, speakers)
        if not speaker_id["approved"]:
            critical_areas.append("identificacao_falantes")

        # 3. Check chronology
        chronology = self._check_hearing_chronology(segments)
        if not chronology["approved"]:
            critical_areas.append("ordem_cronologica")

        # 4. Find speaker inconsistencies
        speaker_issues = self._find_speaker_inconsistencies(segments, speakers)
        issues.extend(speaker_issues)

        # 5. Find timestamp errors
        timestamp_issues = self._find_timestamp_errors(segments)
        issues.extend(timestamp_issues)

        # 6. Find incomplete statements
        incomplete_issues = self._find_incomplete_statements(segments)
        issues.extend(incomplete_issues)

        # Calculate score (0-10)
        score = 10.0
        if not completude["approved"]:
            score -= 2.5
        if not speaker_id["approved"]:
            score -= 2.0
        if not chronology["approved"]:
            score -= 1.5
        if len(issues) > 5:
            score -= 1.0
        score = max(0.0, min(10.0, score))

        approved = completude["approved"] and speaker_id["approved"] and chronology["approved"]
        requires_review = not approved or len(issues) > 3

        review_reasons = []
        if not completude["approved"]:
            review_reasons.append(f"Completude baixa: {completude['rate']*100:.1f}%")
        if not speaker_id["approved"]:
            review_reasons.append(f"Identificação baixa: {speaker_id['rate']*100:.1f}%")
        if not chronology["approved"]:
            review_reasons.append(f"{chronology['inversions']} inversões cronológicas")
        if len(issues) > 3:
            review_reasons.append(f"{len(issues)} problemas detectados")

        return {
            "document_name": document_name,
            "validated_at": datetime.utcnow().isoformat(),
            "approved": approved,
            "score": round(score, 2),
            "mode": mode,
            "completude_rate": completude["rate"],
            "speaker_identification_rate": speaker_id["rate"],
            "evidence_preservation_rate": 1.0,  # Not checked in this simplified version
            "chronology_valid": chronology["approved"],
            "issues": issues,
            "total_issues": len(issues),
            "requires_review": requires_review,
            "review_reason": " / ".join(review_reasons) if review_reasons else None,
            "critical_areas": critical_areas,
        }

    def _check_hearing_completude(
        self,
        segments: List[Dict[str, Any]],
        formatted_content: str,
    ) -> Dict[str, Any]:
        """Check completude of hearing (% without [inaudível])."""
        import re

        INAUDIBLE_PATTERNS = [
            r'\[inaudível\]',
            r'\[inaudivel\]',
            r'\[incompreensível\]',
            r'\[incompreensivel\]',
            r'\[\?\?\?\]',
            r'\[...\]',
        ]

        total_segments = len(segments)
        if total_segments == 0:
            return {"rate": 1.0, "approved": True, "segments_with_inaudible": 0}

        segments_with_inaudible = 0
        for seg in segments:
            text = seg.get("text", "")
            for pattern in INAUDIBLE_PATTERNS:
                if re.search(pattern, text, re.IGNORECASE):
                    segments_with_inaudible += 1
                    break

        # Also check formatted content
        total_inaudibles = 0
        for pattern in INAUDIBLE_PATTERNS:
            total_inaudibles += len(re.findall(pattern, formatted_content, re.IGNORECASE))

        rate = 1.0 - (segments_with_inaudible / total_segments) if total_segments > 0 else 1.0
        approved = rate >= 0.90  # 90% threshold

        return {
            "rate": round(rate, 4),
            "approved": approved,
            "segments_with_inaudible": segments_with_inaudible,
            "total_inaudibles": total_inaudibles,
        }

    def _check_speaker_identification(
        self,
        segments: List[Dict[str, Any]],
        speakers: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Check speaker identification rate."""
        total_segments = len(segments)
        if total_segments == 0:
            return {"rate": 1.0, "approved": True, "identified": 0}

        speaker_ids = {sp.get("speaker_id") for sp in speakers if sp.get("speaker_id")}
        identified = 0

        for seg in segments:
            speaker_id = seg.get("speaker_id")
            speaker_label = seg.get("speaker_label", "")

            if speaker_id and speaker_id in speaker_ids:
                identified += 1
            elif speaker_label and not speaker_label.startswith("SPEAKER "):
                identified += 1

        rate = identified / total_segments if total_segments > 0 else 0.0
        approved = rate >= 0.80  # 80% threshold

        return {
            "rate": round(rate, 4),
            "approved": approved,
            "identified": identified,
            "total": total_segments,
        }

    def _check_hearing_chronology(
        self,
        segments: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Check chronological order of segments."""
        total_segments = len(segments)
        if total_segments < 2:
            return {"approved": True, "inversions": 0}

        inversions = 0
        last_start = -1.0

        for seg in segments:
            start = seg.get("start")
            if start is not None:
                if start < last_start:
                    inversions += 1
                last_start = start

        approved = inversions == 0

        return {
            "approved": approved,
            "inversions": inversions,
        }

    def _find_speaker_inconsistencies(
        self,
        segments: List[Dict[str, Any]],
        speakers: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Find speaker name inconsistencies."""
        import uuid

        issues = []
        speaker_names: Dict[str, Set[str]] = {}  # speaker_id -> names seen

        for seg in segments:
            speaker_id = seg.get("speaker_id")
            speaker_label = seg.get("speaker_label")

            if speaker_id and speaker_label:
                if speaker_id not in speaker_names:
                    speaker_names[speaker_id] = set()
                speaker_names[speaker_id].add(speaker_label)

        # Check for inconsistencies
        for speaker_id, names in speaker_names.items():
            if len(names) > 1:
                issues.append({
                    "id": str(uuid.uuid4())[:8],
                    "type": "speaker_inconsistency",
                    "description": f"Falante {speaker_id} tem múltiplos nomes: {', '.join(sorted(names))}",
                    "severity": "medium",
                    "speaker_id": speaker_id,
                    "suggestion": f"Padronizar o nome do falante {speaker_id}",
                })

        return issues

    def _find_timestamp_errors(
        self,
        segments: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Find timestamp errors (overlaps, large gaps)."""
        import uuid

        issues = []

        for i, seg in enumerate(segments):
            start = seg.get("start")
            end = seg.get("end")
            segment_id = seg.get("id", f"seg_{i}")

            # Check for missing timestamps
            if start is None or end is None:
                issues.append({
                    "id": str(uuid.uuid4())[:8],
                    "type": "timestamp_error",
                    "description": f"Segmento {segment_id} sem timestamps completos",
                    "severity": "low",
                    "segment_id": segment_id,
                })
                continue

            # Check for invalid timestamps (end before start)
            if end < start:
                issues.append({
                    "id": str(uuid.uuid4())[:8],
                    "type": "timestamp_error",
                    "description": f"Segmento {segment_id}: fim ({end:.1f}s) antes do início ({start:.1f}s)",
                    "severity": "high",
                    "segment_id": segment_id,
                    "timestamp": f"{start:.1f}s - {end:.1f}s",
                })

            # Check for overlaps with next segment
            if i < len(segments) - 1:
                next_seg = segments[i + 1]
                next_start = next_seg.get("start")
                if next_start is not None and end > next_start + 0.5:  # 0.5s tolerance
                    issues.append({
                        "id": str(uuid.uuid4())[:8],
                        "type": "timestamp_error",
                        "description": f"Sobreposição: segmento {segment_id} termina em {end:.1f}s, próximo começa em {next_start:.1f}s",
                        "severity": "medium",
                        "segment_id": segment_id,
                    })

        return issues

    def _find_incomplete_statements(
        self,
        segments: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Find incomplete or cut-off statements."""
        import uuid

        issues = []

        for i, seg in enumerate(segments):
            text = seg.get("text", "").strip()
            segment_id = seg.get("id", f"seg_{i}")

            if not text:
                issues.append({
                    "id": str(uuid.uuid4())[:8],
                    "type": "incomplete_statement",
                    "description": f"Segmento {segment_id} está vazio",
                    "severity": "high",
                    "segment_id": segment_id,
                })
                continue

            # Check for cut-off indicators
            cutoff_patterns = [
                r'\.\.\.$',  # Ends with ...
                r'—$',  # Ends with em-dash
                r'–$',  # Ends with en-dash
                r'\s+$',  # Ends with whitespace (shouldn't happen after strip)
            ]

            for pattern in cutoff_patterns:
                if re.search(pattern, text):
                    issues.append({
                        "id": str(uuid.uuid4())[:8],
                        "type": "incomplete_statement",
                        "description": f"Segmento {segment_id} parece estar cortado: '{text[-50:]}'",
                        "severity": "low",
                        "segment_id": segment_id,
                    })
                    break

        return issues

    async def analyze_hearing_segment_issues(
        self,
        segments: List[Dict[str, Any]],
        speakers: List[Dict[str, Any]],
        document_name: str = "hearing",
        include_contradictions: bool = True,
    ) -> Dict[str, Any]:
        """
        Analyzes hearing segments for detailed issue reporting.

        Returns issues grouped by segment for HIL review.
        """
        from datetime import datetime

        logger.info(f"🔬 Analyzing hearing segments: {document_name}")

        issues_by_segment: Dict[str, List[Dict]] = {}
        summary: Dict[str, int] = {
            "speaker_inconsistency": 0,
            "timestamp_error": 0,
            "incomplete_statement": 0,
            "speaker_alignment_error": 0,
        }

        # Collect all issues
        speaker_issues = self._find_speaker_inconsistencies(segments, speakers)
        timestamp_issues = self._find_timestamp_errors(segments)
        incomplete_issues = self._find_incomplete_statements(segments)

        all_issues = speaker_issues + timestamp_issues + incomplete_issues

        # Group by segment
        for issue in all_issues:
            segment_id = issue.get("segment_id", "global")
            if segment_id not in issues_by_segment:
                issues_by_segment[segment_id] = []

            # Find speaker label for this segment
            speaker_label = None
            for seg in segments:
                if seg.get("id") == segment_id:
                    speaker_label = seg.get("speaker_label")
                    break

            issue_data = {
                "segment_id": segment_id,
                "type": issue["type"],
                "description": issue["description"],
                "severity": issue["severity"],
                "speaker_label": speaker_label,
                "timestamp_range": issue.get("timestamp"),
            }

            issues_by_segment[segment_id].append(issue_data)

            # Update summary
            issue_type = issue["type"]
            if issue_type in summary:
                summary[issue_type] += 1

        segments_with_issues = len([s for s in issues_by_segment.values() if s])

        return {
            "document_name": document_name,
            "analyzed_at": datetime.utcnow().isoformat(),
            "total_segments": len(segments),
            "segments_with_issues": segments_with_issues,
            "issues_by_segment": issues_by_segment,
            "summary": summary,
        }


# Singleton instance
quality_service = QualityService()
