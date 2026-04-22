"""PoliticoResto MCP server — admin / staging mode.

Exposes 12 tools for driving the Supabase backend from Claude Desktop.

Every tool uses the service_role key and therefore bypasses Row-Level Security.
This server is not intended to be exposed publicly.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .config import Settings, load_settings
from .session import get_state, require_acting_user
from .supabase_client import SupabaseClient, SupabaseError

# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

settings: Settings = load_settings()
client: SupabaseClient = SupabaseClient(settings)


def _environment_label(s: Settings) -> str:
    if s.is_staging:
        return "STAGING"
    if s.is_prod:
        return "PROD (!!)"
    return "other"


mcp: FastMCP = FastMCP(
    name="politicoresto",
    instructions=(
        f"PoliticoResto admin MCP. Target: {settings.project_ref} "
        f"({_environment_label(settings)}). "
        "Always call list_profiles then set_acting_user before any write."
    ),
)


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------


@mcp.tool()
async def set_acting_user(user_id: str) -> dict[str, Any]:
    """Set the acting user for subsequent write operations.

    Every write tool (create_topic_with_initial_post, create_post, react_to,
    declare_vote, ...) will use this user_id as the author/creator until
    set_acting_user is called again.

    Args:
        user_id: UUID of an existing app_profile. Use list_profiles to find one.

    Returns:
        The full profile of the now-acting user, for confirmation.
    """
    rows = await client.select(
        "app_profile",
        filters={"user_id": f"eq.{user_id}"},
        limit=1,
    )
    if not rows:
        raise ValueError(
            f"No app_profile found with user_id={user_id}. Use list_profiles to see valid user_ids."
        )
    get_state().acting_user_id = user_id
    label = rows[0].get("username") or user_id
    return {"acting_user": rows[0], "message": f"Acting user set to {label}"}


@mcp.tool()
async def get_acting_user() -> dict[str, Any]:
    """Return the user currently set as the acting user for writes."""
    state = get_state()
    if state.acting_user_id is None:
        return {"acting_user_id": None, "message": "No acting user is set"}
    rows = await client.select(
        "app_profile",
        filters={"user_id": f"eq.{state.acting_user_id}"},
        limit=1,
    )
    return {
        "acting_user": rows[0] if rows else None,
        "acting_user_id": state.acting_user_id,
    }


# ---------------------------------------------------------------------------
# Reads — profiles
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_profiles(
    limit: Annotated[int, Field(ge=1, le=200)] = 50,
    offset: Annotated[int, Field(ge=0)] = 0,
) -> list[dict[str, Any]]:
    """List app_profiles (public).

    Useful for discovering user_ids to pass to set_acting_user.
    """
    return await client.select(
        "app_profile",
        columns="user_id,username,display_name,bio,profile_status,created_at",
        order="created_at.desc",
        limit=limit,
        offset=offset,
    )


# ---------------------------------------------------------------------------
# Reads — topics & posts
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_topics(
    status: Literal["draft", "open", "locked", "resolved", "archived", "removed"] | None = None,
    visibility: Literal["public", "authenticated", "private", "moderators_only"] | None = None,
    limit: Annotated[int, Field(ge=1, le=100)] = 20,
    offset: Annotated[int, Field(ge=0)] = 0,
) -> list[dict[str, Any]]:
    """List topics with optional filters on status and visibility."""
    filters: dict[str, str] = {}
    if status:
        filters["topic_status"] = f"eq.{status}"
    if visibility:
        filters["visibility"] = f"eq.{visibility}"
    return await client.select(
        "topic",
        columns=(
            "id,slug,title,description,topic_status,visibility,thread_kind,created_by,created_at"
        ),
        filters=filters,
        order="created_at.desc",
        limit=limit,
        offset=offset,
    )


@mcp.tool()
async def get_topic(topic_id_or_slug: str) -> dict[str, Any]:
    """Return a topic with its thread_posts and their comments.

    Accepts either a UUID or a slug.
    """
    is_uuid = len(topic_id_or_slug) == 36 and topic_id_or_slug.count("-") == 4
    filter_key = "id" if is_uuid else "slug"

    topics = await client.select(
        "topic",
        filters={filter_key: f"eq.{topic_id_or_slug}"},
        limit=1,
    )
    if not topics:
        raise ValueError(f"Topic not found: {topic_id_or_slug}")
    topic = topics[0]

    thread_posts = await client.select(
        "thread_post",
        filters={"thread_id": f"eq.{topic['id']}"},
        order="created_at.asc",
    )

    for tp in thread_posts:
        tp["comments"] = await client.select(
            "post",
            filters={"thread_post_id": f"eq.{tp['id']}"},
            order="created_at.asc",
        )

    return {"topic": topic, "thread_posts": thread_posts}


# ---------------------------------------------------------------------------
# Reads — vote history
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_vote_history(user_id: str) -> list[dict[str, Any]]:
    """Return a user's declared vote history, enriched with election details."""
    history = await client.select(
        "profile_vote_history",
        filters={"user_id": f"eq.{user_id}"},
        order="declared_at.desc",
    )
    if history:
        election_ids = sorted({h["election_id"] for h in history})
        elections = await client.select(
            "election",
            filters={"id": f"in.({','.join(election_ids)})"},
        )
        elections_by_id = {e["id"]: e for e in elections}
        for h in history:
            h["election"] = elections_by_id.get(h["election_id"])
    return history


# ---------------------------------------------------------------------------
# Writes — topics & posts
# ---------------------------------------------------------------------------


@mcp.tool()
async def create_topic_with_initial_post(
    slug: str,
    title: str,
    thread_post_content: str,
    description: str | None = None,
    thread_post_title: str | None = None,
    thread_post_type: Literal["article", "poll", "market"] = "article",
    visibility: Literal["public", "authenticated", "private", "moderators_only"] = "public",
    topic_status: Literal["draft", "open"] = "open",
) -> dict[str, Any]:
    """Create a topic and its initial thread_post atomically.

    Preserves the business invariant that a publicly visible topic must carry
    an initial post. On thread_post failure the newly created topic is
    rolled back.

    Uses the acting user as ``created_by``.
    """
    acting = require_acting_user()

    topic_rows = await client.insert(
        "topic",
        {
            "slug": slug,
            "title": title,
            "description": description,
            "topic_status": topic_status,
            "visibility": visibility,
            "created_by": acting,
        },
    )
    topic = topic_rows[0]

    try:
        tp_rows = await client.insert(
            "thread_post",
            {
                "thread_id": topic["id"],
                "type": thread_post_type,
                "title": thread_post_title,
                "content": thread_post_content,
                "created_by": acting,
                "status": "published",
            },
        )
    except SupabaseError:
        # Roll back the orphan topic to preserve the invariant.
        await client.delete("topic", filters={"id": f"eq.{topic['id']}"})
        raise

    return {"topic": topic, "thread_post": tp_rows[0]}


@mcp.tool()
async def create_post(
    thread_post_id: str,
    body_markdown: str,
    parent_post_id: str | None = None,
    title: str | None = None,
    post_type: Literal[
        "news",
        "analysis",
        "discussion",
        "local",
        "moderation",
        "resolution_justification",
    ] = "discussion",
) -> dict[str, Any]:
    """Create a comment (or nested reply when parent_post_id is given).

    When parent_post_id is provided, depth = parent.depth + 1; otherwise
    depth = 0 (root comment). The parent must belong to the same thread_post.
    """
    acting = require_acting_user()

    tp = await client.select(
        "thread_post",
        columns="id,thread_id",
        filters={"id": f"eq.{thread_post_id}"},
        limit=1,
    )
    if not tp:
        raise ValueError(f"thread_post not found: {thread_post_id}")
    topic_id = tp[0]["thread_id"]

    depth = 0
    if parent_post_id:
        parent = await client.select(
            "post",
            columns="id,depth,thread_post_id",
            filters={"id": f"eq.{parent_post_id}"},
            limit=1,
        )
        if not parent:
            raise ValueError(f"parent post not found: {parent_post_id}")
        if parent[0]["thread_post_id"] != thread_post_id:
            raise ValueError("parent_post_id must belong to the same thread_post")
        depth = (parent[0]["depth"] or 0) + 1

    rows = await client.insert(
        "post",
        {
            "thread_post_id": thread_post_id,
            "topic_id": topic_id,
            "parent_post_id": parent_post_id,
            "author_user_id": acting,
            "post_type": post_type,
            "title": title,
            "body_markdown": body_markdown,
            "depth": depth,
        },
    )
    return rows[0]


@mcp.tool()
async def react_to(
    target_type: Literal["thread_post", "comment"],
    target_id: str,
    reaction_type: Literal["upvote", "downvote"],
) -> dict[str, Any]:
    """Record an upvote/downvote on a thread_post or comment.

    If the acting user has already reacted to this target, the reaction is
    updated rather than duplicated.
    """
    acting = require_acting_user()

    existing = await client.select(
        "reaction",
        filters={
            "target_type": f"eq.{target_type}",
            "target_id": f"eq.{target_id}",
            "user_id": f"eq.{acting}",
        },
        limit=1,
    )

    if existing:
        rows = await client.update(
            "reaction",
            {"reaction_type": reaction_type},
            filters={"id": f"eq.{existing[0]['id']}"},
        )
        return {"action": "updated", "reaction": rows[0]}

    rows = await client.insert(
        "reaction",
        {
            "target_type": target_type,
            "target_id": target_id,
            "user_id": acting,
            "reaction_type": reaction_type,
        },
    )
    return {"action": "created", "reaction": rows[0]}


# ---------------------------------------------------------------------------
# Writes — profiles
# ---------------------------------------------------------------------------


@mcp.tool()
async def upsert_profile(
    user_id: str,
    display_name: str | None = None,
    bio: str | None = None,
    username: str | None = None,
    avatar_url: str | None = None,
) -> dict[str, Any]:
    """Create or update an app_profile row.

    Note: user_id must already exist in ``auth.users`` (created via Supabase
    Auth). This tool does not create auth accounts; it only manages the
    associated public profile.
    """
    payload: dict[str, Any] = {"user_id": user_id}
    if display_name is not None:
        payload["display_name"] = display_name
    if bio is not None:
        payload["bio"] = bio
    if username is not None:
        payload["username"] = username
    if avatar_url is not None:
        payload["avatar_url"] = avatar_url

    rows = await client.upsert("app_profile", payload, on_conflict="user_id")
    return rows[0]


@mcp.tool()
async def upsert_political_profile(
    user_id: str,
    declared_partisan_term_id: str | None = None,
    declared_ideology_term_id: str | None = None,
    political_interest_level: Annotated[int | None, Field(ge=1, le=5)] = None,
    notes_private: str | None = None,
) -> dict[str, Any]:
    """Create or update the private political profile for a user."""
    payload: dict[str, Any] = {"user_id": user_id}
    if declared_partisan_term_id is not None:
        payload["declared_partisan_term_id"] = declared_partisan_term_id
    if declared_ideology_term_id is not None:
        payload["declared_ideology_term_id"] = declared_ideology_term_id
    if political_interest_level is not None:
        payload["political_interest_level"] = political_interest_level
    if notes_private is not None:
        payload["notes_private"] = notes_private

    rows = await client.upsert("user_private_political_profile", payload, on_conflict="user_id")
    return rows[0]


@mcp.tool()
async def declare_vote(
    user_id: str,
    election_id: str,
    choice_kind: Literal[
        "vote", "blanc", "nul", "abstention", "non_inscrit", "ne_se_prononce_pas"
    ] = "vote",
    election_result_id: str | None = None,
    confidence: Annotated[int | None, Field(ge=1, le=5)] = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Append a row to profile_vote_history.

    When choice_kind is ``vote``, election_result_id should be provided — it
    identifies the list or candidate the user declares they chose.
    """
    payload: dict[str, Any] = {
        "user_id": user_id,
        "election_id": election_id,
        "choice_kind": choice_kind,
    }
    if election_result_id is not None:
        payload["election_result_id"] = election_result_id
    if confidence is not None:
        payload["confidence"] = confidence
    if notes is not None:
        payload["notes"] = notes

    rows = await client.insert("profile_vote_history", payload)
    return rows[0]
