'use client';

import React, { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import { Send } from 'lucide-react';

const DELIVERY_LABELS: Record<string, string> = {
  email: 'Email',
  teams_message: 'Teams',
  calendar_event: 'Calendário',
  webhook_out: 'Webhook',
  outlook_reply: 'Resposta Outlook',
};

function DeliveryNodeInner({ data, selected }: { data: any; selected?: boolean }) {
  const deliveryType = data.delivery_type || 'email';
  const deliveryLabel = DELIVERY_LABELS[deliveryType] || deliveryType;

  return (
    <div
      className={`min-w-[180px] rounded-xl border bg-white dark:bg-slate-900 shadow-sm px-4 py-3 ${
        selected ? 'border-green-500 ring-2 ring-green-500/20' : 'border-slate-200 dark:border-slate-700'
      }`}
    >
      <Handle type="target" position={Position.Top} className="!bg-green-500 !w-3 !h-3" />
      <div className="flex items-center gap-2 mb-1">
        <div className="h-7 w-7 rounded-lg bg-green-100 dark:bg-green-500/20 flex items-center justify-center">
          <Send className="h-4 w-4 text-green-600 dark:text-green-400" />
        </div>
        <span className="text-xs font-semibold text-green-700 dark:text-green-300 uppercase tracking-wider">Entrega</span>
      </div>
      <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">{data.label || 'Delivery'}</p>
      <div className="flex items-center gap-2 mt-1">
        <span className="text-[10px] bg-green-100 dark:bg-green-500/20 text-green-600 dark:text-green-400 px-1.5 py-0.5 rounded-full">
          {deliveryLabel}
        </span>
      </div>
    </div>
  );
}

export const DeliveryNode = memo(DeliveryNodeInner);
