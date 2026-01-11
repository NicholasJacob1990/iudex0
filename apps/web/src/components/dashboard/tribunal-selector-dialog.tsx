'use client';

import { useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Scale } from 'lucide-react';
import { toast } from 'sonner';

interface TribunalSelectorDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
}

const tribunals = [
    { id: 'stf', name: 'STF', fullName: 'Supremo Tribunal Federal' },
    { id: 'stj', name: 'STJ', fullName: 'Superior Tribunal de Justiça' },
    { id: 'tst', name: 'TST', fullName: 'Tribunal Superior do Trabalho' },
    { id: 'tse', name: 'TSE', fullName: 'Tribunal Superior Eleitoral' },
    { id: 'stm', name: 'STM', fullName: 'Superior Tribunal Militar' },
    { id: 'trf1', name: 'TRF1', fullName: 'Tribunal Regional Federal da 1ª Região' },
    { id: 'trf2', name: 'TRF2', fullName: 'Tribunal Regional Federal da 2ª Região' },
    { id: 'trf3', name: 'TRF3', fullName: 'Tribunal Regional Federal da 3ª Região' },
    { id: 'trf4', name: 'TRF4', fullName: 'Tribunal Regional Federal da 4ª Região' },
    { id: 'trf5', name: 'TRF5', fullName: 'Tribunal Regional Federal da 5ª Região' },
    { id: 'trf6', name: 'TRF6', fullName: 'Tribunal Regional Federal da 6ª Região' },
];

export function TribunalSelectorDialog({ open, onOpenChange }: TribunalSelectorDialogProps) {
    const [selectedTribunals, setSelectedTribunals] = useState<Set<string>>(new Set(['stf', 'stj']));
    const [syncSearch, setSyncSearch] = useState(true);
    const [searchTerms, setSearchTerms] = useState<Record<string, string>>({});

    const toggleTribunal = (id: string) => {
        const newSet = new Set(selectedTribunals);
        if (newSet.has(id)) {
            newSet.delete(id);
        } else {
            newSet.add(id);
        }
        setSelectedTribunals(newSet);
    };

    const toggleSelectAll = () => {
        if (selectedTribunals.size === tribunals.length) {
            setSelectedTribunals(new Set());
        } else {
            setSelectedTribunals(new Set(tribunals.map((t) => t.id)));
        }
    };

    const handleApply = () => {
        toast.success(`${selectedTribunals.size} tribunal(is) selecionado(s)`);
        onOpenChange(false);
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-2xl">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Scale className="h-5 w-5 text-primary" />
                        Selecionar Tribunais
                    </DialogTitle>
                </DialogHeader>

                <div className="space-y-4 py-4">
                    {/* Sync Toggle */}
                    <div className="flex items-center justify-between rounded-2xl border border-outline/30 bg-sand/20 p-4">
                        <div className="space-y-0.5">
                            <Label htmlFor="sync-search" className="text-sm font-semibold">
                                Sincronizar busca
                            </Label>
                            <p className="text-xs text-muted-foreground">
                                Aplicar o mesmo termo de busca em todos os tribunais
                            </p>
                        </div>
                        <Switch id="sync-search" checked={syncSearch} onCheckedChange={setSyncSearch} />
                    </div>

                    {/* Select All */}
                    <div className="flex items-center space-x-2 pb-2 border-b border-outline/20">
                        <Checkbox
                            id="select-all"
                            checked={selectedTribunals.size === tribunals.length}
                            onCheckedChange={toggleSelectAll}
                        />
                        <Label htmlFor="select-all" className="text-sm font-semibold cursor-pointer">
                            Selecionar todos ({selectedTribunals.size}/{tribunals.length})
                        </Label>
                    </div>

                    {/* Tribunal List */}
                    <div className="max-h-[400px] overflow-y-auto space-y-2">
                        {tribunals.map((tribunal) => {
                            const isSelected = selectedTribunals.has(tribunal.id);
                            return (
                                <div
                                    key={tribunal.id}
                                    className="rounded-2xl border border-outline/30 bg-white p-3 space-y-2"
                                >
                                    <div className="flex items-center space-x-2">
                                        <Checkbox
                                            id={tribunal.id}
                                            checked={isSelected}
                                            onCheckedChange={() => toggleTribunal(tribunal.id)}
                                        />
                                        <Label htmlFor={tribunal.id} className="flex-1 cursor-pointer">
                                            <span className="font-semibold text-primary">{tribunal.name}</span>
                                            <span className="text-xs text-muted-foreground ml-2">
                                                {tribunal.fullName}
                                            </span>
                                        </Label>
                                    </div>
                                    {!syncSearch && isSelected && (
                                        <Input
                                            placeholder={`Termo de busca para ${tribunal.name}...`}
                                            value={searchTerms[tribunal.id] || ''}
                                            onChange={(e) =>
                                                setSearchTerms({ ...searchTerms, [tribunal.id]: e.target.value })
                                            }
                                            className="h-8 text-xs"
                                        />
                                    )}
                                </div>
                            );
                        })}
                    </div>
                </div>

                <DialogFooter>
                    <Button variant="outline" onClick={() => onOpenChange(false)}>
                        Cancelar
                    </Button>
                    <Button onClick={handleApply}>Aplicar Seleção</Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
