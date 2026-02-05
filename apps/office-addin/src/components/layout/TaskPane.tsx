import { useState, useEffect } from 'react';
import { Header } from './Header';
import { TabNavigation, type TabId } from './TabNavigation';
import { ErrorBoundary } from './ErrorBoundary';
import { ChatPanel } from '@/components/chat/ChatPanel';
import { PlaybookPanel } from '@/components/playbook/PlaybookPanel';
import { CorpusPanel } from '@/components/corpus/CorpusPanel';
import { DraftPanel } from '@/components/drafting/DraftPanel';
import { WorkflowPanel } from '@/components/workflows/WorkflowPanel';
import { useDocumentStore } from '@/stores/document-store';

const TAB_LABELS: Record<TabId, string> = {
  chat: 'Chat',
  playbook: 'Playbook',
  corpus: 'Corpus',
  drafting: 'Editor',
  workflows: 'Ferramentas',
};

export function TaskPane() {
  const [activeTab, setActiveTab] = useState<TabId>('chat');
  const refresh = useDocumentStore((s) => s.refresh);

  // Load document context on mount
  useEffect(() => {
    refresh();
  }, [refresh]);

  const renderContent = () => {
    switch (activeTab) {
      case 'chat':
        return <ChatPanel />;
      case 'playbook':
        return <PlaybookPanel />;
      case 'corpus':
        return <CorpusPanel />;
      case 'drafting':
        return <DraftPanel />;
      case 'workflows':
        return <WorkflowPanel />;
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
