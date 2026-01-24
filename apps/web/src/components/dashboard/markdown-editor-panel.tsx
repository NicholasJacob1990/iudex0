'use client';

import { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useEditor, EditorContent, type Editor } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import TipTapTable from '@tiptap/extension-table';
import TableRow from '@tiptap/extension-table-row';
import TableCell from '@tiptap/extension-table-cell';
import TableHeader from '@tiptap/extension-table-header';
import { MarkdownSerializer } from 'prosemirror-markdown';
import type { Node as ProseMirrorNode } from 'prosemirror-model';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import {
    Bold,
    Heading1,
    Heading2,
    Heading3,
    Edit3,
    Eye,
    Italic,
    List,
    ListOrdered,
    Pilcrow,
    Quote,
    Redo,
    Save,
    Strikethrough,
    Table as TableIcon,
    Undo,
    X,
    Undo2,
    Download,
    Split,
    Maximize2,
    Minimize2
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { parseMarkdownToHtmlSync } from '@/lib/markdown-parser';

function backticksFor(node: ProseMirrorNode, side: number) {
    let ticks = /`+/g;
    let m: RegExpExecArray | null;
    let len = 0;
    if (node.isText) {
        while ((m = ticks.exec(node.text || ''))) {
            len = Math.max(len, m[0].length);
        }
    }
    let result = len > 0 && side > 0 ? " `" : "`";
    for (let i = 0; i < len; i++) result += "`";
    if (len > 0 && side < 0) result += " ";
    return result;
}

const tiptapMarkdownSerializer = new MarkdownSerializer(
    {
        blockquote(state, node) {
            state.wrapBlock("> ", null, node, () => state.renderContent(node));
        },
        heading(state, node) {
            state.write(state.repeat("#", node.attrs.level) + " ");
            state.renderInline(node, false);
            state.closeBlock(node);
        },
        horizontalRule(state, node) {
            state.write(node.attrs.markup || "---");
            state.closeBlock(node);
        },
        bulletList(state, node) {
            state.renderList(node, "  ", () => "- ");
        },
        orderedList(state, node) {
            const start = typeof node.attrs.start === 'number' ? node.attrs.start : 1;
            const maxW = String(start + node.childCount - 1).length;
            const space = state.repeat(" ", maxW + 2);
            state.renderList(node, space, (i) => {
                const nStr = String(start + i);
                return state.repeat(" ", maxW - nStr.length) + nStr + ". ";
            });
        },
        listItem(state, node) {
            state.renderContent(node);
        },
        paragraph(state, node) {
            state.renderInline(node);
            state.closeBlock(node);
        },
        table(state, node) {
            const rows: string[][] = [];
            node.forEach((row) => {
                const cells: string[] = [];
                row.forEach((cell) => {
                    const text = (cell.textContent || '').replace(/\s+/g, ' ').trim();
                    cells.push(text);
                });
                rows.push(cells);
            });

            if (rows.length === 0) {
                state.closeBlock(node);
                return;
            }

            const columnCount = rows.reduce((max, row) => Math.max(max, row.length), 0);
            if (columnCount === 0) {
                state.closeBlock(node);
                return;
            }

            const normalizeRow = (row: string[]) => {
                const normalized = row.slice(0, columnCount);
                while (normalized.length < columnCount) normalized.push('');
                return normalized;
            };

            const escapeCell = (value: string) => {
                return (value || '')
                    .replace(/\s+/g, ' ')
                    .trim()
                    .replace(/\|/g, '\\|');
            };

            const header = normalizeRow(rows[0]).map(escapeCell);
            const separator = header.map(() => '---');
            const body = rows.slice(1).map((row) => normalizeRow(row).map(escapeCell));

            state.ensureNewLine();
            state.write(`| ${header.join(' | ')} |\n`);
            state.write(`| ${separator.join(' | ')} |\n`);
            body.forEach((row) => {
                state.write(`| ${row.join(' | ')} |\n`);
            });
            state.closeBlock(node);
        },
        hardBreak(state, node, parent, index) {
            for (let i = index + 1; i < parent.childCount; i += 1) {
                if (parent.child(i).type !== node.type) {
                    state.write("\\\n");
                    return;
                }
            }
        },
        text(state, node) {
            state.text(node.text || '', true);
        },
    },
    {
        italic: { open: "*", close: "*", mixable: true, expelEnclosingWhitespace: true },
        bold: { open: "**", close: "**", mixable: true, expelEnclosingWhitespace: true },
        strike: { open: "~~", close: "~~", mixable: true, expelEnclosingWhitespace: true },
        code: {
            open(_state, _mark, parent, index) {
                return backticksFor(parent.child(index), -1);
            },
            close(_state, _mark, parent, index) {
                return backticksFor(parent.child(index - 1), 1);
            },
            escape: false,
        },
    },
    { hardBreakNodeName: 'hardBreak', strict: false }
);

function serializeTipTapDocToMarkdown(doc: ProseMirrorNode) {
    return tiptapMarkdownSerializer.serialize(doc, { tightLists: true }).trim();
}

function MarkdownRichToolbar({ editor, disabled }: { editor: Editor | null; disabled?: boolean }) {
    if (!editor) return null;

    return (
        <div className="flex flex-wrap items-center gap-1 rounded-lg border bg-card p-2">
            <Button
                variant="ghost"
                size="icon"
                onClick={() => editor.chain().focus().undo().run()}
                disabled={disabled || !editor.can().undo()}
                title="Desfazer"
            >
                <Undo className="h-4 w-4" />
            </Button>
            <Button
                variant="ghost"
                size="icon"
                onClick={() => editor.chain().focus().redo().run()}
                disabled={disabled || !editor.can().redo()}
                title="Refazer"
            >
                <Redo className="h-4 w-4" />
            </Button>

            <div className="mx-1 h-6 w-px bg-border" />

            <Button
                variant={editor.isActive('heading', { level: 1 }) ? 'secondary' : 'ghost'}
                size="icon"
                onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()}
                disabled={disabled}
                title="Título 1"
            >
                <Heading1 className="h-4 w-4" />
            </Button>
            <Button
                variant={editor.isActive('heading', { level: 2 }) ? 'secondary' : 'ghost'}
                size="icon"
                onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
                disabled={disabled}
                title="Título 2"
            >
                <Heading2 className="h-4 w-4" />
            </Button>
            <Button
                variant={editor.isActive('heading', { level: 3 }) ? 'secondary' : 'ghost'}
                size="icon"
                onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()}
                disabled={disabled}
                title="Título 3"
            >
                <Heading3 className="h-4 w-4" />
            </Button>
            <Button
                variant={editor.isActive('paragraph') ? 'secondary' : 'ghost'}
                size="icon"
                onClick={() => editor.chain().focus().setParagraph().run()}
                disabled={disabled}
                title="Texto"
            >
                <Pilcrow className="h-4 w-4" />
            </Button>

            <div className="mx-1 h-6 w-px bg-border" />

            <Button
                variant={editor.isActive('bold') ? 'secondary' : 'ghost'}
                size="icon"
                onClick={() => editor.chain().focus().toggleBold().run()}
                disabled={disabled}
                title="Negrito"
            >
                <Bold className="h-4 w-4" />
            </Button>
            <Button
                variant={editor.isActive('italic') ? 'secondary' : 'ghost'}
                size="icon"
                onClick={() => editor.chain().focus().toggleItalic().run()}
                disabled={disabled}
                title="Itálico"
            >
                <Italic className="h-4 w-4" />
            </Button>
            <Button
                variant={editor.isActive('strike') ? 'secondary' : 'ghost'}
                size="icon"
                onClick={() => editor.chain().focus().toggleStrike().run()}
                disabled={disabled}
                title="Riscado"
            >
                <Strikethrough className="h-4 w-4" />
            </Button>

            <div className="mx-1 h-6 w-px bg-border" />

            <Button
                variant={editor.isActive('blockquote') ? 'secondary' : 'ghost'}
                size="icon"
                onClick={() => editor.chain().focus().toggleBlockquote().run()}
                disabled={disabled}
                title="Citação"
            >
                <Quote className="h-4 w-4" />
            </Button>
            <Button
                variant={editor.isActive('bulletList') ? 'secondary' : 'ghost'}
                size="icon"
                onClick={() => editor.chain().focus().toggleBulletList().run()}
                disabled={disabled}
                title="Lista"
            >
                <List className="h-4 w-4" />
            </Button>
            <Button
                variant={editor.isActive('orderedList') ? 'secondary' : 'ghost'}
                size="icon"
                onClick={() => editor.chain().focus().toggleOrderedList().run()}
                disabled={disabled}
                title="Lista numerada"
            >
                <ListOrdered className="h-4 w-4" />
            </Button>

            <div className="mx-1 h-6 w-px bg-border" />

            <Button
                variant="ghost"
                size="icon"
                onClick={() => editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run()}
                disabled={disabled}
                title="Inserir tabela"
            >
                <TableIcon className="h-4 w-4" />
            </Button>
        </div>
    );
}

interface MarkdownPreviewProps {
    content: string;
    className?: string;
}

export function MarkdownPreview({ content, className }: MarkdownPreviewProps) {
    return (
        <div
            className={cn(
                "prose prose-sm dark:prose-invert max-w-none bg-background rounded-lg border p-6 min-h-full shadow-sm overflow-auto",
                className
            )}
        >
            <Markdown
                remarkPlugins={[remarkGfm]}
                components={{
                    table: ({ node, ...props }) => (
                        <table className="w-full border-collapse border border-zinc-300 my-4 text-sm" {...props} />
                    ),
                    thead: ({ node, ...props }) => (
                        <thead className="bg-zinc-100 dark:bg-zinc-800" {...props} />
                    ),
                    tbody: ({ node, ...props }) => (
                        <tbody className="bg-white dark:bg-zinc-950" {...props} />
                    ),
                    tr: ({ node, ...props }) => (
                        <tr className="border-b border-zinc-300 dark:border-zinc-700" {...props} />
                    ),
                    th: ({ node, ...props }) => (
                        <th className="border border-zinc-300 dark:border-zinc-700 px-4 py-2 text-left font-bold text-zinc-900 dark:text-zinc-100" {...props} />
                    ),
                    td: ({ node, ...props }) => (
                        <td className="border border-zinc-300 dark:border-zinc-700 px-4 py-2 text-zinc-800 dark:text-zinc-300" {...props} />
                    ),
                    p: ({ node, ...props }) => (
                        <p className="mb-4 leading-relaxed" {...props} />
                    ),
                    h1: ({ node, ...props }) => (
                        <h1 className="text-2xl font-bold mb-4 mt-6 text-foreground" {...props} />
                    ),
                    h2: ({ node, ...props }) => (
                        <h2 className="text-xl font-bold mb-3 mt-5 text-foreground" {...props} />
                    ),
                    h3: ({ node, ...props }) => (
                        <h3 className="text-lg font-bold mb-2 mt-4 text-foreground" {...props} />
                    ),
                    ul: ({ node, ...props }) => (
                        <ul className="list-disc pl-5 mb-4 space-y-1" {...props} />
                    ),
                    ol: ({ node, ...props }) => (
                        <ol className="list-decimal pl-5 mb-4 space-y-1" {...props} />
                    ),
                    blockquote: ({ node, ...props }) => (
                        <blockquote className="border-l-4 border-primary/30 pl-4 italic my-4 text-muted-foreground" {...props} />
                    ),
                }}
            >
                {content}
            </Markdown>
        </div>
    );
}

interface MarkdownEditorPanelProps {
    content: string;
    onChange: (content: string) => void;
    onSave?: (content: string) => void | Promise<void>;
    onCancel?: () => void;
    onDownload?: (content: string) => void;
    readOnly?: boolean;
    className?: string;
}

export function MarkdownEditorPanel({
    content,
    onChange,
    onSave,
    onCancel,
    onDownload,
    readOnly = false,
    className,
}: MarkdownEditorPanelProps) {
    const [viewMode, setViewMode] = useState<'formatted' | 'source' | 'preview' | 'split'>('formatted');
    const [savedContent, setSavedContent] = useState(content);
    const [isFullscreen, setIsFullscreen] = useState(false);
    const [hasRichEdits, setHasRichEdits] = useState(false);
    const internalChangeRef = useRef(false);
    const richChangeTimeoutRef = useRef<number | null>(null);
    const lastRichMarkdownRef = useRef<string | null>(null);
    const hasRichEditsRef = useRef(false);

    const handleContentChange = useCallback((nextContent: string) => {
        internalChangeRef.current = true;
        onChange(nextContent);
    }, [onChange]);

    const richEditor = useEditor({
        extensions: [
            StarterKit.configure({ codeBlock: false }),
            TipTapTable.configure({ resizable: true }),
            TableRow,
            TableHeader,
            TableCell,
        ],
        content: parseMarkdownToHtmlSync(content),
        editable: !readOnly,
        onUpdate: ({ editor }) => {
            if (readOnly) return;
            if (!hasRichEditsRef.current) {
                hasRichEditsRef.current = true;
                setHasRichEdits(true);
            }

            if (richChangeTimeoutRef.current) {
                window.clearTimeout(richChangeTimeoutRef.current);
            }
            richChangeTimeoutRef.current = window.setTimeout(() => {
                const markdown = serializeTipTapDocToMarkdown(editor.state.doc);
                lastRichMarkdownRef.current = markdown;
                handleContentChange(markdown);
            }, 250);
        },
    });

    const clearRichChangeTimeout = useCallback(() => {
        if (richChangeTimeoutRef.current) {
            window.clearTimeout(richChangeTimeoutRef.current);
            richChangeTimeoutRef.current = null;
        }
    }, []);

    useEffect(() => {
        if (internalChangeRef.current) {
            internalChangeRef.current = false;
            return;
        }
        setSavedContent(content);
        hasRichEditsRef.current = false;
        setHasRichEdits(false);
    }, [content]);

    const hasChanges = useMemo(() => content !== savedContent, [content, savedContent]);
    const isDirty = hasChanges || hasRichEdits;

    const handleViewModeChange = useCallback((value: string) => {
        if (value === 'formatted' || value === 'source' || value === 'preview' || value === 'split') {
            setViewMode(value);
        }
    }, []);

    const flushRichToMarkdown = useCallback(() => {
        if (!richEditor) return content;
        const markdown = serializeTipTapDocToMarkdown(richEditor.state.doc);
        if (markdown !== content) {
            lastRichMarkdownRef.current = markdown;
            handleContentChange(markdown);
        }
        return markdown;
    }, [content, handleContentChange, richEditor]);

    useEffect(() => {
        return () => clearRichChangeTimeout();
    }, [clearRichChangeTimeout]);

    const lastViewModeRef = useRef(viewMode);
    useEffect(() => {
        const previousViewMode = lastViewModeRef.current;
        lastViewModeRef.current = viewMode;

        if (previousViewMode === 'formatted' && viewMode !== 'formatted') {
            clearRichChangeTimeout();
            flushRichToMarkdown();
        }
    }, [clearRichChangeTimeout, flushRichToMarkdown, viewMode]);

    useEffect(() => {
        if (!richEditor) return;
        if (viewMode !== 'formatted') return;
        if (lastRichMarkdownRef.current === content) return;
        richEditor.commands.setContent(parseMarkdownToHtmlSync(content), false);
    }, [content, richEditor, viewMode]);

    const handleUndo = useCallback(() => {
        internalChangeRef.current = true;
        onChange(savedContent);
        hasRichEditsRef.current = false;
        setHasRichEdits(false);
    }, [onChange, savedContent]);

    const handleSave = useCallback(async () => {
        if (!onSave) return;
        try {
            const latestContent = viewMode === 'formatted' ? flushRichToMarkdown() : content;
            await onSave(latestContent);
            setSavedContent(latestContent);
            hasRichEditsRef.current = false;
            setHasRichEdits(false);
        } catch (error) {
            console.error(error);
        }
    }, [content, flushRichToMarkdown, onSave, viewMode]);

    const handleDownload = useCallback(() => {
        if (!onDownload) return;
        const latestContent = viewMode === 'formatted' ? flushRichToMarkdown() : content;
        onDownload(latestContent);
    }, [content, flushRichToMarkdown, onDownload, viewMode]);

    const wordCount = useMemo(() => {
        return content.split(/\s+/).filter(Boolean).length;
    }, [content]);

    const charCount = content.length;

    const renderSourceEditor = () => (
        <Textarea
            value={content}
            onChange={(e) => handleContentChange(e.target.value)}
            readOnly={readOnly}
            className={cn(
                "font-mono text-sm min-h-[600px] resize-none",
                "bg-zinc-950 text-zinc-100 dark:bg-zinc-900",
                "border-zinc-700 focus:border-primary",
                "leading-relaxed"
            )}
            placeholder="# Título do Documento..."
        />
    );

    const containerClass = cn(
        "flex flex-col rounded-lg border bg-card",
        isFullscreen && "fixed inset-4 z-50 shadow-2xl",
        className
    );

    return (
        <div className={containerClass}>
            {/* Header / Toolbar */}
            <div className="flex items-center justify-between px-4 py-3 border-b bg-muted/30">
                <div className="flex items-center gap-2">
                    <Tabs value={viewMode} onValueChange={handleViewModeChange}>
                        <TabsList className="h-8">
                            <TabsTrigger value="source" className="text-xs gap-1.5">
                                <Edit3 className="h-3.5 w-3.5" />
                                Código
                            </TabsTrigger>
                            <TabsTrigger value="formatted" className="text-xs gap-1.5">
                                <Pilcrow className="h-3.5 w-3.5" />
                                Formatado
                            </TabsTrigger>
                            <TabsTrigger value="preview" className="text-xs gap-1.5">
                                <Eye className="h-3.5 w-3.5" />
                                Preview
                            </TabsTrigger>
                            <TabsTrigger value="split" className="text-xs gap-1.5">
                                <Split className="h-3.5 w-3.5" />
                                Dividir
                            </TabsTrigger>
                        </TabsList>
                    </Tabs>

                    <div className="text-xs text-muted-foreground ml-4">
                        {wordCount.toLocaleString()} palavras · {charCount.toLocaleString()} caracteres
                    </div>
                </div>

                <div className="flex items-center gap-2">
                    {isDirty && !readOnly && (
                        <Button
                            variant="ghost"
                            size="sm"
                            onClick={handleUndo}
                            className="text-xs gap-1.5"
                        >
                            <Undo2 className="h-3.5 w-3.5" />
                            Desfazer
                        </Button>
                    )}

                    {onDownload && (
                        <Button
                            variant="ghost"
                            size="sm"
                            onClick={handleDownload}
                            className="text-xs gap-1.5"
                        >
                            <Download className="h-3.5 w-3.5" />
                            Baixar
                        </Button>
                    )}

                    <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => setIsFullscreen(!isFullscreen)}
                        className="h-8 w-8"
                    >
                        {isFullscreen ? (
                            <Minimize2 className="h-4 w-4" />
                        ) : (
                            <Maximize2 className="h-4 w-4" />
                        )}
                    </Button>

                    {onCancel && (
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={onCancel}
                            className="text-xs gap-1.5"
                        >
                            <X className="h-3.5 w-3.5" />
                            Cancelar
                        </Button>
                    )}

                    {onSave && !readOnly && (
                        <Button
                            size="sm"
                            onClick={handleSave}
                            disabled={!isDirty}
                            className="text-xs gap-1.5"
                        >
                            <Save className="h-3.5 w-3.5" />
                            Salvar
                        </Button>
                    )}
                </div>
            </div>

            {/* Content Area */}
            <div className={cn(
                "flex-1 overflow-hidden",
                isFullscreen ? "h-[calc(100%-60px)]" : "min-h-[600px]"
            )}>
                {viewMode === 'source' && (
                    <div className="h-full p-4 overflow-auto">
                        {renderSourceEditor()}
                    </div>
                )}

                {viewMode === 'formatted' && (
                    <div className="h-full p-4 overflow-auto">
                        <div className="h-full flex flex-col gap-3">
                            <MarkdownRichToolbar editor={richEditor} disabled={readOnly} />
                            <div className="flex-1 overflow-hidden">
                                <div className="h-full overflow-auto rounded-lg border bg-background shadow-sm">
                                    <EditorContent
                                        editor={richEditor}
                                        className="prose prose-sm dark:prose-invert max-w-none p-6 focus:outline-none min-h-[600px]"
                                    />
                                </div>
                            </div>
                        </div>
                    </div>
                )}

                {viewMode === 'preview' && (
                    <div className="h-full p-4 overflow-auto">
                        <MarkdownPreview content={content} />
                    </div>
                )}

                {viewMode === 'split' && (
                    <div className="h-full grid grid-cols-2 divide-x">
                        <div className="p-4 overflow-auto bg-zinc-950 dark:bg-zinc-900">
                            {renderSourceEditor()}
                        </div>
                        <div className="p-4 overflow-auto bg-background">
                            <MarkdownPreview content={content} />
                        </div>
                    </div>
                )}
            </div>

            {/* Status Bar */}
            {isDirty && (
                <div className="px-4 py-2 border-t bg-yellow-50 dark:bg-yellow-900/20 text-xs text-yellow-700 dark:text-yellow-300">
                    ⚠️ Você tem alterações não salvas
                </div>
            )}
        </div>
    );
}
