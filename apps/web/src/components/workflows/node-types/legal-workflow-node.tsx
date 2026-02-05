'use client';

import React, { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import { Scale } from 'lucide-react';

const MODE_LABELS: Record<string, string> = {
  minuta: 'Minuta',
  parecer: 'Parecer',
  chat: 'Chat',
  analysis: 'Análise',
};

function LegalWorkflowNodeInner({ data, selected }: { data: any; selected?: boolean }) {
  const mode = data.mode || 'minuta';

  return (
    <div
      className={`min-w-[200px] rounded-xl border bg-white dark:bg-slate-900 shadow-md px-4 py-3 ${
        selected
          ? 'border-indigo-500 ring-2 ring-indigo-500/20'
          : 'border-slate-200 dark:border-slate-700'
      }`}
    >
      <Handle type="target" position={Position.Top} className="!bg-indigo-500 !w-3 !h-3" />
      <div className="flex items-center gap-2 mb-1">
        <div className="h-7 w-7 rounded-lg bg-gradient-to-br from-indigo-100 to-violet-100 dark:from-indigo-500/20 dark:to-violet-500/20 flex items-center justify-center">
          <Scale className="h-4 w-4 text-indigo-600 dark:text-indigo-400" />
        </div>
        <span className="text-xs font-semibold text-indigo-700 dark:text-indigo-300 uppercase tracking-wider">
          Legal Workflow
        </span>
      </div>
      <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">
        {data.label || `Gerar ${MODE_LABELS[mode] || mode}`}
      </p>
      <div className="flex items-center gap-1.5 mt-1.5">
        <span className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-100 dark:bg-indigo-500/20 text-indigo-600 dark:text-indigo-300 font-medium">
          {MODE_LABELS[mode] || mode}
        </span>
        {data.models && data.models.length > 0 && (
          <span className="text-[10px] text-slate-400 truncate">
            {data.models.length} modelo{data.models.length > 1 ? 's' : ''}
          </span>
        )}
        {data.auto_approve && (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-100 dark:bg-amber-500/20 text-amber-600 dark:text-amber-300">
            Auto
          </span>
        )}
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-indigo-500 !w-3 !h-3" />
    </div>
  );
}

export const LegalWorkflowNode = memo(LegalWorkflowNodeInner);
