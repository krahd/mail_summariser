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


# 06 — Saved scopes that recreate useful MailMate smart mailboxes

## Goal

Add saved query scopes that approximate MailMate smart mailboxes using IMAP/index criteria.

This phase should create reusable scopes such as “Unread or Flagged all”, “Flagged all”, and “Unread or Flagged, Lists_Fing”. These scopes are the bridge between the user’s MailMate mental model and the IMAP-backed app.

## Current problem

MailMate smart mailboxes are not IMAP folders. They are saved searches across accounts, folders, flags, tags, lists, and message state. The app needs its own saved-scope model.

## Files likely involved

- `backend/db.py`
- `backend/schemas.py`
- new service module, e.g. `backend/saved_scope_service.py`
- new router module, e.g. `backend/routers_saved_scopes.py`
- `backend/app.py`
- `webapp/api.js`
- tests
- `STATUS.md`

Inspect existing route and schema style before editing.

## Required implementation steps

### Step 1 — Add saved scopes table

Add table:

```sql
saved_scopes (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  query_json TEXT NOT NULL,
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

Ensure full database reset clears saved scopes or restores defaults, depending on chosen behaviour. Prefer restoring defaults after reset.

### Step 2 — Define saved-scope schema

Add models similar to:

```python
class SavedScope(BaseModel):
    id: str
    name: str
    description: str = ''
    query: dict
    sortOrder: int = 0

class SavedScopeCreateRequest(BaseModel):
    id: str | None = None
    name: str
    description: str = ''
    query: dict
```

### Step 3 — Add default MailMate-like scopes

On startup or reset, ensure defaults exist:

1. `unread_or_flagged_all`
   - name: `Unread or Flagged all`
   - accounts: all enabled
   - mailboxes: default included mailboxes, initially `INBOX`
   - condition: unread OR flagged
   - exclude deleted/junk

2. `flagged_all`
   - name: `Flagged all`
   - condition: flagged

3. `unread_all`
   - name: `Unread all`
   - condition: unread

4. `lists_fing`
   - name: `Unread or Flagged, Lists_Fing`
   - condition: unread OR flagged
   - keyword/tag/list match: `List_Fing` or `fing.edu.uy` list metadata
   - exclude deleted/junk

5. `finance`
   - optional if already present in UI quick filters; map to keyword/sender/list patterns.

Use flexible query JSON. Example:

```json
{
  "accounts": ["*"],
  "mailboxes": ["INBOX"],
  "excludeMailboxes": ["Trash", "Deleted Messages", "Junk"],
  "any": [
    {"unread": true},
    {"flagged": true}
  ],
  "all": [
    {"notMailboxKind": "junk_or_trash"}
  ]
}
```

Keep the evaluator simple.

### Step 4 — Implement scope evaluation against index

Implement:

```python
list_messages_for_scope(scope_id, limit=200)
```

It should use the local index tables from phase 05.

Minimum supported query terms:

- accounts
- mailboxes
- excludeMailboxes
- unread
- flagged
- keyword/tag
- listId contains
- sender contains
- subject contains
- `any` / `all` boolean grouping

Do not build a full query language. Implement only what defaults need plus simple custom use.

### Step 5 — Add API endpoints

Add:

```http
GET /mail/scopes
POST /mail/scopes
PUT /mail/scopes/{scope_id}
DELETE /mail/scopes/{scope_id}
GET /mail/scopes/{scope_id}/messages
POST /mail/scopes/{scope_id}/summary
```

If `POST /mail/scopes/{scope_id}/summary` is too much for this phase, add only the message listing endpoint and document summary integration as next. But prefer implementing summary if it can reuse existing `summarize_messages`.

### Step 6 — Scope summary behaviour

A scope summary should:

1. Load indexed messages for scope.
2. Clamp limit.
3. Fetch cached body preview/body text only.
4. Call existing `summarize_messages`.
5. Store job like normal summaries, with criteria including `scopeId`.

Do not perform IMAP sync automatically unless explicitly requested. Use current index state.

## Required tests

Add tests for:

1. Default scopes are created.
2. Reset restores default scopes.
3. Custom scope can be created/read/updated/deleted.
4. Scope evaluator returns unread OR flagged messages.
5. Scope evaluator excludes Deleted/Junk mailboxes.
6. `lists_fing` matches keyword `List_Fing`.
7. Scope summary creates a job.
8. Scope summary handles empty result without provider call.
9. Existing summary tests pass.

## Backwards compatibility constraints

- Existing quick filters still work.
- Existing `/summaries` endpoint still works.
- Saved scopes are additive.
- No real mailbox actions are applied.

## Manual validation commands

```bash
pytest -q tests/test_backend_mail_flow.py
pytest -q tests/test_web_contract.py
pytest -q
./scripts/check_repo_hygiene.sh
git diff --check
```

Run rendered UI validation only if UI changed:

```bash
python scripts/validate_rendered_ui.py
```

## Definition of done

- The app has persistent saved scopes.
- Default scopes approximate the user’s MailMate sidebar priorities.
- Scopes can list indexed messages.
- Scope summaries work or are explicitly deferred with tests/docs.
- `STATUS.md` records the change.

## Things explicitly not to do in this phase

- Do not redesign the entire dashboard.
- Do not perform destructive actions.
- Do not require MailMate access.
- Do not make automatic sync mandatory before scope queries.

