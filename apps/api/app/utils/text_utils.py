"""
Utilitários para manipulação de texto
"""

import re
from typing import List


def clean_text(text: str) -> str:
    """
    Limpa texto removendo caracteres especiais e espaços extras
    """
    # Remover múltiplos espaços
    text = re.sub(r'\s+', ' ', text)
    
    # Remover espaços no início e fim
    text = text.strip()
    
    return text


def extract_numbers(text: str) -> List[str]:
    """Extrai todos os números de um texto"""
    return re.findall(r'\d+', text)


def extract_process_numbers(text: str) -> List[str]:
    """
    Extrai números de processo CNJ
    Formato: NNNNNNN-DD.AAAA.J.TR.OOOO
    """
    pattern = r'\d{7}-\d{2}\.\d{4}\.\d{1}\.\d{2}\.\d{4}'
    return re.findall(pattern, text)


def truncate_text(text: str, max_length: int, suffix: str = "...") -> str:
    """Trunca texto com sufixo"""
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def remove_accents(text: str) -> str:
    """Remove acentos de um texto"""
    import unicodedata
    nfd = unicodedata.normalize('NFD', text)
    return ''.join(char for char in nfd if unicodedata.category(char) != 'Mn')


def slugify(text: str) -> str:
    """Converte texto para slug URL-friendly"""
    text = remove_accents(text).lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    text = re.sub(r'^-+|-+$', '', text)
    return text


def extract_emails(text: str) -> List[str]:
    """Extrai emails de um texto"""
    pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    return re.findall(pattern, text)


def extract_phones(text: str) -> List[str]:
    """
    Extrai telefones brasileiros
    Formatos: (XX) XXXX-XXXX, (XX) XXXXX-XXXX
    """
    pattern = r'\(?\d{2}\)?[\s-]?\d{4,5}[\s-]?\d{4}'
    return re.findall(pattern, text)


def count_words(text: str) -> int:
    """Conta palavras em um texto"""
    return len(text.split())


def estimate_reading_time(text: str, words_per_minute: int = 200) -> int:
    """
    Estima tempo de leitura em minutos
    Média de 200 palavras por minuto
    """
    word_count = count_words(text)
    return max(1, round(word_count / words_per_minute))

