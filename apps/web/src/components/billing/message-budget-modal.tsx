'use client';

import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';

type BillingQuote = {
  ok: boolean;
  estimated_points: number;
  estimated_usd: number;
  breakdown?: any;
  current_budget?: number | null;
  suggested_budgets?: number[] | null;
  points_available?: number | null;
  error?: string | null;
};

const formatPoints = (n: number | null | undefined) => {
  if (typeof n !== 'number' || !Number.isFinite(n)) return '—';
  return Math.round(n).toLocaleString('pt-BR');
};

export function MessageBudgetModal({
  open,
  quote,
  onClose,
  onSelectBudget,
}: {
  open: boolean;
  quote: BillingQuote | null;
  onClose: () => void;
  onSelectBudget: (points: number) => void;
}) {
  if (!open || !quote) return null;

  const isBudget = quote.error === 'message_budget_exceeded';
  const isBalance = quote.error === 'insufficient_balance';
  const suggested = Array.isArray(quote.suggested_budgets) ? quote.suggested_budgets : [];
  const recommended =
    suggested[0]
    ?? (isBudget && typeof quote.estimated_points === 'number'
      ? Math.ceil(quote.estimated_points)
      : null);

  return (
    <Dialog open={open} onOpenChange={(v) => (!v ? onClose() : null)}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {isBudget
              ? 'Orçamento por mensagem excedido'
              : isBalance
                ? 'Saldo insuficiente'
                : 'Orçamento indisponível'}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-3 text-sm">
          <div className="rounded-lg border p-3">
            <div className="text-muted-foreground">Estimativa desta mensagem</div>
            <div className="mt-1 text-lg font-semibold">{formatPoints(quote.estimated_points)} pts</div>
          </div>

          {typeof quote.points_available === 'number' ? (
            <div className="rounded-lg border p-3">
              <div className="text-muted-foreground">Pontos disponíveis</div>
              <div className="mt-1 text-lg font-semibold">{formatPoints(quote.points_available)} pts</div>
            </div>
          ) : null}

          {isBudget ? (
            <div className="rounded-lg border p-3">
              <div className="text-muted-foreground">Seu orçamento atual por mensagem</div>
              <div className="mt-1 text-lg font-semibold">{formatPoints(quote.current_budget)} pts</div>
            </div>
          ) : null}

          {isBudget && suggested.length > 0 ? (
            <div className="space-y-2">
              <div className="text-muted-foreground">Escolha um novo orçamento para tentar novamente:</div>
              <div className="grid grid-cols-3 gap-2">
                {suggested.slice(0, 3).map((b) => (
                  <Button
                    key={b}
                    variant={b === recommended ? 'default' : 'secondary'}
                    onClick={() => onSelectBudget(b)}
                  >
                    {formatPoints(b)}
                  </Button>
                ))}
              </div>
            </div>
          ) : null}

          <div className="flex items-center justify-between gap-2 pt-2">
            {isBudget && recommended ? (
              <Button onClick={() => onSelectBudget(recommended)}>
                Usar recomendado ({formatPoints(recommended)} pts)
              </Button>
            ) : (
              <span />
            )}
            <Button variant="ghost" onClick={onClose}>
              Fechar
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

