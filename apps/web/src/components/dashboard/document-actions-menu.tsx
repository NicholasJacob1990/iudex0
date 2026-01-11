'use client';

import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { Button } from '@/components/ui/button';
import { MoreVertical, TrendingUp, Clock, AlertCircle, Lightbulb } from 'lucide-react';
import { toast } from 'sonner';

interface DocumentActionsMenuProps {
    documentId: string;
    documentName: string;
}

export function DocumentActionsMenu({ documentId, documentName }: DocumentActionsMenuProps) {
    const handleAction = (action: string) => {
        toast.info(`Executando: ${action} em "${documentName}"`);
        // TODO: Implement actual actions
        setTimeout(() => {
            toast.success(`${action} concluído!`);
        }, 1500);
    };

    return (
        <DropdownMenu>
            <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" className="rounded-full">
                    <MoreVertical className="h-4 w-4" />
                </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56">
                <DropdownMenuItem onClick={() => handleAction('Identificar pontos controvertidos')}>
                    <AlertCircle className="mr-2 h-4 w-4 text-orange-500" />
                    <span>Pontos Controvertidos</span>
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => handleAction('Criar linha do tempo')}>
                    <Clock className="mr-2 h-4 w-4 text-blue-500" />
                    <span>Linha do Tempo</span>
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => handleAction('Identificar próximos passos')}>
                    <TrendingUp className="mr-2 h-4 w-4 text-green-500" />
                    <span>Próximos Passos</span>
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => handleAction('Sugerir estratégias')}>
                    <Lightbulb className="mr-2 h-4 w-4 text-yellow-500" />
                    <span>Sugerir Estratégias</span>
                </DropdownMenuItem>
            </DropdownMenuContent>
        </DropdownMenu>
    );
}
