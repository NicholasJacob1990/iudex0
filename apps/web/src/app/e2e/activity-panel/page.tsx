'use client';

import { Suspense, useMemo, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { ActivityPanel, type ActivityStep, type Citation } from '@/components/chat/activity-panel';

function ActivityPanelContent() {
  const params = useSearchParams();
  const state = (params.get('state') || 'done').toLowerCase();
  const expandedParam = params.get('expanded');

  const isStreaming = state === 'running';
  const defaultExpanded = expandedParam ? expandedParam === '1' : true;
  const [expanded, setExpanded] = useState(defaultExpanded);

  const steps = useMemo<ActivityStep[]>(() => {
    return [
      {
        id: 'assess_query',
        title: '',
        status: isStreaming ? 'running' : 'done',
        kind: 'assess',
        detail:
          'I will analyze the prompt and attached context to determine the best research and response structure.',
      },
      {
        id: 'reviewing_attached_file',
        title: '',
        status: 'done',
        kind: 'attachment_review',
        attachments: [{ name: 'Complaint.pdf', ext: 'PDF' }],
      },
      {
        id: 'checking_terms',
        title: '',
        status: 'done',
        kind: 'file_terms',
        terms: ['breach', 'damages', 'notice', 'performance', 'obligations', 'liability'],
      },
      {
        id: 'web_search',
        title: '',
        status: isStreaming ? 'running' : 'done',
        kind: 'web_search',
        sources: [
          { title: 'Acme Corp', url: 'https://example.com/acme' },
          { title: 'Sterling Group News', url: 'https://example.com/sterling' },
          { title: 'Law360', url: 'https://example.com/law360' },
          { title: 'Reuters Legal News', url: 'https://example.com/reuters' },
        ],
      },
      {
        id: 'evaluating_evidence',
        title: 'Evaluating evidence strength',
        status: isStreaming ? 'running' : 'done',
        detail:
          'I have reviewed the complaint and completed web research. I will now evaluate which evidence best supports the claims and identify gaps.',
        tags: [],
      },
    ];
  }, [isStreaming]);

  const citations = useMemo<Citation[]>(
    () => [
      { number: '1', title: 'Acme Corp', url: 'https://example.com/acme' },
      { number: '2', title: 'Sterling Group News', url: 'https://example.com/sterling' },
      { number: '3', title: 'Law360', url: 'https://example.com/law360' },
      { number: '4', title: 'Reuters Legal News', url: 'https://example.com/reuters' },
    ],
    []
  );

  return (
    <div className="mx-auto max-w-4xl">
      <div className="rounded-2xl border border-slate-200 bg-white p-8">
        <div className="max-w-[min(92%,76ch)]">
          <ActivityPanel
            steps={steps}
            citations={citations}
            open={expanded}
            onOpenChange={setExpanded}
            isStreaming={isStreaming}
          />
        </div>

        <div className="mt-6 text-xs text-slate-500">
          Use query params: <code>?state=running|done&amp;expanded=0|1&amp;ui_lang=en|pt</code>
        </div>
      </div>
    </div>
  );
}

export default function ActivityPanelE2EPage() {
  return (
    <div className="min-h-screen bg-slate-50 p-10">
      <style jsx global>{`
        * {
          animation: none !important;
          transition: none !important;
          caret-color: transparent !important;
        }
      `}</style>

      <Suspense fallback={<div>Loading...</div>}>
        <ActivityPanelContent />
      </Suspense>
    </div>
  );
}
