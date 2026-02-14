import React, { useEffect, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Download, ZoomIn, ZoomOut } from 'lucide-react';
import { cn } from '@/lib/utils';

interface DiagramViewerProps {
    code: string;
    title?: string;
    type?: string;
    compact?: boolean;
}

export function DiagramViewer({ code, title = 'Diagrama', type = 'mermaid', compact = false }: DiagramViewerProps) {
    const elementRef = useRef<HTMLDivElement>(null);
    const [scale, setScale] = React.useState(1);
    const [error, setError] = React.useState<string | null>(null);

    useEffect(() => {
        const renderDiagram = async () => {
            if (!elementRef.current || !code) return;

            try {
                setError(null);
                const mermaid = (await import('mermaid')).default;
                mermaid.initialize({
                    startOnLoad: false,
                    theme: 'default',
                    securityLevel: 'loose',
                    fontFamily: 'inherit',
                });
                const id = `mermaid-${Math.random().toString(36).substr(2, 9)}`;
                const { svg } = await mermaid.render(id, code);
                elementRef.current.innerHTML = svg;
            } catch (err) {
                console.error('Mermaid render error:', err);
                setError('Erro ao renderizar diagrama. Verifique a sintaxe.');
                // Fallback to showing code
                elementRef.current.innerHTML = `<pre class="text-xs p-4 bg-muted rounded overflow-auto">${code}</pre>`;
            }
        };

        renderDiagram();
    }, [code]);

    const handleDownload = () => {
        if (!elementRef.current) return;

        const svg = elementRef.current.querySelector('svg');
        if (!svg) return;

        const svgData = new XMLSerializer().serializeToString(svg);
        const blob = new Blob([svgData], { type: 'image/svg+xml;charset=utf-8' });
        const url = URL.createObjectURL(blob);

        const link = document.createElement('a');
        link.href = url;
        link.download = `${title.toLowerCase().replace(/\s+/g, '-')}.svg`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    };

    return (
        <Card className={cn("w-full overflow-hidden", compact && "border-slate-200 shadow-none")}>
            {!compact && (
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-sm font-medium">
                        {title}
                        {type && <span className="ml-2 text-xs text-muted-foreground uppercase">({type})</span>}
                    </CardTitle>
                    <div className="flex items-center gap-1">
                        <Button variant="ghost" size="icon" onClick={() => setScale(s => Math.max(0.5, s - 0.1))}>
                            <ZoomOut className="h-4 w-4" />
                        </Button>
                        <Button variant="ghost" size="icon" onClick={() => setScale(s => Math.min(2, s + 0.1))}>
                            <ZoomIn className="h-4 w-4" />
                        </Button>
                        <Button variant="ghost" size="icon" onClick={handleDownload}>
                            <Download className="h-4 w-4" />
                        </Button>
                    </div>
                </CardHeader>
            )}
            <CardContent className={cn(compact && "p-3 pt-3")}>
                <div className="overflow-auto flex justify-center min-h-[200px] p-4 bg-white/50 dark:bg-black/20 rounded-lg">
                    {error ? (
                        <div className="text-red-500 text-sm flex flex-col items-center justify-center gap-2">
                            <p>{error}</p>
                            <pre className="text-xs bg-muted p-2 rounded max-w-full overflow-auto">{code}</pre>
                        </div>
                    ) : (
                        <div
                            ref={elementRef}
                            style={{ transform: `scale(${scale})`, transformOrigin: 'center top', transition: 'transform 0.2s' }}
                            className="w-full flex justify-center"
                        />
                    )}
                </div>
            </CardContent>
        </Card>
    );
}
