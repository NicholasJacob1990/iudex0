# Batch Processor - Guia de Uso

## Visão Geral

O `batch_processor.py` detecta e processa automaticamente vídeos sequenciais da mesma disciplina/aula como uma única transcrição.

## Como Funciona

1. **Detecção Automática**: Escaneia o diretório e agrupa vídeos pelo padrão:
   ```
   {Num}_{Disciplina}_Aula_{N}_Bloco_{M}.mp4
   ```

2. **Agrupamento**: Vídeos com mesma disciplina e número de aula são agrupados
   - Exemplo: `02_Previdenciario_Aula_01_Bloco_01.mp4` até `06_Previdenciario_Aula_01_Bloco_05.mp4`
   - Grupo: `Previdenciario_Aula_01` (5 blocos)

3. **Processamento**: Para cada grupo:
   - Extrai e concatena áudios de todos os blocos
   - Transcreve como um único arquivo
   - Gera apostila completa + resumo (MD e DOCX)

## Uso

### Processar Pasta Específica

```bash
./venv/bin/python batch_processor.py "/Users/nicholasjacob/Documents/Aplicativos/Iudex/Reta_Final_PGM/Direito do Trabalho e Previdenciário"
```

### Processar Todas as Pastas (Loop)

```bash
#!/bin/bash
BASE_DIR="/Users/nicholasjacob/Documents/Aplicativos/Iudex/Reta_Final_PGM"

for dir in "$BASE_DIR"/*; do
    if [ -d "$dir" ]; then
        echo "Processando: $dir"
        ./venv/bin/python batch_processor.py "$dir"
    fi
done
```

## Arquivos Gerados

Para cada grupo (ex: `Previdenciario_Aula_01`):

- `Previdenciario_Aula_01_RAW.txt` - Transcrição bruta
- `Previdenciario_Aula_01_APOSTILA_COMPLETA.md` - Markdown completo
- `Previdenciario_Aula_01_COMPLETA_APOSTILA.docx` - Word completo
- `Previdenciario_Aula_01_RESUMO.md` - Markdown resumido
- `Previdenciario_Aula_01_RESUMO_APOSTILA.docx` - Word resumido

## Vantagens

✅ **Transcrição unificada**: Todos os blocos de uma aula em um único documento
✅ **Contexto preservado**: O professor não "perde" o raciocínio entre blocos
✅ **Economia de processamento**: Um único processo de formatação e validação
✅ **Organização automática**: Detecta padrões sem configuração manual

## Requisitos

- FFmpeg instalado (`brew install ffmpeg`)
- Virtual environment ativado com dependências instaladas
- Vídeos seguindo o padrão de nomenclatura esperado
