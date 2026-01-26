"""
SEI Tools para Iudex Chat - 52 funções completas
Paridade total com o MCP sei-mcp

Uso:
    from integrations.sei_tools import SEI_TOOLS, SEIToolExecutor

    # Registrar tools no chat do Iudex
    chat.register_tools(SEI_TOOLS)

    # Executar quando LLM chamar uma função
    executor = SEIToolExecutor(sei_api_url="http://localhost:3001")
    result = await executor.execute(user_id, function_name, arguments)
"""

import httpx
import json
import os
from typing import Optional, Any

# Carregar definições de funções
FUNCTIONS_PATH = os.path.join(os.path.dirname(__file__), "openai-functions.json")
with open(FUNCTIONS_PATH) as f:
    _data = json.load(f)
    SEI_FUNCTIONS = _data["functions"]  # Formato OpenAI
    SEI_TOOLS_NAME = _data["name"]
    SEI_TOOLS_DESCRIPTION = _data["description"]

# Converter para formato de tools (compatível com OpenAI, Claude, Gemini)
SEI_TOOLS = [
    {
        "type": "function",
        "function": func
    }
    for func in SEI_FUNCTIONS
]


class SEIToolExecutor:
    """Executor de ferramentas SEI - chama a API sei-playwright"""

    def __init__(
        self,
        sei_api_url: str = "http://localhost:3001",
        sei_api_key: str = ""
    ):
        self.sei_api_url = sei_api_url.rstrip("/")
        self.sei_api_key = sei_api_key
        self.sessions: dict[str, str] = {}  # user_id -> session_id

    async def execute(
        self,
        user_id: str,
        function_name: str,
        arguments: dict
    ) -> dict:
        """Executa uma função SEI"""
        session_id = self.sessions.get(user_id)

        try:
            result = await self._call_api(user_id, function_name, arguments, session_id)
            return {"success": True, "data": result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _headers(self, session_id: Optional[str] = None) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.sei_api_key:
            headers["X-API-Key"] = self.sei_api_key
        if session_id:
            headers["X-Session-Id"] = session_id
        return headers

    def _encode_process(self, numero: str) -> str:
        return numero.replace("/", "%2F")

    async def _call_api(
        self,
        user_id: str,
        fn: str,
        args: dict,
        session_id: Optional[str]
    ) -> Any:
        """Chama endpoint correspondente na API SEI"""
        headers = self._headers(session_id)
        url = self.sei_api_url

        async with httpx.AsyncClient(timeout=120.0) as client:

            # ========== AUTENTICAÇÃO ==========
            if fn == "sei_login":
                resp = await client.post(f"{url}/sessions", headers=headers, json={
                    "seiUrl": args.get("seiUrl"),
                    "usuario": args.get("usuario"),
                    "senha": args.get("senha"),
                    "orgao": args.get("orgao")
                })
                data = resp.json()
                if "sessionId" in data:
                    self.sessions[user_id] = data["sessionId"]
                return data

            if fn == "sei_logout":
                sid = session_id
                if sid:
                    resp = await client.delete(f"{url}/sessions/{sid}", headers=headers)
                    if user_id in self.sessions:
                        del self.sessions[user_id]
                    return resp.json()
                return {"message": "Nenhuma sessão ativa"}

            if fn == "sei_get_session":
                resp = await client.get(f"{url}/session", headers=headers)
                return resp.json()

            # ========== PROCESSOS ==========
            if fn == "sei_search_process":
                params = {
                    "query": args.get("query"),
                    "type": args.get("type", "numero"),
                    "limit": args.get("limit", 20)
                }
                if args.get("unidade"):
                    params["unidade"] = args["unidade"]
                if args.get("tipo_processo"):
                    params["tipo_processo"] = args["tipo_processo"]
                if args.get("data_inicio"):
                    params["data_inicio"] = args["data_inicio"]
                if args.get("data_fim"):
                    params["data_fim"] = args["data_fim"]
                resp = await client.get(f"{url}/process/search", headers=headers, params=params)
                return resp.json()

            if fn == "sei_open_process":
                numero = self._encode_process(args["numeroProcesso"])
                resp = await client.post(f"{url}/process/{numero}/open", headers=headers)
                return resp.json()

            if fn == "sei_create_process":
                resp = await client.post(f"{url}/process", headers=headers, json={
                    "tipoProcedimento": args.get("tipoProcedimento"),
                    "especificacao": args.get("especificacao"),
                    "assuntos": args.get("assuntos", []),
                    "interessados": args.get("interessados"),
                    "observacao": args.get("observacao"),
                    "nivelAcesso": args.get("nivelAcesso", "publico"),
                    "hipoteseLegal": args.get("hipoteseLegal")
                })
                return resp.json()

            if fn == "sei_get_status":
                numero = self._encode_process(args["numeroProcesso"])
                params = {
                    "includeHistory": args.get("includeHistory", True),
                    "includeDocuments": args.get("includeDocuments", True)
                }
                resp = await client.get(f"{url}/process/{numero}/status", headers=headers, params=params)
                return resp.json()

            if fn == "sei_forward_process":
                numero = self._encode_process(args["numeroProcesso"])
                resp = await client.post(f"{url}/process/{numero}/forward", headers=headers, json={
                    "unidadeDestino": args.get("unidadeDestino"),
                    "manterAberto": args.get("manterAberto", False),
                    "prazo": args.get("prazo"),
                    "urgente": args.get("urgente", False),
                    "observacao": args.get("observacao")
                })
                return resp.json()

            if fn == "sei_conclude_process":
                numero = self._encode_process(args["numeroProcesso"])
                resp = await client.post(f"{url}/process/{numero}/conclude", headers=headers)
                return resp.json()

            if fn == "sei_reopen_process":
                numero = self._encode_process(args["numeroProcesso"])
                resp = await client.post(f"{url}/process/{numero}/reopen", headers=headers)
                return resp.json()

            if fn == "sei_relate_processes":
                numero = self._encode_process(args["numeroProcesso"])
                resp = await client.post(f"{url}/process/{numero}/relate", headers=headers, json={
                    "processoRelacionado": args.get("processoRelacionado"),
                    "tipoRelacao": args.get("tipoRelacao", "relacionamento")
                })
                return resp.json()

            # ========== DOCUMENTOS ==========
            if fn == "sei_list_documents":
                numero = self._encode_process(args["numeroProcesso"])
                resp = await client.get(f"{url}/process/{numero}/documents", headers=headers)
                return resp.json()

            if fn == "sei_get_document":
                doc_id = args["documentoId"]
                params = {"includeContent": args.get("includeContent", False)}
                resp = await client.get(f"{url}/document/{doc_id}", headers=headers, params=params)
                return resp.json()

            if fn == "sei_create_document":
                numero = self._encode_process(args["numeroProcesso"])
                resp = await client.post(f"{url}/process/{numero}/documents", headers=headers, json={
                    "tipoDocumento": args.get("tipoDocumento"),
                    "textoInicial": args.get("textoInicial", "nenhum"),
                    "textoPadraoId": args.get("textoPadraoId"),
                    "descricao": args.get("descricao"),
                    "numero": args.get("numero"),
                    "nomeArvore": args.get("nomeArvore"),
                    "interessados": args.get("interessados"),
                    "destinatarios": args.get("destinatarios"),
                    "assuntos": args.get("assuntos"),
                    "observacoes": args.get("observacoes"),
                    "nivelAcesso": args.get("nivelAcesso", "publico"),
                    "hipoteseLegal": args.get("hipoteseLegal"),
                    "conteudo": args.get("conteudo")
                })
                return resp.json()

            if fn == "sei_upload_document":
                numero = self._encode_process(args["numeroProcesso"])
                resp = await client.post(f"{url}/process/{numero}/upload", headers=headers, json={
                    "filePath": args.get("filePath"),
                    "fileName": args.get("fileName"),
                    "tipoDocumento": args.get("tipoDocumento"),
                    "descricao": args.get("descricao"),
                    "dataDocumento": args.get("dataDocumento"),
                    "nivelAcesso": args.get("nivelAcesso", "publico"),
                    "hipoteseLegal": args.get("hipoteseLegal"),
                    "formato": args.get("formato", "nato_digital")
                })
                return resp.json()

            if fn == "sei_upload_document_base64":
                numero = self._encode_process(args["numeroProcesso"])
                resp = await client.post(f"{url}/process/{numero}/upload-base64", headers=headers, json={
                    "conteudoBase64": args.get("conteudoBase64"),
                    "nomeArquivo": args.get("nomeArquivo"),
                    "mimeType": args.get("mimeType"),
                    "tipoDocumento": args.get("tipoDocumento"),
                    "descricao": args.get("descricao"),
                    "nivelAcesso": args.get("nivelAcesso", "publico")
                })
                return resp.json()

            # ========== ASSINATURA ==========
            if fn == "sei_sign_document":
                doc_id = args["documentoId"]
                resp = await client.post(f"{url}/document/{doc_id}/sign", headers=headers, json={
                    "senha": args.get("senha"),
                    "cargo": args.get("cargo")
                })
                return resp.json()

            if fn == "sei_sign_multiple":
                resp = await client.post(f"{url}/documents/sign-multiple", headers=headers, json={
                    "documentoIds": args.get("documentoIds"),
                    "senha": args.get("senha"),
                    "cargo": args.get("cargo")
                })
                return resp.json()

            if fn == "sei_sign_block":
                bloco_id = args["blocoId"]
                resp = await client.post(f"{url}/bloco/{bloco_id}/sign", headers=headers, json={
                    "senha": args.get("senha")
                })
                return resp.json()

            if fn == "sei_cancel_document":
                doc_id = args["documentoId"]
                resp = await client.post(f"{url}/document/{doc_id}/cancel", headers=headers, json={
                    "motivo": args.get("motivo")
                })
                return resp.json()

            # ========== DOWNLOAD ==========
            if fn == "sei_download_process":
                numero = self._encode_process(args["numeroProcesso"])
                params = {
                    "includeAttachments": args.get("includeAttachments", True),
                    "format": args.get("format", "pdf")
                }
                if args.get("outputPath"):
                    params["outputPath"] = args["outputPath"]
                resp = await client.get(f"{url}/process/{numero}/download", headers=headers, params=params)
                return resp.json()

            if fn == "sei_download_document":
                doc_id = args["documentoId"]
                params = {}
                if args.get("outputPath"):
                    params["outputPath"] = args["outputPath"]
                resp = await client.get(f"{url}/document/{doc_id}/download", headers=headers, params=params)
                return resp.json()

            # ========== ANOTAÇÕES ==========
            if fn == "sei_add_annotation":
                numero = self._encode_process(args["numeroProcesso"])
                resp = await client.post(f"{url}/process/{numero}/annotations", headers=headers, json={
                    "texto": args.get("texto"),
                    "prioridade": args.get("prioridade", "normal")
                })
                return resp.json()

            if fn == "sei_list_annotations":
                numero = self._encode_process(args["numeroProcesso"])
                resp = await client.get(f"{url}/process/{numero}/annotations", headers=headers)
                return resp.json()

            # ========== BLOCOS ==========
            if fn == "sei_list_blocks":
                params = {}
                if args.get("tipo"):
                    params["tipo"] = args["tipo"]
                resp = await client.get(f"{url}/blocos", headers=headers, params=params)
                return resp.json()

            if fn == "sei_create_block":
                resp = await client.post(f"{url}/blocos", headers=headers, json={
                    "tipo": args.get("tipo"),
                    "descricao": args.get("descricao"),
                    "unidadesDisponibilizacao": args.get("unidadesDisponibilizacao"),
                    "documentos": args.get("documentos"),
                    "disponibilizar": args.get("disponibilizar", False)
                })
                return resp.json()

            if fn == "sei_get_block":
                bloco_id = args["blocoId"]
                params = {"includeDocuments": args.get("includeDocuments", True)}
                resp = await client.get(f"{url}/bloco/{bloco_id}", headers=headers, params=params)
                return resp.json()

            if fn == "sei_add_to_block":
                bloco_id = args["blocoId"]
                resp = await client.post(f"{url}/bloco/{bloco_id}/documents", headers=headers, json={
                    "documentoId": args.get("documentoId"),
                    "numeroProcesso": args.get("numeroProcesso")
                })
                return resp.json()

            if fn == "sei_remove_from_block":
                bloco_id = args["blocoId"]
                doc_id = args["documentoId"]
                resp = await client.delete(f"{url}/bloco/{bloco_id}/documents/{doc_id}", headers=headers)
                return resp.json()

            if fn == "sei_release_block":
                bloco_id = args["blocoId"]
                resp = await client.post(f"{url}/bloco/{bloco_id}/release", headers=headers)
                return resp.json()

            # ========== MARCADORES ==========
            if fn == "sei_add_marker":
                numero = self._encode_process(args["numeroProcesso"])
                resp = await client.post(f"{url}/process/{numero}/markers", headers=headers, json={
                    "marcador": args.get("marcador"),
                    "texto": args.get("texto")
                })
                return resp.json()

            if fn == "sei_remove_marker":
                numero = self._encode_process(args["numeroProcesso"])
                marcador = args["marcador"]
                resp = await client.delete(f"{url}/process/{numero}/markers/{marcador}", headers=headers)
                return resp.json()

            # ========== PRAZOS ==========
            if fn == "sei_set_deadline":
                numero = self._encode_process(args["numeroProcesso"])
                resp = await client.post(f"{url}/process/{numero}/deadline", headers=headers, json={
                    "dias": args.get("dias"),
                    "tipo": args.get("tipo", "util")
                })
                return resp.json()

            # ========== CIÊNCIA ==========
            if fn == "sei_register_knowledge":
                doc_id = args["documentoId"]
                resp = await client.post(f"{url}/document/{doc_id}/knowledge", headers=headers)
                return resp.json()

            # ========== PUBLICAÇÃO ==========
            if fn == "sei_schedule_publication":
                doc_id = args["documentoId"]
                resp = await client.post(f"{url}/document/{doc_id}/publish", headers=headers, json={
                    "veiculo": args.get("veiculo"),
                    "dataPublicacao": args.get("dataPublicacao"),
                    "resumo": args.get("resumo")
                })
                return resp.json()

            # ========== LISTAGENS ==========
            if fn == "sei_list_document_types":
                params = {}
                if args.get("filter"):
                    params["filter"] = args["filter"]
                resp = await client.get(f"{url}/tipos-documento", headers=headers, params=params)
                return resp.json()

            if fn == "sei_list_process_types":
                params = {}
                if args.get("filter"):
                    params["filter"] = args["filter"]
                resp = await client.get(f"{url}/tipos-processo", headers=headers, params=params)
                return resp.json()

            if fn == "sei_list_units":
                params = {}
                if args.get("filter"):
                    params["filter"] = args["filter"]
                resp = await client.get(f"{url}/unidades", headers=headers, params=params)
                return resp.json()

            if fn == "sei_list_users":
                params = {}
                if args.get("filter"):
                    params["filter"] = args["filter"]
                resp = await client.get(f"{url}/usuarios", headers=headers, params=params)
                return resp.json()

            if fn == "sei_list_hipoteses_legais":
                resp = await client.get(f"{url}/hipoteses-legais", headers=headers)
                return resp.json()

            if fn == "sei_list_marcadores":
                resp = await client.get(f"{url}/marcadores", headers=headers)
                return resp.json()

            if fn == "sei_list_my_processes":
                params = {
                    "status": args.get("status", "abertos"),
                    "limit": args.get("limit", 50)
                }
                resp = await client.get(f"{url}/meus-processos", headers=headers, params=params)
                return resp.json()

            # ========== CONTROLE DE ACESSO ==========
            if fn == "sei_grant_access":
                numero = self._encode_process(args["numeroProcesso"])
                resp = await client.post(f"{url}/process/{numero}/access", headers=headers, json={
                    "usuario": args.get("usuario"),
                    "tipo": args.get("tipo", "consulta")
                })
                return resp.json()

            if fn == "sei_revoke_access":
                numero = self._encode_process(args["numeroProcesso"])
                usuario = args["usuario"]
                resp = await client.delete(f"{url}/process/{numero}/access/{usuario}", headers=headers)
                return resp.json()

            # ========== VISUALIZAÇÃO ==========
            if fn == "sei_screenshot":
                params = {"fullPage": args.get("fullPage", False)}
                if args.get("outputPath"):
                    params["outputPath"] = args["outputPath"]
                resp = await client.get(f"{url}/screenshot", headers=headers, params=params)
                return resp.json()

            if fn == "sei_snapshot":
                params = {"includeHidden": args.get("includeHidden", False)}
                resp = await client.get(f"{url}/snapshot", headers=headers, params=params)
                return resp.json()

            if fn == "sei_get_current_page":
                resp = await client.get(f"{url}/current-page", headers=headers)
                return resp.json()

            # ========== NAVEGAÇÃO ==========
            if fn == "sei_navigate":
                resp = await client.post(f"{url}/navigate", headers=headers, json={
                    "target": args.get("target")
                })
                return resp.json()

            if fn == "sei_click":
                resp = await client.post(f"{url}/click", headers=headers, json={
                    "selector": args.get("selector")
                })
                return resp.json()

            if fn == "sei_type":
                resp = await client.post(f"{url}/type", headers=headers, json={
                    "selector": args.get("selector"),
                    "text": args.get("text"),
                    "clear": args.get("clear", True)
                })
                return resp.json()

            if fn == "sei_select":
                resp = await client.post(f"{url}/select", headers=headers, json={
                    "selector": args.get("selector"),
                    "value": args.get("value")
                })
                return resp.json()

            if fn == "sei_wait":
                resp = await client.post(f"{url}/wait", headers=headers, json={
                    "selector": args.get("selector"),
                    "timeout": args.get("timeout", 10000)
                })
                return resp.json()

            return {"error": f"Função desconhecida: {fn}"}

    def get_session(self, user_id: str) -> Optional[str]:
        return self.sessions.get(user_id)

    def has_session(self, user_id: str) -> bool:
        return user_id in self.sessions


# Prompt de sistema para adicionar ao chat do Iudex
SEI_SYSTEM_PROMPT = """Você tem acesso a 52 ferramentas para automação completa do SEI (Sistema Eletrônico de Informações).

CAPACIDADES:
- Autenticação: login, logout, sessão
- Processos: criar, buscar, abrir, tramitar, concluir, reabrir, relacionar
- Documentos: criar, listar, obter, upload (arquivo ou base64), assinar, cancelar
- Download: processo completo (PDF/ZIP), documento individual
- Blocos: criar, listar, adicionar/remover documentos, disponibilizar, assinar bloco
- Anotações: adicionar, listar
- Marcadores: adicionar, remover
- Prazos: definir prazo
- Ciência: registrar ciência em documento
- Publicação: agendar publicação
- Listagens: tipos de documento/processo, unidades, usuários, hipóteses legais, marcadores
- Controle de acesso: conceder/revogar acesso
- Navegação: screenshot, snapshot, página atual, navegar, clicar, digitar, selecionar, aguardar

REGRAS:
1. Sempre confirme ações destrutivas antes de executar
2. Se o usuário não estiver logado, peça para fazer login primeiro
3. Formate números de processo corretamente (ex: 5030.01.0001234/2025-00)
4. Seja conciso nas respostas
5. Se uma operação falhar, explique o erro de forma clara
6. Use sei_list_* para descobrir tipos, unidades, etc. disponíveis"""
