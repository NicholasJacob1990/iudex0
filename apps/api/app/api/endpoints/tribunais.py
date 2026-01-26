"""
Endpoints FastAPI para integração com serviço de tribunais

Fornece API REST para:
- Gerenciamento de credenciais (senha, certificados A1/A3)
- Consultas de processos
- Peticionamento eletrônico
- Acompanhamento de operações assíncronas
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger

from app.core.security import get_current_user
from app.models.user import User
from app.schemas.tribunais import (
    # Request schemas
    PasswordCredentialCreate,
    CertificateA1Create,
    CertificateA3CloudCreate,
    CertificateA3PhysicalCreate,
    CredentialDelete,
    OperationSyncRequest,
    OperationAsyncRequest,
    PeticionarRequest,
    # Response schemas
    CredentialResponse,
    CredentialListResponse,
    OperationSyncResponse,
    OperationAsyncResponse,
    JobStatusResponse,
    ProcessoInfo,
    DocumentoInfo,
    MovimentacaoInfo,
    TribunaisError,
)
from app.services.tribunais_client import (
    TribunaisClient,
    TribunaisClientError,
    get_tribunais_client,
)

router = APIRouter()


def _handle_tribunais_error(e: TribunaisClientError) -> HTTPException:
    """Converte erro do cliente para HTTPException."""
    status_code = e.status_code or status.HTTP_500_INTERNAL_SERVER_ERROR

    # Mapear códigos específicos
    if status_code == 404:
        status_code = status.HTTP_404_NOT_FOUND
    elif status_code == 400:
        status_code = status.HTTP_400_BAD_REQUEST
    elif status_code == 503:
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return HTTPException(
        status_code=status_code,
        detail={
            "error": e.message,
            "detail": e.detail,
            "requiresInteraction": e.requires_interaction,
            "authType": e.auth_type,
        },
    )


# =============================================================================
# Credenciais
# =============================================================================


@router.post(
    "/credentials/password",
    response_model=CredentialResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar credencial com senha",
    description="Salva credencial de login com CPF e senha para tribunal",
    responses={
        201: {"description": "Credencial criada com sucesso"},
        400: {"model": TribunaisError, "description": "Dados inválidos"},
        503: {"model": TribunaisError, "description": "Serviço indisponível"},
    },
)
async def create_password_credential(
    data: PasswordCredentialCreate,
    current_user: User = Depends(get_current_user),
    client: TribunaisClient = Depends(get_tribunais_client),
):
    """
    Cria credencial de login com senha.

    - **userId**: ID do usuário (será validado contra usuário autenticado)
    - **tribunal**: Tipo do tribunal (pje, eproc, esaj)
    - **tribunalUrl**: URL do tribunal
    - **name**: Nome amigável para identificação
    - **cpf**: CPF do advogado (11 dígitos, apenas números)
    - **password**: Senha do tribunal
    """
    # Validar que o userId corresponde ao usuário autenticado
    if data.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Não é permitido criar credenciais para outros usuários",
        )

    try:
        result = await client.save_password_credential(
            user_id=data.user_id,
            tribunal=data.tribunal.value,
            tribunal_url=data.tribunal_url,
            name=data.name,
            cpf=data.cpf,
            password=data.password,
        )
        logger.info(f"Credencial de senha criada para usuário {current_user.id}")
        return result
    except TribunaisClientError as e:
        logger.error(f"Erro ao criar credencial de senha: {e.message}")
        raise _handle_tribunais_error(e)


@router.post(
    "/credentials/certificate-a1",
    response_model=CredentialResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload de certificado A1",
    description="Salva certificado digital A1 (.pfx) para tribunal",
)
async def create_certificate_a1(
    data: CertificateA1Create,
    current_user: User = Depends(get_current_user),
    client: TribunaisClient = Depends(get_tribunais_client),
):
    """
    Upload de certificado A1 (.pfx).

    - **pfxBase64**: Arquivo .pfx codificado em base64
    - **pfxPassword**: Senha do certificado
    - **expiresAt**: Data de expiração (opcional)
    """
    if data.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Não é permitido criar credenciais para outros usuários",
        )

    try:
        result = await client.save_certificate_a1(
            user_id=data.user_id,
            tribunal=data.tribunal.value,
            tribunal_url=data.tribunal_url,
            name=data.name,
            pfx_base64=data.pfx_base64,
            pfx_password=data.pfx_password,
            expires_at=data.expires_at,
        )
        logger.info(f"Certificado A1 salvo para usuário {current_user.id}")
        return result
    except TribunaisClientError as e:
        logger.error(f"Erro ao salvar certificado A1: {e.message}")
        raise _handle_tribunais_error(e)


@router.post(
    "/credentials/certificate-a3-cloud",
    response_model=CredentialResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar certificado A3 na nuvem",
    description="Registra certificado digital A3 hospedado na nuvem",
)
async def create_certificate_a3_cloud(
    data: CertificateA3CloudCreate,
    current_user: User = Depends(get_current_user),
    client: TribunaisClient = Depends(get_tribunais_client),
):
    """
    Registra certificado A3 na nuvem.

    - **provider**: Provedor do certificado (certisign, serasa, safeweb)
    """
    if data.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Não é permitido criar credenciais para outros usuários",
        )

    try:
        result = await client.save_certificate_a3_cloud(
            user_id=data.user_id,
            tribunal=data.tribunal.value,
            tribunal_url=data.tribunal_url,
            name=data.name,
            provider=data.provider.value,
        )
        logger.info(f"Certificado A3 cloud registrado para usuário {current_user.id}")
        return result
    except TribunaisClientError as e:
        logger.error(f"Erro ao registrar certificado A3 cloud: {e.message}")
        raise _handle_tribunais_error(e)


@router.post(
    "/credentials/certificate-a3-physical",
    response_model=CredentialResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar certificado A3 físico",
    description="Registra certificado digital A3 físico (token USB)",
)
async def create_certificate_a3_physical(
    data: CertificateA3PhysicalCreate,
    current_user: User = Depends(get_current_user),
    client: TribunaisClient = Depends(get_tribunais_client),
):
    """
    Registra certificado A3 físico (token USB).

    Operações com este tipo de certificado requerem interação do usuário
    através da extensão do navegador.
    """
    if data.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Não é permitido criar credenciais para outros usuários",
        )

    try:
        result = await client.save_certificate_a3_physical(
            user_id=data.user_id,
            tribunal=data.tribunal.value,
            tribunal_url=data.tribunal_url,
            name=data.name,
        )
        logger.info(f"Certificado A3 físico registrado para usuário {current_user.id}")
        return result
    except TribunaisClientError as e:
        logger.error(f"Erro ao registrar certificado A3 físico: {e.message}")
        raise _handle_tribunais_error(e)


@router.get(
    "/credentials/{user_id}",
    response_model=List[CredentialResponse],
    summary="Listar credenciais do usuário",
    description="Lista todas as credenciais cadastradas para o usuário",
)
async def list_credentials(
    user_id: str,
    current_user: User = Depends(get_current_user),
    client: TribunaisClient = Depends(get_tribunais_client),
):
    """
    Lista credenciais do usuário.

    Retorna apenas metadados, nunca dados sensíveis como senhas ou certificados.
    """
    # Validar acesso
    if user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Não é permitido listar credenciais de outros usuários",
        )

    try:
        result = await client.list_credentials(user_id)
        return result
    except TribunaisClientError as e:
        logger.error(f"Erro ao listar credenciais: {e.message}")
        raise _handle_tribunais_error(e)


@router.delete(
    "/credentials/{credential_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remover credencial",
    description="Remove uma credencial cadastrada",
)
async def delete_credential(
    credential_id: str,
    data: CredentialDelete,
    current_user: User = Depends(get_current_user),
    client: TribunaisClient = Depends(get_tribunais_client),
):
    """
    Remove credencial.

    A credencial será permanentemente removida, incluindo todos os dados
    criptografados associados.
    """
    if data.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Não é permitido remover credenciais de outros usuários",
        )

    try:
        deleted = await client.delete_credential(credential_id, data.user_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Credencial não encontrada",
            )
        logger.info(f"Credencial {credential_id} removida pelo usuário {current_user.id}")
    except TribunaisClientError as e:
        logger.error(f"Erro ao remover credencial: {e.message}")
        raise _handle_tribunais_error(e)


# =============================================================================
# Consultas de Processos
# =============================================================================


@router.get(
    "/processo/{credential_id}/{numero}",
    response_model=ProcessoInfo,
    summary="Consultar processo",
    description="Consulta informações de um processo",
)
async def consultar_processo(
    credential_id: str,
    numero: str,
    current_user: User = Depends(get_current_user),
    client: TribunaisClient = Depends(get_tribunais_client),
):
    """
    Consulta informações de um processo.

    Retorna dados como partes, classe, assunto, vara, etc.
    """
    try:
        result = await client.consultar_processo(credential_id, numero)
        return result
    except TribunaisClientError as e:
        logger.error(f"Erro ao consultar processo {numero}: {e.message}")
        raise _handle_tribunais_error(e)


@router.get(
    "/processo/{credential_id}/{numero}/documentos",
    response_model=List[DocumentoInfo],
    summary="Listar documentos do processo",
    description="Lista todos os documentos de um processo",
)
async def listar_documentos(
    credential_id: str,
    numero: str,
    current_user: User = Depends(get_current_user),
    client: TribunaisClient = Depends(get_tribunais_client),
):
    """
    Lista documentos de um processo.

    Retorna lista com ID, tipo, data de juntada e outros metadados.
    """
    try:
        result = await client.listar_documentos(credential_id, numero)
        return result
    except TribunaisClientError as e:
        logger.error(f"Erro ao listar documentos do processo {numero}: {e.message}")
        raise _handle_tribunais_error(e)


@router.get(
    "/processo/{credential_id}/{numero}/movimentacoes",
    response_model=List[MovimentacaoInfo],
    summary="Listar movimentações do processo",
    description="Lista todas as movimentações de um processo",
)
async def listar_movimentacoes(
    credential_id: str,
    numero: str,
    current_user: User = Depends(get_current_user),
    client: TribunaisClient = Depends(get_tribunais_client),
):
    """
    Lista movimentações de um processo.

    Retorna histórico de movimentações com data, tipo e descrição.
    """
    try:
        result = await client.listar_movimentacoes(credential_id, numero)
        return result
    except TribunaisClientError as e:
        logger.error(f"Erro ao listar movimentações do processo {numero}: {e.message}")
        raise _handle_tribunais_error(e)


# =============================================================================
# Operações Síncronas e Assíncronas
# =============================================================================


@router.post(
    "/operations/sync",
    response_model=OperationSyncResponse,
    summary="Executar operação síncrona",
    description="Executa operação de forma síncrona (para consultas rápidas)",
)
async def execute_operation_sync(
    data: OperationSyncRequest,
    current_user: User = Depends(get_current_user),
    client: TribunaisClient = Depends(get_tribunais_client),
):
    """
    Executa operação de forma síncrona.

    Indicado para consultas rápidas. Operações que requerem assinatura
    com certificado A3 devem usar o endpoint assíncrono.
    """
    try:
        result = await client.execute_operation_sync(
            credential_id=data.credential_id,
            operation=data.operation.value,
            params=data.params,
        )
        return result
    except TribunaisClientError as e:
        logger.error(f"Erro na operação síncrona: {e.message}")
        raise _handle_tribunais_error(e)


@router.post(
    "/operations/async",
    response_model=OperationAsyncResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Executar operação assíncrona",
    description="Adiciona operação à fila para execução assíncrona",
)
async def execute_operation_async(
    data: OperationAsyncRequest,
    current_user: User = Depends(get_current_user),
    client: TribunaisClient = Depends(get_tribunais_client),
):
    """
    Adiciona operação à fila para execução assíncrona.

    Indicado para operações demoradas ou que requerem interação do usuário
    (certificados A3). Use o endpoint de status para acompanhar o progresso.
    """
    if data.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Não é permitido executar operações para outros usuários",
        )

    try:
        result = await client.execute_operation_async(
            user_id=data.user_id,
            credential_id=data.credential_id,
            operation=data.operation.value,
            params=data.params,
            webhook_url=data.webhook_url,
        )
        return result
    except TribunaisClientError as e:
        logger.error(f"Erro ao adicionar operação à fila: {e.message}")
        raise _handle_tribunais_error(e)


@router.get(
    "/operations/{job_id}",
    response_model=JobStatusResponse,
    summary="Consultar status de operação",
    description="Consulta status de uma operação assíncrona",
)
async def get_operation_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
    client: TribunaisClient = Depends(get_tribunais_client),
):
    """
    Consulta status de uma operação assíncrona.

    Retorna status atual, progresso e resultado (se concluído).
    """
    try:
        result = await client.get_operation_status(job_id)
        return result
    except TribunaisClientError as e:
        logger.error(f"Erro ao consultar status do job {job_id}: {e.message}")
        raise _handle_tribunais_error(e)


# =============================================================================
# Peticionamento
# =============================================================================


@router.post(
    "/peticionar",
    response_model=OperationAsyncResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Protocolar petição",
    description="Protocola petição no tribunal (sempre assíncrono)",
)
async def peticionar(
    data: PeticionarRequest,
    current_user: User = Depends(get_current_user),
    client: TribunaisClient = Depends(get_tribunais_client),
):
    """
    Protocola petição no tribunal.

    A operação é sempre executada de forma assíncrona. Para certificados A3,
    pode requerer interação do usuário através da extensão do navegador.

    - **processo**: Número do processo
    - **tipo**: Tipo da petição (peticao_inicial, peticao_intermediaria, recurso, outros)
    - **arquivos**: Lista de arquivos para upload
    - **webhookUrl**: URL para notificação ao concluir (opcional)
    """
    if data.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Não é permitido peticionar para outros usuários",
        )

    try:
        # Converter arquivos para formato esperado pelo serviço
        arquivos = [
            {
                "name": a.name,
                "path": a.path,
                "base64": a.base64,
                "mimeType": a.mime_type,
                "tipoDocumento": a.tipo_documento,
            }
            for a in data.arquivos
        ]

        result = await client.peticionar(
            user_id=data.user_id,
            credential_id=data.credential_id,
            processo=data.processo,
            tipo=data.tipo.value,
            arquivos=arquivos,
            webhook_url=data.webhook_url,
        )
        logger.info(f"Petição adicionada à fila para processo {data.processo}")
        return result
    except TribunaisClientError as e:
        logger.error(f"Erro ao protocolar petição: {e.message}")
        raise _handle_tribunais_error(e)
