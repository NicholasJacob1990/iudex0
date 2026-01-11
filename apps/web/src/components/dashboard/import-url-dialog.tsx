'use client';

import { useState } from 'react';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { toast } from 'sonner';
import { Link, Loader2 } from 'lucide-react';

interface ImportUrlDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onSuccess?: () => void;
}

export function ImportUrlDialog({ open, onOpenChange, onSuccess }: ImportUrlDialogProps) {
    const [url, setUrl] = useState('');
    const [tags, setTags] = useState('');
    const [isImporting, setIsImporting] = useState(false);

    const isValidUrl = (urlString: string) => {
        try {
            const url = new URL(urlString);
            return url.protocol === 'http:' || url.protocol === 'https:';
        } catch {
            return false;
        }
    };

    const handleImport = async () => {
        if (!url.trim()) {
            toast.error('Por favor, insira uma URL');
            return;
        }

        if (!isValidUrl(url)) {
            toast.error('Por favor, insira uma URL válida (http:// ou https://)');
            return;
        }

        setIsImporting(true);

        try {
            const formData = new FormData();
            formData.append('url', url);
            if (tags) {
                formData.append('tags', tags);
            }

            const response = await fetch('/api/documents/from-url', {
                method: 'POST',
                credentials: 'include',
                body: formData,
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Erro ao importar URL');
            }

            const document = await response.json();
            toast.success(`Conteúdo importado de "${document.name}"!`);

            // Limpar campos
            setUrl('');
            setTags('');

            // Chamar callback de sucesso
            if (onSuccess) {
                onSuccess();
            }

            onOpenChange(false);
        } catch (error) {
            console.error('Erro ao importar URL:', error);
            toast.error(error instanceof Error ? error.message : 'Erro ao importar conteúdo da URL');
        } finally {
            setIsImporting(false);
        }
    };

    const handleCancel = () => {
        setUrl('');
        setTags('');
        onOpenChange(false);
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-[500px]">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Link className="h-5 w-5 text-primary" />
                        Importar de URL
                    </DialogTitle>
                    <DialogDescription>
                        Importe artigos, páginas web e documentos online
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-4 py-4">
                    {/* URL */}
                    <div className="space-y-2">
                        <Label htmlFor="url">URL *</Label>
                        <Input
                            id="url"
                            type="url"
                            placeholder="https://exemplo.com/artigo"
                            value={url}
                            onChange={(e) => setUrl(e.target.value)}
                            disabled={isImporting}
                        />
                        <p className="text-xs text-muted-foreground">
                            O conteúdo será extraído automaticamente da página
                        </p>
                    </div>

                    {/* Tags (opcional) */}
                    <div className="space-y-2">
                        <Label htmlFor="tags">Tags (opcional)</Label>
                        <Input
                            id="tags"
                            placeholder="Ex: artigo, direito, jurisprudência"
                            value={tags}
                            onChange={(e) => setTags(e.target.value)}
                            disabled={isImporting}
                        />
                        <p className="text-xs text-muted-foreground">
                            Separe as tags por vírgulas
                        </p>
                    </div>
                </div>

                <DialogFooter>
                    <Button variant="outline" onClick={handleCancel} disabled={isImporting}>
                        Cancelar
                    </Button>
                    <Button onClick={handleImport} disabled={isImporting || !url.trim()}>
                        {isImporting ? (
                            <>
                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                Importando...
                            </>
                        ) : (
                            'Importar'
                        )}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
