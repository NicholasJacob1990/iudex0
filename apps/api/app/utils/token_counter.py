"""
Utilitário para cálculo de tokens
Reutiliza lógica de DocumentChunk
"""

from typing import Optional


def estimate_tokens(text: str) -> int:
    """
    Estima número de tokens baseado no comprimento do texto.
    Aproximação: 1 token ≈ 4 caracteres
    
    Esta é a mesma lógica usada em DocumentChunk.token_count
    para garantir consistência em todo o sistema.
    
    Args:
        text: Texto para estimar tokens
        
    Returns:
        Número estimado de tokens (mínimo 0)
    """
    if not text:
        return 0
    return max(0, len(text) // 4)


def estimate_tokens_from_file_size(file_size_bytes: int) -> int:
    """
    Estima tokens baseado no tamanho do arquivo.
    Assume encoding UTF-8 médio de 1 byte por caractere.
    
    Args:
        file_size_bytes: Tamanho do arquivo em bytes
        
    Returns:
        Número estimado de tokens
    """
    if file_size_bytes <= 0:
        return 0
    # Aproximação: file_size_bytes ≈ chars, chars/4 ≈ tokens
    return max(0, file_size_bytes // 4)
