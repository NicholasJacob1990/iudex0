import dynamic from 'next/dynamic';

const WorkflowBuilderClient = dynamic(
  () => import('./WorkflowBuilderClient'),
  { ssr: false }
);

export default function WorkflowBuilderPage({ params }: { params: { id: string } }) {
  return <WorkflowBuilderClient workflowId={params.id} />;
}
