"""Abstract connector interface and shared data types for schema discovery."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ColumnMeta:
    """Metadata for a single column discovered from a data source."""

    name: str
    data_type: str
    nullable: bool = True
    primary_key: bool = False
    indexed: bool = False
    foreign_key: tuple[str, str] | None = None
    description: str | None = None
    sample_values: list[Any] | None = None
    max_length: int | None = None
    enum_values: list[str] | None = None


@dataclass
class DiscoveredTable:
    """A table/collection discovered from a data source, with its columns."""

    source_name: str
    suggested_entity_type: str
    columns: list[ColumnMeta]
    description: str | None = None
    row_count: int | None = None


@dataclass
class DiscoveredRelationship:
    """A foreign-key relationship discovered between two tables."""

    from_entity_type: str
    from_column: str
    to_entity_type: str
    to_column: str
    suggested_relationship_name: str | None = None


@dataclass
class DiscoveredSchema:
    """Full schema discovered from a data source, before ontology conversion."""

    tables: list[DiscoveredTable] = field(default_factory=list)
    relationships: list[DiscoveredRelationship] = field(default_factory=list)


@dataclass
class SchemaDiscoveryResult:
    """Output of a connector scan — proposed ontology changes.

    This is NOT automatically applied. The caller must present it for
    review and apply via the standard ontology MCP tools.
    """

    schema: DiscoveredSchema
    proposed_entity_types: dict[str, dict[str, Any]] = field(default_factory=dict)
    proposed_relationships: list[dict[str, Any]] = field(default_factory=list)
    proposed_enums: dict[str, list[str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


class SchemaConnector(Protocol):
    """Protocol for data source connectors that discover schema metadata."""

    def connect(self, **kwargs: Any) -> None:
        """Establish connection to the data source."""
        ...

    def scan(self, **kwargs: Any) -> SchemaDiscoveryResult:
        """Scan the data source and return discovered schema + proposed ontology."""
        ...

    def close(self) -> None:
        """Close the connection."""
        ...


def _sample_type(values: list[Any]) -> str:
    """Infer a Cruxible property type from sampled column values."""
    if not values:
        return "string"
    for v in values:
        if v is None:
            continue
        if isinstance(v, int):
            return "int"
        if isinstance(v, float):
            return "float"
        if isinstance(v, bool):
            return "bool"
        # Recognize common date/datetime patterns
        if isinstance(v, str):
            v_lower = v.strip().lower()
            if v_lower in {"true", "false"}:
                return "bool"
    return "string"


def _infer_enum(values: list[Any], max_enum: int = 20) -> list[str] | None:
    """If a column has few distinct values, propose it as an enum."""
    if not values:
        return None
    distinct = sorted(set(str(v) for v in values if v is not None), key=str)
    if 2 <= len(distinct) <= max_enum:
        return distinct
    return None


def convert_to_proposed_ontology(schema: DiscoveredSchema) -> SchemaDiscoveryResult:
    """Convert discovered schema into proposed ontology changes.

    This is the core inference logic:
    - Each table → one entity type
    - Each column → one property
    - Columns with few distinct values → proposed enum
    - Foreign keys → proposed relationships
    - Table name → snake_case entity type name
    """
    from cruxible_core.primitives import new_id

    result = SchemaDiscoveryResult(schema=schema)

    for table in schema.tables:
        props: dict[str, dict[str, Any]] = {}
        enums_for_type: list[str] = []

        for col in table.columns:
            prop_def: dict[str, Any] = {"type": _sample_type(col.sample_values)}

            if col.primary_key:
                prop_def["primary_key"] = True
            elif col.nullable:
                prop_def["optional"] = True
            if col.indexed:
                prop_def["indexed"] = True
            if col.description:
                prop_def["description"] = col.description

            # Infer enum from sample values
            if col.enum_values:
                enum_name = f"{table.suggested_entity_type}_{col.name}_enum"
                result.proposed_enums[enum_name] = col.enum_values
                prop_def["enum_ref"] = enum_name
                enums_for_type.append(enum_name)
            elif col.sample_values:
                inferred = _infer_enum(col.sample_values)
                if inferred:
                    enum_name = f"{table.suggested_entity_type}_{col.name}"
                    result.proposed_enums[enum_name] = inferred
                    prop_def["enum_ref"] = enum_name
                    enums_for_type.append(enum_name)

            props[col.name] = prop_def

        result.proposed_entity_types[table.suggested_entity_type] = {
            "properties": props,
            "description": table.description or f"Discovered from {table.source_name}",
        }

    for rel in schema.relationships:
        rel_def = {
            "name": rel.suggested_relationship_name or f"{rel.from_entity_type}_to_{rel.to_entity_type}",
            "from_entity": rel.from_entity_type,
            "to_entity": rel.to_entity_type,
        }
        result.proposed_relationships.append(rel_def)

    return result
