"""Service functions for programmatic ontology editing.

Each function loads the current CoreConfig, applies one or more
changes via :class:`ConfigEditor`, and optionally applies the
modified config back to the instance.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cruxible_core.config.editor import ConfigEditor, OntologyEditError
from cruxible_core.config.loader import load_config
from cruxible_core.config.schema import CoreConfig
from cruxible_core.errors import ConfigError
from cruxible_core.instance_protocol import InstanceProtocol
from cruxible_core.service.lifecycle import service_reload_config
from cruxible_core.service.queries import service_schema


def _load_editor(instance: InstanceProtocol) -> ConfigEditor:
    """Load the current ontology config and wrap it in an editor."""
    config = service_schema(instance)
    return ConfigEditor(config)


def _apply_edit(
    instance: InstanceProtocol,
    editor: ConfigEditor,
    *,
    dry_run: bool = False,
    summary: str,
) -> dict[str, Any]:
    """Apply the edited config if not dry_run, return result dict."""
    new_yaml = editor.to_yaml()
    result = {
        "summary": summary,
        "config_yaml": new_yaml,
        "dry_run": dry_run,
    }

    if not dry_run:
        reload_result = service_reload_config(
            instance,
            config_yaml=new_yaml,
        )
        result["reload_status"] = reload_result.status
        result["warnings"] = reload_result.warnings

    return result


def service_entity_type_add(
    instance: InstanceProtocol,
    name: str,
    *,
    properties: dict[str, dict[str, Any]] | None = None,
    description: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Add a new entity type to the ontology."""
    editor = _load_editor(instance)
    summary = editor.add_entity_type(name, properties=properties, description=description)
    return _apply_edit(instance, editor, dry_run=dry_run, summary=summary)


def service_entity_type_update(
    instance: InstanceProtocol,
    name: str,
    *,
    add_properties: dict[str, dict[str, Any]] | None = None,
    set_description: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Add properties to an existing entity type."""
    editor = _load_editor(instance)
    summary = editor.update_entity_type(
        name,
        add_properties=add_properties,
        set_description=set_description,
    )
    return _apply_edit(instance, editor, dry_run=dry_run, summary=summary)


def service_relationship_add(
    instance: InstanceProtocol,
    name: str,
    from_entity: str,
    to_entity: str,
    *,
    cardinality: str = "many_to_many",
    properties: dict[str, dict[str, Any]] | None = None,
    description: str | None = None,
    reverse_name: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Add a new relationship to the ontology."""
    editor = _load_editor(instance)
    summary = editor.add_relationship(
        name,
        from_entity,
        to_entity,
        cardinality=cardinality,
        properties=properties,
        description=description,
        reverse_name=reverse_name,
    )
    return _apply_edit(instance, editor, dry_run=dry_run, summary=summary)


def service_enum_add(
    instance: InstanceProtocol,
    name: str,
    values: list[str],
    *,
    ordered: bool = False,
    description: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Add a new enum vocabulary."""
    editor = _load_editor(instance)
    summary = editor.add_enum(name, values, ordered=ordered, description=description)
    return _apply_edit(instance, editor, dry_run=dry_run, summary=summary)


def service_enum_value_add(
    instance: InstanceProtocol,
    name: str,
    values: list[str],
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Add values to an existing enum."""
    editor = _load_editor(instance)
    summary = editor.add_enum_values(name, values)
    return _apply_edit(instance, editor, dry_run=dry_run, summary=summary)


def service_ontology_describe(
    instance: InstanceProtocol,
) -> str:
    """Return a human-readable summary of the ontology."""
    editor = _load_editor(instance)
    return editor.describe()


# Short-name aliases for import convenience
add_entity_type = service_entity_type_add
add_relationship = service_relationship_add
add_enum = service_enum_add
add_enum_values = service_enum_value_add
describe = service_ontology_describe
