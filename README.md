# politicoresto-admin-mcp

[![CI](https://github.com/mlabarrere/politicoresto-admin-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/mlabarrere/politicoresto-admin-mcp/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Code style: Ruff](https://img.shields.io/badge/lint%20%2B%20format-ruff-261230)](https://github.com/astral-sh/ruff)
[![Checked with mypy --strict](https://img.shields.io/badge/mypy-strict-2a6db2.svg)](http://mypy-lang.org/)

An [MCP](https://modelcontextprotocol.io/) server that exposes CRUD operations
on the [PoliticoResto](https://github.com/mlabarrere/politicoresto) Supabase
backend to Claude Desktop. Built in Python on top of
[FastMCP](https://github.com/modelcontextprotocol/python-sdk), runs locally
over stdio, authenticates with a Supabase `service_role` key that bypasses RLS.

It exists so I can seed the staging database, test flows end-to-end, and
explore data conversationally from Claude Desktop without building a throwaway
admin UI.

---

## What this is — and what it is not

**This is:**
- A **local, single-user admin tool**.
- Launched by Claude Desktop over **stdio** — never exposed to the network.
- Authenticated with the Supabase `service_role` key, which **bypasses
  Row-Level Security** on every request.

**This is not:**
- A public-facing server.
- A backend for end users.
- Safe to run over HTTP — the `service_role` key grants full read/write on
  every table.

If PoliticoResto ever needs end-user MCP access, that will be a **separate
server** with OAuth, user JWTs, and active RLS. This repository stays the
developer tool.

---

## Quickstart

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate

pip install -e .

cp .env.example .env
# Fill SUPABASE_SERVICE_ROLE_KEY with your staging key.

python -m politicoresto_mcp   # starts the stdio server
```

To iterate without Claude Desktop, use the official MCP inspector:

```bash
npx @modelcontextprotocol/inspector python -m politicoresto_mcp
```

---

## What you need to provide

You need **two pairs of credentials** — one per Supabase project. By default
you should only use the staging pair; the server refuses to start against
production unless you explicitly opt in.

### Staging (default)

Open the staging Supabase dashboard:
<https://supabase.com/dashboard/project/nvwpvckjsvicsyzpzjfi>

| Variable                     | Where to find it                                                                    |
| ---------------------------- | ----------------------------------------------------------------------------------- |
| `SUPABASE_PROJECT_URL`       | *Settings → API → Project URL*. `https://nvwpvckjsvicsyzpzjfi.supabase.co`.         |
| `SUPABASE_SERVICE_ROLE_KEY`  | *Settings → API → Project API keys → `service_role` secret → Reveal*. `eyJhbGciOi…`. |

Put them in `.env` (already git-ignored):

```env
SUPABASE_PROJECT_URL=https://nvwpvckjsvicsyzpzjfi.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOi...        # staging service_role
```

### Production (only when you mean it)

Open the production dashboard:
<https://supabase.com/dashboard/project/gzdpisxkavpyfmhsktcg>

Grab the same two values (they are **different** keys — production has its own
`service_role` secret) and add the explicit override:

```env
SUPABASE_PROJECT_URL=https://gzdpisxkavpyfmhsktcg.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOi...        # production service_role (distinct from staging)
POLITICORESTO_ALLOW_PROD=yes_i_know
```

Without `POLITICORESTO_ALLOW_PROD=yes_i_know`, the server refuses to start when
the URL points to the production project ref (`gzdpisxkavpyfmhsktcg`). That's
the guardrail.

### Switching between environments

Keep two `.env` snapshots and swap them as needed:

```bash
cp .env.staging .env   # run against staging
cp .env.prod    .env   # run against prod (requires the override flag)
```

Alternatively, configure two entries in your Claude Desktop config — one per
environment — with the variables inlined. Both will show up and you pick the
one to connect to.

### Configuration reference

| Variable                     | Required | Default                                         | Description                                                   |
| ---------------------------- | -------- | ----------------------------------------------- | ------------------------------------------------------------- |
| `SUPABASE_PROJECT_URL`       | yes      | —                                               | Supabase project URL, must end in `.supabase.co`.             |
| `SUPABASE_SERVICE_ROLE_KEY`  | yes      | —                                               | `service_role` secret for that project. Never commit it.      |
| `POLITICORESTO_ALLOW_PROD`   | no       | unset                                           | Must equal `yes_i_know` to run against the production ref.    |

---

## Wiring it into Claude Desktop

Open the config file (`~/Library/Application Support/Claude/claude_desktop_config.json`
on macOS, `%APPDATA%\Claude\claude_desktop_config.json` on Windows) and add:

```jsonc
{
  "mcpServers": {
    "politicoresto-staging": {
      "command": "/absolute/path/to/repo/.venv/bin/python",
      "args": ["-m", "politicoresto_mcp"],
      "env": {
        "SUPABASE_PROJECT_URL": "https://nvwpvckjsvicsyzpzjfi.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "eyJhbGciOi..."
      }
    }
  }
}
```

Restart Claude Desktop. You should see the **politicoresto** server with its
tools in the sidebar. Add a second entry with the prod URL + prod key +
`POLITICORESTO_ALLOW_PROD` if you need to drive production occasionally.

---

## Tool reference

The server exposes 12 tools grouped by role. See [SKILL.md](SKILL.md) for the
usage conventions Claude is expected to follow.

### Session state

| Tool                | Purpose                                                               |
| ------------------- | --------------------------------------------------------------------- |
| `set_acting_user`   | Set the user_id used by every subsequent write tool.                  |
| `get_acting_user`   | Inspect the currently-set acting user.                                |

### Reads

| Tool                | Purpose                                                                           |
| ------------------- | --------------------------------------------------------------------------------- |
| `list_profiles`     | List `app_profile` rows — useful for discovering user_ids.                        |
| `list_topics`       | List topics with optional filters on status and visibility.                       |
| `get_topic`         | Fetch a topic plus its thread_posts and the comments under each.                  |
| `list_vote_history` | Declared vote history for a user, enriched with election details.                 |

### Writes

| Tool                                | Purpose                                                                                       |
| ----------------------------------- | --------------------------------------------------------------------------------------------- |
| `create_topic_with_initial_post`    | Atomically insert a `topic` + its first `thread_post`. Rolls back the topic if the post fails. |
| `create_post`                       | Add a root comment or a nested reply; depth is computed from the parent.                      |
| `react_to`                          | Up/downvote a `thread_post` or `comment`; updates the existing row if the user already reacted. |
| `upsert_profile`                    | Create or update an `app_profile` (public display data).                                      |
| `upsert_political_profile`          | Create or update the private political positioning row.                                       |
| `declare_vote`                      | Append a `profile_vote_history` entry (with `choice_kind` and optional `confidence`).         |

All write tools require an acting user. Call `set_acting_user` first; otherwise
they raise `RuntimeError` with a clear message.

---

## Troubleshooting

**`ERROR: SUPABASE_PROJECT_URL is required`**
Your `.env` is missing or not loaded. Confirm the file is at the repo root and
that you invoked the server from that directory, or inline the variables in the
Claude Desktop config.

**`ERROR: Invalid Supabase URL: https://example.com`**
The URL must end in `.supabase.co`. Copy the exact value from *Settings → API*.

**`ERROR: Refusing to start: SUPABASE_PROJECT_URL points to production`**
The guardrail fired. Either change the URL back to the staging ref, or — if
you really intend to run against production — set
`POLITICORESTO_ALLOW_PROD=yes_i_know` and think twice.

**Tool call fails with `RuntimeError: No acting user is set`**
Call `set_acting_user(user_id=...)` before the write. Use `list_profiles` to
find a valid user_id.

**HTTP 401 / `Supabase request failed: 401`**
The `service_role` key is invalid or expired. Regenerate it in *Settings → API →
service_role → Regenerate*, update `.env`, restart the server.

**HTTP 404 on every request**
The project URL is wrong (points to a project ref that does not exist). Copy
the URL again from the dashboard.

**`pip install -e ".[dev]"` fails with a Hatch metadata error**
You likely added an author entry with a malformed email. Either provide a
valid `email = "..."` or drop the `email =` field entirely.

---

## Security

The `service_role` key grants full read/write on every table. Treat it like a
root password:

- Never commit a real value. `.env` is git-ignored; `.env.example` is a
  template with the key left blank.
- If a key is ever pasted into a log, screenshot, chat, or issue — rotate
  immediately via *Settings → API → service_role → Regenerate* on the affected
  project.
- See [SECURITY.md](SECURITY.md) for the full threat model, rotation playbook,
  and the private vulnerability disclosure channel.

---

## Contributing

PRs welcome inside the "admin / staging" scope. Start at
[CONTRIBUTING.md](CONTRIBUTING.md) for dev setup and the quality gates. The
short version:

```bash
pip install -e ".[dev]"
pre-commit install
ruff check . && ruff format --check . && mypy && bandit -r src -c pyproject.toml
pytest --cov=politicoresto_mcp --cov-fail-under=85
```

---

## License

[MIT](LICENSE). Copyright © 2026 Mickaël Labarrère.

---

## Acknowledgments

- [Model Context Protocol](https://modelcontextprotocol.io/) by Anthropic.
- [FastMCP](https://github.com/modelcontextprotocol/python-sdk) — the server
  decorator API this project builds on.
- [Supabase](https://supabase.com/) and [PostgREST](https://postgrest.org/).
