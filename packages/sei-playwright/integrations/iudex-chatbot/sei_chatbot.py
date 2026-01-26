"""
SEI Chatbot Integration para Iudex
Suporta GPT, Claude e Gemini como LLM

Exemplo de uso:
    from sei_chatbot import SEIChatbot

    # Com OpenAI
    chatbot = SEIChatbot(
        sei_api_url="http://localhost:3001",
        provider="openai",
        api_key="sk-..."
    )

    # Com Anthropic Claude
    chatbot = SEIChatbot(
        sei_api_url="http://localhost:3001",
        provider="anthropic",
        api_key="sk-ant-..."
    )

    # Com Google Gemini
    chatbot = SEIChatbot(
        sei_api_url="http://localhost:3001",
        provider="google",
        api_key="AIza..."
    )

    response = await chatbot.chat("user123", "tramite o processo X para GENSU")
"""

import httpx
import json
from typing import Optional, Literal
from abc import ABC, abstractmethod

# Carregar definições de funções
import os
FUNCTIONS_PATH = os.path.join(os.path.dirname(__file__), "openai-functions.json")
with open(FUNCTIONS_PATH) as f:
    SEI_FUNCTIONS = json.load(f)["functions"]


# ============================================================================
# LLM Providers
# ============================================================================

class LLMProvider(ABC):
    """Interface abstrata para provedores de LLM"""

    @abstractmethod
    async def chat_with_functions(
        self,
        messages: list,
        functions: list
    ) -> tuple[Optional[str], Optional[dict]]:
        """
        Envia mensagens e retorna resposta ou chamada de função.
        Returns: (response_text, function_call) - um dos dois será None
        """
        pass


class OpenAIProvider(LLMProvider):
    """Provider para OpenAI GPT"""

    def __init__(self, api_key: str, model: str = "gpt-4o"):
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

    async def chat_with_functions(self, messages, functions):
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            functions=functions,
            function_call="auto"
        )

        msg = response.choices[0].message

        if msg.function_call:
            return None, {
                "name": msg.function_call.name,
                "arguments": json.loads(msg.function_call.arguments)
            }

        return msg.content, None


class AnthropicProvider(LLMProvider):
    """Provider para Anthropic Claude"""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        from anthropic import AsyncAnthropic
        self.client = AsyncAnthropic(api_key=api_key)
        self.model = model

    def _convert_functions_to_tools(self, functions: list) -> list:
        """Converte formato OpenAI functions para Anthropic tools"""
        tools = []
        for func in functions:
            tools.append({
                "name": func["name"],
                "description": func["description"],
                "input_schema": func["parameters"]
            })
        return tools

    def _convert_messages(self, messages: list) -> tuple[str, list]:
        """Converte mensagens para formato Anthropic"""
        system = ""
        converted = []

        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            elif msg["role"] == "function":
                # Claude usa tool_result
                converted.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.get("tool_use_id", "call_1"),
                        "content": msg["content"]
                    }]
                })
            elif msg["role"] == "assistant" and msg.get("function_call"):
                # Claude usa tool_use
                converted.append({
                    "role": "assistant",
                    "content": [{
                        "type": "tool_use",
                        "id": "call_1",
                        "name": msg["function_call"]["name"],
                        "input": json.loads(msg["function_call"]["arguments"])
                            if isinstance(msg["function_call"]["arguments"], str)
                            else msg["function_call"]["arguments"]
                    }]
                })
            else:
                converted.append({
                    "role": msg["role"],
                    "content": msg["content"] or ""
                })

        return system, converted

    async def chat_with_functions(self, messages, functions):
        tools = self._convert_functions_to_tools(functions)
        system, converted_messages = self._convert_messages(messages)

        response = await self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system,
            messages=converted_messages,
            tools=tools
        )

        # Verificar se há tool_use na resposta
        for block in response.content:
            if block.type == "tool_use":
                return None, {
                    "name": block.name,
                    "arguments": block.input,
                    "tool_use_id": block.id
                }

        # Resposta de texto
        text = ""
        for block in response.content:
            if block.type == "text":
                text += block.text

        return text, None


class GoogleProvider(LLMProvider):
    """Provider para Google Gemini"""

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        self.model_name = model
        self.genai = genai

    def _convert_functions_to_tools(self, functions: list) -> list:
        """Converte para formato Gemini function declarations"""
        from google.generativeai.types import FunctionDeclaration, Tool

        declarations = []
        for func in functions:
            # Gemini precisa de parâmetros no formato específico
            params = func["parameters"].copy()
            declarations.append(
                FunctionDeclaration(
                    name=func["name"],
                    description=func["description"],
                    parameters=params
                )
            )

        return [Tool(function_declarations=declarations)]

    def _build_history(self, messages: list) -> tuple[str, list]:
        """Converte mensagens para formato Gemini"""
        system = ""
        history = []

        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            elif msg["role"] == "user":
                history.append({"role": "user", "parts": [msg["content"]]})
            elif msg["role"] == "assistant":
                if msg.get("function_call"):
                    # Gemini representa chamadas de função diferente
                    history.append({
                        "role": "model",
                        "parts": [{
                            "function_call": {
                                "name": msg["function_call"]["name"],
                                "args": json.loads(msg["function_call"]["arguments"])
                                    if isinstance(msg["function_call"]["arguments"], str)
                                    else msg["function_call"]["arguments"]
                            }
                        }]
                    })
                else:
                    history.append({"role": "model", "parts": [msg["content"] or ""]})
            elif msg["role"] == "function":
                history.append({
                    "role": "user",
                    "parts": [{
                        "function_response": {
                            "name": msg["name"],
                            "response": {"result": msg["content"]}
                        }
                    }]
                })

        return system, history

    async def chat_with_functions(self, messages, functions):
        tools = self._convert_functions_to_tools(functions)
        system, history = self._build_history(messages)

        model = self.genai.GenerativeModel(
            model_name=self.model_name,
            tools=tools,
            system_instruction=system if system else None
        )

        chat = model.start_chat(history=history[:-1] if history else [])

        # Última mensagem
        last_msg = history[-1] if history else {"parts": [""]}
        response = await chat.send_message_async(last_msg["parts"])

        # Verificar function call
        for part in response.parts:
            if hasattr(part, "function_call") and part.function_call:
                fc = part.function_call
                return None, {
                    "name": fc.name,
                    "arguments": dict(fc.args)
                }

        return response.text, None


# ============================================================================
# SEI Chatbot
# ============================================================================

ProviderType = Literal["openai", "anthropic", "google"]

# Modelos padrão por provider
DEFAULT_MODELS = {
    "openai": "gpt-4o",
    "anthropic": "claude-sonnet-4-20250514",
    "google": "gemini-2.0-flash"
}


class SEIChatbot:
    """Chatbot que usa LLM para interpretar comandos SEI"""

    def __init__(
        self,
        sei_api_url: str,
        provider: ProviderType = "openai",
        api_key: str = "",
        model: Optional[str] = None,
        sei_api_key: str = "",
        # Aliases para compatibilidade
        openai_api_key: str = "",
    ):
        self.sei_api_url = sei_api_url.rstrip("/")
        self.sei_api_key = sei_api_key

        # Resolver API key (aceita ambos formatos)
        resolved_key = api_key or openai_api_key
        if not resolved_key:
            raise ValueError(f"API key para {provider} é obrigatória")

        # Modelo padrão se não especificado
        resolved_model = model or DEFAULT_MODELS.get(provider, "")

        # Criar provider
        self.provider = self._create_provider(provider, resolved_key, resolved_model)
        self.provider_name = provider

        # Sessões e históricos por usuário
        self.sessions: dict[str, str] = {}  # user_id -> session_id
        self.conversations: dict[str, list] = {}  # user_id -> messages
        self.tool_use_ids: dict[str, str] = {}  # user_id -> last tool_use_id

    def _create_provider(self, provider: str, api_key: str, model: str) -> LLMProvider:
        """Factory para criar provider"""
        if provider == "openai":
            return OpenAIProvider(api_key, model)
        elif provider == "anthropic":
            return AnthropicProvider(api_key, model)
        elif provider == "google":
            return GoogleProvider(api_key, model)
        else:
            raise ValueError(f"Provider desconhecido: {provider}")

    @property
    def system_prompt(self) -> str:
        return """Você é um assistente especializado no SEI (Sistema Eletrônico de Informações).

Você pode ajudar os usuários a:
- Criar, consultar e tramitar processos
- Criar, assinar e gerenciar documentos
- Gerenciar blocos de assinatura
- Consultar andamentos e histórico

REGRAS:
1. Sempre confirme ações destrutivas antes de executar
2. Se o usuário não estiver logado, peça para fazer login primeiro
3. Formate números de processo corretamente (ex: 5030.01.0001234/2025-00)
4. Seja conciso nas respostas
5. Se uma operação falhar, explique o erro de forma clara

IMPORTANTE: Você tem acesso a funções que executam ações reais no SEI. Use-as quando o usuário pedir."""

    async def chat(self, user_id: str, message: str) -> str:
        """Processa mensagem do usuário e retorna resposta"""

        # Inicializar histórico se necessário
        if user_id not in self.conversations:
            self.conversations[user_id] = [
                {"role": "system", "content": self.system_prompt}
            ]

        # Adicionar mensagem do usuário
        self.conversations[user_id].append({
            "role": "user",
            "content": message
        })

        # Chamar LLM com functions
        response_text, function_call = await self.provider.chat_with_functions(
            self.conversations[user_id],
            SEI_FUNCTIONS
        )

        # Se LLM quer chamar uma função
        if function_call:
            function_name = function_call["name"]
            function_args = function_call["arguments"]
            tool_use_id = function_call.get("tool_use_id", "call_1")

            # Guardar tool_use_id para Claude
            self.tool_use_ids[user_id] = tool_use_id

            # Executar função
            result = await self._execute_function(user_id, function_name, function_args)

            # Adicionar ao histórico
            self.conversations[user_id].append({
                "role": "assistant",
                "content": None,
                "function_call": {
                    "name": function_name,
                    "arguments": json.dumps(function_args, ensure_ascii=False)
                }
            })
            self.conversations[user_id].append({
                "role": "function",
                "name": function_name,
                "content": json.dumps(result, ensure_ascii=False),
                "tool_use_id": tool_use_id
            })

            # Pedir ao LLM para formatar a resposta
            final_text, _ = await self.provider.chat_with_functions(
                self.conversations[user_id],
                SEI_FUNCTIONS
            )

            response_text = final_text or "Operação concluída."

        # Adicionar resposta ao histórico
        self.conversations[user_id].append({
            "role": "assistant",
            "content": response_text
        })

        return response_text

    async def _execute_function(
        self,
        user_id: str,
        function_name: str,
        args: dict
    ) -> dict:
        """Executa função chamando a API SEI"""

        session_id = self.sessions.get(user_id)

        try:
            result = await self._call_sei_api(user_id, function_name, args, session_id)
            return {"success": True, "data": result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _call_sei_api(
        self,
        user_id: str,
        function_name: str,
        args: dict,
        session_id: Optional[str]
    ) -> dict:
        """Chama endpoint correspondente na API SEI"""

        headers = {
            "X-API-Key": self.sei_api_key,
            "Content-Type": "application/json"
        }

        if session_id:
            headers["X-Session-Id"] = session_id

        async with httpx.AsyncClient(timeout=60.0) as client:
            # Login
            if function_name == "sei_login":
                resp = await client.post(
                    f"{self.sei_api_url}/sessions",
                    headers=headers,
                    json={
                        "seiUrl": args["seiUrl"],
                        "usuario": args["usuario"],
                        "senha": args["senha"],
                        "orgao": args.get("orgao")
                    }
                )
                data = resp.json()
                if "sessionId" in data:
                    self.sessions[user_id] = data["sessionId"]
                return data

            # Logout
            if function_name == "sei_logout":
                sid = args.get("sessionId") or session_id
                resp = await client.delete(
                    f"{self.sei_api_url}/sessions/{sid}",
                    headers=headers
                )
                if user_id in self.sessions:
                    del self.sessions[user_id]
                return resp.json()

            # Criar processo
            if function_name == "sei_criar_processo":
                resp = await client.post(
                    f"{self.sei_api_url}/process",
                    headers=headers,
                    json={
                        "tipoProcedimento": args["tipoProcedimento"],
                        "especificacao": args["especificacao"],
                        "assuntos": args["assuntos"],
                        "interessados": args.get("interessados"),
                        "observacao": args.get("observacao"),
                        "nivelAcesso": args.get("nivelAcesso", 0)
                    }
                )
                return resp.json()

            # Consultar processo
            if function_name == "sei_consultar_processo":
                numero = args["numeroProcesso"].replace("/", "%2F")
                resp = await client.get(
                    f"{self.sei_api_url}/process/{numero}",
                    headers=headers
                )
                return resp.json()

            # Tramitar processo
            if function_name == "sei_tramitar_processo":
                numero = args["numeroProcesso"].replace("/", "%2F")
                resp = await client.post(
                    f"{self.sei_api_url}/process/{numero}/forward",
                    headers=headers,
                    json={
                        "unidadesDestino": args["unidadesDestino"],
                        "manterAberto": args.get("manterAberto", False),
                        "enviarEmailNotificacao": args.get("enviarEmail", False)
                    }
                )
                return resp.json()

            # Concluir processo
            if function_name == "sei_concluir_processo":
                numero = args["numeroProcesso"].replace("/", "%2F")
                resp = await client.post(
                    f"{self.sei_api_url}/process/{numero}/conclude",
                    headers=headers
                )
                return resp.json()

            # Reabrir processo
            if function_name == "sei_reabrir_processo":
                numero = args["numeroProcesso"].replace("/", "%2F")
                resp = await client.post(
                    f"{self.sei_api_url}/process/{numero}/reopen",
                    headers=headers
                )
                return resp.json()

            # Anexar processo
            if function_name == "sei_anexar_processo":
                numero = args["processoPrincipal"].replace("/", "%2F")
                resp = await client.post(
                    f"{self.sei_api_url}/process/{numero}/anexar",
                    headers=headers,
                    json={"processoAnexado": args["processoAnexado"]}
                )
                return resp.json()

            # Relacionar processos
            if function_name == "sei_relacionar_processos":
                numero = args["processo1"].replace("/", "%2F")
                resp = await client.post(
                    f"{self.sei_api_url}/process/{numero}/relacionar",
                    headers=headers,
                    json={"processoRelacionado": args["processo2"]}
                )
                return resp.json()

            # Atribuir processo
            if function_name == "sei_atribuir_processo":
                numero = args["numeroProcesso"].replace("/", "%2F")
                resp = await client.post(
                    f"{self.sei_api_url}/process/{numero}/atribuir",
                    headers=headers,
                    json={"usuario": args["usuario"]}
                )
                return resp.json()

            # Listar documentos
            if function_name == "sei_listar_documentos":
                numero = args["numeroProcesso"].replace("/", "%2F")
                resp = await client.get(
                    f"{self.sei_api_url}/process/{numero}/documents",
                    headers=headers
                )
                return resp.json()

            # Criar documento
            if function_name == "sei_criar_documento":
                numero = args["numeroProcesso"].replace("/", "%2F")
                resp = await client.post(
                    f"{self.sei_api_url}/process/{numero}/documents",
                    headers=headers,
                    json={
                        "idSerie": args["tipoDocumento"],
                        "descricao": args.get("descricao"),
                        "conteudoHtml": args.get("conteudo"),
                        "destinatarios": args.get("destinatarios"),
                        "nivelAcesso": args.get("nivelAcesso", 0)
                    }
                )
                return resp.json()

            # Upload documento
            if function_name == "sei_upload_documento":
                numero = args["numeroProcesso"].replace("/", "%2F")
                resp = await client.post(
                    f"{self.sei_api_url}/process/{numero}/upload",
                    headers=headers,
                    json={
                        "nomeArquivo": args["nomeArquivo"],
                        "conteudoBase64": args["conteudoBase64"],
                        "descricao": args.get("descricao")
                    }
                )
                return resp.json()

            # Assinar documento
            if function_name == "sei_assinar_documento":
                resp = await client.post(
                    f"{self.sei_api_url}/document/{args['documentoId']}/sign",
                    headers=headers,
                    json={
                        "senha": args["senha"],
                        "cargo": args.get("cargo")
                    }
                )
                return resp.json()

            # Cancelar documento
            if function_name == "sei_cancelar_documento":
                resp = await client.post(
                    f"{self.sei_api_url}/document/{args['documentoId']}/cancel",
                    headers=headers,
                    json={"motivo": args["motivo"]}
                )
                return resp.json()

            # Consultar andamentos
            if function_name == "sei_consultar_andamentos":
                numero = args["numeroProcesso"].replace("/", "%2F")
                resp = await client.get(
                    f"{self.sei_api_url}/process/{numero}/andamentos",
                    headers=headers
                )
                return resp.json()

            # Listar blocos
            if function_name == "sei_listar_blocos":
                resp = await client.get(
                    f"{self.sei_api_url}/blocos",
                    headers=headers
                )
                return resp.json()

            # Criar bloco
            if function_name == "sei_criar_bloco":
                resp = await client.post(
                    f"{self.sei_api_url}/blocos",
                    headers=headers,
                    json={
                        "descricao": args["descricao"],
                        "tipo": args.get("tipo", "assinatura")
                    }
                )
                return resp.json()

            # Adicionar documento ao bloco
            if function_name == "sei_adicionar_documento_bloco":
                resp = await client.post(
                    f"{self.sei_api_url}/bloco/{args['blocoId']}/documentos",
                    headers=headers,
                    json={"documentoId": args["documentoId"]}
                )
                return resp.json()

            # Disponibilizar bloco
            if function_name == "sei_disponibilizar_bloco":
                resp = await client.post(
                    f"{self.sei_api_url}/bloco/{args['blocoId']}/disponibilizar",
                    headers=headers,
                    json={"unidades": args.get("unidades")}
                )
                return resp.json()

            # Listar tipos de processo
            if function_name == "sei_listar_tipos_processo":
                resp = await client.get(
                    f"{self.sei_api_url}/tipos-processo",
                    headers=headers
                )
                return resp.json()

            # Listar tipos de documento
            if function_name == "sei_listar_tipos_documento":
                resp = await client.get(
                    f"{self.sei_api_url}/tipos-documento",
                    headers=headers
                )
                return resp.json()

            # Listar unidades
            if function_name == "sei_listar_unidades":
                resp = await client.get(
                    f"{self.sei_api_url}/unidades",
                    headers=headers
                )
                return resp.json()

            return {"error": f"Função desconhecida: {function_name}"}

    def clear_history(self, user_id: str):
        """Limpa histórico de conversa do usuário"""
        if user_id in self.conversations:
            self.conversations[user_id] = [
                {"role": "system", "content": self.system_prompt}
            ]
