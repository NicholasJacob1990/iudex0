'use client';

import React, { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import { GitBranch } from 'lucide-react';

function ConditionNodeInner({ data, selected }: { data: any; selected?: boolean }) {
  const branchCount = data.branches ? Object.keys(data.branches).length : 0;

  return (
    <div
      className={`min-w-[180px] rounded-xl border bg-white dark:bg-slate-900 shadow-sm px-4 py-3 ${
        selected ? 'border-orange-500 ring-2 ring-orange-500/20' : 'border-slate-200 dark:border-slate-700'
      }`}
    >
      <Handle type="target" position={Position.Top} className="!bg-orange-500 !w-3 !h-3" />
      <div className="flex items-center gap-2 mb-1">
        <div className="h-7 w-7 rounded-lg bg-orange-100 dark:bg-orange-500/20 flex items-center justify-center">
          <GitBranch className="h-4 w-4 text-orange-600 dark:text-orange-400" />
        </div>
        <span className="text-xs font-semibold text-orange-700 dark:text-orange-300 uppercase tracking-wider">Condição</span>
      </div>
      <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">{data.label || 'Condição'}</p>
      {branchCount > 0 && (
        <p className="text-[10px] text-slate-400 mt-1">{branchCount} ramos</p>
      )}
      <Handle type="source" position={Position.Bottom} className="!bg-orange-500 !w-3 !h-3" />
    </div>
  );
}

export const ConditionNode = memo(ConditionNodeInner);
