# Guia de Migração - Iudex v0.3.0

## 📋 Visão Geral

Este guia descreve como migrar o banco de dados para suportar as novas funcionalidades de perfis individuais/institucionais e assinaturas digitais.

## 🗄️ Alterações no Banco de Dados

### Novos Campos na Tabela `users`

```sql
-- Tipo de conta
ALTER TABLE users ADD COLUMN account_type VARCHAR(20) DEFAULT 'INDIVIDUAL' NOT NULL;

-- Dados individuais (pessoa física)
ALTER TABLE users ADD COLUMN cpf VARCHAR(11);
ALTER TABLE users ADD COLUMN oab_state VARCHAR(2);
ALTER TABLE users ADD COLUMN phone VARCHAR(20);

-- Dados institucionais (pessoa jurídica)
ALTER TABLE users ADD COLUMN institution_name VARCHAR(200);
ALTER TABLE users ADD COLUMN cnpj VARCHAR(14);
ALTER TABLE users ADD COLUMN department VARCHAR(100);
ALTER TABLE users ADD COLUMN institution_address TEXT;
ALTER TABLE users ADD COLUMN institution_phone VARCHAR(20);

-- Assinatura
ALTER TABLE users ADD COLUMN signature_image TEXT;
ALTER TABLE users ADD COLUMN signature_text VARCHAR(500);

-- Renomear campos existentes (se necessário)
-- ALTER TABLE users RENAME COLUMN institution TO institution_name;
-- ALTER TABLE users RENAME COLUMN signature TO signature_image;
```

### Índices Recomendados

```sql
-- Índice para busca por tipo de conta
CREATE INDEX idx_users_account_type ON users(account_type);

-- Índice para busca por CPF (pessoa física)
CREATE INDEX idx_users_cpf ON users(cpf) WHERE cpf IS NOT NULL;

-- Índice para busca por CNPJ (pessoa jurídica)
CREATE INDEX idx_users_cnpj ON users(cnpj) WHERE cnpj IS NOT NULL;
```

## 🔧 Migração com Alembic

### Criar Nova Migração

```bash
cd apps/api

# Ativar ambiente virtual
source venv/bin/activate  # Linux/Mac
# ou venv\Scripts\activate no Windows

# Gerar migração automática
alembic revision --autogenerate -m "add_user_profiles_and_signatures"

# Revisar arquivo gerado em alembic/versions/
```

### Script de Migração Manual

Caso prefira criar manualmente:

```python
# alembic/versions/xxxx_add_user_profiles_and_signatures.py
"""add_user_profiles_and_signatures

Revision ID: xxxx
Revises: yyyy
Create Date: 2025-11-18 10:00:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'xxxx'
down_revision = 'yyyy'
branch_labels = None
depends_on = None


def upgrade():
    # Add account_type enum
    op.execute("CREATE TYPE accounttype AS ENUM ('INDIVIDUAL', 'INSTITUTIONAL')")
    
    # Add new columns
    op.add_column('users', sa.Column('account_type', sa.Enum('INDIVIDUAL', 'INSTITUTIONAL', name='accounttype'), nullable=False, server_default='INDIVIDUAL'))
    
    # Individual fields
    op.add_column('users', sa.Column('cpf', sa.String(length=11), nullable=True))
    op.add_column('users', sa.Column('oab_state', sa.String(length=2), nullable=True))
    op.add_column('users', sa.Column('phone', sa.String(length=20), nullable=True))
    
    # Institutional fields
    op.add_column('users', sa.Column('institution_name', sa.String(length=200), nullable=True))
    op.add_column('users', sa.Column('cnpj', sa.String(length=14), nullable=True))
    op.add_column('users', sa.Column('department', sa.String(length=100), nullable=True))
    op.add_column('users', sa.Column('institution_address', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('institution_phone', sa.String(length=20), nullable=True))
    
    # Signature fields
    op.add_column('users', sa.Column('signature_image', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('signature_text', sa.String(length=500), nullable=True))
    
    # Create indexes
    op.create_index('idx_users_account_type', 'users', ['account_type'])
    op.create_index('idx_users_cpf', 'users', ['cpf'], unique=False, postgresql_where=sa.text('cpf IS NOT NULL'))
    op.create_index('idx_users_cnpj', 'users', ['cnpj'], unique=False, postgresql_where=sa.text('cnpj IS NOT NULL'))


def downgrade():
    # Drop indexes
    op.drop_index('idx_users_cnpj', table_name='users')
    op.drop_index('idx_users_cpf', table_name='users')
    op.drop_index('idx_users_account_type', table_name='users')
    
    # Drop columns
    op.drop_column('users', 'signature_text')
    op.drop_column('users', 'signature_image')
    op.drop_column('users', 'institution_phone')
    op.drop_column('users', 'institution_address')
    op.drop_column('users', 'department')
    op.drop_column('users', 'cnpj')
    op.drop_column('users', 'institution_name')
    op.drop_column('users', 'phone')
    op.drop_column('users', 'oab_state')
    op.drop_column('users', 'cpf')
    op.drop_column('users', 'account_type')
    
    # Drop enum type
    op.execute('DROP TYPE accounttype')
```

### Aplicar Migração

```bash
# Visualizar SQL que será executado (dry-run)
alembic upgrade head --sql

# Aplicar migração
alembic upgrade head

# Verificar status
alembic current
```

## 🔄 Migração de Dados Existentes

### Se Você Já Tem Usuários

Se já existem usuários no banco, você precisa decidir o tipo de conta para cada um:

```python
# Script de migração de dados
from app.core.database import SessionLocal
from app.models.user import User, AccountType

async def migrate_existing_users():
    db = SessionLocal()
    
    # Buscar todos os usuários
    users = db.query(User).all()
    
    for user in users:
        # Lógica para determinar tipo de conta
        # Exemplo: se tem OAB, é individual
        if user.oab:
            user.account_type = AccountType.INDIVIDUAL
        else:
            # Pedir confirmação ou definir padrão
            user.account_type = AccountType.INDIVIDUAL
    
    db.commit()
    db.close()

# Executar migração
import asyncio
asyncio.run(migrate_existing_users())
```

### Campos Opcionais

Todos os novos campos são opcionais (`nullable=True`), então:
- Usuários existentes não serão afetados
- Podem atualizar perfil posteriormente
- Sistema funciona sem dados completos

## ⚙️ Variáveis de Ambiente

Adicionar ao `.env`:

```env
# Já existente
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/iudex

# Novas (opcionais)
ENABLE_SIGNATURE_UPLOAD=True
MAX_SIGNATURE_SIZE_MB=5
SIGNATURE_ALLOWED_FORMATS=png,jpg,jpeg
```

## ✅ Verificação Pós-Migração

### 1. Verificar Estrutura da Tabela

```sql
-- PostgreSQL
\d users

-- Ou
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'users'
ORDER BY ordinal_position;
```

### 2. Testar Criação de Usuário Individual

```bash
curl -X POST http://localhost:8000/api/auth/register/individual \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Teste Individual",
    "email": "teste@individual.com",
    "password": "senha123",
    "cpf": "12345678900",
    "oab": "123456",
    "oab_state": "SP"
  }'
```

### 3. Testar Criação de Usuário Institucional

```bash
curl -X POST http://localhost:8000/api/auth/register/institutional \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Teste Institucional",
    "email": "teste@institucional.com",
    "password": "senha123",
    "institution_name": "Teste Advogados",
    "cnpj": "12345678000190"
  }'
```

### 4. Verificar Dados

```sql
-- Ver usuários criados
SELECT id, name, email, account_type, oab, institution_name 
FROM users
ORDER BY created_at DESC
LIMIT 10;
```

## 🐛 Troubleshooting

### Erro: "column already exists"

Se algum campo já existe com nome diferente:

```python
# Na migração, renomear em vez de criar
def upgrade():
    # Renomear campo existente
    op.alter_column('users', 'institution', new_column_name='institution_name')
    
    # Adicionar novos campos
    op.add_column('users', sa.Column('account_type', ...))
```

### Erro: "enum type already exists"

```python
def upgrade():
    # Verificar se enum existe antes de criar
    from sqlalchemy import inspect
    conn = op.get_bind()
    
    # Criar enum apenas se não existir
    conn.execute("""
        DO $$ BEGIN
            CREATE TYPE accounttype AS ENUM ('INDIVIDUAL', 'INSTITUTIONAL');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
```

### Reversão de Migração

Se algo der errado:

```bash
# Voltar uma migração
alembic downgrade -1

# Voltar para versão específica
alembic downgrade <revision_id>

# Ver histórico
alembic history
```

## 📊 Impacto da Migração

- **Tempo estimado**: 2-5 minutos (depende do tamanho da tabela)
- **Downtime**: Recomendado (ou usar estratégia blue-green)
- **Rollback**: Suportado (via `alembic downgrade`)
- **Dados existentes**: Preservados
- **Compatibilidade**: Retrocompatível

## 🚀 Deploy

### Desenvolvimento

```bash
# 1. Backup do banco
pg_dump -U postgres iudex > backup_pre_migration.sql

# 2. Aplicar migração
alembic upgrade head

# 3. Reiniciar aplicação
python main.py
```

### Produção

```bash
# 1. Backup completo
pg_dump -U postgres iudex_prod > backup_$(date +%Y%m%d_%H%M%S).sql

# 2. Modo manutenção (opcional)
# Desabilitar acesso temporariamente

# 3. Aplicar migração
alembic upgrade head

# 4. Verificar logs
tail -f logs/app.log

# 5. Smoke tests
curl http://api.iudex.com/health

# 6. Habilitar acesso
```

## 📝 Checklist de Migração

- [ ] Backup do banco de dados
- [ ] Revisar script de migração
- [ ] Testar migração em ambiente de desenvolvimento
- [ ] Atualizar variáveis de ambiente
- [ ] Aplicar migração em staging
- [ ] Testar endpoints de registro
- [ ] Verificar usuários existentes
- [ ] Aplicar migração em produção
- [ ] Monitorar logs e métricas
- [ ] Documentar problemas encontrados

---

**Nota**: Em caso de dúvidas, consulte a documentação do Alembic: https://alembic.sqlalchemy.org/





