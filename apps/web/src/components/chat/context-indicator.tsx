'use client';

import * as React from 'react';
import { Loader2, Minimize2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';

export interface ContextIndicatorProps {
  usagePercent: number;
  tokensUsed: number;
  tokenLimit: number;
  onCompact?: () => void;
  isCompacting?: boolean;
}

/**
 * Formata números grandes com separador de milhar
 */
function formatNumber(num: number): string {
  return num.toLocaleString('pt-BR');
}

/**
 * Retorna a cor baseada na porcentagem de uso
 * - Verde: < 50%
 * - Amarelo: 50-70%
 * - Vermelho: > 70%
 */
function getColorClasses(percent: number): {
  bar: string;
  text: string;
  bg: string;
} {
  if (percent < 50) {
    return {
      bar: 'bg-emerald-500',
      text: 'text-emerald-600',
      bg: 'bg-emerald-100',
    };
  }
  if (percent <= 70) {
    return {
      bar: 'bg-amber-500',
      text: 'text-amber-600',
      bg: 'bg-amber-100',
    };
  }
  return {
    bar: 'bg-red-500',
    text: 'text-red-600',
    bg: 'bg-red-100',
  };
}

export function ContextIndicator({
  usagePercent,
  tokensUsed,
  tokenLimit,
  onCompact,
  isCompacting = false,
}: ContextIndicatorProps) {
  // Clamp percent entre 0 e 100
  const clampedPercent = Math.min(100, Math.max(0, usagePercent));
  const colors = getColorClasses(clampedPercent);
  const showCompactButton = clampedPercent > 60 && onCompact;

  return (
    <TooltipProvider>
      <div className="flex items-center gap-2 px-3 py-2 rounded-lg border border-slate-200 bg-white shadow-sm">
        {/* Label com porcentagem */}
        <Tooltip>
          <TooltipTrigger asChild>
            <div className="flex items-center gap-2 cursor-help">
              <span className="text-xs font-medium text-slate-600">
                Contexto:
              </span>
              <span className={cn('text-xs font-bold', colors.text)}>
                {clampedPercent.toFixed(0)}%
              </span>
            </div>
          </TooltipTrigger>
          <TooltipContent side="bottom" className="max-w-xs">
            <div className="text-xs space-y-1">
              <p className="font-medium">Uso da janela de contexto</p>
              <p>
                <span className="font-semibold">{formatNumber(tokensUsed)}</span>
                {' / '}
                <span className="text-muted-foreground">{formatNumber(tokenLimit)} tokens</span>
              </p>
              {clampedPercent > 70 && (
                <p className="text-red-500 font-medium">
                  Atenção: Contexto quase cheio! Considere compactar.
                </p>
              )}
              {clampedPercent > 50 && clampedPercent <= 70 && (
                <p className="text-amber-500">
                  Uso moderado. Compactação disponível.
                </p>
              )}
            </div>
          </TooltipContent>
        </Tooltip>

        {/* Barra de progresso customizada */}
        <div className="relative flex-1 min-w-[80px] max-w-[120px]">
          <div
            className={cn(
              'h-2 w-full overflow-hidden rounded-full',
              colors.bg
            )}
          >
            <div
              className={cn(
                'h-full rounded-full transition-all duration-500 ease-out',
                colors.bar
              )}
              style={{ width: `${clampedPercent}%` }}
            />
          </div>
        </div>

        {/* Botao de compactar */}
        {showCompactButton && (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="outline"
                size="sm"
                onClick={onCompact}
                disabled={isCompacting}
                className={cn(
                  'h-7 px-2 text-xs font-medium gap-1',
                  'border-slate-200 hover:bg-slate-100',
                  'transition-all duration-200'
                )}
              >
                {isCompacting ? (
                  <>
                    <Loader2 className="h-3 w-3 animate-spin" />
                    <span className="hidden sm:inline">Compactando...</span>
                  </>
                ) : (
                  <>
                    <Minimize2 className="h-3 w-3" />
                    <span className="hidden sm:inline">Compactar</span>
                  </>
                )}
              </Button>
            </TooltipTrigger>
            <TooltipContent side="bottom">
              <p className="text-xs">
                Resumir mensagens antigas para liberar espaco no contexto
              </p>
            </TooltipContent>
          </Tooltip>
        )}
      </div>
    </TooltipProvider>
  );
}

/**
 * Versao compacta para uso inline (ex: no header)
 */
export function ContextIndicatorCompact({
  usagePercent,
  tokensUsed,
  tokenLimit,
}: Pick<ContextIndicatorProps, 'usagePercent' | 'tokensUsed' | 'tokenLimit'>) {
  const clampedPercent = Math.min(100, Math.max(0, usagePercent));
  const colors = getColorClasses(clampedPercent);

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <div
            className={cn(
              'inline-flex h-8 w-8 items-center justify-center',
              'rounded-full ring-1 ring-slate-200 cursor-help',
              'text-[11px] font-bold transition-colors',
              colors.bg,
              colors.text
            )}
            aria-label={`Uso do contexto: ${clampedPercent.toFixed(0)}%`}
          >
            {clampedPercent.toFixed(0)}
          </div>
        </TooltipTrigger>
        <TooltipContent side="bottom">
          <div className="text-xs space-y-1">
            <p className="font-medium">Janela de contexto</p>
            <p>
              <span className="font-semibold">{formatNumber(tokensUsed)}</span>
              {' / '}
              <span className="text-muted-foreground">{formatNumber(tokenLimit)} tokens</span>
            </p>
            <p>({clampedPercent.toFixed(1)}% utilizado)</p>
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
