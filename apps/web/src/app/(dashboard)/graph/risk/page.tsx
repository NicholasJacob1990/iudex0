import dynamic from 'next/dynamic';

const GraphRiskPageClient = dynamic(() => import('./GraphRiskPageClient'), {
  ssr: false,
});

export default function GraphRiskPage() {
  return <GraphRiskPageClient />;
}

