# 🎯 Próximos Passos - Roadmap de Implementação

Este documento guia o que falta implementar para completar o Iudex.

## 📊 Status Atual

**Completo (60%):**
- ✅ Backend Python/FastAPI 100%
- ✅ Sistema Multi-Agente IA
- ✅ Processamento sem limite de contexto
- ✅ Busca semântica
- ✅ Workers Celery
- ✅ Documentação completa

**Falta (40%):**
- ⏳ Frontend Next.js
- ⏳ Implementações específicas (OCR, Transcrição, etc.)
- ⏳ Integrações externas (CNJ, DJEN, Tribunais)

---

## 🎯 Fase 1: Implementações Backend Específicas

### 1.1 Processamento Real de Documentos

**Prioridade**: Alta  
**Tempo Estimado**: 3-5 dias  
**Arquivos**: `app/services/document_processor.py`

**Tarefas:**
```python
# Implementar em document_processor.py

async def extract_text_from_pdf(file_path: str) -> str:
    """Extrair texto de PDF"""
    import pdfplumber
    
    with pdfplumber.open(file_path) as pdf:
        text = ""
        for page in pdf.pages:
            text += page.extract_text() or ""
    return text

async def extract_text_from_docx(file_path: str) -> str:
    """Extrair texto de DOCX"""
    import docx
    
    doc = docx.Document(file_path)
    return "\n".join([p.text for p in doc.paragraphs])
```

**Bibliotecas Necessárias:**
- `pdfplumber` - Melhor para PDFs
- `python-docx` - Para DOCX
- `openpyxl` - Para Excel
- `python-magic` - Detecção de tipo

### 1.2 OCR com Tesseract

**Prioridade**: Média  
**Tempo Estimado**: 2-3 dias  
**Arquivos**: `app/workers/tasks/document_tasks.py`

**Implementação:**
```python
def ocr_document_task(document_id: str, file_path: str, language: str = "por"):
    import pytesseract
    from pdf2image import convert_from_path
    from PIL import Image
    
    # Converter PDF para imagens
    images = convert_from_path(file_path, dpi=300)
    
    # Aplicar OCR em cada página
    text = ""
    for i, image in enumerate(images):
        # Pré-processamento da imagem
        image = image.convert('L')  # Grayscale
        
        # OCR
        page_text = pytesseract.image_to_string(
            image, 
            lang=language,
            config='--psm 1'
        )
        text += f"\n--- Página {i+1} ---\n{page_text}"
    
    return text
```

**Dependências Sistema:**
```bash
# macOS
brew install tesseract tesseract-lang

# Ubuntu
sudo apt install tesseract-ocr tesseract-ocr-por

# Bibliotecas Python
pip install pytesseract pdf2image pillow
```

### 1.3 Transcrição de Áudio com Whisper

**Prioridade**: Média  
**Tempo Estimado**: 2-3 dias  
**Arquivos**: `app/workers/tasks/document_tasks.py`

**Implementação:**
```python
def transcribe_audio_task(document_id: str, audio_path: str, identify_speakers: bool = False):
    import whisper
    from pydub import AudioSegment
    
    # Carregar modelo Whisper
    model = whisper.load_model("base")
    
    # Converter para formato suportado se necessário
    audio = AudioSegment.from_file(audio_path)
    audio.export("/tmp/audio.wav", format="wav")
    
    # Transcrever
    result = model.transcribe("/tmp/audio.wav", language="pt")
    
    # Se identificar falantes (diarização)
    if identify_speakers:
        # TODO: Implementar com pyannote.audio
        pass
    
    return result["text"]
```

**Bibliotecas:**
```bash
pip install openai-whisper pydub
# FFmpeg necessário
brew install ffmpeg  # macOS
sudo apt install ffmpeg  # Ubuntu
```

### 1.4 Embeddings Reais

**Prioridade**: Alta  
**Tempo Estimado**: 1-2 dias  
**Arquivos**: `app/services/embedding_service.py`

**Implementação:**
```python
from sentence_transformers import SentenceTransformer

class EmbeddingService:
    def __init__(self):
        self.model = SentenceTransformer(
            'paraphrase-multilingual-mpnet-base-v2'
        )
    
    async def generate_embedding(self, text: str) -> List[float]:
        embedding = self.model.encode(text)
        return embedding.tolist()
    
    async def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        embeddings = self.model.encode(texts, batch_size=32)
        return embeddings.tolist()
```

### 1.5 Vector Store Real

**Prioridade**: Alta  
**Tempo Estimado**: 2-3 dias  
**Arquivos**: `app/services/embedding_service.py`

**Opção 1 - Qdrant (Local):**
```python
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

class VectorStore:
    def __init__(self):
        self.client = QdrantClient(host="localhost", port=6333)
        
        # Criar coleção
        self.client.recreate_collection(
            collection_name="documents",
            vectors_config=VectorParams(size=768, distance=Distance.COSINE)
        )
    
    async def upsert_vectors(self, vectors: List[Dict]):
        points = [
            PointStruct(
                id=v["id"],
                vector=v["embedding"],
                payload=v["metadata"]
            )
            for v in vectors
        ]
        
        self.client.upsert(
            collection_name="documents",
            points=points
        )
```

**Opção 2 - ChromaDB (Mais Simples):**
```python
import chromadb

class VectorStore:
    def __init__(self):
        self.client = chromadb.Client()
        self.collection = self.client.create_collection("documents")
    
    async def upsert_vectors(self, vectors: List[Dict]):
        self.collection.add(
            ids=[v["id"] for v in vectors],
            embeddings=[v["embedding"] for v in vectors],
            metadatas=[v["metadata"] for v in vectors]
        )
    
    async def search_similar(self, query_embedding: List[float], top_k: int = 10):
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k
        )
        return results
```

---

## 🎨 Fase 2: Frontend Next.js

### 2.1 Setup Inicial

**Prioridade**: Alta  
**Tempo Estimado**: 1 dia

```bash
cd apps/web

# Instalar dependências
npm install

# Criar estrutura base
mkdir -p src/{app,components,lib,stores,styles}

# Configurar Tailwind
npx tailwindcss init -p

# Instalar Shadcn/ui
npx shadcn-ui@latest init
```

### 2.2 Sistema de Autenticação

**Prioridade**: Alta  
**Tempo Estimado**: 2-3 dias

**Páginas:**
```typescript
// app/(auth)/login/page.tsx
export default function LoginPage() {
  const { login } = useAuthStore();
  
  const handleLogin = async (e: FormEvent) => {
    e.preventDefault();
    await login(email, password);
    router.push('/dashboard');
  };
  
  return <LoginForm onSubmit={handleLogin} />;
}

// app/(auth)/register/page.tsx
// Similar ao login
```

### 2.3 Layout Principal

**Prioridade**: Alta  
**Tempo Estimado**: 3-4 dias

**Estrutura:**
```
┌─────────────────────────────────────────┐
│ Navbar (Logo, User Menu)                │
├──────┬──────────────────────────────────┤
│      │ ┌──────────────────────────────┐ │
│      │ │ Tabs (Início, Minuta, Docs)  │ │
│ Side │ ├──────────────────────────────┤ │
│ bar  │ │                              │ │
│      │ │                              │ │
│      │ │      Content Area            │ │
│      │ │                              │ │
│      │ │                              │ │
│      │ └──────────────────────────────┘ │
└──────┴──────────────────────────────────┘
```

### 2.4 Editor de Documentos (TipTap)

**Prioridade**: Alta  
**Tempo Estimado**: 3-4 dias

```typescript
// components/editor/document-editor.tsx
import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';

export function DocumentEditor({ content, onChange }) {
  const editor = useEditor({
    extensions: [StarterKit],
    content: content,
    onUpdate: ({ editor }) => {
      onChange(editor.getHTML());
    },
  });

  return (
    <div className="border rounded-lg">
      <EditorToolbar editor={editor} />
      <EditorContent editor={editor} />
    </div>
  );
}
```

### 2.5 Interface de Chat

**Prioridade**: Alta  
**Tempo Estimado**: 2-3 dias

```typescript
// components/chat/chat-interface.tsx
export function ChatInterface({ chatId }) {
  const { messages, sendMessage } = useChatStore();
  const { mutate: generate } = useGenerateDocument(chatId);
  
  return (
    <div className="flex flex-col h-full">
      <MessageList messages={messages} />
      <ChatInput onSend={sendMessage} />
      <GenerateButton onClick={() => generate({ ... })} />
    </div>
  );
}
```

### 2.6 Sistema de Abas

**Prioridade**: Alta  
**Tempo Estimado**: 2 dias

```typescript
// components/layout/tab-system.tsx
const tabs = [
  { id: 'home', label: 'Início', icon: Home },
  { id: 'minuta', label: 'Minuta', icon: FileText },
  { id: 'documents', label: 'Documentos', icon: Upload },
  { id: 'models', label: 'Modelos', icon: BookOpen },
  { id: 'legislation', label: 'Legislação', icon: Scale },
  { id: 'jurisprudence', label: 'Jurisprudência', icon: Gavel },
];

export function TabSystem() {
  const [activeTab, setActiveTab] = useState('home');
  
  return (
    <Tabs value={activeTab} onValueChange={setActiveTab}>
      <TabsList>
        {tabs.map(tab => (
          <TabsTrigger key={tab.id} value={tab.id}>
            <tab.icon /> {tab.label}
          </TabsTrigger>
        ))}
      </TabsList>
      {/* Tab Contents */}
    </Tabs>
  );
}
```

---

## 🔌 Fase 3: Integrações Externas

### 3.1 Busca de Jurisprudência

**Prioridade**: Média  
**Tempo Estimado**: 5-7 dias

**APIs dos Tribunais:**
- STF: https://portal.stf.jus.br/
- STJ: API não oficial
- TST, TSE, STM: APIs específicas
- TRFs, TJs: APIs estaduais

**Implementação:**
```python
# app/services/jurisprudence_service.py
class JurisprudenceService:
    async def search_stf(self, query: str):
        # Implementar scraping ou API oficial
        pass
    
    async def search_stj(self, query: str):
        # Implementar
        pass
```

### 3.2 Busca de Legislação

**Prioridade**: Média  
**Tempo Estimado**: 3-5 dias

**Fontes:**
- Planalto (leis federais)
- Senado (legislação consolidada)
- Câmara dos Deputados

```python
# app/services/legislation_service.py
class LegislationService:
    async def search_federal_law(self, number: str):
        url = f"https://www.planalto.gov.br/ccivil_03/leis/l{number}.htm"
        # Parse HTML
        pass
```

### 3.3 Integração CNJ

**Prioridade**: Baixa  
**Tempo Estimado**: 3-4 dias

```python
# app/services/cnj_service.py
class CNJService:
    async def get_process_metadata(self, process_number: str):
        # API CNJ
        pass
```

---

## 🎨 Fase 4: Recursos Avançados

### 4.1 Geração de Podcasts

**Prioridade**: Baixa  
**Tempo Estimado**: 5-7 dias

**Fluxo:**
1. Gerar script do podcast com IA
2. Converter texto para áudio (TTS)
3. Editar áudio (música, transições)
4. Salvar arquivo final

### 4.2 Diagramas Visuais

**Prioridade**: Baixa  
**Tempo Estimado**: 3-4 dias

**Ferramentas:**
- Mermaid.js para diagramas
- D3.js para visualizações
- React Flow para fluxogramas

### 4.3 Colaboração em Tempo Real

**Prioridade**: Baixa  
**Tempo Estimado**: 7-10 dias

**Tecnologias:**
- WebSockets
- Y.js ou Automerge
- Conflict resolution

---

## 📱 Fase 5: Mobile (Opcional)

### 5.1 React Native ou Flutter

**Prioridade**: Muito Baixa  
**Tempo Estimado**: 30-60 dias

---

## 🚀 Ordem de Implementação Recomendada

### Sprint 1 (1-2 semanas)
1. ✅ Processamento real de PDF/DOCX
2. ✅ Embeddings reais
3. ✅ Vector store (ChromaDB)

### Sprint 2 (2-3 semanas)
1. ✅ Setup frontend Next.js
2. ✅ Autenticação
3. ✅ Layout principal

### Sprint 3 (2-3 semanas)
1. ✅ Editor TipTap
2. ✅ Chat interface
3. ✅ Upload de documentos

### Sprint 4 (2 semanas)
1. ✅ OCR
2. ✅ Transcrição
3. ✅ Busca de jurisprudência (básico)

### Sprint 5 (2 semanas)
1. ✅ Bibliotecários
2. ✅ Compartilhamento
3. ✅ Colaboração

---

## 📚 Recursos para Implementação

### Documentação
- FastAPI: https://fastapi.tiangolo.com/
- Next.js: https://nextjs.org/docs
- TipTap: https://tiptap.dev/
- Shadcn/ui: https://ui.shadcn.com/

### Tutoriais Úteis
- LangChain: https://python.langchain.com/
- Whisper: https://github.com/openai/whisper
- Sentence Transformers: https://www.sbert.net/

### Comunidades
- FastAPI Discord
- Next.js Discord
- Python Brasil

---

## ✅ Checklist Final

### Backend
- [x] FastAPI configurado
- [x] Modelos de banco
- [x] Sistema Multi-Agente
- [x] Processamento de contexto
- [x] Workers Celery
- [ ] Extração de texto real
- [ ] OCR implementado
- [ ] Transcrição implementada
- [ ] Vector store funcionando

### Frontend
- [ ] Next.js setup
- [ ] Autenticação
- [ ] Layout principal
- [ ] Editor TipTap
- [ ] Chat interface
- [ ] Upload de documentos
- [ ] Visualização de docs
- [ ] Integração com API

### Integrações
- [ ] Jurisprudência
- [ ] Legislação
- [ ] CNJ/DJEN
- [ ] Email notifications
- [ ] Webhooks

---

## 🎯 Métricas de Sucesso

**MVP (Mínimo Viável):**
- [ ] Usuário pode fazer login
- [ ] Upload de PDF funciona
- [ ] Chat com IA responde
- [ ] Geração de minuta funciona
- [ ] Documento pode ser exportado

**Versão 1.0:**
- [ ] Todos os recursos do MVP
- [ ] OCR funcional
- [ ] Busca de jurisprudência
- [ ] Biblioteca de documentos
- [ ] Colaboração básica

**Versão 2.0:**
- [ ] Transcrição de áudio
- [ ] Podcasts
- [ ] Diagramas
- [ ] Mobile app
- [ ] API pública

---

**📌 Use este documento como guia para continuar o desenvolvimento!**

**Priorize:** Backend específico → Frontend básico → Integrações → Recursos avançados

