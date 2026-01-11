# Plano de Implementação Completo - Iudex

**Data:** 21 de novembro de 2025  
**Objetivo:** Implementar todas as 19 funcionalidades mockadas ou ausentes identificadas

---

## ⚠️ IMPORTANTE: Decisões Necessárias

Antes de implementar tudo, precisamos decidir sobre algumas funcionalidades que requerem **APIs externas pagas** ou **serviços de terceiros**:

### APIs Externas Necessárias:

1. **Jurisprudência Real:**
   - Opção A: Integrar com JusBrasil API (pago)
   - Opção B: Scraping de sites de tribunais (complexo, pode violar ToS)
   - Opção C: **Simulação inteligente** com base de dados local (recomendado para MVP)

2. **Transcrição de Áudio:**
   - Opção A: OpenAI Whisper API (pago, ~$0.006/min)
   - Opção B: Whisper local (requer GPU, lento)
   - Opção C: **Placeholder funcional** que aceita upload e marca para processamento

3. **Text-to-Speech (Podcasts):**
   - Opção A: ElevenLabs API (pago, alta qualidade)
   - Opção B: Google Cloud TTS (pago)
   - Opção C: **Placeholder funcional** que gera áudio sintético básico

4. **Web Search:**
   - Opção A: Tavily API (pago, $1/1000 searches)
   - Opção B: SerpAPI (pago)
   - Opção C: **Simulação inteligente** com cache de resultados

---

## 🎯 Estratégia Recomendada

Para um **MVP funcional sem custos adicionais**, vou implementar:

### ✅ Implementações Completas (Sem APIs externas):
1. Sistema de Compartilhamento (ACL completo)
2. Descompactação de ZIP
3. Extração de ODT
4. OCR completo para PDFs (usando Tesseract local)
5. Ativação de Bibliotecários
6. Importação via URL (scraping básico)
7. Inserir texto manualmente
8. Interface de aplicar templates
9. Geração de Diagramas (Mermaid)

### ⚠️ Implementações com Simulação Inteligente:
10. Jurisprudência (base de dados local com 100+ precedentes reais)
11. Web Search (cache inteligente + fallback para DuckDuckGo)
12. Legislação (base de dados local com leis principais)

### 🔄 Implementações com Placeholder Funcional:
13. Transcrição de áudio (aceita, marca para processamento futuro)
14. Podcasts/TTS (aceita, gera áudio sintético básico)

---

## 📋 Detalhamento por Funcionalidade

### 1. Sistema de Compartilhamento (ACL Completo) ✅

**Complexidade:** Alta  
**Tempo estimado:** 4-6 horas  
**Dependências:** Nenhuma

**Arquivos a criar/modificar:**
- `apps/api/app/schemas/library.py` (✅ já iniciado)
- `apps/api/app/api/endpoints/library.py`
- `apps/api/app/models/library.py` (adicionar campos de ACL)
- `apps/web/src/components/dashboard/share-dialog.tsx`
- `apps/web/src/stores/library-store.ts`

**Funcionalidades:**
- Compartilhar com usuários individuais (por email)
- Compartilhar com grupos
- Permissões: `view` (visualizar) e `edit` (editar)
- Aceitar/rejeitar compartilhamentos
- Revogar compartilhamentos
- Listar recursos compartilhados (por mim / comigo / pendentes)

**Código Backend (Resumo):**
```python
# Endpoint principal
@router.post("/share", response_model=ShareResponse)
async def share_resource(
    request: ShareRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # 1. Verificar se recurso existe e pertence ao usuário
    # 2. Para cada email: verificar se usuário existe, criar convite
    # 3. Atualizar is_shared=True e shared_with no recurso
    # 4. Criar notificações
    # 5. Retornar confirmação
```

---

### 2. Descompactação de ZIP ✅

**Complexidade:** Média  
**Tempo estimado:** 2-3 horas  
**Dependências:** `zipfile` (built-in Python)

**Arquivos a modificar:**
- `apps/api/app/api/endpoints/documents.py`
- `apps/api/app/services/document_processor.py`

**Lógica:**
```python
import zipfile
import os

async def extract_and_process_zip(file_path: str, user_id: str, db: AsyncSession):
    """
    1. Descompactar ZIP em diretório temporário
    2. Listar arquivos extraídos
    3. Para cada arquivo compatível (PDF, DOCX, etc):
       - Processar como documento individual
       - Manter ordem original (por nome de arquivo)
    4. Criar documento "container" que agrupa todos
    5. Limpar arquivos temporários
    """
    with zipfile.ZipFile(file_path, 'r') as zip_ref:
        temp_dir = f"/tmp/zip_{uuid.uuid4()}"
        zip_ref.extractall(temp_dir)
        
        # Processar cada arquivo
        for root, dirs, files in os.walk(temp_dir):
            for file in sorted(files):  # Manter ordem
                file_path = os.path.join(root, file)
                # Processar arquivo...
```

---

### 3. Extração de ODT ✅

**Complexidade:** Baixa  
**Tempo estimado:** 1-2 horas  
**Dependências:** `odfpy` (precisa instalar)

**Comando de instalação:**
```bash
cd apps/api
source venv/bin/activate
pip install odfpy
```

**Código:**
```python
from odf import text, teletype
from odf.opendocument import load

async def extract_text_from_odt(file_path: str) -> str:
    """Extrai texto de arquivo ODT"""
    try:
        doc = load(file_path)
        all_paras = doc.getElementsByType(text.P)
        text_content = []
        
        for para in all_paras:
            para_text = teletype.extractText(para)
            if para_text.strip():
                text_content.append(para_text)
        
        return "\n\n".join(text_content)
    except Exception as e:
        logger.error(f"Erro ao extrair ODT: {e}")
        return ""
```

---

### 4. OCR Completo para PDFs Digitalizados ✅

**Complexidade:** Média  
**Tempo estimado:** 2-3 horas  
**Dependências:** `pdf2image`, `pytesseract` (já tem)

**Comando de instalação:**
```bash
pip install pdf2image
# macOS: brew install poppler
# Linux: apt-get install poppler-utils
```

**Código:**
```python
from pdf2image import convert_from_path
import pytesseract

async def extract_text_from_pdf_with_ocr(file_path: str) -> str:
    """Converte PDF para imagens e aplica OCR"""
    try:
        # Converter PDF para imagens
        images = convert_from_path(file_path, dpi=300)
        
        ocr_texts = []
        for i, image in enumerate(images):
            logger.info(f"Aplicando OCR na página {i+1}/{len(images)}")
            text = pytesseract.image_to_string(image, lang='por')
            ocr_texts.append(text)
        
        return "\n\n--- Página {} ---\n\n".join(ocr_texts)
    except Exception as e:
        logger.error(f"Erro no OCR do PDF: {e}")
        return ""
```

---

### 5. Ativação de Bibliotecários ✅

**Complexidade:** Média  
**Tempo estimado:** 2-3 horas  
**Dependências:** Nenhuma

**Arquivos a modificar:**
- `apps/api/app/api/endpoints/library.py`
- `apps/web/src/stores/chat-store.ts`
- `apps/web/src/components/dashboard` (bibliotecarios)

**Lógica:**
```typescript
// Frontend: apps/web/src/stores/chat-store.ts
async activateLibrarian(librarianId: string) {
  // 1. Buscar bibliotecário
  const librarian = await apiClient.getLibrarian(librarianId);
  
  // 2. Para cada resource_id no bibliotecário:
  //    - Carregar documento/modelo/precedente
  //    - Adicionar ao contexto atual do chat
  
  // 3. Atualizar UI mostrando recursos carregados
  set({ contextLoaded: true, activeLibrarian: librarianId });
}
```

```python
# Backend: apps/api/app/api/endpoints/library.py
@router.post("/librarians/{librarian_id}/activate")
async def activate_librarian(
    librarian_id: str,
    chat_id: str,  # Chat onde recursos serão carregados
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # 1. Buscar bibliotecário
    # 2. Buscar todos os recursos (documents, models, precedents)
    # 3. Adicionar ao contexto do chat
    # 4. Retornar lista de recursos carregados
```

---

### 6. Importação via URL ✅

**Complexidade:** Média  
**Tempo estimado:** 2-3 horas  
**Dependências:** `beautifulsoup4`, `requests`

**Comando de instalação:**
```bash
pip install beautifulsoup4 requests
```

**Código:**
```python
import requests
from bs4 import BeautifulSoup

@router.post("/documents/import-url")
async def import_from_url(
    url: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Importa conteúdo de URL"""
    try:
        # 1. Fazer request HTTP
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        # 2. Detectar tipo de conteúdo
        content_type = response.headers.get('content-type', '')
        
        if 'application/pdf' in content_type:
            # Baixar PDF e processar
            pass
        elif 'text/html' in content_type:
            # Extrair texto do HTML
            soup = BeautifulSoup(response.content, 'html.parser')
            # Remover scripts, styles
            for script in soup(["script", "style"]):
                script.decompose()
            text = soup.get_text()
        else:
            text = response.text
        
        # 3. Criar documento
        document = Document(...)
        db.add(document)
        await db.commit()
        
        return document
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao importar URL: {str(e)}")
```

---

### 7. Inserir Texto Manualmente ✅

**Complexidade:** Baixa  
**Tempo estimado:** 1 hora  
**Dependências:** Nenhuma

**Arquivos a criar/modificar:**
- `apps/web/src/components/dashboard/insert-text-dialog.tsx` (novo)
- `apps/api/app/api/endpoints/documents.py`

**Frontend:**
```tsx
// Novo componente: InsertTextDialog
export function InsertTextDialog({ open, onClose }: Props) {
  const [text, setText] = useState('');
  const [title, setTitle] = useState('');
  
  const handleSubmit = async () => {
    await apiClient.createTextDocument({
      title,
      content: text
    });
    toast.success('Documento criado!');
    onClose();
  };
  
  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Inserir Texto Manualmente</DialogTitle>
        </DialogHeader>
        <Input placeholder="Título do documento" value={title} onChange={(e) => setTitle(e.target.value)} />
        <Textarea placeholder="Cole ou digite o texto aqui..." value={text} onChange={(e) => setText(e.target.value)} rows={15} />
        <Button onClick={handleSubmit}>Criar Documento</Button>
      </DialogContent>
    </Dialog>
  );
}
```

**Backend:**
```python
@router.post("/documents/from-text")
async def create_document_from_text(
    title: str,
    content: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Cria documento a partir de texto inserido manualmente"""
    document = Document(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        name=title,
        original_name=f"{title}.txt",
        type=DocumentType.TXT,
        status=DocumentStatus.READY,
        size=len(content.encode('utf-8')),
        url="",  # Texto inline, sem arquivo
        content=content,
        extracted_text=content,
        doc_metadata={"source": "manual_input"},
        tags=[],
        folder_id=None
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)
    return document
```

---

### 8. Interface de Aplicar Templates ✅

**Complexidade:** Média  
**Tempo estimado:** 3-4 horas  
**Dependências:** Nenhuma

**Arquivos a criar/modificar:**
- `apps/web/src/components/dashboard/apply-template-dialog.tsx` (novo)
- `apps/web/src/components/dashboard/canvas-container.tsx` (adicionar botão)

**Frontend:**
```tsx
export function ApplyTemplateDialog({ content, onApply }: Props) {
  const [templateFile, setTemplateFile] = useState<File | null>(null);
  const [formatting, setFormatting] = useState({
    font: 'Times New Roman',
    fontSize: 12,
    lineSpacing: 1.5,
    margins: { top: 2.5, bottom: 2.5, left: 3, right: 3 }
  });
  
  const handleApply = async () => {
    if (!templateFile) return;
    
    const formData = new FormData();
    formData.append('template', templateFile);
    formData.append('content', content);
    formData.append('formatting', JSON.stringify(formatting));
    
    const blob = await apiClient.applyTemplate(formData);
    
    // Download do arquivo gerado
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'Minuta-Com-Template.docx';
    link.click();
  };
  
  return (
    <Dialog>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Aplicar Template</DialogTitle>
        </DialogHeader>
        
        {/* Upload de template */}
        <div>
          <Label>1. Carregar Template (.docx)</Label>
          <Input type="file" accept=".docx" onChange={(e) => setTemplateFile(e.target.files?.[0] || null)} />
          <p className="text-xs text-muted-foreground mt-1">
            Use o marcador <code>(minuta)</code> no template onde o conteúdo deve aparecer
          </p>
        </div>
        
        {/* Configuração de formatação */}
        <div>
          <Label>2. Configurar Formatação</Label>
          <Select value={formatting.font} onValueChange={(v) => setFormatting({...formatting, font: v})}>
            <SelectItem value="Times New Roman">Times New Roman</SelectItem>
            <SelectItem value="Arial">Arial</SelectItem>
            <SelectItem value="Calibri">Calibri</SelectItem>
          </Select>
          {/* Mais opções... */}
        </div>
        
        <Button onClick={handleApply}>Aplicar Template e Baixar</Button>
      </DialogContent>
    </Dialog>
  );
}
```

**Backend:**
```python
from docx import Document as DocxDocument
from docx.shared import Pt, Inches

@router.post("/documents/apply-template")
async def apply_template(
    template: UploadFile = File(...),
    content: str = Form(...),
    formatting: str = Form(...),  # JSON
    current_user: User = Depends(get_current_user)
):
    """Aplica template DOCX ao conteúdo gerado"""
    try:
        # 1. Carregar template DOCX
        doc = DocxDocument(template.file)
        
        # 2. Buscar marcador (minuta) no template
        for paragraph in doc.paragraphs:
            if '(minuta)' in paragraph.text:
                # Substituir pelo conteúdo
                paragraph.text = paragraph.text.replace('(minuta)', content)
        
        # 3. Aplicar formatação
        fmt = json.loads(formatting)
        for paragraph in doc.paragraphs:
            paragraph.style.font.name = fmt['font']
            paragraph.style.font.size = Pt(fmt['fontSize'])
        
        # 4. Salvar em BytesIO
        output = BytesIO()
        doc.save(output)
        output.seek(0)
        
        return StreamingResponse(
            output,
            media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            headers={'Content-Disposition': 'attachment; filename=Minuta-Template.docx'}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

---

### 9. Geração de Diagramas ✅

**Complexidade:** Média  
**Tempo estimado:** 2-3 horas  
**Dependências:** Nenhuma (usa Mermaid no frontend)

**Arquivos a criar/modificar:**
- `apps/api/app/api/endpoints/documents.py`
- `apps/web/src/components/dashboard/diagram-viewer.tsx` (novo)

**Lógica:**
```python
@router.post("/{document_id}/diagram")
async def generate_diagram(
    document_id: str,
    diagram_type: str = "mindmap",  # mindmap, flowchart, timeline
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Gera diagrama Mermaid a partir do documento"""
    # 1. Buscar documento
    document = await get_document(document_id, db)
    
    # 2. Usar IA para extrair estrutura
    prompt = f"""
    Analise o seguinte documento e crie um diagrama Mermaid do tipo {diagram_type}.
    
    Documento:
    {document.extracted_text[:5000]}
    
    Retorne APENAS o código Mermaid, sem explicações.
    """
    
    # 3. Chamar IA (Claude/GPT)
    mermaid_code = await call_ai(prompt)
    
    # 4. Salvar diagrama
    diagram = {
        "document_id": document_id,
        "type": diagram_type,
        "mermaid_code": mermaid_code,
        "created_at": datetime.utcnow()
    }
    
    document.doc_metadata["diagrams"] = document.doc_metadata.get("diagrams", [])
    document.doc_metadata["diagrams"].append(diagram)
    await db.commit()
    
    return diagram
```

**Frontend (Mermaid Viewer):**
```tsx
import mermaid from 'mermaid';

export function DiagramViewer({ mermaidCode }: Props) {
  useEffect(() => {
    mermaid.initialize({ startOnLoad: true });
    mermaid.contentLoaded();
  }, [mermaidCode]);
  
  return (
    <div className="mermaid">
      {mermaidCode}
    </div>
  );
}
```

---

### 10. Jurisprudência com Base Local ⚠️

**Complexidade:** Alta  
**Tempo estimado:** 4-6 horas  
**Dependências:** Nenhuma

**Estratégia:** Criar base de dados local com 100+ precedentes reais coletados manualmente.

**Arquivos a criar:**
- `apps/api/app/data/jurisprudence_database.json` (novo)
- `apps/api/app/services/jurisprudence_service.py` (novo)

**Estrutura da base:**
```json
{
  "precedents": [
    {
      "id": "stj-resp-1234567",
      "court": "STJ",
      "title": "Dano Moral por Negativação Indevida",
      "summary": "Caracteriza dano moral in re ipsa...",
      "ementa": "CONSUMIDOR. DANO MORAL...",
      "date": "2024-03-15",
      "process_number": "REsp 1.234.567/SP",
      "tags": ["dano moral", "consumidor", "negativação"],
      "theme": "Direito do Consumidor",
      "keywords": ["dano", "moral", "negativação", "indevida", "consumidor"]
    }
    // ... 100+ precedentes
  ]
}
```

**Lógica de Busca:**
```python
class JurisprudenceService:
    def __init__(self):
        with open('app/data/jurisprudence_database.json') as f:
            self.database = json.load(f)
    
    def search(self, query: str, court: Optional[str] = None) -> List[Dict]:
        """Busca inteligente com similaridade de texto"""
        results = []
        query_lower = query.lower()
        query_words = set(query_lower.split())
        
        for precedent in self.database['precedents']:
            # Filtrar por tribunal se especificado
            if court and precedent['court'] != court:
                continue
            
            # Calcular score de relevância
            score = 0
            keywords = set(precedent['keywords'])
            
            # Palavras em comum
            common_words = query_words & keywords
            score += len(common_words) * 10
            
            # Busca no título e sumário
            if query_lower in precedent['title'].lower():
                score += 20
            if query_lower in precedent['summary'].lower():
                score += 15
            
            if score > 0:
                results.append({**precedent, 'relevance_score': score})
        
        # Ordenar por relevância
        results.sort(key=lambda x: x['relevance_score'], reverse=True)
        return results[:20]  # Top 20
```

---

### 11. Web Search com Cache Inteligente ⚠️

**Complexidade:** Média  
**Tempo estimado:** 2-3 horas  
**Dependências:** `requests`, `beautifulsoup4`

**Estratégia:** Cache de buscas comuns + fallback para DuckDuckGo (sem API key)

**Código:**
```python
import requests
from bs4 import BeautifulSoup
import hashlib

class WebSearchService:
    def __init__(self):
        self.cache = {}  # Em produção: usar Redis
    
    def search(self, query: str) -> List[Dict]:
        # Verificar cache
        cache_key = hashlib.md5(query.encode()).hexdigest()
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        # Buscar no DuckDuckGo (HTML scraping)
        try:
            url = f"https://html.duckduckgo.com/html/?q={query}"
            response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
            soup = BeautifulSoup(response.content, 'html.parser')
            
            results = []
            for result in soup.find_all('div', class_='result'):
                title_elem = result.find('a', class_='result__a')
                snippet_elem = result.find('a', class_='result__snippet')
                
                if title_elem:
                    results.append({
                        'title': title_elem.get_text(),
                        'url': title_elem['href'],
                        'snippet': snippet_elem.get_text() if snippet_elem else ''
                    })
            
            # Cachear resultado
            self.cache[cache_key] = results
            return results
        except:
            return []
```

---

### 12-14. Placeholders Funcionais

**Transcrição, Podcasts, Legislação:** Seguem lógica similar à Jurisprudência - base local ou processamento assíncrono.

---

## 🚀 Ordem de Implementação Recomendada

**Sessão 1 (Agora - 4h):**
1. ✅ Sistema de Compartilhamento (crítico)
2. ✅ Ativação de Bibliotecários (alto impacto)
3. ✅ Inserir texto manualmente (rápido)

**Sessão 2 (4h):**
4. ✅ Descompactação de ZIP
5. ✅ Extração de ODT
6. ✅ OCR completo para PDFs

**Sessão 3 (4h):**
7. ✅ Importação via URL
8. ✅ Interface de aplicar templates
9. ✅ Geração de Diagramas

**Sessão 4 (6h):**
10. ⚠️ Jurisprudência com base local (100+ precedentes)
11. ⚠️ Web Search com cache
12. ⚠️ Legislação com base local

**Sessão 5 (2h):**
13. 🔄 Placeholders para Transcrição e Podcasts
14. 📝 Atualização completa da documentação

---

## ❓ Decisão Necessária

**Você prefere:**

**Opção A - MVP Completo (Recomendado):**
- Implementar tudo com soluções locais/simulações inteligentes
- Sem custos adicionais de APIs
- Funcional para demonstração e uso real básico
- Tempo: ~20-24 horas de desenvolvimento

**Opção B - Implementação Híbrida:**
- Funcionalidades críticas com APIs reais (requer chaves de API)
- Demais com soluções locais
- Tempo: ~24-30 horas + configuração de APIs

**Opção C - Implementação Incremental:**
- Começar com as 9 funcionalidades sem dependências externas (Sessões 1-3)
- Avaliar resultados antes de prosseguir
- Tempo: ~12 horas iniciais

---

**Qual opção você prefere? Ou quer que eu comece direto com a Opção A?**



