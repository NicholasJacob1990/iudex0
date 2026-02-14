/**
 * Card de resumo de e-mail.
 *
 * Renderiza o resultado da sumarizacao com tipo juridico, confianca e resumo.
 * Suporta modo streaming com cursor pulsante.
 */

import { Badge, Text } from '@fluentui/react-components';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface SummaryCardProps {
  resumo: string;
  tipoJuridico?: string;
  confianca?: number;
  isStreaming?: boolean;
}

export function SummaryCard({
  resumo,
  tipoJuridico,
  confianca,
  isStreaming = false,
}: SummaryCardProps) {
  return (
    <div className="office-card">
      {/* Header com tipo e confianca */}
      {tipoJuridico && (
        <div className="mb-2 flex items-center gap-2">
          <Badge appearance="filled" color="brand" size="small">
            {tipoJuridico}
          </Badge>
          {confianca !== undefined && (
            <Text size={100} className="text-text-tertiary">
              {(confianca * 100).toFixed(0)}% confianca
            </Text>
          )}
        </div>
      )}

      {/* Conteudo do resumo em Markdown */}
      <div className="prose prose-sm max-w-none text-office-sm leading-relaxed text-text-primary">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>
          {resumo}
        </ReactMarkdown>
        {isStreaming && (
          <span className="ml-0.5 inline-block h-4 w-1 animate-pulse bg-brand" />
        )}
      </div>
    </div>
  );
}
