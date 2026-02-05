/**
 * Exemplo de uso do componente AskModeToggle
 *
 * Este arquivo demonstra como usar o toggle de modo de consulta
 */

'use client';

import { useState } from 'react';
import { AskModeToggle, type QueryMode } from './ask-mode-toggle';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

export function AskModeToggleExample() {
  const [mode, setMode] = useState<QueryMode>('auto');

  const handleModeChange = (newMode: QueryMode) => {
    console.log('Modo alterado para:', newMode);
    setMode(newMode);
  };

  const getModeDescription = () => {
    switch (mode) {
      case 'auto':
        return 'O Claude decidirá automaticamente se deve editar o documento ou apenas responder com análise.';
      case 'edit':
        return 'O Claude editará diretamente o documento no canvas conforme sua solicitação.';
      case 'answer':
        return 'O Claude responderá com análise e sugestões, mas não fará edições diretas no documento.';
      default:
        return '';
    }
  };

  return (
    <div className="flex flex-col gap-6 p-8 max-w-2xl mx-auto">
      <Card>
        <CardHeader>
          <CardTitle>Modo de Consulta</CardTitle>
          <CardDescription>
            Selecione como o Claude deve processar suas solicitações
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <AskModeToggle mode={mode} onChange={handleModeChange} />

          <div className="rounded-lg bg-muted p-4">
            <p className="text-sm font-medium mb-1">Modo atual: {mode}</p>
            <p className="text-sm text-muted-foreground">
              {getModeDescription()}
            </p>
          </div>
        </CardContent>
      </Card>

      <div className="text-xs text-muted-foreground space-y-2">
        <p><strong>Dica:</strong> Use o modo Automático para deixar o Claude decidir a melhor abordagem.</p>
        <p><strong>Responsivo:</strong> Em telas pequenas, apenas os ícones são exibidos. Passe o mouse sobre cada opção para ver a descrição completa.</p>
      </div>
    </div>
  );
}
