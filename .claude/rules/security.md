# Regras de Segurança

## Nunca Fazer

- Commitar `.env`, credenciais ou tokens
- Logar dados sensíveis (senhas, tokens, PII)
- Executar SQL/queries sem sanitização
- Confiar em input do usuário sem validação

## Autenticação

- JWT com expiração curta
- Refresh tokens com rotação
- Logout deve invalidar tokens

## API

- Validar todos os inputs com Pydantic
- Rate limiting em endpoints públicos
- CORS configurado corretamente
- Headers de segurança habilitados

## Frontend

- Sanitizar HTML antes de renderizar (XSS)
- CSRF tokens em formulários
- Não armazenar tokens em localStorage (usar httpOnly cookies)

## Dados Sensíveis

- Encriptar dados em repouso
- TLS para dados em trânsito
- Logs não devem conter dados pessoais

## Revisão de Código

- Mudanças em auth/security precisam de review extra
- Verificar OWASP Top 10 em novos endpoints
