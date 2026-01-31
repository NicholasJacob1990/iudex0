"use client";

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Plus, Search, FolderOpen, MoreVertical, Archive, ArrowRight } from 'lucide-react';
import apiClient from '@/lib/api-client';
import { toast } from 'sonner';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from "@/components/ui/dialog"
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Badge } from '@/components/ui/badge';
import { AnimatedContainer, StaggerContainer } from '@/components/ui/animated-container';
import { MotionDiv, fadeUp } from '@/components/ui/motion';

interface Case {
    id: string;
    title: string;
    client_name?: string;
    process_number?: string;
    status: string;
    updated_at: string;
}

export default function CasesPage() {
    const router = useRouter();
    const [cases, setCases] = useState<Case[]>([]);
    const [loading, setLoading] = useState(true);
    const [searchTerm, setSearchTerm] = useState('');
    const [isCreateOpen, setIsCreateOpen] = useState(false);

    // Form state
    const [newCaseData, setNewCaseData] = useState({
        title: '',
        client_name: '',
        process_number: '',
        area: ''
    });

    const fetchCases = async () => {
        try {
            setLoading(true);
            const data = await apiClient.getCases();
            setCases(data);
        } catch (error) {
            console.error(error);
            toast.error("Erro ao carregar casos");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchCases();
    }, []);

    const handleCreateCase = async () => {
        if (!newCaseData.title) {
            toast.error("O título é obrigatório");
            return;
        }

        try {
            await apiClient.createCase(newCaseData);
            toast.success("Caso criado com sucesso!");
            setIsCreateOpen(false);
            setNewCaseData({ title: '', client_name: '', process_number: '', area: '' });
            fetchCases();
        } catch (error) {
            console.error(error);
            toast.error("Erro ao criar caso");
        }
    };

    const handleDeleteCase = async (id: string, e: React.MouseEvent) => {
        e.stopPropagation();
        if (confirm("Tem certeza que deseja arquivar este caso?")) {
            try {
                await apiClient.deleteCase(id);
                toast.success("Caso arquivado.");
                fetchCases();
            } catch (error) {
                toast.error("Erro ao arquivar caso.");
            }
        }
    };

    const filteredCases = cases.filter(c =>
        c.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
        c.client_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        c.process_number?.includes(searchTerm)
    );

    return (
        <div className="container py-8 space-y-6 max-w-7xl mx-auto">
            <AnimatedContainer>
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight">Gestão de Casos</h1>
                    <p className="text-muted-foreground mt-1">
                        Gerencie seus processos, clientes e documentos.
                    </p>
                </div>

                <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
                    <DialogTrigger asChild>
                        <Button className="rounded-xl">
                            <Plus className="mr-2 h-4 w-4" />
                            Novo Caso
                        </Button>
                    </DialogTrigger>
                    <DialogContent className="sm:max-w-[425px]">
                        <DialogHeader>
                            <DialogTitle>Criar Novo Caso</DialogTitle>
                            <DialogDescription>
                                Preencha as informações básicas para iniciar um novo dossiê.
                            </DialogDescription>
                        </DialogHeader>
                        <div className="grid gap-4 py-4">
                            <div className="space-y-2">
                                <Label htmlFor="title">Título do Caso / Referência *</Label>
                                <Input
                                    id="title"
                                    placeholder="Ex: Ação de Cobrança - Silva vs Souza"
                                    value={newCaseData.title}
                                    onChange={(e) => setNewCaseData({ ...newCaseData, title: e.target.value })}
                                />
                            </div>
                            <div className="space-y-2">
                                <Label htmlFor="client">Nome do Cliente</Label>
                                <Input
                                    id="client"
                                    placeholder="Ex: João da Silva"
                                    value={newCaseData.client_name}
                                    onChange={(e) => setNewCaseData({ ...newCaseData, client_name: e.target.value })}
                                />
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <div className="space-y-2">
                                    <Label htmlFor="process">Nº Processo</Label>
                                    <Input
                                        id="process"
                                        placeholder="0000000-00.2024.8.26.0000"
                                        value={newCaseData.process_number}
                                        onChange={(e) => setNewCaseData({ ...newCaseData, process_number: e.target.value })}
                                    />
                                </div>
                                <div className="space-y-2">
                                    <Label htmlFor="area">Área</Label>
                                    <Input
                                        id="area"
                                        placeholder="Ex: Cível"
                                        value={newCaseData.area}
                                        onChange={(e) => setNewCaseData({ ...newCaseData, area: e.target.value })}
                                    />
                                </div>
                            </div>
                        </div>
                        <DialogFooter>
                            <Button variant="outline" onClick={() => setIsCreateOpen(false)}>Cancelar</Button>
                            <Button onClick={handleCreateCase}>Criar Caso</Button>
                        </DialogFooter>
                    </DialogContent>
                </Dialog>
            </div>
            </AnimatedContainer>

            {/* Search & Filters */}
            <div className="flex items-center gap-4">
                <div className="relative flex-1 max-w-md">
                    <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                    <Input
                        placeholder="Buscar por título, cliente ou processo..."
                        className="pl-9 bg-white"
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                    />
                </div>
            </div>

            {/* Cases Grid */}
            {loading ? (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {[1, 2, 3].map(i => (
                        <Card key={i} className="h-[200px] animate-pulse bg-muted/50" />
                    ))}
                </div>
            ) : filteredCases.length === 0 ? (
                <div className="flex flex-col items-center justify-center p-12 border-2 border-dashed rounded-xl border-muted bg-muted/10">
                    <FolderOpen className="h-12 w-12 text-muted-foreground mb-4" />
                    <h3 className="text-lg font-medium">Nenhum caso encontrado</h3>
                    <p className="text-sm text-muted-foreground mb-4 text-center max-w-sm">
                        Crie seu primeiro caso para começar a organizar seus documentos e gerar peças com IA.
                    </p>
                    <Button onClick={() => setIsCreateOpen(true)} variant="outline">Criar Caso</Button>
                </div>
            ) : (
                <StaggerContainer className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {filteredCases.map((c) => (
                        <MotionDiv key={c.id} variants={fadeUp}>
                        <Card
                            className="group relative cursor-pointer hover:shadow-md transition-all border-outline/40 hover:border-primary/50 bg-white card-premium glow-hover"
                            onClick={() => router.push(`/cases/${c.id}`)}
                        >
                            <CardHeader className="pb-3">
                                <div className="flex justify-between items-start">
                                    <div className="space-y-1">
                                        <CardTitle className="text-base font-semibold leading-snug line-clamp-2">
                                            {c.title}
                                        </CardTitle>
                                        <CardDescription className="text-xs">
                                            Atualizado em {new Date(c.updated_at).toLocaleDateString()}
                                        </CardDescription>
                                    </div>
                                    <DropdownMenu>
                                        <DropdownMenuTrigger asChild>
                                            <Button variant="ghost" className="h-8 w-8 p-0" onClick={e => e.stopPropagation()}>
                                                <MoreVertical className="h-4 w-4 text-muted-foreground" />
                                            </Button>
                                        </DropdownMenuTrigger>
                                        <DropdownMenuContent align="end">
                                            <DropdownMenuItem onClick={(e) => handleDeleteCase(c.id, e)} className="text-red-600 focus:text-red-600">
                                                <Archive className="mr-2 h-4 w-4" />
                                                Arquivar
                                            </DropdownMenuItem>
                                        </DropdownMenuContent>
                                    </DropdownMenu>
                                </div>
                            </CardHeader>
                            <CardContent>
                                <div className="space-y-3">
                                    <div className="flex items-center justify-between text-sm">
                                        <span className="text-muted-foreground text-xs">Cliente</span>
                                        <span className="font-medium truncate max-w-[150px]">{c.client_name || '-'}</span>
                                    </div>
                                    <div className="flex items-center justify-between text-sm">
                                        <span className="text-muted-foreground text-xs">Processo</span>
                                        <Badge variant="secondary" className="font-mono text-[10px] font-normal">
                                            {c.process_number || 'Sem número'}
                                        </Badge>
                                    </div>

                                    <div className="pt-4 flex justify-end">
                                        <Button size="sm" variant="ghost" className="text-xs group-hover:bg-primary/5 group-hover:text-primary transition-colors">
                                            Abrir Dossuiê
                                            <ArrowRight className="ml-2 h-3 w-3" />
                                        </Button>
                                    </div>
                                </div>
                            </CardContent>
                        </Card>
                        </MotionDiv>
                    ))}
                </StaggerContainer>
            )}
        </div>
    );
}
