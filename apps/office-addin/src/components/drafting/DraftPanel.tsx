import { useCallback, useState } from 'react';
import { useDraftingStore, type EditMode, type HistoryEntry } from '@/stores/drafting-store';
import { useDocumentStore } from '@/stores/document-store';
import { replaceText, insertTextAtCursor } from '@/office/document-bridge';
import { DiffPreview, SideBySideDiff } from './DiffPreview';
import { PromptLibraryModal } from '@/components/prompts/PromptLibrary';
import type { PromptTemplate } from '@/data/prompt-library';

type DiffView = 'inline' | 'side-by-side';

const EDIT_MODES: Array<{ id: EditMode; label: string; description: string }> = [
  { id: 'custom', label: 'Instrucao livre', description: 'Descreva a edicao desejada' },
  { id: 'improve', label: 'Melhorar', description: 'Corrigir erros e melhorar redacao' },
  { id: 'simplify', label: 'Simplificar', description: 'Linguagem acessivel para leigos' },
  { id: 'formalize', label: 'Formalizar', description: 'Adequar para documentos oficiais' },
  { id: 'rewrite', label: 'Reescrever', description: 'Reescrever conforme instrucao' },
  { id: 'insert-after', label: 'Inserir apos', description: 'Gerar texto complementar' },
];

// Quick instructions removidas - agora usamos a PromptLibrary (Gap 10)

export function DraftPanel() {
  const {
    state,
    instruction,
    editMode,
    originalContent,
    editedContent,
    streamingContent,
    isStreaming,
    error,
    history,
    setInstruction,
    setEditMode,
    startEdit,
    abort,
    accept,
    reject,
    clearError,
    replayHistoryEntry,
  } = useDraftingStore();

  const selectedText = useDocumentStore((s) => s.selectedText);
  const loadSelection = useDocumentStore((s) => s.loadSelection);

  const [diffView, setDiffView] = useState<DiffView>('inline');
  const [showHistory, setShowHistory] = useState(false);
  const [showPromptLibrary, setShowPromptLibrary] = useState(false);

  // Gap 10: Handler para selecao de prompt da biblioteca
  const handlePromptSelect = useCallback(
    (prompt: PromptTemplate) => {
      setInstruction(prompt.prompt);
      setEditMode('custom');
      setShowPromptLibrary(false);
    },
    [setInstruction, setEditMode]
  );

  const handleAccept = useCallback(async () => {
    if (!originalContent || !editedContent) return;

    if (editMode === 'insert-after') {
      // Insert after the selection instead of replacing
      await insertTextAtCursor('\n' + editedContent);
    } else {
      await replaceText(originalContent.slice(0, 200), editedContent);
    }

    accept();
    await useDocumentStore.getState().loadFullText();
  }, [originalContent, editedContent, editMode, accept]);

  const displayContent = isStreaming ? streamingContent : editedContent;

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="border-b border-gray-200 p-office-md">
        <div className="flex items-center justify-between">
          <h2 className="text-office-lg font-semibold">Editar com IA</h2>
          {history.length > 0 && (
            <button
              onClick={() => setShowHistory(!showHistory)}
              className="text-office-xs text-brand hover:underline"
            >
              {showHistory ? 'Voltar' : `Historico (${history.length})`}
            </button>
          )}
        </div>
        <p className="mt-1 text-office-xs text-text-secondary">
          Selecione um trecho no Word e escolha o tipo de edicao.
        </p>
      </div>

      <div className="flex-1 overflow-y-auto p-office-md">
        {/* Error */}
        {error && (
          <div className="mb-3 flex items-start justify-between rounded bg-red-50 p-2">
            <p className="text-office-sm text-status-error">{error}</p>
            <button
              onClick={clearError}
              className="ml-2 shrink-0 text-office-xs text-status-error hover:underline"
            >
              Fechar
            </button>
          </div>
        )}

        {/* History view */}
        {showHistory && (
          <HistoryView
            history={history}
            onReplay={(entry) => {
              replayHistoryEntry(entry);
              setShowHistory(false);
            }}
          />
        )}

        {/* Main editing flow */}
        {!showHistory && (
          <>
            {/* Edit mode selector */}
            {(state === 'idle' || state === 'editing') && (
              <div className="space-y-3">
                {/* Mode chips */}
                <div className="flex flex-wrap gap-1.5">
                  {EDIT_MODES.map((mode) => (
                    <button
                      key={mode.id}
                      onClick={() => setEditMode(mode.id)}
                      disabled={isStreaming}
                      className={`rounded-full px-2.5 py-1 text-office-xs font-medium transition-colors ${
                        editMode === mode.id
                          ? 'bg-brand text-white'
                          : 'bg-surface-tertiary text-text-secondary hover:bg-gray-200'
                      } disabled:opacity-50`}
                      title={mode.description}
                    >
                      {mode.label}
                    </button>
                  ))}
                </div>

                {/* Instruction input (shown for custom/rewrite/insert-after) */}
                {(editMode === 'custom' ||
                  editMode === 'rewrite' ||
                  editMode === 'insert-after') && (
                  <textarea
                    value={instruction}
                    onChange={(e) => setInstruction(e.target.value)}
                    placeholder="Ex: Reescreva esta clausula para proteger o locatario..."
                    className="office-input min-h-[80px] resize-none"
                    disabled={isStreaming}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                        e.preventDefault();
                        startEdit();
                      }
                    }}
                  />
                )}

                {/* Gap 10: Botao para abrir biblioteca de prompts */}
                {(editMode === 'custom' || editMode === 'rewrite') && (
                  <button
                    onClick={() => setShowPromptLibrary(true)}
                    className="flex w-full items-center justify-center gap-2 rounded border border-dashed border-gray-300 px-3 py-2 text-office-xs text-text-secondary hover:border-brand hover:bg-blue-50"
                  >
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      width="16"
                      height="16"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
                      <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
                    </svg>
                    Explorar biblioteca de prompts
                  </button>
                )}

                {/* Selection preview */}
                {selectedText && (
                  <div className="rounded bg-surface-tertiary p-2">
                    <p className="mb-1 text-office-xs font-medium text-text-secondary">
                      Selecao atual:
                    </p>
                    <p className="text-office-xs text-text-tertiary italic">
                      &ldquo;{selectedText.slice(0, 300)}
                      {selectedText.length > 300 ? '...' : ''}&rdquo;
                    </p>
                  </div>
                )}

                {/* Action buttons */}
                <div className="flex gap-2">
                  {isStreaming ? (
                    <button onClick={abort} className="office-btn-secondary flex-1">
                      Cancelar
                    </button>
                  ) : (
                    <>
                      <button
                        onClick={startEdit}
                        disabled={
                          (editMode === 'custom' && !instruction.trim()) ||
                          ((editMode === 'rewrite' || editMode === 'insert-after') &&
                            !instruction.trim())
                        }
                        className="office-btn-primary flex-1"
                      >
                        Editar selecao
                      </button>
                      <button
                        onClick={loadSelection}
                        className="office-btn-secondary"
                        title="Atualizar texto selecionado"
                      >
                        Atualizar
                      </button>
                    </>
                  )}
                </div>
              </div>
            )}

            {/* Streaming preview */}
            {state === 'editing' && displayContent && (
              <div className="mt-4">
                <p className="mb-1 text-office-xs font-medium text-text-secondary">
                  Gerando...
                </p>
                <div className="rounded border border-gray-200 bg-white p-3 text-office-sm leading-relaxed">
                  {displayContent}
                  <span className="ml-0.5 inline-block h-3 w-1 animate-pulse bg-brand" />
                </div>
              </div>
            )}

            {/* Preview with diff */}
            {state === 'preview' && editedContent && (
              <div className="space-y-3">
                {/* Diff view toggle */}
                <div className="flex items-center justify-between">
                  <p className="text-office-xs font-medium text-text-secondary">
                    Resultado da edicao:
                  </p>
                  <div className="flex gap-1">
                    <button
                      onClick={() => setDiffView('inline')}
                      className={`rounded px-2 py-0.5 text-office-xs ${
                        diffView === 'inline'
                          ? 'bg-brand text-white'
                          : 'bg-surface-tertiary text-text-secondary'
                      }`}
                    >
                      Inline
                    </button>
                    <button
                      onClick={() => setDiffView('side-by-side')}
                      className={`rounded px-2 py-0.5 text-office-xs ${
                        diffView === 'side-by-side'
                          ? 'bg-brand text-white'
                          : 'bg-surface-tertiary text-text-secondary'
                      }`}
                    >
                      Lado a lado
                    </button>
                  </div>
                </div>

                {/* Diff content */}
                {diffView === 'inline' ? (
                  <DiffPreview original={originalContent} edited={editedContent} />
                ) : (
                  <SideBySideDiff original={originalContent} edited={editedContent} />
                )}

                {/* Accept/Reject */}
                <div className="flex gap-2">
                  <button onClick={handleAccept} className="office-btn-primary flex-1">
                    {editMode === 'insert-after'
                      ? 'Inserir no documento'
                      : 'Aplicar no documento'}
                  </button>
                  <button onClick={reject} className="office-btn-secondary flex-1">
                    Descartar
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {/* Gap 10: Modal da biblioteca de prompts */}
      <PromptLibraryModal
        isOpen={showPromptLibrary}
        onClose={() => setShowPromptLibrary(false)}
        onSelect={handlePromptSelect}
      />
    </div>
  );
}

// ── History sub-component ──────────────────────────────────────

function HistoryView({
  history,
  onReplay,
}: {
  history: HistoryEntry[];
  onReplay: (entry: HistoryEntry) => void;
}) {
  return (
    <div className="space-y-2">
      <p className="text-office-xs font-medium text-text-secondary">
        Edicoes recentes:
      </p>
      {history.map((entry) => (
        <div key={entry.id} className="office-card">
          <div className="flex items-start justify-between gap-2">
            <p className="text-office-xs font-medium">{entry.instruction}</p>
            {entry.applied && (
              <span className="shrink-0 rounded-full bg-green-100 px-2 py-0.5 text-office-xs text-status-success">
                Aplicado
              </span>
            )}
          </div>
          <p className="mt-1 text-office-xs text-text-tertiary">
            {new Date(entry.timestamp).toLocaleTimeString('pt-BR', {
              hour: '2-digit',
              minute: '2-digit',
            })}
            {' - '}
            {entry.mode}
          </p>
          <button
            onClick={() => onReplay(entry)}
            className="mt-1 text-office-xs text-brand hover:underline"
          >
            Ver resultado
          </button>
        </div>
      ))}
    </div>
  );
}
