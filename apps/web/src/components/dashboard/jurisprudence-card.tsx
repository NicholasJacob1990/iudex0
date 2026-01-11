import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardFooter, CardHeader } from '@/components/ui/card';
import { Copy, Sparkles, Gavel, ExternalLink, Bookmark, CheckSquare, FileText, Trash2 } from 'lucide-react';
import { cn } from '@/lib/utils';

interface JurisprudenceCardProps {
    precedent: {
        id: string;
        court: string;
        title: string;
        summary: string;
        date: string;
        tags: string[];
        processNumber: string;
    };
    onCopy: (text: string) => void;
    onSummarize: (id: string) => void;
    onSelect?: (id: string) => void;
    onOpenInCourt?: (id: string) => void;
    onViewFull?: (id: string) => void;
    onSaveToLibrary?: (id: string) => void;
    onDelete?: (id: string) => void;
}

export function JurisprudenceCard({
    precedent,
    onCopy,
    onSummarize,
    onSelect,
    onOpenInCourt,
    onViewFull,
    onSaveToLibrary,
    onDelete
}: JurisprudenceCardProps) {
    return (
        <Card className="group overflow-hidden border-outline/30 bg-white transition-all hover:border-primary/30 hover:shadow-md">
            <CardHeader className="flex flex-row items-start justify-between space-y-0 pb-2">
                <div className="flex items-center gap-2">
                    <Badge variant="outline" className="bg-indigo-500/10 text-indigo-600 border-indigo-500/20">
                        {precedent.court}
                    </Badge>
                    <span className="text-xs text-muted-foreground">{precedent.date}</span>
                </div>
                <div className="flex gap-1">
                    {onSaveToLibrary && (
                        <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 text-muted-foreground hover:text-primary"
                            onClick={() => onSaveToLibrary(precedent.id)}
                            title="Salvar na biblioteca"
                        >
                            <Bookmark className="h-4 w-4" />
                        </Button>
                    )}
                    {onOpenInCourt && (
                        <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 text-muted-foreground hover:text-primary"
                            onClick={() => onOpenInCourt(precedent.id)}
                            title="Abrir consulta no tribunal"
                        >
                            <ExternalLink className="h-4 w-4" />
                        </Button>
                    )}
                    {onDelete && (
                        <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 text-muted-foreground hover:text-destructive"
                            onClick={() => onDelete(precedent.id)}
                            title="Deletar"
                        >
                            <Trash2 className="h-4 w-4" />
                        </Button>
                    )}
                </div>
            </CardHeader>
            <CardContent>
                <h3 className="mb-2 font-semibold leading-tight text-foreground group-hover:text-primary transition-colors">
                    {precedent.title}
                </h3>
                <p className="mb-4 text-sm text-muted-foreground line-clamp-3">
                    {precedent.summary}
                </p>
                <div className="flex flex-wrap gap-2">
                    {precedent.tags.map((tag) => (
                        <Badge key={tag} variant="secondary" className="bg-sand/70 text-xs text-foreground">
                            {tag}
                        </Badge>
                    ))}
                </div>
            </CardContent>
            <CardFooter className="border-t border-outline/20 bg-sand/30 pt-3">
                <div className="flex w-full items-center justify-between gap-3 flex-wrap">
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                        <Gavel className="h-3 w-3" />
                        <span>{precedent.processNumber}</span>
                    </div>
                    <div className="flex gap-2 flex-wrap">
                        {onSelect && (
                            <Button
                                variant="default"
                                size="sm"
                                className="h-8 gap-2 text-xs bg-primary text-primary-foreground"
                                onClick={() => onSelect(precedent.id)}
                            >
                                <CheckSquare className="h-3 w-3" />
                                Selecionar
                            </Button>
                        )}
                        {onViewFull && (
                            <Button
                                variant="outline"
                                size="sm"
                                className="h-8 gap-2 text-xs"
                                onClick={() => onViewFull(precedent.id)}
                            >
                                <FileText className="h-3 w-3" />
                                Inteiro Teor
                            </Button>
                        )}
                        <Button
                            variant="ghost"
                            size="sm"
                            className="h-8 gap-2 text-xs hover:bg-primary/10 hover:text-primary"
                            onClick={() => onSummarize(precedent.id)}
                        >
                            <Sparkles className="h-3 w-3" />
                            Resumir
                        </Button>
                        <Button
                            variant="outline"
                            size="sm"
                            className="h-8 gap-2 text-xs"
                            onClick={() => onCopy(precedent.summary)}
                        >
                            <Copy className="h-3 w-3" />
                            Copiar
                        </Button>
                    </div>
                </div>
            </CardFooter>
        </Card>
    );
}
