export type TabId = 'chat' | 'playbook' | 'corpus' | 'drafting' | 'workflows';

interface Tab {
  id: TabId;
  label: string;
}

const TABS: Tab[] = [
  { id: 'chat', label: 'Chat' },
  { id: 'playbook', label: 'Playbook' },
  { id: 'corpus', label: 'Corpus' },
  { id: 'drafting', label: 'Editar' },
  { id: 'workflows', label: 'Ferramentas' },
];

interface TabNavigationProps {
  activeTab: TabId;
  onChange: (tab: TabId) => void;
}

export function TabNavigation({ activeTab, onChange }: TabNavigationProps) {
  return (
    <nav className="flex border-b border-gray-200">
      {TABS.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onChange(tab.id)}
          className={`flex-1 px-2 py-2 text-office-sm font-medium transition-colors ${
            activeTab === tab.id
              ? 'border-b-2 border-brand text-brand'
              : 'text-text-secondary hover:bg-surface-tertiary hover:text-text-primary'
          }`}
        >
          {tab.label}
        </button>
      ))}
    </nav>
  );
}
