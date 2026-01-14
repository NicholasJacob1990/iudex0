from enum import Enum
from typing import List, Optional, Any, Dict
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
