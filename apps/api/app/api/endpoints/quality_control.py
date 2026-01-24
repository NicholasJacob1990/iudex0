"""
Quality Control API Endpoints

Provides validation, fix application, and Word regeneration for documents.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum
from loguru import logger

from app.services.quality_service import quality_service, FixType


router = APIRouter()


# ============================================================================
# SCHEMAS
# ============================================================================

# ----------------------------------------------------------------------------
# HEARING/MEETING SCHEMAS
# ----------------------------------------------------------------------------

class HearingSegment(BaseModel):
    """A segment of a hearing/meeting transcription."""
    id: Optional[str] = None
    text: str
    speaker_id: Optional[str] = None
    speaker_label: Optional[str] = None
    speaker_role: Optional[str] = None  # juiz, advogado, promotor, testemunha, etc.
    start: Optional[float] = None  # timestamp in seconds
    end: Optional[float] = None
    confidence: Optional[float] = None


class Speaker(BaseModel):
    """A speaker in a hearing/meeting."""
    speaker_id: str
    name: Optional[str] = None
    label: Optional[str] = None
    role: Optional[str] = None  # juiz, advogado, promotor, testemunha, etc.
    party: Optional[str] = None  # parte processual


class HearingValidationRequest(BaseModel):
    """Request body for hearing validation."""
    segments: List[HearingSegment] = Field(..., description="Transcription segments")
    speakers: List[Speaker] = Field(default_factory=list, description="Identified speakers")
    formatted_content: Optional[str] = Field(default=None, description="Formatted hearing text")
    raw_content: Optional[str] = Field(default=None, description="Raw transcription")
    document_name: str = Field(default="hearing", description="Name identifier")
    mode: str = Field(default="AUDIENCIA", description="AUDIENCIA, REUNIAO, or DEPOIMENTO")


class HearingIssue(BaseModel):
    """An issue detected in hearing validation."""
    id: str
    type: str  # speaker_inconsistency, timestamp_error, speaker_alignment_error, evidence_gap, contradiction, incomplete_statement
    description: str
    severity: str  # low, medium, high, critical
    segment_id: Optional[str] = None
    speaker_id: Optional[str] = None
    timestamp: Optional[str] = None
    suggestion: Optional[str] = None


class HearingValidationResponse(BaseModel):
    """Response from hearing validation."""
    document_name: str
    validated_at: str
    approved: bool
    score: float
    mode: str

    # Metrics
    completude_rate: float = 0.0  # % of segments without [inaudível]
    speaker_identification_rate: float = 0.0  # % of segments with identified speakers
    evidence_preservation_rate: float = 0.0  # % of evidence preserved
    chronology_valid: bool = True

    # Issues
    issues: List[HearingIssue] = []
    total_issues: int = 0

    # HIL recommendation
    requires_review: bool = False
    review_reason: Optional[str] = None
    critical_areas: List[str] = []

    error: Optional[str] = None


class HearingSegmentAnalysisRequest(BaseModel):
    """Request for segment-by-segment analysis."""
    segments: List[HearingSegment]
    speakers: List[Speaker] = Field(default_factory=list)
    document_name: str = Field(default="hearing")
    include_contradictions: bool = Field(default=True)


class SegmentIssue(BaseModel):
    """An issue in a specific segment."""
    segment_id: str
    type: str
    description: str
    severity: str
    speaker_label: Optional[str] = None
    timestamp_range: Optional[str] = None


class HearingSegmentAnalysisResponse(BaseModel):
    """Response from segment analysis."""
    document_name: str
    analyzed_at: str
    total_segments: int
    segments_with_issues: int
    issues_by_segment: Dict[str, List[SegmentIssue]] = {}
    summary: Dict[str, int] = {}  # Issue type counts


class HearingChecklistRequest(BaseModel):
    """Request for hearing legal checklist."""
    segments: List[HearingSegment]
    speakers: List[Speaker] = Field(default_factory=list)
    formatted_content: Optional[str] = None
    document_name: str = Field(default="hearing")
    include_timeline: bool = Field(default=True)
    group_by_speaker: bool = Field(default=True)


class SpeakerReference(BaseModel):
    """A legal reference attributed to a speaker."""
    identifier: str
    category: str
    timestamp: Optional[str] = None
    segment_id: Optional[str] = None
    context: Optional[str] = None


class HearingChecklistResponse(BaseModel):
    """Response with hearing legal checklist."""
    document_name: str
    total_references: int

    # Grouped by speaker
    by_speaker: Dict[str, List[SpeakerReference]] = {}

    # Grouped by category
    by_category: Dict[str, List[SpeakerReference]] = {}

    # Timeline view
    timeline: List[Dict[str, Any]] = []

    # Markdown output
    checklist_markdown: str = ""


# ----------------------------------------------------------------------------
# APOSTILA SCHEMAS (existing)
# ----------------------------------------------------------------------------

class ValidateRequest(BaseModel):
    """Request body for document validation."""
    raw_content: str = Field(..., description="Original raw transcription text")
    formatted_content: str = Field(..., description="Formatted markdown/apostila text")
    document_name: str = Field(..., description="Name identifier for the document")


class ValidateResponse(BaseModel):
    """Response from validation endpoint."""
    document_name: str
    validated_at: str
    approved: bool
    score: float
    omissions: List[str] = []
    distortions: List[str] = []
    structural_issues: List[str] = []
    observations: str = ""
    error: Optional[str] = None


class ApplyFixRequest(BaseModel):
    """Request body for applying fixes."""
    content: str = Field(..., description="Markdown content to fix")
    fix_type: FixType = Field(default=FixType.STRUCTURAL)
    document_name: Optional[str] = None
    issues: Optional[List[str]] = None  # For semantic fixes


class ApplyFixResponse(BaseModel):
    """Response from fix application."""
    success: bool
    fixed_content: Optional[str] = None
    fixes_applied: List[str] = []
    size_reduction: Optional[str] = None
    suggestions: Optional[str] = None  # For semantic
    error: Optional[str] = None


class RegenerateWordRequest(BaseModel):
    """Request for Word document regeneration."""
    content: str = Field(..., description="Markdown content")
    document_name: str = Field(..., description="Output filename (without extension)")
    output_dir: str = Field(default="/tmp", description="Directory for output")


class RegenerateWordResponse(BaseModel):
    """Response from Word regeneration."""
    success: bool
    output_path: Optional[str] = None
    error: Optional[str] = None


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.post("/validate", response_model=ValidateResponse, summary="Validate Document Quality")
async def validate_document(request: ValidateRequest):
    """
    Validates a formatted document against its raw source.
    Returns a fidelity score (0-10) and lists of issues.
    """
    try:
        result = await quality_service.validate_document(
            raw_content=request.raw_content,
            formatted_content=request.formatted_content,
            document_name=request.document_name
        )
        return ValidateResponse(**result)
    except Exception as e:
        logger.error(f"Validation endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/fix", response_model=ApplyFixResponse, summary="Apply Automated Fixes")
async def apply_fix(request: ApplyFixRequest):
    """
    Applies automated corrections to a document.
    - STRUCTURAL: Merges duplicate sections, removes redundant paragraphs.
    - SEMANTIC: Generates AI suggestions for content issues (requires `issues` list).
    """
    try:
        if request.fix_type == FixType.STRUCTURAL:
            result = await quality_service.apply_structural_fix(request.content)
            return ApplyFixResponse(
                success=result.get("success", False),
                fixed_content=result.get("fixed_content"),
                fixes_applied=result.get("fixes_applied", []),
                size_reduction=result.get("size_reduction"),
                error=result.get("error"),
            )
        elif request.fix_type == FixType.SEMANTIC:
            if not request.issues:
                raise HTTPException(
                    status_code=400,
                    detail="Semantic fix requires 'issues' list in request body"
                )
            result = await quality_service.generate_semantic_suggestions(
                document_name=request.document_name or "document",
                issues=request.issues
            )
            return ApplyFixResponse(
                success=result.get("has_suggestions", False),
                suggestions=result.get("suggestions"),
                error=result.get("error"),
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Fix endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/regenerate-word", response_model=RegenerateWordResponse, summary="Regenerate Word Document")
async def regenerate_word(request: RegenerateWordRequest):
    """
    Regenerates a Word document from markdown content.
    Uses professional formatting with tables and styling.
    """
    try:
        result = await quality_service.regenerate_word_document(
            content=request.content,
            document_name=request.document_name,
            output_dir=request.output_dir
        )
        return RegenerateWordResponse(**result)
    except Exception as e:
        logger.error(f"Word regeneration error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health", summary="Quality Service Health Check")
async def health_check():
    """
    Checks if the quality service dependencies are available.
    """
    return {
        "status": "ok",
        "service": "quality_control",
        "mlx_available": quality_service._vomo is not None or True,
    }


# ============================================================================
# HIL (Human-in-the-Loop) ENDPOINTS
# ============================================================================

class AnalyzeRequest(BaseModel):
    """Request for structural analysis (HIL mode)."""
    content: str = Field(..., description="Markdown content to analyze")
    document_name: str = Field(default="document")


class HilPatch(BaseModel):
    """Patch data for semantic fixes (INSERT/REPLACE)."""
    anchor_text: Optional[str] = None  # Text to locate insertion point
    old_text: Optional[str] = None     # For REPLACE: text to find
    new_text: Optional[str] = None     # Content to insert/replace with


class PendingFix(BaseModel):
    """A single pending fix awaiting approval (unified HIL)."""
    id: str
    type: str  # duplicate_paragraph, duplicate_section, heading_numbering, omission, distortion
    description: str
    action: str  # REMOVE, MERGE, RENUMBER, INSERT, REPLACE
    severity: str  # low, medium, high
    source: Optional[str] = None  # structural_audit, fidelity_audit, preventive_audit

    # Structural fixes
    fingerprint: Optional[str] = None
    title: Optional[str] = None

    # Semantic fixes
    patch: Optional[HilPatch] = None
    evidence: Optional[List[str]] = None  # Raw content snippets supporting the fix


class AnalyzeResponse(BaseModel):
    """Response from HIL analysis."""
    document_name: str
    analyzed_at: str
    total_issues: int
    pending_fixes: List[PendingFix]
    requires_approval: bool
    error: Optional[str] = None


class ApplyApprovedRequest(BaseModel):
    """Request to apply user-approved fixes."""
    content: str = Field(..., description="Original content")
    approved_fix_ids: List[str] = Field(..., description="List of fix IDs to apply")
    approved_fixes: Optional[List[Dict[str, Any]]] = Field(default=None, description="Optional fix objects")


class ApplyApprovedResponse(BaseModel):
    """Response from applying approved fixes."""
    success: bool
    fixed_content: Optional[str] = None
    fixes_applied: List[str] = []
    size_reduction: Optional[str] = None
    error: Optional[str] = None


class ConvertToHilRequest(BaseModel):
    """Request to convert validation/audit results to unified HIL issues."""
    raw_content: str = Field(..., description="Original raw transcription")
    formatted_content: str = Field(..., description="Current formatted content")
    document_name: str = Field(default="document")

    # From fidelity validation
    omissions: Optional[List[str]] = Field(default=None, description="List of omission descriptions")
    distortions: Optional[List[str]] = Field(default=None, description="List of distortion descriptions")

    # From structural analysis (optional - can also run internally)
    include_structural: bool = Field(default=True, description="Also run structural analysis")

    # Model for generating patches
    model_selection: Optional[str] = Field(default=None, description="Model for generating semantic patches")


class CompressionAnalysis(BaseModel):
    """Analysis of content compression ratio."""
    ratio: float
    adjusted_ratio: Optional[float] = None
    status: str  # ok, warning, critical
    is_intentional_summarization: bool = False
    metadata_removed_count: int = 0
    notes: List[str] = []


class ConvertToHilResponse(BaseModel):
    """Response with unified HIL issues."""
    document_name: str
    converted_at: str
    total_issues: int
    hil_issues: List[PendingFix]
    structural_count: int = 0
    semantic_count: int = 0
    requires_approval: bool
    filtered_false_positives: int = 0  # Issues filtered due to low confidence
    compression_analysis: Optional[CompressionAnalysis] = None
    error: Optional[str] = None


class ApplyUnifiedHilRequest(BaseModel):
    """Request to apply unified HIL fixes (structural + semantic)."""
    content: str = Field(..., description="Current formatted content")
    raw_content: Optional[str] = Field(default=None, description="Raw content for semantic fixes")
    approved_fixes: List[Dict[str, Any]] = Field(..., description="List of approved fix objects")
    model_selection: Optional[str] = Field(default=None, description="Model for semantic patches")


class ApplyUnifiedHilResponse(BaseModel):
    """Response from applying unified HIL fixes."""
    success: bool
    fixed_content: Optional[str] = None
    fixes_applied: List[str] = []
    skipped_fixes: List[str] = []  # Fixes skipped due to validation failures
    structural_applied: int = 0
    semantic_applied: int = 0
    size_reduction: Optional[str] = None
    error: Optional[str] = None


@router.post("/analyze", response_model=AnalyzeResponse, summary="Analyze Document (HIL)")
async def analyze_document(request: AnalyzeRequest):
    """
    Analyzes a document for structural issues WITHOUT applying fixes.
    Returns a list of pending fixes for user approval.
    
    This is the first step of the Human-in-the-Loop flow.
    """
    try:
        result = await quality_service.analyze_structural_issues(
            content=request.content,
            document_name=request.document_name
        )
        return AnalyzeResponse(**result)
    except Exception as e:
        logger.error(f"Analysis endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/apply-approved", response_model=ApplyApprovedResponse, summary="Apply Approved Fixes (HIL)")
async def apply_approved_fixes(request: ApplyApprovedRequest):
    """
    Applies only the user-approved fixes to the content.
    
    This is the second step of the Human-in-the-Loop flow.
    User reviews pending_fixes from /analyze and selects which to apply.
    """
    try:
        logger.info(
            "📥 Apply approved request: "
            f"fix_ids_count={len(request.approved_fix_ids)}, "
            f"fixes_count={len(request.approved_fixes) if request.approved_fixes else 0}"
        )
        
        result = await quality_service.apply_approved_fixes(
            content=request.content,
            approved_fix_ids=request.approved_fix_ids,
            approved_fixes=request.approved_fixes
        )
        logger.info(
            "📤 Apply approved result: "
            f"success={result.get('success')}, "
            f"fixes_applied_count={len(result.get('fixes_applied', []))}"
        )
        return ApplyApprovedResponse(**result)
    except Exception as e:
        logger.error(f"Apply approved endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# UNIFIED HIL ENDPOINTS (Structural + Semantic)
# ============================================================================

@router.post("/convert-to-hil", response_model=ConvertToHilResponse, summary="Convert to Unified HIL Issues")
async def convert_to_hil(request: ConvertToHilRequest):
    """
    Converts validation results (omissions, distortions) and structural issues
    into a unified list of HIL issues with patches for review.

    This endpoint:
    1. Optionally runs structural analysis (duplicates, numbering)
    2. Converts omissions/distortions into semantic HIL issues
    3. Uses AI to generate patches for semantic issues
    4. Returns unified HilIssue[] for review

    The user can then select which issues to fix and call /apply-unified-hil.
    """
    try:
        result = await quality_service.convert_to_hil_issues(
            raw_content=request.raw_content,
            formatted_content=request.formatted_content,
            document_name=request.document_name,
            omissions=request.omissions or [],
            distortions=request.distortions or [],
            include_structural=request.include_structural,
            model_selection=request.model_selection,
        )
        return ConvertToHilResponse(**result)
    except Exception as e:
        logger.error(f"Convert to HIL endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/apply-unified-hil", response_model=ApplyUnifiedHilResponse, summary="Apply Unified HIL Fixes")
async def apply_unified_hil(request: ApplyUnifiedHilRequest):
    """
    Applies unified HIL fixes to the content.

    Handles both:
    - Structural fixes (deterministic): REMOVE, MERGE, RENUMBER
    - Semantic fixes (AI patches): INSERT, REPLACE

    This is the second step of the unified HIL flow.
    """
    try:
        logger.info(
            "📥 Apply unified HIL request: "
            f"fixes_count={len(request.approved_fixes)}"
        )

        result = await quality_service.apply_unified_hil_fixes(
            content=request.content,
            raw_content=request.raw_content,
            approved_fixes=request.approved_fixes,
            model_selection=request.model_selection,
        )

        logger.info(
            "📤 Apply unified HIL result: "
            f"success={result.get('success')}, "
            f"structural={result.get('structural_applied', 0)}, "
            f"semantic={result.get('semantic_applied', 0)}"
        )
        return ApplyUnifiedHilResponse(**result)
    except Exception as e:
        logger.error(f"Apply unified HIL endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# LEGAL CHECKLIST ENDPOINTS
# ============================================================================

class GenerateChecklistRequest(BaseModel):
    """Request to generate legal checklist."""
    content: str = Field(..., description="Document content to analyze")
    document_name: str = Field(default="document")
    include_counts: bool = Field(default=True, description="Include reference counts")
    append_to_content: bool = Field(default=True, description="Append checklist to content")


class LegalReferenceItem(BaseModel):
    """A single legal reference."""
    identifier: str
    category: str
    number: str
    count: int = 1


class GenerateChecklistResponse(BaseModel):
    """Response with legal checklist."""
    document_name: str
    total_references: int
    checklist_markdown: str
    content_with_checklist: Optional[str] = None

    # Breakdown by category
    controle_concentrado: List[LegalReferenceItem] = []
    sumulas_vinculantes: List[LegalReferenceItem] = []
    sumulas_stf: List[LegalReferenceItem] = []
    sumulas_stj: List[LegalReferenceItem] = []
    recursos_repetitivos: List[LegalReferenceItem] = []
    temas_repetitivos: List[LegalReferenceItem] = []
    iac: List[LegalReferenceItem] = []
    irdr: List[LegalReferenceItem] = []
    constituicao: List[LegalReferenceItem] = []
    leis_federais: List[LegalReferenceItem] = []
    codigos: List[LegalReferenceItem] = []


@router.post("/generate-checklist", response_model=GenerateChecklistResponse, summary="Generate Legal Checklist")
async def generate_legal_checklist(request: GenerateChecklistRequest):
    """
    Extracts legal references from document content and generates a checklist.

    Based on Art. 927 CPC - Binding Precedents:
    - Decisions in concentrated constitutional control (ADI, ADC, ADPF)
    - Binding summaries (STF)
    - IAC rulings (Incident of Assumption of Competence)
    - IRDR rulings (Incident of Resolution of Repetitive Demands)
    - Repetitive extraordinary and special appeals (STF/STJ)
    - STF summaries (constitutional matter) and STJ (infraconstitutional)

    Also extracts:
    - Constitutional articles
    - Federal laws, complementary laws, decrees
    - Legal codes (CC, CPC, CP, etc.)
    """
    from app.services.legal_checklist_generator import legal_checklist_generator

    try:
        logger.info(f"📋 Generating legal checklist for: {request.document_name}")

        # Extract references
        checklist = legal_checklist_generator.extract_references(
            content=request.content,
            document_name=request.document_name,
        )

        # Generate markdown
        checklist_markdown = legal_checklist_generator.generate_markdown_checklist(
            checklist=checklist,
            include_counts=request.include_counts,
        )

        # Optionally append to content
        content_with_checklist = None
        if request.append_to_content:
            content_with_checklist = request.content + "\n\n" + checklist_markdown

        # Convert to response format
        def refs_to_items(refs):
            return [
                LegalReferenceItem(
                    identifier=r.identifier,
                    category=r.category.value,
                    number=r.number,
                    count=r.count,
                )
                for r in refs
            ]

        return GenerateChecklistResponse(
            document_name=request.document_name,
            total_references=checklist.total_references,
            checklist_markdown=checklist_markdown,
            content_with_checklist=content_with_checklist,
            controle_concentrado=refs_to_items(checklist.controle_concentrado),
            sumulas_vinculantes=refs_to_items(checklist.sumulas_vinculantes),
            sumulas_stf=refs_to_items(checklist.sumulas_stf),
            sumulas_stj=refs_to_items(checklist.sumulas_stj),
            recursos_repetitivos=refs_to_items(checklist.recursos_repetitivos),
            temas_repetitivos=refs_to_items(checklist.temas_repetitivos),
            iac=refs_to_items(checklist.iac),
            irdr=refs_to_items(checklist.irdr),
            constituicao=refs_to_items(checklist.constituicao),
            leis_federais=refs_to_items(checklist.leis_federais),
            codigos=refs_to_items(checklist.codigos),
        )

    except Exception as e:
        logger.error(f"Generate checklist error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# HEARING/MEETING QUALITY ENDPOINTS
# ============================================================================

@router.post("/validate-hearing", response_model=HearingValidationResponse, summary="Validate Hearing Quality")
async def validate_hearing(request: HearingValidationRequest):
    """
    Validates a hearing/meeting transcription.

    Checks:
    - Completude de falas (% without [inaudível])
    - Identificação de falantes (% with identified speakers)
    - Preservação de evidências (claims preservation)
    - Coerência cronológica (timestamp order)
    - Detecção de contradições

    Returns a fidelity score (0-10) and list of issues.
    """
    try:
        logger.info(f"🔍 Validating hearing: {request.document_name}")

        result = await quality_service.validate_hearing_segments(
            segments=[s.model_dump() for s in request.segments],
            speakers=[s.model_dump() for s in request.speakers],
            formatted_content=request.formatted_content or "",
            raw_content=request.raw_content or "",
            document_name=request.document_name,
            mode=request.mode,
        )

        return HearingValidationResponse(**result)

    except Exception as e:
        logger.error(f"Hearing validation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze-hearing-segments", response_model=HearingSegmentAnalysisResponse, summary="Analyze Hearing Segments")
async def analyze_hearing_segments(request: HearingSegmentAnalysisRequest):
    """
    Analyzes hearing segments for specific issues.

    Returns issues grouped by segment for detailed HIL review.
    """
    try:
        logger.info(f"🔬 Analyzing hearing segments: {request.document_name}")

        result = await quality_service.analyze_hearing_segment_issues(
            segments=[s.model_dump() for s in request.segments],
            speakers=[s.model_dump() for s in request.speakers],
            document_name=request.document_name,
            include_contradictions=request.include_contradictions,
        )

        return HearingSegmentAnalysisResponse(**result)

    except Exception as e:
        logger.error(f"Hearing segment analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate-hearing-checklist", response_model=HearingChecklistResponse, summary="Generate Hearing Legal Checklist")
async def generate_hearing_checklist(request: HearingChecklistRequest):
    """
    Generates a legal checklist for hearings with speaker attribution.

    Groups legal references by:
    - Speaker (Juiz, Advogado, Promotor, Testemunha, etc.)
    - Category (legislação, jurisprudência, etc.)
    - Timeline (when each reference was mentioned)
    """
    from app.services.legal_checklist_generator import legal_checklist_generator

    try:
        logger.info(f"📋 Generating hearing checklist: {request.document_name}")

        result = legal_checklist_generator.generate_hearing_checklist(
            segments=[s.model_dump() for s in request.segments],
            speakers=[s.model_dump() for s in request.speakers],
            formatted_content=request.formatted_content,
            document_name=request.document_name,
            include_timeline=request.include_timeline,
            group_by_speaker=request.group_by_speaker,
        )

        return HearingChecklistResponse(**result)

    except Exception as e:
        logger.error(f"Hearing checklist generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
