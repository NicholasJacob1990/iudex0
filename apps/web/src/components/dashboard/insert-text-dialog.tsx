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
import { Textarea } from '@/components/ui/textarea';
import { toast } from 'sonner';
import { FileText } from 'lucide-react';

interface InsertTextDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onSuccess?: () => void;
}

export function InsertTextDialog({ open, onOpenChange, onSuccess }: InsertTextDialogProps) {
    const [title, setTitle] = useState('');
    const [content, setContent] = useState('');
    const [tags, setTags] = useState('');
    const [isCreating, setIsCreating] = useState(false);

    const handleSubmit = async () => {
        if (!title.trim()) {
            toast.error('Por favor, insira um título para o documento');
            return;
        }

        if (!content.trim()) {
            toast.error('Por favor, insira o conteúdo do documento');
            return;
        }

        setIsCreating(true);

        try {
            const formData = new FormData();
            formData.append('title', title);
            formData.append('content', content);
            if (tags) {
                formData.append('tags', tags);
            }

            const response = await fetch('/api/documents/from-text', {
                method: 'POST',
                credentials: 'include',
                body: formData,
            });

            if (!response.ok) {
                throw new Error('Erro ao criar documento');
            }

            const document = await response.json();
            toast.success(`Documento "${title}" criado com sucesso!`);

            // Limpar campos
            setTitle('');
            setContent('');
            setTags('');

            // Chamar callback de sucesso
            if (onSuccess) {
                onSuccess();
            }

            onOpenChange(false);
        } catch (error) {
            console.error('Erro ao criar documento:', error);
            toast.error('Erro ao criar documento');
        } finally {
            setIsCreating(false);
        }
    };

    const handleCancel = () => {
        setTitle('');
        setContent('');
        setTags('');
        onOpenChange(false);
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-[600px]">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <FileText className="h-5 w-5 text-primary" />
                        Inserir Texto Manualmente
                    </DialogTitle>
                    <DialogDescription>
                        Cole ou digite o conteúdo que deseja adicionar como documento
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-4 py-4">
                    {/* Título */}
                    <div className="space-y-2">
                        <Label htmlFor="title">Título do documento *</Label>
                        <Input
                            id="title"
                            placeholder="Ex: Contrato de Prestação de Serviços"
                            value={title}
                            onChange={(e) => setTitle(e.target.value)}
                        />
                    </div>

                    {/* Conteúdo */}
                    <div className="space-y-2">
                        <Label htmlFor="content">Conteúdo *</Label>
                        <Textarea
                            id="content"
                            placeholder="Cole ou digite o texto aqui..."
                            value={content}
                            onChange={(e) => setContent(e.target.value)}
                            rows={15}
                            className="font-mono text-sm"
                        />
                        <p className="text-xs text-muted-foreground">
                            {content.length > 0 && `${content.length} caracteres`}
                        </p>
                    </div>

                    {/* Tags (opcional) */}
                    <div className="space-y-2">
                        <Label htmlFor="tags">Tags (opcional)</Label>
                        <Input
                            id="tags"
                            placeholder="Ex: contrato, civil, prestação de serviços"
                            value={tags}
                            onChange={(e) => setTags(e.target.value)}
                        />
                        <p className="text-xs text-muted-foreground">
                            Separe as tags por vírgulas
                        </p>
                    </div>
                </div>

                <DialogFooter>
                    <Button variant="outline" onClick={handleCancel} disabled={isCreating}>
                        Cancelar
                    </Button>
                    <Button onClick={handleSubmit} disabled={isCreating}>
                        {isCreating ? 'Criando...' : 'Criar Documento'}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
