"""Shared pytest fixtures.

Sets up hermetic env vars BEFORE any import of `politicoresto_mcp.server`,
because the server module calls `load_settings()` at import time. Tests that
need to exercise config error paths should import `load_settings` directly and
use `monkeypatch.delenv` / `monkeypatch.setenv`.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any
from unittest.mock import AsyncMock

import pytest

# Set env before any server import. Values are fake but shaped correctly so
# that config.load_settings() accepts them.
os.environ.setdefault("SUPABASE_PROJECT_URL", "https://nvwpvckjsvicsyzpzjfi.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.pop("POLITICORESTO_ALLOW_PROD", None)


@pytest.fixture
def fake_client() -> AsyncMock:
    """Return a MagicMock shaped like `SupabaseClient` with async methods."""
    client = AsyncMock()
    client.select = AsyncMock(return_value=[])
    client.insert = AsyncMock(return_value=[])
    client.update = AsyncMock(return_value=[])
    client.upsert = AsyncMock(return_value=[])
    client.delete = AsyncMock(return_value=[])
    client.rpc = AsyncMock(return_value=None)
    return client


@pytest.fixture
def patch_server_client(
    monkeypatch: pytest.MonkeyPatch, fake_client: AsyncMock
) -> Iterator[AsyncMock]:
    """Swap the module-level ``politicoresto_mcp.server.client`` for ``fake_client``.

    Also resets the session state between tests.
    """
    from politicoresto_mcp import server as server_module
    from politicoresto_mcp.session import reset_state

    reset_state()
    monkeypatch.setattr(server_module, "client", fake_client)
    try:
        yield fake_client
    finally:
        reset_state()


@pytest.fixture
def tool() -> Callable[[str], Callable[..., Any]]:
    """Return a helper that resolves a tool by name to its plain Python callable.

    FastMCP wraps the decorated async functions; we want to call the underlying
    implementation directly in unit tests without going through MCP transport.
    """
    from politicoresto_mcp import server as server_module

    def _resolve(name: str) -> Callable[..., Any]:
        fn: Callable[..., Any] | None = getattr(server_module, name, None)
        if fn is None:
            raise AttributeError(f"No such tool on server module: {name}")
        return fn

    return _resolve


@pytest.fixture
async def set_acting_user_fixture(
    patch_server_client: AsyncMock, tool: Callable[[str], Callable[..., Any]]
) -> AsyncIterator[str]:
    """Pre-seed the session with an acting user so write-path tests can focus.

    Returns the user_id that was set.
    """
    user_id = "00000000-0000-0000-0000-000000000001"
    patch_server_client.select.return_value = [
        {"user_id": user_id, "username": "acting_user_for_tests"}
    ]
    await tool("set_acting_user")(user_id=user_id)
    # Reset return_value so subsequent calls in the test start fresh.
    patch_server_client.select.return_value = []
    yield user_id
