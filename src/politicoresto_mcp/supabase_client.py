"""Client HTTP vers PostgREST + RPC Supabase.

Pas de dépendance sur supabase-py : on parle directement à PostgREST,
ce qui donne un contrôle fin et évite une grosse dépendance pour peu de features.
"""

from __future__ import annotations

from typing import Any

import httpx

from .config import Settings


class SupabaseError(Exception):
    """Erreur retournée par PostgREST ou le wrapper."""

    def __init__(self, message: str, status_code: int | None = None, detail: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


class SupabaseClient:
    """Wrapper httpx pour PostgREST.

    Toutes les requêtes utilisent la service_role key → bypass RLS.
    Pas de gestion d'user token ici, c'est volontaire (admin mode only).
    """

    def __init__(self, settings: Settings):
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.rest_url,
            headers={
                "apikey": settings.service_role_key,
                "Authorization": f"Bearer {settings.service_role_key}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
            timeout=30.0,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def select(
        self,
        table: str,
        *,
        columns: str = "*",
        filters: dict[str, str] | None = None,
        order: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[dict[str, Any]]:
        """SELECT via PostgREST.

        filters : dict de {column: "op.value"} au format PostgREST
                  ex: {"status": "eq.published", "created_at": "gte.2026-01-01"}
        """
        params: dict[str, Any] = {"select": columns}
        if filters:
            params.update(filters)
        if order:
            params["order"] = order
        if limit is not None:
            params["limit"] = str(limit)
        if offset is not None:
            params["offset"] = str(offset)

        resp = await self._client.get(f"/{table}", params=params)
        self._raise_for_error(resp)
        return resp.json()

    async def insert(self, table: str, rows: dict | list[dict]) -> list[dict[str, Any]]:
        """INSERT via PostgREST, retourne la/les ligne(s) insérée(s)."""
        payload = rows if isinstance(rows, list) else [rows]
        resp = await self._client.post(f"/{table}", json=payload)
        self._raise_for_error(resp)
        return resp.json()

    async def update(
        self,
        table: str,
        values: dict[str, Any],
        *,
        filters: dict[str, str],
    ) -> list[dict[str, Any]]:
        """UPDATE via PostgREST. filters obligatoire pour éviter update global."""
        if not filters:
            raise ValueError("update() nécessite des filters pour éviter un update global")
        resp = await self._client.patch(f"/{table}", params=filters, json=values)
        self._raise_for_error(resp)
        return resp.json()

    async def upsert(
        self,
        table: str,
        rows: dict | list[dict],
        *,
        on_conflict: str | None = None,
    ) -> list[dict[str, Any]]:
        """UPSERT via PostgREST (Prefer: resolution=merge-duplicates)."""
        payload = rows if isinstance(rows, list) else [rows]
        headers = {"Prefer": "return=representation,resolution=merge-duplicates"}
        params = {"on_conflict": on_conflict} if on_conflict else {}
        resp = await self._client.post(
            f"/{table}", json=payload, headers=headers, params=params
        )
        self._raise_for_error(resp)
        return resp.json()

    async def delete(self, table: str, *, filters: dict[str, str]) -> list[dict[str, Any]]:
        """DELETE via PostgREST. filters obligatoire."""
        if not filters:
            raise ValueError("delete() nécessite des filters pour éviter un delete global")
        resp = await self._client.delete(f"/{table}", params=filters)
        self._raise_for_error(resp)
        return resp.json()

    async def rpc(self, function_name: str, args: dict[str, Any] | None = None) -> Any:
        """Appel d'une fonction SQL (RPC)."""
        resp = await self._client.post(f"/rpc/{function_name}", json=args or {})
        self._raise_for_error(resp)
        return resp.json()

    @staticmethod
    def _raise_for_error(resp: httpx.Response) -> None:
        if resp.is_success:
            return
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text
        raise SupabaseError(
            f"Supabase request failed: {resp.status_code}",
            status_code=resp.status_code,
            detail=detail,
        )
