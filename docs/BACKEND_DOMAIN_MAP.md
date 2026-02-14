# Mapa de APIs por Dominio Funcional

Base path: `/api` (ver `apps/api/app/main.py`).

## Matriz feature -> backend

| Feature (dominio) | API (prefixo) | Endpoints (qtde) | Services | Models/Schemas |
| --- | --- | --- | --- | --- |
| Admin Flags | `/api` | 4 | app.services.ai.shared.feature_flags | app.models.user |
| Admin Rag | `/api` | 5 | app.services.rag_module_old, app.services.rag_policy | app.models.rag_ingestion, app.models.rag_policy, app.models.user |
| Advanced | `/api/advanced` | 10 | app.services.ai.audit_service, app.services.quality_service, app.services.rag_module_old, app.services.transcription_service | app.models.user |
| Agent Tasks | `/api/agent` | 4 | app.services.ai.claude_agent.parallel_agents | app.models.user |
| Analytics | `/api/analytics` | 5 | app.services.corpus_service | app.models.chat, app.models.document, app.models.rag_trace, app.models.workflow |
| Assistant | `/api/assistant` | 1 | app.services.ai.agent_clients | app.models.document, app.models.user, app.models.workflow |
| Audit | `/api/audit` | 19 | app.services.ai.audit_service, app.services.ai.observability.audit_log, app.services.document_extraction_service | app.models.case_task, app.models.user, app.models.workflow_state |
| Audit Logs | `/api/audit-logs` | 2 | — | app.models.audit_log, app.models.user, app.schemas.audit_log |
| Auth | `/api/auth` | 6 | — | app.models.user, app.schemas.user |
| Billing | `/api/billing` | 3 | app.services.ai.agent_clients, app.services.billing_quote_service, app.services.billing_service, app.services.poe_like_billing, app.services.token_budget_service | app.models.chat, app.models.user, app.schemas.chat |
| Cases | `/api/cases` | 9 | app.services.case_service, app.services.document_extraction_service, app.services.rag.core.neo4j_mvp, app.services.rag.pipeline.rag_pipeline | app.models.document, app.models.user, app.schemas.case |
| Chat | `/api/multi-chat` | 6 | app.services.ai.agent_clients, app.services.ai.model_registry, app.services.ai.prompt_flags, app.services.api_call_tracker, app.services.billing_quote_service, app.services.billing_service, app.services.chat_service, app.services.poe_like_billing, app.services.rag_policy, app.services.token_budget_service | app.models.document, app.models.user |
| Chat Integration | `/api/chat` | 2 | app.services.ai.juridico_adapter, app.services.case_service | app.models.user, app.schemas.chat |
| Chats | `/api/chats` | 13 | app.services.agent_session_registry, app.services.ai.agent_clients, app.services.ai.chat_tools, app.services.ai.citations, app.services.ai.citations.base, app.services.ai.citations.grounding, app.services.ai.claude_agent.permissions, app.services.ai.deep_research_hard_service, app.services.ai.deep_research_service, app.services.ai.genai_utils, app.services.ai.internal_rag_agent, app.services.ai.juridico_adapter, app.services.ai.langgraph.improvements.checkpoint_manager, app.services.ai.langgraph_legal_workflow, app.services.ai.mcp_tools, app.services.ai.model_registry, app.services.ai.nodes.catalogo_documentos, app.services.ai.observability.audit_log, app.services.ai.observability.metrics, app.services.ai.orchestration.router, app.services.ai.orchestrator, app.services.ai.perplexity_config, app.services.ai.prompt_flags, app.services.ai.rag_helpers, app.services.ai.rag_memory_store, app.services.ai.rag_router, app.services.ai.research_policy, app.services.ai.shared.feature_flags, app.services.ai.skills.matcher, app.services.ai.thinking_parser, app.services.api_call_tracker, app.services.billing_quote_service, app.services.billing_service, app.services.chat_service, app.services.command_service, app.services.context_strategy, app.services.corpus_chat_tool, app.services.document_extraction_service, app.services.document_generator, app.services.job_manager, app.services.mcp_hub, app.services.mention_parser, app.services.model_registry, app.services.poe_like_billing, app.services.rag.pipeline_adapter, app.services.rag_policy, app.services.rag_trace, app.services.token_budget_service, app.services.web_rag_service, app.services.web_search_service | app.models.chat, app.models.document, app.models.library, app.models.user, app.schemas.chat, app.schemas.document, app.schemas.smart_template |
| Clauses | `/api/clauses` | 3 | — | app.models.library, app.models.user |
| Config | `/api/config` | 2 | app.services.billing_service | — |
| Context Bridge | `/api/context` | 3 | app.services.ai.claude_agent.parallel_agents, app.services.unified_context_store | app.models.user |
| Corpus | `/api/corpus` | 26 | app.services.corpus_service, app.services.rag.regional_sources_catalog | app.models.user, app.schemas.corpus |
| Corpus Projects | `/api/corpus/projects` | 13 | — | app.models.corpus_project, app.models.document, app.models.user, app.schemas.corpus_project |
| Dashboard | `/api/dashboard` | 1 | — | app.models.chat, app.models.corpus_project, app.models.playbook, app.models.review_table, app.models.user |
| Djen | `/api/djen` | 14 | app.services.djen_scheduler, app.services.djen_service, app.services.djen_sync | app.models.djen, app.models.user, app.schemas.djen |
| Dms | `/api/dms` | 12 | app.services.dms_service | app.models.user, app.schemas.dms |
| Documents | `/api/documents` | 22 | app.services.ai.audit_service, app.services.ai.model_registry, app.services.docs_utils, app.services.document_extraction_service, app.services.document_generator, app.services.url_scraper_service | app.models.document, app.models.user, app.schemas.document |
| Email Triggers | `/api/email-triggers` | 3 | app.services.graph_client | app.models.email_trigger_config, app.models.graph_subscription, app.models.microsoft_user, app.models.user |
| Extraction Jobs | `/api/review-tables` | 8 | app.services.batch_extraction_service | app.models.extraction_job, app.models.review_table, app.models.user |
| Graph | `/api/graph` | 19 | app.services.graph_enrich_service, app.services.rag.config, app.services.rag.core.argument_neo4j, app.services.rag.core.neo4j_mvp, app.services.rag.storage.opensearch_service | app.models.user, app.schemas.graph_enrich |
| Graph Ask | `/api/graph` | 8 | app.services.graph_ask_service | app.models.user |
| Graph Risk | `/api/graph` | 6 | app.services.graph_risk_service | app.schemas.graph_risk |
| Graph Webhooks | `/api/graph-webhooks` | 5 | app.services.builtin_workflows, app.services.graph_client, app.services.graph_email, app.services.workflow_triggers | app.models.email_trigger_config, app.models.graph_subscription, app.models.microsoft_user, app.models.organization, app.models.user, app.models.workflow |
| Guest Auth | `/api/auth` | 4 | — | app.models.guest_session, app.models.shared_space, app.schemas.guest |
| Health | `/api` | 4 | app.services.rag.core.resilience, app.services.rag.storage.opensearch_service, app.services.rag.storage.qdrant_service | app.models.user |
| Jobs | `/api/jobs` | 4 | app.services.ai.checklist_parser, app.services.ai.citations.base, app.services.ai.document_store, app.services.ai.langgraph_legal_workflow, app.services.ai.model_registry, app.services.ai.nodes.catalogo_documentos, app.services.ai.orchestration.router, app.services.ai.quality_profiles, app.services.ai.rag_memory_store, app.services.api_call_tracker, app.services.billing_quote_service, app.services.billing_service, app.services.chat_history, app.services.context_strategy, app.services.document_extraction_service, app.services.job_manager, app.services.model_registry, app.services.poe_like_billing, app.services.rag_policy, app.services.token_budget_service | app.models.document, app.models.user, app.models.workflow_state |
| Knowledge | `/api/knowledge` | 5 | app.services.jurisprudence_service, app.services.jurisprudence_verifier, app.services.legislation_service, app.services.web_search_service | app.models.document, app.schemas.citation_verification |
| Library | `/api/library` | 15 | — | app.models.document, app.models.library, app.models.user, app.schemas.library |
| Marketplace | `/api/marketplace` | 6 | — | app.models.library, app.models.marketplace, app.models.workflow, app.schemas.marketplace |
| Mcp | `/api/mcp` | 12 | app.services.ai.tool_gateway, app.services.ai.tool_gateway.tool_registry, app.services.mcp_hub | app.models.user |
| Mcp Bnp | `/api/mcp/bnp` | 1 | app.services.mcp_servers.bnp_server | — |
| Microsoft Sso | `/api/auth` | 2 | — | app.schemas.microsoft_auth |
| Models | `/api/models` | 7 | app.services.ai.model_registry, app.services.ai.model_router, app.services.ai.shared.feature_flags, app.services.audit_logger | app.models.user |
| Organizations | `/api/organizations` | 12 | — | app.models.organization, app.models.user, app.schemas.organization |
| Outlook Addin | `/api/outlook-addin` | 5 | app.services.builtin_workflows, app.services.outlook_addin_service | app.models.organization, app.models.user, app.models.workflow, app.schemas.outlook_addin_schemas |
| Playbooks | `/api/playbooks` | 22 | app.services.document_extraction_service, app.services.playbook_service | app.models.playbook, app.models.user, app.schemas.playbook, app.schemas.playbook_analysis |
| Quality Control | `/api/quality` | 12 | app.services.legal_checklist_generator, app.services.quality_service | — |
| Rag | `/api/rag` | 10 | app.services.rag.config, app.services.rag.core.contextual_embeddings, app.services.rag.core.embeddings, app.services.rag.core.graph_factory, app.services.rag.core.graph_rag, app.services.rag.core.kg_builder.pipeline, app.services.rag.core.metrics, app.services.rag.core.neo4j_mvp, app.services.rag.core.result_cache, app.services.rag.embedding_router, app.services.rag.jurisbert_embeddings, app.services.rag.kanon_embeddings, app.services.rag.legal_embeddings, app.services.rag.pipeline, app.services.rag.utils.ingest, app.services.rag.voyage_embeddings, app.services.rag_module, app.services.rag_policy | app.models.user |
| Review Tables | `/api/review-tables` | 32 | app.services.cell_verification_service, app.services.column_builder_service, app.services.review_table_service, app.services.table_chat_service | app.models.document, app.models.dynamic_column, app.models.review_table, app.models.table_chat, app.models.user |
| Skills | `/api/skills` | 3 | app.services.ai.skills.loader, app.services.ai.skills.skill_builder | app.models.library, app.models.user, app.schemas.skills |
| Spaces | `/api/spaces` | 12 | — | app.models.shared_space, app.models.user, app.schemas.shared_space |
| Teams Bot | `/api/teams-bot` | 2 | app.services.teams_bot.bot, app.services.teams_bot.cards, app.services.teams_bot.conversation_store | — |
| Templates | `/api/templates` | 19 | app.services.ai.nodes.catalogo_documentos, app.services.ai.template_generator, app.services.legal_templates, app.services.template_service | app.models.library, app.models.user, app.schemas.smart_template |
| Transcription | `/api/transcription` | 31 | app.services.api_call_tracker, app.services.job_manager, app.services.mlx_loader, app.services.preventive_hil, app.services.quality_service, app.services.transcription_service | app.models.user, app.schemas.transcription |
| Tribunais | `/api/tribunais` | 13 | app.services.tribunais_client | app.models.user, app.schemas.tribunais |
| Users | `/api/users` | 4 | — | app.models.user |
| Webhooks | `/api/webhooks` | 3 | — | app.schemas.tribunais |
| Word Addin | `/api/word-addin` | 16 | app.services.redline_service, app.services.word_addin_service | app.models.playbook, app.models.playbook_run_cache, app.models.redline_state, app.models.user, app.schemas.word_addin |
| Workflows | `/api/workflows` | 38 | app.services.ai.agent_clients, app.services.ai.model_registry, app.services.ai.nl_to_graph, app.services.ai.workflow_compiler, app.services.ai.workflow_runner, app.services.unified_context_store, app.services.workflow_export_service, app.services.workflow_permission_service | app.models.user, app.models.workflow, app.models.workflow_permission |

## Detalhe por dominio (endpoints + services + models)

### Admin Flags
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/admin_flags.py`
Prefixo: `/api`

Endpoints:
- `GET /api/admin/feature-flags`
- `POST /api/admin/feature-flags/override`
- `DELETE /api/admin/feature-flags/override`
- `POST /api/admin/feature-flags/clear-overrides`
Services:
- `app.services.ai.shared.feature_flags`
Models/Schemas:
- `app.models.user`

### Admin Rag
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/admin_rag.py`
Prefixo: `/api`

Endpoints:
- `GET /api/admin/rag`
- `GET /api/admin/rag/policies`
- `POST /api/admin/rag/policies`
- `POST /api/admin/rag/policies/form`
- `DELETE /api/admin/rag/policies/{policy_id}`
Services:
- `app.services.rag_module_old`
- `app.services.rag_policy`
Models/Schemas:
- `app.models.rag_ingestion`
- `app.models.rag_policy`
- `app.models.user`

### Advanced
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/advanced.py`
Prefixo: `/api/advanced`

Endpoints:
- `POST /api/advanced/renumber`
- `POST /api/advanced/audit-structure-rigorous`
- `POST /api/advanced/consistency-check`
- `POST /api/advanced/verify-citation`
- `POST /api/advanced/dry-run-analysis`
- `POST /api/advanced/cross-file-duplicates`
- `POST /api/advanced/apply-structural-fixes`
- `POST /api/advanced/transcribe-advanced`
- `POST /api/advanced/audit-with-rag`
- `POST /api/advanced/diarization/align`
Services:
- `app.services.ai.audit_service`
- `app.services.quality_service`
- `app.services.rag_module_old`
- `app.services.transcription_service`
Models/Schemas:
- `app.models.user`

### Agent Tasks
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/agent_tasks.py`
Prefixo: `/api/agent`

Endpoints:
- `POST /api/agent/spawn`
- `GET /api/agent/tasks`
- `GET /api/agent/tasks/{task_id}`
- `DELETE /api/agent/tasks/{task_id}`
Services:
- `app.services.ai.claude_agent.parallel_agents`
Models/Schemas:
- `app.models.user`

### Analytics
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/analytics.py`
Prefixo: `/api/analytics`

Endpoints:
- `GET /api/analytics/corpus/overview`
- `GET /api/analytics/corpus/trending`
- `GET /api/analytics/corpus/usage-over-time`
- `GET /api/analytics/workflows/stats`
- `GET /api/analytics/documents/insights`
Services:
- `app.services.corpus_service`
Models/Schemas:
- `app.models.chat`
- `app.models.document`
- `app.models.rag_trace`
- `app.models.workflow`

### Assistant
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/assistant.py`
Prefixo: `/api/assistant`

Endpoints:
- `POST /api/assistant/chat`
Services:
- `app.services.ai.agent_clients`
Models/Schemas:
- `app.models.document`
- `app.models.user`
- `app.models.workflow`

### Audit
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/audit.py`
Prefixo: `/api/audit`

Endpoints:
- `POST /api/audit/run`
- `POST /api/audit/verify-snippet`
- `POST /api/audit/edit-proposal`
- `POST /api/audit/edit-proposal/{proposal_id}/apply`
- `POST /api/audit/edit-proposal/{proposal_id}/reject`
- `GET /api/audit/workflow-states`
- `GET /api/audit/workflow-states/{state_id}`
- `GET /api/audit/workflow-states/by-job/{job_id}`
- `GET /api/audit/workflow-states/{state_id}/sources`
- `GET /api/audit/workflow-states/{state_id}/decisions`
- `GET /api/audit/workflow-states/{state_id}/hil-history`
- `GET /api/audit/tasks`
- `GET /api/audit/tasks/{task_id}`
- `POST /api/audit/tasks`
- `PATCH /api/audit/tasks/{task_id}`
- `DELETE /api/audit/tasks/{task_id}`
- `GET /api/audit/summary`
- `GET /api/audit/tool-calls`
- `GET /api/audit/tool-calls/export`
Services:
- `app.services.ai.audit_service`
- `app.services.ai.observability.audit_log`
- `app.services.document_extraction_service`
Models/Schemas:
- `app.models.case_task`
- `app.models.user`
- `app.models.workflow_state`

### Audit Logs
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/audit_logs.py`
Prefixo: `/api/audit-logs`

Endpoints:
- `GET /api/audit-logs/export`
- `GET /api/audit-logs/stats`
Services:
- —
Models/Schemas:
- `app.models.audit_log`
- `app.models.user`
- `app.schemas.audit_log`

### Auth
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/auth.py`
Prefixo: `/api/auth`

Endpoints:
- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/login-test`
- `POST /api/auth/logout`
- `POST /api/auth/refresh`
- `GET /api/auth/me`
Services:
- —
Models/Schemas:
- `app.models.user`
- `app.schemas.user`

### Billing
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/billing.py`
Prefixo: `/api/billing`

Endpoints:
- `GET /api/billing/summary`
- `POST /api/billing/quote_message`
- `GET /api/billing/pricing_sheet`
Services:
- `app.services.ai.agent_clients`
- `app.services.billing_quote_service`
- `app.services.billing_service`
- `app.services.poe_like_billing`
- `app.services.token_budget_service`
Models/Schemas:
- `app.models.chat`
- `app.models.user`
- `app.schemas.chat`

### Cases
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/cases.py`
Prefixo: `/api/cases`

Endpoints:
- `GET /api/cases`
- `POST /api/cases`
- `GET /api/cases/{case_id}`
- `PUT /api/cases/{case_id}`
- `DELETE /api/cases/{case_id}`
- `POST /api/cases/{case_id}/documents/upload`
- `GET /api/cases/{case_id}/documents`
- `POST /api/cases/{case_id}/documents/{doc_id}/attach`
- `DELETE /api/cases/{case_id}/documents/{doc_id}/detach`
Services:
- `app.services.case_service`
- `app.services.document_extraction_service`
- `app.services.rag.core.neo4j_mvp`
- `app.services.rag.pipeline.rag_pipeline`
Models/Schemas:
- `app.models.document`
- `app.models.user`
- `app.schemas.case`

### Chat
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/chat.py`
Prefixo: `/api/multi-chat`

Endpoints:
- `POST /api/multi-chat/threads`
- `GET /api/multi-chat/threads`
- `GET /api/multi-chat/threads/{thread_id}`
- `POST /api/multi-chat/threads/{thread_id}/messages`
- `POST /api/multi-chat/threads/{thread_id}/consolidate`
- `POST /api/multi-chat/threads/{thread_id}/edit`
Services:
- `app.services.ai.agent_clients`
- `app.services.ai.model_registry`
- `app.services.ai.prompt_flags`
- `app.services.api_call_tracker`
- `app.services.billing_quote_service`
- `app.services.billing_service`
- `app.services.chat_service`
- `app.services.poe_like_billing`
- `app.services.rag_policy`
- `app.services.token_budget_service`
Models/Schemas:
- `app.models.document`
- `app.models.user`

### Chat Integration
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/chat_integration.py`
Prefixo: `/api/chat`

Endpoints:
- `POST /api/chat/message`
- `POST /api/chat/export-to-case`
Services:
- `app.services.ai.juridico_adapter`
- `app.services.case_service`
Models/Schemas:
- `app.models.user`
- `app.schemas.chat`

### Chats
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/chats.py`
Prefixo: `/api/chats`

Endpoints:
- `GET /api/chats`
- `POST /api/chats`
- `GET /api/chats/{chat_id}`
- `POST /api/chats/{chat_id}/duplicate`
- `DELETE /api/chats/{chat_id}`
- `GET /api/chats/{chat_id}/messages`
- `POST /api/chats/{chat_id}/messages`
- `POST /api/chats/{chat_id}/messages/stream`
- `POST /api/chats/{chat_id}/outline`
- `POST /api/chats/{chat_id}/generate`
- `POST /api/chats/{chat_id}/edit`
- `POST /api/chats/{chat_id}/tool-approval`
- `POST /api/chats/{chat_id}/restore-checkpoint`
Services:
- `app.services.agent_session_registry`
- `app.services.ai.agent_clients`
- `app.services.ai.chat_tools`
- `app.services.ai.citations`
- `app.services.ai.citations.base`
- `app.services.ai.citations.grounding`
- `app.services.ai.claude_agent.permissions`
- `app.services.ai.deep_research_hard_service`
- `app.services.ai.deep_research_service`
- `app.services.ai.genai_utils`
- `app.services.ai.internal_rag_agent`
- `app.services.ai.juridico_adapter`
- `app.services.ai.langgraph.improvements.checkpoint_manager`
- `app.services.ai.langgraph_legal_workflow`
- `app.services.ai.mcp_tools`
- `app.services.ai.model_registry`
- `app.services.ai.nodes.catalogo_documentos`
- `app.services.ai.observability.audit_log`
- `app.services.ai.observability.metrics`
- `app.services.ai.orchestration.router`
- `app.services.ai.orchestrator`
- `app.services.ai.perplexity_config`
- `app.services.ai.prompt_flags`
- `app.services.ai.rag_helpers`
- `app.services.ai.rag_memory_store`
- `app.services.ai.rag_router`
- `app.services.ai.research_policy`
- `app.services.ai.shared.feature_flags`
- `app.services.ai.skills.matcher`
- `app.services.ai.thinking_parser`
- `app.services.api_call_tracker`
- `app.services.billing_quote_service`
- `app.services.billing_service`
- `app.services.chat_service`
- `app.services.command_service`
- `app.services.context_strategy`
- `app.services.corpus_chat_tool`
- `app.services.document_extraction_service`
- `app.services.document_generator`
- `app.services.job_manager`
- `app.services.mcp_hub`
- `app.services.mention_parser`
- `app.services.model_registry`
- `app.services.poe_like_billing`
- `app.services.rag.pipeline_adapter`
- `app.services.rag_policy`
- `app.services.rag_trace`
- `app.services.token_budget_service`
- `app.services.web_rag_service`
- `app.services.web_search_service`
Models/Schemas:
- `app.models.chat`
- `app.models.document`
- `app.models.library`
- `app.models.user`
- `app.schemas.chat`
- `app.schemas.document`
- `app.schemas.smart_template`

### Clauses
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/clauses.py`
Prefixo: `/api/clauses`

Endpoints:
- `GET /api/clauses`
- `POST /api/clauses`
- `DELETE /api/clauses/{clause_id}`
Services:
- —
Models/Schemas:
- `app.models.library`
- `app.models.user`

### Config
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/config.py`
Prefixo: `/api/config`

Endpoints:
- `GET /api/config/limits`
- `GET /api/config/billing`
Services:
- `app.services.billing_service`
Models/Schemas:
- —

### Context Bridge
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/context_bridge.py`
Prefixo: `/api/context`

Endpoints:
- `POST /api/context/promote-to-agent`
- `POST /api/context/export-to-workflow`
- `GET /api/context/session/{session_id}`
Services:
- `app.services.ai.claude_agent.parallel_agents`
- `app.services.unified_context_store`
Models/Schemas:
- `app.models.user`

### Corpus
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/corpus.py`
Prefixo: `/api/corpus`

Endpoints:
- `GET /api/corpus/stats`
- `GET /api/corpus/documents`
- `GET /api/corpus/documents/export`
- `GET /api/corpus/documents/{document_id}/source`
- `GET /api/corpus/documents/{document_id}/viewer-manifest`
- `GET /api/corpus/documents/{document_id}/content`
- `GET /api/corpus/documents/{document_id}/preview`
- `GET /api/corpus/sources/regional`
- `POST /api/corpus/ingest`
- `DELETE /api/corpus/documents/{document_id}`
- `POST /api/corpus/search`
- `GET /api/corpus/collections`
- `GET /api/corpus/collections/{collection_name}`
- `POST /api/corpus/documents/{document_id}/promote`
- `POST /api/corpus/documents/{document_id}/extend-ttl`
- `GET /api/corpus/retention-policy`
- `PUT /api/corpus/retention-policy`
- `GET /api/corpus/admin/overview`
- `GET /api/corpus/admin/users`
- `GET /api/corpus/admin/users/{user_id}/documents`
- `POST /api/corpus/admin/transfer/{document_id}`
- `GET /api/corpus/admin/activity`
- `POST /api/corpus/admin/backfill/jurisdiction`
- `POST /api/corpus/admin/backfill/source-id`
- `POST /api/corpus/admin/viewer/backfill`
- `POST /api/corpus/verbatim`
Services:
- `app.services.corpus_service`
- `app.services.rag.regional_sources_catalog`
Models/Schemas:
- `app.models.user`
- `app.schemas.corpus`

### Corpus Projects
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/corpus_projects.py`
Prefixo: `/api/corpus/projects`

Endpoints:
- `GET /api/corpus/projects/{project_id}`
- `PUT /api/corpus/projects/{project_id}`
- `DELETE /api/corpus/projects/{project_id}`
- `POST /api/corpus/projects/{project_id}/documents`
- `DELETE /api/corpus/projects/{project_id}/documents/{document_id}`
- `GET /api/corpus/projects/{project_id}/duplicates`
- `GET /api/corpus/projects/{project_id}/folders`
- `POST /api/corpus/projects/{project_id}/folders`
- `GET /api/corpus/projects/{project_id}/documents`
- `PATCH /api/corpus/projects/{project_id}/documents/{document_id}/move`
- `POST /api/corpus/projects/{project_id}/share`
- `DELETE /api/corpus/projects/{project_id}/share/{share_id}`
- `POST /api/corpus/projects/{project_id}/transfer`
Services:
- —
Models/Schemas:
- `app.models.corpus_project`
- `app.models.document`
- `app.models.user`
- `app.schemas.corpus_project`

### Dashboard
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/dashboard.py`
Prefixo: `/api/dashboard`

Endpoints:
- `GET /api/dashboard/recent-activity`
Services:
- —
Models/Schemas:
- `app.models.chat`
- `app.models.corpus_project`
- `app.models.playbook`
- `app.models.review_table`
- `app.models.user`

### Djen
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/djen.py`
Prefixo: `/api/djen`

Endpoints:
- `POST /api/djen/watchlist`
- `GET /api/djen/watchlist`
- `POST /api/djen/watchlist/oab`
- `GET /api/djen/watchlist/oab`
- `DELETE /api/djen/watchlist/oab/{watchlist_id}`
- `PATCH /api/djen/watchlist/{watchlist_id}`
- `PATCH /api/djen/watchlist/oab/{watchlist_id}`
- `DELETE /api/djen/watchlist/{watchlist_id}`
- `POST /api/djen/datajud/search`
- `POST /api/djen/comunica/search`
- `POST /api/djen/search`
- `GET /api/djen/intimations`
- `GET /api/djen/intimations/{intimation_id}`
- `POST /api/djen/sync`
Services:
- `app.services.djen_scheduler`
- `app.services.djen_service`
- `app.services.djen_sync`
Models/Schemas:
- `app.models.djen`
- `app.models.user`
- `app.schemas.djen`

### Dms
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/dms.py`
Prefixo: `/api/dms`

Endpoints:
- `GET /api/dms/providers`
- `POST /api/dms/connect`
- `GET /api/dms/callback`
- `POST /api/dms/connect/{provider}`
- `GET /api/dms/callback/{provider}`
- `GET /api/dms/integrations`
- `DELETE /api/dms/integrations/{integration_id}`
- `GET /api/dms/integrations/{integration_id}/files`
- `POST /api/dms/integrations/{integration_id}/import`
- `GET /api/dms/{provider}/files`
- `POST /api/dms/{provider}/import`
- `POST /api/dms/integrations/{integration_id}/sync`
Services:
- `app.services.dms_service`
Models/Schemas:
- `app.models.user`
- `app.schemas.dms`

### Documents
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/documents.py`
Prefixo: `/api/documents`

Endpoints:
- `POST /api/documents/export/docx`
- `GET /api/documents`
- `GET /api/documents/{document_id}`
- `POST /api/documents/upload`
- `POST /api/documents/from-text`
- `POST /api/documents/from-url`
- `GET /api/documents/{document_id}`
- `DELETE /api/documents/{document_id}`
- `POST /api/documents/{document_id}/ocr`
- `POST /api/documents/{document_id}/summary`
- `POST /api/documents/{document_id}/transcribe`
- `POST /api/documents/{document_id}/podcast`
- `POST /api/documents/{document_id}/diagram`
- `POST /api/documents/{document_id}/process`
- `POST /api/documents/generate`
- `POST /api/documents/{document_id}/audit`
- `GET /api/documents/signature`
- `PUT /api/documents/signature`
- `POST /api/documents/{document_id}/add-signature`
- `POST /api/documents/{document_id}/share`
- `DELETE /api/documents/{document_id}/share`
- `GET /api/documents/share/{token}`
Services:
- `app.services.ai.audit_service`
- `app.services.ai.model_registry`
- `app.services.docs_utils`
- `app.services.document_extraction_service`
- `app.services.document_generator`
- `app.services.url_scraper_service`
Models/Schemas:
- `app.models.document`
- `app.models.user`
- `app.schemas.document`

### Email Triggers
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/email_triggers.py`
Prefixo: `/api/email-triggers`

Endpoints:
- `PUT /api/email-triggers/{config_id}`
- `DELETE /api/email-triggers/{config_id}`
- `POST /api/email-triggers/subscribe`
Services:
- `app.services.graph_client`
Models/Schemas:
- `app.models.email_trigger_config`
- `app.models.graph_subscription`
- `app.models.microsoft_user`
- `app.models.user`

### Extraction Jobs
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/extraction_jobs.py`
Prefixo: `/api/review-tables`

Endpoints:
- `POST /api/review-tables/{table_id}/extract`
- `GET /api/review-tables/{table_id}/jobs`
- `GET /api/review-tables/{table_id}/jobs/{job_id}`
- `GET /api/review-tables/{table_id}/jobs/{job_id}/progress`
- `POST /api/review-tables/{table_id}/jobs/{job_id}/pause`
- `POST /api/review-tables/{table_id}/jobs/{job_id}/resume`
- `POST /api/review-tables/{table_id}/jobs/{job_id}/cancel`
- `GET /api/review-tables/{table_id}/jobs/{job_id}/stream`
Services:
- `app.services.batch_extraction_service`
Models/Schemas:
- `app.models.extraction_job`
- `app.models.review_table`
- `app.models.user`

### Graph
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/graph.py`
Prefixo: `/api/graph`

Endpoints:
- `GET /api/graph/entities`
- `GET /api/graph/entity/{entity_id}`
- `GET /api/graph/export`
- `GET /api/graph/path`
- `GET /api/graph/stats`
- `POST /api/graph/extract-entities`
- `GET /api/graph/relation-types`
- `GET /api/graph/semantic-neighbors/{entity_id}`
- `GET /api/graph/remissoes/{entity_id}`
- `POST /api/graph/enrich`
- `POST /api/graph/candidates/recompute`
- `GET /api/graph/candidates/stats`
- `POST /api/graph/candidates/promote`
- `POST /api/graph/lexical-search`
- `POST /api/graph/content-search`
- `POST /api/graph/add-from-rag`
- `GET /api/graph/argument-graph/{case_id}`
- `GET /api/graph/argument-stats`
- `POST /api/graph/add-facts-from-rag`
Services:
- `app.services.graph_enrich_service`
- `app.services.rag.config`
- `app.services.rag.core.argument_neo4j`
- `app.services.rag.core.neo4j_mvp`
- `app.services.rag.storage.opensearch_service`
Models/Schemas:
- `app.models.user`
- `app.schemas.graph_enrich`

### Graph Ask
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/graph_ask.py`
Prefixo: `/api/graph`

Endpoints:
- `POST /api/graph/ask`
- `POST /api/graph/ask/path`
- `POST /api/graph/ask/neighbors`
- `POST /api/graph/ask/cooccurrence`
- `POST /api/graph/ask/search`
- `POST /api/graph/ask/count`
- `POST /api/graph/ask/text2cypher`
- `GET /api/graph/ask/health`
Services:
- `app.services.graph_ask_service`
Models/Schemas:
- `app.models.user`

### Graph Risk
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/graph_risk.py`
Prefixo: `/api/graph`

Endpoints:
- `POST /api/graph/risk/scan`
- `GET /api/graph/risk/reports`
- `GET /api/graph/risk/reports/{report_id}`
- `DELETE /api/graph/risk/reports/{report_id}`
- `POST /api/graph/risk/audit/edge`
- `POST /api/graph/risk/audit/chain`
Services:
- `app.services.graph_risk_service`
Models/Schemas:
- `app.schemas.graph_risk`

### Graph Webhooks
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/graph_webhooks.py`
Prefixo: `/api/graph-webhooks`

Endpoints:
- `POST /api/graph-webhooks/notification`
- `POST /api/graph-webhooks/lifecycle`
- `POST /api/graph-webhooks/subscriptions`
- `POST /api/graph-webhooks/subscriptions/{subscription_id}/renew`
- `DELETE /api/graph-webhooks/subscriptions/{subscription_id}`
Services:
- `app.services.builtin_workflows`
- `app.services.graph_client`
- `app.services.graph_email`
- `app.services.workflow_triggers`
Models/Schemas:
- `app.models.email_trigger_config`
- `app.models.graph_subscription`
- `app.models.microsoft_user`
- `app.models.organization`
- `app.models.user`
- `app.models.workflow`

### Guest Auth
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/guest_auth.py`
Prefixo: `/api/auth`

Endpoints:
- `POST /api/auth/guest`
- `POST /api/auth/guest/from-share/{token}`
- `GET /api/auth/guest/me`
- `POST /api/auth/guest/invalidate`
Services:
- —
Models/Schemas:
- `app.models.guest_session`
- `app.models.shared_space`
- `app.schemas.guest`

### Health
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/health.py`
Prefixo: `/api`

Endpoints:
- `GET /api/health/rag`
- `GET /api/health/rag/opensearch`
- `GET /api/health/rag/qdrant`
- `POST /api/health/rag/reset-circuits`
Services:
- `app.services.rag.core.resilience`
- `app.services.rag.storage.opensearch_service`
- `app.services.rag.storage.qdrant_service`
Models/Schemas:
- `app.models.user`

### Jobs
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/jobs.py`
Prefixo: `/api/jobs`

Endpoints:
- `GET /api/jobs/{jobid}/stream`
- `POST /api/jobs/start`
- `POST /api/jobs/{jobid}/resume`
- `GET /api/jobs/{jobid}/status`
Services:
- `app.services.ai.checklist_parser`
- `app.services.ai.citations.base`
- `app.services.ai.document_store`
- `app.services.ai.langgraph_legal_workflow`
- `app.services.ai.model_registry`
- `app.services.ai.nodes.catalogo_documentos`
- `app.services.ai.orchestration.router`
- `app.services.ai.quality_profiles`
- `app.services.ai.rag_memory_store`
- `app.services.api_call_tracker`
- `app.services.billing_quote_service`
- `app.services.billing_service`
- `app.services.chat_history`
- `app.services.context_strategy`
- `app.services.document_extraction_service`
- `app.services.job_manager`
- `app.services.model_registry`
- `app.services.poe_like_billing`
- `app.services.rag_policy`
- `app.services.token_budget_service`
Models/Schemas:
- `app.models.document`
- `app.models.user`
- `app.models.workflow_state`

### Knowledge
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/knowledge.py`
Prefixo: `/api/knowledge`

Endpoints:
- `GET /api/knowledge/legislation/search`
- `GET /api/knowledge/jurisprudence/search`
- `GET /api/knowledge/web/search`
- `POST /api/knowledge/verify-citations`
- `POST /api/knowledge/shepardize`
Services:
- `app.services.jurisprudence_service`
- `app.services.jurisprudence_verifier`
- `app.services.legislation_service`
- `app.services.web_search_service`
Models/Schemas:
- `app.models.document`
- `app.schemas.citation_verification`

### Library
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/library.py`
Prefixo: `/api/library`

Endpoints:
- `GET /api/library`
- `POST /api/library`
- `DELETE /api/library/{item_id}`
- `GET /api/library/items`
- `POST /api/library/items`
- `GET /api/library/folders`
- `POST /api/library/folders`
- `GET /api/library/librarians`
- `POST /api/library/librarians`
- `POST /api/library/librarians/{librarian_id}/activate`
- `POST /api/library/share`
- `GET /api/library/shares`
- `POST /api/library/shares/accept`
- `POST /api/library/shares/reject`
- `POST /api/library/shares/revoke`
Services:
- —
Models/Schemas:
- `app.models.document`
- `app.models.library`
- `app.models.user`
- `app.schemas.library`

### Marketplace
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/marketplace.py`
Prefixo: `/api/marketplace`

Endpoints:
- `GET /api/marketplace/categories`
- `GET /api/marketplace/{item_id}`
- `DELETE /api/marketplace/{item_id}`
- `POST /api/marketplace/{item_id}/install`
- `POST /api/marketplace/{item_id}/review`
- `GET /api/marketplace/{item_id}/reviews`
Services:
- —
Models/Schemas:
- `app.models.library`
- `app.models.marketplace`
- `app.models.workflow`
- `app.schemas.marketplace`

### Mcp
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/mcp.py`
Prefixo: `/api/mcp`

Endpoints:
- `GET /api/mcp/servers`
- `POST /api/mcp/tools/search`
- `POST /api/mcp/tools/call`
- `POST /api/mcp/gateway/rpc`
- `GET /api/mcp/gateway/sse`
- `GET /api/mcp/gateway/tools`
- `POST /api/mcp/gateway/approve/{approval_id}`
- `GET /api/mcp/gateway/audit`
- `GET /api/mcp/user-servers`
- `POST /api/mcp/user-servers`
- `DELETE /api/mcp/user-servers/{label}`
- `POST /api/mcp/user-servers/{label}/test`
Services:
- `app.services.ai.tool_gateway`
- `app.services.ai.tool_gateway.tool_registry`
- `app.services.mcp_hub`
Models/Schemas:
- `app.models.user`

### Mcp Bnp
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/mcp_bnp.py`
Prefixo: `/api/mcp/bnp`

Endpoints:
- `POST /api/mcp/bnp/rpc`
Services:
- `app.services.mcp_servers.bnp_server`
Models/Schemas:
- —

### Microsoft Sso
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/microsoft_sso.py`
Prefixo: `/api/auth`

Endpoints:
- `POST /api/auth/microsoft-sso`
- `POST /api/auth/teams-sso`
Services:
- —
Models/Schemas:
- `app.schemas.microsoft_auth`

### Models
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/models.py`
Prefixo: `/api/models`

Endpoints:
- `POST /api/models/route`
- `GET /api/models/routes`
- `GET /api/models/metrics`
- `GET /api/models/available`
- `GET /api/models/agentic-flags`
- `PUT /api/models/agentic-flags`
- `DELETE /api/models/agentic-flags/{flag_key}`
Services:
- `app.services.ai.model_registry`
- `app.services.ai.model_router`
- `app.services.ai.shared.feature_flags`
- `app.services.audit_logger`
Models/Schemas:
- `app.models.user`

### Organizations
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/organizations.py`
Prefixo: `/api/organizations`

Endpoints:
- `POST /api/organizations`
- `GET /api/organizations/current`
- `PUT /api/organizations/current`
- `GET /api/organizations/members`
- `POST /api/organizations/members/invite`
- `PUT /api/organizations/members/{user_id}/role`
- `DELETE /api/organizations/members/{user_id}`
- `POST /api/organizations/teams`
- `GET /api/organizations/teams`
- `GET /api/organizations/teams/mine`
- `POST /api/organizations/teams/{team_id}/members`
- `DELETE /api/organizations/teams/{team_id}/members/{user_id}`
Services:
- —
Models/Schemas:
- `app.models.organization`
- `app.models.user`
- `app.schemas.organization`

### Outlook Addin
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/outlook_addin.py`
Prefixo: `/api/outlook-addin`

Endpoints:
- `POST /api/outlook-addin/summarize`
- `POST /api/outlook-addin/classify`
- `POST /api/outlook-addin/extract-deadlines`
- `POST /api/outlook-addin/workflow/trigger`
- `GET /api/outlook-addin/workflow/status/{run_id}`
Services:
- `app.services.builtin_workflows`
- `app.services.outlook_addin_service`
Models/Schemas:
- `app.models.organization`
- `app.models.user`
- `app.models.workflow`
- `app.schemas.outlook_addin_schemas`

### Playbooks
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/playbooks.py`
Prefixo: `/api/playbooks`

Endpoints:
- `GET /api/playbooks/{playbook_id}`
- `PUT /api/playbooks/{playbook_id}`
- `DELETE /api/playbooks/{playbook_id}`
- `POST /api/playbooks/{playbook_id}/rules`
- `PUT /api/playbooks/{playbook_id}/rules/{rule_id}`
- `DELETE /api/playbooks/{playbook_id}/rules/{rule_id}`
- `POST /api/playbooks/{playbook_id}/rules/reorder`
- `POST /api/playbooks/{playbook_id}/share`
- `DELETE /api/playbooks/{playbook_id}/share/{share_id}`
- `POST /api/playbooks/{playbook_id}/duplicate`
- `POST /api/playbooks/generate`
- `POST /api/playbooks/import`
- `POST /api/playbooks/extract-from-contracts`
- `POST /api/playbooks/import-document`
- `POST /api/playbooks/import-document/confirm`
- `GET /api/playbooks/{playbook_id}/export`
- `POST /api/playbooks/{playbook_id}/analyze/{document_id}`
- `GET /api/playbooks/{playbook_id}/analyses`
- `GET /api/playbooks/{playbook_id}/analyses/{analysis_id}`
- `PATCH /api/playbooks/{playbook_id}/analyses/{analysis_id}/review`
- `GET /api/playbooks/{playbook_id}/prompt`
- `GET /api/playbooks/{playbook_id}/versions`
Services:
- `app.services.document_extraction_service`
- `app.services.playbook_service`
Models/Schemas:
- `app.models.playbook`
- `app.models.user`
- `app.schemas.playbook`
- `app.schemas.playbook_analysis`

### Quality Control
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/quality_control.py`
Prefixo: `/api/quality`

Endpoints:
- `POST /api/quality/validate`
- `POST /api/quality/fix`
- `POST /api/quality/regenerate-word`
- `GET /api/quality/health`
- `POST /api/quality/analyze`
- `POST /api/quality/apply-approved`
- `POST /api/quality/convert-to-hil`
- `POST /api/quality/apply-unified-hil`
- `POST /api/quality/generate-checklist`
- `POST /api/quality/validate-hearing`
- `POST /api/quality/analyze-hearing-segments`
- `POST /api/quality/generate-hearing-checklist`
Services:
- `app.services.legal_checklist_generator`
- `app.services.quality_service`
Models/Schemas:
- —

### Rag
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/rag.py`
Prefixo: `/api/rag`

Endpoints:
- `POST /api/rag/search`
- `POST /api/rag/ingest/local`
- `POST /api/rag/ingest/global`
- `DELETE /api/rag/local/{case_id}`
- `GET /api/rag/stats`
- `GET /api/rag/metrics`
- `POST /api/rag/smart-search`
- `POST /api/rag/smart-ingest`
- `GET /api/rag/embedding-router/stats`
- `POST /api/rag/embeddings/compare`
Services:
- `app.services.rag.config`
- `app.services.rag.core.contextual_embeddings`
- `app.services.rag.core.embeddings`
- `app.services.rag.core.graph_factory`
- `app.services.rag.core.graph_rag`
- `app.services.rag.core.kg_builder.pipeline`
- `app.services.rag.core.metrics`
- `app.services.rag.core.neo4j_mvp`
- `app.services.rag.core.result_cache`
- `app.services.rag.embedding_router`
- `app.services.rag.jurisbert_embeddings`
- `app.services.rag.kanon_embeddings`
- `app.services.rag.legal_embeddings`
- `app.services.rag.pipeline`
- `app.services.rag.utils.ingest`
- `app.services.rag.voyage_embeddings`
- `app.services.rag_module`
- `app.services.rag_policy`
Models/Schemas:
- `app.models.user`

### Review Tables
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/review_tables.py`
Prefixo: `/api/review-tables`

Endpoints:
- `GET /api/review-tables/templates`
- `GET /api/review-tables/templates/system`
- `GET /api/review-tables/templates/{template_id}`
- `POST /api/review-tables/templates`
- `POST /api/review-tables/templates/seed`
- `POST /api/review-tables/columns/generate`
- `POST /api/review-tables/{review_id}/columns/generate`
- `POST /api/review-tables/from-template`
- `GET /api/review-tables/{review_id}`
- `POST /api/review-tables/{review_id}/process`
- `POST /api/review-tables/{review_id}/fill`
- `GET /api/review-tables/{review_id}/export`
- `POST /api/review-tables/{review_id}/export/xlsx`
- `POST /api/review-tables/{review_id}/export/csv`
- `PATCH /api/review-tables/{review_id}/cell`
- `GET /api/review-tables/{review_id}/cell-history`
- `PATCH /api/review-tables/{table_id}/cells/{cell_id}/verify`
- `POST /api/review-tables/{table_id}/cells/bulk-verify`
- `GET /api/review-tables/{table_id}/verification-stats`
- `GET /api/review-tables/{table_id}/cells/low-confidence`
- `GET /api/review-tables/{table_id}/cells/{cell_id}/source`
- `GET /api/review-tables/{table_id}/cells`
- `POST /api/review-tables/{review_id}/query`
- `POST /api/review-tables/{table_id}/chat`
- `GET /api/review-tables/{table_id}/chat/history`
- `DELETE /api/review-tables/{table_id}/chat/history`
- `GET /api/review-tables/{table_id}/chat/statistics`
- `POST /api/review-tables/{table_id}/dynamic-columns`
- `GET /api/review-tables/{table_id}/dynamic-columns`
- `GET /api/review-tables/{table_id}/dynamic-columns/{column_id}`
- `DELETE /api/review-tables/{table_id}/dynamic-columns/{column_id}`
- `POST /api/review-tables/{table_id}/dynamic-columns/{column_id}/reprocess`
Services:
- `app.services.cell_verification_service`
- `app.services.column_builder_service`
- `app.services.review_table_service`
- `app.services.table_chat_service`
Models/Schemas:
- `app.models.document`
- `app.models.dynamic_column`
- `app.models.review_table`
- `app.models.table_chat`
- `app.models.user`

### Skills
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/skills.py`
Prefixo: `/api/skills`

Endpoints:
- `POST /api/skills/generate`
- `POST /api/skills/validate`
- `POST /api/skills/publish`
Services:
- `app.services.ai.skills.loader`
- `app.services.ai.skills.skill_builder`
Models/Schemas:
- `app.models.library`
- `app.models.user`
- `app.schemas.skills`

### Spaces
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/spaces.py`
Prefixo: `/api/spaces`

Endpoints:
- `POST /api/spaces`
- `GET /api/spaces`
- `GET /api/spaces/{space_id}`
- `PUT /api/spaces/{space_id}`
- `DELETE /api/spaces/{space_id}`
- `POST /api/spaces/{space_id}/invite`
- `GET /api/spaces/{space_id}/members`
- `DELETE /api/spaces/{space_id}/members/{member_email}`
- `POST /api/spaces/join/{token}`
- `POST /api/spaces/{space_id}/resources`
- `GET /api/spaces/{space_id}/resources`
- `DELETE /api/spaces/{space_id}/resources/{resource_id}`
Services:
- —
Models/Schemas:
- `app.models.shared_space`
- `app.models.user`
- `app.schemas.shared_space`

### Teams Bot
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/teams_bot.py`
Prefixo: `/api/teams-bot`

Endpoints:
- `POST /api/teams-bot/webhook`
- `POST /api/teams-bot/notify/{user_id}`
Services:
- `app.services.teams_bot.bot`
- `app.services.teams_bot.cards`
- `app.services.teams_bot.conversation_store`
Models/Schemas:
- —

### Templates
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/templates.py`
Prefixo: `/api/templates`

Endpoints:
- `GET /api/templates`
- `POST /api/templates`
- `PUT /api/templates/{template_id}`
- `POST /api/templates/{template_id}/duplicate`
- `DELETE /api/templates/{template_id}`
- `POST /api/templates/extract-variables`
- `POST /api/templates/apply`
- `GET /api/templates/{template_id}`
- `GET /api/templates/{template_id}/schema`
- `GET /api/templates/catalog/types`
- `GET /api/templates/catalog/defaults/{doc_kind}/{doc_subtype}`
- `POST /api/templates/catalog/validate`
- `POST /api/templates/catalog/parse`
- `POST /api/templates/preview`
- `GET /api/templates/legal`
- `GET /api/templates/legal/{template_id}`
- `GET /api/templates/legal/{template_id}/schema`
- `POST /api/templates/legal/{template_id}/render`
- `POST /api/templates/legal/{template_id}/import`
Services:
- `app.services.ai.nodes.catalogo_documentos`
- `app.services.ai.template_generator`
- `app.services.legal_templates`
- `app.services.template_service`
Models/Schemas:
- `app.models.library`
- `app.models.user`
- `app.schemas.smart_template`

### Transcription
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/transcription.py`
Prefixo: `/api/transcription`

Endpoints:
- `GET /api/transcription/pending`
- `POST /api/transcription/resume`
- `DELETE /api/transcription/cache/{file_hash}`
- `POST /api/transcription/export/docx`
- `POST /api/transcription/vomo/jobs`
- `POST /api/transcription/vomo/jobs/{job_id}/retry`
- `POST /api/transcription/vomo/jobs/url`
- `POST /api/transcription/hearing/jobs`
- `POST /api/transcription/hearing/jobs/url`
- `GET /api/transcription/jobs`
- `GET /api/transcription/jobs/{job_id}`
- `POST /api/transcription/jobs/{job_id}/cancel`
- `GET /api/transcription/jobs/{job_id}/result`
- `POST /api/transcription/jobs/{job_id}/convert-preventive-to-hil`
- `POST /api/transcription/jobs/{job_id}/audit-issues/merge`
- `DELETE /api/transcription/jobs/{job_id}`
- `GET /api/transcription/jobs/{job_id}/reports/{report_key}`
- `GET /api/transcription/jobs/{job_id}/media`
- `GET /api/transcription/jobs/{job_id}/media/list`
- `POST /api/transcription/jobs/{job_id}/preventive-audit/recompute`
- `POST /api/transcription/jobs/{job_id}/quality`
- `POST /api/transcription/jobs/{job_id}/content`
- `GET /api/transcription/jobs/{job_id}/stream`
- `POST /api/transcription/vomo`
- `POST /api/transcription/vomo/stream`
- `POST /api/transcription/vomo/batch/stream`
- `POST /api/transcription/apply-revisions`
- `POST /api/transcription/jobs/{job_id}/hearing/apply-revisions`
- `POST /api/transcription/hearing/stream`
- `POST /api/transcription/hearing/speakers`
- `POST /api/transcription/hearing/enroll`
Services:
- `app.services.api_call_tracker`
- `app.services.job_manager`
- `app.services.mlx_loader`
- `app.services.preventive_hil`
- `app.services.quality_service`
- `app.services.transcription_service`
Models/Schemas:
- `app.models.user`
- `app.schemas.transcription`

### Tribunais
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/tribunais.py`
Prefixo: `/api/tribunais`

Endpoints:
- `POST /api/tribunais/credentials/password`
- `POST /api/tribunais/credentials/certificate-a1`
- `POST /api/tribunais/credentials/certificate-a3-cloud`
- `POST /api/tribunais/credentials/certificate-a3-physical`
- `GET /api/tribunais/credentials/{user_id}`
- `DELETE /api/tribunais/credentials/{credential_id}`
- `GET /api/tribunais/processo/{credential_id}/{numero}`
- `GET /api/tribunais/processo/{credential_id}/{numero}/documentos`
- `GET /api/tribunais/processo/{credential_id}/{numero}/movimentacoes`
- `POST /api/tribunais/operations/sync`
- `POST /api/tribunais/operations/async`
- `GET /api/tribunais/operations/{job_id}`
- `POST /api/tribunais/peticionar`
Services:
- `app.services.tribunais_client`
Models/Schemas:
- `app.models.user`
- `app.schemas.tribunais`

### Users
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/users.py`
Prefixo: `/api/users`

Endpoints:
- `GET /api/users/profile`
- `PUT /api/users/profile`
- `GET /api/users/preferences`
- `PUT /api/users/preferences`
Services:
- —
Models/Schemas:
- `app.models.user`

### Webhooks
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/webhooks.py`
Prefixo: `/api/webhooks`

Endpoints:
- `POST /api/webhooks/tribunais`
- `POST /api/webhooks/tribunais/test`
- `POST /api/webhooks/generic/{service}`
Services:
- —
Models/Schemas:
- `app.schemas.tribunais`

### Word Addin
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/word_addin.py`
Prefixo: `/api/word-addin`

Endpoints:
- `POST /api/word-addin/analyze-content`
- `POST /api/word-addin/edit-content`
- `POST /api/word-addin/translate`
- `POST /api/word-addin/anonymize`
- `POST /api/word-addin/playbook/run`
- `GET /api/word-addin/playbook/run/{playbook_run_id}/restore`
- `POST /api/word-addin/redline/apply`
- `POST /api/word-addin/redline/reject`
- `POST /api/word-addin/redline/apply-all`
- `GET /api/word-addin/playbook/list`
- `POST /api/word-addin/redline/state/{playbook_run_id}/{redline_id}/applied`
- `POST /api/word-addin/redline/state/{playbook_run_id}/{redline_id}/rejected`
- `GET /api/word-addin/redline/state/{playbook_run_id}`
- `GET /api/word-addin/user/playbook-runs`
- `POST /api/word-addin/playbook/recommend`
- `GET /api/word-addin/playbook/run/{playbook_run_id}/audit-report`
Services:
- `app.services.redline_service`
- `app.services.word_addin_service`
Models/Schemas:
- `app.models.playbook`
- `app.models.playbook_run_cache`
- `app.models.redline_state`
- `app.models.user`
- `app.schemas.word_addin`

### Workflows
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/api/endpoints/workflows.py`
Prefixo: `/api/workflows`

Endpoints:
- `GET /api/workflows/catalog`
- `POST /api/workflows/templates/seed`
- `POST /api/workflows/{workflow_id}/clone`
- `POST /api/workflows/{workflow_id}/improve`
- `POST /api/workflows/generate-from-nl`
- `GET /api/workflows/admin/dashboard`
- `GET /api/workflows/admin/approval-queue`
- `GET /api/workflows/{workflow_id}`
- `PUT /api/workflows/{workflow_id}`
- `DELETE /api/workflows/{workflow_id}`
- `GET /api/workflows/{workflow_id}/files`
- `POST /api/workflows/{workflow_id}/files`
- `DELETE /api/workflows/{workflow_id}/files/{file_id}`
- `POST /api/workflows/{workflow_id}/versions`
- `GET /api/workflows/{workflow_id}/versions`
- `GET /api/workflows/{workflow_id}/versions/{version_number}`
- `POST /api/workflows/{workflow_id}/versions/{version_number}/restore`
- `POST /api/workflows/{workflow_id}/submit`
- `POST /api/workflows/{workflow_id}/approve`
- `POST /api/workflows/{workflow_id}/publish`
- `POST /api/workflows/{workflow_id}/unpublish`
- `GET /api/workflows/app/{slug}`
- `POST /api/workflows/{workflow_id}/archive`
- `POST /api/workflows/{workflow_id}/run`
- `POST /api/workflows/{workflow_id}/test`
- `GET /api/workflows/runs/{run_id}/export/{format}`
- `POST /api/workflows/runs/{run_id}/resume`
- `POST /api/workflows/runs/{run_id}/follow-up`
- `POST /api/workflows/runs/{run_id}/share`
- `POST /api/workflows/runs/{run_id}/share-org`
- `GET /api/workflows/{workflow_id}/audit`
- `GET /api/workflows/{workflow_id}/runs`
- `GET /api/workflows/{workflow_id}/schedule`
- `PUT /api/workflows/{workflow_id}/schedule`
- `POST /api/workflows/{workflow_id}/trigger`
- `GET /api/workflows/{workflow_id}/permissions`
- `POST /api/workflows/{workflow_id}/permissions`
- `DELETE /api/workflows/{workflow_id}/permissions/{user_id}`
Services:
- `app.services.ai.agent_clients`
- `app.services.ai.model_registry`
- `app.services.ai.nl_to_graph`
- `app.services.ai.workflow_compiler`
- `app.services.ai.workflow_runner`
- `app.services.unified_context_store`
- `app.services.workflow_export_service`
- `app.services.workflow_permission_service`
Models/Schemas:
- `app.models.user`
- `app.models.workflow`
- `app.models.workflow_permission`

## Outros backends no repo

### Juridico AI API (SSE)
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/juridico_api.py`
Prefixo: (sem `/api`)

Endpoints:
- `POST /jobs`
- `GET /jobs/{job_id}/stream`
- `GET /jobs/{job_id}`
- `GET /templates`
- `GET /modes`
- `GET /health`
Services:
- `juridico_gemini.LegalDrafter` (engine de geração)
- `job_manager` (persistência de jobs)
Models/Schemas:
- `JobConfig` (Pydantic local)
- `JobStatus` (Pydantic local)

### MCP Legal Server
Arquivo: `/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/mcp-legal-server/main.py`
Prefixo: (sem `/api`)

Endpoints:
- `GET /health`
- `POST /rpc`
Services:
- (implementação local MCP server)
Models/Schemas:
- —
