"""
Utilitários para manipulação de arquivos
"""

import os
import uuid
from pathlib import Path
from typing import List
from fastapi import UploadFile
from loguru import logger

from app.core.config import settings


ALLOWED_EXTENSIONS = {
    'pdf', 'docx', 'doc', 'odt', 'txt', 'rtf', 'html',
    'pptx', 'xlsx', 'xls', 'csv',
    'jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp',
    'mp3', 'wav', 'ogg', 'm4a', 'flac', 'aac',
    'mp4', 'avi', 'mov', 'wmv', 'flv', 'mkv',
    'zip'
}

# Mapeamento de extensões para MIME types
MIME_TYPE_MAP = {
    'pdf': 'application/pdf',
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'doc': 'application/msword',
    'odt': 'application/vnd.oasis.opendocument.text',
    'txt': 'text/plain',
    'rtf': 'application/rtf',
    'html': 'text/html',
    'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'xls': 'application/vnd.ms-excel',
    'csv': 'text/csv',
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'png': 'image/png',
    'gif': 'image/gif',
    'webp': 'image/webp',
    'bmp': 'image/bmp',
    'mp3': 'audio/mpeg',
    'wav': 'audio/wav',
    'ogg': 'audio/ogg',
    'm4a': 'audio/mp4',
    'flac': 'audio/flac',
    'aac': 'audio/aac',
    'mp4': 'video/mp4',
    'avi': 'video/x-msvideo',
    'mov': 'video/quicktime',
    'wmv': 'video/x-ms-wmv',
    'flv': 'video/x-flv',
    'mkv': 'video/x-matroska',
    'zip': 'application/zip',
}


def get_mime_type(filename: str) -> str:
    """Retorna o MIME type baseado na extensão do arquivo"""
    ext = get_file_extension(filename)
    return MIME_TYPE_MAP.get(ext, 'application/octet-stream')


def get_file_extension(filename: str) -> str:
    """Extrai extensão do arquivo"""
    return Path(filename).suffix.lower().lstrip('.')


def is_allowed_file(filename: str, allowed: List[str] = None) -> bool:
    """Verifica se extensão é permitida"""
    ext = get_file_extension(filename)
    allowed_set = set(allowed) if allowed else ALLOWED_EXTENSIONS
    return ext in allowed_set


def generate_unique_filename(original_filename: str) -> str:
    """Gera nome único para arquivo"""
    ext = get_file_extension(original_filename)
    unique_id = str(uuid.uuid4())
    return f"{unique_id}.{ext}"


async def save_upload_file(upload_file: UploadFile, destination: str = None) -> str:
    """
    Salva arquivo enviado
    
    Returns:
        Caminho do arquivo salvo
    """
    try:
        # Gerar nome único
        filename = generate_unique_filename(upload_file.filename)
        
        # Definir destino
        if destination is None:
            destination = settings.LOCAL_STORAGE_PATH
        
        # Criar diretório se não existir
        os.makedirs(destination, exist_ok=True)
        
        # Caminho completo
        file_path = os.path.join(destination, filename)
        
        # Salvar arquivo
        with open(file_path, "wb") as f:
            content = await upload_file.read()
            f.write(content)
        
        logger.info(f"Arquivo salvo: {file_path}")
        return file_path
        
    except Exception as e:
        logger.error(f"Erro ao salvar arquivo: {e}")
        raise


def get_file_size(file_path: str) -> int:
    """Retorna tamanho do arquivo em bytes"""
    return os.path.getsize(file_path)


def delete_file(file_path: str) -> bool:
    """Deleta arquivo"""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Arquivo deletado: {file_path}")
            return True
        return False
    except Exception as e:
        logger.error(f"Erro ao deletar arquivo: {e}")
        return False

