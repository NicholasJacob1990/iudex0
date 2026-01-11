# Problema de Registro - Diagnóstico e Solução

## Problema Identificado

O endpoint de registro estava retornando erro 500 (Internal Server Error) devido a:

1. **Campos duplicados no schema `UserCreate`**
   - Os campos `oab`, `institution_name` e `cnpj` estavam definidos duas vezes
   - Isso causava problemas de validação do Pydantic

2. **Conversão incorreta do enum `AccountType`**
   - O código tentava converter de string para enum de forma que poderia falhar
   - SQLAlchemy pode converter automaticamente se receber a string correta

## Correções Aplicadas

### 1. Schema de Usuário (`apps/api/app/schemas/user.py`)

Removidos os campos duplicados e organizado os campos opcional corretamente:

```python
class UserCreate(UserBase):
    """Schema para criação de usuário"""
    password: str = Field(..., min_length=8, max_length=100)
    account_type: str = Field(default="INDIVIDUAL", pattern="^(INDIVIDUAL|INSTITUTIONAL)$")
    
    # Campos opcionais para conta Individual
    cpf: Optional[str] = None
    oab: Optional[str] = None
    oab_state: Optional[str] = None
    phone: Optional[str] = None
    
    # Campos opcionais para conta Institucional
    institution_name: Optional[str] = None
    cnpj: Optional[str] = None
    position: Optional[str] = None
    team_size: Optional[str] = None
    department: Optional[str] = None
```

### 2. Endpoint de Registro (`apps/api/app/api/endpoints/auth.py`)

Simplificado a conversão do `account_type` e garantido uso do Enum:

```python
# Normalizar account_type
account_type_str = user_in.account_type.upper() if isinstance(user_in.account_type, str) else str(user_in.account_type).upper()

# Validar account_type
if account_type_str not in ["INDIVIDUAL", "INSTITUTIONAL"]:
    account_type_str = "INDIVIDUAL"

# Converter para Enum explicitamente
account_type_enum = AccountType.INDIVIDUAL if account_type_str == "INDIVIDUAL" else AccountType.INSTITUTIONAL

user_data = {
    ...
    "account_type": account_type_enum,  # Passando o Enum member diretamente
    ...
}
```

## Para Testar

### 1. Reiniciar o Servidor Backend

```bash
# Na pasta apps/api
# Parar o servidor atual (Ctrl+C se estiver no terminal)
# Ou matar o processo:
pkill -f uvicorn

# Iniciar novamente com hot reload
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Testar o Endpoint via cURL

```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "João Silva",
    "email": "joao.silva@exemplo.com",
    "password": "senha12345",
    "account_type": "INDIVIDUAL"
  }'
```

Resposta esperada (sucesso):
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 1800,
  "user": {
    "id": "...",
    "email": "joao.silva@exemplo.com",
    "name": "João Silva",
    ...
  }
}
```

### 3. Testar via Interface Web

1. Acesse `http://localhost:3000/register`
2. Escolha o tipo de perfil (Individual ou Institucional)
3. Preencha os dados
4. Clique em "Finalizar Cadastro"

Se funcionar, você será redirecionado para `/generator`.

## Status

- ✅ Schema `UserCreate` corrigido
- ✅ Endpoint de registro atualizado
- ⏳ Aguardando reinício do servidor para aplicar mudanças
- ⏳ Teste completo pendente

## Próximos Passos

1. Reiniciar o servidor backend
2. Testar o registro via interface web
3. Verificar se o usuário consegue fazer login após registro
4. Atualizar o `status.md` com os resultados


