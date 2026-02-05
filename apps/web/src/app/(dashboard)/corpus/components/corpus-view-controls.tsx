'use client';

import { useEffect, useState } from 'react';
import { List, LayoutGrid, Layers, ArrowUpDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { cn } from '@/lib/utils';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type CorpusViewMode = 'list' | 'grid' | 'grouped';
export type CorpusSortOption = 'recent' | 'oldest' | 'alpha';

interface ViewControlsProps {
  viewMode: CorpusViewMode;
  onViewModeChange: (mode: CorpusViewMode) => void;
  sortOption: CorpusSortOption;
  onSortChange: (sort: CorpusSortOption) => void;
}

// ---------------------------------------------------------------------------
// Persistence helpers
// ---------------------------------------------------------------------------

const VIEW_MODE_KEY = 'corpus-view-mode';
const SORT_KEY = 'corpus-sort';

export function usePersistedViewPreferences() {
  const [viewMode, setViewMode] = useState<CorpusViewMode>('list');
  const [sortOption, setSortOption] = useState<CorpusSortOption>('recent');

  // Load from localStorage on mount
  useEffect(() => {
    try {
      const savedView = localStorage.getItem(VIEW_MODE_KEY) as CorpusViewMode | null;
      if (savedView && ['list', 'grid', 'grouped'].includes(savedView)) {
        setViewMode(savedView);
      }
      const savedSort = localStorage.getItem(SORT_KEY) as CorpusSortOption | null;
      if (savedSort && ['recent', 'oldest', 'alpha'].includes(savedSort)) {
        setSortOption(savedSort);
      }
    } catch {
      // localStorage may not be available
    }
  }, []);

  const updateViewMode = (mode: CorpusViewMode) => {
    setViewMode(mode);
    try {
      localStorage.setItem(VIEW_MODE_KEY, mode);
    } catch {
      // ignore
    }
  };

  const updateSortOption = (sort: CorpusSortOption) => {
    setSortOption(sort);
    try {
      localStorage.setItem(SORT_KEY, sort);
    } catch {
      // ignore
    }
  };

  return { viewMode, setViewMode: updateViewMode, sortOption, setSortOption: updateSortOption };
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const viewModes: { value: CorpusViewMode; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
  { value: 'list', label: 'Lista', icon: List },
  { value: 'grid', label: 'Grade', icon: LayoutGrid },
  { value: 'grouped', label: 'Agrupado', icon: Layers },
];

const sortOptions: { value: CorpusSortOption; label: string }[] = [
  { value: 'recent', label: 'Mais recentes' },
  { value: 'oldest', label: 'Mais antigos' },
  { value: 'alpha', label: 'Ordem alfabetica' },
];

export function CorpusViewControls({
  viewMode,
  onViewModeChange,
  sortOption,
  onSortChange,
}: ViewControlsProps) {
  return (
    <div className="flex items-center gap-2">
      {/* View mode toggle */}
      <div className="flex items-center rounded-lg border bg-muted/30 p-0.5">
        {viewModes.map(({ value, label, icon: Icon }) => (
          <Button
            key={value}
            variant="ghost"
            size="sm"
            className={cn(
              'h-7 w-7 p-0 rounded-md',
              viewMode === value && 'bg-white shadow-sm'
            )}
            onClick={() => onViewModeChange(value)}
            title={label}
          >
            <Icon className="h-3.5 w-3.5" />
          </Button>
        ))}
      </div>

      {/* Sort dropdown */}
      <Select value={sortOption} onValueChange={(v) => onSortChange(v as CorpusSortOption)}>
        <SelectTrigger className="w-[160px] rounded-xl h-8 text-xs">
          <ArrowUpDown className="h-3 w-3 mr-1" />
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {sortOptions.map((opt) => (
            <SelectItem key={opt.value} value={opt.value}>
              {opt.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
