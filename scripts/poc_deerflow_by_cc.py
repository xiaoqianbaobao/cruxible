from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from cruxible_core.runtime.instance import CruxibleInstance
from cruxible_core.service import service_batch_direct_write, service_init
from cruxible_core.service.types import (
    BatchDirectWriteInput,
    BatchRelationshipWriteInput,
    EntityWriteInput,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _wait_for_http_ok(url: str, *, timeout_s: float = 60.0) -> None:
    deadline = time.time() + timeout_s
    last_error: str | None = None
    while time.time() < deadline:
        try:
            resp = httpx.get(url, timeout=5.0)
            if 200 <= resp.status_code < 300:
                return
            last_error = f"{resp.status_code} {resp.text}"
        except Exception as exc:
            last_error = str(exc)
        time.sleep(1.0)
    raise RuntimeError(f"health check failed for {url}: {last_error}")


def _post_json(base_url: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = base_url.rstrip("/") + path
    resp = httpx.post(url, json=payload, timeout=30.0)
    resp.raise_for_status()
    return resp.json()


def _get_json(base_url: str, path: str) -> dict[str, Any]:
    url = base_url.rstrip("/") + path
    resp = httpx.get(url, timeout=30.0)
    resp.raise_for_status()
    return resp.json()


def _ensure_clean_instance_root(instance_root: Path, *, reset: bool) -> None:
    if not reset:
        instance_root.mkdir(parents=True, exist_ok=True)
        return
    if instance_root.exists():
        shutil.rmtree(instance_root)
    instance_root.mkdir(parents=True, exist_ok=True)


def _init_cruxible_instance(*, instance_root: Path, config_path: Path) -> CruxibleInstance:
    metadata_path = instance_root / CruxibleInstance.INSTANCE_DIR / "instance.json"
    if metadata_path.exists():
        return CruxibleInstance.load(instance_root)
    service_init(instance_root, config_path=str(config_path), instance_mode=CruxibleInstance.DEV_MODE)
    return CruxibleInstance.load(instance_root)


def _seed_deerflow_thread(base_url: str) -> tuple[str, dict[str, Any]]:
    thread = _post_json(
        base_url,
        "/api/threads",
        {
            "metadata": {
                "poc": True,
                "source": "cruxible_poc_deerflow_by_cc",
                "created_at": _utc_now_iso(),
            }
        },
    )
    thread_id = str(thread["thread_id"])
    messages = [
        {
            "id": f"{thread_id}:m0",
            "role": "user",
            "content": "POC: 将 DeerFlow thread state 落到 Cruxible 图里。",
        },
        {
            "id": f"{thread_id}:m1",
            "role": "assistant",
            "content": "收到。我会生成一个最小可验证的数据结构：Thread → Messages。",
            "tool_calls": [
                {
                    "id": str(uuid.uuid4()),
                    "name": "poc_tool",
                    "args": {"example": True},
                }
            ],
        },
    ]
    _post_json(
        base_url,
        f"/api/threads/{thread_id}/state",
        {
            "values": {
                "title": "cruxible deerflow POC",
                "messages": messages,
            }
        },
    )
    state = _get_json(base_url, f"/api/threads/{thread_id}/state")
    return thread_id, state


def _extract_messages(state: dict[str, Any]) -> list[dict[str, Any]]:
    values = state.get("values") or {}
    messages = values.get("messages") or []
    if not isinstance(messages, list):
        return []
    result: list[dict[str, Any]] = []
    for item in messages:
        if isinstance(item, dict):
            result.append(item)
        else:
            result.append({"role": "unknown", "content": str(item), "raw": item})
    return result


def _build_batch_payload(
    *,
    thread_id: str,
    state: dict[str, Any],
    deerflow_base_url: str,
) -> BatchDirectWriteInput:
    now = _utc_now_iso()
    values = state.get("values") or {}
    title = values.get("title") if isinstance(values, dict) else None
    metadata = {
        "deerflow_base_url": deerflow_base_url,
        "checkpoint_id": state.get("checkpoint_id"),
        "parent_checkpoint_id": state.get("parent_checkpoint_id"),
        "tasks": state.get("tasks", []),
        "next": state.get("next", []),
        "raw_state": state,
    }
    entities: list[EntityWriteInput] = [
        EntityWriteInput(
            entity_type="DeerflowThread",
            entity_id=thread_id,
            properties={
                "thread_id": thread_id,
                "title": str(title) if title is not None else "",
                "metadata": metadata,
                "created_at": now,
                "updated_at": now,
            },
        )
    ]

    relationships: list[BatchRelationshipWriteInput] = []
    for index, message in enumerate(_extract_messages(state)):
        message_id = str(message.get("id") or f"{thread_id}:auto:{index}")
        role = message.get("role") or message.get("type") or "unknown"
        content = message.get("content")
        entities.append(
            EntityWriteInput(
                entity_type="DeerflowMessage",
                entity_id=message_id,
                properties={
                    "message_id": message_id,
                    "thread_id": thread_id,
                    "role": str(role),
                    "content": str(content) if content is not None else "",
                    "position": index,
                    "raw": message,
                },
            )
        )
        relationships.append(
            BatchRelationshipWriteInput(
                relationship_type="thread_has_message",
                from_type="DeerflowThread",
                from_id=thread_id,
                to_type="DeerflowMessage",
                to_id=message_id,
                properties={"position": index},
                shared_evidence_keys=[],
            )
        )

    return BatchDirectWriteInput(entities=entities, relationships=relationships, shared_evidence={})


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--deerflow-base-url", default="http://localhost:2026")
    parser.add_argument("--thread-id", default=None)
    parser.add_argument("--instance-root", default=str(Path(".poc/deerflow_instance").resolve()))
    parser.add_argument("--config-path", default=str(Path(".poc/deerflow_poc_config.yaml").resolve()))
    parser.add_argument("--reset-instance", action="store_true")
    args = parser.parse_args(argv)

    _wait_for_http_ok(args.deerflow_base_url.rstrip("/") + "/health", timeout_s=120.0)

    if args.thread_id:
        thread_id = str(args.thread_id)
        state = _get_json(args.deerflow_base_url, f"/api/threads/{thread_id}/state")
    else:
        thread_id, state = _seed_deerflow_thread(args.deerflow_base_url)

    instance_root = Path(args.instance_root)
    config_path = Path(args.config_path)
    if not config_path.exists():
        raise RuntimeError(f"config not found: {config_path}")
    _ensure_clean_instance_root(instance_root, reset=args.reset_instance)
    instance = _init_cruxible_instance(instance_root=instance_root, config_path=config_path)

    payload = _build_batch_payload(
        thread_id=thread_id,
        state=state,
        deerflow_base_url=args.deerflow_base_url,
    )
    result = service_batch_direct_write(
        instance,
        payload,
        dry_run=False,
        source="poc_deerflow_by_cc",
        source_ref="deerflow_by_cc_poc",
    )

    graph = instance.load_graph()
    summary = {
        "deerflow_thread_id": thread_id,
        "cruxible_instance_root": str(instance_root),
        "entities_total": graph.entity_count(),
        "threads": graph.entity_count("DeerflowThread"),
        "messages": graph.entity_count("DeerflowMessage"),
        "relationships_total": graph.edge_count(),
        "thread_has_message": graph.edge_count("thread_has_message"),
        "batch_result": asdict(result),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
