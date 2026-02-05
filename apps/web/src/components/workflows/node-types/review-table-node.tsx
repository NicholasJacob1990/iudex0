'use client';

import React, { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import { Table2 } from 'lucide-react';

function ReviewTableNodeInner({ data, selected }: { data: any; selected?: boolean }) {
  const columns = data.columns || [];

  return (
    <div
      className={`min-w-[180px] rounded-xl border bg-white dark:bg-slate-900 shadow-sm px-4 py-3 ${
        selected ? 'border-teal-500 ring-2 ring-teal-500/20' : 'border-slate-200 dark:border-slate-700'
      }`}
    >
      <Handle type="target" position={Position.Top} className="!bg-teal-500 !w-3 !h-3" />
      <div className="flex items-center gap-2 mb-1">
        <div className="h-7 w-7 rounded-lg bg-teal-100 dark:bg-teal-500/20 flex items-center justify-center">
          <Table2 className="h-4 w-4 text-teal-600 dark:text-teal-400" />
        </div>
        <span className="text-xs font-semibold text-teal-700 dark:text-teal-300 uppercase tracking-wider">Tabela</span>
      </div>
      <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">{data.label || 'Tabela de Revisão'}</p>
      {columns.length > 0 && (
        <p className="text-[10px] text-slate-400 mt-1 truncate">
          {columns.length} col: {columns.map((c: any) => c.name).filter(Boolean).join(', ')}
        </p>
      )}
      {data.model && (
        <p className="text-[10px] text-slate-400 mt-0.5 truncate">{data.model}</p>
      )}
      <Handle type="source" position={Position.Bottom} className="!bg-teal-500 !w-3 !h-3" />
    </div>
  );
}

export const ReviewTableNode = memo(ReviewTableNodeInner);
