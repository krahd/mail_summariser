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


# 10 — Polish, documentation, validation, and release readiness

## Goal

Bring the multi-account, mailbox-discovery, index, saved-scope, dashboard, safe-action, and analytics work into a coherent documented release state.

This phase is for integration polish, documentation, validation, and user-facing clarity. It should not introduce major new architecture.

## Files likely involved

- `README.md`
- `STATUS.md`
- `docs/index.html`
- `docs/site.css`
- `docs/site.js`
- `webapp/`
- `macos-app/`
- `scripts/`
- tests
- CI workflows

Inspect actual repository structure.

## Required implementation steps

### Step 1 — Update README

README must document:

1. Purpose:
   - local-first mail summarisation and triage.
2. Modes:
   - Sample Mailbox;
   - live IMAP/SMTP.
3. Multi-account setup.
4. Mailbox discovery.
5. Local index.
6. Saved scopes.
7. MailMate-like scopes:
   - explain that MailMate smart mailboxes are recreated as app scopes, not read directly from MailMate.
8. Safe actions:
   - preview;
   - confirmation;
   - no default destructive operations.
9. Provider setup:
   - Ollama;
   - OpenAI;
   - Anthropic.
10. Security caveats:
   - real mailbox credentials;
   - local SQLite;
   - secret masking;
   - use at own risk.

### Step 2 — Update project website in `docs/`

Update GitHub Pages docs to reflect:

- multi-account workflow;
- mailbox discovery;
- local index;
- saved scopes;
- dashboard screenshots or placeholder descriptions;
- safety model.

Do not overpromise. If a feature is partial, label it accurately.

### Step 3 — Update UI copy

Review browser and macOS UI text for consistency:

- “Sample Mailbox”
- “Live Mailbox”
- “Accounts”
- “Mailboxes”
- “Saved Scopes”
- “Triage Dashboard”
- “Preview action”
- “Apply action”

Do not expose internal names like `dummyMode` in user-facing text unless it is an advanced/developer field.

### Step 4 — Add validation script coverage if missing

If not already covered, extend rendered/full-stack validation to check:

1. Settings loads.
2. Sample mailbox still works.
3. Mailbox discovery endpoint in sample mode works.
4. Saved scopes list.
5. Dashboard loads.
6. Action preview rejects missing confirmation or shows preview.

Keep CI runtime reasonable.

### Step 5 — Run full verification

Run:

```bash
pytest -q
./scripts/check_repo_hygiene.sh
git diff --check
python scripts/validate_full_stack.py
./scripts/validate_full_stack.sh
python scripts/validate_rendered_ui.py
```

If environment constraints prevent a command, document exactly why.

### Step 6 — Update `STATUS.md`

`STATUS.md` must include:

- current architecture;
- implemented multi-account status;
- mailbox discovery status;
- indexing status;
- saved-scope status;
- dashboard status;
- safe-action status;
- known limitations;
- validation commands and results;
- next steps.

## Required tests

This phase should mainly update/extend existing tests. Add tests only where validation gaps are found.

Minimum:

1. Documentation links are not broken if existing checks support this.
2. Web contract covers new endpoints if it has endpoint coverage.
3. Rendered UI covers at least one new surface.
4. Full test suite passes.

## Backwards compatibility constraints

- Do not rename public API fields without compatibility.
- Do not remove old quick filters unless replacements are tested.
- Do not break packaged backend startup.
- Do not require live IMAP credentials for tests.

## Manual validation commands

```bash
pytest -q
./scripts/check_repo_hygiene.sh
git diff --check
python scripts/validate_full_stack.py
./scripts/validate_full_stack.sh
python scripts/validate_rendered_ui.py
```

## Definition of done

- README and docs match implemented behaviour.
- UI copy is coherent.
- Validation covers the main new flows.
- All tests pass or environment-blocked tests are clearly documented.
- `STATUS.md` is current.

## Things explicitly not to do in this phase

- Do not introduce new major features.
- Do not change architecture unless required to fix integration bugs.
- Do not suppress tests.
- Do not present partial features as complete.

