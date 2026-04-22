"""Runtime configuration for the MCP server.

Loads environment variables, validates them, and applies the production
safeguard. `load_settings` raises `ConfigError` on any invalid input so
callers (CLI, tests) can decide how to react.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse

from dotenv import load_dotenv

PROD_PROJECT_REF = "gzdpisxkavpyfmhsktcg"
STAGING_PROJECT_REF = "nvwpvckjsvicsyzpzjfi"

PROD_OVERRIDE_VALUE = "yes_i_know"


class ConfigError(RuntimeError):
    """Raised when the runtime configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    """Immutable runtime configuration."""

    supabase_url: str
    service_role_key: str
    project_ref: str

    @property
    def rest_url(self) -> str:
        return f"{self.supabase_url}/rest/v1"

    @property
    def is_prod(self) -> bool:
        return self.project_ref == PROD_PROJECT_REF

    @property
    def is_staging(self) -> bool:
        return self.project_ref == STAGING_PROJECT_REF


def _extract_project_ref(url: str) -> str:
    """Extract the project ref from a Supabase URL.

    Example:
        https://nvwpvckjsvicsyzpzjfi.supabase.co -> nvwpvckjsvicsyzpzjfi
    """
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if not host.endswith(".supabase.co"):
        raise ConfigError(f"Invalid Supabase URL: {url}")
    return host.split(".")[0]


def load_settings(*, load_dotenv_file: bool = True) -> Settings:
    """Load and validate the runtime configuration.

    Args:
        load_dotenv_file: when True (default), read variables from a local
            `.env` file before reading the process environment. Disabled in
            tests to keep them hermetic.

    Raises:
        ConfigError: when a required variable is missing, the URL is malformed,
            or the URL points to production without the opt-in override.
    """
    if load_dotenv_file:
        load_dotenv()

    supabase_url = os.environ.get("SUPABASE_PROJECT_URL", "").strip().rstrip("/")
    service_role_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    allow_prod = os.environ.get("POLITICORESTO_ALLOW_PROD", "").strip()

    if not supabase_url:
        raise ConfigError("SUPABASE_PROJECT_URL is required")
    if not service_role_key:
        raise ConfigError("SUPABASE_SERVICE_ROLE_KEY is required")

    project_ref = _extract_project_ref(supabase_url)

    if project_ref == PROD_PROJECT_REF and allow_prod != PROD_OVERRIDE_VALUE:
        raise ConfigError(
            f"Refusing to start: SUPABASE_PROJECT_URL points to production "
            f"(ref={PROD_PROJECT_REF}). "
            f"If that is truly intended, set POLITICORESTO_ALLOW_PROD={PROD_OVERRIDE_VALUE}. "
            "Otherwise point SUPABASE_PROJECT_URL at staging."
        )

    return Settings(
        supabase_url=supabase_url,
        service_role_key=service_role_key,
        project_ref=project_ref,
    )
