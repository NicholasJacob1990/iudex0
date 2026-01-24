#!/bin/bash
# Script para processar aulas de Direito Administrativo em ordem sequencial

cd /Users/nicholasjacob/Documents/Aplicativos/Iudex
source venv311/bin/activate

# Diretório de saída
OUTPUT_DIR="/Users/nicholasjacob/Downloads/MediaExtractor/Processados"
mkdir -p "$OUTPUT_DIR"

echo "🚀 Iniciando processamento sequencial de Direito Administrativo..."

# Array de arquivos na ordem correta
FILES=(
    "/Users/nicholasjacob/Downloads/MediaExtractor/Administrativo Disponível - Direito Adm. Bloco 1 - Parte 1(15 minutos).mp3"
    "/Users/nicholasjacob/Downloads/MediaExtractor/Administrativo Disponível - Direito Adm. Bloco 1 - Parte 2(14 minutos.mp3"
    "/Users/nicholasjacob/Downloads/MediaExtractor/Administrativo Disponível - Direito Adm. Bloco 2 - Parte 1(15 minutos).mp3"
    "/Users/nicholasjacob/Downloads/MediaExtractor/Administrativo Disponível - Direito Adm. Bloco 2 - Parte 2(14 minutos.mp3"
    "/Users/nicholasjacob/Downloads/MediaExtractor/Administrativo Disponível - Direito Adm. Bloco 3 - Parte 1(5 minutos)a.mp3"
    "/Users/nicholasjacob/Downloads/MediaExtractor/Administrativo Disponível - Direito Adm. Bloco 3 - Parte 2(5 minutos)a.mp3"
    "/Users/nicholasjacob/Downloads/MediaExtractor/Administrativo Disponível - Direito Adm. Bloco 3 - Parte 3(5 minutos)a.mp3"
    "/Users/nicholasjacob/Downloads/MediaExtractor/Administrativo Disponível - Direito Adm. Bloco 3 - Parte 4(5 minutos)a.mp3"
    "/Users/nicholasjacob/Downloads/MediaExtractor/Administrativo Disponível - Direito Adm. Bloco 3 - Parte 5(5 minutos)a.mp3"
    "/Users/nicholasjacob/Downloads/MediaExtractor/Administrativo Disponível - Direito Adm. Bloco 3 - Parte 6(4 minutos e.mp3"
    "/Users/nicholasjacob/Downloads/MediaExtractor/Administrativo Disponível - Direito Adm. Bloco 4 - Parte 1(10 minutos).mp3"
    "/Users/nicholasjacob/Downloads/MediaExtractor/Administrativo Disponível - Direito Adm. Bloco 4 - Parte 2(10 minutos).mp3"
    "/Users/nicholasjacob/Downloads/MediaExtractor/Administrativo Disponível - Direito Adm. Bloco 4 - Parte 3(9 minutos e.mp3"
)

# Processar cada arquivo gerando apenas RAW (transcrição)
RAW_FILES=()
for i in "${!FILES[@]}"; do
    FILE="${FILES[$i]}"
    NUM=$((i + 1))
    
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📝 Processando arquivo $NUM de ${#FILES[@]}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    if [ -f "$FILE" ]; then
        echo "✅ Arquivo encontrado: $(basename "$FILE")"
        
        # Processa apenas transcrição (skip formatting para ir mais rápido)
        python mlx_vomo.py "$FILE" --skip-formatting
        
        # Localiza o arquivo RAW gerado
        BASE_NAME=$(basename "$FILE" .mp3)
        RAW_FILE="${FILE%.*}_RAW.txt"
        
        if [ -f "$RAW_FILE" ]; then
            echo "✅ Transcrição gerada: $RAW_FILE"
            RAW_FILES+=("$RAW_FILE")
        else
            echo "❌ ERRO: Transcrição não encontrada para $FILE"
        fi
    else
        echo "❌ ERRO: Arquivo não encontrado: $FILE"
    fi
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📚 Consolidando transcrições em arquivo único..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Arquivo consolidado
CONSOLIDATED_RAW="$OUTPUT_DIR/Direito_Administrativo_CONSOLIDADO_RAW.txt"
> "$CONSOLIDATED_RAW"

# Concatenar todos os RAW files
for i in "${!RAW_FILES[@]}"; do
    RAW="${RAW_FILES[$i]}"
    NUM=$((i + 1))
    
    echo "" >> "$CONSOLIDATED_RAW"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" >> "$CONSOLIDATED_RAW"
    echo "BLOCO $NUM" >> "$CONSOLIDATED_RAW"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" >> "$CONSOLIDATED_RAW"
    echo "" >> "$CONSOLIDATED_RAW"
    
    cat "$RAW" >> "$CONSOLIDATED_RAW"
done

echo "✅ Arquivo consolidado criado: $CONSOLIDATED_RAW"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎨 Formatando apostila final no modo FIDELIDADE..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Processar o arquivo consolidado no modo fidelidade
python mlx_vomo.py "$CONSOLIDATED_RAW" --mode=FIDELIDADE

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✨ PROCESSAMENTO CONCLUÍDO!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📄 Apostila final: ${CONSOLIDATED_RAW%_RAW.txt}_FIDELIDADE.docx"
echo "📄 Markdown: ${CONSOLIDATED_RAW%_RAW.txt}_FIDELIDADE.md"
echo ""
