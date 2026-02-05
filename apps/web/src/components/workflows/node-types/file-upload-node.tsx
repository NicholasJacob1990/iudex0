'use client';

import React, { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import { Upload } from 'lucide-react';

function FileUploadNodeInner({ data, selected }: { data: any; selected?: boolean }) {
  return (
    <div
      className={`relative min-w-[180px] rounded-xl border bg-white dark:bg-slate-900 shadow-sm px-4 py-3 ${
        selected ? 'border-emerald-500 ring-2 ring-emerald-500/20' : 'border-slate-200 dark:border-slate-700'
      }`}
    >
      {data.optional && (
        <span className="absolute -top-1 -right-1 w-3 h-3 rounded-full bg-amber-400 border-2 border-white" title="Passo opcional" />
      )}
      <Handle type="target" position={Position.Top} className="!bg-emerald-500 !w-3 !h-3" />
      <div className="flex items-center gap-2 mb-1">
        <div className="h-7 w-7 rounded-lg bg-emerald-100 dark:bg-emerald-500/20 flex items-center justify-center">
          <Upload className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
        </div>
        <span className="text-xs font-semibold text-emerald-700 dark:text-emerald-300 uppercase tracking-wider">Upload</span>
      </div>
      <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">{data.label || 'Upload de Arquivo'}</p>
      {data.optional && (
        <span className="text-[10px] bg-slate-100 dark:bg-slate-800 text-slate-500 px-1.5 py-0.5 rounded mt-1 inline-block">opcional</span>
      )}
      <Handle type="source" position={Position.Bottom} className="!bg-emerald-500 !w-3 !h-3" />
    </div>
  );
}

export const FileUploadNode = memo(FileUploadNodeInner);
