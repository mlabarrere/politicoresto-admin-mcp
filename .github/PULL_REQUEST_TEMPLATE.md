<!-- Title uses Conventional Commits: feat: | fix: | chore: | docs: | test: | ci: | refactor: -->

## Summary

<!-- What does this PR do, in 1–3 bullets? -->

## Why

<!-- Link to the issue this closes (Closes #123) or explain the motivation. -->

## Checklist

- [ ] Title follows [Conventional Commits](https://www.conventionalcommits.org/).
- [ ] `ruff check .` passes.
- [ ] `ruff format --check .` passes.
- [ ] `mypy` passes.
- [ ] `pytest --cov --cov-fail-under=85` passes.
- [ ] `bandit -r src -c pyproject.toml` passes (or finding is documented).
- [ ] New/changed tools have tests and updated docs (README, SKILL.md, CHANGELOG).
- [ ] No `SUPABASE_SERVICE_ROLE_KEY` or other secret sneaks in.

## Notes for the reviewer
