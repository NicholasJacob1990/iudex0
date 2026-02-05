'use client';

import React, { useState, useRef, useMemo, useCallback } from 'react';
import { useWorkflowStore } from '@/stores/workflow-store';
import { AtSign } from 'lucide-react';

interface PromptEditorProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  currentNodeId?: string;
  rows?: number;
}

/**
 * PromptEditor with dual autocomplete:
 * - Legacy `@node_id` syntax (backwards-compatible)
 * - New `{{node_id.output}}` syntax with dropdown autocomplete
 *
 * Shows a dropdown when user types `{{` listing available upstream nodes.
 * On selection, inserts `{{node_id.output}}` at cursor position.
 */
export function PromptEditor({
  value,
  onChange,
  placeholder,
  className,
  currentNodeId,
  rows = 6,
}: PromptEditorProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [filterText, setFilterText] = useState('');
  const [dropdownPos, setDropdownPos] = useState({ top: 0, left: 0 });

  const { nodes, edges } = useWorkflowStore();

  // Compute available variables from upstream nodes (same logic as VariableAutocomplete)
  const availableNodes = useMemo(() => {
    // Build reverse adjacency
    const reverseAdj: Record<string, string[]> = {};
    edges.forEach((e) => {
      if (!reverseAdj[e.target]) reverseAdj[e.target] = [];
      reverseAdj[e.target].push(e.source);
    });

    // BFS backwards from currentNodeId
    const upstream = new Set<string>();
    if (currentNodeId) {
      const queue = [...(reverseAdj[currentNodeId] || [])];
      while (queue.length) {
        const nid = queue.shift()!;
        if (upstream.has(nid)) continue;
        upstream.add(nid);
        (reverseAdj[nid] || []).forEach((s) => queue.push(s));
      }
    }

    // Build node list
    const result: { id: string; label: string; type: string; fields: string[] }[] = [];
    const nodeMap = new Map(nodes.map((n) => [n.id, n]));

    for (const nid of upstream) {
      const node = nodeMap.get(nid);
      if (!node) continue;
      const label = node.data?.label || nid;
      const type = node.type || 'unknown';
      const fields = ['output'];
      if (type === 'rag_search') fields.push('sources');
      if (type === 'file_upload') fields.push('files');
      if (type === 'legal_workflow') fields.push('metadata');
      result.push({ id: nid, label, type, fields });
    }

    return result;
  }, [nodes, edges, currentNodeId]);

  // Filter suggestions based on typed text after {{
  const filteredSuggestions = useMemo(() => {
    if (!filterText) return availableNodes;
    const lower = filterText.toLowerCase();
    return availableNodes.filter(
      (n) =>
        n.label.toLowerCase().includes(lower) ||
        n.id.toLowerCase().includes(lower) ||
        n.type.toLowerCase().includes(lower)
    );
  }, [availableNodes, filterText]);

  const calculateDropdownPosition = useCallback(() => {
    const ta = textareaRef.current;
    if (!ta) return;

    const lineHeight = parseInt(getComputedStyle(ta).lineHeight) || 20;
    const pos = ta.selectionStart || 0;
    const textBefore = value.slice(0, pos);
    const lines = textBefore.split('\n');
    const currentLine = lines.length - 1;

    setDropdownPos({
      top: Math.min((currentLine + 1) * lineHeight + 4, ta.offsetHeight),
      left: 8,
    });
  }, [value]);

  const checkForTrigger = useCallback(
    (newValue: string, pos: number) => {
      const textBefore = newValue.slice(0, pos);

      // Check for {{ trigger
      const braceMatch = textBefore.match(/\{\{([^}]*)$/);
      if (braceMatch) {
        setFilterText(braceMatch[1]);
        setSelectedIndex(0);
        setShowSuggestions(true);
        calculateDropdownPosition();
        return;
      }

      // Check for @ trigger (legacy)
      const atMatch = textBefore.match(/@([\w]*)$/);
      if (atMatch) {
        setFilterText(atMatch[1]);
        setSelectedIndex(0);
        setShowSuggestions(true);
        calculateDropdownPosition();
        return;
      }

      setShowSuggestions(false);
    },
    [calculateDropdownPosition]
  );

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const newValue = e.target.value;
    const pos = e.target.selectionStart || 0;
    onChange(newValue);
    checkForTrigger(newValue, pos);
  };

  const insertReference = useCallback(
    (nodeId: string, field: string = 'output') => {
      const textarea = textareaRef.current;
      if (!textarea) return;

      const pos = textarea.selectionStart || 0;
      const textBefore = value.slice(0, pos);
      const textAfter = value.slice(pos);

      // Determine which trigger syntax was used
      const braceMatch = textBefore.match(/\{\{([^}]*)$/);
      const atMatch = textBefore.match(/@([\w]*)$/);

      let before: string;
      let insertion: string;

      if (braceMatch) {
        // {{ syntax — insert {{node_id.output}}
        const matchStart = textBefore.lastIndexOf('{{');
        before = value.slice(0, matchStart);
        insertion = `{{${nodeId}.${field}}}`;
      } else if (atMatch) {
        // @ syntax — insert @node_id (legacy)
        const matchStart = textBefore.lastIndexOf('@');
        before = value.slice(0, matchStart);
        insertion = field === 'output' ? `@${nodeId}` : `@${nodeId}.${field}`;
      } else {
        return;
      }

      const newValue = before + insertion + textAfter;
      onChange(newValue);
      setShowSuggestions(false);

      // Set cursor after insertion
      setTimeout(() => {
        if (textarea) {
          const newPos = before.length + insertion.length;
          textarea.setSelectionRange(newPos, newPos);
          textarea.focus();
        }
      }, 0);
    },
    [value, onChange]
  );

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!showSuggestions) return;

    if (e.key === 'Escape') {
      setShowSuggestions(false);
      e.preventDefault();
      return;
    }

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex((prev) =>
        prev < filteredSuggestions.length - 1 ? prev + 1 : 0
      );
      return;
    }

    if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex((prev) =>
        prev > 0 ? prev - 1 : filteredSuggestions.length - 1
      );
      return;
    }

    if (e.key === 'Enter' || e.key === 'Tab') {
      if (filteredSuggestions.length > 0) {
        e.preventDefault();
        const selected = filteredSuggestions[selectedIndex];
        insertReference(selected.id, 'output');
      }
      return;
    }
  };

  const nodeTypeColors: Record<string, string> = {
    prompt: 'bg-violet-100 dark:bg-violet-900/30 text-violet-600 dark:text-violet-400',
    rag_search: 'bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400',
    user_input: 'bg-teal-100 dark:bg-teal-900/30 text-teal-600 dark:text-teal-400',
    file_upload: 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-600 dark:text-emerald-400',
    selection: 'bg-amber-100 dark:bg-amber-900/30 text-amber-600 dark:text-amber-400',
    tool_call: 'bg-cyan-100 dark:bg-cyan-900/30 text-cyan-600 dark:text-cyan-400',
    legal_workflow: 'bg-indigo-100 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400',
    human_review: 'bg-rose-100 dark:bg-rose-900/30 text-rose-600 dark:text-rose-400',
  };

  return (
    <div className="relative">
      <textarea
        ref={textareaRef}
        value={value}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        onBlur={() => setTimeout(() => setShowSuggestions(false), 200)}
        placeholder={
          placeholder || 'Use {{ ou @ para referenciar outros nos...'
        }
        rows={rows}
        className={
          className ||
          'w-full rounded-md border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-3 py-2 text-sm font-mono focus:ring-2 focus:ring-indigo-500 focus:border-transparent resize-y'
        }
      />

      {/* Toggle button */}
      {availableNodes.length > 0 && (
        <button
          type="button"
          onClick={() => {
            setShowSuggestions(!showSuggestions);
            setFilterText('');
            setSelectedIndex(0);
            calculateDropdownPosition();
          }}
          className="absolute top-2 right-2 p-1 rounded hover:bg-slate-100 dark:hover:bg-slate-700"
          title="Inserir referencia"
        >
          <AtSign className="h-3.5 w-3.5 text-slate-400" />
        </button>
      )}

      {/* Reference hint */}
      <div className="flex items-center gap-1 mt-1">
        <span className="text-[10px] text-slate-400">
          Digite{' '}
          <code className="px-1 py-0.5 bg-slate-100 dark:bg-slate-800 rounded text-[10px]">
            {'{{'}
          </code>{' '}
          ou{' '}
          <code className="px-1 py-0.5 bg-slate-100 dark:bg-slate-800 rounded text-[10px]">
            @
          </code>{' '}
          para referenciar saidas de nos anteriores
        </span>
      </div>

      {/* Autocomplete dropdown */}
      {showSuggestions && filteredSuggestions.length > 0 && (
        <div
          ref={dropdownRef}
          className="absolute z-50 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg shadow-lg max-h-56 overflow-y-auto min-w-[240px]"
          style={{ top: dropdownPos.top, left: dropdownPos.left }}
        >
          <div className="px-3 py-1.5 text-[10px] font-semibold text-slate-400 uppercase tracking-wider border-b border-slate-100 dark:border-slate-800">
            Nos disponíveis
          </div>
          {filteredSuggestions.map((node, idx) => (
            <div key={node.id}>
              {/* Main node output */}
              <button
                className={`w-full text-left px-3 py-2 flex items-center gap-2 text-xs transition-colors ${
                  idx === selectedIndex
                    ? 'bg-indigo-50 dark:bg-indigo-500/10'
                    : 'hover:bg-slate-50 dark:hover:bg-slate-800'
                }`}
                onMouseDown={(e) => {
                  e.preventDefault();
                  insertReference(node.id, 'output');
                }}
                onMouseEnter={() => setSelectedIndex(idx)}
              >
                <span
                  className={`text-[10px] px-1.5 py-0.5 rounded font-mono ${
                    nodeTypeColors[node.type] ||
                    'bg-slate-100 dark:bg-slate-800 text-slate-500'
                  }`}
                >
                  {node.type}
                </span>
                <span className="text-slate-700 dark:text-slate-300 font-medium truncate">
                  {node.label}
                </span>
                <span className="text-slate-400 ml-auto font-mono text-[10px] shrink-0">
                  {`{{${node.id}.output}}`}
                </span>
              </button>
              {/* Extra fields (sources, files, metadata) */}
              {node.fields
                .filter((f) => f !== 'output')
                .map((field) => (
                  <button
                    key={`${node.id}.${field}`}
                    className="w-full text-left px-3 py-1.5 pl-8 flex items-center gap-2 text-xs hover:bg-slate-50 dark:hover:bg-slate-800 text-slate-500"
                    onMouseDown={(e) => {
                      e.preventDefault();
                      insertReference(node.id, field);
                    }}
                  >
                    <span className="text-[10px] text-slate-400 font-mono">
                      .{field}
                    </span>
                    <span className="text-slate-400 ml-auto font-mono text-[10px]">
                      {`{{${node.id}.${field}}}`}
                    </span>
                  </button>
                ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
