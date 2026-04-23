# Changelog

All notable changes to `politicoresto-admin-mcp` are documented in this file.

The format is based on [Keep a Changelog 1.1.0][kac], and this project adheres
to [Semantic Versioning][semver].

[kac]: https://keepachangelog.com/en/1.1.0/
[semver]: https://semver.org/spec/v2.0.0.html

## [Unreleased]

### Planned

- 0.2.0 — soft-delete + update tools on existing tables; Auth Admin client
  (create/delete auth users; one-shot `create_persona` tool).
- 0.3.0 — polls, topic resolution, elections, taxonomy, editorial content.
- Later — `call_rpc(function_name, args)` escape hatch for `SECURITY DEFINER`
  functions.

## [0.1.0] - 2026-04-23

First public release. The server is a local, stdio-only admin tool for the
PoliticoResto Supabase backend. It ships twelve tools grouped into session,
read, and write categories.

### Added

- **Twelve MCP tools:**
  - Session: `set_acting_user`, `get_acting_user`.
  - Reads: `list_profiles`, `list_topics`, `get_topic`, `list_vote_history`.
  - Writes: `create_topic_with_initial_post`, `create_post`, `react_to`,
    `upsert_profile`, `upsert_political_profile`, `declare_vote`.
- **Production guardrail.** The server refuses to start when
  `SUPABASE_PROJECT_URL` points to the production project ref
  (`gzdpisxkavpyfmhsktcg`) unless `POLITICORESTO_ALLOW_PROD=yes_i_know`.
- **Atomic topic creation.** `create_topic_with_initial_post` rolls back the
  newly created `topic` row if the matching `thread_post` insert fails, so
  the public invariant "a visible topic has an initial post" holds.
- **Acting-user session state.** Write tools use a process-wide acting user
  set once via `set_acting_user`; no need to pass `acting_user_id` to every
  call.
- **PostgREST client** (`SupabaseClient`) implementing `select`, `insert`,
  `update` (requires filters), `upsert`, `delete` (requires filters), and
  `rpc`. 4xx/5xx responses surface as `SupabaseError` with the decoded
  detail.
- **Developer tooling:** Ruff (lint + format), Mypy strict, Bandit, Pytest
  + pytest-asyncio + pytest-cov + respx, pre-commit (including a local hook
  that blocks committed `SUPABASE_SERVICE_ROLE_KEY` values).
- **Tests.** 65 pytest tests, 96.9% line coverage on `src/politicoresto_mcp`.
  Integration tests are marked and skipped by default.
- **CI/CD.** GitHub Actions workflow running ruff, ruff format, mypy, bandit,
  and pytest across Python 3.11 and 3.12. Release workflow builds sdist +
  wheel and publishes to PyPI via OIDC Trusted Publishing on `v*` tags.
  Dependabot keeps pip and GitHub Actions dependencies current.
- **Documentation.** `README.md` (quickstart, configuration, tool reference,
  troubleshooting), `SKILL.md` (Claude-facing usage guide), `CONTRIBUTING.md`,
  `CODE_OF_CONDUCT.md`, `SECURITY.md` (threat model + rotation playbook),
  issue and pull-request templates.
- **Package hygiene.** `py.typed` marker, PEP 621 metadata with authors /
  URLs / classifiers / keywords, MIT license.

### Security

- **Service-role key threat model** documented in `SECURITY.md`, including the
  rotation procedure for a leaked key.
- **Pre-commit secret guard** rejects any staged file that assigns a
  non-placeholder value to `SUPABASE_SERVICE_ROLE_KEY`.
- **CI workflow** uses `permissions: contents: read` by default; third-party
  actions are pinned to commit SHAs; the publish job opts into `id-token: write`
  only for the OIDC handshake with PyPI.
