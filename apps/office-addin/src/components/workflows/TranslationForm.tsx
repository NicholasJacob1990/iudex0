import { useState, useCallback, useRef } from 'react';
import { useDocumentStore } from '@/stores/document-store';
import { streamTranslateContent } from '@/api/sse-client';
import { replaceText, insertTextAtCursor } from '@/office/document-bridge';

const LANGUAGES = [
  { code: 'pt', label: 'Portugues' },
  { code: 'en', label: 'Ingles' },
  { code: 'es', label: 'Espanhol' },
  { code: 'fr', label: 'Frances' },
  { code: 'de', label: 'Alemao' },
  { code: 'it', label: 'Italiano' },
];

type TranslateState = 'idle' | 'translating' | 'preview';

export function TranslationForm() {
  const loadSelection = useDocumentStore((s) => s.loadSelection);
  const selectedText = useDocumentStore((s) => s.selectedText);

  const [sourceLang, setSourceLang] = useState('pt');
  const [targetLang, setTargetLang] = useState('en');
  const [state, setState] = useState<TranslateState>('idle');
  const [translatedText, setTranslatedText] = useState('');
  const [streamingText, setStreamingText] = useState('');
  const [originalText, setOriginalText] = useState('');
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const handleTranslate = useCallback(async () => {
    await loadSelection();
    const sel = useDocumentStore.getState().selectedText;

    if (!sel.trim()) {
      setError('Selecione um trecho no documento Word primeiro.');
      return;
    }

    setOriginalText(sel);
    setTranslatedText('');
    setStreamingText('');
    setState('translating');
    setError(null);

    abortRef.current = new AbortController();
    let accumulated = '';

    await streamTranslateContent({
      content: sel,
      source_lang: sourceLang,
      target_lang: targetLang,
      onContent: (text) => {
        accumulated += text;
        setStreamingText(accumulated);
      },
      onDone: (result) => {
        setTranslatedText(result || accumulated);
        setStreamingText('');
        setState('preview');
      },
      onError: (err) => {
        setError(err);
        setState('idle');
      },
      signal: abortRef.current.signal,
    });
  }, [sourceLang, targetLang, loadSelection]);

  const handleAbort = useCallback(() => {
    abortRef.current?.abort();
    setState('idle');
    setStreamingText('');
  }, []);

  const handleReplace = useCallback(async () => {
    if (originalText && translatedText) {
      await replaceText(originalText.slice(0, 200), translatedText);
      setState('idle');
      setTranslatedText('');
      setOriginalText('');
    }
  }, [originalText, translatedText]);

  const handleInsertAfter = useCallback(async () => {
    if (translatedText) {
      await insertTextAtCursor('\n\n' + translatedText);
      setState('idle');
      setTranslatedText('');
      setOriginalText('');
    }
  }, [translatedText]);

  const handleCopy = useCallback(async () => {
    if (translatedText) {
      await navigator.clipboard.writeText(translatedText);
    }
  }, [translatedText]);

  const handleDiscard = useCallback(() => {
    setState('idle');
    setTranslatedText('');
    setOriginalText('');
    setStreamingText('');
  }, []);

  const displayText = state === 'translating' ? streamingText : translatedText;

  return (
    <div className="space-y-3">
      {/* Language selector */}
      <div className="flex items-center gap-2">
        <select
          value={sourceLang}
          onChange={(e) => setSourceLang(e.target.value)}
          className="flex-1 rounded border border-gray-300 px-2 py-1.5 text-office-xs"
          disabled={state === 'translating'}
        >
          {LANGUAGES.map((l) => (
            <option key={l.code} value={l.code}>
              {l.label}
            </option>
          ))}
        </select>

        <button
          onClick={() => {
            const temp = sourceLang;
            setSourceLang(targetLang);
            setTargetLang(temp);
          }}
          className="shrink-0 rounded border border-gray-300 px-2 py-1.5 text-office-xs hover:bg-surface-tertiary"
          title="Inverter idiomas"
        >
          ⇄
        </button>

        <select
          value={targetLang}
          onChange={(e) => setTargetLang(e.target.value)}
          className="flex-1 rounded border border-gray-300 px-2 py-1.5 text-office-xs"
          disabled={state === 'translating'}
        >
          {LANGUAGES.map((l) => (
            <option key={l.code} value={l.code}>
              {l.label}
            </option>
          ))}
        </select>
      </div>

      {/* Selection preview */}
      {selectedText && state === 'idle' && (
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

      {/* Action button */}
      {state === 'idle' && (
        <div className="flex gap-2">
          <button onClick={handleTranslate} className="office-btn-primary flex-1">
            Traduzir selecao
          </button>
          <button onClick={loadSelection} className="office-btn-secondary" title="Atualizar">
            Sel.
          </button>
        </div>
      )}

      {state === 'translating' && (
        <button onClick={handleAbort} className="office-btn-secondary w-full">
          Cancelar
        </button>
      )}

      {/* Result */}
      {displayText && (
        <div>
          <p className="mb-1 text-office-xs font-medium text-text-secondary">
            {state === 'translating' ? 'Traduzindo...' : 'Traducao:'}
          </p>
          <div className="rounded border border-gray-200 bg-white p-3 text-office-sm leading-relaxed">
            {displayText}
            {state === 'translating' && (
              <span className="ml-0.5 inline-block h-3 w-1 animate-pulse bg-brand" />
            )}
          </div>
        </div>
      )}

      {/* Preview actions */}
      {state === 'preview' && (
        <div className="flex flex-wrap gap-2">
          <button onClick={handleReplace} className="office-btn-primary flex-1">
            Substituir original
          </button>
          <button onClick={handleInsertAfter} className="office-btn-secondary flex-1">
            Inserir apos
          </button>
          <button
            onClick={handleCopy}
            className="rounded border border-gray-300 px-3 py-2 text-office-xs hover:bg-surface-tertiary"
          >
            Copiar
          </button>
          <button
            onClick={handleDiscard}
            className="rounded border border-gray-300 px-3 py-2 text-office-xs text-text-tertiary hover:bg-surface-tertiary"
          >
            Descartar
          </button>
        </div>
      )}
    </div>
  );
}
