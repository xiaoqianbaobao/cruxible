"""Default-instance resolution helpers for MCP tool surface.

Why this exists
---------------
End users should never be forced to remember or paste an opaque
``instance_id`` just because they want to query/write Cruxible state.
Instead, operators expose a **default instance** via the
``CRUXIBLE_DEFAULT_INSTANCE_ID`` environment variable, and every
instance-scoped MCP tool transparently falls back to it when the
caller omits ``instance_id``.

Resolution rules
----------------
1. If the caller supplied an explicit non-empty ``instance_id``, use
   it unchanged and return a ``resolved=False`` marker so callers can
   still audit whether substitution happened.
2. Otherwise read ``CRUXIBLE_DEFAULT_INSTANCE_ID``. Leading/trailing
   whitespace is trimmed.
3. If the env var is unset/empty, raise ``ConfigError`` with a clear
   operator action.

This module is intentionally tiny: it's the seam between the MCP
surface and operator configuration, so keeping the logic auditable is
more valuable than cleverness.
"""

from __future__ import annotations

import os

from cruxible_core.errors import ConfigError

ENV_DEFAULT_INSTANCE_ID = "CRUXIBLE_DEFAULT_INSTANCE_ID"


def resolve_default_instance_id(explicit_instance_id: str | None) -> tuple[str, bool]:
    """Resolve the effective instance_id for an instance-scoped tool call.

    Returns:
        A 2-tuple ``(effective_instance_id, used_default)``.

        - ``effective_instance_id``: the ID to use for downstream handlers.
        - ``used_default``: ``True`` when the value came from
          ``CRUXIBLE_DEFAULT_INSTANCE_ID`` because the caller omitted
          an explicit value. ``False`` when the caller's value was used.

    Raises:
        ConfigError: caller omitted the value AND no default is configured.
    """
    explicit = explicit_instance_id.strip() if isinstance(explicit_instance_id, str) else ""
    if explicit:
        return explicit, False

    configured = (os.environ.get(ENV_DEFAULT_INSTANCE_ID) or "").strip()
    if not configured:
        raise ConfigError(
            "instance_id is required for this tool call because no default "
            f"is configured. Set {ENV_DEFAULT_INSTANCE_ID}=<instance_id> in the "
            "Cruxible MCP server's environment, or pass instance_id explicitly."
        )
    return configured, True
