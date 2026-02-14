'use client';

import React, { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import { Zap } from 'lucide-react';

const TRIGGER_LABELS: Record<string, string> = {
  teams_command: 'Teams',
  outlook_email: 'Outlook',
  djen_movement: 'DJEN/DataJud',
  schedule: 'Agendamento',
  webhook: 'Webhook',
};

function TriggerNodeInner({ data, selected }: { data: any; selected?: boolean }) {
  const triggerType = data.trigger_type || 'webhook';
  const triggerLabel = TRIGGER_LABELS[triggerType] || triggerType;

  return (
    <div
      className={`min-w-[180px] rounded-xl border bg-white dark:bg-slate-900 shadow-sm px-4 py-3 ${
        selected ? 'border-amber-500 ring-2 ring-amber-500/20' : 'border-slate-200 dark:border-slate-700'
      }`}
    >
      <div className="flex items-center gap-2 mb-1">
        <div className="h-7 w-7 rounded-lg bg-amber-100 dark:bg-amber-500/20 flex items-center justify-center">
          <Zap className="h-4 w-4 text-amber-600 dark:text-amber-400" />
        </div>
        <span className="text-xs font-semibold text-amber-700 dark:text-amber-300 uppercase tracking-wider">Trigger</span>
      </div>
      <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">{data.label || 'Trigger'}</p>
      <div className="flex items-center gap-2 mt-1">
        <span className="text-[10px] bg-amber-100 dark:bg-amber-500/20 text-amber-600 dark:text-amber-400 px-1.5 py-0.5 rounded-full">
          {triggerLabel}
        </span>
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-amber-500 !w-3 !h-3" />
    </div>
  );
}

export const TriggerNode = memo(TriggerNodeInner);
