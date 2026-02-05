'use client';

import * as React from 'react';
import { cn } from '@/lib/utils';
import { Progress } from '@/components/ui/progress';
import { Button } from '@/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  ShieldCheck,
  Clock,
  AlertTriangle,
  Filter,
  CheckCircle2,
} from 'lucide-react';
import type { VerificationStats as VerificationStatsType } from '@/types/review-table';

interface VerificationStatsProps {
  stats: VerificationStatsType | null;
  showVerifiedOnly: boolean;
  showLowConfidenceOnly: boolean;
  onToggleVerifiedOnly: () => void;
  onToggleLowConfidenceOnly: () => void;
  className?: string;
}

export function VerificationStats({
  stats,
  showVerifiedOnly,
  showLowConfidenceOnly,
  onToggleVerifiedOnly,
  onToggleLowConfidenceOnly,
  className,
}: VerificationStatsProps) {
  if (!stats) {
    return null;
  }

  const { total_cells, verified_cells, pending_cells, low_confidence_cells, verification_percentage } = stats;

  return (
    <div
      className={cn(
        'flex items-center gap-4 px-4 py-2 bg-muted/50 rounded-lg',
        className
      )}
    >
      {/* Progress bar */}
      <div className="flex items-center gap-3 flex-1 min-w-0">
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <div className="flex items-center gap-2 min-w-[120px]">
                <Progress
                  value={verification_percentage}
                  className="h-2 w-24"
                />
                <span className="text-sm font-medium whitespace-nowrap">
                  {Math.round(verification_percentage)}%
                </span>
              </div>
            </TooltipTrigger>
            <TooltipContent>
              <p>
                {verified_cells} de {total_cells} celulas verificadas
              </p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>

        <div className="h-4 w-px bg-border" />

        {/* Stats badges */}
        <div className="flex items-center gap-3">
          {/* Verified */}
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant={showVerifiedOnly ? 'secondary' : 'ghost'}
                  size="sm"
                  className={cn(
                    'h-7 gap-1.5 text-xs',
                    showVerifiedOnly && 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200'
                  )}
                  onClick={onToggleVerifiedOnly}
                >
                  <ShieldCheck className="h-3.5 w-3.5" />
                  <span>{verified_cells}</span>
                  <span className="text-muted-foreground hidden sm:inline">
                    verificadas
                  </span>
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                <p>
                  {showVerifiedOnly
                    ? 'Mostrar todas as celulas'
                    : 'Filtrar apenas celulas verificadas'}
                </p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>

          {/* Pending */}
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Clock className="h-3.5 w-3.5" />
                  <span>{pending_cells}</span>
                  <span className="hidden sm:inline">pendentes</span>
                </div>
              </TooltipTrigger>
              <TooltipContent>
                <p>{pending_cells} celulas aguardando verificacao</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>

          {/* Low confidence */}
          {low_confidence_cells > 0 && (
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant={showLowConfidenceOnly ? 'secondary' : 'ghost'}
                    size="sm"
                    className={cn(
                      'h-7 gap-1.5 text-xs',
                      showLowConfidenceOnly && 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200',
                      !showLowConfidenceOnly && 'text-yellow-600'
                    )}
                    onClick={onToggleLowConfidenceOnly}
                  >
                    <AlertTriangle className="h-3.5 w-3.5" />
                    <span>{low_confidence_cells}</span>
                    <span className="text-muted-foreground hidden sm:inline">
                      baixa confianca
                    </span>
                  </Button>
                </TooltipTrigger>
                <TooltipContent>
                  <p>
                    {showLowConfidenceOnly
                      ? 'Mostrar todas as celulas'
                      : 'Filtrar celulas com confianca abaixo de 50%'}
                  </p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          )}
        </div>
      </div>

      {/* Filter indicator */}
      {(showVerifiedOnly || showLowConfidenceOnly) && (
        <div className="flex items-center gap-1 text-xs text-primary">
          <Filter className="h-3.5 w-3.5" />
          <span>Filtro ativo</span>
        </div>
      )}
    </div>
  );
}

// Compact version for mobile or smaller spaces
export function VerificationStatsCompact({
  stats,
  className,
}: {
  stats: VerificationStatsType | null;
  className?: string;
}) {
  if (!stats) {
    return null;
  }

  const { verification_percentage, verified_cells, total_cells, low_confidence_cells } = stats;
  const isComplete = verification_percentage === 100;

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <div
            className={cn(
              'flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium',
              isComplete
                ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200'
                : 'bg-muted text-muted-foreground',
              className
            )}
          >
            {isComplete ? (
              <>
                <CheckCircle2 className="h-3.5 w-3.5" />
                <span>100% verificado</span>
              </>
            ) : (
              <>
                <ShieldCheck className="h-3.5 w-3.5" />
                <span>{Math.round(verification_percentage)}%</span>
                {low_confidence_cells > 0 && (
                  <>
                    <span className="text-muted-foreground/60">|</span>
                    <AlertTriangle className="h-3 w-3 text-yellow-600" />
                    <span className="text-yellow-600">{low_confidence_cells}</span>
                  </>
                )}
              </>
            )}
          </div>
        </TooltipTrigger>
        <TooltipContent>
          <div className="space-y-1">
            <p>
              {verified_cells} de {total_cells} celulas verificadas
            </p>
            {low_confidence_cells > 0 && (
              <p className="text-yellow-600">
                {low_confidence_cells} com baixa confianca
              </p>
            )}
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
