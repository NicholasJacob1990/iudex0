"""
Endpoints de templates de documentos
"""

from fastapi import APIRouter, HTTPException, status
from loguru import logger

from app.services.document_templates import DocumentTemplates

router = APIRouter()


@router.get("/")
async def list_templates():
    """
    Listar todos os templates de documentos disponíveis
    """
    try:
        templates = DocumentTemplates.list_all_templates()
        return {
            "templates": templates,
            "total": len(templates)
        }
    except Exception as e:
        logger.error(f"Erro ao listar templates: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao listar templates: {str(e)}"
        )


@router.get("/{template_id}")
async def get_template(template_id: str):
    """
    Obter template específico por ID
    """
    try:
        template = DocumentTemplates.get_template_by_id(template_id)
        
        if not template:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Template não encontrado"
            )
        
        return template
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao buscar template: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao buscar template: {str(e)}"
        )

