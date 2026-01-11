'use client';

import { useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { FileText } from 'lucide-react';
import { toast } from 'sonner';

interface ManualPrecedentDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
}

export function ManualPrecedentDialog({ open, onOpenChange }: ManualPrecedentDialogProps) {
    const [tribunal, setTribunal] = useState('');
    const [processo, setProcesso] = useState('');
    const [ementa, setEmenta] = useState('');

    const handleSubmit = () => {
        if (!tribunal.trim() || !ementa.trim()) {
            toast.error('Preencha ao menos o tribunal e a ementa');
            return;
        }

        toast.success('Precedente adicionado com sucesso!');
        setTribunal('');
        setProcesso('');
        setEmenta('');
        onOpenChange(false);
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-2xl">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <FileText className="h-5 w-5 text-primary" />
                        Inserir Precedente Manualmente
                    </DialogTitle>
                </DialogHeader>

                <div className="space-y-4 py-4">
                    <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-2">
                            <Label htmlFor="tribunal">Tribunal *</Label>
                            <Input
                                id="tribunal"
                                placeholder="Ex: STJ, STF, TRF3..."
                                value={tribunal}
                                onChange={(e) => setTribunal(e.target.value)}
                            />
                        </div>
                        <div className="space-y-2">
                            <Label htmlFor="processo">Número do Processo</Label>
                            <Input
                                id="processo"
                                placeholder="Ex: REsp 1234567"
                                value={processo}
                                onChange={(e) => setProcesso(e.target.value)}
                            />
                        </div>
                    </div>

                    <div className="space-y-2">
                        <Label htmlFor="ementa">Ementa *</Label>
                        <textarea
                            id="ementa"
                            className="w-full min-h-[200px] rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                            placeholder="Cole ou digite a ementa do precedente aqui..."
                            value={ementa}
                            onChange={(e) => setEmenta(e.target.value)}
                        />
                    </div>

                    <p className="text-xs text-muted-foreground">* Campos obrigatórios</p>
                </div>

                <DialogFooter>
                    <Button variant="outline" onClick={() => onOpenChange(false)}>
                        Cancelar
                    </Button>
                    <Button onClick={handleSubmit}>Adicionar Precedente</Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
