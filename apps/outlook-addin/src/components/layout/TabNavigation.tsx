import {
  TabList,
  Tab,
  type SelectTabEvent,
  type SelectTabData,
} from '@fluentui/react-components';

export type TabId = 'resumo' | 'pesquisa' | 'workflows';

interface TabDef {
  id: TabId;
  label: string;
}

const TABS: TabDef[] = [
  { id: 'resumo', label: 'Resumo' },
  { id: 'pesquisa', label: 'Pesquisa' },
  { id: 'workflows', label: 'Workflows' },
];

interface TabNavigationProps {
  activeTab: TabId;
  onChange: (tab: TabId) => void;
}

export function TabNavigation({ activeTab, onChange }: TabNavigationProps) {
  const handleTabSelect = (_event: SelectTabEvent, data: SelectTabData) => {
    onChange(data.value as TabId);
  };

  return (
    <TabList
      selectedValue={activeTab}
      onTabSelect={handleTabSelect}
      appearance="subtle"
      size="small"
      className="border-b border-gray-200"
    >
      {TABS.map((tab) => (
        <Tab key={tab.id} value={tab.id}>
          {tab.label}
        </Tab>
      ))}
    </TabList>
  );
}
