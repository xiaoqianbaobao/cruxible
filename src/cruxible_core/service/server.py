"""Server-level service helpers that do not depend on a specific instance."""

from __future__ import annotations

import os

from cruxible_core import __version__
from cruxible_core.mcp.default_instance import ENV_DEFAULT_INSTANCE_ID
from cruxible_core.runtime.permissions import get_current_mode
from cruxible_core.server.config import (
    get_server_state_dir,
    is_server_auth_enabled,
    is_server_required,
)
from cruxible_core.server.credentials import get_runtime_credential_store
from cruxible_core.server.registry import get_registry
from cruxible_core.service.types import ServerInfoServiceResult


def _configured_default_instance_id() -> str | None:
    raw = (os.environ.get(ENV_DEFAULT_INSTANCE_ID) or "").strip()
    return raw or None


def service_server_info() -> ServerInfoServiceResult:
    """Return live daemon metadata for local hardening and diagnostics."""
    credential_store = get_runtime_credential_store()
    try:
        mode_value = get_current_mode().name.lower()
    except Exception:  # noqa: BLE001  — best-effort surface
        mode_value = None
    return ServerInfoServiceResult(
        server_required=is_server_required(),
        state_dir=str(get_server_state_dir()),
        version=__version__,
        instance_count=get_registry().count_instances(),
        auth_enabled=is_server_auth_enabled(),
        auth_required=credential_store.is_auth_required(),
        default_instance_id=_configured_default_instance_id(),
        permission_mode=mode_value,
    )
