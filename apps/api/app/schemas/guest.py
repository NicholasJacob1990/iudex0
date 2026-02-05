"""
Schemas Pydantic para Guest Sessions
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class GuestCreateRequest(BaseModel):
    """Criar sessao guest anonima."""
    display_name: Optional[str] = Field(
        None, min_length=1, max_length=200,
        description="Nome de exibicao do visitante"
    )


class GuestFromShareRequest(BaseModel):
    """Criar sessao guest a partir de link de compartilhamento."""
    display_name: Optional[str] = Field(
        None, min_length=1, max_length=200,
        description="Nome de exibicao do visitante"
    )


class GuestTokenResponse(BaseModel):
    """Resposta com token JWT para guest."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    guest: "GuestSessionResponse"


class GuestSessionResponse(BaseModel):
    """Informacoes da sessao guest."""
    id: str
    display_name: str
    is_guest: bool = True
    expires_at: datetime
    space_id: Optional[str] = None
    permissions: dict = {}
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GuestInfoResponse(BaseModel):
    """Informacoes minimas do guest para /auth/me quando e guest."""
    id: str
    display_name: str
    is_guest: bool = True
    expires_at: datetime
    space_id: Optional[str] = None
    permissions: dict = {}
