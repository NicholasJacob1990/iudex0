# Funcionalidades Mockadas ou Não Implementadas - Iudex

**Data:** 21 de novembro de 2025  
**Baseado em:** Verificação completa do código vs manual.md

---

## 🔴 Funcionalidades em Modo de Demonstração (MOCKADAS)

### 1. 🔴 Jurisprudência - **100% MOCKADA**

**O que o manual promete:**
> "A aba Jurisprudência permite que o usuário pesquise e adicione precedentes judiciais atualizados para fundamentar suas minutas, garantindo fidelidade jurídica e citações precisas."
> 
> "Modelos de IA não são treinados com jurisprudência atualizada e podem criar precedentes inexistentes ou desatualizados ('alucinações jurídicas'). Ciente disso, a busca de jurisprudência do MinutaIA garante a pesquisa em bases oficiais dos tribunais, com precedentes reais."

**Realidade no código:**
```python
# apps/api/app/api/endpoints/knowledge.py (linhas 39-70)

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
            "summary": "Caracteriza dano moral in re ipsa a inscrição indevida...",
            "date": "2024-03-15",
            "tags": ["Dano Moral", "Consumidor"],
            "processNumber": "REsp 1.234.567/SP",
        },
        {
            "id": "jp-2",
            "court": "STF",
            "title": "Tema 1234 - Repercussão Geral",
            "summary": "Inconstitucional a exigência de garantia...",
            "date": "2024-02-10",
            "tags": ["Tributário", "Livre Iniciativa"],
            "processNumber": "RE 987.654/RJ",
        },
    ]
    if court:
        data = [item for item in data if item["court"] == court]
    return {"items": data, "total": len(data), "query": query, "court": court}
```

**Problemas:**
- ❌ Retorna sempre os mesmos 2 precedentes fixos, independente da busca
- ❌ Não há integração com APIs de tribunais (STF, STJ, TRFs, TJs)
- ❌ **RISCO JURÍDICO ALTO:** Usuários podem citar precedentes inexistentes
- ❌ Filtro por tribunal é simulado (apenas filtra os 2 resultados fixos)

**Status:** 🔴 **CRÍTICO - Não usar em produção**

**Aviso no Frontend:** ✅ Implementado (21/11/2025)

---

### 2. 🔴 Pesquisa Web - **100% MOCKADA**

**O que o manual promete:**
> "Busca inteligente na internet."
> "O Iudex consulta fontes confiáveis automaticamente antes de gerar uma minuta."

**Realidade no código:**
```python
# apps/api/app/api/endpoints/knowledge.py (linhas 73-85)

@router.get("/web/search")
async def search_web(
    query: str = Query(..., min_length=2),
    current_user: dict = Depends(get_current_user),
):
    """
    Pesquisa web simplificada (mock).
    """
    results = [
        {"id": "web-1", "title": "Resumo sobre repercussão geral", 
         "url": "https://example.com/artigo", 
         "snippet": "Entenda como funciona a repercussão geral no STF..."},
        {"id": "web-2", "title": "Guia prático de temas repetitivos", 
         "url": "https://example.com/guia", 
         "snippet": "Saiba como localizar e citar temas repetitivos do STJ..."},
    ]
    return {"items": results, "total": len(results), "query": query}
```

**Problemas:**
- ❌ Retorna sempre os mesmos 2 resultados fixos
- ❌ Não há integração com motores de busca (Google, Bing, DuckDuckGo, Tavily, SerpAPI)
- ❌ URLs são fictícias (example.com)
- ❌ Busca não funciona de verdade

**Status:** 🔴 **Não funcional**

**Aviso no Frontend:** ✅ Implementado (21/11/2025)

---

### 3. 🔴 Legislação - **100% MOCKADA**

**O que o manual promete:**
> Embora não esteja explicitamente no manual, a aba "Legislação" existe na sidebar.

**Realidade no código:**
```python
# apps/api/app/api/endpoints/knowledge.py (linhas 12-36)

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
            "excerpt": "Dispõe sobre o tratamento de dados pessoais...",
            "status": "Consolidada",
            "updated_at": "2024-04-01T10:00:00Z",
        },
        {
            "id": "leg-2",
            "title": "Lei nº 14.133/2021 - Nova Lei de Licitações",
            "excerpt": "Institui normas gerais de licitação e contratação...",
            "status": "Atualizada em 34 minutos",
            "updated_at": "2024-04-10T09:30:00Z",
        },
    ]
    return {"items": results, "total": len(results), "query": query}
```

**Problemas:**
- ❌ Retorna sempre os mesmos 2 resultados fixos
- ❌ Não há integração com bases legislativas (Planalto, Senado, Câmara)
- ❌ Busca não funciona

**Status:** 🔴 **Não funcional**

---

## ⚠️ Funcionalidades Parcialmente Implementadas

### 4. ⚠️ Podcasts - **PLACEHOLDER**

**O que o manual promete:**
> "Podcast: cria uma experiência narrativa mais elaborada e envolvente, com explicação em linguagem simples, sobre os documentos selecionados."
> "Podcasts: acessa os podcasts gerados na aba Documentos."

**Realidade no código:**
```python
# apps/api/app/api/endpoints/documents.py (linhas 267-286)

@router.post("/{document_id}/podcast")
async def generate_podcast(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Gerar podcast do documento
    """
    result = await db.execute(
        select(Document).where(Document.id == document_id, Document.user_id == current_user.id)
    )
    document = result.scalars().first()
    if not document:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    podcast_url = f"/documents/{document_id}/podcast.mp3"
    document.doc_metadata = {**document.doc_metadata, "podcast_url": podcast_url}
    await db.commit()
    return {"podcast_url": podcast_url, "document_id": document_id}
```

**Problemas:**
- ❌ Retorna URL fictícia que não existe
- ❌ Não há geração real de áudio (TTS - Text-to-Speech)
- ❌ Não há integração com serviços de síntese de voz (Google TTS, Amazon Polly, ElevenLabs, etc.)

**Status:** ⚠️ **Endpoint existe mas não funciona**

---

### 5. ⚠️ Resumo em Áudio - **PLACEHOLDER**

**O que o manual promete:**
> "Resumo em Áudio: fornece uma síntese objetiva e direta do conteúdo dos documentos selecionados."

**Realidade:**
- ❌ Mesmo problema do Podcast
- ❌ Não há diferenciação entre "Resumo em Áudio" e "Podcast" no código
- ❌ Ambos retornariam URLs fictícias

**Status:** ⚠️ **Não implementado**

---

### 6. ⚠️ Diagramas - **NÃO ENCONTRADO**

**O que o manual promete:**
> "Diagrama: cria um mapa mental sobre os documentos."
> "Diagramas: visualiza diagramas criados na aba Documentos."

**Realidade:**
- ❌ Não encontrei endpoint específico para geração de diagramas
- ❌ Ícone existe na sidebar (`resourceShortcuts` em `sidebar-pro.tsx`)
- ❌ Não há integração com bibliotecas de diagramas (Mermaid, Graphviz, D3.js)

**Status:** 🔴 **Não implementado**

---

### 7. ⚠️ Transcrição de Áudio/Vídeo - **PLACEHOLDER**

**O que o manual promete:**
> "Transcrever: para transformar audiências gravadas em texto"
> "Áudio/Vídeo: MP3, WAV, MP4, WebM"

**Realidade no código:**
```python
# apps/api/app/api/endpoints/documents.py (linhas 246-264)

@router.post("/{document_id}/transcribe")
async def transcribe_audio(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Transcrever áudio
    """
    result = await db.execute(
        select(Document).where(Document.id == document_id, Document.user_id == current_user.id)
    )
    document = result.scalars().first()
    if not document:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    document.doc_metadata = {**document.doc_metadata, "transcription": "queued"}
    await db.commit()
    return {"message": "Transcription initiated", "document_id": document_id}
```

**Problemas:**
- ❌ Apenas marca como "queued" mas não transcreve
- ❌ Não há integração com Whisper (OpenAI) ou Google Speech-to-Text
- ❌ Arquivos de áudio/vídeo são aceitos no upload (após correção de 21/11), mas não são processados

**Status:** ⚠️ **Upload aceito, processamento não implementado**

---

### 8. ⚠️ Descompactação de ZIP - **NÃO IMPLEMENTADA**

**O que o manual promete:**
> "Arquivos ZIP: descompacta automaticamente e importa todos os documentos compatíveis mantendo a ordem original."

**Realidade no código:**
```python
# apps/api/app/api/endpoints/documents.py (linhas 161-164)

elif doc_type == DocumentType.ZIP:
    # TODO: Implementar descompactação e processamento de arquivos internos
    logger.warning(f"ZIP detectado mas descompactação não implementada: {file_path}")
    document.doc_metadata = {**document.doc_metadata, "extraction_pending": "ZIP"}
```

**Problemas:**
- ⚠️ Upload aceito (após correção de 21/11)
- ❌ Arquivo é salvo mas não é descompactado
- ❌ Documentos internos não são processados

**Status:** ⚠️ **Upload aceito, processamento não implementado**

---

### 9. ⚠️ Extração de ODT - **NÃO IMPLEMENTADA**

**O que o manual promete:**
> "Tipos de arquivo suportados: [...] ODT"

**Realidade no código:**
```python
# apps/api/app/api/endpoints/documents.py (linhas 152-155)

elif doc_type == DocumentType.ODT:
    # TODO: Implementar extração de ODT (usar odfpy ou similar)
    logger.warning(f"ODT detectado mas extração não implementada: {file_path}")
    document.doc_metadata = {**document.doc_metadata, "extraction_pending": "ODT"}
```

**Problemas:**
- ⚠️ Upload aceito (após correção de 21/11)
- ❌ Texto não é extraído
- ❌ Precisa biblioteca `odfpy` ou similar

**Status:** ⚠️ **Upload aceito, extração não implementada**

---

### 10. ⚠️ OCR para PDFs Digitalizados - **PARCIALMENTE IMPLEMENTADO**

**O que o manual promete:**
> "Quando o botão está ativado, a plataforma identificará automaticamente as páginas do PDF que precisam de reconhecimento de texto e executará automaticamente."

**Realidade no código:**
```python
# apps/api/app/api/endpoints/documents.py (linhas 145-151)

if doc_type == DocumentType.PDF:
    extracted_text = await extract_text_from_pdf(file_path)
    # Fallback para OCR se PDF estiver vazio (digitalizado)
    if not extracted_text or len(extracted_text.strip()) < 50:
        logger.info(f"PDF com pouco texto detectado, aplicando OCR: {file_path}")
        document.doc_metadata = {**document.doc_metadata, "ocr_applied": True}
        # TODO: Implementar conversão PDF->Imagens->OCR
        # Por enquanto, mantém o texto extraído (mesmo que vazio)
```

**Problemas:**
- ✅ Detecta PDFs digitalizados (implementado 21/11)
- ❌ Não converte PDF para imagens
- ❌ Não aplica OCR automaticamente
- ⚠️ Precisa `pdf2image` + `pytesseract`

**Status:** ⚠️ **Detecção implementada, conversão pendente**

---

## 🔴 Funcionalidades Completamente Ausentes

### 11. 🔴 Compartilhamento - **NÃO IMPLEMENTADO**

**O que o manual promete:**
> "A aba Compartilhamentos permite que o usuário gerencie todos os recursos (documentos, modelos, jurisprudência, prompts, assistentes e pastas) compartilhados com outros usuários ou grupos"
> 
> "No compartilhamento com usuários, após incluir os e-mails, deverá ser escolhido o nível de permissão."
> 
> "Usuários com permissão para visualizar: poderão apenas ativar o bibliotecário"
> 
> "Usuários com permissão para editar: poderão incluir e remover itens"

**Realidade no código:**
```python
# apps/api/app/api/endpoints/library.py (linhas 234-243)

@router.post("/share")
async def share_resource(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Compartilhar recurso
    """
    # TODO: Implementar compartilhamento
    return {"message": "Resource shared"}
```

**Problemas:**
- ❌ Endpoint retorna sucesso falso
- ❌ Não há lógica de ACL (Access Control List)
- ❌ Não há verificação de permissões (`is_shared`, `shared_with`)
- ❌ Não há sistema de grupos
- ❌ Não há notificações de compartilhamento

**Status:** 🔴 **Completamente ausente**

---

### 12. 🔴 Ativação de Bibliotecários - **PARCIAL**

**O que o manual promete:**
> "Funcionam como agrupamentos inteligentes de recursos que o usuário, em vez de carregar manualmente cada documento, modelo e precedente toda vez que for usá-los, crie o bibliotecário com aqueles recursos usados frequentemente e acione-o automaticamente com um único clique, no botão 'Ativar'."

**Realidade:**
- ✅ CRUD de bibliotecários funciona
- ✅ Interface existe
- ❌ Botão "Ativar" não carrega recursos no contexto da minuta
- ❌ Não há integração com o store de contexto do chat

**Status:** ⚠️ **Interface pronta, lógica de ativação ausente**

---

### 13. 🔴 Importação de Google Drive - **NÃO IMPLEMENTADO**

**O que o manual não menciona, mas o frontend promete:**
```tsx
// apps/web/src/components/dashboard/documents-dropzone.tsx (linha 41)
<span className="chip bg-sand text-foreground">Google Drive</span>
```

**Realidade:**
- ❌ Botão existe no frontend
- ❌ Não há endpoint no backend
- ❌ Não há integração com Google Drive API

**Status:** 🔴 **Não implementado**

---

### 14. 🔴 Importação via URL - **NÃO IMPLEMENTADO**

**O que o manual promete:**
> "Botões de carregamento: [...] em 'URL', para carregar arquivos e sites da internet"

**Realidade:**
```tsx
// apps/web/src/components/dashboard/documents-dropzone.tsx (linha 43)
<span className="chip bg-sand text-foreground">URL</span>
```

**Problemas:**
- ❌ Botão existe no frontend
- ❌ Não há endpoint no backend para importar de URL
- ❌ Não há scraping de sites

**Status:** 🔴 **Não implementado**

---

### 15. 🔴 Inserir Texto Manualmente - **NÃO IMPLEMENTADO**

**O que o manual promete:**
> "Botões de carregamento: [...] em 'Inserir Texto', para inserir textos manualmente"

**Realidade:**
```tsx
// apps/web/src/components/dashboard/documents-dropzone.tsx (linha 44)
<span className="chip bg-sand text-foreground">Inserir texto</span>
```

**Problemas:**
- ❌ Botão existe no frontend
- ❌ Não abre modal ou textarea
- ❌ Não há endpoint para criar documento a partir de texto

**Status:** 🔴 **Não implementado**

---

### 16. 🔴 Aplicar Template com Marcador `(minuta)` em DOCX - **CORRIGIDO PARCIALMENTE**

**O que o manual promete:**
> "No local onde o conteúdo da minuta deve aparecer, digite exatamente: (minuta)"
> "Salve no formato DOCX"
> "Faça o upload e configure sua formatação"

**Realidade:**
- ✅ Backend agora suporta marcador `(minuta)` (corrigido 21/11)
- ❌ Não há interface para upload de template DOCX
- ❌ Não há interface para "Aplicar template" conforme manual
- ❌ Funcionalidade de "Configurar formatação" não existe

**Status:** ⚠️ **Backend pronto, frontend ausente**

---

### 17. 🔴 Metadados CNJ - **NÃO IMPLEMENTADO**

**O que o frontend sugere:**
```tsx
// apps/web/src/components/layout/sidebar-pro.tsx (linha 40)
'Metadados CNJ': Scale,
```

**Realidade:**
- ❌ Ícone existe na sidebar
- ❌ Não há funcionalidade relacionada
- ❌ Não há endpoint no backend

**Status:** 🔴 **Não implementado**

---

### 18. 🔴 Comunicações DJEN - **NÃO IMPLEMENTADO**

**O que o frontend sugere:**
```tsx
// apps/web/src/components/layout/sidebar-pro.tsx (linha 41)
'Comunicações DJEN': Bot,
```

**Realidade:**
- ❌ Ícone existe na sidebar
- ❌ Não há funcionalidade relacionada
- ❌ Não há endpoint no backend

**Status:** 🔴 **Não implementado**

---

## 📊 Resumo Estatístico

### Por Categoria:

| Categoria | Total | Mockadas | Parciais | Ausentes | Funcionais |
|-----------|-------|----------|----------|----------|------------|
| **Busca/Pesquisa** | 3 | 3 | 0 | 0 | 0 |
| **Processamento de Arquivos** | 5 | 0 | 4 | 1 | 0 |
| **Geração de Conteúdo** | 3 | 0 | 2 | 1 | 0 |
| **Compartilhamento** | 2 | 0 | 1 | 1 | 0 |
| **Importação** | 3 | 0 | 0 | 3 | 0 |
| **Templates** | 1 | 0 | 1 | 0 | 0 |
| **Integrações Externas** | 2 | 0 | 0 | 2 | 0 |
| **TOTAL** | **19** | **3** | **8** | **8** | **0** |

### Por Criticidade:

| Nível | Quantidade | Funcionalidades |
|-------|------------|-----------------|
| 🔴 **Crítico** (Risco jurídico/segurança) | 3 | Jurisprudência, Legislação, Compartilhamento |
| ⚠️ **Alto** (Prometido mas não funciona) | 8 | Podcasts, Diagramas, Transcrição, ZIP, ODT, OCR completo, Templates UI, Bibliotecários |
| 🟡 **Médio** (Botões sem função) | 8 | Web Search, Google Drive, URL, Inserir Texto, Metadados CNJ, DJEN, Resumo Áudio, Ativação |

---

## 🎯 Recomendações de Priorização

### Prioridade 1 - Crítico (1-2 semanas):
1. **Jurisprudência Real:** Integrar com APIs de tribunais ou remover funcionalidade
2. **Compartilhamento:** Implementar ACL completo ou remover promessa do manual
3. **Avisos Claros:** Manter avisos de demonstração (✅ já implementado)

### Prioridade 2 - Alto (2-4 semanas):
4. **Transcrição de Áudio:** Integrar Whisper ou similar
5. **Descompactação ZIP:** Implementar processamento de arquivos internos
6. **OCR Completo:** Implementar conversão PDF→Imagens→OCR
7. **Templates UI:** Criar interface para aplicar templates conforme manual

### Prioridade 3 - Médio (1-2 meses):
8. **Web Search Real:** Integrar Tavily ou SerpAPI
9. **Podcasts/Áudio:** Integrar TTS (Text-to-Speech)
10. **Diagramas:** Integrar Mermaid ou similar
11. **Importação URL:** Implementar scraping de sites

### Prioridade 4 - Baixa (Backlog):
12. **Google Drive:** Integração com API do Google
13. **Metadados CNJ/DJEN:** Definir escopo e implementar
14. **Legislação Real:** Integrar com bases oficiais

---

## ✅ O Que Está Funcionando Bem

Para contexto, estas funcionalidades **estão totalmente implementadas**:

1. ✅ Sistema de autenticação (JWT, perfis Individual/Institucional)
2. ✅ Upload de documentos (PDF, DOCX, imagens)
3. ✅ Extração de texto (PDF, DOCX)
4. ✅ OCR para imagens (Tesseract)
5. ✅ Geração de minutas multi-agente (Claude, Gemini, GPT)
6. ✅ Editor de documentos (Tiptap com formatação rica)
7. ✅ Exportação (DOCX, HTML, TXT, Impressão)
8. ✅ Biblioteca (CRUD de itens e pastas)
9. ✅ Bibliotecários (CRUD)
10. ✅ Chat com IA
11. ✅ Modo Rigoroso para templates
12. ✅ Assinatura digital automática

---

## 📝 Conclusão

**Taxa de Funcionalidades Mockadas/Não Implementadas:** **19 de 38 funcionalidades** mencionadas no manual (50%)

**Recomendação:** Antes de lançar em produção:
1. ✅ Manter avisos de demonstração (já implementado)
2. ⚠️ Remover botões de funcionalidades não implementadas OU
3. ⚠️ Implementar as funcionalidades críticas (Jurisprudência, Compartilhamento)
4. ✅ Atualizar manual para refletir o estado real do sistema

---

**Documento gerado automaticamente pela análise holística do código.**  
**Última atualização:** 21/11/2025 - 14:30



