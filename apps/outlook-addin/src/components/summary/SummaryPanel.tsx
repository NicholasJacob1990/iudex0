/**
 * Painel principal de sumarizacao de e-mail.
 *
 * Conforme Design Doc Section 7.4:
 * - Carrega e-mail via getCurrentEmailData()
 * - Streams sumarizacao via SSE
 * - Renderiza: badge de classificacao, card de resumo, prazos, acoes
 * - Escuta evento ItemChanged para painel fixado (pinned pane)
 */

import { useCallback, useEffect, useRef } from 'react';
import {
  Button,
  Spinner,
  Badge,
  Text,
} from '@fluentui/react-components';
import {
  ArrowSyncRegular,
  DismissRegular,
} from '@fluentui/react-icons';
import { useEmailStore } from '@/stores/email-store';
import { useSummaryStore } from '@/stores/summary-store';
import { onItemChanged, offItemChanged } from '@/office/mail-bridge';
import { SummaryCard } from './SummaryCard';
import { DeadlineList } from './DeadlineList';
import { ActionBar } from './ActionBar';

export function SummaryPanel() {
  const {
    currentEmail,
    isLoading: isLoadingEmail,
    error: emailError,
    loadCurrentEmail,
  } = useEmailStore();

  const {
    summary,
    isStreaming,
    streamingContent,
    error: summaryError,
    summarize,
    cancel,
    clear,
  } = useSummaryStore();

  const hasAutoAnalyzed = useRef(false);

  // Escuta ItemChanged para quando o painel esta fixado e o usuario muda de e-mail
  useEffect(() => {
    const handleItemChanged = () => {
      clear();
      hasAutoAnalyzed.current = false;
      loadCurrentEmail();
    };

    onItemChanged(handleItemChanged);
    return () => {
      offItemChanged();
    };
  }, [loadCurrentEmail, clear]);

  // Auto-analisa quando o e-mail carrega (apenas uma vez por e-mail)
  useEffect(() => {
    if (currentEmail && !hasAutoAnalyzed.current && !isStreaming && !summary) {
      hasAutoAnalyzed.current = true;
      summarize(currentEmail);
    }
  }, [currentEmail, isStreaming, summary, summarize]);

  const handleReanalyze = useCallback(() => {
    if (currentEmail) {
      clear();
      summarize(currentEmail);
    }
  }, [currentEmail, clear, summarize]);

  const handleRefreshEmail = useCallback(() => {
    clear();
    hasAutoAnalyzed.current = false;
    loadCurrentEmail();
  }, [clear, loadCurrentEmail]);

  // Estado: carregando e-mail
  if (isLoadingEmail) {
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner size="medium" label="Carregando e-mail..." />
      </div>
    );
  }

  // Estado: erro ao carregar e-mail
  if (emailError) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 p-office-md text-center">
        <Text className="text-status-error">{emailError}</Text>
        <Button
          appearance="secondary"
          icon={<ArrowSyncRegular />}
          onClick={handleRefreshEmail}
        >
          Tentar novamente
        </Button>
      </div>
    );
  }

  // Estado: nenhum e-mail selecionado
  if (!currentEmail) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 p-office-md text-center">
        <Text size={300} className="text-text-secondary">
          Selecione um e-mail para analisar
        </Text>
        <Text size={200} className="text-text-tertiary">
          Abra um e-mail no Outlook e o painel sera atualizado automaticamente.
        </Text>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Cabecalho do e-mail */}
      <div className="border-b border-gray-200 p-office-md">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <Text size={300} weight="semibold" className="block truncate">
              {currentEmail.subject || '(Sem assunto)'}
            </Text>
            <Text size={200} className="mt-0.5 block text-text-secondary">
              De: {currentEmail.sender} ({currentEmail.senderEmail})
            </Text>
          </div>

          <div className="flex shrink-0 gap-1">
            <Button
              appearance="subtle"
              size="small"
              icon={<ArrowSyncRegular />}
              onClick={handleReanalyze}
              disabled={isStreaming}
              title="Reanalisar"
            />
            {isStreaming && (
              <Button
                appearance="subtle"
                size="small"
                icon={<DismissRegular />}
                onClick={cancel}
                title="Cancelar"
              />
            )}
          </div>
        </div>

        {/* Badge de classificacao */}
        {summary?.classificacao && (
          <div className="mt-2 flex items-center gap-2">
            <Badge
              appearance="filled"
              color="brand"
              size="small"
            >
              {summary.classificacao.tipo_juridico}
            </Badge>
            {summary.classificacao.subtipo && (
              <Badge appearance="outline" size="small">
                {summary.classificacao.subtipo}
              </Badge>
            )}
            <Text size={100} className="text-text-tertiary">
              Confianca: {(summary.classificacao.confianca * 100).toFixed(0)}%
            </Text>
          </div>
        )}
      </div>

      {/* Conteudo principal com scroll */}
      <div className="flex-1 overflow-y-auto p-office-md">
        {/* Erro de sumarizacao */}
        {summaryError && (
          <div className="mb-3 rounded bg-red-50 p-2">
            <Text size={200} className="text-status-error">
              {summaryError}
            </Text>
          </div>
        )}

        {/* Streaming em andamento */}
        {isStreaming && (
          <div className="mb-3">
            <div className="mb-2 flex items-center gap-2">
              <Spinner size="tiny" />
              <Text size={200} className="text-text-secondary">
                Analisando e-mail...
              </Text>
            </div>
            {streamingContent && (
              <SummaryCard
                resumo={streamingContent}
                isStreaming={true}
              />
            )}
          </div>
        )}

        {/* Resultado final */}
        {summary && !isStreaming && (
          <div className="space-y-3">
            {/* Resumo */}
            <SummaryCard
              resumo={summary.resumo}
              tipoJuridico={summary.classificacao?.tipo_juridico}
              confianca={summary.classificacao?.confianca}
            />

            {/* Prazos */}
            {summary.prazos.length > 0 && (
              <DeadlineList deadlines={summary.prazos} />
            )}

            {/* Acoes sugeridas e workflows */}
            <ActionBar
              acoes={summary.acoes_sugeridas}
              workflows={summary.workflows_recomendados}
            />
          </div>
        )}

        {/* Estado inicial: aguardando analise */}
        {!isStreaming && !summary && !summaryError && (
          <div className="py-4 text-center">
            <Text size={200} className="text-text-tertiary">
              A analise iniciara automaticamente...
            </Text>
          </div>
        )}
      </div>
    </div>
  );
}
