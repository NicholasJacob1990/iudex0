'use client';

import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Placeholder from '@tiptap/extension-placeholder';
import Underline from '@tiptap/extension-underline';
import TextAlign from '@tiptap/extension-text-align';
import TextStyle from '@tiptap/extension-text-style';
import { Color } from '@tiptap/extension-color';
import { FontFamily } from '@tiptap/extension-font-family';
import Table from '@tiptap/extension-table';
import TableRow from '@tiptap/extension-table-row';
import TableCell from '@tiptap/extension-table-cell';
import TableHeader from '@tiptap/extension-table-header';
import { EditorToolbar } from './editor-toolbar';

interface DocumentEditorProps {
  content?: string;
  onChange?: (content: string) => void;
  editable?: boolean;
  placeholder?: string;
}

export function DocumentEditor({
  content = '',
  onChange,
  editable = true,
  placeholder = 'Digite ou cole seu documento aqui...',
}: DocumentEditorProps) {
  const editor = useEditor({
    extensions: [
      StarterKit,
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
      Table.configure({
        resizable: true,
      }),
      TableRow,
      TableCell,
      TableHeader,
    ],
    content,
    editable,
    onUpdate: ({ editor }) => {
      onChange?.(editor.getHTML());
    },
  });

  return (
    <div className="flex flex-col items-center space-y-4">
      {editable && (
        <div className="sticky top-0 z-10 w-full max-w-[850px] rounded-xl border border-border/50 bg-background/80 p-2 shadow-sm backdrop-blur-xl">
          <EditorToolbar editor={editor} />
        </div>
      )}
      <div className="min-h-[1100px] w-full max-w-[850px] bg-white shadow-lg ring-1 ring-black/5 transition-all duration-300 ease-in-out print:shadow-none">
        <EditorContent
          editor={editor}
          className="prose prose-slate max-w-none p-[96px] font-serif text-lg leading-relaxed focus:outline-none print:p-0"
        />
      </div>
    </div>
  );
}

