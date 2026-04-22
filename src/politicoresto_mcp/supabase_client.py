"""HTTP client for Supabase PostgREST and RPC.

We talk to PostgREST directly via httpx rather than depending on `supabase-py`.
That keeps the dependency footprint small, gives precise control over request
shape, and reduces the attack surface of a public repository.
"""

from __future__ import annotations

from typing import Any

import httpx

from .config import Settings

_JsonRow = dict[str, Any]
_JsonRows = list[_JsonRow]


class SupabaseError(Exception):
    """Error returned by PostgREST or raised by this wrapper."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        detail: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


class SupabaseClient:
    """Thin httpx wrapper over PostgREST.

    Every request uses the service_role key, so Row-Level Security is bypassed.
    There is no per-user token handling here — that is deliberate; this client
    is admin-only.
    """

    def __init__(self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None):
        self._settings = settings
        client_kwargs: dict[str, Any] = {
            "base_url": settings.rest_url,
            "headers": {
                "apikey": settings.service_role_key,
                "Authorization": f"Bearer {settings.service_role_key}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
            "timeout": 30.0,
        }
        if transport is not None:
            client_kwargs["transport"] = transport
        self._client = httpx.AsyncClient(**client_kwargs)

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
    ) -> _JsonRows:
        """Run a SELECT against PostgREST.

        Args:
            table: table name.
            columns: comma-separated column list or "*".
            filters: dict of ``{column: "op.value"}`` in PostgREST syntax.
                Example: ``{"status": "eq.published", "created_at": "gte.2026-01-01"}``.
            order: PostgREST order clause, e.g. ``"created_at.desc"``.
            limit: maximum rows to return.
            offset: rows to skip.
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
        return self._as_rows(resp)

    async def insert(self, table: str, rows: _JsonRow | _JsonRows) -> _JsonRows:
        """Run an INSERT via PostgREST and return the created rows."""
        payload = rows if isinstance(rows, list) else [rows]
        resp = await self._client.post(f"/{table}", json=payload)
        self._raise_for_error(resp)
        return self._as_rows(resp)

    async def update(
        self,
        table: str,
        values: _JsonRow,
        *,
        filters: dict[str, str],
    ) -> _JsonRows:
        """Run an UPDATE via PostgREST. Filters are required to avoid a global update."""
        if not filters:
            raise ValueError("update() requires filters to avoid a global update")
        resp = await self._client.patch(f"/{table}", params=filters, json=values)
        self._raise_for_error(resp)
        return self._as_rows(resp)

    async def upsert(
        self,
        table: str,
        rows: _JsonRow | _JsonRows,
        *,
        on_conflict: str | None = None,
    ) -> _JsonRows:
        """Run an UPSERT via PostgREST (``Prefer: resolution=merge-duplicates``)."""
        payload = rows if isinstance(rows, list) else [rows]
        headers = {"Prefer": "return=representation,resolution=merge-duplicates"}
        params: dict[str, str] = {}
        if on_conflict:
            params["on_conflict"] = on_conflict
        resp = await self._client.post(f"/{table}", json=payload, headers=headers, params=params)
        self._raise_for_error(resp)
        return self._as_rows(resp)

    async def delete(self, table: str, *, filters: dict[str, str]) -> _JsonRows:
        """Run a DELETE via PostgREST. Filters are required to avoid a global delete."""
        if not filters:
            raise ValueError("delete() requires filters to avoid a global delete")
        resp = await self._client.delete(f"/{table}", params=filters)
        self._raise_for_error(resp)
        return self._as_rows(resp)

    async def rpc(self, function_name: str, args: dict[str, Any] | None = None) -> Any:
        """Call a SQL function (RPC endpoint)."""
        resp = await self._client.post(f"/rpc/{function_name}", json=args or {})
        self._raise_for_error(resp)
        return resp.json()

    @staticmethod
    def _as_rows(resp: httpx.Response) -> _JsonRows:
        payload = resp.json()
        if not isinstance(payload, list):
            raise SupabaseError(
                "Unexpected PostgREST response: expected a JSON array",
                status_code=resp.status_code,
                detail=payload,
            )
        return payload

    @staticmethod
    def _raise_for_error(resp: httpx.Response) -> None:
        if resp.is_success:
            return
        try:
            detail: Any = resp.json()
        except ValueError:
            detail = resp.text
        raise SupabaseError(
            f"Supabase request failed: {resp.status_code}",
            status_code=resp.status_code,
            detail=detail,
        )
