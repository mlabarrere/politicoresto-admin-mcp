# Contributing

Thanks for taking the time to look at `politicoresto-admin-mcp`. This is a
small, single-purpose tool, so most contributions will be bug fixes,
documentation polish, or additional tools that stay inside the
"admin / staging" scope (see [README](README.md#what-this-is-and-what-it-is-not)).

## Dev setup

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate

pip install -e ".[dev]"
pre-commit install
```

Copy `.env.example` to `.env` and fill `SUPABASE_SERVICE_ROLE_KEY` with a
staging key. Without it, most tools will still fail at the first HTTP call;
configure it once and the rest is hermetic.

## Running the quality gates

```bash
ruff check .
ruff format --check .
mypy
bandit -r src -c pyproject.toml
pytest --cov=politicoresto_mcp --cov-report=term-missing --cov-fail-under=85
```

All five must pass before CI will let the PR merge. `pre-commit run --all-files`
runs the first four in one shot.

## Testing

- Tests run against an `httpx` mock via [`respx`](https://github.com/lundberg/respx)
  or against an in-memory `AsyncMock` client. **Never add a test that hits a
  real Supabase project by default.** Mark such tests `@pytest.mark.integration`
  — they are skipped by default and only run when you explicitly pass
  `-m integration`.
- Aim for ≥ 85 % coverage on `src/politicoresto_mcp`. New tools should have
  at least one happy-path test and one failure-path test.
- Tests must be deterministic. If you seed timestamps or randomness, pass the
  seed through a fixture.

## Style

- **Python 3.11+** syntax (`str | None`, `list[dict[...]]`).
- Type-annotate all public functions. Mypy is strict.
- Docstrings in US English, Google style.
- Keep comments sparse: if the *why* isn't obvious, add one short line.
  The *what* should already be readable from the code.
- Prefer editing existing files to creating new ones. One FastMCP server file
  is fine until it visibly hurts.

## Commit messages

We use [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` for a new tool, argument, or capability.
- `fix:` for a bug fix.
- `chore:`, `docs:`, `test:`, `ci:`, `refactor:`, `build:` as appropriate.

Keep commits small and focused — one logical change each. Rebase or squash
before opening the PR.

## Public-API changes

The public API is the 12 tool signatures. Any breaking change (renamed
argument, removed tool, changed return shape) must:

1. Show up in the PR title as a `feat!:` / `fix!:` (or with `BREAKING CHANGE:`
   in the body).
2. Bump the minor version (we are pre-1.0; breaking changes are permitted
   but should still be flagged).
3. Be described in `CHANGELOG.md` under the matching version.

## Scope — when to say "no"

If your change requires:
- Exposing the server over HTTP or to end users,
- Managing user tokens / OAuth flows,
- Handling multi-tenant writes with active RLS,

it does not belong in this repo. Please open a fresh project — the boundary
is intentional and keeping it clean is what lets this one stay safe.
