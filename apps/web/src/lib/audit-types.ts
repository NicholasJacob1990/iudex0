/**
 * Unified audit types — single source of truth for audit data from audit_summary.json.
 */

export interface AuditSummary {
  summary: {
    version: string;
    generated_at?: string;
    status: 'ok' | 'warning' | 'error';
    score: number | null;
    scores: Record<string, number>;
    diagnostic_issues_total?: number;
    issues_total: number;
    issues: AuditSummaryIssue[];
    false_positives_removed: number;
    revalidated_at?: string;
  };
  modules: AuditModule[];
  report_keys: Record<string, string>;
}

export interface AuditSummaryIssue {
  source: string;
  category: string;
  severity: 'critical' | 'high' | 'medium' | 'low' | 'info' | 'warning';
  description: string;
  raw_item?: Record<string, unknown>;
  has_evidence?: boolean;
  evidence_raw?: string;
  evidence_formatted?: string;
  is_false_positive?: boolean;
}

export interface AuditModule {
  id: string;
  label: string;
  status: string;
  score: number | null;
  issues: AuditSummaryIssue[];
  report_paths?: Record<string, string | null>;
  error?: string;
}

/** Actionable HIL issue with stable ID — from audit_issues array. */
export interface AuditActionableIssue {
  id: string;
  type: string;
  fix_type?: 'structural' | 'content' | string;
  severity: string;
  source?: string;
  origin?: string;
  description: string;
  suggestion?: string;
  reference?: string;
  raw_evidence?: string | Array<string | { snippet?: string; text?: string }>;
  evidence_formatted?: string;
}
