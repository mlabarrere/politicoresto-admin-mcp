"""Serveur MCP PoliticoResto — mode admin staging.

Expose ~10 tools pour piloter le backend Supabase via Claude Desktop.

Toutes les opérations utilisent la service_role key et bypassent RLS.
N'est PAS destiné à être exposé publiquement.
"""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .config import load_settings
from .session import get_state, require_acting_user
from .supabase_client import SupabaseClient, SupabaseError

# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

settings = load_settings()
client = SupabaseClient(settings)

mcp = FastMCP(
    name="politicoresto",
    instructions=(
        f"MCP admin pour PoliticoResto. Cible: {settings.project_ref} "
        f"({'STAGING' if settings.is_staging else 'PROD (!!)' if settings.is_prod else 'other'}). "
        "Commence toujours par list_profiles puis set_acting_user avant toute écriture."
    ),
)


# ---------------------------------------------------------------------------
# État session
# ---------------------------------------------------------------------------


@mcp.tool()
async def set_acting_user(user_id: str) -> dict[str, Any]:
    """Définit l'utilisateur actif pour les écritures suivantes.

    Tous les writes (create_topic, create_post, react_to, declare_vote, etc.)
    utiliseront cet user_id comme auteur/créateur jusqu'à un nouvel appel
    de set_acting_user.

    Args:
        user_id: UUID d'un app_profile existant. Utilise list_profiles pour trouver.

    Returns:
        Le profil complet de l'user activé, pour confirmation.
    """
    rows = await client.select(
        "app_profile",
        filters={"user_id": f"eq.{user_id}"},
        limit=1,
    )
    if not rows:
        raise ValueError(
            f"Aucun app_profile avec user_id={user_id}. "
            "Utilise list_profiles pour voir les user_id valides."
        )
    get_state().acting_user_id = user_id
    return {"acting_user": rows[0], "message": f"Acting user set to {rows[0].get('username') or user_id}"}


@mcp.tool()
async def get_acting_user() -> dict[str, Any]:
    """Retourne l'utilisateur actuellement actif pour les écritures."""
    state = get_state()
    if state.acting_user_id is None:
        return {"acting_user_id": None, "message": "Aucun acting user défini"}
    rows = await client.select(
        "app_profile",
        filters={"user_id": f"eq.{state.acting_user_id}"},
        limit=1,
    )
    return {"acting_user": rows[0] if rows else None, "acting_user_id": state.acting_user_id}


# ---------------------------------------------------------------------------
# Lecture — profils
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_profiles(
    limit: int = Field(default=50, ge=1, le=200),
    offset: int = Field(default=0, ge=0),
) -> list[dict[str, Any]]:
    """Liste les app_profiles (publics).

    Utile pour trouver un user_id à utiliser avec set_acting_user.
    """
    return await client.select(
        "app_profile",
        columns="user_id,username,display_name,bio,profile_status,created_at",
        order="created_at.desc",
        limit=limit,
        offset=offset,
    )


# ---------------------------------------------------------------------------
# Lecture — topics & posts
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_topics(
    status: (
        Literal["draft", "open", "locked", "resolved", "archived", "removed"] | None
    ) = None,
    visibility: (
        Literal["public", "authenticated", "private", "moderators_only"] | None
    ) = None,
    limit: int = Field(default=20, ge=1, le=100),
    offset: int = Field(default=0, ge=0),
) -> list[dict[str, Any]]:
    """Liste les topics avec filtres optionnels."""
    filters: dict[str, str] = {}
    if status:
        filters["topic_status"] = f"eq.{status}"
    if visibility:
        filters["visibility"] = f"eq.{visibility}"
    return await client.select(
        "topic",
        columns="id,slug,title,description,topic_status,visibility,thread_kind,created_by,created_at",
        filters=filters,
        order="created_at.desc",
        limit=limit,
        offset=offset,
    )


@mcp.tool()
async def get_topic(topic_id_or_slug: str) -> dict[str, Any]:
    """Retourne un topic avec ses thread_posts et commentaires.

    Accepte un UUID ou un slug.
    """
    # Heuristique simple : UUID = 36 chars avec des tirets
    is_uuid = len(topic_id_or_slug) == 36 and topic_id_or_slug.count("-") == 4
    filter_key = "id" if is_uuid else "slug"

    topics = await client.select(
        "topic",
        filters={filter_key: f"eq.{topic_id_or_slug}"},
        limit=1,
    )
    if not topics:
        raise ValueError(f"Topic introuvable: {topic_id_or_slug}")
    topic = topics[0]

    thread_posts = await client.select(
        "thread_post",
        filters={"thread_id": f"eq.{topic['id']}"},
        order="created_at.asc",
    )

    # Pour chaque thread_post, on récupère ses commentaires (posts)
    for tp in thread_posts:
        tp["comments"] = await client.select(
            "post",
            filters={"thread_post_id": f"eq.{tp['id']}"},
            order="created_at.asc",
        )

    return {"topic": topic, "thread_posts": thread_posts}


# ---------------------------------------------------------------------------
# Lecture — historique de vote
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_vote_history(user_id: str) -> list[dict[str, Any]]:
    """Historique de vote déclaré d'un utilisateur, avec détails élection."""
    history = await client.select(
        "profile_vote_history",
        filters={"user_id": f"eq.{user_id}"},
        order="declared_at.desc",
    )
    # Enrichit avec les infos d'élection
    if history:
        election_ids = list({h["election_id"] for h in history})
        elections = await client.select(
            "election",
            filters={"id": f"in.({','.join(election_ids)})"},
        )
        elections_by_id = {e["id"]: e for e in elections}
        for h in history:
            h["election"] = elections_by_id.get(h["election_id"])
    return history


# ---------------------------------------------------------------------------
# Écriture — topics & posts
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
    """Crée un topic ET son thread_post initial atomiquement.

    Garantit l'invariant métier : un topic exposé doit avoir un post initial.
    Utilise l'acting user comme created_by.
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
        # Cleanup du topic si thread_post fail, pour maintenir l'invariant
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
        "news", "analysis", "discussion", "local", "moderation", "resolution_justification"
    ] = "discussion",
) -> dict[str, Any]:
    """Crée un commentaire (ou sous-commentaire si parent_post_id est fourni).

    Si parent_post_id est fourni, depth = parent.depth + 1.
    Sinon depth = 0 (commentaire racine).
    """
    acting = require_acting_user()

    # Récupère le topic_id depuis le thread_post
    tp = await client.select(
        "thread_post",
        columns="id,thread_id",
        filters={"id": f"eq.{thread_post_id}"},
        limit=1,
    )
    if not tp:
        raise ValueError(f"thread_post introuvable: {thread_post_id}")
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
            raise ValueError(f"parent post introuvable: {parent_post_id}")
        if parent[0]["thread_post_id"] != thread_post_id:
            raise ValueError("parent_post_id doit appartenir au même thread_post")
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
    """Ajoute une réaction (upvote/downvote) sur un thread_post ou comment.

    Si l'user a déjà réagi, met à jour le reaction_type.
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
# Écriture — profils
# ---------------------------------------------------------------------------


@mcp.tool()
async def upsert_profile(
    user_id: str,
    display_name: str | None = None,
    bio: str | None = None,
    username: str | None = None,
    avatar_url: str | None = None,
) -> dict[str, Any]:
    """Crée ou met à jour un app_profile.

    Note: user_id doit exister dans auth.users (créé via Supabase Auth).
    Ce tool ne crée pas de compte auth, il crée seulement le profil associé.
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
    political_interest_level: int | None = Field(default=None, ge=1, le=5),
    notes_private: str | None = None,
) -> dict[str, Any]:
    """Crée ou met à jour le profil politique privé d'un user."""
    payload: dict[str, Any] = {"user_id": user_id}
    if declared_partisan_term_id is not None:
        payload["declared_partisan_term_id"] = declared_partisan_term_id
    if declared_ideology_term_id is not None:
        payload["declared_ideology_term_id"] = declared_ideology_term_id
    if political_interest_level is not None:
        payload["political_interest_level"] = political_interest_level
    if notes_private is not None:
        payload["notes_private"] = notes_private

    rows = await client.upsert(
        "user_private_political_profile", payload, on_conflict="user_id"
    )
    return rows[0]


@mcp.tool()
async def declare_vote(
    user_id: str,
    election_id: str,
    choice_kind: Literal[
        "vote", "blanc", "nul", "abstention", "non_inscrit", "ne_se_prononce_pas"
    ] = "vote",
    election_result_id: str | None = None,
    confidence: int | None = Field(default=None, ge=1, le=5),
    notes: str | None = None,
) -> dict[str, Any]:
    """Ajoute une ligne dans profile_vote_history.

    Pour choice_kind=vote, election_result_id devrait être renseigné
    (le candidat/liste effectivement choisi).
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
