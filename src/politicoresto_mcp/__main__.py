"""Entry point for the PoliticoResto MCP server."""

from __future__ import annotations

import sys

from .config import ConfigError


def main() -> int:
    """Start the MCP server over stdio.

    Returns:
        Process exit code. 0 on clean shutdown, 1 on configuration error.
    """
    try:
        # Importing server triggers load_settings() at module level; we want
        # any ConfigError to surface here as a clean CLI message, not a
        # traceback.
        from .server import mcp, settings
    except ConfigError as err:
        sys.stderr.write(f"ERROR: {err}\n")
        return 1

    sys.stderr.write(
        f"[politicoresto-admin-mcp] Starting against project {settings.project_ref} "
        f"({'STAGING' if settings.is_staging else 'PROD' if settings.is_prod else 'OTHER'})\n"
    )
    mcp.run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
