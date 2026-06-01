# mail_summariser implementation prompt set

These files are intended to be used one phase at a time with a coding model. The model should be treated as simple: each phase gives explicit scope, file targets, tests, and things not to do.

Repository: `krahd/mail_summariser`
Branch recommendation: create a fresh branch before each phase, or one long branch with one commit per phase.

General non-negotiable rules for every phase:

1. Inspect the repository before editing.
2. Preserve existing behaviour unless the phase explicitly changes it.
3. Do not remove tests to make the suite pass.
4. Add or update tests for every behavioural change.
5. Keep sample mailbox / `dummyMode` behaviour working.
6. Keep secret masking semantics intact.
7. Keep fake-mail dev tooling gated.
8. Run the specified validation commands.
9. Update `STATUS.md` with concise notes about what changed and what was verified.
10. Stop after the current phase. Do not implement later phases early.


# 00 — Master plan and operating instructions

## Purpose

This is the orchestration prompt for the complete `mail_summariser` evolution from a single-inbox summariser into a local-first multi-mailbox triage system that can reproduce useful MailMate-like views via IMAP.

Read this file first. Then read only the current phase file that the user gives you. Use later phase titles only as roadmap context. Do not implement later phases.

## User goal

The user has a MailMate setup with multiple accounts, many MailMate smart mailboxes, thousands of unread or flagged messages, list mail such as `List_Fing`, and a need to regain control of email.

The target system should eventually:

- connect to mailboxes through IMAP, not MailMate internals;
- support multiple accounts;
- discover IMAP mailboxes/folders/labels;
- reproduce MailMate-like smart scopes such as “Unread or Flagged all” and “Unread or Flagged, Lists_Fing”;
- avoid fetching every full message body on every summary;
- keep a local incremental index;
- produce useful triage summaries and action recommendations;
- default to safe, read-only behaviour unless the user explicitly applies actions.

## Existing architecture to preserve

The repo currently has:

- `backend/` — FastAPI backend, mail services, settings, persistence, model providers.
- `webapp/` — static browser UI.
- `macos-app/` — SwiftUI desktop client.
- `tests/` — pytest suite.
- `scripts/` — validation, build, release, hygiene.
- `STATUS.md` — status and implementation notes.

The app already supports:

- sample mailbox mode exposed to users as “Sample Mailbox”;
- backend API field `dummyMode`;
- live IMAP/SMTP mode;
- provider-backed summaries through Ollama/OpenAI/Anthropic;
- deterministic fallback summaries;
- SQLite persistence;
- logs and undo;
- rendered UI validation.

## Global implementation constraints

### Preserve `dummyMode`

The backend setting name `dummyMode` must remain compatible. End-user UI should continue to call it “Sample Mailbox”. Do not rename API fields unless backwards-compatible aliases are provided.

### Preserve secret handling

Settings reads must mask secrets. Writes using masked sentinel values must not overwrite stored secrets. Provider and mail errors must not expose passwords or API keys.

### Preserve fake-mail gating

Developer fake-mail endpoints must remain disabled unless `MAIL_SUMMARISER_ENABLE_DEV_TOOLS` is explicitly enabled.

### Avoid destructive mailbox operations by default

All new real-mail actions must either be read-only or dry-run by default. Any action that marks, flags, moves, archives, deletes, or tags real mail must have explicit confirmation and tests.

### Keep interfaces narrow

Prefer adding small service functions and route modules rather than large rewrites. Do not collapse the existing router decomposition.

### Tests first when possible

For every phase:

1. Add or update tests that describe the intended behaviour.
2. Implement the minimum change to pass those tests.
3. Run targeted tests.
4. Run broad tests.
5. Update `STATUS.md`.

## Standard workflow for each phase

When the user gives you one phase file, perform this workflow:

1. Read `STATUS.md`, `README.md`, relevant backend files, relevant webapp files, and relevant tests.
2. Produce a brief implementation plan before editing.
3. Implement only the requested phase.
4. Add tests.
5. Run the required validation commands.
6. Fix failures.
7. Update `STATUS.md`.
8. Report:
   - files changed;
   - behaviours added;
   - tests run;
   - any risks or incomplete items.

## Standard validation commands

Use these unless a phase gives narrower or additional commands:

```bash
pytest -q
./scripts/check_repo_hygiene.sh
git diff --check
```

If UI changes were made:

```bash
python -m playwright install chromium
python scripts/validate_rendered_ui.py
```

If startup or packaging-relevant behaviour changed:

```bash
./scripts/validate_full_stack.sh
python scripts/validate_full_stack.py
```

## Phase sequence

1. `01-live-imap-hardening.md`
2. `02-multi-account-settings.md`
3. `03-mailbox-discovery.md`
4. `04-server-side-search.md`
5. `05-local-index.md`
6. `06-saved-scopes-mailmate.md`
7. `07-triage-dashboard.md`
8. `08-actions-and-dry-run.md`
9. `09-summary-analytics.md`
10. `10-polish-docs-release.md`

## Important instruction to the coding model

Do not “improve” adjacent areas unless necessary to complete the phase. If you discover a problem outside the phase scope, write it under `STATUS.md` as a future task, but do not implement it.

