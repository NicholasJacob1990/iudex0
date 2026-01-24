from enum import Enum
from typing import List, Optional, Any, Dict, Literal
from pydantic import BaseModel, Field

class BlockType(str, Enum):
    FIXED = "fixed"       # Immutable system text
    VARIABLE = "variable" # User input fields
    AI = "ai"             # AI-generated content
    CLAUSE = "clause"     # Reference to a Clause Library item

class TemplateBlock(BaseModel):
    id: str = Field(..., description="Unique ID of the block")
    type: BlockType
    title: str = Field(..., description="Human readable title for the block")
    
    # Content/Configuration
    content: Optional[str] = Field(None, description="Static text for FIXED blocks or default text")
    prompt: Optional[str] = Field(None, description="Prompt for AI blocks")
    variable_name: Optional[str] = Field(None, description="Variable identifier for VARIABLE blocks")
    
    # Permissions
    lockable: bool = Field(False, description="Whether the user can lock this block")
    locked: bool = Field(False, description="Whether the block is currently locked")
    user_can_edit: bool = Field(True, description="Whether the user can manually edit the text")
    
    # Logic
    condition: Optional[str] = Field(None, description="Condition to include this block (e.g., 'is_pj == true')")
    depends_on: Optional[List[str]] = Field(None, description="List of block IDs this block depends on")

class SmartTemplate(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    blocks: List[TemplateBlock]
    version: str = "1.0.0"
    tags: List[str] = Field(default_factory=list)

class TemplateRenderInput(BaseModel):
    template_id: str
    variables: Dict[str, Any] = Field(default_factory=dict)
    locked_blocks: Dict[str, bool] = Field(default_factory=dict) # block_id -> is_locked
    overrides: Dict[str, str] = Field(default_factory=dict)      # block_id -> manual text content


class UserTemplateFormat(BaseModel):
    numbering: Literal["ROMAN", "ARABIC", "CLAUSE", "NONE"] = "ROMAN"
    tone: Literal["very_formal", "formal", "neutral", "executive"] = "formal"
    verbosity: Literal["short", "medium", "long"] = "medium"
    voice: Literal["first_person", "third_person", "impersonal"] = "third_person"


class UserTemplateSection(BaseModel):
    title: str
    required: bool = True
    notes: Optional[str] = None


class UserTemplateField(BaseModel):
    name: str
    type: Literal["text", "number", "date", "list", "id", "reference"] = "text"
    required: bool = True
    on_missing: Literal["block", "mark_pending"] = "block"


class UserTemplateChecklistItem(BaseModel):
    id: str
    level: Literal["required", "recommended", "conditional", "forbidden"] = "required"
    rule: Literal["has_section", "has_field", "mentions_any", "forbidden_phrase_any"] = "has_section"
    value: Any
    condition: Literal["none", "if_tutela", "if_personal_data", "if_appeal"] = "none"
    note: Optional[str] = None


class UserTemplateV1(BaseModel):
    version: int = 1
    name: str
    doc_kind: str
    doc_subtype: str
    format: UserTemplateFormat = Field(default_factory=UserTemplateFormat)
    sections: List[UserTemplateSection] = Field(default_factory=list)
    required_fields: List[UserTemplateField] = Field(default_factory=list)
    checklist: List[UserTemplateChecklistItem] = Field(default_factory=list)
