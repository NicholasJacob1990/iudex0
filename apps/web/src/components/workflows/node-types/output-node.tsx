'use client';

import React, { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import { FileOutput } from 'lucide-react';

function OutputNodeInner({ data, selected }: { data: any; selected?: boolean }) {
  const sectionCount = (data.sections || []).length;
  return (
    <div
      className={`min-w-[180px] rounded-xl border bg-white dark:bg-slate-900 shadow-sm px-4 py-3 ${
        selected ? 'border-emerald-500 ring-2 ring-emerald-500/20' : 'border-slate-200 dark:border-slate-700'
      }`}
    >
      <Handle type="target" position={Position.Top} className="!bg-emerald-500 !w-3 !h-3" />
      <div className="flex items-center gap-2 mb-1">
        <div className="h-7 w-7 rounded-lg bg-emerald-100 dark:bg-emerald-500/20 flex items-center justify-center">
          <FileOutput className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
        </div>
        <span className="text-xs font-semibold text-emerald-700 dark:text-emerald-300 uppercase tracking-wider">Resposta</span>
      </div>
      <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">{data.label || 'Resposta Final'}</p>
      {sectionCount > 0 && (
        <p className="text-[10px] text-slate-400 mt-1">{sectionCount} seções</p>
      )}
      {/* No source handle — output is terminal */}
    </div>
  );
}

export const OutputNode = memo(OutputNodeInner);
