'use client';

import React, { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import { GitBranch } from 'lucide-react';

function ParallelAgentsNodeInner({ data, selected }: { data: any; selected?: boolean }) {
  const promptCount = (data.prompts || []).length;
  return (
    <div
      className={`min-w-[180px] rounded-xl border bg-white dark:bg-slate-900 shadow-sm px-4 py-3 ${
        selected ? 'border-fuchsia-500 ring-2 ring-fuchsia-500/20' : 'border-slate-200 dark:border-slate-700'
      }`}
    >
      <Handle type="target" position={Position.Top} className="!bg-fuchsia-500 !w-3 !h-3" />
      <div className="flex items-center gap-2 mb-1">
        <div className="h-7 w-7 rounded-lg bg-fuchsia-100 dark:bg-fuchsia-500/20 flex items-center justify-center">
          <GitBranch className="h-4 w-4 text-fuchsia-600 dark:text-fuchsia-400" />
        </div>
        <span className="text-xs font-semibold text-fuchsia-700 dark:text-fuchsia-300 uppercase tracking-wider">Paralelo</span>
      </div>
      <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">{data.label || 'Agentes Paralelos'}</p>
      <div className="flex items-center gap-2 mt-1">
        {promptCount > 0 && (
          <span className="text-[10px] bg-fuchsia-100 dark:bg-fuchsia-500/20 text-fuchsia-600 dark:text-fuchsia-400 px-1.5 py-0.5 rounded-full">
            {promptCount} agente{promptCount > 1 ? 's' : ''}
          </span>
        )}
        {data.aggregation_strategy && (
          <span className="text-[10px] text-slate-400">{data.aggregation_strategy}</span>
        )}
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-fuchsia-500 !w-3 !h-3" />
    </div>
  );
}

export const ParallelAgentsNode = memo(ParallelAgentsNodeInner);
