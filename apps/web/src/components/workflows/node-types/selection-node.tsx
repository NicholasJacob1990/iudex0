'use client';

import React, { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import { ListChecks } from 'lucide-react';

function SelectionNodeInner({ data, selected }: { data: any; selected?: boolean }) {
  return (
    <div
      className={`relative min-w-[180px] rounded-xl border bg-white dark:bg-slate-900 shadow-sm px-4 py-3 ${
        selected ? 'border-amber-500 ring-2 ring-amber-500/20' : 'border-slate-200 dark:border-slate-700'
      }`}
    >
      {data.optional && (
        <span className="absolute -top-1 -right-1 w-3 h-3 rounded-full bg-amber-400 border-2 border-white" title="Passo opcional" />
      )}
      <Handle type="target" position={Position.Top} className="!bg-amber-500 !w-3 !h-3" />
      <div className="flex items-center gap-2 mb-1">
        <div className="h-7 w-7 rounded-lg bg-amber-100 dark:bg-amber-500/20 flex items-center justify-center">
          <ListChecks className="h-4 w-4 text-amber-600 dark:text-amber-400" />
        </div>
        <span className="text-xs font-semibold text-amber-700 dark:text-amber-300 uppercase tracking-wider">Seleção</span>
      </div>
      <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">{data.label || 'Escolha'}</p>
      <div className="flex items-center gap-1.5 mt-1">
        {data.options && data.options.length > 0 && (
          <span className="text-[10px] text-slate-400">{data.options.length} opcoes</span>
        )}
        {data.optional && (
          <span className="text-[10px] bg-slate-100 dark:bg-slate-800 text-slate-500 px-1.5 py-0.5 rounded">opcional</span>
        )}
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-amber-500 !w-3 !h-3" />
    </div>
  );
}

export const SelectionNode = memo(SelectionNodeInner);
