from typing import Tuple, Optional, Dict, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models.document import Document
from app.models.library import LibraryItem, LibraryItemType

class CommandService:
    """
    Serviço para processar Slash Commands (/comando) no chat.
    """

    async def parse_command(self, text: str, db: AsyncSession, user_id: str, chat_context: Dict) -> Tuple[Optional[str], Optional[str]]:
        """
        Analisa se a mensagem começa com um comando.
        Retorna (resposta_sistema, erro).
        Se não for comando, retorna (None, None).
        """
        if not text.startswith("/"):
            return None, None

        parts = text.split(" ", 1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if command == "/list":
            return await self._handle_list(db, user_id), None
        
        elif command == "/use":
            return await self._handle_use(args, chat_context, db, user_id), None
            
        elif command == "/templates":
            return self._handle_templates(args, chat_context), None

        elif command == "/template_id":
            return await self._handle_template_id(args, chat_context, db, user_id), None

        elif command == "/template_doc":
            return await self._handle_template_doc(args, chat_context, db, user_id), None

        elif command == "/template_filters":
            return self._handle_template_filters(args, chat_context), None

        elif command == "/template_clear":
            return self._handle_template_clear(chat_context), None

        elif command == "/clear":
            return self._handle_clear(chat_context), None
            
        elif command == "/help":
            return self._handle_help(), None

        # Comando desconhecido: ignora e trata como texto normal ou retorna aviso?
        # Por enquanto, se começa com /, avisamos.
        return None, f"Comando '{command}' desconhecido. Tente /help."

    async def _handle_list(self, db: AsyncSession, user_id: str) -> str:
        """Lista documentos e itens da biblioteca recentes"""
        # Buscar 5 docs recentes
        docs_res = await db.execute(
            select(Document).where(Document.user_id == user_id).order_by(Document.created_at.desc()).limit(5)
        )
        docs = docs_res.scalars().all()
        
        # Buscar 5 itens lib recentes
        lib_res = await db.execute(
             select(LibraryItem).where(LibraryItem.user_id == user_id).order_by(LibraryItem.created_at.desc()).limit(5)
        )
        libs = lib_res.scalars().all()

        msg = ["**Arquivos Recentes:**"]
        for d in docs: msg.append(f"- {d.name} (id: {d.id})")
        
        msg.append("\n**Biblioteca Recente:**")
        for l in libs: msg.append(f"- {l.name} (id: {l.id})")
        
        return "\n".join(msg)

    async def _handle_use(self, args: str, chat_context: Dict, db: AsyncSession, user_id: str) -> str:
        """Fixa um contexto (Sticky Context)"""
        # Espera formato @[Nome](id) ou apenas nome parcial
        # Por simplificação, vamos focar no formato de menção padrão gerado pelo frontend
        import re
        match = re.search(r"@\[(.*?)\]\((.*?):(.*?)\)", args)
        
        if not match:
            return "Formato inválido. Use a menção automática: /use @[Nome](id:type)"
        
        name, item_id, item_type = match.groups()
        
        # Buscar conteúdo para confirmar existência
        content = None
        if item_type == 'doc':
             res = await db.execute(select(Document).where(Document.id == item_id, Document.user_id == user_id))
             item = res.scalars().first()
             if item: content = item.extracted_text or item.content
        elif item_type == 'lib':
             res = await db.execute(select(LibraryItem).where(LibraryItem.id == item_id, LibraryItem.user_id == user_id))
             item = res.scalars().first()
             if item: content = item.description

        if not content:
            return f"Item '{name}' não encontrado ou sem conteúdo."

        # Adicionar ao sticky context
        sticky = chat_context.get("sticky_docs", [])
        
        # Verificar duplicatas
        if any(s['id'] == item_id for s in sticky):
            return f"Item '{name}' já está fixado no contexto."
            
        sticky.append({
            "id": item_id,
            "type": item_type,
            "name": name,
            "preview": content[:200] + "..." # Apenas para referencia visual se precisar
        })
        
        # Atualiza o contexto (a persistência deve ser feita pelo chamador no DB)
        chat_context["sticky_docs"] = sticky
        return f"✅ Contexto fixado: **{name}**. Ele será enviado em todas as mensagens até usar /clear."

    def _handle_clear(self, chat_context: Dict) -> str:
        if "sticky_docs" in chat_context:
            del chat_context["sticky_docs"]
            return "Contexto fixado limpo com sucesso."
        return "Não havia contexto fixado para limpar."

    def _handle_help(self) -> str:
        return """
**Comandos Disponíveis:**
- `/list`: Lista seus arquivos e modelos recentes.
- `/use @[...]`: Fixa um documento no contexto (Sticky).
- `/templates on|off`: Ativa ou desativa o RAG de modelos de peça.
- `/template_id <id|off>`: Define o template da biblioteca para estruturar a minuta (aceita @[Nome](id:lib)).
- `/template_doc <id|off>`: Define documento base (RAG) como referência estrutural (aceita @[Nome](id:doc)).
- `/template_filters tipo=<...> area=<...> rito=<...> clause=on|off`: Filtra modelos do RAG.
- `/template_clear`: Limpa configurações de templates no chat.
- `/clear`: Limpa documentos fixados.
- `/help`: Mostra esta ajuda.
        """

    def _handle_templates(self, args: str, chat_context: Dict) -> str:
        value = (args or "").strip().lower()
        if value in ("on", "true", "1", "sim", "yes", "ativar", "ativa"):
            chat_context["use_templates"] = True
            return "✅ Modelos de peça ativados para este chat."
        if value in ("off", "false", "0", "nao", "não", "desativar", "desativa"):
            chat_context["use_templates"] = False
            return "✅ Modelos de peça desativados para este chat."
        return "Uso: /templates on|off"

    async def _handle_template_id(self, args: str, chat_context: Dict, db: AsyncSession, user_id: str) -> str:
        value = (args or "").strip()
        if not value:
            current = chat_context.get("template_id")
            return f"Uso: /template_id <id|off>. Atual: {current or 'nenhum'}"
        if value.lower() in ("off", "clear", "null", "none"):
            chat_context.pop("template_id", None)
            return "✅ Template ID removido."
        import re
        match = re.search(r"@\[(.*?)\]\((.*?):(.*?)\)", value)
        if match:
            name, item_id, item_type = match.groups()
            if item_type != "lib":
                return "Formato inválido. Use um item da biblioteca: /template_id @[Nome](id:lib)"
            res = await db.execute(
                select(LibraryItem).where(LibraryItem.id == item_id, LibraryItem.user_id == user_id)
            )
            item = res.scalars().first()
            if not item:
                return f"Template '{name}' não encontrado ou sem permissão."
            if item.type != LibraryItemType.MODEL:
                return f"Item '{name}' não é um template de modelo."
            chat_context["template_id"] = item.id
            return f"✅ Template ID definido: {item.name}"
        chat_context["template_id"] = value
        return f"✅ Template ID definido: {value}"

    async def _handle_template_doc(self, args: str, chat_context: Dict, db: AsyncSession, user_id: str) -> str:
        value = (args or "").strip()
        if not value:
            current = chat_context.get("template_document_id")
            return f"Uso: /template_doc <id|off>. Atual: {current or 'nenhum'}"
        if value.lower() in ("off", "clear", "null", "none"):
            chat_context.pop("template_document_id", None)
            return "✅ Documento base removido."
        import re
        match = re.search(r"@\[(.*?)\]\((.*?):(.*?)\)", value)
        if match:
            name, item_id, item_type = match.groups()
            if item_type != "doc":
                return "Formato inválido. Use um documento: /template_doc @[Nome](id:doc)"
            res = await db.execute(
                select(Document).where(Document.id == item_id, Document.user_id == user_id)
            )
            doc = res.scalars().first()
            if not doc:
                return f"Documento '{name}' não encontrado ou sem permissão."
            chat_context["template_document_id"] = doc.id
            return f"✅ Documento base definido: {doc.name}"
        chat_context["template_document_id"] = value
        return f"✅ Documento base definido: {value}"

    def _handle_template_filters(self, args: str, chat_context: Dict) -> str:
        tokens = [t for t in (args or "").split() if "=" in t]
        if not tokens:
            current = chat_context.get("template_filters", {})
            return f"Uso: /template_filters tipo=<...> area=<...> rito=<...> clause=on|off. Atual: {current or 'nenhum'}"

        filters = dict(chat_context.get("template_filters") or {})
        for token in tokens:
            key, value = token.split("=", 1)
            key = key.strip().lower()
            value = value.strip()
            if not value:
                continue
            if key in ("tipo", "tipo_peca", "tipos"):
                filters["tipo_peca"] = value
            elif key == "area":
                filters["area"] = value
            elif key == "rito":
                filters["rito"] = value
            elif key in ("clause", "clause_bank", "apenas_clause_bank"):
                filters["apenas_clause_bank"] = value.lower() in ("on", "true", "1", "sim", "yes")

        chat_context["template_filters"] = filters
        return f"✅ Filtros de modelo atualizados: {filters}"

    def _handle_template_clear(self, chat_context: Dict) -> str:
        for key in ("template_id", "template_document_id", "template_filters"):
            chat_context.pop(key, None)
        chat_context["use_templates"] = False
        return "✅ Configurações de templates limpas."
