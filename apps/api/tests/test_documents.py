"""
Testes para processamento de documentos
"""

import pytest
from app.services.document_processor import DocumentChunker, UnlimitedContextProcessor
from app.utils.validators import InputValidator, DocumentValidator


def test_document_chunker_basic():
    """Teste básico de chunking de documentos"""
    chunker = DocumentChunker(chunk_size=100, overlap=20)
    
    text = "Este é um texto de teste. " * 50  # Texto grande o suficiente para múltiplos chunks
    chunks = chunker.chunk_by_tokens(text)
    
    assert len(chunks) > 1
    assert all(chunk.content for chunk in chunks)
    assert all(chunk.position == i for i, chunk in enumerate(chunks))


def test_document_chunker_semantic():
    """Teste de chunking semântico"""
    chunker = DocumentChunker()
    
    text = """
    RELATÓRIO
    Este é o relatório dos fatos.
    
    FUNDAMENTAÇÃO
    Esta é a fundamentação jurídica.
    
    DECISÃO
    Esta é a decisão.
    """
    
    chunks = chunker.chunk_semantically(text)
    
    assert len(chunks) > 0
    assert any("RELATÓRIO" in chunk.content for chunk in chunks)


@pytest.mark.asyncio
async def test_unlimited_context_processor():
    """Teste do processador de contexto ilimitado"""
    processor = UnlimitedContextProcessor()
    
    text = "Este é um documento de teste. " * 100
    result = await processor.process_large_document(
        text,
        task="resumir",
        strategy="map-reduce"
    )
    
    assert result is not None
    assert "strategy" in result
    assert result["strategy"] == "map-reduce"


def test_input_validator_email():
    """Teste de validação de email"""
    validator = InputValidator()
    
    assert validator.validate_email("test@example.com") is True
    assert validator.validate_email("invalid.email") is False
    assert validator.validate_email("@example.com") is False


def test_input_validator_cpf():
    """Teste de validação de CPF"""
    validator = InputValidator()
    
    # CPF válido
    assert validator.validate_cpf("123.456.789-09") is True
    
    # CPF inválido
    assert validator.validate_cpf("111.111.111-11") is False
    assert validator.validate_cpf("12345") is False


def test_input_validator_cnpj():
    """Teste de validação de CNPJ"""
    validator = InputValidator()
    
    # CNPJ válido
    assert validator.validate_cnpj("11.222.333/0001-81") is True
    
    # CNPJ inválido
    assert validator.validate_cnpj("11.111.111/1111-11") is False


def test_input_validator_oab():
    """Teste de validação de OAB"""
    validator = InputValidator()
    
    assert validator.validate_oab("123456", "SP") is True
    assert validator.validate_oab("12", "SP") is False  # Muito curto
    assert validator.validate_oab("123456", "XX") is False  # Estado inválido


def test_input_validator_password_strength():
    """Teste de validação de força de senha"""
    validator = InputValidator()
    
    # Senha forte
    valid, errors = validator.validate_password_strength("Senha@Forte123")
    assert valid is True
    assert len(errors) == 0
    
    # Senha fraca
    valid, errors = validator.validate_password_strength("senha123")
    assert valid is False
    assert len(errors) > 0


def test_input_validator_sanitize_filename():
    """Teste de sanitização de nome de arquivo"""
    validator = InputValidator()
    
    filename = validator.sanitize_filename("arquivo  com  espaços.pdf")
    assert "  " not in filename
    
    filename = validator.sanitize_filename("arquivo../../../etc/passwd")
    assert "../" not in filename


def test_document_validator_process_number():
    """Teste de validação de número de processo"""
    validator = DocumentValidator()
    
    # Número de processo válido
    assert validator.validate_process_number("0000000-00.0000.0.00.0000") is True
    
    # Número inválido
    assert validator.validate_process_number("123456") is False


def test_document_validator_legal_citation():
    """Teste de validação de citação legal"""
    validator = DocumentValidator()
    
    assert validator.validate_legal_citation("Lei nº 8.080/90") is True
    assert validator.validate_legal_citation("CF/88") is True
    assert validator.validate_legal_citation("art. 5º") is True
    assert validator.validate_legal_citation("texto qualquer") is False


def test_document_validator_extract_references():
    """Teste de extração de referências legais"""
    validator = DocumentValidator()
    
    text = """
    Conforme dispõe a Lei nº 8.080/90 e o art. 5º da CF/88,
    bem como o Decreto nº 1.234/2020...
    """
    
    references = validator.extract_legal_references(text)
    
    assert len(references) > 0
    assert any("8.080" in ref for ref in references)
    assert any("CF/88" in ref for ref in references)

