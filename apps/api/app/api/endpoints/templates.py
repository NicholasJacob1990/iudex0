from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Body, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from app.core.security import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.models.library import LibraryItem, LibraryItemType
from app.services.template_service import template_service
from app.utils.token_counter import estimate_tokens
from loguru import logger
import shutil
import os
import uuid
from pathlib import Path
from app.core.config import settings
from app.schemas.smart_template import SmartTemplate, TemplateRenderInput, UserTemplateV1
from app.services.legal_templates import legal_template_library
from app.services.ai.nodes.catalogo_documentos import (
    list_doc_kinds,
    get_template,
    template_spec_to_dict,
)
from app.services.ai.template_generator import generate_user_template_from_description
import json

router = APIRouter()


class TemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    content_template: Optional[str] = None
    document_type: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class TemplateUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    content_template: Optional[str] = None
    document_type: Optional[str] = None
    tags: Optional[List[str]] = None


class TemplateDuplicate(BaseModel):
    name: Optional[str] = None


class LegalTemplateImport(BaseModel):
    name: Optional[str] = None


class CatalogValidateRequest(BaseModel):
    template: Dict[str, Any]


class CatalogParseRequest(BaseModel):
    description: str
    doc_kind: Optional[str] = None
    doc_subtype: Optional[str] = None
    model_id: Optional[str] = None


def _extract_doc_type(tags: List[str]) -> Optional[str]:
    for tag in tags or []:
        if tag.startswith("doc_type:"):
            return tag.split(":", 1)[1]
    return None


@router.get("/", response_model=dict)
async def list_templates(
    skip: int = 0,
    limit: int = 50,
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    query = select(LibraryItem).where(
        LibraryItem.user_id == current_user.id,
        LibraryItem.type == LibraryItemType.MODEL
    )
    if search:
        query = query.where(LibraryItem.name.ilike(f"%{search}%"))

    result = await db.execute(query.offset(skip).limit(limit))
    items = result.scalars().all()

    templates = [
        {
            "id": item.id,
            "name": item.name,
            "title": item.name,
            "description": item.description,
            "document_type": _extract_doc_type(item.tags),
            "tags": item.tags,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }
        for item in items
    ]
    return {"templates": templates, "total": len(templates)}


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=dict)
async def create_template(
    payload: TemplateCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    content = payload.description or payload.content_template
    if not content:
        raise HTTPException(status_code=400, detail="Descrição do template é obrigatória")

    tags = list(payload.tags or [])
    if payload.document_type:
        tags = [t for t in tags if not t.startswith("doc_type:")]
        tags.append(f"doc_type:{payload.document_type}")

    item = LibraryItem(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        type=LibraryItemType.MODEL,
        name=payload.name,
        description=content,
        tags=tags,
        folder_id=None,
        resource_id=str(uuid.uuid4()),
        token_count=estimate_tokens(content)
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)

    return {
        "id": item.id,
        "name": item.name,
        "title": item.name,
        "description": item.description,
        "document_type": _extract_doc_type(item.tags),
        "tags": item.tags,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


@router.put("/{template_id}", response_model=dict)
async def update_template(
    template_id: str,
    payload: TemplateUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(LibraryItem).where(
            LibraryItem.id == template_id,
            LibraryItem.user_id == current_user.id,
            LibraryItem.type == LibraryItemType.MODEL
        )
    )
    item = result.scalars().first()
    if not item:
        raise HTTPException(status_code=404, detail="Template não encontrado")

    content = payload.description if payload.description is not None else payload.content_template
    if content is not None:
        item.description = content
        item.token_count = estimate_tokens(content)

    if payload.name:
        item.name = payload.name

    if payload.tags is not None:
        tags = list(payload.tags or [])
        if payload.document_type:
            tags = [t for t in tags if not t.startswith("doc_type:")]
            tags.append(f"doc_type:{payload.document_type}")
        item.tags = tags
    elif payload.document_type:
        tags = list(item.tags or [])
        tags = [t for t in tags if not t.startswith("doc_type:")]
        tags.append(f"doc_type:{payload.document_type}")
        item.tags = tags

    db.add(item)
    await db.commit()
    await db.refresh(item)

    return {
        "id": item.id,
        "name": item.name,
        "title": item.name,
        "description": item.description,
        "document_type": _extract_doc_type(item.tags),
        "tags": item.tags,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


@router.post("/{template_id}/duplicate", status_code=status.HTTP_201_CREATED, response_model=dict)
async def duplicate_template(
    template_id: str,
    payload: TemplateDuplicate = Body(default=TemplateDuplicate()),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(LibraryItem).where(
            LibraryItem.id == template_id,
            LibraryItem.user_id == current_user.id,
            LibraryItem.type == LibraryItemType.MODEL
        )
    )
    item = result.scalars().first()
    if not item:
        raise HTTPException(status_code=404, detail="Template não encontrado")

    base_name = item.name or "Template"
    new_name = (payload.name or "").strip() or f"{base_name} (copia)"
    new_item = LibraryItem(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        type=LibraryItemType.MODEL,
        name=new_name,
        description=item.description,
        tags=list(item.tags or []),
        folder_id=item.folder_id,
        resource_id=str(uuid.uuid4()),
        token_count=item.token_count
    )
    db.add(new_item)
    await db.commit()
    await db.refresh(new_item)

    return {
        "id": new_item.id,
        "name": new_item.name,
        "title": new_item.name,
        "description": new_item.description,
        "document_type": _extract_doc_type(new_item.tags),
        "tags": new_item.tags,
        "created_at": new_item.created_at,
        "updated_at": new_item.updated_at,
    }


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(LibraryItem).where(
            LibraryItem.id == template_id,
            LibraryItem.user_id == current_user.id,
            LibraryItem.type == LibraryItemType.MODEL
        )
    )
    item = result.scalars().first()
    if not item:
        raise HTTPException(status_code=404, detail="Template não encontrado")
    await db.delete(item)
    await db.commit()
    return {}

@router.post("/extract-variables")
async def extract_template_variables(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    """
    Extrai variáveis de um arquivo DOCX template
    """
    temp_path = Path(settings.LOCAL_STORAGE_PATH) / "temp" / f"temp_{uuid.uuid4()}.docx"
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        variables = await template_service.extract_variables(str(temp_path))
        
        return {
            "filename": file.filename,
            "variables": variables,
            "count": len(variables)
        }
        
    except Exception as e:
        logger.error(f"Erro ao extrair variáveis: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if temp_path.exists():
            os.remove(temp_path)

@router.post("/apply")
async def apply_template(
    file: UploadFile = File(...),
    variables: str = Form(...),  # JSON string
    current_user: User = Depends(get_current_user)
):
    """
    Aplica variáveis em um template DOCX e retorna o arquivo gerado
    """
    import json
    
    temp_path = Path(settings.LOCAL_STORAGE_PATH) / "temp" / f"temp_{uuid.uuid4()}.docx"
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        # Salvar arquivo temporário
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # Parse variáveis
        try:
            vars_dict = json.loads(variables)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Variáveis inválidas (JSON esperado)")
            
        # Aplicar template
        result = await template_service.apply_template(
            template_path=str(temp_path),
            variables=vars_dict
        )
        
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result["error"])
            
        # Retornar informações do arquivo gerado
        return {
            "success": True,
            "generated_file": result["filename"],
            "download_url": f"/api/documents/download/generated/{result['filename']}",
            "replacements": result["replacements"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao aplicar template: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if temp_path.exists():
            os.remove(temp_path)


@router.get("/{template_id}", response_model=dict)
async def get_template(
    template_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(LibraryItem).where(
            LibraryItem.id == template_id,
            LibraryItem.user_id == current_user.id,
            LibraryItem.type == LibraryItemType.MODEL
        )
    )
    item = result.scalars().first()
    if not item:
        raise HTTPException(status_code=404, detail="Template não encontrado")

    return {
        "id": item.id,
        "name": item.name,
        "title": item.name,
        "description": item.description,
        "document_type": _extract_doc_type(item.tags),
        "tags": item.tags,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }

@router.get("/{template_id}/schema", response_model=SmartTemplate)
async def get_template_schema(
    template_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Retorna o schema (blocos) de um Smart Template.
    """
    result = await db.execute(
        select(LibraryItem).where(
            LibraryItem.id == template_id,
            LibraryItem.user_id == current_user.id
        )
    )
    item = result.scalars().first()
    if not item:
        raise HTTPException(status_code=404, detail="Template não encontrado")

    # Verifica se é um Smart Template via tags ou heurística
    is_smart = False
    for tag in item.tags or []:
        if "smart_template" in tag:
            is_smart = True
            break
            
    if not is_smart:
        # Se não for marcado, tenta fazer parse mesmo assim se parecer JSON
        if item.description and item.description.strip().startswith("{"):
            try:
                data = json.loads(item.description)
                if "blocks" in data:
                    is_smart = True
            except:
                pass

    if not is_smart:
         raise HTTPException(status_code=400, detail="Este não é um Smart Template válido.")

    try:
        data = json.loads(item.description)
        # Ensure ID match
        data["id"] = item.id
        return SmartTemplate(**data)
    except Exception as e:
        logger.error(f"Erro ao fazer parse do Smart Template {template_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erro de formato no template: {str(e)}")


@router.get("/catalog/types", response_model=dict)
async def list_catalog_types():
    """Lista doc_kind e doc_subtype disponiveis no catalogo base."""
    types = list_doc_kinds()
    return {"types": types, "total": sum(len(v) for v in types.values())}


@router.get("/catalog/defaults/{doc_kind}/{doc_subtype}", response_model=dict)
async def get_catalog_defaults(doc_kind: str, doc_subtype: str):
    """Retorna o template base do catalogo para doc_kind/doc_subtype."""
    spec = get_template(doc_kind, doc_subtype)
    if not spec:
        raise HTTPException(status_code=404, detail="Template base nao encontrado")
    return {"template": template_spec_to_dict(spec)}


@router.post("/catalog/validate", response_model=dict)
async def validate_catalog_template(payload: CatalogValidateRequest):
    """Valida JSON do UserTemplateV1."""
    try:
        parsed = UserTemplateV1.model_validate(payload.template)
        return {"valid": True, "template": parsed.model_dump()}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Template invalido: {e}")


@router.post("/catalog/parse", response_model=dict)
async def parse_catalog_template(payload: CatalogParseRequest):
    """Gera UserTemplateV1 a partir de descricao em linguagem simples."""
    try:
        parsed = await generate_user_template_from_description(
            description=payload.description,
            doc_kind=payload.doc_kind,
            doc_subtype=payload.doc_subtype,
            model_id=payload.model_id,
        )
        return {"template": parsed}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/preview", response_model=dict)
async def preview_smart_template(
    payload: TemplateRenderInput,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Gera um preview do Smart Template com os inputs fornecidos.
    """
    # 1. Carregar Template do Banco
    result = await db.execute(
        select(LibraryItem).where(
            LibraryItem.id == payload.template_id,
            LibraryItem.user_id == current_user.id
        )
    )
    item = result.scalars().first()
    if not item:
        raise HTTPException(status_code=404, detail="Template não encontrado")
        
    try:
        template_data = json.loads(item.description)
        template_data["id"] = item.id
        smart_template = SmartTemplate(**template_data)
        
        # 2. Montar Documento
        rendered_content = template_service.assemble_smart_template(smart_template, payload)
        
        return {
            "content": rendered_content,
            "success": True
        }
        
    except Exception as e:
        logger.error(f"Erro ao gerar preview do template {payload.template_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# LEGAL TEMPLATES (Biblioteca Pré-definida)
# ============================================================================

@router.get("/legal/", response_model=dict)
async def list_legal_templates(
    document_type: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """
    Lista todos os templates jurídicos pré-definidos da biblioteca.
    """
    from app.services.legal_templates import DocumentType
    
    doc_type_filter = None
    if document_type:
        try:
            doc_type_filter = DocumentType(document_type.lower())
        except ValueError:
            pass  # Ignora filtro inválido
    
    templates = legal_template_library.list_templates(document_type=doc_type_filter)
    
    return {
        "templates": [
            {
                "id": t.id,
                "name": t.name,
                "document_type": t.document_type.value,
                "description": t.description,
                "variables_count": len(t.variables),
                "required_variables": t.get_required_variables(),
                "is_predefined": True,
            }
            for t in templates
        ],
        "total": len(templates)
    }


@router.get("/legal/{template_id}", response_model=dict)
async def get_legal_template(
    template_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Obtém detalhes de um template jurídico pré-definido específico.
    """
    template = legal_template_library.get_template(template_id)
    
    if not template:
        raise HTTPException(status_code=404, detail=f"Template legal '{template_id}' não encontrado")
    
    return {
        "id": template.id,
        "name": template.name,
        "document_type": template.document_type.value,
        "description": template.description,
        "structure": template.structure,
        "instructions": template.instructions,
        "example": template.example,
        "variables": [
            {
                "name": v.name,
                "description": v.description,
                "required": v.required,
                "type": v.type,
                "default": v.default,
            }
            for v in template.variables
        ],
        "is_predefined": True,
    }


@router.get("/legal/{template_id}/schema", response_model=dict)
async def get_legal_template_schema(
    template_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Retorna as variáveis/campos de um template legal pré-definido.
    Útil para gerar formulários dinâmicos no frontend.
    """
    try:
        info = legal_template_library.get_template_info(template_id)
        return info
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/legal/{template_id}/render", response_model=dict)
async def render_legal_template(
    template_id: str,
    variables: Dict[str, Any] = Body(...),
    validate: bool = True,
    current_user: User = Depends(get_current_user)
):
    """
    Renderiza um template legal pré-definido com as variáveis fornecidas.
    """
    try:
        rendered = legal_template_library.render_template(
            template_id=template_id,
            variables=variables,
            validate=validate
        )
        return {
            "content": rendered,
            "template_id": template_id,
            "success": True,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _convert_single_to_double_braces(text: str) -> str:
    """
    Converte placeholders {variavel} para {{variavel}}.
    Ignora {0}, {1} etc (índices numéricos).
    """
    import re
    # Match {word} mas não {{word}} nem {0}
    pattern = r'(?<!\{)\{([a-zA-Z_][a-zA-Z0-9_]*)\}(?!\})'
    return re.sub(pattern, r'{{\1}}', text)


def _generate_frontmatter(template) -> str:
    """
    Gera frontmatter IUDX_TEMPLATE_V1 a partir de um LegalTemplate.
    """
    variables_schema = {}
    for v in template.variables:
        variables_schema[v.name] = {
            "type": v.type or "string",
            "label": v.description,
            "required": v.required,
        }
        if v.default:
            variables_schema[v.name]["default"] = v.default
    
    meta = {
        "id": template.id,
        "version": "1.0.0",
        "document_type": template.document_type.value,
        "system_instructions": template.instructions or "",
        "variables_schema": variables_schema,
        "blocks": [],  # Templates legados não usam blocos
        "output_mode": "text",
        "imported_from": "legal_template_library",
    }
    
    meta_json = json.dumps(meta, indent=2, ensure_ascii=False)
    return f"<!-- IUDX_TEMPLATE_V1\n{meta_json}\n-->"


@router.post("/legal/{template_id}/import", status_code=status.HTTP_201_CREATED, response_model=dict)
async def import_legal_template(
    template_id: str,
    payload: LegalTemplateImport = Body(default=LegalTemplateImport()),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Importa um template legal pré-definido para a biblioteca do usuário.
    
    - Converte placeholders `{variavel}` para `{{variavel}}`
    - Gera frontmatter IUDX_TEMPLATE_V1 com variables_schema
    - Cria LibraryItem do tipo MODEL para o usuário
    """
    name = (payload.name or "").strip() or None

    # 1. Buscar template na biblioteca
    template = legal_template_library.get_template(template_id)
    if not template:
        raise HTTPException(
            status_code=404, 
            detail=f"Template legal '{template_id}' não encontrado"
        )
    
    # 2. Verificar se já foi importado (evitar duplicados)
    check_result = await db.execute(
        select(LibraryItem).where(
            LibraryItem.user_id == current_user.id,
            LibraryItem.type == LibraryItemType.MODEL,
            LibraryItem.name == (name or template.name)
        )
    )
    existing = check_result.scalars().first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Já existe um template com o nome '{name or template.name}'. Escolha outro nome."
        )
    
    # 3. Converter placeholders {var} → {{var}}
    converted_structure = _convert_single_to_double_braces(template.structure)
    
    # 4. Gerar frontmatter
    frontmatter = _generate_frontmatter(template)
    
    # 5. Montar description completa
    full_description = f"{frontmatter}\n\n{converted_structure}"
    
    # 6. Criar LibraryItem
    item = LibraryItem(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        type=LibraryItemType.MODEL,
        name=name or template.name,
        description=full_description,
        tags=[
            f"doc_type:{template.document_type.value}",
            "imported:legal_template_library",
            f"source:{template_id}",
        ],
        folder_id=None,
        resource_id=str(uuid.uuid4()),
        token_count=estimate_tokens(full_description)
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    
    logger.info(f"Template legal '{template_id}' importado como '{item.name}' para usuário {current_user.id}")
    
    return {
        "id": item.id,
        "name": item.name,
        "original_template_id": template_id,
        "document_type": template.document_type.value,
        "variables_count": len(template.variables),
        "success": True,
        "message": f"Template '{template.name}' importado com sucesso!",
    }
