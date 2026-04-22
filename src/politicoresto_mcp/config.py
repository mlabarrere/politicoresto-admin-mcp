"""Configuration du serveur MCP.

Charge les variables d'environnement et applique les garde-fous.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from urllib.parse import urlparse

from dotenv import load_dotenv

PROD_PROJECT_REF = "gzdpisxkavpyfmhsktcg"
STAGING_PROJECT_REF = "nvwpvckjsvicsyzpzjfi"


@dataclass(frozen=True)
class Settings:
    """Configuration runtime, immuable une fois chargée."""

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
    """Extrait le ref projet depuis une URL Supabase.

    Ex: https://nvwpvckjsvicsyzpzjfi.supabase.co -> nvwpvckjsvicsyzpzjfi
    """
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if not host.endswith(".supabase.co"):
        raise ValueError(f"URL Supabase invalide: {url}")
    return host.split(".")[0]


def load_settings() -> Settings:
    """Charge et valide la config. Sort si invalide."""
    load_dotenv()

    supabase_url = os.environ.get("SUPABASE_PROJECT_URL", "").strip().rstrip("/")
    service_role_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    allow_prod = os.environ.get("POLITICORESTO_ALLOW_PROD", "").strip()

    if not supabase_url:
        print("ERROR: SUPABASE_PROJECT_URL manquant", file=sys.stderr)
        sys.exit(1)

    if not service_role_key:
        print("ERROR: SUPABASE_SERVICE_ROLE_KEY manquant", file=sys.stderr)
        sys.exit(1)

    try:
        project_ref = _extract_project_ref(supabase_url)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    # Garde-fou prod : ne démarre pas contre prod sans override explicite
    if project_ref == PROD_PROJECT_REF and allow_prod != "yes_i_know":
        print(
            "ERROR: Ce MCP est configuré pour pointer sur PROD "
            f"(ref={PROD_PROJECT_REF}). "
            "Si c'est vraiment voulu, définis POLITICORESTO_ALLOW_PROD=yes_i_know. "
            "Sinon corrige SUPABASE_PROJECT_URL vers staging.",
            file=sys.stderr,
        )
        sys.exit(1)

    return Settings(
        supabase_url=supabase_url,
        service_role_key=service_role_key,
        project_ref=project_ref,
    )
