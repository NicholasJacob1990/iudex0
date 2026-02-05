'use client';

import React, { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import { Search } from 'lucide-react';

function RagSearchNodeInner({ data, selected }: { data: any; selected?: boolean }) {
  return (
    <div
      className={`min-w-[180px] rounded-xl border bg-white dark:bg-slate-900 shadow-sm px-4 py-3 ${
        selected ? 'border-blue-500 ring-2 ring-blue-500/20' : 'border-slate-200 dark:border-slate-700'
      }`}
    >
      <Handle type="target" position={Position.Top} className="!bg-blue-500 !w-3 !h-3" />
      <div className="flex items-center gap-2 mb-1">
        <div className="h-7 w-7 rounded-lg bg-blue-100 dark:bg-blue-500/20 flex items-center justify-center">
          <Search className="h-4 w-4 text-blue-600 dark:text-blue-400" />
        </div>
        <span className="text-xs font-semibold text-blue-700 dark:text-blue-300 uppercase tracking-wider">RAG Search</span>
      </div>
      <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">{data.label || 'Pesquisar'}</p>
      {data.limit && (
        <p className="text-[10px] text-slate-400 mt-1">Top {data.limit} resultados</p>
      )}
      <Handle type="source" position={Position.Bottom} className="!bg-blue-500 !w-3 !h-3" />
    </div>
  );
}

export const RagSearchNode = memo(RagSearchNodeInner);
