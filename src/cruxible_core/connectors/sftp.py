"""SFTP connector — scan remote files and infer schema from structured data."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any

from cruxible_core.connectors.base import (
    ColumnMeta,
    DiscoveredSchema,
    DiscoveredTable,
    SchemaDiscoveryResult,
    _infer_enum,
    _sample_type,
)


def _file_name_to_entity(name: str) -> str:
    """Convert a filename (without extension) to entity type name."""
    stem = Path(name).stem
    cleaned = stem.lower().replace("-", "_").replace(" ", "_")
    for prefix in ["dim_", "fact_", "ods_", "stg_"]:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break
    return "".join(word.capitalize() for word in cleaned.split("_"))


def _detect_format(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext == ".csv":
        return "csv"
    if ext in (".json", ".jsonl"):
        return "json"
    if ext in (".xlsx", ".xls"):
        return "excel"
    if ext == ".xml":
        return "xml"
    if ext == ".parquet":
        return "parquet"
    return "unknown"


def _infer_columns_from_csv(
    content: str, sample_size: int = 100
) -> list[ColumnMeta]:
    """Read CSV content and infer column metadata from a sample."""
    reader = csv.DictReader(io.StringIO(content))
    rows: list[dict[str, str]] = []
    for i, row in enumerate(reader):
        if i >= sample_size:
            break
        rows.append(row)

    if not rows:
        return []

    columns: list[ColumnMeta] = []
    for col_name in rows[0].keys():
        values = [r.get(col_name) for r in rows]
        non_null = [v for v in values if v is not None and v.strip()]
        typed_values = non_null[:20]

        # Try simple type inference
        inferred_type = _sample_type(typed_values)
        enum_vals = _infer_enum(typed_values)
        nullable = any(v is None or v.strip() == "" for v in values)

        columns.append(
            ColumnMeta(
                name=col_name,
                data_type=inferred_type,
                nullable=nullable,
                sample_values=typed_values,
                enum_values=enum_vals,
            )
        )
    return columns


def _infer_columns_from_json(
    content: str, sample_size: int = 100
) -> list[ColumnMeta]:
    """Read JSON/JSONL content and infer column metadata."""
    lines = content.strip().split("\n")
    records: list[dict[str, Any]] = []

    for i, line in enumerate(lines):
        if i >= sample_size:
            break
        try:
            record = json.loads(line)
            if isinstance(record, dict):
                records.append(record)
            elif isinstance(record, list):
                for item in record[:sample_size]:
                    if isinstance(item, dict):
                        records.append(item)
        except json.JSONDecodeError:
            continue

    if not records:
        return []

    all_keys: set[str] = set()
    for r in records:
        all_keys.update(r.keys())

    columns: list[ColumnMeta] = []
    for key in sorted(all_keys):
        values = [r.get(key) for r in records]
        non_null = [v for v in values if v is not None]
        typed_values = non_null[:20]

        inferred_type = _sample_type(typed_values)
        enum_vals = _infer_enum(typed_values)
        nullable = any(v is None for v in values)

        columns.append(
            ColumnMeta(
                name=key,
                data_type=inferred_type,
                nullable=nullable,
                sample_values=typed_values,
                enum_values=enum_vals,
            )
        )
    return columns


class SFTPConnector:
    """Connect to an SFTP server and discover file-based datasets.

    Scans remote directories for structured files (CSV, JSON, JSONL, Parquet),
    reads a sample of each, and infers column schemas and proposed entity types.
    """

    def __init__(self) -> None:
        self._transport: Any = None
        self._sftp: Any = None

    def connect(
        self,
        host: str = "localhost",
        port: int = 22,
        user: str = "",
        password: str | None = None,
        private_key: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Connect to SFTP server using paramiko."""
        try:
            import paramiko

            self._transport = paramiko.Transport((host, port))
            if private_key:
                key = paramiko.RSAKey.from_private_key_file(private_key)
                self._transport.connect(username=user, pkey=key)
            else:
                self._transport.connect(username=user, password=password)
            self._sftp = paramiko.SFTPClient.from_transport(self._transport)
        except ImportError:
            pass

    def _list_files(
        self, remote_dir: str, pattern: str | None = None
    ) -> list[str]:
        """List structured data files in a remote directory."""
        if not self._sftp:
            return []
        supported = {".csv", ".json", ".jsonl", ".parquet", ".xlsx"}
        try:
            files = self._sftp.listdir(remote_dir)
            result = []
            for f in files:
                ext = Path(f).suffix.lower()
                if ext in supported:
                    if pattern is None or pattern in f:
                        result.append(f"{remote_dir}/{f}")
            return sorted(result)
        except Exception:
            return []

    def _read_file(self, remote_path: str, max_bytes: int = 5 * 1024 * 1024) -> str:
        """Read a remote file content (up to max_bytes)."""
        if not self._sftp:
            return ""
        with self._sftp.open(remote_path, "rb") as f:
            return f.read(max_bytes).decode("utf-8", errors="replace")

    def scan(
        self,
        remote_dir: str = ".",
        file_pattern: str | None = None,
        file_paths: list[str] | None = None,
    ) -> SchemaDiscoveryResult:
        """Scan remote directory for structured data files and infer schema."""
        if file_paths:
            files = file_paths
        else:
            files = self._list_files(remote_dir, file_pattern)

        discovered = DiscoveredSchema()
        warnings: list[str] = []

        for fpath in files:
            try:
                fmt = _detect_format(fpath)
                entity_name = _file_name_to_entity(fpath)
                content = self._read_file(fpath)

                if fmt == "csv":
                    columns = _infer_columns_from_csv(content)
                elif fmt in ("json", "jsonl"):
                    columns = _infer_columns_from_json(content)
                else:
                    warnings.append(f"Unsupported format '{fmt}' for {fpath}")
                    continue

                if not columns:
                    warnings.append(f"No columns inferred from {fpath}")
                    continue

                discovered.tables.append(
                    DiscoveredTable(
                        source_name=f"sftp:{fpath}",
                        suggested_entity_type=entity_name,
                        columns=columns,
                        description=f"File: {fpath} ({fmt})",
                    )
                )
            except Exception as e:
                warnings.append(f"Failed to scan '{fpath}': {e}")

        result = SchemaDiscoveryResult(schema=discovered, warnings=warnings)
        return result

    def close(self) -> None:
        if self._sftp:
            self._sftp.close()
        if self._transport:
            self._transport.close()
