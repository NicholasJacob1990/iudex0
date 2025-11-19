"""
Processador de Documentos com Suporte a Contexto Ilimitado
Sistema que divide documentos grandes em chunks e processa em paralelo
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import hashlib
from loguru import logger

from app.core.config import settings


@dataclass
class DocumentChunk:
    """Chunk de documento"""
    id: str
    content: str
    position: int
    metadata: Dict[str, Any]
    embedding: Optional[List[float]] = None
    
    @property
    def token_count(self) -> int:
        """Estima número de tokens (1 token ≈ 4 caracteres)"""
        return len(self.content) // 4


@dataclass
class ProcessedDocument:
    """Documento processado"""
    document_id: str
    original_size: int
    chunks: List[DocumentChunk]
    total_tokens: int
    extracted_text: str
    metadata: Dict[str, Any]


class DocumentChunker:
    """
    Divide documentos grandes em chunks semânticos
    Mantém contexto entre chunks para não perder informação
    """
    
    def __init__(
        self,
        chunk_size: int = 4000,  # tokens por chunk
        overlap: int = 200,  # overlap entre chunks
    ):
        self.chunk_size = chunk_size
        self.overlap = overlap
        logger.info(f"DocumentChunker inicializado - Chunk size: {chunk_size}, Overlap: {overlap}")
    
    def chunk_by_tokens(self, text: str, metadata: Dict[str, Any] = None) -> List[DocumentChunk]:
        """
        Divide texto em chunks baseado em tokens
        Mantém overlap para preservar contexto
        """
        if metadata is None:
            metadata = {}
        
        # Estimar tokens (1 token ≈ 4 caracteres)
        chars_per_chunk = self.chunk_size * 4
        chars_overlap = self.overlap * 4
        
        chunks: List[DocumentChunk] = []
        position = 0
        start = 0
        
        while start < len(text):
            # Calcular fim do chunk
            end = start + chars_per_chunk
            
            # Se não é o último chunk, tentar quebrar em parágrafo ou frase
            if end < len(text):
                # Procurar quebra de parágrafo
                paragraph_break = text.rfind('\n\n', start + chars_per_chunk - 500, end + 500)
                if paragraph_break > start:
                    end = paragraph_break
                else:
                    # Procurar quebra de frase
                    sentence_break = text.rfind('. ', start + chars_per_chunk - 200, end + 200)
                    if sentence_break > start:
                        end = sentence_break + 1
            
            # Extrair chunk
            chunk_text = text[start:end].strip()
            
            if chunk_text:
                chunk_id = self._generate_chunk_id(chunk_text, position)
                
                chunks.append(DocumentChunk(
                    id=chunk_id,
                    content=chunk_text,
                    position=position,
                    metadata={
                        **metadata,
                        "start_char": start,
                        "end_char": end,
                        "chunk_index": position,
                    }
                ))
                
                position += 1
            
            # Próximo chunk com overlap
            start = end - chars_overlap if end < len(text) else end
            
            # Evitar loop infinito
            if start >= len(text):
                break
        
        logger.info(f"Documento dividido em {len(chunks)} chunks")
        return chunks
    
    def chunk_by_pages(
        self,
        pages: List[str],
        pages_per_chunk: int = 10,
        metadata: Dict[str, Any] = None
    ) -> List[DocumentChunk]:
        """
        Divide documento em chunks baseado em páginas
        Útil para PDFs onde queremos manter páginas juntas
        """
        if metadata is None:
            metadata = {}
        
        chunks: List[DocumentChunk] = []
        
        for i in range(0, len(pages), pages_per_chunk):
            chunk_pages = pages[i:i + pages_per_chunk]
            chunk_text = "\n\n".join(chunk_pages)
            
            chunk_id = self._generate_chunk_id(chunk_text, i // pages_per_chunk)
            
            chunks.append(DocumentChunk(
                id=chunk_id,
                content=chunk_text,
                position=i // pages_per_chunk,
                metadata={
                    **metadata,
                    "page_start": i,
                    "page_end": min(i + pages_per_chunk, len(pages)),
                    "num_pages": len(chunk_pages),
                }
            ))
        
        logger.info(f"Documento dividido em {len(chunks)} chunks por página")
        return chunks
    
    def chunk_semantically(
        self,
        text: str,
        section_markers: List[str] = None,
        metadata: Dict[str, Any] = None
    ) -> List[DocumentChunk]:
        """
        Divide documento em chunks semânticos (por seções)
        Identifica seções baseado em marcadores
        """
        if section_markers is None:
            # Marcadores padrão para documentos jurídicos
            section_markers = [
                "RELATÓRIO",
                "FUNDAMENTAÇÃO",
                "VOTO",
                "DECISÃO",
                "DISPOSITIVO",
                "EMENTA",
                "DOS FATOS",
                "DO DIREITO",
                "I -",
                "II -",
                "III -",
            ]
        
        if metadata is None:
            metadata = {}
        
        chunks: List[DocumentChunk] = []
        current_section = ""
        current_content = []
        position = 0
        
        lines = text.split('\n')
        
        for line in lines:
            # Verificar se linha é um marcador de seção
            is_section = any(line.strip().upper().startswith(marker) for marker in section_markers)
            
            if is_section and current_content:
                # Salvar seção anterior
                section_text = '\n'.join(current_content).strip()
                if section_text:
                    chunk_id = self._generate_chunk_id(section_text, position)
                    chunks.append(DocumentChunk(
                        id=chunk_id,
                        content=section_text,
                        position=position,
                        metadata={
                            **metadata,
                            "section": current_section,
                            "semantic_chunk": True,
                        }
                    ))
                    position += 1
                
                # Iniciar nova seção
                current_section = line.strip()
                current_content = [line]
            else:
                current_content.append(line)
        
        # Adicionar última seção
        if current_content:
            section_text = '\n'.join(current_content).strip()
            if section_text:
                chunk_id = self._generate_chunk_id(section_text, position)
                chunks.append(DocumentChunk(
                    id=chunk_id,
                    content=section_text,
                    position=position,
                    metadata={
                        **metadata,
                        "section": current_section,
                        "semantic_chunk": True,
                    }
                ))
        
        # Se ficou muito grande, dividir novamente por tokens
        final_chunks = []
        for chunk in chunks:
            if chunk.token_count > self.chunk_size:
                sub_chunks = self.chunk_by_tokens(
                    chunk.content,
                    {**chunk.metadata, "parent_chunk_id": chunk.id}
                )
                final_chunks.extend(sub_chunks)
            else:
                final_chunks.append(chunk)
        
        logger.info(f"Documento dividido em {len(final_chunks)} chunks semânticos")
        return final_chunks
    
    def _generate_chunk_id(self, content: str, position: int) -> str:
        """Gera ID único para chunk"""
        content_hash = hashlib.md5(content.encode()).hexdigest()[:8]
        return f"chunk-{position}-{content_hash}"


class UnlimitedContextProcessor:
    """
    Processador que suporta contexto ilimitado
    
    Estratégias:
    1. Map-Reduce: Processa chunks em paralelo e consolida
    2. Hierarchical: Cria resumos hierárquicos
    3. Rolling: Mantém janela deslizante de contexto
    """
    
    def __init__(self):
        self.chunker = DocumentChunker()
        logger.info("UnlimitedContextProcessor inicializado")
    
    async def process_large_document(
        self,
        text: str,
        task: str,
        strategy: str = "map-reduce",
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Processa documento grande com estratégia escolhida
        
        Args:
            text: Texto completo do documento
            task: Tarefa a realizar (resumir, analisar, etc)
            strategy: "map-reduce", "hierarchical", ou "rolling"
            metadata: Metadados adicionais
        """
        logger.info(f"Processando documento grande - Estratégia: {strategy}, Tamanho: {len(text)} chars")
        
        if strategy == "map-reduce":
            return await self._process_map_reduce(text, task, metadata)
        elif strategy == "hierarchical":
            return await self._process_hierarchical(text, task, metadata)
        elif strategy == "rolling":
            return await self._process_rolling(text, task, metadata)
        else:
            raise ValueError(f"Estratégia desconhecida: {strategy}")
    
    async def _process_map_reduce(
        self,
        text: str,
        task: str,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Map-Reduce: Processa cada chunk independentemente e depois consolida
        Ideal para: resumos, extração de informações
        """
        logger.info("Executando estratégia Map-Reduce")
        
        # 1. Dividir em chunks
        chunks = self.chunker.chunk_by_tokens(text, metadata)
        
        # 2. MAP: Processar cada chunk (em paralelo)
        # TODO: Implementar processamento paralelo com asyncio.gather
        chunk_results = []
        for chunk in chunks:
            # Aqui chamaria o agente IA para processar o chunk
            # result = await ai_agent.process(chunk.content, task)
            result = {
                "chunk_id": chunk.id,
                "position": chunk.position,
                "summary": f"[Resumo do chunk {chunk.position}]",  # Placeholder
            }
            chunk_results.append(result)
        
        # 3. REDUCE: Consolidar resultados
        # TODO: Chamar IA para consolidar todos os resumos
        final_result = {
            "strategy": "map-reduce",
            "total_chunks": len(chunks),
            "chunk_results": chunk_results,
            "consolidated": "[Resultado consolidado de todos os chunks]",  # Placeholder
            "metadata": {
                "original_size": len(text),
                "total_tokens": sum(c.token_count for c in chunks),
            }
        }
        
        logger.info(f"Map-Reduce concluído - {len(chunks)} chunks processados")
        return final_result
    
    async def _process_hierarchical(
        self,
        text: str,
        task: str,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Hierarchical: Cria resumos em níveis, cada nível resume o anterior
        Ideal para: análise detalhada, manutenção de contexto global
        """
        logger.info("Executando estratégia Hierarchical")
        
        levels = []
        current_text = text
        level = 0
        
        # Continuar até conseguir processar em um único chunk
        while len(current_text) > self.chunker.chunk_size * 4:
            logger.info(f"Nível {level}: {len(current_text)} chars")
            
            # Dividir em chunks
            chunks = self.chunker.chunk_by_tokens(current_text, metadata)
            
            # Resumir cada chunk
            summaries = []
            for chunk in chunks:
                # TODO: Chamar IA para resumir
                summary = f"[Resumo do chunk {chunk.position}]"  # Placeholder
                summaries.append(summary)
            
            # Consolidar resumos deste nível
            current_text = "\n\n".join(summaries)
            levels.append({
                "level": level,
                "num_chunks": len(chunks),
                "summaries": summaries,
            })
            
            level += 1
            
            # Proteção contra loop infinito
            if level > 10:
                break
        
        # Processar nível final
        # TODO: Chamar IA para análise final
        final_analysis = "[Análise final do documento completo]"  # Placeholder
        
        result = {
            "strategy": "hierarchical",
            "num_levels": len(levels),
            "levels": levels,
            "final_analysis": final_analysis,
            "metadata": {
                "original_size": len(text),
            }
        }
        
        logger.info(f"Hierarchical concluído - {len(levels)} níveis processados")
        return result
    
    async def _process_rolling(
        self,
        text: str,
        task: str,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Rolling Window: Processa com janela deslizante mantendo contexto
        Ideal para: geração de documento contínuo, manutenção de narrativa
        """
        logger.info("Executando estratégia Rolling Window")
        
        chunks = self.chunker.chunk_by_tokens(text, metadata)
        
        results = []
        context_window = []
        window_size = 3  # Manter últimos 3 chunks no contexto
        
        for i, chunk in enumerate(chunks):
            logger.info(f"Processando chunk {i+1}/{len(chunks)} com contexto")
            
            # Montar contexto (chunks anteriores)
            context = "\n\n".join([c.content for c in context_window])
            
            # Processar chunk com contexto
            # TODO: Chamar IA com contexto
            result = {
                "chunk_id": chunk.id,
                "position": chunk.position,
                "context_size": len(context_window),
                "result": f"[Resultado do chunk {i} com contexto]",  # Placeholder
            }
            results.append(result)
            
            # Atualizar janela de contexto
            context_window.append(chunk)
            if len(context_window) > window_size:
                context_window.pop(0)
        
        # Consolidar resultados mantendo a narrativa
        final_result = {
            "strategy": "rolling",
            "total_chunks": len(chunks),
            "window_size": window_size,
            "results": results,
            "consolidated": "[Resultado consolidado mantendo narrativa]",  # Placeholder
            "metadata": {
                "original_size": len(text),
                "total_tokens": sum(c.token_count for c in chunks),
            }
        }
        
        logger.info(f"Rolling Window concluído - {len(chunks)} chunks processados")
        return final_result


# Funções auxiliares para extração de texto de diferentes formatos

async def extract_text_from_pdf(file_path: str) -> str:
    """Extrai texto de PDF usando pypdf"""
    # TODO: Implementar com pypdf ou pdfplumber
    logger.info(f"Extraindo texto de PDF: {file_path}")
    return "[Texto extraído do PDF]"  # Placeholder


async def extract_text_from_docx(file_path: str) -> str:
    """Extrai texto de DOCX usando python-docx"""
    # TODO: Implementar com python-docx
    logger.info(f"Extraindo texto de DOCX: {file_path}")
    return "[Texto extraído do DOCX]"  # Placeholder


async def extract_text_from_image(file_path: str) -> str:
    """Extrai texto de imagem usando OCR"""
    # TODO: Implementar com pytesseract
    logger.info(f"Extraindo texto de imagem: {file_path}")
    return "[Texto extraído da imagem via OCR]"  # Placeholder

