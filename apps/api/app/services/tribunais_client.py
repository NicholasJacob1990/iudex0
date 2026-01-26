"""
Cliente HTTP para o serviço de tribunais Node.js

Fornece interface Python assíncrona para comunicação com o microserviço
de integração com tribunais (PJe, e-Proc, e-SAJ).
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from loguru import logger

from app.core.config import settings


class TribunaisClientError(Exception):
    """Erro genérico do cliente de tribunais"""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        detail: Optional[str] = None,
        requires_interaction: bool = False,
        auth_type: Optional[str] = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.detail = detail
        self.requires_interaction = requires_interaction
        self.auth_type = auth_type


class TribunaisClient:
    """
    Cliente para serviço de tribunais Node.js

    Fornece métodos para:
    - Gerenciamento de credenciais (senha, certificados A1/A3)
    - Consultas de processos
    - Peticionamento eletrônico
    - Acompanhamento de operações assíncronas

    Exemplo de uso:
        client = TribunaisClient()
        credentials = await client.list_credentials(user_id="user123")
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: float = 30.0,
    ):
        """
        Inicializa o cliente de tribunais.

        Args:
            base_url: URL base do serviço de tribunais (default: http://localhost:3100/api)
            timeout: Timeout padrão para requisições em segundos
        """
        self.base_url = base_url or getattr(
            settings, "TRIBUNAIS_SERVICE_URL", "http://localhost:3100/api"
        )
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        logger.info(f"TribunaisClient inicializado - URL: {self.base_url}")

    async def _get_client(self) -> httpx.AsyncClient:
        """Retorna cliente HTTP, criando se necessário."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout),
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
        return self._client

    async def close(self) -> None:
        """Fecha o cliente HTTP."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def _request(
        self,
        method: str,
        endpoint: str,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Faz requisição HTTP ao serviço de tribunais.

        Args:
            method: Método HTTP (GET, POST, DELETE, etc.)
            endpoint: Endpoint relativo (ex: /credentials/password)
            json: Corpo da requisição em JSON
            params: Parâmetros de query string

        Returns:
            Resposta JSON do serviço

        Raises:
            TribunaisClientError: Em caso de erro na requisição
        """
        client = await self._get_client()

        try:
            logger.debug(f"Tribunais API: {method} {endpoint}")
            response = await client.request(
                method=method,
                url=endpoint,
                json=json,
                params=params,
            )

            # Tratar resposta 204 (No Content)
            if response.status_code == 204:
                return {"success": True}

            # Tentar parsear JSON
            try:
                data = response.json()
            except Exception:
                data = {"raw": response.text}

            # Verificar erros
            if response.status_code >= 400:
                error_msg = data.get("error", f"HTTP {response.status_code}")
                raise TribunaisClientError(
                    message=error_msg,
                    status_code=response.status_code,
                    detail=data.get("detail"),
                    requires_interaction=data.get("requiresInteraction", False),
                    auth_type=data.get("authType"),
                )

            return data

        except httpx.TimeoutException as e:
            logger.error(f"Timeout na requisição para {endpoint}: {e}")
            raise TribunaisClientError(
                message="Timeout na comunicação com serviço de tribunais",
                status_code=504,
            )
        except httpx.ConnectError as e:
            logger.error(f"Erro de conexão com serviço de tribunais: {e}")
            raise TribunaisClientError(
                message="Não foi possível conectar ao serviço de tribunais",
                status_code=503,
            )
        except TribunaisClientError:
            raise
        except Exception as e:
            logger.error(f"Erro inesperado na requisição: {e}")
            raise TribunaisClientError(
                message=f"Erro inesperado: {str(e)}",
                status_code=500,
            )

    # =========================================================================
    # Credenciais
    # =========================================================================

    async def save_password_credential(
        self,
        user_id: str,
        tribunal: str,
        tribunal_url: str,
        name: str,
        cpf: str,
        password: str,
    ) -> Dict[str, Any]:
        """
        Salva credencial de login com senha.

        Args:
            user_id: ID do usuário no Iudex
            tribunal: Tipo do tribunal (pje, eproc, esaj)
            tribunal_url: URL do tribunal
            name: Nome amigável para a credencial
            cpf: CPF do advogado (11 dígitos)
            password: Senha do tribunal

        Returns:
            Credencial criada
        """
        logger.info(f"Salvando credencial de senha para usuário {user_id}")
        return await self._request(
            "POST",
            "/credentials/password",
            json={
                "userId": user_id,
                "tribunal": tribunal,
                "tribunalUrl": tribunal_url,
                "name": name,
                "cpf": cpf,
                "password": password,
            },
        )

    async def save_certificate_a1(
        self,
        user_id: str,
        tribunal: str,
        tribunal_url: str,
        name: str,
        pfx_base64: str,
        pfx_password: str,
        expires_at: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Salva certificado A1 (.pfx).

        Args:
            user_id: ID do usuário no Iudex
            tribunal: Tipo do tribunal
            tribunal_url: URL do tribunal
            name: Nome amigável
            pfx_base64: Arquivo .pfx codificado em base64
            pfx_password: Senha do certificado
            expires_at: Data de expiração do certificado

        Returns:
            Credencial criada
        """
        logger.info(f"Salvando certificado A1 para usuário {user_id}")
        payload = {
            "userId": user_id,
            "tribunal": tribunal,
            "tribunalUrl": tribunal_url,
            "name": name,
            "pfxBase64": pfx_base64,
            "pfxPassword": pfx_password,
        }
        if expires_at:
            payload["expiresAt"] = expires_at.isoformat()

        return await self._request("POST", "/credentials/certificate-a1", json=payload)

    async def save_certificate_a3_cloud(
        self,
        user_id: str,
        tribunal: str,
        tribunal_url: str,
        name: str,
        provider: str,
    ) -> Dict[str, Any]:
        """
        Registra certificado A3 na nuvem.

        Args:
            user_id: ID do usuário
            tribunal: Tipo do tribunal
            tribunal_url: URL do tribunal
            name: Nome amigável
            provider: Provedor do certificado (certisign, serasa, safeweb)

        Returns:
            Credencial criada
        """
        logger.info(f"Salvando certificado A3 cloud para usuário {user_id}")
        return await self._request(
            "POST",
            "/credentials/certificate-a3-cloud",
            json={
                "userId": user_id,
                "tribunal": tribunal,
                "tribunalUrl": tribunal_url,
                "name": name,
                "provider": provider,
            },
        )

    async def save_certificate_a3_physical(
        self,
        user_id: str,
        tribunal: str,
        tribunal_url: str,
        name: str,
    ) -> Dict[str, Any]:
        """
        Registra certificado A3 físico (token USB).

        Args:
            user_id: ID do usuário
            tribunal: Tipo do tribunal
            tribunal_url: URL do tribunal
            name: Nome amigável

        Returns:
            Credencial criada
        """
        logger.info(f"Salvando certificado A3 físico para usuário {user_id}")
        return await self._request(
            "POST",
            "/credentials/certificate-a3-physical",
            json={
                "userId": user_id,
                "tribunal": tribunal,
                "tribunalUrl": tribunal_url,
                "name": name,
            },
        )

    async def list_credentials(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Lista credenciais do usuário.

        Args:
            user_id: ID do usuário

        Returns:
            Lista de credenciais (sem dados sensíveis)
        """
        logger.debug(f"Listando credenciais do usuário {user_id}")
        return await self._request("GET", f"/credentials/{user_id}")

    async def delete_credential(self, credential_id: str, user_id: str) -> bool:
        """
        Remove credencial.

        Args:
            credential_id: ID da credencial
            user_id: ID do usuário (para validação de ownership)

        Returns:
            True se removida com sucesso
        """
        logger.info(f"Removendo credencial {credential_id}")
        result = await self._request(
            "DELETE",
            f"/credentials/{credential_id}",
            json={"userId": user_id},
        )
        return result.get("success", True)

    # =========================================================================
    # Consultas
    # =========================================================================

    async def consultar_processo(
        self,
        credential_id: str,
        numero: str,
    ) -> Dict[str, Any]:
        """
        Consulta informações de um processo.

        Args:
            credential_id: ID da credencial a usar
            numero: Número do processo

        Returns:
            Informações do processo
        """
        logger.info(f"Consultando processo {numero}")
        return await self._request(
            "GET",
            f"/processo/{credential_id}/{numero}",
        )

    async def listar_documentos(
        self,
        credential_id: str,
        numero: str,
    ) -> List[Dict[str, Any]]:
        """
        Lista documentos de um processo.

        Args:
            credential_id: ID da credencial
            numero: Número do processo

        Returns:
            Lista de documentos
        """
        logger.info(f"Listando documentos do processo {numero}")
        return await self._request(
            "GET",
            f"/processo/{credential_id}/{numero}/documentos",
        )

    async def listar_movimentacoes(
        self,
        credential_id: str,
        numero: str,
    ) -> List[Dict[str, Any]]:
        """
        Lista movimentações de um processo.

        Args:
            credential_id: ID da credencial
            numero: Número do processo

        Returns:
            Lista de movimentações
        """
        logger.info(f"Listando movimentações do processo {numero}")
        return await self._request(
            "GET",
            f"/processo/{credential_id}/{numero}/movimentacoes",
        )

    async def execute_operation_sync(
        self,
        credential_id: str,
        operation: str,
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Executa operação de forma síncrona.

        Args:
            credential_id: ID da credencial
            operation: Tipo de operação
            params: Parâmetros da operação

        Returns:
            Resultado da operação
        """
        logger.info(f"Executando operação síncrona: {operation}")
        return await self._request(
            "POST",
            "/operations/sync",
            json={
                "credentialId": credential_id,
                "operation": operation,
                "params": params,
            },
        )

    async def execute_operation_async(
        self,
        user_id: str,
        credential_id: str,
        operation: str,
        params: Dict[str, Any],
        webhook_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Adiciona operação à fila para execução assíncrona.

        Args:
            user_id: ID do usuário
            credential_id: ID da credencial
            operation: Tipo de operação
            params: Parâmetros da operação
            webhook_url: URL para notificação ao concluir

        Returns:
            Informações do job criado (job_id, status)
        """
        logger.info(f"Adicionando operação à fila: {operation}")
        payload = {
            "userId": user_id,
            "credentialId": credential_id,
            "operation": operation,
            "params": params,
        }
        if webhook_url:
            payload["webhookUrl"] = webhook_url

        return await self._request("POST", "/operations/async", json=payload)

    # =========================================================================
    # Peticionamento
    # =========================================================================

    async def peticionar(
        self,
        user_id: str,
        credential_id: str,
        processo: str,
        tipo: str,
        arquivos: List[Dict[str, Any]],
        webhook_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Protocola petição (sempre assíncrono).

        Args:
            user_id: ID do usuário
            credential_id: ID da credencial
            processo: Número do processo
            tipo: Tipo da petição (peticao_inicial, peticao_intermediaria, recurso, outros)
            arquivos: Lista de arquivos para upload
            webhook_url: URL para notificação

        Returns:
            Informações do job criado
        """
        logger.info(f"Protocolando petição no processo {processo}")
        payload = {
            "userId": user_id,
            "credentialId": credential_id,
            "processo": processo,
            "tipo": tipo,
            "arquivos": arquivos,
        }
        if webhook_url:
            payload["webhookUrl"] = webhook_url

        return await self._request("POST", "/peticionar", json=payload)

    # =========================================================================
    # Status de Operações
    # =========================================================================

    async def get_operation_status(self, job_id: str) -> Dict[str, Any]:
        """
        Consulta status de uma operação assíncrona.

        Args:
            job_id: ID do job

        Returns:
            Status do job (status, progress, result, etc.)
        """
        logger.debug(f"Consultando status do job {job_id}")
        return await self._request("GET", f"/operations/{job_id}")


# Instância singleton do cliente
_tribunais_client: Optional[TribunaisClient] = None


def get_tribunais_client() -> TribunaisClient:
    """
    Retorna instância singleton do cliente de tribunais.

    Returns:
        Instância do TribunaisClient
    """
    global _tribunais_client
    if _tribunais_client is None:
        _tribunais_client = TribunaisClient()
    return _tribunais_client


async def close_tribunais_client() -> None:
    """Fecha o cliente de tribunais."""
    global _tribunais_client
    if _tribunais_client:
        await _tribunais_client.close()
        _tribunais_client = None
