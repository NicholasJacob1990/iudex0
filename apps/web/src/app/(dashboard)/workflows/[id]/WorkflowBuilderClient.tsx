'use client';

import React from 'react';
import { WorkflowBuilder } from '@/components/workflows/workflow-builder';

export default function WorkflowBuilderClient({ workflowId }: { workflowId: string }) {
  return (
    <div className="h-[calc(100vh-64px)] flex flex-col">
      <WorkflowBuilder workflowId={workflowId} />
    </div>
  );
}
