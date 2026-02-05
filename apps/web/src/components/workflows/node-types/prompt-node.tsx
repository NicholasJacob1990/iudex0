'use client';

import React, { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import { BrainCircuit } from 'lucide-react';

function PromptNodeInner({ data, selected }: { data: any; selected?: boolean }) {
  return (
    <div
      className={`min-w-[180px] rounded-xl border bg-white dark:bg-slate-900 shadow-sm px-4 py-3 ${
        selected ? 'border-violet-500 ring-2 ring-violet-500/20' : 'border-slate-200 dark:border-slate-700'
      }`}
    >
      <Handle type="target" position={Position.Top} className="!bg-violet-500 !w-3 !h-3" />
      <div className="flex items-center gap-2 mb-1">
        <div className="h-7 w-7 rounded-lg bg-violet-100 dark:bg-violet-500/20 flex items-center justify-center">
          <BrainCircuit className="h-4 w-4 text-violet-600 dark:text-violet-400" />
        </div>
        <span className="text-xs font-semibold text-violet-700 dark:text-violet-300 uppercase tracking-wider">Prompt</span>
      </div>
      <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">{data.label || 'LLM Call'}</p>
      {data.model && (
        <p className="text-[10px] text-slate-400 mt-1 truncate">{data.model}</p>
      )}
      <Handle type="source" position={Position.Bottom} className="!bg-violet-500 !w-3 !h-3" />
    </div>
  );
}

export const PromptNode = memo(PromptNodeInner);
