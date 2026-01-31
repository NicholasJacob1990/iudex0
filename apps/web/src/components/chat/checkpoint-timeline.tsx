'use client';

import { Clock, RotateCcw, GitBranch } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

interface Checkpoint {
  id: string;
  description: string;
  createdAt: string;
  node_name?: string;
}

interface CheckpointTimelineProps {
  checkpoints: Checkpoint[];
  onRestore: (checkpointId: string) => void;
  className?: string;
}

export function CheckpointTimeline({
  checkpoints,
  onRestore,
  className,
}: CheckpointTimelineProps) {
  if (!checkpoints.length) return null;

  return (
    <div className={cn('space-y-3 p-4', className)}>
      <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
        <GitBranch className="h-4 w-4" />
        <span>Checkpoints</span>
      </div>
      <div className="relative space-y-4 pl-6 before:absolute before:left-2 before:top-0 before:h-full before:w-px before:bg-border">
        {checkpoints.map((cp) => (
          <div key={cp.id} className="relative">
            <div className="absolute -left-[18px] top-1 h-2.5 w-2.5 rounded-full bg-primary" />
            <div className="flex items-start justify-between gap-2">
              <div className="space-y-1">
                <p className="text-sm font-medium">{cp.description}</p>
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Clock className="h-3 w-3" />
                  <span>
                    {new Date(cp.createdAt).toLocaleTimeString('pt-BR')}
                  </span>
                  {cp.node_name && (
                    <>
                      <span>·</span>
                      <span>{cp.node_name}</span>
                    </>
                  )}
                </div>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onRestore(cp.id)}
                className="h-7 gap-1 text-xs"
              >
                <RotateCcw className="h-3 w-3" />
                Restaurar
              </Button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
