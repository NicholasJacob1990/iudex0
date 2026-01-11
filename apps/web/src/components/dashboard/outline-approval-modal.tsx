'use client';

import { useState, useCallback } from 'react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog';
import {
    GripVertical,
    Plus,
    Trash2,
    Check,
    X,
    FileText,
    Sparkles,
    Edit3,
} from 'lucide-react';

export interface OutlineApprovalSection {
    id: string;
    title: string;
}

interface OutlineApprovalModalProps {
    isOpen: boolean;
    onClose: () => void;
    initialSections: OutlineApprovalSection[];
    documentType: string;
    onApprove: (sections: OutlineApprovalSection[]) => void;
    onReject: () => void;
}

export function OutlineApprovalModal({
    isOpen,
    onClose,
    initialSections,
    documentType,
    onApprove,
    onReject,
}: OutlineApprovalModalProps) {
    const [sections, setSections] = useState<OutlineApprovalSection[]>(initialSections);
    const [editingId, setEditingId] = useState<string | null>(null);
    const [editingTitle, setEditingTitle] = useState('');
    const [draggedIndex, setDraggedIndex] = useState<number | null>(null);
    const [dragOverIndex, setDragOverIndex] = useState<number | null>(null);

    // Sync with initial sections when modal opens
    useState(() => {
        setSections(initialSections);
    });

    const handleAddSection = useCallback(() => {
        const newId = `section-${Date.now()}`;
        setSections(prev => [...prev, { id: newId, title: 'Nova Seção' }]);
        setEditingId(newId);
        setEditingTitle('Nova Seção');
    }, []);

    const handleRemoveSection = useCallback((id: string) => {
        setSections(prev => prev.filter(s => s.id !== id));
    }, []);

    const handleStartEdit = useCallback((section: OutlineApprovalSection) => {
        setEditingId(section.id);
        setEditingTitle(section.title);
    }, []);

    const handleSaveEdit = useCallback(() => {
        if (editingId && editingTitle.trim()) {
            setSections(prev =>
                prev.map(s => (s.id === editingId ? { ...s, title: editingTitle.trim() } : s))
            );
        }
        setEditingId(null);
        setEditingTitle('');
    }, [editingId, editingTitle]);

    const handleCancelEdit = useCallback(() => {
        setEditingId(null);
        setEditingTitle('');
    }, []);

    // Drag and drop handlers
    const handleDragStart = useCallback((e: React.DragEvent, index: number) => {
        setDraggedIndex(index);
        e.dataTransfer.effectAllowed = 'move';
    }, []);

    const handleDragOver = useCallback((e: React.DragEvent, index: number) => {
        e.preventDefault();
        setDragOverIndex(index);
    }, []);

    const handleDragEnd = useCallback(() => {
        if (draggedIndex !== null && dragOverIndex !== null && draggedIndex !== dragOverIndex) {
            setSections(prev => {
                const newSections = [...prev];
                const [removed] = newSections.splice(draggedIndex, 1);
                newSections.splice(dragOverIndex, 0, removed);
                return newSections;
            });
        }
        setDraggedIndex(null);
        setDragOverIndex(null);
    }, [draggedIndex, dragOverIndex]);

    const handleApprove = useCallback(() => {
        onApprove(sections);
        onClose();
    }, [sections, onApprove, onClose]);

    const handleReject = useCallback(() => {
        onReject();
        onClose();
    }, [onReject, onClose]);

    return (
        <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
            <DialogContent className="sm:max-w-[600px] max-h-[80vh] flex flex-col">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Sparkles className="h-5 w-5 text-indigo-500" />
                        Aprovar Estrutura do Documento
                    </DialogTitle>
                    <DialogDescription>
                        Revise e edite o esqueleto proposto para <strong>{documentType}</strong>.
                        Arraste para reordenar, clique para editar.
                    </DialogDescription>
                </DialogHeader>

                <div className="flex-1 overflow-y-auto py-4 pr-2 -mr-2">
                    <div className="space-y-2">
                        {sections.map((section, index) => (
                            <div
                                key={section.id}
                                draggable={editingId !== section.id}
                                onDragStart={(e) => handleDragStart(e, index)}
                                onDragOver={(e) => handleDragOver(e, index)}
                                onDragEnd={handleDragEnd}
                                className={cn(
                                    'flex items-center gap-2 p-3 rounded-lg border bg-background transition-all',
                                    'hover:border-primary/50 hover:shadow-sm',
                                    draggedIndex === index && 'opacity-50 scale-95',
                                    dragOverIndex === index && draggedIndex !== index && 'border-primary border-dashed',
                                    editingId === section.id && 'ring-2 ring-primary/50'
                                )}
                            >
                                {/* Drag Handle */}
                                <div className="cursor-grab active:cursor-grabbing text-muted-foreground hover:text-foreground">
                                    <GripVertical className="h-4 w-4" />
                                </div>

                                {/* Section Number */}
                                <div className="flex-shrink-0 w-6 h-6 rounded-full bg-primary/10 text-primary text-xs font-bold flex items-center justify-center">
                                    {index + 1}
                                </div>

                                {/* Title */}
                                {editingId === section.id ? (
                                    <div className="flex-1 flex items-center gap-2">
                                        <Input
                                            value={editingTitle}
                                            onChange={(e) => setEditingTitle(e.target.value)}
                                            className="h-8 text-sm"
                                            autoFocus
                                            onKeyDown={(e) => {
                                                if (e.key === 'Enter') handleSaveEdit();
                                                if (e.key === 'Escape') handleCancelEdit();
                                            }}
                                        />
                                        <Button size="icon" variant="ghost" className="h-6 w-6" onClick={handleSaveEdit}>
                                            <Check className="h-3 w-3 text-green-500" />
                                        </Button>
                                        <Button size="icon" variant="ghost" className="h-6 w-6" onClick={handleCancelEdit}>
                                            <X className="h-3 w-3 text-red-500" />
                                        </Button>
                                    </div>
                                ) : (
                                    <div
                                        className="flex-1 text-sm font-medium cursor-pointer hover:text-primary"
                                        onClick={() => handleStartEdit(section)}
                                    >
                                        {section.title}
                                    </div>
                                )}

                                {/* Actions */}
                                {editingId !== section.id && (
                                    <div className="flex items-center gap-1">
                                        <Button
                                            size="icon"
                                            variant="ghost"
                                            className="h-6 w-6 text-muted-foreground hover:text-primary"
                                            onClick={() => handleStartEdit(section)}
                                        >
                                            <Edit3 className="h-3 w-3" />
                                        </Button>
                                        <Button
                                            size="icon"
                                            variant="ghost"
                                            className="h-6 w-6 text-muted-foreground hover:text-red-500"
                                            onClick={() => handleRemoveSection(section.id)}
                                            disabled={sections.length <= 1}
                                        >
                                            <Trash2 className="h-3 w-3" />
                                        </Button>
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>

                    {/* Add Section Button */}
                    <Button
                        variant="outline"
                        className="w-full mt-4 border-dashed"
                        onClick={handleAddSection}
                    >
                        <Plus className="h-4 w-4 mr-2" />
                        Adicionar Seção
                    </Button>
                </div>

                {/* Footer */}
                <DialogFooter className="gap-2 sm:gap-0">
                    <div className="flex items-center gap-2 text-xs text-muted-foreground mr-auto">
                        <FileText className="h-3 w-3" />
                        {sections.length} seções
                    </div>
                    <Button variant="outline" onClick={handleReject}>
                        <X className="h-4 w-4 mr-2" />
                        Cancelar
                    </Button>
                    <Button onClick={handleApprove} className="bg-primary">
                        <Check className="h-4 w-4 mr-2" />
                        Aprovar e Gerar
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

export default OutlineApprovalModal;
