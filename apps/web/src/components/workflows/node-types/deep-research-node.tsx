'use client';

import React, { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import { BookOpen } from 'lucide-react';

function DeepResearchNodeInner({ data, selected }: { data: any; selected?: boolean }) {
  const mode = (data.mode || 'hard') as string;
  const providers = Array.isArray(data.providers) ? data.providers : [];

  return (
    <div
      className={`min-w-[190px] rounded-xl border bg-white dark:bg-slate-900 shadow-sm px-4 py-3 ${
        selected ? 'border-emerald-500 ring-2 ring-emerald-500/20' : 'border-slate-200 dark:border-slate-700'
      }`}
    >
      <Handle type="target" position={Position.Top} className="!bg-emerald-500 !w-3 !h-3" />
      <div className="flex items-center gap-2 mb-1">
        <div className="h-7 w-7 rounded-lg bg-emerald-100 dark:bg-emerald-500/20 flex items-center justify-center">
          <BookOpen className="h-4 w-4 text-emerald-700 dark:text-emerald-400" />
        </div>
        <span className="text-xs font-semibold text-emerald-700 dark:text-emerald-300 uppercase tracking-wider">
          Deep Research
        </span>
      </div>

      <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">{data.label || 'Deep Research'}</p>
      <div className="flex items-center gap-2 mt-1">
        <span className="text-[10px] text-slate-400 truncate">{mode === 'hard' ? 'hard (multi-provider)' : 'normal'}</span>
        {mode === 'hard' && providers.length > 0 && (
          <span className="text-[10px] bg-emerald-100 dark:bg-emerald-500/20 text-emerald-700 dark:text-emerald-300 px-1.5 py-0.5 rounded-full">
            {providers.length} prov.
          </span>
        )}
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-emerald-500 !w-3 !h-3" />
    </div>
  );
}

export const DeepResearchNode = memo(DeepResearchNodeInner);

