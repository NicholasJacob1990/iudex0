/**
 * Exemplo de uso do AskSourcesPanel
 *
 * Este componente exibe citações com sinais Shepard's e itens de contexto selecionados pelo usuário.
 */

import { AskSourcesPanel } from './ask-sources-panel';

export function AskSourcesPanelExample() {
  // Exemplo de citações com diferentes sinais Shepard's
  const citations = [
    {
      id: '1',
      title: 'STF - RE 123456',
      source: 'Supremo Tribunal Federal',
      snippet: 'O princípio da dignidade da pessoa humana é fundamento da República...',
      signal: 'positive' as const,
      url: 'https://portal.stf.jus.br/processos/exemplo',
    },
    {
      id: '2',
      title: 'Lei 8.666/93 - Art. 3º',
      source: 'Licitações e Contratos',
      snippet: 'A licitação destina-se a garantir a observância do princípio constitucional...',
      signal: 'neutral' as const,
    },
    {
      id: '3',
      title: 'STJ - REsp 987654',
      source: 'Superior Tribunal de Justiça',
      snippet: 'Precedente superado pela nova jurisprudência...',
      signal: 'negative' as const,
      url: 'https://portal.stj.jus.br/processos/exemplo',
    },
    {
      id: '4',
      title: 'Código Civil - Art. 186',
      source: 'Legislação Federal',
      snippet: 'Aquele que, por ação ou omissão voluntária, negligência ou imprudência...',
      signal: 'caution' as const,
    },
  ];

  // Exemplo de itens de contexto
  const contextItems = [
    { id: 'file-1', type: 'file' as const, name: 'Contrato_Prestacao_Servicos.pdf' },
    { id: 'file-2', type: 'file' as const, name: 'Procuracao.docx' },
    { id: 'folder-1', type: 'folder' as const, name: 'Processo 123/2024' },
    { id: 'model-1', type: 'model' as const, name: 'Modelo - Petição Inicial' },
    { id: 'leg-1', type: 'legislation' as const, name: 'Lei 8.666/93' },
    { id: 'jur-1', type: 'jurisprudence' as const, name: 'STF RE 123456' },
  ];

  const handleRemoveItem = (id: string) => {
    console.log('Removendo item:', id);
    // Implementar lógica de remoção
  };

  const handleClose = () => {
    console.log('Fechando painel');
    // Implementar lógica de fechamento
  };

  return (
    <div className="h-screen w-96">
      <AskSourcesPanel
        citations={citations}
        contextItems={contextItems}
        onRemoveItem={handleRemoveItem}
        onClose={handleClose}
      />
    </div>
  );
}
