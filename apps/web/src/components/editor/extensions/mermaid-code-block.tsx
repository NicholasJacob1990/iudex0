'use client';

import { useState } from 'react';
import { NodeViewContent, NodeViewWrapper, ReactNodeViewRenderer, type NodeViewProps } from '@tiptap/react';
import CodeBlock from '@tiptap/extension-code-block';
import { DiagramViewer } from '@/components/dashboard/diagram-viewer';

function MermaidCodeBlockView({ node }: NodeViewProps) {
  const language = String(node.attrs.language || '').toLowerCase();
  const isMermaid = language === 'mermaid';
  const code = node.textContent || '';
  const [showEditor, setShowEditor] = useState(false);

  if (!isMermaid) {
    return (
      <NodeViewWrapper className="tiptap-code-block">
        <pre className="tiptap-code-block-pre">
          <NodeViewContent as="code" className="tiptap-code-block-content" />
        </pre>
      </NodeViewWrapper>
    );
  }

  return (
    <NodeViewWrapper className="tiptap-mermaid-block">
      <div className="tiptap-mermaid-toolbar" contentEditable={false}>
        <span className="tiptap-mermaid-label">Mermaid</span>
        <button
          type="button"
          className="tiptap-mermaid-toggle"
          onClick={() => setShowEditor((prev) => !prev)}
        >
          {showEditor ? 'Fechar' : 'Editar'}
        </button>
      </div>
      <div contentEditable={false} className="tiptap-mermaid-preview">
        <DiagramViewer code={code} compact />
      </div>
      {showEditor ? (
        <pre className="tiptap-code-block-pre">
          <NodeViewContent as="code" className="tiptap-code-block-content" />
        </pre>
      ) : null}
    </NodeViewWrapper>
  );
}

export const MermaidCodeBlock = CodeBlock.extend({
  addNodeView() {
    return ReactNodeViewRenderer(MermaidCodeBlockView);
  },
});
