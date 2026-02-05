'use client';

import React, { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import { Wrench } from 'lucide-react';

function ToolCallNodeInner({ data, selected }: { data: any; selected?: boolean }) {
  return (
    <div
      className={`min-w-[180px] rounded-xl border bg-white dark:bg-slate-900 shadow-sm px-4 py-3 ${
        selected ? 'border-cyan-500 ring-2 ring-cyan-500/20' : 'border-slate-200 dark:border-slate-700'
      }`}
    >
      <Handle type="target" position={Position.Top} className="!bg-cyan-500 !w-3 !h-3" />
      <div className="flex items-center gap-2 mb-1">
        <div className="h-7 w-7 rounded-lg bg-cyan-100 dark:bg-cyan-500/20 flex items-center justify-center">
          <Wrench className="h-4 w-4 text-cyan-600 dark:text-cyan-400" />
        </div>
        <span className="text-xs font-semibold text-cyan-700 dark:text-cyan-300 uppercase tracking-wider">Tool</span>
      </div>
      <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">{data.label || 'Tool Call'}</p>
      {data.tool_name && (
        <p className="text-[10px] text-slate-400 mt-1 truncate">{data.tool_name}</p>
      )}
      <Handle type="source" position={Position.Bottom} className="!bg-cyan-500 !w-3 !h-3" />
    </div>
  );
}

export const ToolCallNode = memo(ToolCallNodeInner);
