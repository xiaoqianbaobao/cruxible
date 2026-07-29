"""Programmatic CoreConfig editor for ontology CRUD operations.

Wraps a :class:`CoreConfig` instance with high-level add/update/delete
methods that validate changes and produce a serializable YAML diff.
"""

from __future__ import annotations

from typing import Any

from cruxible_core.config.schema import (
    CoreConfig,
    EntityTypeSchema,
    EnumSchema,
    PropertySchema,
    RelationshipSchema,
)
from cruxible_core.errors import ConfigError


class OntologyEditError(ConfigError):
    """Raised when an ontology edit would produce an invalid or destructive config."""


class ConfigEditor:
    """Mutable wrapper around a CoreConfig for ontology CRUD operations.

    All edit methods validate the change against the current config state.
    The caller must call :meth:`to_yaml` and ``cruxible_reload_config`` to
    apply changes to a running instance.

    Usage::

        editor = ConfigEditor(config)
        editor.add_entity_type("Sprint", props={"name": "string", "start_date": "datetime"})
        editor.add_relationship("belongs_to", "Sprint", "Project")
        yaml_str = editor.to_yaml()
        # → cruxible_reload_config(instance_id, config_yaml=yaml_str)
    """

    def __init__(self, config: CoreConfig) -> None:
        self._config = config

    # ── Entity Types ──────────────────────────────────────────────

    def add_entity_type(
        self,
        name: str,
        *,
        id_field: str | None = None,
        properties: dict[str, dict[str, Any]] | None = None,
        description: str | None = None,
    ) -> str:
        """Add a new entity type.

        Args:
            name: Entity type name (e.g. ``"Sprint"``).
            id_field: Primary key property name. Defaults to ``{name.lower()}_id``.
            properties: Dict of property name → property definition dict.
                Simple form: ``{"title": {"type": "string", "indexed": true}}``.
            description: Optional human-readable description.

        Returns:
            A human-readable summary of the change.

        Raises:
            OntologyEditError: If the type already exists.
        """
        if name in self._config.entity_types:
            raise OntologyEditError(f"Entity type '{name}' already exists")

        pk = id_field or f"{name.lower()}_id"
        props: dict[str, PropertySchema] = {}
        props[pk] = PropertySchema(type="string", primary_key=True)

        for prop_name, prop_spec in (properties or {}).items():
            props[prop_name] = PropertySchema(**prop_spec)

        self._config.entity_types[name] = EntityTypeSchema(
            description=description,
            properties=props,
        )
        return f"Added entity type '{name}' with {len(props)} properties (PK: {pk})"

    def update_entity_type(
        self,
        name: str,
        *,
        add_properties: dict[str, dict[str, Any]] | None = None,
        set_description: str | None = None,
    ) -> str:
        """Add properties to an existing entity type or update its description.

        Args:
            name: Existing entity type name.
            add_properties: New properties to add (name → definition).
            set_description: Replace the description.

        Returns:
            A human-readable summary.

        Raises:
            OntologyEditError: If the type does not exist or a property already exists.
        """
        if name not in self._config.entity_types:
            raise OntologyEditError(f"Entity type '{name}' not found")

        entity = self._config.entity_types[name]
        added: list[str] = []

        for prop_name, prop_spec in (add_properties or {}).items():
            if prop_name in entity.properties:
                raise OntologyEditError(
                    f"Property '{prop_name}' already exists on '{name}'"
                )
            entity.properties[prop_name] = PropertySchema(**prop_spec)
            added.append(prop_name)

        if set_description is not None:
            object.__setattr__(entity, "description", set_description)

        return (
            f"Updated entity type '{name}': {len(added)} properties added"
            if added
            else f"Updated entity type '{name}' description"
        )

    # ── Relationships ─────────────────────────────────────────────

    def add_relationship(
        self,
        name: str,
        from_entity: str,
        to_entity: str,
        *,
        cardinality: str = "many_to_many",
        properties: dict[str, dict[str, Any]] | None = None,
        description: str | None = None,
        reverse_name: str | None = None,
    ) -> str:
        """Add a new relationship between two entity types.

        Args:
            name: Relationship type name (e.g. ``"sprint_belongs_to_project"``).
            from_entity: Source entity type name.
            to_entity: Target entity type name.
            cardinality: Relationship cardinality.
            properties: Optional edge properties.
            description: Optional description.
            reverse_name: Optional inverse relationship name.

        Returns:
            A human-readable summary.

        Raises:
            OntologyEditError: If the relationship already exists or entity types are unknown.
        """
        if from_entity not in self._config.entity_types:
            raise OntologyEditError(f"Source entity type '{from_entity}' not found")
        if to_entity not in self._config.entity_types:
            raise OntologyEditError(f"Target entity type '{to_entity}' not found")

        existing = [r for r in self._config.relationships if r.name == name]
        if existing:
            raise OntologyEditError(f"Relationship '{name}' already exists")

        rel = RelationshipSchema(
            name=name,
            from_entity=from_entity,
            to_entity=to_entity,
            cardinality=cardinality,
            description=description,
            reverse_name=reverse_name,
        )
        if properties:
            rel.properties = {k: PropertySchema(**v) for k, v in properties.items()}

        self._config.relationships.append(rel)
        return (
            f"Added relationship '{name}': {from_entity} → {to_entity} "
            f"({cardinality})"
        )

    # ── Enums ─────────────────────────────────────────────────────

    def add_enum(
        self,
        name: str,
        values: list[str],
        *,
        ordered: bool = False,
        description: str | None = None,
    ) -> str:
        """Add a new enum vocabulary.

        Args:
            name: Enum name (e.g. ``"severity"``).
            values: List of enum values (e.g. ``["P0", "P1", "P2"]``).
            ordered: Whether the enum has a meaningful order.
            description: Optional description.

        Returns:
            A human-readable summary.

        Raises:
            OntologyEditError: If the enum already exists.
        """
        if name in self._config.enums:
            raise OntologyEditError(f"Enum '{name}' already exists")

        self._config.enums[name] = EnumSchema(
            values=values,
            ordered="low_to_high" if ordered else None,
            description=description,
        )
        return f"Added enum '{name}' with {len(values)} values"

    def add_enum_values(self, name: str, values: list[str]) -> str:
        """Add values to an existing enum.

        Args:
            name: Existing enum name.
            values: New values to append.

        Returns:
            A human-readable summary.

        Raises:
            OntologyEditError: If the enum does not exist or a value already exists.
        """
        if name not in self._config.enums:
            raise OntologyEditError(f"Enum '{name}' not found")

        enum = self._config.enums[name]
        existing = set(enum.values)
        added = [v for v in values if v not in existing]
        duplicates = [v for v in values if v in existing]

        if duplicates:
            raise OntologyEditError(
                f"Values already exist in enum '{name}': {duplicates}"
            )
        if not added:
            return f"No new values to add to enum '{name}'"

        object.__setattr__(enum, "values", list(enum.values) + added)
        return f"Added {len(added)} values to enum '{name}': {added}"

    # ── Serialization ─────────────────────────────────────────────

    def to_yaml(self) -> str:
        """Serialize the edited config to YAML for reload_config."""
        from cruxible_core.config.compact import dump_expanded

        return dump_expanded(self._config.model_dump(mode="json", exclude_none=True))

    def describe(self) -> str:
        """Return a human-readable summary of the config structure."""
        parts = [
            f"Entity types ({len(self._config.entity_types)}): "
            + ", ".join(sorted(self._config.entity_types)),
            f"Relationships ({len(self._config.relationships)}): "
            + ", ".join(sorted(r.name for r in self._config.relationships)),
            f"Enums ({len(self._config.enums)}): "
            + ", ".join(sorted(self._config.enums)),
        ]
        return "\n".join(parts)
