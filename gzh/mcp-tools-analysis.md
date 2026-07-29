# Cruxible MCP 工具全景分析报告

> 分析日期：2026-07-29
> 工具总数：81
> 权限分级：READ_ONLY 只读 / GOVERNED_WRITE 受控写入 / GRAPH_WRITE 图写入 / ADMIN 管理

---

## 查询与读取（17 个）

| 工具名 | 权限 | 说明 |
|--------|------|------|
| `cruxible_describe_query` | 只读 | Use when you need the purpose, parameters, and result shape for one named query. |
| `cruxible_get_entity` | 只读 | Use when you need to fetch one entity by type and ID. The payload defaults to th… |
| `cruxible_get_feedback_profile` | 只读 | Use when you need the allowed feedback codes and guidance for a relationship typ… |
| `cruxible_get_group` | 只读 | Use when you need the details and members for one candidate relationship group. |
| `cruxible_get_outcome_profile` | 只读 | Use when you need the allowed outcome codes and guidance for a decision surface. |
| `cruxible_get_relationship` | 只读 | Use when you need to fetch one relationship by endpoints and relationship type. |
| `cruxible_list` | 只读 | Use when you need a paged list of entities, relationships, receipts, feedback, o… |
| `cruxible_list_groups` | 只读 | Use when you need to find candidate relationship groups by type, status, or page… |
| `cruxible_list_queries` | 只读 | Use when you need to discover the named queries available in the active config. … |
| `cruxible_list_resolutions` | 只读 | Use when you need to review past group decisions by relationship type or action. |
| `cruxible_query` | 只读 | Use when you need to run a named query from the active config and receive matchi… |
| `cruxible_query_inline` | 只读 | Use when you need a one-off bounded graph query without adding it to the config.… |
| `cruxible_sample` | 只读 | Use when you need example entities of one type before writing a query or review.… |
| `cruxible_schema` | 只读 | Use when you need the active entity types, relationships, queries, workflows, an… |
| `cruxible_server_info` | 只读 | Use when you need live daemon details such as state directory, version, and how … |
| `cruxible_stats` | 只读 | Use when you need quick counts of entity and relationship types in an instance. |
| `cruxible_version` | 只读 | Use when you need to confirm which cruxible build this MCP server is running. |

## 实体与关系写入（3 个）

| 工具名 | 权限 | 说明 |
|--------|------|------|
| `cruxible_add_entity` | 图写入 | Use when you need to add or update a small number of explicit entities. |
| `cruxible_add_relationship` | 图写入 | Use when you need to add or update a small number of explicit relationships and … |
| `cruxible_batch_direct_write` | 图写入 | Use when you need to validate or apply one coherent batch of explicit entities a… |

## 治理与反馈（10 个）

| 工具名 | 权限 | 说明 |
|--------|------|------|
| `cruxible_evaluate` | 只读 | Use when you need graph quality findings such as orphaned entities, coverage gap… |
| `cruxible_feedback` | 受控写入 | Use when a person or reviewer agent adjudicated one explicit relationship and yo… |
| `cruxible_feedback_batch` | 受控写入 | Use when you need to record several relationship feedback decisions from the sam… |
| `cruxible_feedback_from_query` | 受控写入 | Use when a query receipt and result index identify the relationship that needs f… |
| `cruxible_group_status` | 只读 | Use when you need the latest status for a group or for a known group signature. |
| `cruxible_lint` | 只读 | Use when you need a combined quality report for config, graph state, feedback, a… |
| `cruxible_outcome` | 受控写入 | Use when you need to record what happened after a decision, query, workflow, or … |
| `cruxible_propose_group` | 受控写入 | Use when you need to create a review group for candidate relationship changes. |
| `cruxible_propose_workflow` | 受控写入 | Use when a workflow proposes reviewable relationship changes instead of writing … |
| `cruxible_resolve_group` | 图写入 | Use when a reviewer approves, rejects, or otherwise resolves a pending group. |

## 工作流与执行（0 个）

| 工具名 | 权限 | 说明 |
|--------|------|------|

## 配置与本体（21 个）

| 工具名 | 权限 | 说明 |
|--------|------|------|
| `cruxible_add_constraint` | 受控写入 | Use when you need to add a graph quality rule that future evaluations should che… |
| `cruxible_analyze_feedback` | 只读 | Use when you need patterns from recorded feedback, such as common corrections or… |
| `cruxible_analyze_outcomes` | 只读 | Use when you need patterns from recorded outcomes for a query, workflow, relatio… |
| `cruxible_apply_workflow` | 图写入 | Use when a workflow preview returned an apply digest and you are ready to commit… |
| `cruxible_config_status` | 只读 | Use when you need to check source drift or active config integrity. |
| `cruxible_enum_value_add` | 受控写入 | Use when a business user needs to extend an existing enum with new options — for… |
| `cruxible_init` | 只读 | Use when you need to create a governed instance from a config or reconnect to an… |
| `cruxible_inspect_entity` | 只读 | Use when you need everything relevant about one entity within a bounded number o… |
| `cruxible_inspect_entity_history` | 只读 | Use when you need receipt-derived property changes for one entity type or entity… |
| `cruxible_inspect_governance` | 只读 | Use when you need to review feedback, outcome, group, and policy settings. |
| `cruxible_inspect_ontology` | 只读 | Use when you need a compact overview of entity types, relationships, and rules. |
| `cruxible_inspect_overview` | 只读 | Use when you need a single high-level summary of the instance. |
| `cruxible_inspect_queries` | 只读 | Use when you need to understand configured queries and their parameters. |
| `cruxible_inspect_workflows` | 只读 | Use when you need to understand the workflows declared by the active config. |
| `cruxible_plan_workflow` | 只读 | Use when you need to preview the concrete steps a configured workflow would run … |
| `cruxible_relationship_lineage` | 只读 | Use when you need the provenance, review state, feedback, and receipts for one r… |
| `cruxible_reload_config` | 管理 | Use when you need to replace or reload the active config for an instance. |
| `cruxible_run_workflow` | 受控写入 | Use when you need to execute a configured workflow and receive its output, recei… |
| `cruxible_test_workflow` | 受控写入 | Use when you need to run workflow tests declared by the active config. |
| `cruxible_update_trust_status` | 图写入 | Use when you need to mark a prior group resolution as trusted, invalidated, or o… |
| `cruxible_validate` | 只读 | Use when you need to check whether a Cruxible config is valid before creating or… |

## 生命周期与状态（11 个）

| 工具名 | 权限 | 说明 |
|--------|------|------|
| `cruxible_clone_snapshot` | 管理 | Use when you need a new local instance created from an existing snapshot. On aut… |
| `cruxible_create_snapshot` | 受控写入 | Use when you need to mark the current state with a named snapshot. |
| `cruxible_instance_backup` | 管理 | Use when you need a portable same-identity backup of an instance, including its … |
| `cruxible_instance_relocate` | 管理 | Use when you need to move a healthy daemon-backed instance to a new directory wh… |
| `cruxible_instance_restore` | 管理 | Use when you need to restore a daemon-backed instance from a same-identity backu… |
| `cruxible_list_snapshots` | 只读 | Use when you need to browse available snapshots for an instance. |
| `cruxible_state_create_overlay` | 管理 | Use when you need a local overlay instance based on a published upstream state r… |
| `cruxible_state_publish` | 管理 | Use when you need to publish the current instance state as an immutable release. |
| `cruxible_state_pull_apply` | 受控写入 | Use when a pull preview returned an apply digest and you are ready to apply it. |
| `cruxible_state_pull_preview` | 只读 | Use when you need to preview upstream state changes before applying them. |
| `cruxible_state_status` | 只读 | Use when you need to see whether an overlay is connected to an upstream state an… |

## 决策记录（7 个）

| 工具名 | 权限 | 说明 |
|--------|------|------|
| `cruxible_abandon_decision_record` | 受控写入 | Use when a tracked decision should be closed without a final decision. |
| `cruxible_add_decision_policy` | 受控写入 | Use when you need to record a policy that affects how a decision surface should … |
| `cruxible_create_decision_record` | 受控写入 | Use when you need to open a tracked decision before gathering evidence, running … |
| `cruxible_finalize_decision_record` | 受控写入 | Use when a tracked decision has a final answer and rationale. |
| `cruxible_get_decision_record` | 只读 | Use when you need the current state and optional event history for one decision. |
| `cruxible_list_decision_events` | 只读 | Use when you need the event timeline for decisions, optionally filtered by recei… |
| `cruxible_list_decision_records` | 只读 | Use when you need to find decision records by status, subject, class, or page. |

## 溯源与证据（5 个）

| 工具名 | 权限 | 说明 |
|--------|------|------|
| `cruxible_dereference_source_evidence` | 只读 | Use when you need to read back a registered source evidence chunk and verify its… |
| `cruxible_get_trace` | 只读 | Use when you need the execution trace for one provider or workflow step. |
| `cruxible_list_traces` | 只读 | Use when you need to browse execution traces by workflow, provider, or page. |
| `cruxible_receipt` | 只读 | Use when you need to inspect the proof record for a previous query, write, workf… |
| `cruxible_register_source_artifact` | 受控写入 | Use when you need to register a source document so relationship evidence can cit… |

## 扩展与新工具（6 个）

| 工具名 | 权限 | 说明 |
|--------|------|------|
| `cruxible_discover_schema` | 受控写入 | Use when you need to reverse-engineer an ontology from an existing data source. … |
| `cruxible_entity_type_add` | 受控写入 | Use when a business user describes a new kind of entity that should be tracked i… |
| `cruxible_entity_type_update` | 受控写入 | Use when a business user wants to add new attributes to an existing entity type … |
| `cruxible_enum_add` | 受控写入 | Use when a business user defines a set of allowed values for a property — for ex… |
| `cruxible_ontology_describe` | 只读 | Use when an agent or user wants a high-level summary of the current ontology — w… |
| `cruxible_relationship_add` | 受控写入 | Use when a business user describes how two entity types connect — for example 'a… |

## 管理（1 个）

| 工具名 | 权限 | 说明 |
|--------|------|------|
| `cruxible_lock_workflow` | 管理 | Use when workflow inputs, providers, or artifacts changed and you need to refres… |


---

## 权限分布

| 权限等级 | 数量 | 累计 | 说明 |
|---------|------|------|------|
| READ_ONLY | 45 | 45 | 查询、统计、评估、描述等只读操作 |
| GOVERNED_WRITE | 22 | 67 | 受控写入——反馈、提案、本体编辑、数据源发现 |
| GRAPH_WRITE | 6 | 73 | 图数据直接写入——实体、关系、批量写入 |
| ADMIN | 8 | 81 | 实例生命周期、配置变更、克隆备份 |
