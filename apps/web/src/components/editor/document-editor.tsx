'use client';

import { useEditor, EditorContent, BubbleMenu } from '@tiptap/react';
import { useEffect, useRef } from 'react';
import StarterKit from '@tiptap/starter-kit';
import Placeholder from '@tiptap/extension-placeholder';
import Underline from '@tiptap/extension-underline';
import TextAlign from '@tiptap/extension-text-align';
import TextStyle from '@tiptap/extension-text-style';
import { Color } from '@tiptap/extension-color';
import { FontFamily } from '@tiptap/extension-font-family';
import Image from '@tiptap/extension-image';
import Table from '@tiptap/extension-table';
import TableRow from '@tiptap/extension-table-row';
import TableCell from '@tiptap/extension-table-cell';
import TableHeader from '@tiptap/extension-table-header';
import { EditorToolbar } from './editor-toolbar';
import { CitationMark } from './extensions/citation-mark';
import { SuggestionHighlight } from './extensions/suggestion-highlight';
import { MermaidCodeBlock } from './extensions/mermaid-code-block';
import { Sparkles, Scissors, MessageSquare, Wand2, Scale } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import { useCanvasStore } from '@/stores/canvas-store';

interface DocumentEditorProps {
  content?: string;
  onChange?: (content: string) => void;
  editable?: boolean;
  placeholder?: string;
  onRequestImprove?: (selectedText: string) => void;
  onRequestShorten?: (selectedText: string) => void;
  onRequestVerify?: (selectedText: string) => void;
  highlightedText?: string | null;
}

export function DocumentEditor({
  content = '',
  onChange,
  editable = true,
  placeholder = 'Digite ou cole seu documento aqui...',
  onRequestImprove,
  onRequestShorten,
  onRequestVerify,
  highlightedText,
}: DocumentEditorProps) {
  const ignoreNextUpdateRef = useRef(false);
  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        codeBlock: false,
      }),
      MermaidCodeBlock,
      Placeholder.configure({
        placeholder,
      }),
      Underline,
      TextAlign.configure({
        types: ['heading', 'paragraph'],
      }),
      TextStyle,
      Color,
      FontFamily,
      Image.configure({
        inline: false,
        allowBase64: true,
      }),
      Table.configure({
        resizable: true,
      }),
      TableRow,
      TableCell,
      TableHeader,
      // Canvas UX extensions
      CitationMark,
      SuggestionHighlight,
    ],
    content,
    editable,
    onUpdate: ({ editor }) => {
      if (ignoreNextUpdateRef.current) {
        ignoreNextUpdateRef.current = false;
        return;
      }
      onChange?.(editor.getHTML());
    },
    onSelectionUpdate: ({ editor }) => {
      const { from, to } = editor.state.selection;
      const text = editor.state.doc.textBetween(from, to, ' ').trim();
      if (!text) {
        useCanvasStore.getState().setSelectedText('', null, null, null);
        return;
      }

      const docSize = editor.state.doc.content.size;
      const beforeStart = Math.max(0, from - 200);
      const afterEnd = Math.min(docSize, to + 200);
      const before = editor.state.doc.textBetween(beforeStart, from, ' ').trim();
      const after = editor.state.doc.textBetween(to, afterEnd, ' ').trim();
      useCanvasStore.getState().setSelectedText(text, null, { from, to }, { before, after });
    },
  });

  // Track last content to avoid syncing on internal edits
  const lastExternalContent = useRef(content);

  // Sync editor content when prop changes externally (e.g., AI regeneration)
  useEffect(() => {
    if (!editor) return;
    // Only update if content changed externally (not from internal edits)
    if (content !== lastExternalContent.current) {
      lastExternalContent.current = content;
      // Preserve cursor position if possible
      const { from, to } = editor.state.selection;
      editor.commands.setContent(content, false);
      // Try to restore cursor (may fail if content structure changed drastically)
      try {
        const docLength = editor.state.doc.content.size;
        const safeFrom = Math.min(from, docLength);
        const safeTo = Math.min(to, docLength);
        editor.commands.setTextSelection({ from: safeFrom, to: safeTo });
      } catch {
        // Ignore cursor restoration errors
      }
    }
  }, [content, editor]);
  // Handle pending edits from store
  const pendingEdit = useCanvasStore(state => state.pendingEdit);
  const clearPendingEdit = useCanvasStore(state => state.clearPendingEdit);
  const pushHistory = useCanvasStore(state => state.pushHistory);

  useEffect(() => {
    if (!editor || !pendingEdit) return;
    if (!pendingEdit.range || pendingEdit.range.from === pendingEdit.range.to) {
      clearPendingEdit();
      return;
    }

    try {
      const rangeText = editor.state.doc
        .textBetween(pendingEdit.range.from, pendingEdit.range.to, ' ')
        .replace(/\s+/g, ' ')
        .trim();
      const expectedText = (pendingEdit.original || '').replace(/\s+/g, ' ').trim();

      if (expectedText && rangeText && rangeText !== expectedText) {
        const fallback = useCanvasStore.getState().applyTextReplacement(
          pendingEdit.original,
          pendingEdit.replacement,
          pendingEdit.label || 'Sugestão aplicada',
          null
        );
        if (!fallback.success) {
          toast.error("Falha ao aplicar edição no editor.");
        } else {
          toast.success("Edição aplicada!");
        }
        return;
      }

      editor.chain().focus().setTextSelection(pendingEdit.range).insertContent(pendingEdit.replacement).run();
      const nextHtml = editor.getHTML();
      pushHistory(nextHtml, pendingEdit.label || 'Sugestão aplicada');
      toast.success("Edição aplicada!");
    } catch (e) {
      console.error("Failed to apply edit", e);
      toast.error("Falha ao aplicar edição no editor.");
    } finally {
      clearPendingEdit();
    }
  }, [editor, pendingEdit, clearPendingEdit, pushHistory]);

  // Sync editor content when prop changes externally (e.g., AI regeneration)

  // Get canvas store for context-aware chat
  const setSelectedText = useCanvasStore(state => state.setSelectedText);

  const handleImprove = () => {
    if (!editor) return;
    const { from, to } = editor.state.selection;
    const selectedText = editor.state.doc.textBetween(from, to, ' ');
    if (selectedText.trim()) {
      const docSize = editor.state.doc.content.size;
      const beforeStart = Math.max(0, from - 200);
      const afterEnd = Math.min(docSize, to + 200);
      const before = editor.state.doc.textBetween(beforeStart, from, ' ').trim();
      const after = editor.state.doc.textBetween(to, afterEnd, ' ').trim();
      if (onRequestImprove) {
        onRequestImprove(selectedText);
      } else {
        // Context-aware: set in store for ChatInput to pick up
        setSelectedText(selectedText, 'improve', { from, to }, { before, after });
        toast.success('Texto selecionado! Digite no chat para refinar.', {
          description: `"${selectedText.slice(0, 50)}${selectedText.length > 50 ? '...' : ''}"`,
        });
      }
    }
  };

  const handleShorten = () => {
    if (!editor) return;
    const { from, to } = editor.state.selection;
    const selectedText = editor.state.doc.textBetween(from, to, ' ');
    if (selectedText.trim()) {
      const docSize = editor.state.doc.content.size;
      const beforeStart = Math.max(0, from - 200);
      const afterEnd = Math.min(docSize, to + 200);
      const before = editor.state.doc.textBetween(beforeStart, from, ' ').trim();
      const after = editor.state.doc.textBetween(to, afterEnd, ' ').trim();
      if (onRequestShorten) {
        onRequestShorten(selectedText);
      } else {
        // Context-aware: set in store for ChatInput to pick up
        setSelectedText(selectedText, 'shorten', { from, to }, { before, after });
        toast.success('Texto selecionado! Digite no chat para resumir.', {
          description: `"${selectedText.slice(0, 50)}${selectedText.length > 50 ? '...' : ''}"`,
        });
      }
    }
  };

  const handleVerify = async () => {
    if (!editor) return;
    const { from, to } = editor.state.selection;
    const selectedText = editor.state.doc.textBetween(from, to, ' ');
    if (!selectedText.trim()) return;

    if (onRequestVerify) {
      onRequestVerify(selectedText);
      return;
    }

    // Call backend API for inline verification
    const toastId = toast.loading('Verificando citações...');
    try {
      const API_URL = process.env.NEXT_PUBLIC_API_URL || '/api';
      const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;

      const response = await fetch(`${API_URL}/audit/verify-snippet`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ text: selectedText }),
      });

      if (!response.ok) {
        throw new Error('Falha na verificação');
      }

      const data = await response.json();

      // Show result based on status
      if (data.status === 'valid' || data.status === 'found') {
        toast.success(data.message || 'Citações parecem válidas!', { id: toastId });
      } else if (data.status === 'suspicious') {
        toast.warning(data.message || 'Citações suspeitas detectadas!', { id: toastId });
      } else if (data.status === 'not_found') {
        toast.info('Nenhuma citação jurídica identificada.', { id: toastId });
      } else {
        toast.info(data.message || 'Verificação concluída.', { id: toastId });
      }

      // If citations found, show them
      if (data.citations && data.citations.length > 0) {
        setTimeout(() => {
          toast.info(`Citações encontradas: ${data.citations.slice(0, 3).join(', ')}${data.citations.length > 3 ? '...' : ''}`);
        }, 500);
      }

    } catch (error) {
      toast.error('Erro ao verificar citações. Copie o prompt para o chat.', { id: toastId });
      navigator.clipboard.writeText(`Verifique as citações jurídicas neste trecho: "${selectedText}"`);
    }
  };

  useEffect(() => {
    if (!editor) return;
    const normalizeWhitespace = (value: string) => value.replace(/\s+/g, ' ').trim();
    const text = normalizeWhitespace(highlightedText || '');
    const { from, to } = editor.state.selection;
    const docSize = editor.state.doc.content.size;

    ignoreNextUpdateRef.current = true;
    editor.commands.setTextSelection({ from: 0, to: docSize });
    editor.commands.unsetMark('suggestionHighlight');
    editor.commands.setTextSelection({ from, to });

    if (!text) return;

    const map: number[] = [];
    let normalizedDoc = '';
    let lastSpace = false;
    let lastBlock: any = null;

    editor.state.doc.descendants((node, pos, parent) => {
      if (!node.isText || !node.text) return;
      const block = parent && parent.isBlock ? parent : null;
      if (block && lastBlock && block !== lastBlock && !lastSpace) {
        normalizedDoc += ' ';
        map.push(pos);
        lastSpace = true;
      }
      if (block) lastBlock = block;

      for (let i = 0; i < node.text.length; i += 1) {
        const ch = node.text[i];
        if (/\s/.test(ch)) {
          if (lastSpace) continue;
          normalizedDoc += ' ';
          map.push(pos + i);
          lastSpace = true;
          continue;
        }
        normalizedDoc += ch;
        map.push(pos + i);
        lastSpace = false;
      }
    });

    let idx = normalizedDoc.indexOf(text);
    if (idx === -1) {
      idx = normalizedDoc.toLowerCase().indexOf(text.toLowerCase());
    }

    let foundRange: { from: number; to: number } | null = null;
    if (idx !== -1) {
      const endIndex = idx + text.length - 1;
      if (idx >= 0 && endIndex < map.length) {
        foundRange = { from: map[idx], to: map[endIndex] + 1 };
      }
    }

    if (!foundRange) {
      const tokens = text.split(' ').filter(Boolean);
      const anchorSizes = [8, 6, 4];

      for (const size of anchorSizes) {
        if (tokens.length < size) continue;
        const startAnchor = tokens.slice(0, size).join(' ');
        const endAnchor = tokens.slice(-size).join(' ');

        let startIdx = normalizedDoc.indexOf(startAnchor);
        if (startIdx === -1) {
          startIdx = normalizedDoc.toLowerCase().indexOf(startAnchor.toLowerCase());
        }
        if (startIdx === -1) continue;

        let endIdx = normalizedDoc.indexOf(endAnchor, startIdx + startAnchor.length);
        if (endIdx === -1) {
          endIdx = normalizedDoc.toLowerCase().indexOf(endAnchor.toLowerCase(), startIdx + startAnchor.length);
        }
        if (endIdx === -1) continue;

        const endIndex = endIdx + endAnchor.length - 1;
        if (startIdx >= 0 && endIndex < map.length) {
          foundRange = { from: map[startIdx], to: map[endIndex] + 1 };
          break;
        }
      }
    }

    if (!foundRange) return;

    ignoreNextUpdateRef.current = true;
    editor.commands.setTextSelection(foundRange);
    editor.commands.setMark('suggestionHighlight', { type: 'pending' });
    editor.commands.setTextSelection({ from, to });
  }, [editor, highlightedText]);

  return (
    <div className="flex flex-col items-center space-y-4">
      {editable && (
        <div className="sticky top-0 z-10 w-full max-w-[850px] rounded-xl border border-border/50 bg-background/80 p-2 shadow-sm backdrop-blur-xl">
          <EditorToolbar editor={editor} />
        </div>
      )}

      {/* Floating Bubble Menu - Canvas Pattern */}
      {editor && editable && (
        <BubbleMenu
          editor={editor}
          tippyOptions={{
            duration: 150,
            placement: 'top',
          }}
          className="flex items-center gap-1 rounded-lg border border-border/50 bg-background/95 p-1 shadow-lg backdrop-blur-xl"
        >
          <Button
            variant="ghost"
            size="sm"
            onClick={handleImprove}
            className="h-8 gap-1.5 text-xs font-medium hover:bg-primary/10 hover:text-primary"
          >
            <Sparkles className="h-3.5 w-3.5" />
            Melhorar
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleShorten}
            className="h-8 gap-1.5 text-xs font-medium hover:bg-orange-500/10 hover:text-orange-600"
          >
            <Scissors className="h-3.5 w-3.5" />
            Resumir
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleVerify}
            className="h-8 gap-1.5 text-xs font-medium hover:bg-blue-500/10 hover:text-blue-600"
          >
            <Scale className="h-3.5 w-3.5" />
            Verificar
          </Button>
        </BubbleMenu>
      )}

      <div className="min-h-[1100px] w-full max-w-[850px] bg-white shadow-lg ring-1 ring-black/5 transition-all duration-300 ease-in-out print:shadow-none">
        <EditorContent
          editor={editor}
          className="prose prose-slate max-w-none p-[96px] font-google-sans-text text-lg leading-relaxed focus:outline-none print:p-0"
        />
      </div>
    </div>
  );
}
