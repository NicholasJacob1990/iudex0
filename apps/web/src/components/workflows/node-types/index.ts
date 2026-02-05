import { PromptNode } from './prompt-node';
import { RagSearchNode } from './rag-search-node';
import { FileUploadNode } from './file-upload-node';
import { SelectionNode } from './selection-node';
import { ConditionNode } from './condition-node';
import { HumanReviewNode } from './human-review-node';
import { ToolCallNode } from './tool-call-node';
import { LegalWorkflowNode } from './legal-workflow-node';
import { OutputNode } from './output-node';
import { UserInputNode } from './user-input-node';
import { ReviewTableNode } from './review-table-node';

export { PromptNode, RagSearchNode, FileUploadNode, SelectionNode, ConditionNode, HumanReviewNode, ToolCallNode, LegalWorkflowNode, OutputNode, UserInputNode, ReviewTableNode };

export const nodeTypes: Record<string, any> = {
  prompt: PromptNode,
  rag_search: RagSearchNode,
  file_upload: FileUploadNode,
  selection: SelectionNode,
  condition: ConditionNode,
  human_review: HumanReviewNode,
  tool_call: ToolCallNode,
  legal_workflow: LegalWorkflowNode,
  output: OutputNode,
  user_input: UserInputNode,
  review_table: ReviewTableNode,
};
