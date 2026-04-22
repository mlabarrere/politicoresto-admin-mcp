"""Tests for `politicoresto_mcp.supabase_client`.

Uses respx to mock the httpx transport so nothing hits the network.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from politicoresto_mcp.config import Settings
from politicoresto_mcp.supabase_client import SupabaseClient, SupabaseError

_STAGING_URL = "https://nvwpvckjsvicsyzpzjfi.supabase.co"
_REST_BASE = f"{_STAGING_URL}/rest/v1"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        supabase_url=_STAGING_URL,
        service_role_key="sk_test",
        project_ref="nvwpvckjsvicsyzpzjfi",
    )


@pytest.fixture
async def client(settings: Settings) -> SupabaseClient:
    return SupabaseClient(settings)


class TestSelect:
    @respx.mock
    async def test_basic_select(self, client: SupabaseClient) -> None:
        route = respx.get(f"{_REST_BASE}/topic").mock(
            return_value=httpx.Response(200, json=[{"id": "t1"}])
        )
        rows = await client.select("topic")
        assert rows == [{"id": "t1"}]
        assert route.called
        call = route.calls[0]
        assert call.request.url.params["select"] == "*"

    @respx.mock
    async def test_select_with_all_params(self, client: SupabaseClient) -> None:
        route = respx.get(f"{_REST_BASE}/topic").mock(return_value=httpx.Response(200, json=[]))
        await client.select(
            "topic",
            columns="id,slug",
            filters={"status": "eq.open"},
            order="created_at.desc",
            limit=10,
            offset=5,
        )
        params = route.calls[0].request.url.params
        assert params["select"] == "id,slug"
        assert params["status"] == "eq.open"
        assert params["order"] == "created_at.desc"
        assert params["limit"] == "10"
        assert params["offset"] == "5"

    @respx.mock
    async def test_auth_headers_are_attached(self, client: SupabaseClient) -> None:
        route = respx.get(f"{_REST_BASE}/topic").mock(return_value=httpx.Response(200, json=[]))
        await client.select("topic")
        headers = route.calls[0].request.headers
        assert headers["apikey"] == "sk_test"
        assert headers["authorization"] == "Bearer sk_test"
        assert "return=representation" in headers["prefer"]

    @respx.mock
    async def test_non_list_payload_raises(self, client: SupabaseClient) -> None:
        respx.get(f"{_REST_BASE}/topic").mock(
            return_value=httpx.Response(200, json={"not": "a list"})
        )
        with pytest.raises(SupabaseError, match="expected a JSON array"):
            await client.select("topic")


class TestInsert:
    @respx.mock
    async def test_insert_single_dict_wraps_to_list(self, client: SupabaseClient) -> None:
        route = respx.post(f"{_REST_BASE}/topic").mock(
            return_value=httpx.Response(201, json=[{"id": "t1"}])
        )
        rows = await client.insert("topic", {"title": "hi"})
        assert rows == [{"id": "t1"}]
        sent = route.calls[0].request.content
        assert b"[" in sent  # list payload
        assert b"title" in sent

    @respx.mock
    async def test_insert_list_passthrough(self, client: SupabaseClient) -> None:
        respx.post(f"{_REST_BASE}/topic").mock(
            return_value=httpx.Response(201, json=[{"id": "a"}, {"id": "b"}])
        )
        rows = await client.insert("topic", [{"title": "a"}, {"title": "b"}])
        assert len(rows) == 2


class TestUpdate:
    @respx.mock
    async def test_update_with_filters(self, client: SupabaseClient) -> None:
        route = respx.patch(f"{_REST_BASE}/topic").mock(
            return_value=httpx.Response(200, json=[{"id": "t1"}])
        )
        await client.update("topic", {"title": "new"}, filters={"id": "eq.t1"})
        assert route.calls[0].request.url.params["id"] == "eq.t1"

    async def test_update_without_filters_raises(self, client: SupabaseClient) -> None:
        with pytest.raises(ValueError, match="requires filters"):
            await client.update("topic", {"title": "x"}, filters={})


class TestUpsert:
    @respx.mock
    async def test_upsert_with_on_conflict(self, client: SupabaseClient) -> None:
        route = respx.post(f"{_REST_BASE}/app_profile").mock(
            return_value=httpx.Response(200, json=[{"user_id": "u1"}])
        )
        await client.upsert("app_profile", {"user_id": "u1"}, on_conflict="user_id")
        req = route.calls[0].request
        assert req.url.params["on_conflict"] == "user_id"
        assert "merge-duplicates" in req.headers["prefer"]


class TestDelete:
    @respx.mock
    async def test_delete_with_filters(self, client: SupabaseClient) -> None:
        route = respx.delete(f"{_REST_BASE}/topic").mock(
            return_value=httpx.Response(200, json=[{"id": "t1"}])
        )
        rows = await client.delete("topic", filters={"id": "eq.t1"})
        assert rows == [{"id": "t1"}]
        assert route.calls[0].request.url.params["id"] == "eq.t1"

    async def test_delete_without_filters_raises(self, client: SupabaseClient) -> None:
        with pytest.raises(ValueError, match="requires filters"):
            await client.delete("topic", filters={})


class TestRpc:
    @respx.mock
    async def test_rpc_passes_args(self, client: SupabaseClient) -> None:
        route = respx.post(f"{_REST_BASE}/rpc/do_thing").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )
        payload = await client.rpc("do_thing", {"x": 1})
        assert payload == {"ok": True}
        assert b'"x":1' in route.calls[0].request.content.replace(b" ", b"")

    @respx.mock
    async def test_rpc_with_no_args(self, client: SupabaseClient) -> None:
        route = respx.post(f"{_REST_BASE}/rpc/do_thing").mock(
            return_value=httpx.Response(200, json=[])
        )
        out = await client.rpc("do_thing")
        assert out == []
        # Body should be "{}" (no args -> empty dict).
        assert route.calls[0].request.content.strip() == b"{}"


class TestErrorHandling:
    @respx.mock
    async def test_4xx_raises_with_json_detail(self, client: SupabaseClient) -> None:
        respx.get(f"{_REST_BASE}/topic").mock(
            return_value=httpx.Response(404, json={"code": "PGRST116", "message": "not found"})
        )
        with pytest.raises(SupabaseError) as exc:
            await client.select("topic")
        assert exc.value.status_code == 404
        assert isinstance(exc.value.detail, dict)
        assert exc.value.detail["code"] == "PGRST116"

    @respx.mock
    async def test_5xx_with_non_json_falls_back_to_text(self, client: SupabaseClient) -> None:
        respx.get(f"{_REST_BASE}/topic").mock(return_value=httpx.Response(502, text="Bad Gateway"))
        with pytest.raises(SupabaseError) as exc:
            await client.select("topic")
        assert exc.value.status_code == 502
        assert exc.value.detail == "Bad Gateway"


async def test_close_disposes_the_inner_client(client: SupabaseClient) -> None:
    await client.close()
    # Calling close twice should not raise (httpx.AsyncClient is idempotent).
    await client.close()
