'use client';

import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';

type RateRow = {
  label: string;
  points: number;
  usd: number;
  unit: string;
};

const formatPoints = (n: number | null | undefined) => {
  if (typeof n !== 'number' || !Number.isFinite(n)) return '—';
  return Math.round(n).toLocaleString('pt-BR');
};

const formatUsd = (n: number | null | undefined) => {
  if (typeof n !== 'number' || !Number.isFinite(n)) return '—';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 6,
  }).format(n);
};

export function PointsPricingModal({
  open,
  onClose,
  pointsAvailable,
  planLabel,
  modelLabel,
  rateTable,
  notes,
}: {
  open: boolean;
  onClose: () => void;
  pointsAvailable: number | null;
  planLabel: string | null;
  modelLabel: string;
  rateTable: RateRow[];
  notes?: string[];
}) {
  if (!open) return null;

  return (
    <Dialog open={open} onOpenChange={(v) => (!v ? onClose() : null)}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>Pontos & Tarifas</DialogTitle>
        </DialogHeader>

        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-sm text-muted-foreground">Modelo</div>
            <div className="text-lg font-semibold">{modelLabel}</div>
          </div>
          <div className="text-right">
            {planLabel ? (
              <div className="inline-flex rounded-md bg-muted px-3 py-1 text-xs font-semibold text-muted-foreground">
                {planLabel}
              </div>
            ) : null}
            <div className="mt-2 text-sm text-muted-foreground">Pontos disponíveis</div>
            <div className="text-xl font-semibold">{formatPoints(pointsAvailable)} pts</div>
          </div>
        </div>

        <div className="mt-5 overflow-hidden rounded-xl border">
          <div className="grid grid-cols-2 bg-muted/40 px-4 py-3 text-sm font-semibold">
            <div>Item</div>
            <div className="text-right">Rate</div>
          </div>
          {rateTable.map((row) => (
            <div key={row.label} className="grid grid-cols-2 border-t px-4 py-3 text-sm">
              <div>{row.label}</div>
              <div className="text-right">
                <span className="font-semibold">{formatPoints(row.points)}</span>{' '}
                <span className="text-muted-foreground">({formatUsd(row.usd)})</span>{' '}
                <span className="text-muted-foreground">{row.unit}</span>
              </div>
            </div>
          ))}
        </div>

        {Array.isArray(notes) && notes.length > 0 ? (
          <div className="mt-4 space-y-1 text-sm text-muted-foreground">
            {notes.map((t, idx) => (
              <div key={idx}>{t}</div>
            ))}
          </div>
        ) : null}

        <div className="mt-4 flex justify-end">
          <Button variant="ghost" onClick={onClose}>
            Fechar
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
