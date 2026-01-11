"""
Validadores e sanitizadores para segurança e qualidade de dados
"""

import re
from typing import Optional, List
from loguru import logger


class InputValidator:
    """Validação e sanitização de inputs do usuário"""
    
    @staticmethod
    def sanitize_text(text: str, max_length: Optional[int] = None) -> str:
        """
        Sanitiza texto removendo caracteres perigosos
        Mantém formatação básica
        """
        if not text:
            return ""
        
        # Remover caracteres de controle perigosos
        text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)
        
        # Limitar comprimento se especificado
        if max_length and len(text) > max_length:
            text = text[:max_length]
        
        return text.strip()
    
    @staticmethod
    def sanitize_html(html: str) -> str:
        """
        Remove tags HTML perigosas mantendo formatação básica
        Usa whitelist de tags permitidas
        """
        # TODO: Implementar com biblioteca como bleach
        # Por enquanto, remove todas as tags
        import re
        return re.sub(r'<[^>]+>', '', html)
    
    @staticmethod
    def validate_email(email: str) -> bool:
        """Valida formato de email"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    @staticmethod
    def validate_cpf(cpf: str) -> bool:
        """Valida CPF brasileiro"""
        # Remover formatação
        cpf = re.sub(r'[^\d]', '', cpf)
        
        if len(cpf) != 11:
            return False
        
        # Verificar se todos os dígitos são iguais
        if cpf == cpf[0] * 11:
            return False
        
        # Validar primeiro dígito verificador
        sum_digits = sum(int(cpf[i]) * (10 - i) for i in range(9))
        digit1 = 11 - (sum_digits % 11)
        if digit1 >= 10:
            digit1 = 0
        if int(cpf[9]) != digit1:
            return False
        
        # Validar segundo dígito verificador
        sum_digits = sum(int(cpf[i]) * (11 - i) for i in range(10))
        digit2 = 11 - (sum_digits % 11)
        if digit2 >= 10:
            digit2 = 0
        if int(cpf[10]) != digit2:
            return False
        
        return True
    
    @staticmethod
    def validate_cnpj(cnpj: str) -> bool:
        """Valida CNPJ brasileiro"""
        # Remover formatação
        cnpj = re.sub(r'[^\d]', '', cnpj)
        
        if len(cnpj) != 14:
            return False
        
        # Verificar se todos os dígitos são iguais
        if cnpj == cnpj[0] * 14:
            return False
        
        # Validar primeiro dígito verificador
        weights = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        sum_digits = sum(int(cnpj[i]) * weights[i] for i in range(12))
        digit1 = 11 - (sum_digits % 11)
        if digit1 >= 10:
            digit1 = 0
        if int(cnpj[12]) != digit1:
            return False
        
        # Validar segundo dígito verificador
        weights = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        sum_digits = sum(int(cnpj[i]) * weights[i] for i in range(13))
        digit2 = 11 - (sum_digits % 11)
        if digit2 >= 10:
            digit2 = 0
        if int(cnpj[13]) != digit2:
            return False
        
        return True
    
    @staticmethod
    def validate_oab(oab: str, state: str) -> bool:
        """Valida número OAB"""
        # Remover formatação
        oab = re.sub(r'[^\d]', '', oab)
        
        # OAB deve ter entre 4 e 7 dígitos
        if not oab or len(oab) < 4 or len(oab) > 7:
            return False
        
        # Estado deve ter 2 caracteres
        if not state or len(state) != 2:
            return False
        
        # Validar estado
        valid_states = [
            'AC', 'AL', 'AP', 'AM', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA',
            'MT', 'MS', 'MG', 'PA', 'PB', 'PR', 'PE', 'PI', 'RJ', 'RN',
            'RS', 'RO', 'RR', 'SC', 'SP', 'SE', 'TO'
        ]
        
        return state.upper() in valid_states
    
    @staticmethod
    def validate_phone(phone: str) -> bool:
        """Valida telefone brasileiro"""
        # Remover formatação
        phone = re.sub(r'[^\d]', '', phone)
        
        # Telefone deve ter 10 ou 11 dígitos (com celular 9)
        if len(phone) not in [10, 11]:
            return False
        
        # DDD deve ser válido (11-99)
        ddd = int(phone[:2])
        if ddd < 11 or ddd > 99:
            return False
        
        return True
    
    @staticmethod
    def validate_password_strength(password: str) -> tuple[bool, List[str]]:
        """
        Valida força da senha
        Retorna (is_valid, [mensagens de erro])
        """
        errors = []
        
        if len(password) < 8:
            errors.append("Senha deve ter no mínimo 8 caracteres")
        
        if not re.search(r'[a-z]', password):
            errors.append("Senha deve conter letras minúsculas")
        
        if not re.search(r'[A-Z]', password):
            errors.append("Senha deve conter letras maiúsculas")
        
        if not re.search(r'\d', password):
            errors.append("Senha deve conter números")
        
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("Senha deve conter caracteres especiais")
        
        # Verificar sequências comuns
        common_patterns = ['123456', 'abcdef', 'qwerty', 'password']
        for pattern in common_patterns:
            if pattern in password.lower():
                errors.append("Senha não deve conter sequências comuns")
                break
        
        return len(errors) == 0, errors
    
    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """
        Sanitiza nome de arquivo removendo caracteres perigosos
        """
        # Remover caracteres perigosos
        filename = re.sub(r'[^\w\s.-]', '', filename)
        
        # Remover espaços múltiplos
        filename = re.sub(r'\s+', '_', filename)
        
        # Limitar tamanho
        if len(filename) > 255:
            name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
            max_name_len = 255 - len(ext) - 1
            filename = f"{name[:max_name_len]}.{ext}" if ext else name[:255]
        
        return filename
    
    @staticmethod
    def validate_file_extension(filename: str, allowed_extensions: List[str]) -> bool:
        """Valida extensão de arquivo"""
        if '.' not in filename:
            return False
        
        ext = filename.rsplit('.', 1)[1].lower()
        return ext in [e.lower().lstrip('.') for e in allowed_extensions]
    
    @staticmethod
    def validate_file_size(size_bytes: int, max_size_mb: int = 500) -> bool:
        """Valida tamanho de arquivo"""
        max_size_bytes = max_size_mb * 1024 * 1024
        return size_bytes <= max_size_bytes
    
    @staticmethod
    def sanitize_sql_like(value: str) -> str:
        """Escapa caracteres especiais para consultas SQL LIKE"""
        # Escapar caracteres especiais do LIKE
        value = value.replace('\\', '\\\\')
        value = value.replace('%', '\\%')
        value = value.replace('_', '\\_')
        return value
    
    @staticmethod
    def validate_json_structure(data: dict, required_fields: List[str]) -> tuple[bool, Optional[str]]:
        """
        Valida se JSON contém campos obrigatórios
        Retorna (is_valid, error_message)
        """
        missing_fields = []
        
        for field in required_fields:
            # Suporta campos aninhados com dot notation (ex: "user.email")
            keys = field.split('.')
            current = data
            
            try:
                for key in keys:
                    if not isinstance(current, dict) or key not in current:
                        missing_fields.append(field)
                        break
                    current = current[key]
            except (KeyError, TypeError):
                missing_fields.append(field)
        
        if missing_fields:
            return False, f"Campos obrigatórios faltando: {', '.join(missing_fields)}"
        
        return True, None


class DocumentValidator:
    """Validações específicas para documentos jurídicos"""
    
    @staticmethod
    def validate_process_number(process_number: str) -> bool:
        """
        Valida número de processo judicial (padrão CNJ)
        Formato: NNNNNNN-DD.AAAA.J.TT.OOOO
        """
        # Remover formatação
        clean = re.sub(r'[^\d]', '', process_number)
        
        if len(clean) != 20:
            return False
        
        # Validar dígitos verificadores
        try:
            # Extrair partes
            seq = clean[:7]
            dd = clean[7:9]
            year = clean[9:13]
            segment = clean[13]
            court = clean[14:16]
            origin = clean[16:20]
            
            # Calcular dígito verificador
            number_to_validate = f"{origin}{year}{segment}{court}{seq}"
            remainder = int(number_to_validate) % 97
            calculated_dd = 98 - remainder
            
            return int(dd) == calculated_dd
        except Exception as e:
            logger.warning(f"Erro ao validar número de processo: {e}")
            return False
    
    @staticmethod
    def validate_legal_citation(citation: str) -> bool:
        """Valida se citação legal está em formato válido"""
        # Padrões comuns de citação legal brasileira
        patterns = [
            r'Lei\s+n[ºª°]?\s*[\d.]+',  # Lei nº 8.080/90
            r'Decreto\s+n[ºª°]?\s*[\d.]+',
            r'CF/\d{2,4}',  # CF/88
            r'CLT',
            r'CC/\d{2,4}',  # CC/2002
            r'CPC/\d{2,4}',
            r'CPP/\d{2,4}',
            r'art\.?\s*\d+',  # art. 5º
        ]
        
        for pattern in patterns:
            if re.search(pattern, citation, re.IGNORECASE):
                return True
        
        return False
    
    @staticmethod
    def extract_legal_references(text: str) -> List[str]:
        """Extrai referências legais do texto"""
        patterns = [
            r'Lei\s+n[ºª°]?\s*[\d.]+(?:/\d{2,4})?',
            r'Decreto\s+n[ºª°]?\s*[\d.]+(?:/\d{2,4})?',
            r'CF/\d{2,4},?\s*art\.?\s*\d+',
            r'art\.?\s*\d+[ºª°]?(?:,\s*§\s*\d+[ºª°]?)?',
        ]
        
        references = []
        for pattern in patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            references.extend([m.group() for m in matches])
        
        return list(set(references))  # Remove duplicatas


# Instâncias globais
input_validator = InputValidator()
document_validator = DocumentValidator()

