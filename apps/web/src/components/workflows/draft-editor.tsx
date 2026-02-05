'use client';

import React, { useState, useCallback, useRef, useEffect } from 'react';
import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Underline from '@tiptap/extension-underline';
import Placeholder from '@tiptap/extension-placeholder';
import { Button } from '@/components/ui/button';
import {
  Bold,
  Italic,
  Underline as UnderlineIcon,
  Heading1,
  Heading2,
  Heading3,
  List,
  ListOrdered,
  Undo,
  Redo,
  Pencil,
  Eye,
  Save,
  RotateCcw,
  Pilcrow,
} from 'lucide-react';

interface DraftEditorProps {
  content: string;
  onSave: (content: string) => void;
  onDiscard: () => void;
  readOnly?: boolean;
}

export function DraftEditor({
  content,
  onSave,
  onDiscard,
  readOnly = false,
}: DraftEditorProps) {
  const [isEditing, setIsEditing] = useState(!readOnly);
  const [hasChanges, setHasChanges] = useState(false);
  const originalContentRef = useRef(content);

  const editor = useEditor({
    immediatelyRender: false,
    extensions: [
      StarterKit,
      Underline,
      Placeholder.configure({
        placeholder: 'Conteúdo do workflow aparecerá aqui...',
      }),
    ],
    content,
    editable: isEditing,
    onUpdate: () => {
      setHasChanges(true);
    },
  });

  // Sync editable state when toggling mode
  useEffect(() => {
    if (editor) {
      editor.setEditable(isEditing);
    }
  }, [editor, isEditing]);

  // Sync content when prop changes externally
  useEffect(() => {
    if (!editor) return;
    if (content !== originalContentRef.current) {
      originalContentRef.current = content;
      editor.commands.setContent(content, false);
      setHasChanges(false);
    }
  }, [content, editor]);

  const handleSave = useCallback(() => {
    if (!editor) return;
    const html = editor.getHTML();
    originalContentRef.current = html;
    setHasChanges(false);
    onSave(html);
  }, [editor, onSave]);

  const handleDiscard = useCallback(() => {
    if (!editor) return;
    editor.commands.setContent(originalContentRef.current, false);
    setHasChanges(false);
    onDiscard();
  }, [editor, onDiscard]);

  const toggleMode = useCallback(() => {
    setIsEditing((prev) => !prev);
  }, []);

  return (
    <div className="flex flex-col rounded-lg border border-border bg-background">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-1 border-b border-border bg-muted/30 px-3 py-2">
        {/* Mode toggle */}
        <Button
          variant={isEditing ? 'secondary' : 'ghost'}
          size="sm"
          onClick={toggleMode}
          className="mr-1 gap-1.5 text-xs"
          title={isEditing ? 'Alternar para leitura' : 'Alternar para edição'}
        >
          {isEditing ? (
            <>
              <Pencil className="h-3.5 w-3.5" />
              Editando
            </>
          ) : (
            <>
              <Eye className="h-3.5 w-3.5" />
              Leitura
            </>
          )}
        </Button>

        <div className="mx-1 h-6 w-px bg-border" />

        {/* Editing controls - only visible in edit mode */}
        {isEditing && editor && (
          <>
            {/* Undo/Redo */}
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={() => editor.chain().focus().undo().run()}
              disabled={!editor.can().undo()}
              title="Desfazer"
            >
              <Undo className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={() => editor.chain().focus().redo().run()}
              disabled={!editor.can().redo()}
              title="Refazer"
            >
              <Redo className="h-4 w-4" />
            </Button>

            <div className="mx-1 h-6 w-px bg-border" />

            {/* Headings */}
            <Button
              variant={editor.isActive('heading', { level: 1 }) ? 'secondary' : 'ghost'}
              size="icon"
              className="h-8 w-8"
              onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()}
              title="Título 1"
            >
              <Heading1 className="h-4 w-4" />
            </Button>
            <Button
              variant={editor.isActive('heading', { level: 2 }) ? 'secondary' : 'ghost'}
              size="icon"
              className="h-8 w-8"
              onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
              title="Título 2"
            >
              <Heading2 className="h-4 w-4" />
            </Button>
            <Button
              variant={editor.isActive('heading', { level: 3 }) ? 'secondary' : 'ghost'}
              size="icon"
              className="h-8 w-8"
              onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()}
              title="Título 3"
            >
              <Heading3 className="h-4 w-4" />
            </Button>
            <Button
              variant={editor.isActive('paragraph') ? 'secondary' : 'ghost'}
              size="icon"
              className="h-8 w-8"
              onClick={() => editor.chain().focus().setParagraph().run()}
              title="Texto Normal"
            >
              <Pilcrow className="h-4 w-4" />
            </Button>

            <div className="mx-1 h-6 w-px bg-border" />

            {/* Text Formatting */}
            <Button
              variant={editor.isActive('bold') ? 'secondary' : 'ghost'}
              size="icon"
              className="h-8 w-8"
              onClick={() => editor.chain().focus().toggleBold().run()}
              title="Negrito"
            >
              <Bold className="h-4 w-4" />
            </Button>
            <Button
              variant={editor.isActive('italic') ? 'secondary' : 'ghost'}
              size="icon"
              className="h-8 w-8"
              onClick={() => editor.chain().focus().toggleItalic().run()}
              title="Itálico"
            >
              <Italic className="h-4 w-4" />
            </Button>
            <Button
              variant={editor.isActive('underline') ? 'secondary' : 'ghost'}
              size="icon"
              className="h-8 w-8"
              onClick={() => editor.chain().focus().toggleUnderline().run()}
              title="Sublinhado"
            >
              <UnderlineIcon className="h-4 w-4" />
            </Button>

            <div className="mx-1 h-6 w-px bg-border" />

            {/* Lists */}
            <Button
              variant={editor.isActive('bulletList') ? 'secondary' : 'ghost'}
              size="icon"
              className="h-8 w-8"
              onClick={() => editor.chain().focus().toggleBulletList().run()}
              title="Lista com marcadores"
            >
              <List className="h-4 w-4" />
            </Button>
            <Button
              variant={editor.isActive('orderedList') ? 'secondary' : 'ghost'}
              size="icon"
              className="h-8 w-8"
              onClick={() => editor.chain().focus().toggleOrderedList().run()}
              title="Lista numerada"
            >
              <ListOrdered className="h-4 w-4" />
            </Button>
          </>
        )}

        {/* Spacer */}
        <div className="flex-1" />

        {/* Action buttons */}
        {isEditing && (
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              className="gap-1.5 text-xs text-muted-foreground hover:text-destructive"
              onClick={handleDiscard}
              disabled={!hasChanges}
              title="Descartar alterações"
            >
              <RotateCcw className="h-3.5 w-3.5" />
              Descartar
            </Button>
            <Button
              size="sm"
              className="gap-1.5 text-xs"
              onClick={handleSave}
              disabled={!hasChanges}
              title="Salvar edições"
            >
              <Save className="h-3.5 w-3.5" />
              Salvar Edições
            </Button>
          </div>
        )}
      </div>

      {/* Editor Content */}
      <div className={`min-h-[200px] ${isEditing ? 'bg-background' : 'bg-muted/10'}`}>
        <EditorContent
          editor={editor}
          className="prose prose-slate dark:prose-invert max-w-none p-6 text-sm leading-relaxed focus:outline-none"
        />
      </div>

      {/* Status bar */}
      {hasChanges && isEditing && (
        <div className="border-t border-border bg-amber-50 dark:bg-amber-950/20 px-4 py-1.5">
          <span className="text-xs text-amber-700 dark:text-amber-400">
            Alterações não salvas
          </span>
        </div>
      )}
    </div>
  );
}
