'use client';

import React, { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import { FormInput } from 'lucide-react';

function UserInputNodeInner({ data, selected }: { data: any; selected?: boolean }) {
  const inputType = data.input_type || 'text';
  const isOptional = data.optional;
  return (
    <div
      className={`relative min-w-[180px] rounded-xl border bg-white dark:bg-slate-900 shadow-sm px-4 py-3 ${
        selected ? 'border-teal-500 ring-2 ring-teal-500/20' : 'border-slate-200 dark:border-slate-700'
      }`}
    >
      {isOptional && (
        <span className="absolute -top-1 -right-1 w-3 h-3 rounded-full bg-amber-400 border-2 border-white" title="Passo opcional" />
      )}
      <Handle type="target" position={Position.Top} className="!bg-teal-500 !w-3 !h-3" />
      <div className="flex items-center gap-2 mb-1">
        <div className="h-7 w-7 rounded-lg bg-teal-100 dark:bg-teal-500/20 flex items-center justify-center">
          <FormInput className="h-4 w-4 text-teal-600 dark:text-teal-400" />
        </div>
        <span className="text-xs font-semibold text-teal-700 dark:text-teal-300 uppercase tracking-wider">Input</span>
      </div>
      <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">{data.label || 'User Input'}</p>
      <div className="flex items-center gap-1.5 mt-1">
        <span className="text-[10px] text-slate-400">{inputType}</span>
        {isOptional && (
          <span className="text-[10px] bg-slate-100 dark:bg-slate-800 text-slate-500 px-1.5 py-0.5 rounded">opcional</span>
        )}
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-teal-500 !w-3 !h-3" />
    </div>
  );
}

export const UserInputNode = memo(UserInputNodeInner);
