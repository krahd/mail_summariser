# CLAUDE.md

Claude Code instructions for this repository.

The durable source of truth for all AI coding agents in this project is [AGENTS.md](AGENTS.md). Read it before making changes. The rules, communication style, work loop, project map, safety invariants, `STATUS.md` upkeep requirements, validation commands, and final-response requirements defined there apply to Claude Code without exception.

## Quick reference

- Read [AGENTS.md](AGENTS.md) and [STATUS.md](STATUS.md) before editing.
- Keep [STATUS.md](STATUS.md) accurate; update both `Last updated:` lines together (24-hour `America/Montevideo` time unless otherwise specified).
- Never commit `dist/`, `release_artifacts/`, `*.egg-info/`, `__pycache__/`, `.pytest_cache/`, `.DS_Store`, mail data, secrets, or local SQLite databases.
- Use British English in prose docs. Terse, factual, technical updates only — no decorative progress phrases.
- Preserve secret-masking semantics in settings routes; `__MASKED__` writes must not overwrite stored secrets.
- Dev fake-mail endpoints stay gated by `MAIL_SUMMARISER_ENABLE_DEV_TOOLS`.

## Standard validation

```bash
pytest -q
./scripts/validate_full_stack.sh
python scripts/validate_full_stack.py
./scripts/check_repo_hygiene.sh
```

Run the narrowest relevant check first. Do not claim tests passed unless they were actually run.

## When this file and AGENTS.md disagree

[AGENTS.md](AGENTS.md) wins. Update it there and, if necessary, refresh the quick reference above.
