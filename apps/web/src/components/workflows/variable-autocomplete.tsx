'use client';

import React, { useState, useRef, useMemo } from 'react';
import { useWorkflowStore } from '@/stores/workflow-store';
import { AtSign } from 'lucide-react';

interface VariableAutocompleteProps {
  value: string;
  onChange: (value: string) => void;
  nodeId: string;
  placeholder?: string;
  rows?: number;
}

export function VariableAutocomplete({
  value,
  onChange,
  nodeId,
  placeholder,
  rows = 4,
}: VariableAutocompleteProps) {
  const { nodes, edges } = useWorkflowStore();
  const [showDropdown, setShowDropdown] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Compute available variables from upstream nodes
  const availableVars = useMemo(() => {
    // Build reverse adjacency
    const reverseAdj: Record<string, string[]> = {};
    edges.forEach((e) => {
      if (!reverseAdj[e.target]) reverseAdj[e.target] = [];
      reverseAdj[e.target].push(e.source);
    });

    // BFS backwards
    const upstream = new Set<string>();
    const queue = [...(reverseAdj[nodeId] || [])];
    while (queue.length) {
      const nid = queue.shift()!;
      if (upstream.has(nid)) continue;
      upstream.add(nid);
      (reverseAdj[nid] || []).forEach((s) => queue.push(s));
    }

    // Build vars
    const vars: { ref: string; label: string; type: string }[] = [];
    const nodeMap = new Map(nodes.map((n) => [n.id, n]));
    for (const nid of upstream) {
      const node = nodeMap.get(nid);
      if (!node) continue;
      const label = node.data?.label || nid;
      vars.push({ ref: `@${nid}`, label: `${label} (output)`, type: node.type || '' });
      if (node.type === 'rag_search') {
        vars.push({ ref: `@${nid}.sources`, label: `${label} (fontes)`, type: 'rag_search' });
      }
      if (node.type === 'file_upload') {
        vars.push({ ref: `@${nid}.files`, label: `${label} (arquivos)`, type: 'file_upload' });
      }
    }
    return vars;
  }, [nodes, edges, nodeId]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === '@' || (e.key === '2' && e.shiftKey)) {
      // Will trigger after onChange
      setTimeout(() => setShowDropdown(true), 50);
    }
    if (e.key === 'Escape') {
      setShowDropdown(false);
    }
  };

  const insertVariable = (ref: string) => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    const pos = textarea.selectionStart;
    // Check if there's an @ just before cursor
    const before = value.slice(0, pos);
    const lastAt = before.lastIndexOf('@');
    const newValue =
      lastAt >= 0 && pos - lastAt < 30
        ? value.slice(0, lastAt) + ref + value.slice(pos)
        : value.slice(0, pos) + ref + ' ' + value.slice(pos);
    onChange(newValue);
    setShowDropdown(false);
    setTimeout(() => textarea.focus(), 50);
  };

  return (
    <div className="relative">
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        onBlur={() => setTimeout(() => setShowDropdown(false), 200)}
        placeholder={placeholder}
        rows={rows}
        className="w-full rounded-md border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-3 py-2 text-sm font-mono focus:ring-2 focus:ring-indigo-500 focus:border-transparent resize-y"
      />
      {availableVars.length > 0 && (
        <button
          type="button"
          onClick={() => setShowDropdown(!showDropdown)}
          className="absolute top-2 right-2 p-1 rounded hover:bg-slate-100 dark:hover:bg-slate-700"
          title="Inserir variavel"
        >
          <AtSign className="h-3.5 w-3.5 text-slate-400" />
        </button>
      )}
      {showDropdown && availableVars.length > 0 && (
        <div className="absolute z-50 top-full left-0 mt-1 w-full max-h-48 overflow-auto rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 shadow-lg">
          <div className="px-3 py-1.5 text-[10px] font-semibold text-slate-400 uppercase tracking-wider border-b border-slate-100 dark:border-slate-800">
            Variaveis disponíveis
          </div>
          {availableVars.map((v) => (
            <button
              key={v.ref}
              onClick={() => insertVariable(v.ref)}
              className="w-full text-left px-3 py-2 text-sm hover:bg-indigo-50 dark:hover:bg-indigo-500/10 flex items-center gap-2"
            >
              <code className="text-indigo-600 dark:text-indigo-400 font-mono text-xs">{v.ref}</code>
              <span className="text-slate-500 text-xs truncate">{v.label}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
