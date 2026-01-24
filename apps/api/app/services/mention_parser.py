import re
from typing import Tuple, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from loguru import logger

from app.core.config import settings
from app.models.document import Document
from app.models.library import LibraryItem, Librarian

class MentionService:
    """
    Serviço para processar menções no chat (formato @[Nome](id:type))
    e injetar conteúdo no contexto do LLM.
    """
    
    # Regex para capturar @[Nome](id:type)
    MENTION_PATTERN = r"@\[(.*?)\]\((.*?):(.*?)\)"
    
    # Limites
    MAX_MENTIONS = settings.MENTION_MAX_ITEMS
    MAX_CONTENT_PER_MENTION = settings.MENTION_MAX_CONTENT_CHARS

    async def parse_mentions(
        self, 
        text: str, 
        db: AsyncSession, 
        user_id: str,
        sticky_docs: Optional[List[dict]] = None
    ) -> Tuple[str, str, List[dict]]:
        """
        Analisa menções no texto + sticky context.
        """
        matches = re.findall(self.MENTION_PATTERN, text)
        
        # Combinar menções da mensagem com sticky context
        # Sticky docs vêm como dicts {id, type, name}
        # Precisamos normalizar para tuplas (name, id, type) para processamento unificado
        all_items = list(matches)
        
        if sticky_docs:
            for d in sticky_docs:
                # Evitar duplicata se o usuário mencionar algo que já está sticky
                if not any(m[1] == d['id'] for m in matches):
                    all_items.append((d['name'], d['id'], d['type']))

        if not all_items:
            return text, "", []

        if len(all_items) > self.MAX_MENTIONS:
             raise ValueError(f"Muitas menções! O limite é {self.MAX_MENTIONS} documentos por vez.")

        system_context_parts = []
        mentions_metadata = []
        
        replacements = {} # Apenas para as menções explícitas no texto

        for name, item_id, item_type in all_items:
            content = None
            source_type = "unknown"
            
            try:
                if item_type == 'doc':
                    # Documento
                    result = await db.execute(
                        select(Document).where(Document.id == item_id, Document.user_id == user_id)
                    )
                    doc = result.scalars().first()
                    if doc:
                        content = doc.extracted_text or doc.content
                        source_type = "Documento"
                        
                elif item_type == 'lib':
                    # Item da Biblioteca
                    result = await db.execute(
                        select(LibraryItem).where(LibraryItem.id == item_id, LibraryItem.user_id == user_id)
                    )
                    item = result.scalars().first()
                    if item:
                        # Se for documento/modelo linkado
                        if item.resource_id: 
                             doc_res = await db.execute(
                                select(Document).where(Document.id == item.resource_id)
                             )
                             linked_doc = doc_res.scalars().first()
                             if linked_doc:
                                 content = linked_doc.extracted_text or linked_doc.content
                        
                        # Se não tiver resource_id ou não achou doc, usa descrição
                        if not content:
                            content = item.description
                        
                        # Fallback final: se não tem descrição nem doc linkado
                        if not content:
                            content = (
                                f"AVISO DO SISTEMA: O item da biblioteca '{item.name}' foi referenciado, "
                                "mas não possui descrição textual nem documento vinculado válido acessível. "
                                "O usuário pode ter esquecido de adicionar o conteúdo."
                            )

                        source_type = "Biblioteca"

                if content:
                    # Limitar tamanho do conteúdo
                    if len(content) > self.MAX_CONTENT_PER_MENTION:
                         content = content[:self.MAX_CONTENT_PER_MENTION] + "\n...[TRUNCADO PELO LIMITE DE SISTEMA]..."

                    context_block = (
                        f"--- INÍCIO DO CONTEXTO REFERENCIADO: {name} ({source_type}) ---\n"
                        f"{content}\n"
                        f"--- FIM DO CONTEXTO REFERENCIADO ---\n"
                    )
                    system_context_parts.append(context_block)
                    
                    mentions_metadata.append({
                        "id": item_id,
                        "type": item_type,
                        "name": name,
                        "found": True
                    })
                else:
                    mentions_metadata.append({
                        "id": item_id,
                        "type": item_type,
                        "name": name,
                        "found": False,
                        "error": "Conteúdo não encontrado ou sem permissão"
                    })

            except Exception as e:
                logger.error(f"Erro ao processar menção {name} ({item_id}): {e}")
                mentions_metadata.append({
                    "id": item_id,
                    "type": item_type,
                    "name": name,
                    "error": str(e)
                })

            # Preparar substituição visual
            full_match = f"@[{name}]({item_id}:{item_type})"
            replacements[full_match] = f"@{name}"

        # 1. Limpar texto (visual)
        clean_text = text
        for old, new in replacements.items():
            clean_text = clean_text.replace(old, new)

        # 2. Montar contexto do sistema
        system_context = "\n".join(system_context_parts)

        return clean_text, system_context, mentions_metadata
