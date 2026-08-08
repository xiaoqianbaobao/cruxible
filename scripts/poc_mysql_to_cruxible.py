from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from decimal import Decimal
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

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


def _json_sanitize(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except Exception:
            return value.hex()
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _json_sanitize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_sanitize(v) for v in value]
    return str(value)


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


def _get_json(base_url: str, path: str) -> dict[str, Any]:
    url = base_url.rstrip("/") + path
    resp = httpx.get(url, timeout=30.0)
    resp.raise_for_status()
    return resp.json()


def _init_instance_root(*, instance_root: Path, config_path: Path) -> CruxibleInstance:
    metadata_path = instance_root / CruxibleInstance.INSTANCE_DIR / "instance.json"
    if metadata_path.exists():
        return CruxibleInstance.load(instance_root)
    service_init(instance_root, config_path=str(config_path), instance_mode=CruxibleInstance.DEV_MODE)
    return CruxibleInstance.load(instance_root)


def _require_pymysql():
    try:
        import pymysql  # type: ignore[import-not-found]
    except Exception as exc:
        raise RuntimeError(
            "Missing dependency 'pymysql'. Install it with: uv pip install pymysql"
        ) from exc
    return pymysql


def _mysql_connect(
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    database: str,
):
    pymysql = _require_pymysql()
    return pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def _mysql_execute(conn, sql: str, params: dict[str, Any] | tuple[Any, ...] | None = None) -> None:
    with conn.cursor() as cur:
        cur.execute(sql, params)


def _mysql_fetchall(conn, sql: str, params: dict[str, Any] | tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    return list(rows or [])


def _ensure_schema(conn) -> None:
    _mysql_execute(
        conn,
        """
        CREATE TABLE IF NOT EXISTS threads (
          thread_id VARCHAR(128) PRIMARY KEY,
          title TEXT NOT NULL,
          metadata JSON NULL,
          created_at DATETIME NULL,
          updated_at DATETIME NULL
        )
        """,
    )
    _mysql_execute(
        conn,
        """
        CREATE TABLE IF NOT EXISTS messages (
          message_id VARCHAR(255) PRIMARY KEY,
          thread_id VARCHAR(128) NOT NULL,
          role VARCHAR(32) NOT NULL,
          content LONGTEXT NOT NULL,
          position INT NOT NULL,
          raw JSON NULL,
          CONSTRAINT fk_messages_thread FOREIGN KEY (thread_id) REFERENCES threads(thread_id)
        )
        """,
    )
    _mysql_execute(conn, "CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id)")
    _mysql_execute(conn, "CREATE INDEX IF NOT EXISTS idx_messages_position ON messages(thread_id, position)")


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


def _seed_mysql_from_deerflow(
    conn,
    *,
    deerflow_base_url: str,
    thread_id: str,
) -> dict[str, Any]:
    state = _get_json(deerflow_base_url, f"/api/threads/{thread_id}/state")
    now_iso = _utc_now_iso()
    values = state.get("values") or {}
    title = values.get("title") if isinstance(values, dict) else None
    metadata = {
        "deerflow_base_url": deerflow_base_url,
        "checkpoint_id": state.get("checkpoint_id"),
        "parent_checkpoint_id": state.get("parent_checkpoint_id"),
        "raw_state": state,
        "seeded_at": now_iso,
    }
    _mysql_execute(
        conn,
        """
        INSERT INTO threads(thread_id, title, metadata, created_at, updated_at)
        VALUES (%s, %s, %s, NOW(), NOW())
        ON DUPLICATE KEY UPDATE
          title=VALUES(title),
          metadata=VALUES(metadata),
          updated_at=NOW()
        """,
        (thread_id, str(title or ""), json.dumps(metadata, ensure_ascii=False)),
    )
    for index, message in enumerate(_extract_messages(state)):
        message_id = str(message.get("id") or f"{thread_id}:auto:{index}")
        role = message.get("role") or message.get("type") or "unknown"
        content = message.get("content")
        _mysql_execute(
            conn,
            """
            INSERT INTO messages(message_id, thread_id, role, content, position, raw)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
              thread_id=VALUES(thread_id),
              role=VALUES(role),
              content=VALUES(content),
              position=VALUES(position),
              raw=VALUES(raw)
            """,
            (
                message_id,
                thread_id,
                str(role),
                str(content) if content is not None else "",
                int(index),
                json.dumps(message, ensure_ascii=False),
            ),
        )
    return {"thread_id": thread_id, "message_count": len(_extract_messages(state))}


def _iter_threads(conn, *, thread_id: str | None) -> Iterable[dict[str, Any]]:
    if thread_id:
        rows = _mysql_fetchall(conn, "SELECT * FROM threads WHERE thread_id=%s", (thread_id,))
    else:
        rows = _mysql_fetchall(conn, "SELECT * FROM threads ORDER BY updated_at DESC")
    return rows


def _iter_messages(conn, *, thread_id: str) -> list[dict[str, Any]]:
    return _mysql_fetchall(
        conn,
        "SELECT * FROM messages WHERE thread_id=%s ORDER BY position ASC",
        (thread_id,),
    )


def _build_batch_payload(
    *,
    thread_row: dict[str, Any],
    message_rows: list[dict[str, Any]],
    mysql_ref: dict[str, Any],
) -> BatchDirectWriteInput:
    thread_id = str(thread_row["thread_id"])
    title = str(thread_row.get("title") or "")
    now = _utc_now_iso()
    metadata_cell = thread_row.get("metadata")
    if isinstance(metadata_cell, (dict, list)):
        thread_metadata_value: Any = metadata_cell
    elif metadata_cell is None:
        thread_metadata_value = {}
    else:
        try:
            thread_metadata_value = json.loads(metadata_cell)
        except Exception:
            thread_metadata_value = {"raw": metadata_cell}
    if isinstance(thread_metadata_value, dict):
        thread_metadata_value = dict(thread_metadata_value)
        thread_metadata_value.setdefault("mysql", _json_sanitize(mysql_ref))
    entities: list[EntityWriteInput] = [
        EntityWriteInput(
            entity_type="DeerflowThread",
            entity_id=thread_id,
            properties={
                "thread_id": thread_id,
                "title": title,
                "metadata": thread_metadata_value,
                "created_at": now,
                "updated_at": now,
            },
        )
    ]
    relationships: list[BatchRelationshipWriteInput] = []
    for row in message_rows:
        message_id = str(row["message_id"])
        role = str(row.get("role") or "unknown")
        content = str(row.get("content") or "")
        position = int(row.get("position") or 0)
        raw_value: Any
        raw_cell = row.get("raw")
        if isinstance(raw_cell, (dict, list)):
            raw_value = raw_cell
        elif raw_cell is None:
            raw_value = {}
        else:
            try:
                raw_value = json.loads(raw_cell)
            except Exception:
                raw_value = {"raw": raw_cell}
        if isinstance(raw_value, dict):
            raw_value = dict(raw_value)
            raw_value.setdefault("mysql", _json_sanitize(mysql_ref))
        entities.append(
            EntityWriteInput(
                entity_type="DeerflowMessage",
                entity_id=message_id,
                properties={
                    "message_id": message_id,
                    "thread_id": thread_id,
                    "role": role,
                    "content": content,
                    "position": position,
                    "raw": raw_value,
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
                properties={"position": position},
                shared_evidence_keys=[],
            )
        )
    return BatchDirectWriteInput(entities=entities, relationships=relationships, shared_evidence={})


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mysql-host", default="127.0.0.1")
    parser.add_argument("--mysql-port", type=int, default=3307)
    parser.add_argument("--mysql-user", default="root")
    parser.add_argument("--mysql-password", default="cruxible")
    parser.add_argument("--mysql-database", default="deerflow_poc")
    parser.add_argument("--thread-id", default=None)
    parser.add_argument("--seed-from-deerflow", action="store_true")
    parser.add_argument("--deerflow-base-url", default="http://localhost:2026")
    parser.add_argument("--instance-root", default=str(Path(".poc/deerflow_instance").resolve()))
    parser.add_argument("--config-path", default=str(Path(".poc/deerflow_poc_config.yaml").resolve()))
    args = parser.parse_args(argv)

    config_path = Path(args.config_path)
    if not config_path.exists():
        raise RuntimeError(f"config not found: {config_path}")

    mysql_ref = {
        "host": args.mysql_host,
        "port": args.mysql_port,
        "database": args.mysql_database,
    }

    conn = _mysql_connect(
        host=args.mysql_host,
        port=int(args.mysql_port),
        user=args.mysql_user,
        password=args.mysql_password,
        database=args.mysql_database,
    )
    try:
        _ensure_schema(conn)
        seed_result: dict[str, Any] | None = None
        if args.seed_from_deerflow:
            if not args.thread_id:
                raise RuntimeError("--seed-from-deerflow requires --thread-id")
            _wait_for_http_ok(args.deerflow_base_url.rstrip("/") + "/health", timeout_s=120.0)
            seed_result = _seed_mysql_from_deerflow(
                conn,
                deerflow_base_url=args.deerflow_base_url,
                thread_id=str(args.thread_id),
            )

        instance_root = Path(args.instance_root)
        instance = _init_instance_root(instance_root=instance_root, config_path=config_path)

        touched_threads = 0
        touched_messages = 0
        last_receipt_id: str | None = None
        for thread_row in _iter_threads(conn, thread_id=args.thread_id):
            thread_id = str(thread_row["thread_id"])
            message_rows = _iter_messages(conn, thread_id=thread_id)
            payload = _build_batch_payload(
                thread_row=thread_row,
                message_rows=message_rows,
                mysql_ref=mysql_ref,
            )
            result = service_batch_direct_write(
                instance,
                payload,
                dry_run=False,
                source="poc_mysql",
                source_ref=f"mysql://{args.mysql_host}:{args.mysql_port}/{args.mysql_database}",
            )
            last_receipt_id = result.receipt_id
            touched_threads += 1
            touched_messages += len(message_rows)

        graph = instance.load_graph()
        summary = {
            "mysql": mysql_ref,
            "seed": seed_result,
            "threads_ingested": touched_threads,
            "messages_ingested": touched_messages,
            "cruxible_instance_root": str(instance_root),
            "entities_total": graph.entity_count(),
            "threads": graph.entity_count("DeerflowThread"),
            "messages": graph.entity_count("DeerflowMessage"),
            "relationships_total": graph.edge_count(),
            "thread_has_message": graph.edge_count("thread_has_message"),
            "last_receipt_id": last_receipt_id,
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
