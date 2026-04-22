"""Point d'entrée du serveur MCP PoliticoResto."""

from __future__ import annotations

import sys

from .server import mcp, settings


def main() -> None:
    """Démarre le serveur MCP en transport stdio."""
    print(
        f"[politicoresto-mcp] Starting against project {settings.project_ref} "
        f"({'STAGING' if settings.is_staging else 'PROD' if settings.is_prod else 'OTHER'})",
        file=sys.stderr,
    )
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
