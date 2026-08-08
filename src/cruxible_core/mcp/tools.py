"""MCP tool registrations.

Each tool is a thin wrapper that delegates to handlers.py.
Exceptions propagate to FastMCP, which wraps them as ToolError.
"""

from __future__ import annotations

import asyncio
from functools import wraps
from typing import Any, Callable

from mcp.server.fastmcp import FastMCP
from pydantic import TypeAdapter

from cruxible_client import contracts
from cruxible_core import __version__
from cruxible_core.mcp import handlers
from cruxible_core.mcp.tool_prompts import tool_description


def register_tools(server: FastMCP, *, offload_sync_calls: bool = False) -> list[str]:
    """Register all cruxible tools on the FastMCP server.

    Args:
        server: FastMCP server receiving the registrations.
        offload_sync_calls: Run synchronous handlers outside the protocol event loop.

    Returns:
        List of registered tool names (for permission validation).
    """
    registered: list[str] = []

    def _tool(fn: Callable[..., Any]) -> Callable[..., Any]:
        """Register a tool on the server and track its name."""
        registered_fn = fn
        if offload_sync_calls:

            @wraps(fn)
            async def run_in_worker(*args: Any, **kwargs: Any) -> Any:
                # FastMCP invokes synchronous functions on its protocol event
                # loop; daemon HTTP waits must not starve tools/list.
                return await asyncio.to_thread(fn, *args, **kwargs)

            registered_fn = run_in_worker
        server.tool(description=tool_description(fn.__name__))(registered_fn)
        registered.append(fn.__name__)
        return fn

    @_tool
    def cruxible_version() -> dict[str, str]:
        """Return the cruxible-core version. Use this to confirm which build is running."""
        return {"version": __version__}

    @_tool
    def cruxible_server_info() -> contracts.ServerInfoResult:
        """Return live daemon metadata such as permission mode, state dir, and instance count."""
        return handlers.handle_server_info()

    @_tool
    def cruxible_init(
        root_dir: str,
        config_path: str | None = None,
        config_yaml: str | None = None,
        data_dir: str | None = None,
        kits: list[str] | None = None,
        bare: bool = False,
    ) -> contracts.InitResult:
        """Create or reload a governed daemon-backed instance.

        Provide `config_path`, `config_yaml`, or an ordered `kits`
        sequence when creating a new instance. Kit init composes the configured
        default base unless `bare=true`. In server mode, `config_path` is read locally and
        uploaded as config content; the daemon stores its own active
        copy. To reload after a restart, omit all three.
        """
        return handlers.handle_init(root_dir, config_path, config_yaml, data_dir, kits, bare)

    @_tool
    def cruxible_validate(
        config_path: str | None = None,
        config_yaml: str | None = None,
    ) -> contracts.ValidateResult:
        """Validate a config file or inline YAML without creating an instance.

        Provide exactly one of `config_path` (path to a YAML file) or
        `config_yaml` (raw YAML string).
        """
        return handlers.handle_validate(config_path, config_yaml)

    @_tool
    def cruxible_state_create_overlay(
        root_dir: str,
        transport_ref: str | None = None,
        state_ref: str | None = None,
        kit: str | None = None,
        no_kit: bool = False,
    ) -> contracts.StateOverlayResult:
        """Create a new governed overlay from a published state release."""
        return handlers.handle_create_state_overlay(
            root_dir=root_dir,
            transport_ref=transport_ref,
            state_ref=state_ref,
            kit=kit,
            no_kit=no_kit,
        )

    @_tool
    def cruxible_lock_workflow(
        instance_id: str | None = None,
        force: bool = False,
    ) -> contracts.WorkflowLockResult:
        """Generate the workflow lock file for the current instance config.

        Run this after changing providers, artifacts, or workflow config and
        before planning or executing workflows.
        
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_workflow_lock(instance_id, force=force)

    @_tool
    def cruxible_plan_workflow(
        workflow_name: str,
        instance_id: str | None = None,
        input_payload: dict[str, Any] | None = None,
    ) -> contracts.WorkflowPlanResult:
        """Compile a configured workflow into a concrete execution plan.
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_workflow_plan(
            instance_id,
            workflow_name,
            input_payload=input_payload,
        )

    @_tool
    def cruxible_run_workflow(
        workflow_name: str,
        instance_id: str | None = None,
        input_payload: dict[str, Any] | None = None,
        decision_record_id: str | None = None,
    ) -> contracts.WorkflowRunResult:
        """Execute a configured workflow and return receipts, traces, and output.

        Canonical workflows run in preview mode and return an `apply_digest`
        plus the current `head_snapshot_id`. To commit a canonical workflow,
        call `cruxible_apply_workflow` with those values.
        
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_workflow_run(
            instance_id,
            workflow_name,
            input_payload=input_payload,
            decision_record_id=decision_record_id,
        )

    @_tool
    def cruxible_apply_workflow(
        workflow_name: str,
        expected_apply_digest: str,
        instance_id: str | None = None,
        expected_head_snapshot_id: str | None = None,
        input_payload: dict[str, Any] | None = None,
        decision_record_id: str | None = None,
    ) -> contracts.WorkflowApplyResult:
        """Commit a previously previewed canonical workflow after verifying identity.
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_workflow_apply(
            instance_id,
            workflow_name,
            expected_apply_digest=expected_apply_digest,
            expected_head_snapshot_id=expected_head_snapshot_id,
            input_payload=input_payload,
            decision_record_id=decision_record_id,
        )

    @_tool
    def cruxible_test_workflow(
        instance_id: str | None = None,
        name: str | None = None,
    ) -> contracts.WorkflowTestResult:
        """Run configured workflow tests for an instance.
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_workflow_test(instance_id, name=name)

    @_tool
    def cruxible_query(
        query_name: str,
        instance_id: str | None = None,
        params: dict[str, Any] | None = None,
        limit: int | None = None,
        offset: int = 0,
        relationship_state: contracts.QueryVisibilityState | None = None,
        decision_record_id: str | None = None,
        profile: contracts.ReadProfile | None = None,
        layout: contracts.QueryLayout = "rows",
    ) -> dict[str, Any]:
        """Run a named query and return results plus a receipt.

        `params` must include the primary-key field of the query's
        entry_point entity type (e.g. if entry_point is Vehicle and its
        primary key is vehicle_id, pass {"vehicle_id": "V-123"}).
        Use `cruxible_schema` to find primary key fields.

        `receipt_id` is also promoted to top-level for follow-up tools.
        After querying, use `cruxible_receipt` to inspect the traversal
        proof showing exactly how results were derived.

        Use `limit` to cap the number of returned results and omit
        the inline receipt (fetch it later via `cruxible_receipt`).
        Use `offset` with `limit` to request later pages; ordering is
        deterministic per snapshot.

        `profile` shapes item payloads: `compact` (default here) returns
        bounded identity cards with governance markers; pass `standard`
        or `full` when you need provenance or actor context.

        `layout='graph'` replaces per-row `items` with the normalized graph
        transport: `nodes`/`edges` carry each unique entity and physical
        relationship once, `results` preserves row order as index
        references, and `paths` holds step-ref sequences (edge index plus
        traversal-step alias) for path-shaped results. Same information
        without per-row duplication — prefer it for multi-row traversal
        reads where you need the relational context.
        
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        # Returned as a plain dict: the result is a UNION of the rows and
        # graph contract models, and FastMCP wraps union-annotated returns
        # in a {"result": ...} envelope that would break the legacy
        # top-level payload shape for existing MCP consumers. The real
        # rows|graph union schema is still advertised — see
        # _publish_union_output_schemas.
        return handlers.handle_query(
            instance_id,
            query_name,
            params,
            limit=limit,
            offset=offset,
            relationship_state=relationship_state,
            decision_record_id=decision_record_id,
            profile=profile,
            layout=layout,
        ).model_dump(mode="json")

    @_tool
    def cruxible_query_inline(
        definition: contracts.InlineQueryDefinition,
        instance_id: str | None = None,
        params: dict[str, Any] | None = None,
        limit: int | None = None,
        relationship_state: contracts.QueryVisibilityState | None = None,
        decision_record_id: str | None = None,
        profile: contracts.ReadProfile | None = None,
        layout: contracts.QueryLayout = "rows",
    ) -> dict[str, Any]:
        """Run a bounded inline graph query for read-only agent exploration.

        Inline query definitions use the same JSON shape as configured named
        queries plus a required `name`, but they are not persisted to config.
        Use this for one-off filtering and candidate discovery. Promote repeated
        or workflow-critical queries into config as named queries.

        `profile` shapes item payloads: `compact` (default here) returns
        bounded identity cards with governance markers; pass `standard`
        or `full` when you need provenance or actor context.

        `layout='graph'` replaces per-row `items` with the normalized graph
        transport (`nodes`/`edges` once each, `results` as ordered index
        references, `paths` for path-shaped results), exactly as for
        `cruxible_query`.
        
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        # Returned as a plain dict: the result is a UNION of the rows and
        # graph contract models, and FastMCP wraps union-annotated returns
        # in a {"result": ...} envelope that would break the legacy
        # top-level payload shape for existing MCP consumers. The real
        # rows|graph union schema is still advertised — see
        # _publish_union_output_schemas.
        return handlers.handle_query_inline(
            instance_id,
            definition,
            params,
            limit=limit,
            relationship_state=relationship_state,
            decision_record_id=decision_record_id,
            profile=profile,
            layout=layout,
        ).model_dump(mode="json")

    @_tool
    def cruxible_list_queries(
        instance_id: str | None = None,
        detail: contracts.QueryListDetail = "summary",
        limit: int | None = None,
        offset: int = 0,
        continuation: str | None = None,
    ) -> dict[str, Any]:
        """List named queries as bounded summaries; `detail='full'` expands every definition.

        When `truncated` is true the response carries a `continuation_token`;
        pass it back as `continuation` (same `detail`) for the next page. A
        409 stale-continuation error means state changed — restart the read.

        Returns a dict rather than the QueryListResult | QueryListDetailResult
        union because FastMCP nests union returns under a `result` key, which
        would break the flat list-envelope shape shared by every list tool.
        The real union schema is still advertised via
        `_publish_union_output_schemas`.
        
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        result = handlers.handle_list_queries(
            instance_id,
            detail=detail,
            limit=limit,
            offset=offset,
            continuation=continuation,
        )
        return result.model_dump(mode="json")

    @_tool
    def cruxible_describe_query(
        query_name: str,
        instance_id: str | None = None,
    ) -> contracts.NamedQueryInfoResult:
        """Describe one named query with the details needed to invoke it correctly.
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_describe_query(instance_id, query_name)

    @_tool
    def cruxible_receipt(
        receipt_id: str,
        instance_id: str | None = None,
    ) -> dict[str, Any]:
        """Fetch a stored receipt by `receipt_id` from a previous query.
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_receipt(instance_id, receipt_id)

    @_tool
    def cruxible_get_trace(
        trace_id: str,
        instance_id: str | None = None,
    ) -> dict[str, Any]:
        """Fetch a provider execution trace by `trace_id`.
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_get_trace(instance_id, trace_id)

    @_tool
    def cruxible_list_traces(
        instance_id: str | None = None,
        workflow_name: str | None = None,
        provider_name: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> contracts.TraceListResult:
        """List provider execution trace summaries with optional workflow/provider filters.
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_list_traces(
            instance_id,
            workflow_name=workflow_name,
            provider_name=provider_name,
            limit=limit,
            offset=offset,
        )

    @_tool
    def cruxible_feedback(
        action: contracts.FeedbackAction,
        source: contracts.FeedbackSource,
        from_type: str,
        from_id: str,
        relationship_type: str,
        to_type: str,
        to_id: str,
        instance_id: str | None = None,
        edge_key: int | None = None,
        reason: str = "",
        reason_code: str | None = None,
        scope_hints: dict[str, Any] | None = None,
        corrections: dict[str, Any] | None = None,
        group_override: bool = False,
        receipt_id: str | None = None,
    ) -> contracts.FeedbackResult:
        """Record edge-level feedback by explicit relationship coordinates.

        ``source`` identifies who produced this feedback:
        ``"human"`` for human review, ``"agent"`` for AI agent review.

        Rejected edges are excluded from future query results.
        Approved edges are trusted in traversals.

        Use `corrections` with `action="correct"` and set `edge_key` only
        when disambiguation is needed. `applied=False` means the record was
        saved but the graph edge was not updated.

        Set `group_override=True` to mark the edge assertion metadata as a
        group override for group resolve. The edge must already exist in the
        graph.
        
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_feedback(
            instance_id=instance_id,
            receipt_id=receipt_id,
            action=action,
            source=source,
            from_type=from_type,
            from_id=from_id,
            relationship_type=relationship_type,
            to_type=to_type,
            to_id=to_id,
            edge_key=edge_key,
            reason=reason,
            reason_code=reason_code,
            scope_hints=scope_hints,
            corrections=corrections,
            group_override=group_override,
        )

    @_tool
    def cruxible_feedback_batch(
        items: list[contracts.FeedbackBatchItemInput],
        instance_id: str | None = None,
        source: contracts.FeedbackSource = "human",
    ) -> contracts.FeedbackBatchResult:
        """Record batch edge feedback under one top-level mutation receipt.
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_feedback_batch(instance_id, items, source=source)

    @_tool
    def cruxible_feedback_from_query(
        receipt_id: str,
        result_index: int,
        action: contracts.FeedbackAction,
        instance_id: str | None = None,
        source: contracts.FeedbackSource = "human",
        reason: str = "",
        reason_code: str | None = None,
        scope_hints: dict[str, Any] | None = None,
        corrections: dict[str, Any] | None = None,
        group_override: bool = False,
        path_index: int | None = None,
        path_alias: str | None = None,
    ) -> contracts.FeedbackResult:
        """Record edge feedback from one relationship/path row in a query receipt.

        This adjudicates one existing relationship assertion. It does not
        resolve candidate groups; use group resolution for group theses and
        member-set decisions.
        
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_feedback_from_query(
            instance_id,
            receipt_id=receipt_id,
            result_index=result_index,
            action=action,
            source=source,
            reason=reason,
            reason_code=reason_code,
            scope_hints=scope_hints,
            corrections=corrections,
            group_override=group_override,
            path_index=path_index,
            path_alias=path_alias,
        )

    @_tool
    def cruxible_outcome(
        outcome: contracts.OutcomeValue,
        instance_id: str | None = None,
        receipt_id: str | None = None,
        anchor_type: contracts.OutcomeAnchorType = "receipt",
        anchor_id: str | None = None,
        source: contracts.FeedbackSource = "human",
        outcome_code: str | None = None,
        scope_hints: dict[str, Any] | None = None,
        outcome_profile_key: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> contracts.OutcomeResult:
        """Record a structured outcome for a receipt or proposal resolution.
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_outcome(
            instance_id,
            outcome,
            receipt_id=receipt_id,
            anchor_type=anchor_type,
            anchor_id=anchor_id,
            source=source,
            outcome_code=outcome_code,
            scope_hints=scope_hints,
            outcome_profile_key=outcome_profile_key,
            detail=detail,
        )

    @_tool
    def cruxible_list(
        resource_type: contracts.ResourceType,
        instance_id: str | None = None,
        entity_type: str | None = None,
        relationship_type: str | None = None,
        query_name: str | None = None,
        receipt_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
        property_filter: dict[str, Any] | None = None,
        where: dict[str, dict[str, Any]] | None = None,
        operation_type: str | None = None,
        fields: list[str] | None = None,
        relationship_state: contracts.QueryVisibilityState | None = None,
        profile: contracts.ReadProfile | None = None,
        continuation: str | None = None,
    ) -> contracts.ListResult:
        """List `entities|edges|receipts|feedback|outcomes` with optional filters.

        `entity_type` is required for `resource_type="entities"`.
        `relationship_type` filters edges by type for `resource_type="edges"`.
        `property_filter` filters by exact property matches (AND semantics).
        Applies to `resource_type="entities"` and `resource_type="edges"`.
        `where` filters entity/edge properties with bounded operators such as
        `{"status": {"eq": "active"}}`, `{"title": {"contains": "query"}}`,
        or `{"status": {"in": ["active", "planned"]}}`.
        `fields` projects entity properties for `resource_type="entities"`.
        `operation_type` filters receipts (e.g. "query", "add_entity", "ingest").
        `relationship_state` is the read-visibility selector (`live|accepted|all|
        not-live|pending|reviewable`): for entities it gates by lifecycle, for
        edges by review+lifecycle. Entities default to `live`; edges return all
        stored edges unless a selector is given.
        `profile` shapes entity/edge item payloads: `compact` (default here)
        returns bounded identity cards with governance markers; pass `standard`
        or `full` when you need provenance or actor context.

        Edge items include `edge_key` for use with `cruxible_feedback` when
        multiple edges exist between the same endpoints.

        Pagination loop: when `truncated` is true the response carries a
        `continuation_token` — pass it back as `continuation` with the SAME
        filters to fetch the next page. A 409 stale-continuation error means
        state mutated between pages; restart from the first page.
        
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_list(
            instance_id,
            resource_type,
            entity_type=entity_type,
            relationship_type=relationship_type,
            query_name=query_name,
            receipt_id=receipt_id,
            limit=limit,
            offset=offset,
            property_filter=property_filter,
            where=where,
            operation_type=operation_type,
            fields=fields,
            relationship_state=relationship_state,
            profile=profile,
            continuation=continuation,
        )

    @_tool
    def cruxible_evaluate(
        instance_id: str | None = None,
        max_findings: int = 100,
        exclude_orphan_types: list[str] | None = None,
        severity_filter: list[contracts.FindingSeverity] | None = None,
        category_filter: list[contracts.FindingCategory] | None = None,
    ) -> contracts.EvaluateResult:
        """Run graph quality checks (orphans, gaps, violations, co-members).

        Checks: orphan entities, coverage gaps, constraint violations,
        candidate opportunities, governed support state, and unreviewed
        co-members (entities sharing an intermediary with a cross-referenced
        entity but lacking a cross-reference edge themselves).

        Use `exclude_orphan_types` to skip reference/taxonomy entity types
        (e.g. ``["PCDBPartType"]``) that are expected to be unconnected.
        Use `severity_filter` and `category_filter` to ask narrow triage
        questions while preserving full pre-filter summary counts.
        
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_evaluate(
            instance_id,
            max_findings=max_findings,
            exclude_orphan_types=exclude_orphan_types,
            severity_filter=severity_filter,
            category_filter=category_filter,
        )

    @_tool
    def cruxible_stats(instance_id: str | None = None) -> contracts.StatsResult:
        """Return graph counts, relationship counts, and head snapshot metadata.
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_stats(instance_id)

    @_tool
    def cruxible_lint(
        instance_id: str | None = None,
        max_findings: int = 100,
        analysis_limit: int = 200,
        min_support: int = 5,
        exclude_orphan_types: list[str] | None = None,
    ) -> contracts.LintResult:
        """Run aggregate read-only config, graph, feedback, and outcome checks.
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_lint(
            instance_id,
            max_findings=max_findings,
            analysis_limit=analysis_limit,
            min_support=min_support,
            exclude_orphan_types=exclude_orphan_types,
        )

    @_tool
    def cruxible_get_feedback_profile(
        relationship_type: str,
        instance_id: str | None = None,
    ) -> contracts.FeedbackProfileResult:
        """Return the configured feedback profile for one relationship type.
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_get_feedback_profile(instance_id, relationship_type)

    @_tool
    def cruxible_analyze_feedback(
        relationship_type: str,
        instance_id: str | None = None,
        limit: int = 200,
        min_support: int = 5,
        decision_surface_type: str | None = None,
        decision_surface_name: str | None = None,
        property_pairs: list[contracts.PropertyPairInput] | None = None,
    ) -> contracts.AnalyzeFeedbackResult:
        """Analyze structured feedback into deterministic remediation suggestions.
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_analyze_feedback(
            instance_id,
            relationship_type,
            limit=limit,
            min_support=min_support,
            decision_surface_type=decision_surface_type,
            decision_surface_name=decision_surface_name,
            property_pairs=property_pairs,
        )

    @_tool
    def cruxible_get_outcome_profile(
        anchor_type: contracts.OutcomeAnchorType,
        instance_id: str | None = None,
        relationship_type: str | None = None,
        workflow_name: str | None = None,
        surface_type: str | None = None,
        surface_name: str | None = None,
    ) -> contracts.OutcomeProfileResult:
        """Return the configured outcome profile for one anchor context.
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_get_outcome_profile(
            instance_id,
            anchor_type=anchor_type,
            relationship_type=relationship_type,
            workflow_name=workflow_name,
            surface_type=surface_type,
            surface_name=surface_name,
        )

    @_tool
    def cruxible_analyze_outcomes(
        anchor_type: contracts.OutcomeAnchorType,
        instance_id: str | None = None,
        relationship_type: str | None = None,
        workflow_name: str | None = None,
        query_name: str | None = None,
        surface_type: str | None = None,
        surface_name: str | None = None,
        limit: int = 200,
        min_support: int = 5,
    ) -> contracts.AnalyzeOutcomesResult:
        """Analyze structured outcomes into trust and debugging suggestions.
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_analyze_outcomes(
            instance_id,
            anchor_type=anchor_type,
            relationship_type=relationship_type,
            workflow_name=workflow_name,
            query_name=query_name,
            surface_type=surface_type,
            surface_name=surface_name,
            limit=limit,
            min_support=min_support,
        )

    @_tool
    def cruxible_schema(instance_id: str | None = None) -> dict[str, Any]:
        """Return the active config schema for an instance.
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_schema(instance_id)

    @_tool
    def cruxible_sample(
        entity_type: str,
        instance_id: str | None = None,
        limit: int = 5,
        fields: list[str] | None = None,
        profile: contracts.ReadProfile | None = None,
    ) -> contracts.SampleResult:
        """Return up to `limit` entities for quick data inspection.

        `profile` shapes item payloads: `compact` (default here) returns
        bounded identity cards; pass `standard` or `full` for full
        property bags and metadata.
        
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_sample(instance_id, entity_type, limit, fields, profile=profile)

    @_tool
    def cruxible_inspect_entity(
        entity_type: str,
        entity_id: str,
        instance_id: str | None = None,
        direction: str = "both",
        relationship_type: str | None = None,
        limit: int | None = None,
        depth: int | None = None,
        relationship_types: list[str] | None = None,
        target_types: list[str] | None = None,
        state: contracts.QueryVisibilityState | None = None,
        projection: list[str] | None = None,
        max_nodes: int | None = None,
        max_edges: int | None = None,
        profile: contracts.ReadProfile | None = None,
        continuation: str | None = None,
    ) -> dict[str, Any]:
        """THE generic bounded neighborhood read: anchor on one entity, expand outward.

        Answer "everything relevant about X within N hops" in ONE call
        instead of stitching multiple named queries. Anchor -> expand:
        `depth` (1-4) sets the hop horizon; `max_nodes` (default 100, cap
        500) and `max_edges` (default 200, cap 1000) are explicit budgets —
        the response reports `truncated` + `truncation_reasons`
        (node_budget/edge_budget/depth) instead of silently clipping.
        Filters: `relationship_types` (repeatable; unions with the legacy
        `relationship_type`), `target_types` (only expand into/return these
        entity types; the anchor is exempt), `direction`. `state` selects
        relationship visibility exactly like named-query traversal
        (live/accepted/all/not-live/pending/reviewable; default all —
        every stored edge with its review/lifecycle markers, matching the
        inspection contract of the single-hop read and `list edges`).
        An explicit non-`all` state filters exactly like traversal and the
        response reports `edges_hidden_by_state`: edges at the explored
        frontier that passed every other filter but were hidden by state
        alone (no budget consumed; regions behind hidden edges are not
        speculatively counted).
        `projection` (repeatable) trims neighbor properties to the named
        ones; `profile` still shapes metadata. Providing any of these
        returns the expanded nodes/edges shape; a bare call keeps the
        legacy single-hop `neighbors` shape.

        Pagination loop: when the expanded read reports `truncated` on a
        budget it carries a `continuation_token` — pass it back as
        `continuation` with the SAME structural parameters to resume the
        expansion where the budget stopped it. A 409 stale-continuation
        error means state mutated between pages; restart the read.
        
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        # Returned as a plain dict: the result is a UNION of the legacy and
        # expanded contract models, and FastMCP wraps union-annotated returns
        # in a {"result": ...} envelope that would break the legacy top-level
        # payload shape for existing MCP consumers. The real union schema is
        # still advertised — see _publish_union_output_schemas.
        return handlers.handle_inspect_entity(
            instance_id,
            entity_type,
            entity_id,
            direction=direction,
            relationship_type=relationship_type,
            limit=limit,
            depth=depth,
            relationship_types=relationship_types,
            target_types=target_types,
            state=state,
            projection=projection,
            max_nodes=max_nodes,
            max_edges=max_edges,
            profile=profile,
            continuation=continuation,
        ).model_dump(mode="json")

    @_tool
    def cruxible_inspect_entity_history(
        entity_type: str,
        instance_id: str | None = None,
        entity_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> contracts.EntityChangeHistoryResult:
        """Inspect receipt-derived entity property changes for one entity type or entity.
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_inspect_entity_history(
            instance_id,
            entity_type,
            entity_id=entity_id,
            limit=limit,
            offset=offset,
        )

    @_tool
    def cruxible_inspect_ontology(
        instance_id: str | None = None,
    ) -> contracts.CanonicalViewResult:
        """Return the structured canonical ontology view for an instance.
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_inspect_view(instance_id, "ontology")

    @_tool
    def cruxible_inspect_workflows(
        instance_id: str | None = None,
    ) -> contracts.CanonicalViewResult:
        """Return the structured canonical workflow view for an instance.
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_inspect_view(instance_id, "workflows")

    @_tool
    def cruxible_inspect_queries(
        instance_id: str | None = None,
    ) -> contracts.CanonicalViewResult:
        """Return the structured canonical query view for an instance.
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_inspect_view(instance_id, "queries")

    @_tool
    def cruxible_inspect_governance(
        instance_id: str | None = None,
        limit: int = 200,
    ) -> contracts.CanonicalViewResult:
        """Return the structured canonical governance view for an instance.
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_inspect_view(instance_id, "governance", limit=limit)

    @_tool
    def cruxible_inspect_overview(
        instance_id: str | None = None,
        limit: int = 200,
    ) -> contracts.CanonicalViewResult:
        """Return the structured canonical overview view for an instance.
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_inspect_view(instance_id, "overview", limit=limit)

    @_tool
    def cruxible_add_relationship(
        relationships: list[contracts.RelationshipInput],
        instance_id: str | None = None,
        dry_run: bool = False,
    ) -> contracts.AddRelationshipResult:
        """Add or update relationships in the graph (upsert).

        Each relationship needs: from_type, from_id, relationship_type, to_type, to_id.
        Optional properties must be declared by the relationship schema.
        Entities must already exist. Re-submitting an existing edge merges
        declared domain properties while preserving relationship metadata.
        Optional evidence_refs and source_evidence attach provenance to the live
        edge, but do not mark it as group-reviewed accepted state.

        For governed judgment relationships, prefer candidate group proposal
        flows so Cruxible can preserve tri-state signal-source evidence
        (support, unsure, contradict) and review history.

        Batch size: practical limit is ~500 relationships per call.
        For bulk loading, use workflow dataflow steps plus apply_relationships.
        
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_add_relationship(instance_id, relationships, dry_run=dry_run)

    @_tool
    def cruxible_add_entity(
        entities: list[contracts.EntityInput],
        instance_id: str | None = None,
        dry_run: bool = False,
    ) -> contracts.AddEntityResult:
        """Add or update entities in the graph (upsert).

        Each entity needs: entity_type, entity_id.
        Optional properties and metadata dicts. Re-submitting an existing
        entity merges properties and metadata.
        Use for entities from free text or external sources when CSV ingestion
        is not available.
        
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_add_entity(instance_id, entities, dry_run=dry_run)

    @_tool
    def cruxible_batch_direct_write(
        payload: contracts.BatchDirectWritePayload,
        instance_id: str | None = None,
        dry_run: bool = False,
    ) -> contracts.BatchDirectWriteResult:
        """Validate or apply a direct batch graph write payload.

        Use this for coherent hard-state slices that contain entities and
        relationships. The payload may define top-level shared_evidence entries
        and reference them from relationships with shared_evidence_keys. Direct
        writes are live/unreviewed state; group approval remains the path for
        accepted review state.

        Set dry_run=true to validate entity properties, relationship endpoints,
        relationship properties, evidence locators, duplicate IDs, and missing
        shared evidence keys without mutating graph state.
        
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_batch_direct_write(
            instance_id,
            payload,
            dry_run=dry_run,
        )

    @_tool
    def cruxible_add_constraint(
        name: str,
        rule: str,
        instance_id: str | None = None,
        severity: contracts.ConstraintSeverity = "warning",
        description: str | None = None,
    ) -> contracts.AddConstraintResult:
        """Add a constraint rule to the config. Writes the updated config to YAML.

        Constraints are evaluated by cruxible_evaluate to flag edges that violate them.
        Rule format: RELATIONSHIP.FROM.property <op> RELATIONSHIP.TO.property
        Supported operators: ==, !=, >, >=, <, <=
        Identifiers may contain letters, digits, underscores, and hyphens.

        Example: classified_as.FROM.Category == classified_as.TO.CategoryName
        
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_add_constraint(instance_id, name, rule, severity, description)

    @_tool
    def cruxible_add_decision_policy(
        name: str,
        applies_to: contracts.DecisionPolicyAppliesTo,
        relationship_type: str,
        effect: contracts.DecisionPolicyEffect,
        instance_id: str | None = None,
        match: contracts.DecisionPolicyMatchInput | None = None,
        description: str | None = None,
        rationale: str = "",
        query_name: str | None = None,
        workflow_name: str | None = None,
        expires_at: str | None = None,
    ) -> contracts.AddDecisionPolicyResult:
        """Add a decision policy to the config for query/workflow execution.
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_add_decision_policy(
            instance_id,
            name,
            applies_to,
            relationship_type,
            effect,
            match=match,
            description=description,
            rationale=rationale,
            query_name=query_name,
            workflow_name=workflow_name,
            expires_at=expires_at,
        )

    @_tool
    def cruxible_reload_config(
        instance_id: str | None = None,
        config_path: str | None = None,
        config_yaml: str | None = None,
        allow_orphans: bool = False,
        config_source_manifest: contracts.ConfigSourceManifest | None = None,
    ) -> contracts.ReloadConfigResult:
        """Reload or replace an instance config after validation.
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_reload_config(
            instance_id,
            config_path=config_path,
            config_yaml=config_yaml,
            allow_orphans=allow_orphans,
            config_source_manifest=config_source_manifest,
        )

    @_tool
    def cruxible_config_status(
        instance_id: str | None = None,
        current_source_manifest: contracts.ConfigSourceManifest | None = None,
    ) -> contracts.ConfigStatusResult:
        """Report source drift and active materialized-config integrity.
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_config_status(
            instance_id,
            current_source_manifest=current_source_manifest,
        )

    @_tool
    def cruxible_propose_workflow(
        workflow_name: str,
        instance_id: str | None = None,
        input_payload: dict[str, Any] | None = None,
        decision_record_id: str | None = None,
    ) -> contracts.WorkflowProposeResult:
        """Execute a configured workflow and bridge its output into a governed relationship group.

        Use this when a repeated decision procedure should propose relationship state
        through Cruxible's proposal/review/trust boundary instead of writing edges directly.
        The workflow must be `type: proposal` and return a relationship proposal artifact from a
        `propose_relationship_group` step.
        
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_propose_workflow(
            instance_id,
            workflow_name,
            input_payload=input_payload,
            decision_record_id=decision_record_id,
        )

    @_tool
    def cruxible_create_decision_record(
        question: str,
        instance_id: str | None = None,
        subject_type: str | None = None,
        subject_id: str | None = None,
        opened_by: str = "human",
    ) -> contracts.DecisionRecordResult:
        """Open a decision record that can collect query and workflow receipts.
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_create_decision_record(
            instance_id,
            question=question,
            subject_type=subject_type,
            subject_id=subject_id,
            opened_by=opened_by,
        )

    @_tool
    def cruxible_get_decision_record(
        decision_record_id: str,
        instance_id: str | None = None,
        include_events: bool = True,
    ) -> contracts.DecisionRecordResult:
        """Fetch one decision record, optionally including its logged events.
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_get_decision_record(
            instance_id,
            decision_record_id,
            include_events=include_events,
        )

    @_tool
    def cruxible_list_decision_records(
        instance_id: str | None = None,
        status: str | None = None,
        subject_type: str | None = None,
        subject_id: str | None = None,
        decision_class: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> contracts.DecisionRecordListResult:
        """List decision records with lifecycle and subject filters.
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_list_decision_records(
            instance_id,
            status=status,
            subject_type=subject_type,
            subject_id=subject_id,
            decision_class=decision_class,
            limit=limit,
            offset=offset,
        )

    @_tool
    def cruxible_list_decision_events(
        instance_id: str | None = None,
        decision_record_id: str | None = None,
        receipt_id: str | None = None,
        trace_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> contracts.DecisionEventListResult:
        """List decision-record events by record, receipt, trace, or status.
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_list_decision_events(
            instance_id,
            decision_record_id=decision_record_id,
            receipt_id=receipt_id,
            trace_id=trace_id,
            status=status,
            limit=limit,
            offset=offset,
        )

    @_tool
    def cruxible_finalize_decision_record(
        decision_record_id: str,
        final_decision: str,
        decision_class: contracts.DecisionClass,
        instance_id: str | None = None,
        rationale: str = "",
    ) -> contracts.DecisionRecordResult:
        """Finalize a decision record with an indexed decision class and rationale.
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_finalize_decision_record(
            instance_id,
            decision_record_id,
            final_decision=final_decision,
            decision_class=decision_class,
            rationale=rationale,
        )

    @_tool
    def cruxible_abandon_decision_record(
        decision_record_id: str,
        instance_id: str | None = None,
        reason: str = "",
    ) -> contracts.DecisionRecordResult:
        """Abandon an open decision record without finalizing a recommendation.
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_abandon_decision_record(
            instance_id,
            decision_record_id,
            reason=reason,
        )

    @_tool
    def cruxible_propose_group(
        relationship_type: str,
        members: list[contracts.MemberInput],
        instance_id: str | None = None,
        thesis_text: str = "",
        thesis_facts: dict[str, Any] | None = None,
        analysis_state: dict[str, Any] | None = None,
        signal_sources_used: list[str] | None = None,
        proposed_by: contracts.GroupProposedBy = "agent",
        suggested_priority: str | None = None,
    ) -> contracts.ProposeGroupToolResult:
        """Propose a candidate group of edges for batch review.

        Each member carries tri-state signals (support/contradict/unsure) from
        declared signal sources. For direct proposals, optional thesis_facts are
        caller-supplied signature scope stored under agent_scope in Cruxible's
        generated thesis_facts. Signal sources are derived from attached member
        signals. Optional analysis_state remains opaque agent data and is not
        hashed.

        If a prior trusted resolution exists for the same thesis signature and
        all signals meet the auto-resolve policy, the group is auto-resolved.
        Otherwise it enters pending_review with a Cruxible-derived review_priority.
        
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_propose_group(
            instance_id,
            relationship_type,
            members,
            thesis_text=thesis_text,
            thesis_facts=thesis_facts,
            analysis_state=analysis_state,
            signal_sources_used=signal_sources_used,
            proposed_by=proposed_by,
            suggested_priority=suggested_priority,
        )

    @_tool
    def cruxible_resolve_group(
        group_id: str,
        action: contracts.GroupAction,
        expected_pending_version: int,
        instance_id: str | None = None,
        rationale: str = "",
        resolved_by: contracts.GroupResolvedBy = "human",
        stamp_existing: bool = False,
    ) -> contracts.ResolveGroupToolResult:
        """Resolve a candidate group by approving or rejecting it.

        Approve creates edges in the graph for valid members. Members whose
        tuple is already live are skipped with an explanation in
        ``skipped_members``; pass ``stamp_existing=True`` to instead bless each
        surviving pre-existing edge with this group's review status and
        provenance. Reject records the resolution without graph mutation. Both
        persist the resolution for audit and future auto-resolve precedent.
        
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_resolve_group(
            instance_id,
            group_id,
            action,
            rationale=rationale,
            resolved_by=resolved_by,
            expected_pending_version=expected_pending_version,
            stamp_existing=stamp_existing,
        )

    @_tool
    def cruxible_update_trust_status(
        resolution_id: str,
        trust_status: contracts.GroupTrustStatus,
        instance_id: str | None = None,
        reason: str = "",
    ) -> contracts.UpdateTrustStatusToolResult:
        """Update the trust status on a confirmed approved resolution.

        Trust is thesis-scoped: the latest confirmed approval for a signature
        governs auto-resolve eligibility. Promote ``watch`` to ``trusted`` to
        enable auto-resolve. Set ``invalidated`` to block auto-resolve and
        escalate future proposals to critical priority.
        
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_update_trust_status(
            instance_id, resolution_id, trust_status, reason=reason
        )

    @_tool
    def cruxible_get_group(
        group_id: str,
        instance_id: str | None = None,
    ) -> contracts.GetGroupToolResult:
        """Get a candidate group by ID, including its members and resolution.

        Returns the group metadata (thesis, status, review_priority) and
        the full list of members with their signals. If the group has been
        resolved, includes the resolution details (action, trust_status,
        rationale).
        
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_get_group(instance_id, group_id)

    @_tool
    def cruxible_list_groups(
        instance_id: str | None = None,
        relationship_type: str | None = None,
        status: contracts.GroupStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> contracts.ListGroupsToolResult:
        """List candidate groups with optional filters.

        Results are sorted by review_priority descending (critical first).
        Use ``status`` to filter by lifecycle state (pending_review,
        auto_resolved, applying, resolved). Use ``relationship_type``
        to filter by edge type.
        
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_list_groups(
            instance_id,
            relationship_type=relationship_type,
            status=status,
            limit=limit,
            offset=offset,
        )

    @_tool
    def cruxible_list_resolutions(
        instance_id: str | None = None,
        relationship_type: str | None = None,
        action: contracts.GroupAction | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> contracts.ListResolutionsToolResult:
        """List group resolutions with optional filters.

        Returns stored resolutions including analysis_state (for agent reuse),
        thesis_facts, trust_status, and trust_reason. Use ``action`` to filter
        by approve/reject. Use ``relationship_type`` to scope to a specific
        edge type.
        
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_list_resolutions(
            instance_id,
            relationship_type=relationship_type,
            action=action,
            limit=limit,
            offset=offset,
        )

    @_tool
    def cruxible_group_status(
        instance_id: str | None = None,
        group_id: str | None = None,
        signature: str | None = None,
    ) -> contracts.GroupBucketStatusToolResult:
        """Show lifecycle status for a signature bucket or concrete group.
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_group_status(
            instance_id,
            group_id=group_id,
            signature=signature,
        )

    @_tool
    def cruxible_state_publish(
        transport_ref: str,
        state_id: str,
        release_id: str,
        compatibility: contracts.StateCompatibility,
        instance_id: str | None = None,
    ) -> contracts.StatePublishResult:
        """Publish a root state instance as an immutable release bundle.
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_state_publish(
            instance_id,
            transport_ref,
            state_id,
            release_id,
            compatibility,
        )

    @_tool
    def cruxible_create_snapshot(
        instance_id: str | None = None,
        label: str | None = None,
    ) -> contracts.SnapshotCreateResult:
        """Create an immutable snapshot for the current instance.
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_create_snapshot(instance_id, label=label)

    @_tool
    def cruxible_instance_backup(
        artifact_path: str,
        instance_id: str | None = None,
        label: str | None = None,
    ) -> contracts.InstanceBackupResult:
        """Write a portable same-identity backup artifact for an instance.
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_instance_backup(instance_id, artifact_path, label=label)

    @_tool
    def cruxible_instance_restore(
        artifact_path: str,
        root_dir: str | None = None,
    ) -> contracts.InstanceRestoreResult:
        """Restore a same-identity daemon-backed instance from an artifact."""
        return handlers.handle_instance_restore(artifact_path, root_dir=root_dir)

    @_tool
    def cruxible_instance_relocate(
        to_dir: str,
        instance_id: str | None = None,
        remove_source: bool = False,
    ) -> contracts.InstanceRelocateResult:
        """Move a healthy daemon-backed instance to a new directory, preserving identity.
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_instance_relocate(
            instance_id,
            to_dir,
            remove_source=remove_source,
        )

    @_tool
    def cruxible_list_snapshots(
        instance_id: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> contracts.SnapshotListResult:
        """List immutable snapshots for the current instance.
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_list_snapshots(instance_id, limit=limit, offset=offset)

    @_tool
    def cruxible_register_source_artifact(
        source_path: str,
        instance_id: str | None = None,
        source_artifact_id: str | None = None,
        source_kind: contracts.SourceKind = "markdown",
        source_retention: contracts.SourceRetention = "manifest_only",
        original_uri: str | None = None,
        label: str | None = None,
    ) -> contracts.RegisterSourceArtifactResult:
        """Register a local source document for source-backed proposal evidence.

        source_artifact_id is a caller-supplied artifact id so pinned evidence
        locators can reference it deterministically; server-generated when
        omitted. When provided, it must be 3-64 chars of [A-Za-z0-9._-]
        starting with an alphanumeric. Duplicate ids are refused by the service.
        
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_register_source_artifact(
            instance_id,
            source_path=source_path,
            source_artifact_id=source_artifact_id,
            source_kind=source_kind,
            source_retention=source_retention,
            original_uri=original_uri,
            label=label,
        )

    @_tool
    def cruxible_dereference_source_evidence(
        source_artifact_id: str,
        instance_id: str | None = None,
        chunk_id: str | None = None,
        heading_path: list[str] | None = None,
        block_selector: str | None = None,
        expected_content_hash: str | None = None,
    ) -> contracts.DereferenceSourceEvidenceResult:
        """Return source text for a registered source-evidence locator.
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_dereference_source_evidence(
            instance_id,
            source_artifact_id=source_artifact_id,
            chunk_id=chunk_id,
            heading_path=heading_path,
            block_selector=block_selector,
            expected_content_hash=expected_content_hash,
        )

    @_tool
    def cruxible_clone_snapshot(
        snapshot_id: str,
        root_dir: str,
        instance_id: str | None = None,
    ) -> contracts.CloneSnapshotResult:
        """Create a point-in-time clone from an immutable snapshot.
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_clone_snapshot(instance_id, snapshot_id, root_dir)

    @_tool
    def cruxible_state_status(instance_id: str | None = None) -> contracts.StateStatusResult:
        """Return upstream tracking metadata for a release-backed overlay.
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_state_status(instance_id)

    @_tool
    def cruxible_state_pull_preview(
        instance_id: str | None = None,
    ) -> contracts.StatePullPreviewResult:
        """Preview pulling a newer upstream release into a release-backed overlay.
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_state_pull_preview(instance_id)

    @_tool
    def cruxible_state_pull_apply(
        expected_apply_digest: str,
        instance_id: str | None = None,
    ) -> contracts.StatePullApplyResult:
        """Apply a previewed upstream release into a release-backed overlay.
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_state_pull_apply(instance_id, expected_apply_digest)

    @_tool
    def cruxible_get_entity(
        entity_type: str,
        entity_id: str,
        instance_id: str | None = None,
        profile: contracts.ReadProfile | None = None,
    ) -> contracts.GetEntityResult:
        """Look up a specific entity by type and ID. Returns properties and metadata.

        `profile` shapes the payload: `compact` (default here) returns a
        bounded identity card with governance markers; pass `standard` or
        `full` for the complete property bag and metadata.
        
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_get_entity(instance_id, entity_type, entity_id, profile=profile)

    @_tool
    def cruxible_get_relationship(
        from_type: str,
        from_id: str,
        relationship_type: str,
        to_type: str,
        to_id: str,
        instance_id: str | None = None,
        edge_key: int | None = None,
    ) -> contracts.GetRelationshipResult:
        """Look up a specific relationship by its endpoints and type. Returns its properties.

        If multiple same-type edges exist between the same endpoints, pass edge_key
        to select a specific one. Without edge_key, raises an error if ambiguous.
        
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_get_relationship(
            instance_id, from_type, from_id, relationship_type, to_type, to_id, edge_key
        )

    @_tool
    def cruxible_relationship_lineage(
        from_type: str,
        from_id: str,
        relationship_type: str,
        to_type: str,
        to_id: str,
        instance_id: str | None = None,
        edge_key: int | None = None,
    ) -> contracts.RelationshipLineageResult:
        """Look up a relationship and follow group provenance when available.
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_relationship_lineage(
            instance_id,
            from_type,
            from_id,
            relationship_type,
            to_type,
            to_id,
            edge_key,
        )

    @_tool
    def cruxible_entity_type_add(
        name: str,
        instance_id: str | None = None,
        properties: dict[str, dict[str, Any]] | None = None,
        description: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Add a new entity type to the ontology.
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_ontology_edit(
            instance_id, "entity_type_add",
            name=name, properties=properties, description=description,
            dry_run=dry_run,
        )

    @_tool
    def cruxible_entity_type_update(
        name: str,
        instance_id: str | None = None,
        add_properties: dict[str, dict[str, Any]] | None = None,
        set_description: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Add properties to an existing entity type.
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_ontology_edit(
            instance_id, "entity_type_update",
            name=name, add_properties=add_properties,
            set_description=set_description, dry_run=dry_run,
        )

    @_tool
    def cruxible_relationship_add(
        name: str,
        from_entity: str,
        to_entity: str,
        instance_id: str | None = None,
        cardinality: str = "many_to_many",
        description: str | None = None,
        reverse_name: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Add a new relationship between two entity types.
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_ontology_edit(
            instance_id, "relationship_add",
            name=name, from_entity=from_entity, to_entity=to_entity,
            cardinality=cardinality, description=description,
            reverse_name=reverse_name, dry_run=dry_run,
        )

    @_tool
    def cruxible_enum_add(
        name: str,
        values: list[str],
        instance_id: str | None = None,
        ordered: bool = False,
        description: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Add a new enum vocabulary.
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_ontology_edit(
            instance_id, "enum_add",
            name=name, values=values, ordered=ordered,
            description=description, dry_run=dry_run,
        )

    @_tool
    def cruxible_enum_value_add(
        name: str,
        values: list[str],
        instance_id: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Add new values to an existing enum.
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_ontology_edit(
            instance_id, "enum_value_add",
            name=name, values=values, dry_run=dry_run,
        )

    @_tool
    def cruxible_ontology_describe(
        instance_id: str | None = None,
    ) -> dict[str, Any]:
        """Return a human-readable summary of the current ontology.
未提供 instance_id 时，自动使用 CRUXIBLE_DEFAULT_INSTANCE_ID 环境变量配置的默认实例。
        """
        return handlers.handle_ontology_describe(instance_id)


    @_tool
    def cruxible_discover_schema(
        source_type: str,
        host: str | None = None,
        port: int | None = None,
        database: str | None = None,
        user: str | None = None,
        password: str | None = None,
        private_key_path: str | None = None,
        remote_dir: str | None = None,
        file_paths: list[str] | None = None,
        tables: list[str] | None = None,
    ) -> dict[str, Any]:
        """Connect to a data source (hive, oceanbase, sftp) and discover schema. Returns proposed ontology entity types, relationships, and enums that can be reviewed and applied with cruxible_entity_type_add et al."""
        return handlers.handle_discover_schema(
            source_type, host=host, port=port, database=database,
            user=user, password=password, private_key_path=private_key_path,
            remote_dir=remote_dir, file_paths=file_paths, tables=tables,
        )

    _publish_union_output_schemas(server)

    return registered


# Tools that return plain dicts because their results are UNIONS of contract
# models: FastMCP wraps union-annotated returns in a {"result": ...} envelope,
# which would break the legacy top-level payload shape for existing MCP
# consumers. The dict return keeps the wire shape, and the tool's published
# outputSchema is overridden below with the real anyOf union of the contract
# models it emits.
_UNION_OUTPUT_TOOLS: dict[str, Any] = {
    "cruxible_query": contracts.QueryToolResult | contracts.QueryGraphToolResult,
    "cruxible_query_inline": contracts.QueryToolResult | contracts.QueryGraphToolResult,
    "cruxible_list_queries": contracts.QueryListResult | contracts.QueryListDetailResult,
    "cruxible_inspect_entity": (
        contracts.InspectEntityResult | contracts.InspectNeighborhoodResult
    ),
}


def _publish_union_output_schemas(server: FastMCP) -> None:
    """Publish real union outputSchemas for the dict-returning union tools.

    FastMCP derives outputSchema from the return annotation, so a
    ``dict[str, Any]`` return advertises an unrestricted object. FastMCP
    exposes no hook to attach a custom schema to a dict-returning tool
    (``server.tool()`` only takes ``structured_output``), so the derived
    schema is overridden on the registered tool's metadata after
    registration. Only the ADVERTISED schema changes: the permissive dict
    output model stays in place, so runtime structured/unstructured payloads
    remain byte-identical to the handler's model dump (the legacy top-level
    rows shape) instead of being re-validated through a union model.
    """
    for tool_name, union in _UNION_OUTPUT_TOOLS.items():
        tool = server._tool_manager.get_tool(tool_name)
        if tool is None:  # pragma: no cover - registration bug guard
            raise RuntimeError(f"union output tool {tool_name!r} is not registered")
        output_schema = TypeAdapter(union).json_schema()
        output_schema["type"] = "object"
        tool.fn_metadata.output_schema = output_schema
        # Tool.output_schema is a cached_property over fn_metadata; drop any
        # cached value so list_tools publishes the override.
        tool.__dict__.pop("output_schema", None)
