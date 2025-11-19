"""
Formatador de Documentos Jurídicos

Converte documentos para diferentes formatos e aplica formatação adequada
"""

from typing import Dict, Any, Optional
import re
from datetime import datetime
import markdown


class DocumentFormatter:
    """
    Formata documentos jurídicos para diferentes saídas
    """
    
    @staticmethod
    def to_html(content: str, include_styles: bool = True) -> str:
        """
        Converte markdown para HTML com estilos jurídicos
        
        Args:
            content: Conteúdo em markdown
            include_styles: Se deve incluir CSS inline
        
        Returns:
            HTML formatado
        """
        # Converter markdown básico para HTML
        html = markdown.markdown(
            content,
            extensions=['extra', 'nl2br', 'sane_lists']
        )
        
        # Aplicar formatações específicas jurídicas
        html = DocumentFormatter._apply_legal_formatting(html)
        
        if include_styles:
            styles = DocumentFormatter._get_legal_styles()
            html = f"""
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Documento Jurídico</title>
    <style>{styles}</style>
</head>
<body>
    <div class="document-container">
        {html}
    </div>
</body>
</html>
"""
        
        return html
    
    @staticmethod
    def to_plain_text(content: str, line_width: int = 80) -> str:
        """
        Converte para texto puro formatado
        
        Args:
            content: Conteúdo original
            line_width: Largura máxima da linha
        
        Returns:
            Texto formatado
        """
        # Remover markdown
        text = re.sub(r'\*\*(.*?)\*\*', r'\1', content)  # Bold
        text = re.sub(r'\*(.*?)\*', r'\1', text)  # Italic
        text = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', text)  # Links
        
        # Quebrar linhas longas mantendo parágrafos
        paragraphs = text.split('\n\n')
        formatted_paragraphs = []
        
        for para in paragraphs:
            if len(para) <= line_width:
                formatted_paragraphs.append(para)
            else:
                words = para.split()
                lines = []
                current_line = []
                current_length = 0
                
                for word in words:
                    word_length = len(word) + 1
                    if current_length + word_length <= line_width:
                        current_line.append(word)
                        current_length += word_length
                    else:
                        lines.append(' '.join(current_line))
                        current_line = [word]
                        current_length = word_length
                
                if current_line:
                    lines.append(' '.join(current_line))
                
                formatted_paragraphs.append('\n'.join(lines))
        
        return '\n\n'.join(formatted_paragraphs)
    
    @staticmethod
    def add_page_numbers(content: str, start_page: int = 1) -> str:
        """
        Adiciona numeração de páginas (estimada)
        
        Args:
            content: Conteúdo do documento
            start_page: Página inicial
        
        Returns:
            Conteúdo com marcadores de página
        """
        # Estimar páginas baseado em caracteres (~2000 chars por página)
        chars_per_page = 2000
        pages = len(content) // chars_per_page + 1
        
        # Adicionar marcadores de página
        formatted = content
        current_pos = 0
        
        for page in range(start_page, start_page + pages):
            next_pos = current_pos + chars_per_page
            if next_pos < len(content):
                # Encontrar quebra de parágrafo mais próxima
                newline_pos = content.find('\n\n', next_pos)
                if newline_pos != -1 and newline_pos < next_pos + 200:
                    next_pos = newline_pos
                
                marker = f"\n\n--- Página {page} ---\n\n"
                formatted = formatted[:next_pos] + marker + formatted[next_pos:]
                current_pos = next_pos + len(marker)
        
        return formatted
    
    @staticmethod
    def apply_signature_formatting(
        content: str,
        signature_data: Dict[str, Any]
    ) -> str:
        """
        Aplica formatação de assinatura ao documento
        
        Args:
            content: Conteúdo do documento
            signature_data: Dados de assinatura
        
        Returns:
            Documento com assinatura formatada
        """
        signature_block = "\n\n" + "=" * 80 + "\n\n"
        
        # Linha para assinatura física
        signature_block += "_" * 60 + "\n"
        
        # Nome
        signature_block += f"{signature_data.get('name', '')}\n"
        
        # Dados específicos por tipo
        if signature_data.get('type') == 'individual':
            if signature_data.get('oab'):
                signature_block += f"OAB/{signature_data.get('oab_state')} {signature_data.get('oab')}\n"
            if signature_data.get('cpf'):
                signature_block += f"CPF: {signature_data.get('cpf')}\n"
        else:
            if signature_data.get('position'):
                signature_block += f"{signature_data.get('position')}\n"
            if signature_data.get('institution_name'):
                signature_block += f"{signature_data.get('institution_name')}\n"
            if signature_data.get('cnpj'):
                signature_block += f"CNPJ: {signature_data.get('cnpj')}\n"
        
        # Email
        if signature_data.get('email'):
            signature_block += f"Email: {signature_data.get('email')}\n"
        
        # Telefone
        phone = signature_data.get('phone') or signature_data.get('institution_phone')
        if phone:
            signature_block += f"Tel: {phone}\n"
        
        return content + signature_block
    
    @staticmethod
    def _apply_legal_formatting(html: str) -> str:
        """Aplica formatação específica para documentos jurídicos"""
        
        # Destacar seções legais comuns
        legal_sections = [
            'DOS FATOS', 'DO DIREITO', 'DOS PEDIDOS', 'DA FUNDAMENTAÇÃO',
            'EXCELENTÍSSIMO', 'CLÁUSULA', 'CONSULTA', 'ANÁLISE', 'CONCLUSÃO'
        ]
        
        for section in legal_sections:
            pattern = rf'\b({section})\b'
            html = re.sub(
                pattern,
                r'<strong class="legal-section">\1</strong>',
                html,
                flags=re.IGNORECASE
            )
        
        # Destacar artigos de lei
        html = re.sub(
            r'\b(art(?:igo|\.)?\s*\d+(?:º|°)?)',
            r'<span class="legal-article">\1</span>',
            html,
            flags=re.IGNORECASE
        )
        
        # Destacar referências a leis
        html = re.sub(
            r'\b(Lei\s+n?º?\s*[\d\.]+/\d+|CPC|CPP|CC|CF)',
            r'<span class="legal-reference">\1</span>',
            html,
            flags=re.IGNORECASE
        )
        
        return html
    
    @staticmethod
    def _get_legal_styles() -> str:
        """Retorna CSS para documentos jurídicos"""
        return """
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: 'Times New Roman', Times, serif;
    font-size: 12pt;
    line-height: 1.5;
    color: #000;
    background: #fff;
}

.document-container {
    max-width: 210mm; /* A4 width */
    margin: 0 auto;
    padding: 25mm 30mm; /* Margens padrão ABNT */
    background: #fff;
}

h1, h2, h3 {
    font-weight: bold;
    margin-top: 1.5em;
    margin-bottom: 0.75em;
    text-transform: uppercase;
}

h1 {
    font-size: 14pt;
    text-align: center;
}

h2 {
    font-size: 12pt;
}

h3 {
    font-size: 12pt;
    font-weight: normal;
    text-decoration: underline;
}

p {
    text-align: justify;
    text-indent: 1.25cm; /* Recuo de parágrafo ABNT */
    margin-bottom: 0.75em;
}

.legal-section {
    font-weight: bold;
    text-transform: uppercase;
}

.legal-article {
    font-weight: bold;
    color: #004085;
}

.legal-reference {
    font-style: italic;
    color: #004085;
}

ul, ol {
    margin-left: 2cm;
    margin-bottom: 1em;
}

li {
    margin-bottom: 0.5em;
}

blockquote {
    margin: 1em 4cm;
    font-style: italic;
    border-left: 2px solid #ccc;
    padding-left: 1em;
}

table {
    width: 100%;
    border-collapse: collapse;
    margin: 1em 0;
}

th, td {
    border: 1px solid #000;
    padding: 0.5em;
    text-align: left;
}

th {
    background-color: #f0f0f0;
    font-weight: bold;
}

@media print {
    .document-container {
        margin: 0;
        padding: 25mm 30mm;
    }
    
    @page {
        size: A4;
        margin: 0;
    }
}
"""
    
    @staticmethod
    def format_case_value(value: float) -> Dict[str, str]:
        """
        Formata valor da causa (numérico e por extenso)
        
        Args:
            value: Valor numérico
        
        Returns:
            Dict com 'numeric' e 'written'
        """
        # Formatar numérico
        numeric = f"R$ {value:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        
        # Converter para extenso (simplificado - em produção usar biblioteca)
        written = DocumentFormatter._number_to_words(value)
        
        return {
            "numeric": numeric,
            "written": written
        }
    
    @staticmethod
    def _number_to_words(number: float) -> str:
        """
        Converte número para extenso (versão simplificada)
        Em produção, usar biblioteca como num2words
        """
        # Implementação muito simplificada
        reais = int(number)
        centavos = int((number - reais) * 100)
        
        if reais == 0:
            reais_text = "zero reais"
        elif reais == 1:
            reais_text = "um real"
        else:
            reais_text = f"{reais} reais"  # Simplificado
        
        if centavos == 0:
            return reais_text
        elif centavos == 1:
            return f"{reais_text} e um centavo"
        else:
            return f"{reais_text} e {centavos} centavos"
    
    @staticmethod
    def format_date(date: datetime, format_type: str = 'long') -> str:
        """
        Formata data para padrão jurídico brasileiro
        
        Args:
            date: Data a formatar
            format_type: 'short' (DD/MM/YYYY) ou 'long' (DD de MMMM de YYYY)
        
        Returns:
            Data formatada
        """
        months_pt = [
            'janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho',
            'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'
        ]
        
        if format_type == 'short':
            return date.strftime('%d/%m/%Y')
        else:
            day = date.day
            month = months_pt[date.month - 1]
            year = date.year
            return f"{day} de {month} de {year}"
    
    @staticmethod
    def apply_abnt_formatting(content: str, metadata: Dict[str, Any]) -> str:
        """
        Aplica formatação ABNT ao documento
        
        Args:
            content: Conteúdo do documento
            metadata: Metadados (título, autor, etc.)
        
        Returns:
            Documento formatado segundo ABNT
        """
        # Cabeçalho ABNT
        header = ""
        if metadata.get('author'):
            header += f"{metadata['author']}\n"
        if metadata.get('title'):
            header += f"{metadata['title'].upper()}\n"
        header += "\n" + "=" * 80 + "\n\n"
        
        # Conteúdo
        formatted_content = content
        
        # Rodapé com data
        footer = "\n\n" + "=" * 80 + "\n"
        if metadata.get('city'):
            footer += f"{metadata['city']}, "
        footer += DocumentFormatter.format_date(datetime.now(), 'long')
        
        return header + formatted_content + footer

