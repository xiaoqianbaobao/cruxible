from __future__ import annotations

import os

from cruxible_core.mcp.server import configure_structlog, create_server, validate_runtime_tools


def main() -> None:
    configure_structlog()
    server = create_server()
    validate_runtime_tools(server)
    transport = os.getenv("CRUXIBLE_MCP_TRANSPORT", "sse")
    if transport not in ("sse", "streamable-http", "stdio"):
        raise ValueError(f"Unsupported CRUXIBLE_MCP_TRANSPORT={transport!r}")
    server.run(transport=transport)  # type: ignore[arg-type]


if __name__ == "__main__":
    main()
