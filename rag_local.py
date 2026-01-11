"""
RAG Local Module - Índice Efêmero para Processos (v2.0)

Este módulo permite criar índices temporários para análise de processos específicos.
Ideal para SEI, PJe, ePROC e outros sistemas processuais com múltiplos documentos.

Uso:
    from rag_local import LocalProcessIndex
    
    index = LocalProcessIndex(processo_id="SEI-12345/2024", ttl_hours=4)
    index.index_pasta("./autos_processo/")
    results = index.search("laudo pericial", top_k=5)
"""

import os
import re
import hashlib
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field

# Third-party imports
try:
    import chromadb
    from chromadb.config import Settings
    from sentence_transformers import SentenceTransformer
    from rank_bm25 import BM25Okapi
except ImportError as e:
    print(f"❌ RAG Local - Dependências faltando: {e}")
    raise

try:
    from PyPDF2 import PdfReader
except ImportError:
    PdfReader = None

from colorama import Fore, Style, init
init(autoreset=True)

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("RAGLocal")

# =============================================================================
# METADATA SCHEMA
# =============================================================================

@dataclass
class ProcessDocMetadata:
    """Metadados para documentos dentro de um processo"""
    # Identificação do processo
    processo_id: str       # Número SEI ou CNJ
    sistema: str           # SEI, PJe, eproc, SAPIENS
    
    # Identificação do documento
    doc_id: str            # ID interno do documento
    tipo_doc: str          # peticao, despacho, laudo, ata, oficio
    data_doc: str          # Data do documento
    
    # Localização
    pagina: int = 0        # Página do PDF
    volume: int = 1        # Volume
    
    # Conteúdo
    resumo_auto: str = ""  # Resumo gerado
    
    # v2.1: Alinhados com SEIMetadata para permitir joins leves
    orgao: str = ""        # PGFN, AGU, etc.
    unidade: str = ""      # Unidade organizacional
    tenant_id: str = "default"  # Multi-tenancy
    origem: str = "local"  # "local" | "global" - diferencia RAG Local vs Global
    file_path: str = ""    # Caminho absoluto do arquivo original

# =============================================================================
# LOCAL PROCESS INDEX
# =============================================================================

class LocalProcessIndex:
    """
    Índice efêmero para documentos de um processo específico.
    
    Cria um índice temporário (in-memory) para navegar nos autos de um caso,
    encontrar documentos e gerar citações auditáveis.
    """
    
    # Configurações de embedding
    EMBEDDING_MODEL = "intfloat/multilingual-e5-large"
    CHUNK_SIZE = 1500
    CHUNK_OVERLAP = 200
    
    def __init__(
        self, 
        processo_id: str, 
        sistema: str = "SEI",
        ttl_hours: int = 4,
        tenant_id: str = "default"
    ):
        """
        Inicializa índice efêmero para um processo.
        
        Args:
            processo_id: Número do processo (SEI, CNJ, etc.)
            sistema: Sistema de origem (SEI, PJe, eproc)
            ttl_hours: Tempo de vida do índice (horas)
            tenant_id: Tenant ID para isolamento (RBAC)
        """
        self.processo_id = processo_id
        self.sistema = sistema
        self.tenant_id = tenant_id
        self.created_at = datetime.now()
        self.expiry = self.created_at + timedelta(hours=ttl_hours)
        
        # ChromaDB in-memory
        self.client = chromadb.Client()
        self.collection_name = f"proc_{re.sub(r'[^a-zA-Z0-9]', '_', processo_id)}"
        self.collection = self.client.create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"}
        )
        
        # Embedding model
        logger.info(f"🔄 Carregando modelo de embeddings...")
        self.embedding_model = SentenceTransformer(self.EMBEDDING_MODEL)
        
        # BM25 index (lazy)
        self._documents = []
        self._metadatas = []
        self._bm25 = None
        
        logger.info(f"📁 Índice criado para processo: {processo_id} ({sistema})")
        logger.info(f"   Expira em: {self.expiry.strftime('%Y-%m-%d %H:%M')}")
    
    def is_expired(self) -> bool:
        """Verifica se o índice expirou"""
        return datetime.now() > self.expiry
    
    def _chunk_text(self, text: str, page_start: int = 0) -> List[Dict]:
        """Divide texto em chunks com metadados de página estimada"""
        chunks = []
        words = text.split()
        
        # Estimar ~300 palavras por página
        words_per_page = 300
        
        for i in range(0, len(words), self.CHUNK_SIZE - self.CHUNK_OVERLAP):
            chunk_words = words[i:i + self.CHUNK_SIZE]
            chunk_text = " ".join(chunk_words)
            
            # Estimar página
            word_position = i
            estimated_page = page_start + (word_position // words_per_page)
            
            chunks.append({
                "text": chunk_text,
                "page": estimated_page,
                "word_start": i,
                "word_end": i + len(chunk_words)
            })
        
        return chunks
    
    def _read_pdf_with_pages(self, file_path: str) -> List[Dict]:
        """Lê PDF mantendo informação de página"""
        if not PdfReader:
            raise ImportError("PyPDF2 não instalado")
        
        reader = PdfReader(file_path)
        pages = []
        
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            if text.strip():
                pages.append({
                    "text": text,
                    "page": i + 1
                })
        
        return pages
    
    def _detect_doc_type(self, text: str, filename: str) -> str:
        """Detecta tipo de documento a partir do conteúdo e nome"""
        filename_upper = filename.upper()
        text_peek = text[:1000].upper()
        
        patterns = {
            "peticao_inicial": ["PETIÇÃO INICIAL", "EXCELENTÍSSIMO", "AUTOR:"],
            "contestacao": ["CONTESTAÇÃO", "CONTESTANDO", "RÉU:"],
            "recurso": ["APELAÇÃO", "RECURSO", "AGRAVO", "RECORRE"],
            "sentenca": ["SENTENÇA", "JULGO", "DISPOSITIVO"],
            "acordao": ["ACÓRDÃO", "ACORDAM", "VOTO"],
            "despacho": ["DESPACHO", "INTIME-SE", "CITE-SE", "JUNTE-SE"],
            "laudo": ["LAUDO", "PERÍCIA", "PERITO"],
            "ata": ["ATA DE AUDIÊNCIA", "AUDIÊNCIA"],
            "oficio": ["OFÍCIO", "COMUNICAMOS"],
            "parecer": ["PARECER", "OPINAMOS"],
            "decisao": ["DECISÃO", "DEFIRO", "INDEFIRO"],
        }
        
        for tipo, keywords in patterns.items():
            for kw in keywords:
                if kw in filename_upper or kw in text_peek:
                    return tipo
        
        return "documento"
    
    def _extract_doc_id(self, filename: str, text: str) -> str:
        """Extrai ID do documento (SEI, Evento, etc.)"""
        # Padrão SEI: "12345678"
        sei_match = re.search(r'(\d{7,10})', filename)
        if sei_match:
            return sei_match.group(1)
        
        # Padrão PJe/eproc: "Evento 15"
        evento_match = re.search(r'[Ee]vento\s*(\d+)', filename) or re.search(r'[Ee]vento\s*(\d+)', text[:500])
        if evento_match:
            return f"Evento {evento_match.group(1)}"
        
        # Fallback: nome do arquivo sem extensão
        return Path(filename).stem
    
    def _extract_date(self, text: str) -> str:
        """Extrai data do documento"""
        # Padrão brasileiro: dd/mm/yyyy ou dd-mm-yyyy
        date_match = re.search(r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', text[:2000])
        if date_match:
            return f"{date_match.group(3)}-{date_match.group(2).zfill(2)}-{date_match.group(1).zfill(2)}"
        return datetime.now().strftime("%Y-%m-%d")
    
    def index_documento(
        self, 
        file_path: str, 
        doc_id: Optional[str] = None,
        tipo_doc: Optional[str] = None
    ) -> int:
        """
        Indexa um documento do processo.
        
        Args:
            file_path: Caminho para o arquivo (PDF, TXT, etc.)
            doc_id: ID do documento (auto-detectado se não fornecido)
            tipo_doc: Tipo do documento (auto-detectado se não fornecido)
            
        Returns:
            Número de chunks indexados
        """
        filename = Path(file_path).name
        ext = Path(file_path).suffix.lower()
        
        # Ler conteúdo
        if ext == '.pdf':
            pages = self._read_pdf_with_pages(file_path)
            full_text = "\n".join([p["text"] for p in pages])
        elif ext in ['.txt', '.md']:
            with open(file_path, 'r', encoding='utf-8') as f:
                full_text = f.read()
            pages = [{"text": full_text, "page": 1}]
        else:
            logger.warning(f"Extensão não suportada: {ext}")
            return 0
        
        if not full_text.strip() or len(full_text) < 50:
            logger.warning(f"Documento vazio ou muito curto: {filename}")
            return 0
        
        # Auto-detectar metadados
        doc_id = doc_id or self._extract_doc_id(filename, full_text)
        tipo_doc = tipo_doc or self._detect_doc_type(full_text, filename)
        data_doc = self._extract_date(full_text)
        
        # Indexar por página
        total_chunks = 0
        for page_data in pages:
            chunks = self._chunk_text(page_data["text"], page_start=page_data["page"])
            
            for chunk in chunks:
                # Criar ID único
                chunk_id = hashlib.md5(f"{self.processo_id}_{doc_id}_{chunk['page']}_{chunk['word_start']}".encode()).hexdigest()
                
                # Embedding
                embedding = self.embedding_model.encode(chunk["text"]).tolist()
                
                # Metadata
                metadata = {
                    "processo_id": self.processo_id,
                    "sistema": self.sistema,
                    "tenant_id": self.tenant_id,
                    "doc_id": doc_id,
                    "tipo_doc": tipo_doc,
                    "data_doc": data_doc,
                    "pagina": chunk["page"],
                    "filename": filename,
                    "file_path": str(file_path)
                }
                
                # Add to collection
                self.collection.add(
                    ids=[chunk_id],
                    embeddings=[embedding],
                    documents=[chunk["text"]],
                    metadatas=[metadata]
                )
                
                # Store for BM25
                self._documents.append(chunk["text"])
                self._metadatas.append(metadata)
                
                total_chunks += 1
        
        # Invalidate BM25 cache
        self._bm25 = None
        
        logger.info(f"   ✅ {filename}: {total_chunks} chunks ({tipo_doc})")
        return total_chunks
    
    def index_pasta(self, pasta_path: str) -> int:
        """
        Indexa todos os documentos de uma pasta.
        
        Args:
            pasta_path: Caminho para a pasta com os autos
            
        Returns:
            Total de chunks indexados
        """
        pasta = Path(pasta_path)
        if not pasta.exists():
            raise FileNotFoundError(f"Pasta não encontrada: {pasta_path}")
        
        print(f"\n{Fore.CYAN}📁 Indexando processo: {self.processo_id}")
        print(f"   Pasta: {pasta_path}{Style.RESET_ALL}\n")
        
        # Encontrar arquivos
        extensions = ['.pdf', '.txt', '.md']
        files = []
        for ext in extensions:
            files.extend(pasta.glob(f"**/*{ext}"))
        
        files = sorted(files)
        print(f"   Arquivos encontrados: {len(files)}\n")
        
        total = 0
        for file_path in files:
            try:
                count = self.index_documento(str(file_path))
                total += count
            except Exception as e:
                logger.error(f"Erro ao indexar {file_path}: {e}")
        
        print(f"\n{Fore.GREEN}✅ Total indexado: {total} chunks{Style.RESET_ALL}")
        return total
    
    def _build_bm25(self):
        """Constrói índice BM25 (lazy)"""
        if self._bm25 is None and self._documents:
            tokenized = [doc.lower().split() for doc in self._documents]
            self._bm25 = BM25Okapi(tokenized)
    
    def search(
        self, 
        query: str, 
        top_k: int = 5,
        tipo_doc: Optional[str] = None
    ) -> List[Dict]:
        """
        Busca híbrida (semântica + BM25) nos autos do processo.
        
        Args:
            query: Termo de busca
            top_k: Número de resultados
            tipo_doc: Filtrar por tipo de documento
            
        Returns:
            Lista de resultados com texto, metadata e citação
        """
        if self.is_expired():
            logger.warning("⚠️ Índice expirado!")
        
        # Semantic search
        query_embedding = self.embedding_model.encode(query).tolist()
        
        where_filter = {}
        if tipo_doc:
            where_filter["tipo_doc"] = tipo_doc
        
        # Enforce tenant isolation if set and not default
        if self.tenant_id and self.tenant_id != "default":
             where_filter["tenant_id"] = self.tenant_id

        # Se filtro ficou vazio, passar None
        if not where_filter:
            where_filter = None
        
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k * 2,  # Over-fetch for fusion
            where=where_filter,
            include=["documents", "metadatas", "distances"]
        )
        
        # BM25 search
        self._build_bm25()
        bm25_scores = []
        if self._bm25:
            scores = self._bm25.get_scores(query.lower().split())
            scored_docs = [(i, score) for i, score in enumerate(scores)]
            scored_docs.sort(key=lambda x: x[1], reverse=True)
            bm25_scores = scored_docs[:top_k * 2]
        
        # Fusion (simplified RRF)
        doc_scores = {}
        
        # Add semantic results
        if results["documents"] and results["documents"][0]:
            for i, (doc, meta, dist) in enumerate(zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0]
            )):
                doc_id = hashlib.md5(doc.encode()).hexdigest()
                score = 1 - dist  # Convert distance to similarity
                doc_scores[doc_id] = {
                    "text": doc,
                    "metadata": meta,
                    "semantic_score": score,
                    "bm25_score": 0,
                    "final_score": score * 0.7
                }
        
        # Add BM25 boost
        if bm25_scores:
            max_bm25 = max(s for _, s in bm25_scores) if bm25_scores else 1
            for idx, score in bm25_scores:
                if idx < len(self._documents):
                    doc = self._documents[idx]
                    doc_id = hashlib.md5(doc.encode()).hexdigest()
                    normalized = (score / max_bm25) if max_bm25 > 0 else 0
                    
                    if doc_id in doc_scores:
                        doc_scores[doc_id]["bm25_score"] = normalized
                        doc_scores[doc_id]["final_score"] += normalized * 0.3
                    else:
                        doc_scores[doc_id] = {
                            "text": doc,
                            "metadata": self._metadatas[idx],
                            "semantic_score": 0,
                            "bm25_score": normalized,
                            "final_score": normalized * 0.3
                        }
        
        # Sort and return top_k
        results_list = list(doc_scores.values())
        results_list.sort(key=lambda x: x["final_score"], reverse=True)
        
        # Add citation format
        for r in results_list:
            r["citacao"] = self.format_citation(r)
        
        return results_list[:top_k]
    
    def format_citation(self, result: Dict) -> str:
        """
        Formata citação auditável para o resultado.
        
        Args:
            result: Resultado da busca
            
        Returns:
            String de citação Ex: "[LAUDO - Doc. 12345, p. 3]"
        """
        meta = result.get("metadata", {})
        tipo = meta.get("tipo_doc", "DOC").upper()
        doc_id = meta.get("doc_id", "?")
        pagina = meta.get("pagina", "?")
        
        if self.sistema == "SEI":
            return f"[{tipo} - Doc. SEI nº {doc_id}, p. {pagina}]"
        elif self.sistema in ["PJe", "eproc"]:
            return f"[{tipo} - {doc_id}, p. {pagina}]"
        else:
            return f"[{tipo} - {doc_id}, p. {pagina}]"
    
    def get_stats(self) -> Dict:
        """Retorna estatísticas do índice"""
        return {
            "processo_id": self.processo_id,
            "sistema": self.sistema,
            "total_chunks": self.collection.count(),
            "total_documents": len(set(m.get("doc_id", "") for m in self._metadatas)),
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expiry.isoformat(),
            "is_expired": self.is_expired()
        }
    
    def cronologia(self) -> List[Dict]:
        """
        Gera cronologia dos documentos do processo.
        
        Returns:
            Lista de documentos ordenados por data
        """
        # Agrupar por doc_id
        docs = {}
        for meta in self._metadatas:
            doc_id = meta.get("doc_id", "")
            if doc_id not in docs:
                docs[doc_id] = {
                    "doc_id": doc_id,
                    "tipo_doc": meta.get("tipo_doc", ""),
                    "data_doc": meta.get("data_doc", ""),
                    "filename": meta.get("filename", ""),
                    "paginas": set()
                }
            docs[doc_id]["paginas"].add(meta.get("pagina", 0))
        
        # Converter e ordenar
        cronologia = []
        for doc in docs.values():
            doc["paginas"] = sorted(doc["paginas"])
            doc["total_paginas"] = len(doc["paginas"])
            cronologia.append(doc)
        
        cronologia.sort(key=lambda x: x.get("data_doc", ""))
        return cronologia
    
    def cleanup(self):
        """Libera recursos do índice"""
        try:
            self.client.delete_collection(self.collection_name)
            logger.info(f"🗑️ Índice {self.processo_id} removido.")
        except Exception as e:
            logger.warning(f"Erro ao limpar índice: {e}")


# =============================================================================
# CLI PARA TESTES
# =============================================================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="RAG Local - Índice de Processos")
    parser.add_argument("--processo", required=True, help="Número do processo")
    parser.add_argument("--pasta", required=True, help="Pasta com os autos")
    parser.add_argument("--sistema", default="SEI", choices=["SEI", "PJe", "eproc", "SAPIENS"])
    parser.add_argument("--busca", help="Termo para buscar (teste)")
    
    args = parser.parse_args()
    
    # Criar índice
    index = LocalProcessIndex(
        processo_id=args.processo,
        sistema=args.sistema
    )
    
    # Indexar pasta
    index.index_pasta(args.pasta)
    
    # Mostrar cronologia
    print(f"\n{Fore.CYAN}📋 Cronologia do Processo:{Style.RESET_ALL}")
    for doc in index.cronologia():
        print(f"   {doc['data_doc']} | {doc['tipo_doc'].upper():15} | {doc['doc_id']}")
    
    # Buscar (se solicitado)
    if args.busca:
        print(f"\n{Fore.CYAN}🔍 Buscando: '{args.busca}'{Style.RESET_ALL}")
        results = index.search(args.busca, top_k=3)
        for r in results:
            print(f"\n   {r['citacao']} (score: {r['final_score']:.2f})")
            print(f"   \"{r['text'][:200]}...\"")
    
    # Stats
    print(f"\n{Fore.GREEN}📊 Estatísticas:{Style.RESET_ALL}")
    stats = index.get_stats()
    for k, v in stats.items():
        print(f"   {k}: {v}")


if __name__ == "__main__":
    main()
