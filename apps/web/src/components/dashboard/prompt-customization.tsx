'use client';

import { useState, useEffect } from 'react';
import { Plus, Edit2, Trash2, FileText, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { cn } from '@/lib/utils';
import type { PromptCategory } from '@/data/prompts';

export interface CustomPrompt {
    id: string;
    name: string;
    category: PromptCategory;
    description: string;
    template: string;
    isCustom: true;
}

const CATEGORIES: PromptCategory[] = [
    'Peças Processuais',
    'Recursos',
    'Ações Especiais',
    'Peças Complementares',
    'Sentenças',
    'Contratos',
];

export function PromptCustomization() {
    const [customPrompts, setCustomPrompts] = useState<CustomPrompt[]>([]);
    const [isDialogOpen, setIsDialogOpen] = useState(false);
    const [editingPrompt, setEditingPrompt] = useState<CustomPrompt | null>(null);
    const [formData, setFormData] = useState({
        name: '',
        category: 'Peças Processuais' as PromptCategory,
        description: '',
        template: '',
    });

    // Load custom prompts from localStorage on mount
    useEffect(() => {
        const stored = localStorage.getItem('iudex_custom_prompts');
        if (stored) {
            try {
                setCustomPrompts(JSON.parse(stored));
            } catch (e) {
                console.error('Failed to load custom prompts:', e);
            }
        }
    }, []);

    // Save custom prompts to localStorage whenever they change
    useEffect(() => {
        localStorage.setItem('iudex_custom_prompts', JSON.stringify(customPrompts));
    }, [customPrompts]);

    const handleOpenDialog = (prompt?: CustomPrompt) => {
        if (prompt) {
            setEditingPrompt(prompt);
            setFormData({
                name: prompt.name,
                category: prompt.category,
                description: prompt.description,
                template: prompt.template,
            });
        } else {
            setEditingPrompt(null);
            setFormData({
                name: '',
                category: 'Peças Processuais',
                description: '',
                template: '',
            });
        }
        setIsDialogOpen(true);
    };

    const handleCloseDialog = () => {
        setIsDialogOpen(false);
        setEditingPrompt(null);
        setFormData({
            name: '',
            category: 'Peças Processuais',
            description: '',
            template: '',
        });
    };

    const handleSave = () => {
        if (!formData.name || !formData.template) return;

        if (editingPrompt) {
            // Update existing prompt
            setCustomPrompts((prev) =>
                prev.map((p) =>
                    p.id === editingPrompt.id
                        ? { ...p, ...formData }
                        : p
                )
            );
        } else {
            // Create new prompt
            const newPrompt: CustomPrompt = {
                id: `custom_${Date.now()}`,
                ...formData,
                isCustom: true,
            };
            setCustomPrompts((prev) => [...prev, newPrompt]);
        }

        handleCloseDialog();
    };

    const handleDelete = (id: string) => {
        if (confirm('Tem certeza que deseja deletar este prompt personalizado?')) {
            setCustomPrompts((prev) => prev.filter((p) => p.id !== id));
        }
    };

    return (
        <div className="p-6">
            <div className="mb-6 flex items-center justify-between">
                <div>
                    <h2 className="text-2xl font-display font-semibold text-foreground">
                        Prompts Personalizados
                    </h2>
                    <p className="mt-1 text-sm text-muted-foreground">
                        Crie e gerencie seus próprios templates de documentos jurídicos
                    </p>
                </div>
                <Button onClick={() => handleOpenDialog()} className="gap-2">
                    <Plus className="h-4 w-4" />
                    Novo Prompt
                </Button>
            </div>

            {customPrompts.length === 0 ? (
                <div className="rounded-lg border border-dashed border-border bg-muted/50 p-12 text-center">
                    <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-muted">
                        <FileText className="h-8 w-8 text-muted-foreground" />
                    </div>
                    <h3 className="mb-2 text-lg font-medium text-foreground">
                        Nenhum prompt personalizado
                    </h3>
                    <p className="mb-4 text-sm text-muted-foreground">
                        Crie seu primeiro template personalizado para agilizar seu trabalho
                    </p>
                    <Button onClick={() => handleOpenDialog()} variant="outline" className="gap-2">
                        <Plus className="h-4 w-4" />
                        Criar Primeiro Prompt
                    </Button>
                </div>
            ) : (
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                    {customPrompts.map((prompt) => (
                        <div
                            key={prompt.id}
                            className="group relative rounded-lg border border-border bg-background p-4 transition-all hover:shadow-md"
                        >
                            <div className="mb-3">
                                <div className="mb-1 inline-block rounded-md bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
                                    {prompt.category}
                                </div>
                                <h3 className="text-lg font-medium text-foreground">{prompt.name}</h3>
                                <p className="mt-1 text-sm text-muted-foreground line-clamp-2">
                                    {prompt.description}
                                </p>
                            </div>
                            <div className="flex items-center gap-2">
                                <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => handleOpenDialog(prompt)}
                                    className="flex-1 gap-2"
                                >
                                    <Edit2 className="h-3 w-3" />
                                    Editar
                                </Button>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => handleDelete(prompt.id)}
                                    className="gap-2 text-destructive hover:bg-destructive hover:text-destructive-foreground"
                                >
                                    <Trash2 className="h-3 w-3" />
                                </Button>
                            </div>
                        </div>
                    ))}
                </div>
            )}

            {/* Create/Edit Dialog */}
            <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
                <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
                    <DialogHeader>
                        <DialogTitle>
                            {editingPrompt ? 'Editar Prompt' : 'Novo Prompt Personalizado'}
                        </DialogTitle>
                    </DialogHeader>

                    <div className="space-y-4 py-4">
                        <div className="grid gap-4">
                            <div className="grid gap-2">
                                <Label htmlFor="name">Nome do Prompt *</Label>
                                <Input
                                    id="name"
                                    value={formData.name}
                                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                                    placeholder="Ex: Petição de Usucapião"
                                />
                            </div>

                            <div className="grid gap-2">
                                <Label htmlFor="category">Categoria *</Label>
                                <select
                                    id="category"
                                    value={formData.category}
                                    onChange={(e) =>
                                        setFormData({ ...formData, category: e.target.value as PromptCategory })
                                    }
                                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                                >
                                    {CATEGORIES.map((cat) => (
                                        <option key={cat} value={cat}>
                                            {cat}
                                        </option>
                                    ))}
                                </select>
                            </div>

                            <div className="grid gap-2">
                                <Label htmlFor="description">Descrição</Label>
                                <Input
                                    id="description"
                                    value={formData.description}
                                    onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                                    placeholder="Breve descrição do que este prompt faz"
                                />
                            </div>

                            <div className="grid gap-2">
                                <Label htmlFor="template">Template *</Label>
                                <textarea
                                    id="template"
                                    value={formData.template}
                                    onChange={(e) => setFormData({ ...formData, template: e.target.value })}
                                    placeholder="Digite o template do prompt aqui...

Exemplo:
Elabore uma petição de usucapião contendo:

1. Qualificação das partes
2. Dos fatos: narrativa da posse mansa e pacífica
3. Do direito: fundamentação legal
..."
                                    className="flex min-h-[300px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 resize-y"
                                    rows={12}
                                />
                                <p className="text-xs text-muted-foreground">
                                    Este texto será inserido quando você selecionar este prompt usando &quot;/&quot;
                                </p>
                            </div>
                        </div>
                    </div>

                    <DialogFooter>
                        <Button variant="outline" onClick={handleCloseDialog}>
                            Cancelar
                        </Button>
                        <Button
                            onClick={handleSave}
                            disabled={!formData.name || !formData.template}
                        >
                            {editingPrompt ? 'Salvar Alterações' : 'Criar Prompt'}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}
