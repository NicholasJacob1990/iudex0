# 📋 Relatório: Implementações Pendentes no Backend - Iudex

**Data:** 23 de novembro de 2025  
**Versão:** 1.0  
**Última Atualização:** Baseado em análise completa do código e documentação

---

## 📊 Resumo Executivo

### Status Geral do Backend
- **✅ Implementado e Funcional:** ~60%
- **⚠️ Parcialmente Implementado:** ~25%
- **🔴 Mockado/Não Implementado:** ~15%

### Principais Categorias de Pendências

| Categoria | Status | Prioridade | Risco |
|-----------|--------|------------|-------|
| **Busca Externa (Jurisprudência/Legislação/Web)** | 🔴 Mockado | Alta | Alto |
| **Processamento de Arquivos Específicos** | ⚠️ Parcial | Alta | Médio |
| **Geração de Conteúdo Multimídia** | ⚠️ Parcial | Média | Baixo |
| **Integrações Externas (CNJ/DJEN)** | 🔴 Ausente | Baixa | Baixo |
| **Sistema Multi-Agente IA** | ✅ Completo | - | - |
| **CRUD e Autenticação** | ✅ Completo | - | - |

---

## 🔴 CRÍTICO - Funcionalidades Mockadas (Risco Jurídico Alto)

### 1. 🔴 Busca de Jurisprudência (MOCKADO)

**Arquivo:** `apps/api/app/api/endpoints/knowledge.py`  
**Status:** Retorna sempre 2 precedentes fixos

#### Problema
```python
# Linha 39-70 em knowledge.py
@router.get("/jurisprudence/search")
async def search_jurisprudence(
    query: str = Query(..., min_length=2),
    court: str | None = None,
    current_user: dict = Depends(get_current_user),
):
    """
    Pesquisa de jurisprudência (mock).
    """
    data = [
        {
            "id": "jp-1",
            "court": "STJ",
            "title": "Dano Moral por Negativação Indevida",
            # ... sempre os mesmos 2 resultados
        }
    ]
```

#### Impacto
- ❌ Usuários podem achar que estão pesquisando tribunais reais
- ❌ Risco de citar precedentes inexistentes ou desatualizados
- ❌ **RISCO JURÍDICO**: Pode gerar peças processuais com fundamentação falsa

#### Solução Necessária
Implementar integração real com:
- **STF:** Portal oficial (API ou scraping)
- **STJ:** Consulta processual e jurisprudência
- **TRFs e TJs:** APIs estaduais
- **Alternativa:** Usar serviços como Jusbrasil API ou JurisAPI

**Tempo estimado:** 7-10 dias  
**Prioridade:** 🔴 **CRÍTICA**

---

### 2. 🔴 Busca de Legislação (MOCKADO)

**Arquivo:** `apps/api/app/api/endpoints/knowledge.py`  
**Status:** Retorna sempre 2 leis fixas (LGPD e Lei de Licitações)

#### Problema
```python
# Linha 12-36 em knowledge.py
@router.get("/legislation/search")
async def search_legislation(
    query: str = Query(..., min_length=2),
    current_user: dict = Depends(get_current_user),
):
    """
    Pesquisa semântica de legislação (mock).
    """
    results = [
        {
            "id": "leg-1",
            "title": "Lei Geral de Proteção de Dados (Lei 13.709/2018)",
            # ... sempre os mesmos 2 resultados
        }
    ]
```

#### Solução Necessária
Implementar integração com:
- **Planalto:** Leis federais (http://www.planalto.gov.br/ccivil_03/)
- **Senado:** Legislação consolidada
- **Lexml:** Base de dados de legislação (https://www.lexml.gov.br/)

**Serviço já existe parcialmente:** `apps/api/app/services/legislation_service.py`  
**Tempo estimado:** 5-7 dias  
**Prioridade:** 🔴 **ALTA**

---

### 3. 🔴 Busca Web (MOCKADO)

**Arquivo:** `apps/api/app/api/endpoints/knowledge.py`  
**Status:** Retorna sempre 2 URLs fictícias (example.com)

#### Problema
```python
# Linha 73-85 em knowledge.py
@router.get("/web/search")
async def search_web(
    query: str = Query(..., min_length=2),
    current_user: dict = Depends(get_current_user),
):
    """
    Pesquisa web simplificada (mock).
    """
    results = [
        {"id": "web-1", "title": "...", "url": "https://example.com/artigo", ...}
    ]
```

#### Solução Necessária
Implementar integração com:
- **Google Custom Search API**
- **Bing Search API**
- **SerpAPI** (mais fácil)
- **Tavily AI** (otimizado para IA)

**Serviço já existe parcialmente:** `apps/api/app/services/web_search_service.py`  
**Tempo estimado:** 3-4 dias  
**Prioridade:** ⚠️ **MÉDIA**

---

## ⚠️ Funcionalidades Parcialmente Implementadas

### 4. ⚠️ Processamento de Arquivos ODT

**Arquivo:** `apps/api/app/api/endpoints/documents.py`  
**Status:** Upload aceito, mas texto não é extraído

#### Problema
```python
# Linha 152-155 em documents.py
elif doc_type == DocumentType.ODT:
    # TODO: Implementar extração de ODT (usar odfpy ou similar)
    logger.warning(f"ODT detectado mas extração não implementada: {file_path}")
    document.doc_metadata = {**document.doc_metadata, "extraction_pending": "ODT"}
```

#### Solução
```python
# Adicionar ao document_processor.py
async def extract_text_from_odt(file_path: str) -> str:
    from odf import text, teletype
    from odf.opendocument import load
    
    doc = load(file_path)
    all_paras = doc.getElementsByType(text.P)
    return "\n".join([teletype.extractText(p) for p in all_paras])
```

**Dependência:** `pip install odfpy`  
**Tempo estimado:** 1-2 dias  
**Prioridade:** ⚠️ **MÉDIA**

---

### 5. ⚠️ Descompactação de Arquivos ZIP

**Arquivo:** `apps/api/app/api/endpoints/documents.py`  
**Status:** Upload aceito, mas arquivos internos não são processados

#### Problema
```python
# Linha 161-164 em documents.py
elif doc_type == DocumentType.ZIP:
    # TODO: Implementar descompactação e processamento de arquivos internos
    logger.warning(f"ZIP detectado mas descompactação não implementada: {file_path}")
    document.doc_metadata = {**document.doc_metadata, "extraction_pending": "ZIP"}
```

#### Solução
```python
# Adicionar ao document_processor.py
async def extract_text_from_zip(file_path: str) -> str:
    import zipfile
    
    extracted_text = []
    with zipfile.ZipFile(file_path, 'r') as zip_ref:
        for file_info in zip_ref.filelist:
            if file_info.filename.endswith(('.pdf', '.docx', '.txt')):
                with zip_ref.open(file_info) as file:
                    # Processar cada arquivo
                    text = await extract_text_from_file(file, file_info.filename)
                    extracted_text.append(f"\n--- {file_info.filename} ---\n{text}")
    
    return "\n".join(extracted_text)
```

**Tempo estimado:** 2-3 dias  
**Prioridade:** ⚠️ **MÉDIA**

---

### 6. ⚠️ OCR Completo para PDFs Digitalizados

**Arquivo:** `apps/api/app/api/endpoints/documents.py`  
**Status:** Detecta PDFs digitalizados mas não aplica OCR

#### Problema
```python
# Linha 145-151 em documents.py
if doc_type == DocumentType.PDF:
    extracted_text = await extract_text_from_pdf(file_path)
    # Fallback para OCR se PDF estiver vazio (digitalizado)
    if not extracted_text or len(extracted_text.strip()) < 50:
        logger.info(f"PDF com pouco texto detectado, aplicando OCR: {file_path}")
        document.doc_metadata = {**document.doc_metadata, "ocr_applied": True}
        # TODO: Implementar conversão PDF->Imagens->OCR
```

#### Solução
```python
# Implementar em document_processor.py
async def extract_text_from_pdf_with_ocr(file_path: str, language: str = 'por') -> str:
    import pytesseract
    from pdf2image import convert_from_path
    from PIL import Image
    
    # Tentar extração normal primeiro
    text = await extract_text_from_pdf(file_path)
    
    # Se vazio, aplicar OCR
    if not text or len(text.strip()) < 50:
        images = convert_from_path(file_path, dpi=300)
        ocr_text = []
        
        for i, image in enumerate(images):
            # Pré-processamento
            image = image.convert('L')  # Grayscale
            
            # OCR
            page_text = pytesseract.image_to_string(
                image, 
                lang=language,
                config='--psm 1'
            )
            ocr_text.append(f"\n--- Página {i+1} ---\n{page_text}")
        
        return "\n".join(ocr_text)
    
    return text
```

**Dependências:**
```bash
brew install tesseract tesseract-lang  # macOS
pip install pytesseract pdf2image pillow
```

**Tempo estimado:** 3-4 dias  
**Prioridade:** ⚠️ **ALTA**

---

### 7. ⚠️ Transcrição de Áudio/Vídeo

**Arquivo:** `apps/api/app/api/endpoints/documents.py`  
**Status:** Apenas marca como "queued" mas não transcreve

#### Problema
```python
# Linha 437-455 em documents.py
@router.post("/{document_id}/transcribe")
async def transcribe_audio(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Transcrever áudio
    """
    # ... apenas marca status mas não transcreve
    document.doc_metadata = {**document.doc_metadata, "transcription": "queued"}
```

#### Solução
```python
# Implementar em document_processor.py
async def transcribe_audio_video(file_path: str, language: str = 'pt') -> dict:
    import whisper
    from pydub import AudioSegment
    
    # Carregar modelo Whisper
    model = whisper.load_model("base")
    
    # Converter para formato suportado
    audio = AudioSegment.from_file(file_path)
    temp_path = "/tmp/audio_temp.wav"
    audio.export(temp_path, format="wav")
    
    # Transcrever
    result = model.transcribe(temp_path, language=language)
    
    return {
        "text": result["text"],
        "segments": result["segments"],
        "language": result["language"]
    }
```

**Dependências:**
```bash
brew install ffmpeg  # macOS
pip install openai-whisper pydub
```

**Tempo estimado:** 3-4 dias  
**Prioridade:** ⚠️ **MÉDIA**

---

### 8. ⚠️ Geração de Podcasts (TTS)

**Arquivo:** `apps/api/app/api/endpoints/documents.py`  
**Status:** Retorna URL fictícia que não existe

#### Problema
```python
# Linha 458-499 em documents.py
@router.post("/{document_id}/podcast")
async def generate_podcast(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # ... apenas retorna URL fictícia
    podcast_url = f"/documents/{document_id}/podcast.mp3"
```

#### Solução
O serviço `podcast_service.py` já existe, mas precisa de implementação completa com:
- **OpenAI TTS API** (gpt-4o-audio-preview)
- **Google Cloud TTS**
- **Amazon Polly**
- **ElevenLabs** (melhor qualidade)

**Tempo estimado:** 5-7 dias  
**Prioridade:** 🟡 **BAIXA** (feature premium)

---

### 9. ⚠️ Geração de Diagramas

**Status:** Serviço existe (`diagram_service.py`) mas não está conectado ao endpoint

#### Solução
Integrar o serviço existente `diagram_service.py` com:
- Mermaid.js para diagramas de fluxo
- Graphviz para grafos
- Exportação para PNG/SVG

**Tempo estimado:** 2-3 dias  
**Prioridade:** 🟡 **BAIXA**

---

### 10. ⚠️ Scraping de URLs

**Arquivo:** `apps/api/app/api/endpoints/documents.py`  
**Status:** Endpoint existe mas implementação é básica

#### Problema
```python
# Linha 278-346 em documents.py
@router.post("/from-url")
async def create_document_from_url(
    url: str = Form(...),
    # ... implementação básica
```

O serviço `url_scraper_service.py` existe mas pode precisar de melhorias:
- Suporte a JavaScript (Playwright/Selenium)
- Remoção de elementos indesejados (ads, menus)
- Extração inteligente de conteúdo principal

**Tempo estimado:** 2-3 dias  
**Prioridade:** ⚠️ **MÉDIA**

---

## 🔴 Funcionalidades Completamente Ausentes

### 11. 🔴 Integrações CNJ/DJEN

**Status:** Não implementado

#### O que falta
- Busca de metadados de processos via API CNJ
- Consulta ao Diário de Justiça Eletrônico Nacional (DJEN)
- Padrões de metadados CNJ

**Tempo estimado:** 7-10 dias  
**Prioridade:** 🟡 **BAIXA** (funcionalidade específica)

---

### 12. 🔴 Sistema de Grupos para Compartilhamento

**Status:** Parcialmente implementado

O sistema de compartilhamento existe em `library.py`, mas falta:
- Gestão de grupos de usuários
- Permissões hierárquicas (admin, editor, viewer)
- Notificações de compartilhamento

**Tempo estimado:** 5-7 dias  
**Prioridade:** ⚠️ **MÉDIA**

---

## ✅ O Que Está Funcionando Bem (Não Precisa Mexer)

### Implementações Completas
1. ✅ **Sistema de Autenticação** - JWT, perfis Individual/Institucional
2. ✅ **Upload de Documentos** - PDF, DOCX, imagens, áudio, vídeo
3. ✅ **Extração de Texto** - PDF e DOCX funcionais
4. ✅ **OCR para Imagens** - Tesseract funcionando
5. ✅ **Sistema Multi-Agente IA** - Claude, Gemini, GPT com orquestração
6. ✅ **Editor de Documentos** - Geração com 5 níveis de esforço
7. ✅ **Exportação** - DOCX, HTML, TXT, PDF
8. ✅ **Biblioteca** - CRUD completo de itens e pastas
9. ✅ **Bibliotecários** - CRUD completo
10. ✅ **Chat com IA** - Funcional
11. ✅ **Templates** - Sistema de aplicação de templates DOCX
12. ✅ **Assinatura Digital** - Automática individual e institucional
13. ✅ **Compartilhamento de Documentos** - Links públicos funcionais
14. ✅ **Workers Celery** - Tarefas assíncronas

---

## 📊 Priorização de Implementação

### 🔴 Sprint 1 - CRÍTICO (1-2 semanas)
**Objetivo:** Eliminar funcionalidades mockadas que representam risco

1. **Implementar busca real de Jurisprudência** (7-10 dias)
   - Integração com APIs de tribunais
   - Ou adicionar avisos claros de que é demonstração

2. **Implementar busca real de Legislação** (5-7 dias)
   - Integração com Planalto/Lexml
   - Ou adicionar avisos de demonstração

3. **Completar OCR para PDFs** (3-4 dias)
   - Implementar conversão PDF→Imagens→OCR

**Resultado:** Eliminar risco jurídico das funcionalidades mockadas

---

### ⚠️ Sprint 2 - ALTA PRIORIDADE (2-3 semanas)
**Objetivo:** Completar processamento de arquivos

4. **Extração de ODT** (1-2 dias)
5. **Descompactação de ZIP** (2-3 dias)
6. **Transcrição de Áudio/Vídeo** (3-4 dias)
7. **Melhorar Scraping de URLs** (2-3 dias)

**Resultado:** Todos os formatos de arquivo prometidos funcionando

---

### 🟡 Sprint 3 - MÉDIA PRIORIDADE (2-3 semanas)
**Objetivo:** Features avançadas

8. **Busca Web Real** (3-4 dias)
9. **Sistema de Grupos** (5-7 dias)
10. **Geração de Diagramas** (2-3 dias)

**Resultado:** Features completas conforme manual

---

### 🟢 Sprint 4 - BAIXA PRIORIDADE (Backlog)
**Objetivo:** Features premium/específicas

11. **Geração de Podcasts TTS** (5-7 dias)
12. **Integrações CNJ/DJEN** (7-10 dias)

---

## 🛠️ Dependências a Instalar

### Essenciais (Sprint 1-2)
```bash
# Processamento de documentos
pip install odfpy              # Para ODT
pip install pytesseract pdf2image pillow  # OCR completo

# Transcrição
pip install openai-whisper pydub

# Sistema
brew install tesseract tesseract-lang ffmpeg  # macOS
```

### Opcionais (Sprint 3-4)
```bash
# Busca web
pip install google-api-python-client  # Google Search
pip install serpapi                   # SerpAPI (mais fácil)

# TTS para podcasts
pip install openai  # OpenAI TTS
pip install google-cloud-texttospeech
```

---

## 📈 Métricas de Progresso

### Status Atual
- **Endpoints implementados:** 40+
- **Serviços criados:** 20+
- **Funcionalidades completas:** 60%
- **Funcionalidades mockadas:** 15%
- **Funcionalidades parciais:** 25%

### Meta para MVP em Produção
- [ ] 0% de funcionalidades mockadas (remover ou implementar)
- [ ] 90%+ de funcionalidades completas
- [ ] < 10% de funcionalidades parciais (claramente documentadas)

---

## 🎯 Recomendações Finais

### Para Produção Imediata
1. **Manter avisos** de que Jurisprudência, Legislação e Web Search são demonstrações
2. **Desabilitar** botões de funcionalidades não implementadas
3. **Documentar** claramente no manual o que é real vs. demonstração

### Para Versão 1.0 Completa
1. **Priorizar** implementação de buscas reais (Jurisprudência e Legislação)
2. **Completar** processamento de todos os formatos de arquivo
3. **Implementar** transcrição de áudio/vídeo
4. **Melhorar** sistema de compartilhamento com grupos

### Para Versão 2.0 (Features Premium)
1. Geração de podcasts com TTS de alta qualidade
2. Geração de diagramas visuais
3. Integrações CNJ/DJEN
4. Colaboração em tempo real

---

## 📞 Próximos Passos

1. **Revisar este relatório** com a equipe
2. **Decidir prioridades** com base no roadmap de produto
3. **Alocar recursos** para os sprints
4. **Implementar** Sprint 1 (CRÍTICO) primeiro
5. **Testar** cada funcionalidade antes de marcar como completa

---

**Documento criado por:** Antigravity AI  
**Data:** 23 de novembro de 2025  
**Baseado em:** Análise completa do código em `/apps/api/`
