"""Tests for the 12 MCP tools exposed by `politicoresto_mcp.server`.

These tests exercise the underlying async functions (not the MCP transport).
They rely on the `patch_server_client` fixture to swap the module-level
Supabase client for an AsyncMock; all DB calls are verified by inspecting
the mock's call_args.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock

import pytest

from politicoresto_mcp.session import get_state
from politicoresto_mcp.supabase_client import SupabaseError


def _last_call(mock: AsyncMock) -> tuple[tuple[Any, ...], dict[str, Any]]:
    """Return positional args and kwargs of the mock's last call."""
    assert mock.call_args is not None
    args: tuple[Any, ...] = tuple(mock.call_args.args)
    kwargs: dict[str, Any] = dict(mock.call_args.kwargs)
    return args, kwargs


# ---------------------------------------------------------------------------
# Session tools: set_acting_user / get_acting_user
# ---------------------------------------------------------------------------


class TestSetActingUser:
    async def test_happy_path(
        self,
        patch_server_client: AsyncMock,
        tool: Callable[[str], Callable[..., Any]],
    ) -> None:
        user_id = "u-1"
        patch_server_client.select.return_value = [{"user_id": user_id, "username": "alice"}]
        out = await tool("set_acting_user")(user_id=user_id)
        assert out["acting_user"]["user_id"] == user_id
        assert "alice" in out["message"]
        assert get_state().acting_user_id == user_id

    async def test_unknown_user_raises(
        self,
        patch_server_client: AsyncMock,
        tool: Callable[[str], Callable[..., Any]],
    ) -> None:
        patch_server_client.select.return_value = []
        with pytest.raises(ValueError, match="No app_profile"):
            await tool("set_acting_user")(user_id="nope")
        assert get_state().acting_user_id is None

    async def test_falls_back_to_user_id_when_no_username(
        self,
        patch_server_client: AsyncMock,
        tool: Callable[[str], Callable[..., Any]],
    ) -> None:
        patch_server_client.select.return_value = [{"user_id": "u-2", "username": None}]
        out = await tool("set_acting_user")(user_id="u-2")
        assert "u-2" in out["message"]


class TestGetActingUser:
    async def test_returns_none_when_unset(
        self,
        patch_server_client: AsyncMock,
        tool: Callable[[str], Callable[..., Any]],
    ) -> None:
        out = await tool("get_acting_user")()
        assert out["acting_user_id"] is None

    async def test_returns_profile_when_set(
        self,
        set_acting_user_fixture: str,
        patch_server_client: AsyncMock,
        tool: Callable[[str], Callable[..., Any]],
    ) -> None:
        patch_server_client.select.return_value = [
            {"user_id": set_acting_user_fixture, "username": "alice"}
        ]
        out = await tool("get_acting_user")()
        assert out["acting_user_id"] == set_acting_user_fixture
        assert out["acting_user"]["username"] == "alice"


# ---------------------------------------------------------------------------
# Read tools
# ---------------------------------------------------------------------------


class TestListProfiles:
    async def test_defaults(
        self,
        patch_server_client: AsyncMock,
        tool: Callable[[str], Callable[..., Any]],
    ) -> None:
        patch_server_client.select.return_value = [{"user_id": "u1"}]
        out = await tool("list_profiles")()
        assert out == [{"user_id": "u1"}]
        _, kwargs = _last_call(patch_server_client.select)
        assert kwargs["limit"] == 50
        assert kwargs["offset"] == 0
        assert kwargs["order"] == "created_at.desc"


class TestListTopics:
    async def test_no_filters(
        self,
        patch_server_client: AsyncMock,
        tool: Callable[[str], Callable[..., Any]],
    ) -> None:
        patch_server_client.select.return_value = []
        await tool("list_topics")()
        _, kwargs = _last_call(patch_server_client.select)
        assert kwargs["filters"] == {}
        assert kwargs["limit"] == 20

    async def test_with_filters(
        self,
        patch_server_client: AsyncMock,
        tool: Callable[[str], Callable[..., Any]],
    ) -> None:
        patch_server_client.select.return_value = []
        await tool("list_topics")(status="open", visibility="public", limit=5)
        _, kwargs = _last_call(patch_server_client.select)
        assert kwargs["filters"] == {
            "topic_status": "eq.open",
            "visibility": "eq.public",
        }
        assert kwargs["limit"] == 5


class TestGetTopic:
    async def test_by_uuid(
        self,
        patch_server_client: AsyncMock,
        tool: Callable[[str], Callable[..., Any]],
    ) -> None:
        uuid = "00000000-0000-0000-0000-000000000abc"
        patch_server_client.select.side_effect = [
            [{"id": uuid, "slug": "foo"}],  # topic lookup
            [{"id": "tp-1"}],  # thread_posts
            [{"id": "p-1"}],  # comments for tp-1
        ]
        out = await tool("get_topic")(topic_id_or_slug=uuid)
        assert out["topic"]["id"] == uuid
        assert out["thread_posts"][0]["comments"] == [{"id": "p-1"}]
        # First select must have filtered on id, not slug.
        first_call_kwargs = patch_server_client.select.call_args_list[0].kwargs
        assert first_call_kwargs["filters"] == {"id": f"eq.{uuid}"}

    async def test_by_slug(
        self,
        patch_server_client: AsyncMock,
        tool: Callable[[str], Callable[..., Any]],
    ) -> None:
        patch_server_client.select.side_effect = [
            [{"id": "t1", "slug": "my-slug"}],
            [],
        ]
        await tool("get_topic")(topic_id_or_slug="my-slug")
        first_call_kwargs = patch_server_client.select.call_args_list[0].kwargs
        assert first_call_kwargs["filters"] == {"slug": "eq.my-slug"}

    async def test_not_found_raises(
        self,
        patch_server_client: AsyncMock,
        tool: Callable[[str], Callable[..., Any]],
    ) -> None:
        patch_server_client.select.return_value = []
        with pytest.raises(ValueError, match="Topic not found"):
            await tool("get_topic")(topic_id_or_slug="missing")


class TestListVoteHistory:
    async def test_empty_history(
        self,
        patch_server_client: AsyncMock,
        tool: Callable[[str], Callable[..., Any]],
    ) -> None:
        patch_server_client.select.return_value = []
        out = await tool("list_vote_history")(user_id="u1")
        assert out == []
        assert patch_server_client.select.call_count == 1  # no election lookup

    async def test_enriches_with_elections(
        self,
        patch_server_client: AsyncMock,
        tool: Callable[[str], Callable[..., Any]],
    ) -> None:
        patch_server_client.select.side_effect = [
            [
                {"election_id": "e1", "user_id": "u1"},
                {"election_id": "e2", "user_id": "u1"},
            ],
            [
                {"id": "e1", "name": "Election 1"},
                {"id": "e2", "name": "Election 2"},
            ],
        ]
        out = await tool("list_vote_history")(user_id="u1")
        assert out[0]["election"]["name"] == "Election 1"
        assert out[1]["election"]["name"] == "Election 2"
        # Second select should batch elections via in.()
        second = patch_server_client.select.call_args_list[1].kwargs
        assert second["filters"] == {"id": "in.(e1,e2)"}


# ---------------------------------------------------------------------------
# Write tools: require acting user
# ---------------------------------------------------------------------------


class TestActingUserRequired:
    """Every write tool must refuse to run before set_acting_user."""

    @pytest.mark.parametrize(
        "name,kwargs",
        [
            (
                "create_topic_with_initial_post",
                {
                    "slug": "s",
                    "title": "t",
                    "thread_post_content": "body",
                },
            ),
            (
                "create_post",
                {"thread_post_id": "tp-1", "body_markdown": "x"},
            ),
            (
                "react_to",
                {
                    "target_type": "thread_post",
                    "target_id": "tp-1",
                    "reaction_type": "upvote",
                },
            ),
        ],
    )
    async def test_raises(
        self,
        patch_server_client: AsyncMock,
        tool: Callable[[str], Callable[..., Any]],
        name: str,
        kwargs: dict[str, Any],
    ) -> None:
        with pytest.raises(RuntimeError, match="No acting user is set"):
            await tool(name)(**kwargs)


# ---------------------------------------------------------------------------
# Write tools: create_topic_with_initial_post
# ---------------------------------------------------------------------------


class TestCreateTopicWithInitialPost:
    async def test_happy_path(
        self,
        set_acting_user_fixture: str,
        patch_server_client: AsyncMock,
        tool: Callable[[str], Callable[..., Any]],
    ) -> None:
        patch_server_client.insert.side_effect = [
            [{"id": "topic-1", "slug": "s"}],
            [{"id": "tp-1", "thread_id": "topic-1"}],
        ]
        out = await tool("create_topic_with_initial_post")(
            slug="s",
            title="T",
            thread_post_content="body",
        )
        assert out["topic"]["id"] == "topic-1"
        assert out["thread_post"]["id"] == "tp-1"
        # No rollback, no delete call
        patch_server_client.delete.assert_not_called()
        # Uses acting user as created_by
        topic_payload = patch_server_client.insert.call_args_list[0].args[1]
        assert topic_payload["created_by"] == set_acting_user_fixture

    async def test_rollback_on_thread_post_failure(
        self,
        set_acting_user_fixture: str,
        patch_server_client: AsyncMock,
        tool: Callable[[str], Callable[..., Any]],
    ) -> None:
        patch_server_client.insert.side_effect = [
            [{"id": "topic-1", "slug": "s"}],
            SupabaseError("thread_post insert failed", status_code=400),
        ]
        with pytest.raises(SupabaseError):
            await tool("create_topic_with_initial_post")(
                slug="s", title="T", thread_post_content="body"
            )
        # Rollback: delete called on the orphan topic.
        patch_server_client.delete.assert_awaited_once()
        args, kwargs = _last_call(patch_server_client.delete)
        assert args[0] == "topic"
        assert kwargs["filters"] == {"id": "eq.topic-1"}


# ---------------------------------------------------------------------------
# Write tools: create_post
# ---------------------------------------------------------------------------


class TestCreatePost:
    async def test_root_post(
        self,
        set_acting_user_fixture: str,
        patch_server_client: AsyncMock,
        tool: Callable[[str], Callable[..., Any]],
    ) -> None:
        patch_server_client.select.return_value = [{"id": "tp-1", "thread_id": "topic-1"}]
        patch_server_client.insert.return_value = [{"id": "p-1", "depth": 0}]
        out = await tool("create_post")(thread_post_id="tp-1", body_markdown="hello")
        assert out["depth"] == 0
        payload = patch_server_client.insert.call_args.args[1]
        assert payload["depth"] == 0
        assert payload["parent_post_id"] is None
        assert payload["author_user_id"] == set_acting_user_fixture

    async def test_nested_post_computes_depth(
        self,
        set_acting_user_fixture: str,
        patch_server_client: AsyncMock,
        tool: Callable[[str], Callable[..., Any]],
    ) -> None:
        patch_server_client.select.side_effect = [
            [{"id": "tp-1", "thread_id": "topic-1"}],  # thread_post lookup
            [{"id": "parent", "depth": 2, "thread_post_id": "tp-1"}],  # parent
        ]
        patch_server_client.insert.return_value = [{"id": "p-2", "depth": 3}]
        await tool("create_post")(
            thread_post_id="tp-1",
            body_markdown="nested",
            parent_post_id="parent",
        )
        payload = patch_server_client.insert.call_args.args[1]
        assert payload["depth"] == 3

    async def test_parent_in_different_thread_post_raises(
        self,
        set_acting_user_fixture: str,
        patch_server_client: AsyncMock,
        tool: Callable[[str], Callable[..., Any]],
    ) -> None:
        patch_server_client.select.side_effect = [
            [{"id": "tp-1", "thread_id": "topic-1"}],
            [{"id": "parent", "depth": 0, "thread_post_id": "tp-OTHER"}],
        ]
        with pytest.raises(ValueError, match="same thread_post"):
            await tool("create_post")(
                thread_post_id="tp-1",
                body_markdown="x",
                parent_post_id="parent",
            )
        patch_server_client.insert.assert_not_called()

    async def test_missing_thread_post_raises(
        self,
        set_acting_user_fixture: str,
        patch_server_client: AsyncMock,
        tool: Callable[[str], Callable[..., Any]],
    ) -> None:
        patch_server_client.select.return_value = []
        with pytest.raises(ValueError, match="thread_post not found"):
            await tool("create_post")(thread_post_id="missing", body_markdown="x")

    async def test_missing_parent_raises(
        self,
        set_acting_user_fixture: str,
        patch_server_client: AsyncMock,
        tool: Callable[[str], Callable[..., Any]],
    ) -> None:
        patch_server_client.select.side_effect = [
            [{"id": "tp-1", "thread_id": "topic-1"}],  # thread_post exists
            [],  # parent missing
        ]
        with pytest.raises(ValueError, match="parent post not found"):
            await tool("create_post")(
                thread_post_id="tp-1",
                body_markdown="x",
                parent_post_id="nope",
            )


# ---------------------------------------------------------------------------
# Write tools: react_to
# ---------------------------------------------------------------------------


class TestReactTo:
    async def test_creates_when_no_existing_reaction(
        self,
        set_acting_user_fixture: str,
        patch_server_client: AsyncMock,
        tool: Callable[[str], Callable[..., Any]],
    ) -> None:
        patch_server_client.select.return_value = []
        patch_server_client.insert.return_value = [{"id": "r-1", "reaction_type": "upvote"}]
        out = await tool("react_to")(
            target_type="thread_post",
            target_id="tp-1",
            reaction_type="upvote",
        )
        assert out["action"] == "created"
        payload = patch_server_client.insert.call_args.args[1]
        assert payload["user_id"] == set_acting_user_fixture
        patch_server_client.update.assert_not_called()

    async def test_updates_when_reaction_exists(
        self,
        set_acting_user_fixture: str,
        patch_server_client: AsyncMock,
        tool: Callable[[str], Callable[..., Any]],
    ) -> None:
        patch_server_client.select.return_value = [{"id": "r-1", "reaction_type": "upvote"}]
        patch_server_client.update.return_value = [{"id": "r-1", "reaction_type": "downvote"}]
        out = await tool("react_to")(
            target_type="comment",
            target_id="c-1",
            reaction_type="downvote",
        )
        assert out["action"] == "updated"
        patch_server_client.insert.assert_not_called()
        # Update should target the existing reaction id
        _, kwargs = _last_call(patch_server_client.update)
        assert kwargs["filters"] == {"id": "eq.r-1"}


# ---------------------------------------------------------------------------
# Write tools: upsert_profile, upsert_political_profile, declare_vote
# ---------------------------------------------------------------------------


class TestUpsertProfile:
    async def test_only_user_id(
        self,
        patch_server_client: AsyncMock,
        tool: Callable[[str], Callable[..., Any]],
    ) -> None:
        patch_server_client.upsert.return_value = [{"user_id": "u1"}]
        out = await tool("upsert_profile")(user_id="u1")
        assert out == {"user_id": "u1"}
        payload = patch_server_client.upsert.call_args.args[1]
        assert payload == {"user_id": "u1"}

    async def test_all_fields(
        self,
        patch_server_client: AsyncMock,
        tool: Callable[[str], Callable[..., Any]],
    ) -> None:
        patch_server_client.upsert.return_value = [{"user_id": "u1"}]
        await tool("upsert_profile")(
            user_id="u1",
            display_name="Alice",
            bio="Bio",
            username="alice",
            avatar_url="https://example.com/a.png",
        )
        payload = patch_server_client.upsert.call_args.args[1]
        assert payload == {
            "user_id": "u1",
            "display_name": "Alice",
            "bio": "Bio",
            "username": "alice",
            "avatar_url": "https://example.com/a.png",
        }
        assert patch_server_client.upsert.call_args.kwargs["on_conflict"] == "user_id"


class TestUpsertPoliticalProfile:
    async def test_only_user_id(
        self,
        patch_server_client: AsyncMock,
        tool: Callable[[str], Callable[..., Any]],
    ) -> None:
        patch_server_client.upsert.return_value = [{"user_id": "u1"}]
        await tool("upsert_political_profile")(user_id="u1")
        payload = patch_server_client.upsert.call_args.args[1]
        assert payload == {"user_id": "u1"}

    async def test_all_fields(
        self,
        patch_server_client: AsyncMock,
        tool: Callable[[str], Callable[..., Any]],
    ) -> None:
        patch_server_client.upsert.return_value = [{"user_id": "u1"}]
        await tool("upsert_political_profile")(
            user_id="u1",
            declared_partisan_term_id="pt1",
            declared_ideology_term_id="it1",
            political_interest_level=4,
            notes_private="Some notes",
        )
        payload = patch_server_client.upsert.call_args.args[1]
        assert payload["political_interest_level"] == 4
        assert payload["notes_private"] == "Some notes"


class TestDeclareVote:
    async def test_default_choice_kind_vote(
        self,
        patch_server_client: AsyncMock,
        tool: Callable[[str], Callable[..., Any]],
    ) -> None:
        patch_server_client.insert.return_value = [{"id": "vh-1"}]
        await tool("declare_vote")(
            user_id="u1",
            election_id="e1",
            election_result_id="er1",
            confidence=5,
        )
        payload = patch_server_client.insert.call_args.args[1]
        assert payload["choice_kind"] == "vote"
        assert payload["election_result_id"] == "er1"
        assert payload["confidence"] == 5

    async def test_abstention_without_result_id(
        self,
        patch_server_client: AsyncMock,
        tool: Callable[[str], Callable[..., Any]],
    ) -> None:
        patch_server_client.insert.return_value = [{"id": "vh-2"}]
        await tool("declare_vote")(
            user_id="u1",
            election_id="e1",
            choice_kind="abstention",
        )
        payload = patch_server_client.insert.call_args.args[1]
        assert payload["choice_kind"] == "abstention"
        assert "election_result_id" not in payload
