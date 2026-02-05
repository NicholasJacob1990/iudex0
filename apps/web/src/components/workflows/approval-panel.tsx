'use client';

import React from 'react';
import { CheckCircle2, Clock, Send, XCircle, Archive, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { apiClient } from '@/lib/api-client';
import { toast } from 'sonner';

interface ApprovalPanelProps {
  workflowId: string;
  status: string;
  submittedAt?: string | null;
  approvedAt?: string | null;
  publishedVersion?: number | null;
  rejectionReason?: string | null;
  onStatusChange: (newStatus: string) => void;
}

const STATUS_CONFIG: Record<string, { label: string; color: string; icon: React.ElementType }> = {
  draft: { label: 'Rascunho', color: 'slate', icon: Clock },
  pending_approval: { label: 'Aguardando Aprovação', color: 'amber', icon: Send },
  approved: { label: 'Aprovado', color: 'blue', icon: CheckCircle2 },
  published: { label: 'Publicado', color: 'emerald', icon: CheckCircle2 },
  rejected: { label: 'Rejeitado', color: 'red', icon: XCircle },
  archived: { label: 'Arquivado', color: 'gray', icon: Archive },
};

export function ApprovalPanel({
  workflowId, status, submittedAt, approvedAt, publishedVersion,
  rejectionReason, onStatusChange,
}: ApprovalPanelProps) {
  const [loading, setLoading] = React.useState(false);
  const [reason, setReason] = React.useState('');
  const config = STATUS_CONFIG[status] || STATUS_CONFIG.draft;
  const Icon = config.icon;

  const handleSubmit = async () => {
    setLoading(true);
    try {
      await apiClient.submitWorkflowForApproval(workflowId);
      onStatusChange('pending_approval');
      toast.success('Workflow submetido para aprovação');
    } catch {
      toast.error('Erro ao submeter');
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async (approved: boolean) => {
    setLoading(true);
    try {
      await apiClient.approveWorkflow(workflowId, approved, approved ? undefined : reason);
      onStatusChange(approved ? 'approved' : 'rejected');
      toast.success(approved ? 'Workflow aprovado' : 'Workflow rejeitado');
    } catch {
      toast.error('Erro na decisão');
    } finally {
      setLoading(false);
    }
  };

  const handlePublish = async () => {
    setLoading(true);
    try {
      await apiClient.publishWorkflow(workflowId);
      onStatusChange('published');
      toast.success('Workflow publicado');
    } catch {
      toast.error('Erro ao publicar');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="border rounded-lg p-4 space-y-3 bg-white dark:bg-slate-900">
      {/* Status badge */}
      <div className="flex items-center gap-2">
        <Icon className={`h-4 w-4 text-${config.color}-500`} />
        <span className={`text-sm font-semibold text-${config.color}-700 dark:text-${config.color}-400`}>
          {config.label}
        </span>
        {publishedVersion && (
          <span className="text-xs text-slate-500 ml-auto">v{publishedVersion}</span>
        )}
      </div>

      {/* Timeline */}
      <div className="space-y-1 text-xs text-slate-500">
        {submittedAt && <p>Submetido em {new Date(submittedAt).toLocaleDateString('pt-BR')}</p>}
        {approvedAt && <p>Aprovado em {new Date(approvedAt).toLocaleDateString('pt-BR')}</p>}
        {rejectionReason && (
          <p className="text-red-500">Motivo: {rejectionReason}</p>
        )}
      </div>

      {/* Actions */}
      <div className="flex flex-col gap-2">
        {(status === 'draft' || status === 'rejected') && (
          <Button size="sm" onClick={handleSubmit} disabled={loading} className="gap-1.5">
            {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
            Submeter para Aprovação
          </Button>
        )}

        {status === 'pending_approval' && (
          <>
            <Textarea
              placeholder="Motivo da rejeição (opcional)"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              className="text-xs h-16"
            />
            <div className="flex gap-2">
              <Button size="sm" onClick={() => handleApprove(true)} disabled={loading}
                className="gap-1.5 bg-emerald-600 hover:bg-emerald-500 text-white flex-1">
                Aprovar
              </Button>
              <Button size="sm" variant="outline" onClick={() => handleApprove(false)} disabled={loading}
                className="gap-1.5 border-red-300 text-red-600 flex-1">
                Rejeitar
              </Button>
            </div>
          </>
        )}

        {status === 'approved' && (
          <Button size="sm" onClick={handlePublish} disabled={loading}
            className="gap-1.5 bg-emerald-600 hover:bg-emerald-500 text-white">
            {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
            Publicar
          </Button>
        )}
      </div>
    </div>
  );
}
