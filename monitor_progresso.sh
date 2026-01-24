#!/bin/bash
# Script de monitoramento contínuo do processamento

LOG_FILE="/tmp/processo_admin_log.txt"
MONITOR_FILE="/tmp/monitor_status.txt"

echo "🔍 Monitor de Progresso - Direito Administrativo" > $MONITOR_FILE
echo "Início: $(date)" >> $MONITOR_FILE
echo "" >> $MONITOR_FILE

while true; do
    clear
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🔍 MONITOR DE PROGRESSO - DIREITO ADMINISTRATIVO"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "⏰ Atualização: $(date '+%H:%M:%S')"
    echo ""
    
    # Conta quantos arquivos já foram processados
    PROCESSADOS=$(grep -c "✅ Transcrição gerada:" $LOG_FILE 2>/dev/null || echo "0")
    TOTAL=13
    
    echo "📊 Arquivos Processados: $PROCESSADOS / $TOTAL"
    echo ""
    
    # Verifica qual arquivo está sendo processado
    ARQUIVO_ATUAL=$(grep "📝 Processando arquivo" $LOG_FILE | tail -1)
    echo "🔄 $ARQUIVO_ATUAL"
    echo ""
    
    # Verifica se está transcrevendo
    if tail -50 $LOG_FILE | grep -q "Transcrevendo com parâmetros"; then
        echo "⚙️  Status: Transcrevendo áudio..."
        FRAMES=$(tail -10 $LOG_FILE | grep -o "[0-9]*%|" | tail -1 | tr -d '%|')
        if [ ! -z "$FRAMES" ]; then
            echo "   Progresso da transcrição: ${FRAMES}%"
        fi
    elif tail -50 $LOG_FILE | grep -q "Formatando com"; then
        echo "⚙️  Status: Formatando apostila..."
    elif tail -50 $LOG_FILE | grep -q "Consolidando transcrições"; then
        echo "📚 Status: Consolidando todas as transcrições..."
    elif tail -50 $LOG_FILE | grep -q "Formatando apostila final"; then
        echo "🎨 Status: Formatação final no modo FIDELIDADE..."
    elif tail -50 $LOG_FILE | grep -q "PROCESSAMENTO CONCLUÍDO"; then
        echo "✅ PROCESSAMENTO CONCLUÍDO!"
        echo ""
        echo "📄 Apostila disponível em:"
        grep "Apostila final:" $LOG_FILE | tail -1
        break
    fi
    
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Última atualização salva em: $MONITOR_FILE"
    
    # Salva status no arquivo
    echo "Status em $(date '+%H:%M:%S'): $PROCESSADOS/$TOTAL arquivos processados" >> $MONITOR_FILE
    
    sleep 30
done

echo ""
echo "Monitor encerrado: $(date)" >> $MONITOR_FILE
