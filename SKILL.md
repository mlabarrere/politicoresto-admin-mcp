---
name: politicoresto-admin-mcp
description: MCP tools for driving the PoliticoResto Supabase backend in admin mode. Use this skill when the user asks to create, update, or list topics, posts, comments, reactions, user profiles, vote history, or political positioning on their platform. Never use it against the production project without explicit confirmation.
---

# PoliticoResto admin MCP — usage guide

## Context

This MCP server exposes PoliticoResto's Supabase backend in admin mode
(`service_role`, RLS bypassed). It is used to seed staging, test flows, and
explore data from Claude Desktop.

**Default target:** staging (`nvwpvckjsvicsyzpzjfi`).

**Never run against production** unless the user has set
`POLITICORESTO_ALLOW_PROD=yes_i_know` and explicitly asked for it.

## Data model (cheat sheet)

- `topic` — durable discussion unit (`slug`, `title`, `topic_status`, `visibility`)
- `thread_post` — post published inside a topic (`type`: `article` / `poll` / `market`)
- `post` — comment or nested reply on a `thread_post`, with `depth` and optional `parent_post_id`
- `app_profile` — public profile (`username`, `display_name`, `bio`)
- `user_private_political_profile` — private political positioning (partisan, ideology, interest level)
- `profile_vote_history` — declared votes (with `confidence` and `choice_kind`)
- `election` + `election_result` — electoral reference data
- `reaction` — polymorphic upvote/downvote on `thread_post` or `comment`

**Critical invariant:** a publicly visible topic must carry an initial
`thread_post`. The `create_topic_with_initial_post` tool guarantees this
atomically.

## The acting-user pattern

Every write tool needs an "acting user" (the author of the new row). Rather
than passing `acting_user_id` to every call, the server keeps it as session
state:

1. Call `list_profiles` to see which users exist.
2. Call `set_acting_user(user_id=...)` to fix the identity.
3. Every subsequent write uses that user until `set_acting_user` is called
   again.

To simulate a conversation between multiple accounts, switch `set_acting_user`
between actions.

## Available tools

### Session state

- `set_acting_user(user_id)` — set the identity used by subsequent writes.
- `get_acting_user()` — inspect the currently-set acting user.

### Reads

- `list_topics(status=None, visibility=None, limit=20, offset=0)` — paginated listing with optional filters.
- `get_topic(topic_id_or_slug)` — a topic plus its `thread_post`s and their comments.
- `list_profiles(limit=50, offset=0)` — public profiles.
- `list_vote_history(user_id)` — declared vote history, enriched with election details.

### Writes — content

- `create_topic_with_initial_post(slug, title, thread_post_content, ...)` — atomic topic + first post.
- `create_post(thread_post_id, body_markdown, parent_post_id=None, ...)` — root comment or nested reply.
- `react_to(target_type, target_id, reaction_type)` — upvote/downvote a `thread_post` or `comment`.

### Writes — profiles

- `upsert_profile(user_id, display_name=?, bio=?, username=?, avatar_url=?)` — public profile.
- `upsert_political_profile(user_id, declared_partisan_term_id=?, declared_ideology_term_id=?, political_interest_level=?, notes_private=?)` — private political positioning.
- `declare_vote(user_id, election_id, choice_kind, election_result_id=?, confidence=?, notes=?)` — append a `profile_vote_history` row.

## Good practices

1. **Read before writing.** Call `list_profiles` before `set_acting_user`,
   `list_topics` before `create_topic_with_initial_post`, and so on. Don't
   fabricate UUIDs.
2. **Respect invariants.** Don't insert into `topic` directly — always go
   through `create_topic_with_initial_post` so the initial `thread_post`
   exists.
3. **Slugs.** `slug` is `citext` (case-insensitive) and must be URL-safe.
   Prefer short kebab-case values.
4. **Admin means admin.** RLS is bypassed. You can create inconsistent data
   if you're careless. Use this against staging only — never dump demo data
   into production.
5. **Use returned IDs.** Every read tool returns IDs — feed those into the
   next call rather than constructing UUIDs.

## When NOT to use this MCP

- The user is discussing their live production app — stop, confirm before
  any write, and prefer staging.
- The task has nothing to do with the PoliticoResto backend — stop.
- The user asks to delete or mutate production data for testing — stop,
  offer to do it against staging instead.
