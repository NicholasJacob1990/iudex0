from typing import Tuple, Optional, Dict, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models.document import Document
from app.models.library import LibraryItem

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
- `/clear`: Limpa documentos fixados.
- `/help`: Mostra esta ajuda.
        """
