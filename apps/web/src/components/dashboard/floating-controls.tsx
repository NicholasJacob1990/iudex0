'use client';

import { LayoutGrid, Radar, ZoomIn, ZoomOut } from 'lucide-react';

export function FloatingControls() {
  return (
    <div className="pointer-events-none fixed bottom-28 right-6 z-40 hidden flex-col gap-3 xl:flex">
      <ControlButton icon={Radar} label="Monitorar IA" accent />
      <ControlButton icon={LayoutGrid} label="Modo multi-caso" />
      <div className="flex flex-col rounded-2xl border border-white/70 bg-white/90 p-1 shadow-soft">
        <ControlButton icon={ZoomIn} label="Zoom in" compact />
        <ControlButton icon={ZoomOut} label="Zoom out" compact />
      </div>
    </div>
  );
}

interface ControlButtonProps {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  accent?: boolean;
  compact?: boolean;
}

function ControlButton({ icon: Icon, label, accent, compact }: ControlButtonProps) {
  return (
    <button
      type="button"
      className="pointer-events-auto flex items-center gap-2 rounded-2xl border border-white/70 bg-white/90 px-4 py-2 text-xs font-semibold text-foreground shadow-soft transition hover:-translate-y-0.5"
      aria-label={label}
    >
      <span
        className={`flex h-8 w-8 items-center justify-center rounded-xl ${
          accent
            ? 'bg-gradient-to-br from-primary to-rose-400 text-primary-foreground'
            : 'bg-secondary text-secondary-foreground'
        } ${compact ? 'h-7 w-7 rounded-lg' : ''}`}
      >
        <Icon className="h-4 w-4" />
      </span>
      {!compact && <span>{label}</span>}
    </button>
  );
}

