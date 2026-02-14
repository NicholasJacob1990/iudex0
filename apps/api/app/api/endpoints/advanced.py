import logging
import os
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from app.core.security import get_current_user
from app.models.user import User
from app.services.quality_service import quality_service
from app.services.ai.audit_service import audit_service
from app.services.transcription_service import transcription_service

router = APIRouter()
logger = logging.getLogger(__name__)

# Scoped wrapper to force collection filters for audit citations.
class _ScopedRAGManager:
    def __init__(self, rag_manager, sources: List[str]):
        self._rag_manager = rag_manager
        self._sources = sources

    def hybrid_search(self, query: str, *args, **kwargs):
        if kwargs.get("sources") is None:
            kwargs["sources"] = self._sources
        return self._rag_manager.hybrid_search(query, *args, **kwargs)

# ============= REQUEST MODELS =============

class TranscribeRequest(BaseModel):
    """Full transcription request with all CLI-equivalent options."""
    file_path: str  # Local path to audio/video
    mode: str = "APOSTILA"
    provider: Optional[str] = None
    model_selection: Optional[str] = None
    thinking_level: Optional[str] = None
    custom_prompt: Optional[str] = None
    custom_prompt_path: Optional[str] = None
    dry_run: bool = False  # --dry-run: Only analyze, don't process
    skip_formatting: bool = False  # --skip-formatting: Transcribe only
    word_only: bool = False  # --word-only: Generate Word from MD
    high_accuracy: bool = False  # --high-accuracy: Use beam search
    auto_apply_fixes: bool = False  # --auto-apply-fixes: Apply fixes automatically

class ApplyFixesRequest(BaseModel):
    """Apply structural fixes from suggestions."""
    file_path: str  # Path to .md file
    suggestions: Dict[str, Any]  # Suggestions JSON from analyze

class AuditWithRAGRequest(BaseModel):
    """Full audit with RAG/grounding support."""
    text: str
    use_rag: bool = True
    rag_sources: Optional[List[str]] = None
    include_citation_analysis: bool = True

class DryRunAnalysisRequest(BaseModel):
    """Cross-file structural analysis (dry-run)."""
    files: List[str]
    use_fingerprint: bool = False

class RenumberRequest(BaseModel):
    content: str

class DiarizeRequest(BaseModel):
    # For re-alignment, we ideally need segments, but simplest is to just accept audio path if local
    # or handle full pipeline. For now, we will assume this triggers a standalone diarization 
    # if segments are provided, or just diarization return if not.
    audio_path: str
    segments: Optional[List[Dict[str, Any]]] = None # Whispher segments: {start, end, text}

@router.post("/renumber")
async def renumber_paragraphs(request: RenumberRequest, current_user: User = Depends(get_current_user)):
    """
    Exposes VomoMLX.renumber_headings / renumber_topics.
    """
    try:
        # We can use VomoMLX instance for this utility
        vomo = transcription_service._get_vomo()
        if not vomo:
            raise HTTPException(status_code=503, detail="VomoMLX unavailable")
        
        # Use simple renumbering
        renumbered = vomo.renumber_headings(request.content)
        return {"content": renumbered}
    except Exception as e:
        logger.error(f"Renumber error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class AuditStructureRequest(BaseModel):
    content: str
    document_name: str = "documento"
    raw_content: Optional[str] = None

@router.post("/audit-structure-rigorous")
async def audit_structure_rigorous(request: AuditStructureRequest, current_user: User = Depends(get_current_user)):
    """
    Exposes auto_fix_apostilas.analyze_structural_issues.
    Accepts JSON body with content and document_name.
    """
    try:
        # Helper in quality_service that wraps auto_fix_apostilas
        result = await quality_service.analyze_structural_issues(
            content=request.content,
            document_name=request.document_name,
            raw_content=request.raw_content
        )
        return result
                
    except Exception as e:
        logger.error(f"Structural audit error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/consistency-check")
async def consistency_check(request: RenumberRequest, current_user: User = Depends(get_current_user)): # Reusing content model
    """
    Exposes audit_juridico.audit_document_text (Deep Consistency).
    """
    try:
        # Uses audit_service which wraps audit_juridico
        result = audit_service.audit_document(
            text=request.content
        )
        return result
    except Exception as e:
        logger.error(f"Consistency check error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class CitationCheckRequest(BaseModel):
    citation: str
    provider: str = "gemini"

@router.post("/verify-citation")
async def verify_citation(request: CitationCheckRequest, current_user: User = Depends(get_current_user)):
    """
    Exposes audit_juridico.verify_citation_online.
    """
    return await audit_service.verify_citation(request.citation, request.provider)

# ============= CROSS-FILE ANALYSIS (DRY-RUN) =============

@router.post("/dry-run-analysis")
async def dry_run_analysis(request: DryRunAnalysisRequest, current_user: User = Depends(get_current_user)):
    """
    Exposes auto_fix_apostilas.generate_structural_suggestions.
    Analyzes multiple files and returns suggestions without applying changes.
    CLI equivalent: --dry-run
    """
    try:
        from auto_fix_apostilas import generate_structural_suggestions
        result = generate_structural_suggestions(request.files, request.use_fingerprint)
        return result
    except ImportError:
        raise HTTPException(status_code=503, detail="auto_fix_apostilas not available")
    except Exception as e:
        logger.error(f"Dry-run analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class CrossFileDuplicatesRequest(BaseModel):
    files: List[str]

@router.post("/cross-file-duplicates")
async def cross_file_duplicates(request: CrossFileDuplicatesRequest, current_user: User = Depends(get_current_user)):
    """
    Finds duplicate paragraphs across multiple files using fingerprinting.
    Wraps quality_service.find_cross_file_duplicates.
    """
    try:
        result = await quality_service.find_cross_file_duplicates(request.files)
        return result
    except Exception as e:
        logger.error(f"Cross-file duplicates error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/apply-structural-fixes")
async def apply_structural_fixes(request: ApplyFixesRequest, current_user: User = Depends(get_current_user)):
    """
    Exposes auto_fix_apostilas.apply_structural_fixes_to_file.
    Applies approved fixes to a file.
    CLI equivalent: --auto-apply-fixes
    """
    if not os.path.exists(request.file_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    try:
        from auto_fix_apostilas import apply_structural_fixes_to_file
        result = apply_structural_fixes_to_file(request.file_path, request.suggestions)
        return result
    except ImportError:
        raise HTTPException(status_code=503, detail="auto_fix_apostilas not available")
    except Exception as e:
        logger.error(f"Apply fixes error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============= FULL TRANSCRIPTION WITH CLI OPTIONS =============

@router.post("/transcribe-advanced")
async def transcribe_advanced(request: TranscribeRequest, current_user: User = Depends(get_current_user)):
    """
    Full transcription endpoint with all CLI-equivalent options:
    --dry-run, --skip-formatting, --word-only, --high-accuracy, --auto-apply-fixes
    """
    if not os.path.exists(request.file_path):
        raise HTTPException(status_code=404, detail="File not found on server")
    
    try:
        vomo = transcription_service._get_vomo(
            model_selection=request.model_selection,
            thinking_level=request.thinking_level,
            provider=request.provider
        )
        if not vomo:
            raise HTTPException(status_code=503, detail="VomoMLX unavailable")
        
        folder = os.path.dirname(request.file_path)
        video_name = os.path.splitext(os.path.basename(request.file_path))[0]

        custom_prompt = request.custom_prompt
        if request.custom_prompt_path:
            if not os.path.exists(request.custom_prompt_path):
                raise HTTPException(status_code=404, detail="Custom prompt file not found")
            with open(request.custom_prompt_path, 'r', encoding='utf-8') as f:
                custom_prompt = f.read()
        
        # Word-only mode: Generate Word from existing MD
        if request.word_only and request.file_path.endswith('.md'):
            with open(request.file_path, 'r', encoding='utf-8') as f:
                md_content = f.read()
            output_path = vomo.save_as_word(md_content, video_name, folder)
            return {"mode": "word-only", "output": output_path}
        if request.word_only:
            raise HTTPException(status_code=400, detail="word_only requires a .md file")
        
        # Transcription
        if request.file_path.endswith('.txt'):
            with open(request.file_path, 'r', encoding='utf-8') as f:
                transcription = f.read()
        else:
            if request.dry_run:
                return {"error": "Dry run não suporta áudio. Use arquivo .txt"}
            audio = vomo.optimize_audio(request.file_path)
            transcription = vomo.transcribe_file(
                audio,
                mode=request.mode,
                high_accuracy=bool(request.high_accuracy),
            )
        
        # Skip formatting mode
        if request.skip_formatting:
            raw_path = os.path.join(folder, f"{video_name}_RAW.txt")
            with open(raw_path, 'w', encoding='utf-8') as f:
                f.write(transcription)
            return {"mode": "skip-formatting", "raw_path": raw_path, "content": transcription}
        
        # Format transcription
        import asyncio
        formatted = await vomo.format_transcription_async(
            transcription, video_name, folder,
            mode=request.mode,
            custom_prompt=custom_prompt,
            dry_run=request.dry_run
        )
        
        md_path = os.path.join(folder, f"{video_name}_{request.mode}.md")
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(formatted)
        
        word_path = vomo.save_as_word(formatted, video_name, folder, mode=request.mode)
        
        # Auto-apply fixes if requested
        fixes_result = None
        if request.auto_apply_fixes:
            try:
                from auto_fix_apostilas import analyze_structural_issues, apply_structural_fixes_to_file
                issues = analyze_structural_issues(md_path)
                if issues['total_issues'] > 0:
                    fixes_result = apply_structural_fixes_to_file(md_path, issues)
                    if fixes_result.get("fixes_applied"):
                        with open(md_path, 'r', encoding='utf-8') as f:
                            fixed_content = f.read()
                        word_path = vomo.save_as_word(fixed_content, video_name, folder, mode=request.mode)
            except Exception as e:
                fixes_result = {"error": str(e)}
        
        return {
            "mode": request.mode,
            "md_path": md_path,
            "word_path": word_path,
            "content_preview": formatted[:1000],
            "fixes_applied": fixes_result
        }
        
    except Exception as e:
        logger.error(f"Transcribe advanced error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============= AUDIT WITH RAG/GROUNDING =============

@router.post("/audit-with-rag")
async def audit_with_rag(request: AuditWithRAGRequest, current_user: User = Depends(get_current_user)):
    """
    Full audit with optional RAG grounding.
    Exposes audit_juridico.audit_document_text with RAG manager.
    """
    try:
        from audit_juridico import audit_document_text
        
        # Get RAG manager if requested
        rag_manager = None
        if request.use_rag and request.include_citation_analysis:
            try:
                try:
                    from app.services.rag_module_old import RAGManager
                except ImportError:
                    from rag_module import RAGManager
                rag_manager = RAGManager()
                if request.rag_sources:
                    rag_manager = _ScopedRAGManager(rag_manager, request.rag_sources)
            except ImportError:
                logger.warning("RAG module not available, proceeding without RAG")
        
        # Get Gemini client from audit_service
        client = audit_service._get_client()
        model_name = audit_service._get_model_name()
        if not client:
            raise HTTPException(status_code=503, detail="Audit client not configured")
        
        result = audit_document_text(
            client=client,
            model_name=model_name,
            text=request.text,
            rag_manager=rag_manager
        )
        return result
        
    except ImportError:
        raise HTTPException(status_code=503, detail="audit_juridico not available")
    except Exception as e:
        logger.error(f"Audit with RAG error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/diarization/align")
async def align_diarization(request: DiarizeRequest, current_user: User = Depends(get_current_user)):
    """
    Runs isolated Diarization + Alignment (Pyannote + VomoMLX._align_diarization).
    Requires local audio path (since pyannote needs file) and segments.
    """
    if not os.path.exists(request.audio_path):
        raise HTTPException(status_code=404, detail="Audio file not found on server")
        
    try:
        vomo = transcription_service._get_vomo()
        if not vomo:
             raise HTTPException(status_code=503, detail="VomoMLX unavailable")

        # Dynamic import of pipeline (mimicking mlx_vomo.py)
        try:
            from pyannote.audio import Pipeline
            import torch
            hf_token = os.getenv("HUGGING_FACE_TOKEN")
            if not hf_token:
                 raise HTTPException(status_code=500, detail="HUGGING_FACE_TOKEN not set")
                 
            pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-community-1",
                token=hf_token
            )
            device = "mps" if torch.backends.mps.is_available() else "cpu"
            pipeline.to(torch.device(device))
            
            # Run Diarization
            diarization = pipeline(request.audio_path)
            
            # Align if segments provided
            if request.segments:
                aligned_text = vomo._align_diarization(request.segments, diarization)
                return {"diarization": str(diarization), "aligned_text": aligned_text}
            else:
                # Return raw diarization logic (intervals)
                return {"diarization_raw": [(s.start, s.end, l) for s, _, l in diarization.itertracks(yield_label=True)]}
                
        except ImportError:
             raise HTTPException(status_code=503, detail="pyannote.audio not installed")
             
    except Exception as e:
        logger.error(f"Diarization error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
