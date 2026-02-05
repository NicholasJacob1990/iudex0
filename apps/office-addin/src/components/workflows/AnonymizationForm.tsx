import { useState, useCallback } from 'react';
import { useDocumentStore } from '@/stores/document-store';
import { anonymizeContent, type AnonymizeResponse } from '@/api/client';
import { replaceText } from '@/office/document-bridge';

const ENTITY_TYPES = [
  { id: 'CPF', label: 'CPF' },
  { id: 'nome', label: 'Nomes' },
  { id: 'endereco', label: 'Enderecos' },
  { id: 'telefone', label: 'Telefones' },
  { id: 'email', label: 'E-mails' },
  { id: 'RG', label: 'RG' },
  { id: 'OAB', label: 'OAB' },
];

type AnonState = 'idle' | 'processing' | 'preview';

export function AnonymizationForm() {
  const loadSelection = useDocumentStore((s) => s.loadSelection);
  const loadFullText = useDocumentStore((s) => s.loadFullText);
  const selectedText = useDocumentStore((s) => s.selectedText);

  const [entities, setEntities] = useState<string[]>(
    ENTITY_TYPES.map((e) => e.id)
  );
  const [useFullDoc, setUseFullDoc] = useState(false);
  const [state, setState] = useState<AnonState>('idle');
  const [result, setResult] = useState<AnonymizeResponse | null>(null);
  const [originalText, setOriginalText] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [applyFeedback, setApplyFeedback] = useState<string | null>(null);

  const toggleEntity = (id: string) => {
    setEntities((prev) =>
      prev.includes(id) ? prev.filter((e) => e !== id) : [...prev, id]
    );
  };

  const handleAnonymize = useCallback(async () => {
    if (entities.length === 0) {
      setError('Selecione ao menos um tipo de entidade.');
      return;
    }

    let content: string;

    if (useFullDoc) {
      await loadFullText();
      content = useDocumentStore.getState().fullText;
    } else {
      await loadSelection();
      content = useDocumentStore.getState().selectedText;
    }

    if (!content.trim()) {
      setError(
        useFullDoc
          ? 'Documento vazio.'
          : 'Selecione um trecho no documento Word primeiro.'
      );
      return;
    }

    setOriginalText(content);
    setState('processing');
    setError(null);
    setResult(null);

    try {
      const response = await anonymizeContent({
        content,
        entities_to_anonymize: entities,
      });
      setResult(response);
      setState('preview');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Erro na anonimizacao');
      setState('idle');
    }
  }, [entities, useFullDoc, loadSelection, loadFullText]);

  const handleApplyAll = useCallback(async () => {
    if (!result) return;

    let applied = 0;
    for (const entity of result.entities_found) {
      const count = await replaceText(entity.original, entity.replacement);
      applied += count;
    }

    setApplyFeedback(`${applied} substituicoes aplicadas no documento`);
    setTimeout(() => setApplyFeedback(null), 3000);
  }, [result]);

  const handleApplySingle = useCallback(
    async (original: string, replacement: string) => {
      const count = await replaceText(original, replacement);
      if (count > 0) {
        setApplyFeedback(`"${original.slice(0, 20)}..." substituido`);
        setTimeout(() => setApplyFeedback(null), 2000);
      }
    },
    []
  );

  const handleCopy = useCallback(async () => {
    if (result) {
      await navigator.clipboard.writeText(result.anonymized_content);
      setApplyFeedback('Texto anonimizado copiado');
      setTimeout(() => setApplyFeedback(null), 2000);
    }
  }, [result]);

  const handleReset = useCallback(() => {
    setState('idle');
    setResult(null);
    setOriginalText('');
  }, []);

  return (
    <div className="space-y-3">
      {/* Entity type selector */}
      <div>
        <p className="mb-1.5 text-office-xs font-medium text-text-secondary">
          Entidades a anonimizar:
        </p>
        <div className="flex flex-wrap gap-1.5">
          {ENTITY_TYPES.map((et) => (
            <button
              key={et.id}
              onClick={() => toggleEntity(et.id)}
              disabled={state === 'processing'}
              className={`rounded-full px-2.5 py-0.5 text-office-xs font-medium transition-colors ${
                entities.includes(et.id)
                  ? 'bg-brand text-white'
                  : 'bg-surface-tertiary text-text-secondary hover:bg-gray-200'
              } disabled:opacity-50`}
            >
              {et.label}
            </button>
          ))}
        </div>
      </div>

      {/* Scope selector */}
      <div className="flex items-center gap-3">
        <label className="flex items-center gap-1.5 text-office-xs">
          <input
            type="radio"
            checked={!useFullDoc}
            onChange={() => setUseFullDoc(false)}
            disabled={state === 'processing'}
            className="text-brand"
          />
          Selecao
        </label>
        <label className="flex items-center gap-1.5 text-office-xs">
          <input
            type="radio"
            checked={useFullDoc}
            onChange={() => setUseFullDoc(true)}
            disabled={state === 'processing'}
            className="text-brand"
          />
          Documento inteiro
        </label>
      </div>

      {/* Selection preview */}
      {!useFullDoc && selectedText && state === 'idle' && (
        <div className="rounded bg-surface-tertiary p-2">
          <p className="text-office-xs text-text-tertiary italic">
            &ldquo;{selectedText.slice(0, 200)}
            {selectedText.length > 200 ? '...' : ''}&rdquo;
          </p>
        </div>
      )}

      {error && (
        <p className="rounded bg-red-50 p-2 text-office-xs text-status-error">
          {error}
        </p>
      )}

      {applyFeedback && (
        <p className="text-office-xs font-medium text-status-success">
          {applyFeedback}
        </p>
      )}

      {/* Action button */}
      {state === 'idle' && (
        <button onClick={handleAnonymize} className="office-btn-primary w-full">
          Anonimizar
        </button>
      )}

      {state === 'processing' && (
        <div className="flex items-center justify-center gap-2 py-4">
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-brand border-t-transparent" />
          <span className="text-office-sm text-text-secondary">
            Identificando entidades...
          </span>
        </div>
      )}

      {/* Results */}
      {state === 'preview' && result && (
        <div className="space-y-3">
          {/* Summary */}
          <div className="rounded bg-surface-tertiary p-2">
            <p className="text-office-xs font-medium">
              {result.entities_found.length} entidades encontradas
            </p>
          </div>

          {/* Entity list */}
          {result.entities_found.length > 0 && (
            <div className="max-h-48 overflow-y-auto">
              <table className="w-full text-office-xs">
                <thead>
                  <tr className="border-b text-left text-text-tertiary">
                    <th className="pb-1 pr-2">Tipo</th>
                    <th className="pb-1 pr-2">Original</th>
                    <th className="pb-1 pr-2">Substituicao</th>
                    <th className="pb-1"></th>
                  </tr>
                </thead>
                <tbody>
                  {result.entities_found.map((entity, i) => (
                    <tr key={i} className="border-b border-gray-100">
                      <td className="py-1 pr-2 font-medium">{entity.type}</td>
                      <td className="py-1 pr-2 text-status-error line-through">
                        {entity.original.slice(0, 30)}
                      </td>
                      <td className="py-1 pr-2 text-status-success">
                        {entity.replacement}
                      </td>
                      <td className="py-1">
                        <button
                          onClick={() =>
                            handleApplySingle(entity.original, entity.replacement)
                          }
                          className="text-brand hover:underline"
                        >
                          Aplicar
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Anonymized text preview */}
          <div>
            <p className="mb-1 text-office-xs font-medium text-text-secondary">
              Texto anonimizado:
            </p>
            <div className="max-h-32 overflow-y-auto rounded border border-gray-200 bg-white p-2 text-office-xs leading-relaxed">
              {result.anonymized_content.slice(0, 500)}
              {result.anonymized_content.length > 500 ? '...' : ''}
            </div>
          </div>

          {/* Actions */}
          <div className="flex flex-wrap gap-2">
            <button onClick={handleApplyAll} className="office-btn-primary flex-1">
              Aplicar tudo no documento
            </button>
            <button onClick={handleCopy} className="office-btn-secondary">
              Copiar
            </button>
            <button
              onClick={handleReset}
              className="rounded border border-gray-300 px-3 py-2 text-office-xs text-text-tertiary hover:bg-surface-tertiary"
            >
              Voltar
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
