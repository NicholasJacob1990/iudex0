'use client';

import { useState } from 'react';
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
    DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
    Shield,
    ShieldAlert,
    ShieldCheck,
    Check,
    X,
    Eye,
    Wrench,
    ChevronDown,
    ChevronUp,
    Clock,
    AlertTriangle,
} from 'lucide-react';
import { cn } from '@/lib/utils';

export interface ToolApprovalModalProps {
    isOpen: boolean;
    onClose: () => void;
    tool: {
        name: string;
        input: Record<string, any>;
        riskLevel: 'low' | 'medium' | 'high';
        description?: string;
    };
    onApprove: (rememberChoice?: 'session' | 'always') => void;
    onDeny: (rememberChoice?: 'session' | 'always') => void;
}

// Mapeamento de nomes de tools para labels amigáveis
const TOOL_LABELS: Record<string, string> = {
    search_jurisprudencia: 'Pesquisa de Jurisprudência',
    search_legislacao: 'Pesquisa de Legislação',
    search_rag: 'Busca no RAG',
    search_templates: 'Busca de Templates',
    read_document: 'Leitura de Documento',
    edit_document: 'Edição de Documento',
    create_section: 'Criação de Seção',
    verify_citation: 'Verificação de Citação',
    find_citation_source: 'Busca de Fonte de Citação',
    bash: 'Comando de Terminal',
    file_write: 'Escrita de Arquivo',
    file_delete: 'Exclusão de Arquivo',
};

// Configurações visuais por nível de risco
const RISK_CONFIG = {
    low: {
        label: 'Baixo',
        icon: ShieldCheck,
        badgeClass: 'bg-green-100 text-green-700 border-green-200',
        iconClass: 'text-green-600',
        bgClass: 'bg-green-50',
        borderClass: 'border-green-200',
    },
    medium: {
        label: 'Médio',
        icon: Shield,
        badgeClass: 'bg-amber-100 text-amber-700 border-amber-200',
        iconClass: 'text-amber-600',
        bgClass: 'bg-amber-50',
        borderClass: 'border-amber-200',
    },
    high: {
        label: 'Alto',
        icon: ShieldAlert,
        badgeClass: 'bg-red-100 text-red-700 border-red-200',
        iconClass: 'text-red-600',
        bgClass: 'bg-red-50',
        borderClass: 'border-red-200',
    },
};

// Descrições padrão de tools se não fornecida
const TOOL_DESCRIPTIONS: Record<string, string> = {
    search_jurisprudencia: 'Pesquisa decisões judiciais em bases de dados de tribunais.',
    search_legislacao: 'Consulta leis, códigos e normas em bases legislativas.',
    search_rag: 'Busca informações nos documentos do caso carregados no sistema.',
    search_templates: 'Procura modelos e templates de peças jurídicas.',
    read_document: 'Lê o conteúdo de um documento específico.',
    edit_document: 'Modifica o conteúdo de uma seção do documento.',
    create_section: 'Cria uma nova seção no documento sendo elaborado.',
    verify_citation: 'Verifica se uma citação jurisprudencial é válida e correta.',
    find_citation_source: 'Localiza a fonte original de uma citação.',
    bash: 'Executa comandos no terminal do sistema operacional.',
    file_write: 'Escreve dados em um arquivo no sistema de arquivos.',
    file_delete: 'Remove permanentemente um arquivo do sistema.',
};

export function ToolApprovalModal({
    isOpen,
    onClose,
    tool,
    onApprove,
    onDeny,
}: ToolApprovalModalProps) {
    const [showInputDetails, setShowInputDetails] = useState(true);
    const [showRememberOptions, setShowRememberOptions] = useState(false);
    const [pendingAction, setPendingAction] = useState<'approve' | 'deny' | null>(null);

    const riskConfig = RISK_CONFIG[tool.riskLevel];
    const RiskIcon = riskConfig.icon;
    const toolLabel = TOOL_LABELS[tool.name] || tool.name;
    const toolDescription = tool.description || TOOL_DESCRIPTIONS[tool.name] || 'Executa uma operação no sistema.';

    const handleApprove = () => {
        if (tool.riskLevel === 'high') {
            setShowRememberOptions(true);
            setPendingAction('approve');
        } else {
            onApprove();
        }
    };

    const handleDeny = () => {
        setShowRememberOptions(true);
        setPendingAction('deny');
    };

    const handleConfirmWithRemember = (remember?: 'session' | 'always') => {
        if (pendingAction === 'approve') {
            onApprove(remember);
        } else if (pendingAction === 'deny') {
            onDeny(remember);
        }
        setShowRememberOptions(false);
        setPendingAction(null);
    };

    const handleCancelRemember = () => {
        setShowRememberOptions(false);
        setPendingAction(null);
    };

    // Formata o valor do input para exibição
    const formatInputValue = (value: any): string => {
        if (typeof value === 'string') return value;
        if (typeof value === 'number' || typeof value === 'boolean') return String(value);
        return JSON.stringify(value, null, 2);
    };

    // Preview do que a tool vai fazer
    const getPreviewText = (): string | null => {
        const { name, input } = tool;

        if (name.startsWith('search_')) {
            return `Buscar: "${input.query || input.q || Object.values(input)[0] || ''}"`;
        }
        if (name === 'edit_document' || name === 'create_section') {
            const section = input.section || input.title || input.name || '';
            return `Seção: ${section}`;
        }
        if (name === 'read_document') {
            return `Documento: ${input.path || input.id || input.name || ''}`;
        }
        if (name === 'verify_citation' || name === 'find_citation_source') {
            return `Citação: "${(input.citation || input.text || '').slice(0, 100)}..."`;
        }
        if (name === 'bash') {
            return `Comando: ${input.command || input.cmd || ''}`;
        }
        if (name === 'file_write' || name === 'file_delete') {
            return `Arquivo: ${input.path || input.file || ''}`;
        }

        return null;
    };

    const preview = getPreviewText();

    return (
        <Dialog open={isOpen} onOpenChange={onClose}>
            <DialogContent className="max-w-xl">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-3">
                        <div className={cn(
                            'p-2 rounded-lg',
                            riskConfig.bgClass,
                            riskConfig.borderClass,
                            'border'
                        )}>
                            <Wrench className={cn('h-5 w-5', riskConfig.iconClass)} />
                        </div>
                        <div className="flex-1">
                            <div className="flex items-center gap-2">
                                <span>Aprovação de Tool</span>
                                <Badge className={cn('text-[10px]', riskConfig.badgeClass)}>
                                    <RiskIcon className="h-3 w-3 mr-1" />
                                    Risco {riskConfig.label}
                                </Badge>
                            </div>
                        </div>
                    </DialogTitle>
                    <DialogDescription className="text-left">
                        O agente Claude deseja executar uma operação que requer sua aprovação.
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-4 py-4">
                    {/* Tool Info */}
                    <div className={cn(
                        'rounded-lg border p-4',
                        riskConfig.bgClass,
                        riskConfig.borderClass
                    )}>
                        <div className="flex items-start justify-between">
                            <div>
                                <h4 className="font-semibold text-sm">{toolLabel}</h4>
                                <p className="text-xs text-muted-foreground mt-1">{toolDescription}</p>
                            </div>
                            <code className="text-[10px] bg-muted px-1.5 py-0.5 rounded font-mono">
                                {tool.name}
                            </code>
                        </div>
                    </div>

                    {/* Preview (se disponível) */}
                    {preview && (
                        <div className="flex items-center gap-2 text-sm bg-muted/50 rounded-lg p-3 border">
                            <Eye className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                            <span className="text-muted-foreground">Preview:</span>
                            <span className="font-medium truncate">{preview}</span>
                        </div>
                    )}

                    {/* Input Parameters */}
                    <div className="border rounded-lg overflow-hidden">
                        <button
                            onClick={() => setShowInputDetails(!showInputDetails)}
                            className="w-full flex items-center justify-between p-3 bg-muted/30 hover:bg-muted/50 transition-colors"
                        >
                            <span className="text-sm font-medium flex items-center gap-2">
                                <Clock className="h-4 w-4 text-muted-foreground" />
                                Parâmetros de Entrada
                            </span>
                            {showInputDetails ? (
                                <ChevronUp className="h-4 w-4 text-muted-foreground" />
                            ) : (
                                <ChevronDown className="h-4 w-4 text-muted-foreground" />
                            )}
                        </button>

                        {showInputDetails && (
                            <div className="p-3 bg-background">
                                {Object.keys(tool.input).length === 0 ? (
                                    <p className="text-xs text-muted-foreground italic">
                                        Nenhum parâmetro fornecido
                                    </p>
                                ) : (
                                    <div className="space-y-2">
                                        {Object.entries(tool.input).map(([key, value]) => (
                                            <div key={key} className="text-xs">
                                                <span className="font-mono text-muted-foreground">{key}:</span>
                                                <pre className="mt-1 bg-muted/50 p-2 rounded overflow-x-auto whitespace-pre-wrap break-all">
                                                    {formatInputValue(value)}
                                                </pre>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>
                        )}
                    </div>

                    {/* High Risk Warning */}
                    {tool.riskLevel === 'high' && (
                        <div className="flex items-start gap-3 p-3 bg-red-50 border border-red-200 rounded-lg">
                            <AlertTriangle className="h-5 w-5 text-red-600 flex-shrink-0 mt-0.5" />
                            <div className="text-xs text-red-800">
                                <p className="font-semibold">Atenção: Operação de Alto Risco</p>
                                <p className="mt-1">
                                    Esta operação pode modificar arquivos ou executar comandos no sistema.
                                    Revise cuidadosamente antes de aprovar.
                                </p>
                            </div>
                        </div>
                    )}

                    {/* Remember Options */}
                    {showRememberOptions && (
                        <div className="border rounded-lg p-4 bg-muted/30 space-y-3">
                            <p className="text-sm font-medium">
                                {pendingAction === 'approve' ? 'Aprovar' : 'Negar'} esta tool:
                            </p>
                            <div className="grid grid-cols-1 gap-2">
                                <Button
                                    variant="outline"
                                    size="sm"
                                    className="justify-start"
                                    onClick={() => handleConfirmWithRemember()}
                                >
                                    <Check className="mr-2 h-4 w-4" />
                                    Apenas desta vez
                                </Button>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    className="justify-start"
                                    onClick={() => handleConfirmWithRemember('session')}
                                >
                                    <Clock className="mr-2 h-4 w-4" />
                                    Para esta sessão
                                </Button>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    className="justify-start"
                                    onClick={() => handleConfirmWithRemember('always')}
                                >
                                    <Shield className="mr-2 h-4 w-4" />
                                    Sempre (lembrar escolha)
                                </Button>
                            </div>
                            <Button
                                variant="ghost"
                                size="sm"
                                onClick={handleCancelRemember}
                                className="w-full"
                            >
                                Cancelar
                            </Button>
                        </div>
                    )}
                </div>

                {!showRememberOptions && (
                    <DialogFooter className="gap-2 sm:gap-0">
                        <div className="flex items-center gap-2 w-full sm:w-auto">
                            <Button
                                variant="destructive"
                                onClick={handleDeny}
                                className="flex-1 sm:flex-none"
                            >
                                <X className="mr-2 h-4 w-4" />
                                Negar
                            </Button>
                            <Button
                                variant="outline"
                                onClick={() => onDeny('always')}
                                className="flex-1 sm:flex-none text-xs"
                            >
                                Sempre Negar
                            </Button>
                        </div>
                        <div className="flex items-center gap-2 w-full sm:w-auto">
                            <Button
                                variant="outline"
                                onClick={() => onApprove('always')}
                                className="flex-1 sm:flex-none text-xs"
                            >
                                Sempre Permitir
                            </Button>
                            <Button
                                className={cn(
                                    'flex-1 sm:flex-none',
                                    tool.riskLevel === 'low' && 'bg-green-600 hover:bg-green-700',
                                    tool.riskLevel === 'medium' && 'bg-amber-600 hover:bg-amber-700',
                                    tool.riskLevel === 'high' && 'bg-red-600 hover:bg-red-700'
                                )}
                                onClick={handleApprove}
                            >
                                <Check className="mr-2 h-4 w-4" />
                                Aprovar
                            </Button>
                        </div>
                    </DialogFooter>
                )}
            </DialogContent>
        </Dialog>
    );
}
