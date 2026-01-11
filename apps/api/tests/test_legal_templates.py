"""
Testes para templates de documentos jurídicos
"""

import pytest
from app.services.legal_templates import (
    LegalTemplateLibrary,
    DocumentType,
    TemplateVariable
)


def test_template_library_initialization():
    """Teste de inicialização da biblioteca de templates"""
    library = LegalTemplateLibrary()
    
    assert len(library.templates) > 0
    assert "peticao_inicial_civel" in library.templates


def test_get_template():
    """Teste de obtenção de template"""
    library = LegalTemplateLibrary()
    
    template = library.get_template("peticao_inicial_civel")
    
    assert template is not None
    assert template.name == "Petição Inicial - Ação Cível"
    assert template.document_type == DocumentType.PETICAO_INICIAL
    assert len(template.variables) > 0


def test_list_templates():
    """Teste de listagem de templates"""
    library = LegalTemplateLibrary()
    
    # Listar todos
    all_templates = library.list_templates()
    assert len(all_templates) > 0
    
    # Filtrar por tipo
    peticoes = library.list_templates(document_type=DocumentType.PETICAO_INICIAL)
    assert all(t.document_type == DocumentType.PETICAO_INICIAL for t in peticoes)


def test_render_template_success():
    """Teste de renderização de template com sucesso"""
    library = LegalTemplateLibrary()
    
    variables = {
        "juizo": "1ª Vara Cível",
        "comarca": "São Paulo",
        "autor_nome": "João Silva",
        "autor_nacionalidade": "brasileiro",
        "autor_estado_civil": "solteiro",
        "autor_profissao": "advogado",
        "autor_cpf": "123.456.789-00",
        "autor_endereco": "Rua A, 123, São Paulo - SP",
        "reu_nome": "Maria Santos",
        "reu_endereco": "Rua B, 456, São Paulo - SP",
        "tipo_acao": "AÇÃO DE COBRANÇA",
        "causa_pedir": "O autor prestou serviços ao réu...",
        "fundamentacao_juridica": "Conforme art. 123 do CC...",
        "pedidos": "a) Condenação do réu ao pagamento...",
        "valor_causa": "R$ 10.000,00",
        "local": "São Paulo",
        "data": "01/01/2024",
        "advogado_nome": "Dr. João Silva",
        "advogado_oab": "123456",
        "advogado_oab_estado": "SP",
        "advogado_endereco": "Rua C, 789, São Paulo - SP"
    }
    
    rendered = library.render_template("peticao_inicial_civel", variables)
    
    assert "EXCELENTÍSSIMO" in rendered
    assert "João Silva" in rendered
    assert "Maria Santos" in rendered
    assert "AÇÃO DE COBRANÇA" in rendered


def test_render_template_missing_required():
    """Teste de renderização com variável obrigatória faltando"""
    library = LegalTemplateLibrary()
    
    variables = {
        "juizo": "1ª Vara Cível",
        # Faltando outras variáveis obrigatórias
    }
    
    with pytest.raises(ValueError) as exc_info:
        library.render_template("peticao_inicial_civel", variables, validate=True)
    
    assert "obrigatórias faltando" in str(exc_info.value)


def test_render_template_no_validation():
    """Teste de renderização sem validação"""
    library = LegalTemplateLibrary()
    
    variables = {
        "juizo": "1ª Vara Cível",
    }
    
    # Deve falhar ao tentar formatar, mas não na validação
    with pytest.raises(ValueError):
        library.render_template("peticao_inicial_civel", variables, validate=False)


def test_get_template_info():
    """Teste de obtenção de informações do template"""
    library = LegalTemplateLibrary()
    
    info = library.get_template_info("peticao_inicial_civel")
    
    assert "id" in info
    assert "name" in info
    assert "document_type" in info
    assert "variables" in info
    assert len(info["variables"]) > 0
    
    # Verificar estrutura das variáveis
    first_var = info["variables"][0]
    assert "name" in first_var
    assert "description" in first_var
    assert "required" in first_var
    assert "type" in first_var


def test_template_variable_names():
    """Teste de obtenção de nomes de variáveis"""
    library = LegalTemplateLibrary()
    
    template = library.get_template("peticao_inicial_civel")
    variable_names = template.get_variable_names()
    
    assert "juizo" in variable_names
    assert "comarca" in variable_names
    assert "autor_nome" in variable_names


def test_template_required_variables():
    """Teste de obtenção de variáveis obrigatórias"""
    library = LegalTemplateLibrary()
    
    template = library.get_template("peticao_inicial_civel")
    required_vars = template.get_required_variables()
    
    assert "juizo" in required_vars
    assert "comarca" in required_vars
    assert "autor_nome" in required_vars


def test_contestacao_template():
    """Teste específico do template de contestação"""
    library = LegalTemplateLibrary()
    
    template = library.get_template("contestacao")
    
    assert template is not None
    assert template.document_type == DocumentType.CONTESTACAO
    
    variables = {
        "processo_numero": "0000000-00.0000.0.00.0000",
        "reu_nome": "João Silva",
        "autor_nome": "Maria Santos",
        "preliminares": "Ausência de preliminares",
        "merito": "No mérito, verifica-se que...",
        "provas": "Requer produção de prova documental",
        "local": "São Paulo",
        "data": "01/01/2024",
        "advogado_nome": "Dr. João Silva",
        "advogado_oab": "123456",
        "advogado_oab_estado": "SP"
    }
    
    rendered = library.render_template("contestacao", variables)
    
    assert "CONTESTAÇÃO" in rendered
    assert "João Silva" in rendered


def test_procuracao_template():
    """Teste específico do template de procuração"""
    library = LegalTemplateLibrary()
    
    template = library.get_template("procuracao")
    
    assert template is not None
    assert template.document_type == DocumentType.PROCURACAO
    
    variables = {
        "outorgante_nome": "João Silva",
        "outorgante_cpf": "123.456.789-00",
        "outorgante_endereco": "Rua A, 123, São Paulo - SP",
        "outorgado_nome": "Dr. Pedro Santos",
        "outorgado_oab": "654321",
        "advogado_oab_estado": "SP",
        "poderes": "receber, dar quitação, transigir, desistir, renunciar ao direito",
        "local": "São Paulo",
        "data": "01/01/2024"
    }
    
    rendered = library.render_template("procuracao", variables)
    
    assert "PROCURAÇÃO" in rendered
    assert "João Silva" in rendered
    assert "Dr. Pedro Santos" in rendered

