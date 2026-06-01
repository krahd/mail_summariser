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


# 08 — Safe actions and dry-run workflows

## Goal

Add safe action workflows for indexed/scoped mail: mark read/unread, flag/unflag, add/remove keyword, move/archive where supported, and dry-run bulk actions.

This phase must be conservative. Real mailbox changes must require explicit confirmation.

## Current problem

The app has some action support, but it was built for simple message IDs and a single mailbox. After multi-account, mailbox-scoped search, and indexing, actions must understand account/mailbox/UID context and prevent accidental large destructive operations.

## Files likely involved

- `backend/mail_service.py`
- `backend/routers_actions.py`
- `backend/schemas.py`
- `backend/db.py`
- local index service
- saved scope service
- `webapp/app.js`
- `webapp/api.js`
- tests
- `STATUS.md`

Inspect current action routes and undo machinery.

## Required implementation steps

### Step 1 — Define composite message identity parser

If phase 04 created composite IDs, centralise parsing.

Example composite ID:

```text
account_id|mailbox_path|uid
```

Implement robust parsing and validation:

- reject malformed IDs;
- do not allow path traversal semantics;
- preserve mailbox path text exactly after decoding.

If the repo uses separate metadata fields, implement equivalent lookup.

### Step 2 — Add action preview model

Add request/response models:

```python
class MailActionPreviewRequest(BaseModel):
    action: str
    messageIds: list[str] = []
    scopeId: str | None = None
    bucketId: str | None = None
    limit: int = 100

class MailActionPreviewResponse(BaseModel):
    action: str
    count: int
    affectedMessages: list[MessageItem]
    warnings: list[str]
    requiresConfirmation: bool
```

### Step 3 — Add dry-run endpoint

Add:

```http
POST /mail/actions/preview
```

Supported actions:

- `mark_read`
- `mark_unread`
- `flag`
- `unflag`
- `add_keyword`
- `remove_keyword`
- `move_to_mailbox`
- `archive`

For this phase, if archive/move support is not portable enough, implement preview only and mark execution unsupported with a clear error.

### Step 4 — Add confirmed execution endpoint

Add:

```http
POST /mail/actions/apply
```

Rules:

1. Requires `confirm: true`.
2. Requires either explicit message IDs or a saved scope/bucket with a limit.
3. Limit must be clamped, e.g. max 500.
4. If action affects more than safe threshold, return error requiring lower limit or stronger confirmation string.
5. Return affected IDs and failed IDs.
6. Push undo payloads where undo is possible.
7. Update local index after successful actions.

### Step 5 — Implement action semantics

Minimum required real IMAP operations:

- mark read: `+FLAGS (\Seen)`
- mark unread: `-FLAGS (\Seen)`
- flag: `+FLAGS (\Flagged)`
- unflag: `-FLAGS (\Flagged)`
- add keyword: `+FLAGS (<keyword>)`
- remove keyword: `-FLAGS (<keyword>)`

Optional and only if safe:

- archive/move: IMAP `MOVE` if supported, else `COPY` + `STORE +FLAGS.SILENT (\Deleted)` + expunge must NOT be default. Avoid expunge in this phase unless explicit.

### Step 6 — Add UI affordance

Add action buttons only where there is a clear preview step.

Flow:

1. User selects bucket/scope/messages.
2. User clicks action.
3. Preview is shown.
4. User confirms.
5. Apply occurs.
6. Result shown with failures if any.

No one-click destructive actions.

## Required tests

Backend tests:

1. Composite message ID parsing works.
2. Malformed IDs are rejected.
3. Preview returns count and warnings.
4. Apply without confirmation is rejected.
5. Apply mark-read calls IMAP `STORE +FLAGS`.
6. Apply flag calls IMAP `STORE +FLAGS`.
7. Apply updates local index.
8. Failed per-message action is reported.
9. Large actions are blocked or require stronger confirmation.
10. Sample mailbox action behaviour still works.

UI tests if changed:

1. Preview step appears before apply.
2. Apply button disabled until confirmation.
3. Failure result is visible.

## Backwards compatibility constraints

- Existing action routes must keep working if still used by current UI.
- Do not remove undo.
- Do not implement delete/expunge.
- Do not silently archive/move.

## Manual validation commands

```bash
pytest -q tests/test_backend_mail_flow.py
pytest -q
python scripts/validate_rendered_ui.py
./scripts/check_repo_hygiene.sh
git diff --check
```

## Definition of done

- Actions understand account/mailbox/UID context.
- Preview-before-apply is implemented.
- Real actions require confirmation.
- Local index is updated after actions.
- Undo is preserved where possible.
- `STATUS.md` records the change.

## Things explicitly not to do in this phase

- Do not implement permanent deletion.
- Do not expunge mailboxes.
- Do not allow one-click bulk actions.
- Do not auto-apply LLM recommendations.

