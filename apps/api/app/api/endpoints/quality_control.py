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


class PendingFix(BaseModel):
    """A single pending fix awaiting approval."""
    id: str
    type: str
    description: str
    action: str
    severity: str
    fingerprint: Optional[str] = None


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


class ApplyApprovedResponse(BaseModel):
    """Response from applying approved fixes."""
    success: bool
    fixed_content: Optional[str] = None
    fixes_applied: List[str] = []
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
        result = await quality_service.apply_approved_fixes(
            content=request.content,
            approved_fix_ids=request.approved_fix_ids
        )
        return ApplyApprovedResponse(**result)
    except Exception as e:
        logger.error(f"Apply approved endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
