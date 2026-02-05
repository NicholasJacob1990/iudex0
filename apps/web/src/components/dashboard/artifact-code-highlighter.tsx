'use client';

import React, { useEffect, useState, useMemo, useRef, useCallback } from 'react';
import { codeToHtml, type BundledLanguage, type BundledTheme } from 'shiki';
import { type ArtifactLanguage } from '@/stores/canvas-store';
import { cn } from '@/lib/utils';
import { Copy, Check, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';

// Map our language types to Shiki languages
const languageMap: Record<ArtifactLanguage, BundledLanguage> = {
    typescript: 'typescript',
    javascript: 'javascript',
    jsx: 'jsx',
    tsx: 'tsx',
    python: 'python',
    html: 'html',
    css: 'css',
    json: 'json',
    sql: 'sql',
    bash: 'bash',
    markdown: 'markdown',
    yaml: 'yaml',
    rust: 'rust',
    go: 'go',
    java: 'java',
    csharp: 'csharp',
    react: 'tsx',
    vue: 'vue',
    svelte: 'svelte',
    other: 'javascript', // Fallback to javascript for syntax highlighting
};

interface CodeHighlighterProps {
    code: string;
    language: ArtifactLanguage;
    theme?: 'dark' | 'light' | 'auto';
    showLineNumbers?: boolean;
    className?: string;
    maxHeight?: number;
    isStreaming?: boolean;
}

export function CodeHighlighter({
    code,
    language,
    theme = 'dark',
    showLineNumbers = true,
    className,
    maxHeight,
    isStreaming = false,
}: CodeHighlighterProps) {
    const [highlightedCode, setHighlightedCode] = useState<string>('');
    const [isLoading, setIsLoading] = useState(true);
    const [copied, setCopied] = useState(false);
    const codeRef = useRef<HTMLDivElement>(null);
    const debounceRef = useRef<NodeJS.Timeout | null>(null);
    const lastCodeRef = useRef<string>('');
    const requestIdRef = useRef(0); // For race condition protection
    const shouldAutoScrollRef = useRef(true); // Only auto-scroll if user is at bottom

    const shikiLang = (languageMap[language] || 'javascript') as BundledLanguage;
    const shikiTheme: BundledTheme = theme === 'light' ? 'github-light' : 'github-dark';

    // Track if user is at bottom for conditional auto-scroll
    useEffect(() => {
        const el = codeRef.current;
        if (!el) return;

        const onScroll = () => {
            const threshold = 40; // px from bottom
            const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < threshold;
            shouldAutoScrollRef.current = atBottom;
        };

        el.addEventListener('scroll', onScroll, { passive: true });
        onScroll(); // Initial check
        return () => el.removeEventListener('scroll', onScroll);
    }, []);

    // Conditional auto-scroll during streaming (only if user is at bottom)
    useEffect(() => {
        const el = codeRef.current;
        if (!isStreaming || !el) return;
        if (!shouldAutoScrollRef.current) return;

        const id = requestAnimationFrame(() => {
            el.scrollTop = el.scrollHeight;
        });
        return () => cancelAnimationFrame(id);
    }, [code, isStreaming]);

    // Debounced highlighting with race condition protection
    const highlightCode = useCallback(async (codeToHighlight: string) => {
        const reqId = ++requestIdRef.current;
        try {
            const html = await codeToHtml(codeToHighlight, {
                lang: shikiLang,
                theme: shikiTheme,
            });
            // Ignore stale results (race condition protection)
            if (reqId !== requestIdRef.current) return;
            setHighlightedCode(html);
        } catch (error) {
            console.error('Shiki highlighting error:', error);
            if (reqId !== requestIdRef.current) return;
            setHighlightedCode(`<pre><code>${escapeHtml(codeToHighlight)}</code></pre>`);
        } finally {
            if (reqId === requestIdRef.current) {
                setIsLoading(false);
            }
        }
    }, [shikiLang, shikiTheme]);

    useEffect(() => {
        // Skip if code hasn't changed
        if (code === lastCodeRef.current) return;
        lastCodeRef.current = code;

        // Clear pending debounce
        if (debounceRef.current) {
            clearTimeout(debounceRef.current);
        }

        // During streaming, use longer debounce (250ms) to reduce load
        if (isStreaming) {
            debounceRef.current = setTimeout(() => {
                highlightCode(code);
            }, 250); // 250ms debounce during streaming (GPT recommended)
        } else {
            // When not streaming, highlight immediately
            highlightCode(code);
        }

        return () => {
            if (debounceRef.current) {
                clearTimeout(debounceRef.current);
            }
        };
    }, [code, isStreaming, highlightCode]);

    const handleCopy = async () => {
        await navigator.clipboard.writeText(code);
        setCopied(true);
        toast.success('Código copiado');
        setTimeout(() => setCopied(false), 2000);
    };

    // Add line numbers to the HTML
    const processedHtml = useMemo(() => {
        if (!showLineNumbers || !highlightedCode) return highlightedCode;

        // Shiki outputs <pre><code>...</code></pre>
        // We need to wrap each line
        const lines = code.split('\n');
        const lineCount = lines.length;

        // Create line numbers column
        const lineNumbers = Array.from({ length: lineCount }, (_, i) => i + 1)
            .map(n => `<span class="line-number">${n}</span>`)
            .join('\n');

        return `
            <div class="code-with-lines">
                <div class="line-numbers">${lineNumbers}</div>
                <div class="code-content">${highlightedCode}</div>
            </div>
        `;
    }, [highlightedCode, showLineNumbers, code]);

    if (isLoading) {
        return (
            <div className={cn(
                "bg-slate-900 rounded-lg p-4 animate-pulse",
                className
            )}>
                <div className="h-4 bg-slate-700 rounded w-3/4 mb-2" />
                <div className="h-4 bg-slate-700 rounded w-1/2 mb-2" />
                <div className="h-4 bg-slate-700 rounded w-2/3" />
            </div>
        );
    }

    return (
        <div className={cn("relative group", className)}>
            <style jsx global>{`
                .code-with-lines {
                    display: flex;
                    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
                    font-size: 13px;
                    line-height: 1.5;
                }
                .line-numbers {
                    display: flex;
                    flex-direction: column;
                    padding: 1rem 0.75rem 1rem 1rem;
                    text-align: right;
                    color: #6b7280;
                    user-select: none;
                    border-right: 1px solid #374151;
                    background: rgba(0,0,0,0.1);
                }
                .line-number {
                    display: block;
                }
                .code-content {
                    flex: 1;
                    overflow-x: auto;
                }
                .code-content pre {
                    margin: 0;
                    padding: 1rem;
                    background: transparent !important;
                }
                .code-content code {
                    background: transparent !important;
                }
                .shiki {
                    background: transparent !important;
                }
                @keyframes blink {
                    0%, 50% { opacity: 1; }
                    51%, 100% { opacity: 0; }
                }
                .streaming-cursor {
                    animation: blink 1s step-end infinite;
                }
            `}</style>

            {/* Streaming indicator bar */}
            {isStreaming && (
                <div className="absolute top-0 left-0 right-0 h-0.5 bg-gradient-to-r from-emerald-400 via-blue-500 to-emerald-400 animate-pulse z-10" />
            )}

            <div
                ref={codeRef}
                className={cn(
                    "bg-slate-900 rounded-lg overflow-hidden transition-all",
                    isStreaming && "ring-1 ring-emerald-400/50"
                )}
                style={{ maxHeight: maxHeight ? `${maxHeight}px` : undefined, overflow: 'auto' }}
            >
                <div
                    dangerouslySetInnerHTML={{ __html: processedHtml }}
                />
                {/* Streaming cursor at the end */}
                {isStreaming && (
                    <div className="px-4 pb-2 flex items-center gap-2">
                        <span className="streaming-cursor text-emerald-400 text-lg font-bold">▌</span>
                        <span className="text-xs text-emerald-400/70 flex items-center gap-1">
                            <Loader2 className="h-3 w-3 animate-spin" />
                            Gerando código...
                        </span>
                    </div>
                )}
            </div>

            {/* Copy button - hidden during streaming */}
            {!isStreaming && (
                <Button
                    variant="ghost"
                    size="icon"
                    className="absolute top-2 right-2 h-8 w-8 opacity-0 group-hover:opacity-100 transition-opacity bg-slate-800 hover:bg-slate-700"
                    onClick={handleCopy}
                >
                    {copied ? (
                        <Check className="h-4 w-4 text-green-400" />
                    ) : (
                        <Copy className="h-4 w-4 text-slate-400" />
                    )}
                </Button>
            )}
        </div>
    );
}

function escapeHtml(text: string): string {
    return text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

export default CodeHighlighter;
