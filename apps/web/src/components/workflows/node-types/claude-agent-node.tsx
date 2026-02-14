'use client';

import React, { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import { Bot } from 'lucide-react';

function ClaudeAgentNodeInner({ data, selected }: { data: any; selected?: boolean }) {
  const toolCount = (data.tool_names || []).length;
  return (
    <div
      className={`min-w-[180px] rounded-xl border bg-white dark:bg-slate-900 shadow-sm px-4 py-3 ${
        selected ? 'border-indigo-500 ring-2 ring-indigo-500/20' : 'border-slate-200 dark:border-slate-700'
      }`}
    >
      <Handle type="target" position={Position.Top} className="!bg-indigo-500 !w-3 !h-3" />
      <div className="flex items-center gap-2 mb-1">
        <div className="h-7 w-7 rounded-lg bg-indigo-100 dark:bg-indigo-500/20 flex items-center justify-center">
          <Bot className="h-4 w-4 text-indigo-600 dark:text-indigo-400" />
        </div>
        <span className="text-xs font-semibold text-indigo-700 dark:text-indigo-300 uppercase tracking-wider">Agente</span>
      </div>
      <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">{data.label || 'Claude Agent'}</p>
      <div className="flex items-center gap-2 mt-1">
        {data.model && (
          <span className="text-[10px] text-slate-400 truncate">{data.model}</span>
        )}
        {toolCount > 0 && (
          <span className="text-[10px] bg-indigo-100 dark:bg-indigo-500/20 text-indigo-600 dark:text-indigo-400 px-1.5 py-0.5 rounded-full">
            {toolCount} tool{toolCount > 1 ? 's' : ''}
          </span>
        )}
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-indigo-500 !w-3 !h-3" />
    </div>
  );
}

export const ClaudeAgentNode = memo(ClaudeAgentNodeInner);
