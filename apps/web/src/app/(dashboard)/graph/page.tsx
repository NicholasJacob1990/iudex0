import dynamic from 'next/dynamic';

const GraphPageClient = dynamic(() => import('./GraphPageClient'), {
  ssr: false,
});

export default function GraphPage() {
  return <GraphPageClient />;
}
