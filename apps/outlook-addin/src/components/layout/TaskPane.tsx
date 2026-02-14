import { useState, useEffect } from 'react';
import { Header } from './Header';
import { TabNavigation, type TabId } from './TabNavigation';
import { ErrorBoundary } from './ErrorBoundary';
import { SummaryPanel } from '@/components/summary/SummaryPanel';
import { CorpusSearch } from '@/components/search/CorpusSearch';
import { WorkflowTrigger } from '@/components/workflow/WorkflowTrigger';
import { useEmailStore } from '@/stores/email-store';

const TAB_LABELS: Record<TabId, string> = {
  resumo: 'Resumo',
  pesquisa: 'Pesquisa',
  workflows: 'Workflows',
};

export function TaskPane() {
  const [activeTab, setActiveTab] = useState<TabId>('resumo');
  const loadCurrentEmail = useEmailStore((s) => s.loadCurrentEmail);

  // Carrega dados do e-mail ao montar
  useEffect(() => {
    loadCurrentEmail();
  }, [loadCurrentEmail]);

  const renderContent = () => {
    switch (activeTab) {
      case 'resumo':
        return <SummaryPanel />;
      case 'pesquisa':
        return <CorpusSearch />;
      case 'workflows':
        return <WorkflowTrigger />;
    }
  };

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <Header />
      <TabNavigation activeTab={activeTab} onChange={setActiveTab} />
      <main className="flex-1 overflow-hidden">
        <ErrorBoundary key={activeTab} fallbackLabel={TAB_LABELS[activeTab]}>
          {renderContent()}
        </ErrorBoundary>
      </main>
    </div>
  );
}
