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


# 05 — Local incremental mail index

## Goal

Add a SQLite-backed local mail index so summaries and dashboards can operate over cached message metadata instead of rescanning IMAP mailboxes every time.

This phase should introduce the index and a basic sync operation. It should not yet build the full dashboard.

## Current problem

Even with server-side search, repeated IMAP scans are slow and provider prompts are too raw. The app needs persistent local metadata for accounts, mailboxes, messages, flags, keywords, and sync state.

## Files likely involved

- `backend/db.py`
- `backend/mail_service.py`
- `backend/schemas.py`
- new service module, e.g. `backend/mail_index_service.py`
- new route module, e.g. `backend/routers_mail_index.py`
- `backend/app.py`
- tests
- `STATUS.md`

Inspect existing DB style before editing.

## Required implementation steps

### Step 1 — Add database tables

Add migrations or idempotent `CREATE TABLE IF NOT EXISTS` statements for:

```sql
mail_accounts_index (
  id TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  username TEXT NOT NULL,
  imap_host TEXT NOT NULL,
  enabled INTEGER NOT NULL,
  updated_at TEXT NOT NULL
);

mailboxes_index (
  id TEXT PRIMARY KEY,
  account_id TEXT NOT NULL,
  path TEXT NOT NULL,
  delimiter TEXT,
  selectable INTEGER NOT NULL,
  flags_json TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(account_id, path)
);

messages_index (
  id TEXT PRIMARY KEY,
  account_id TEXT NOT NULL,
  mailbox_path TEXT NOT NULL,
  uid TEXT NOT NULL,
  message_id_header TEXT,
  subject TEXT NOT NULL,
  sender TEXT NOT NULL,
  recipients_json TEXT NOT NULL,
  date TEXT NOT NULL,
  flags_json TEXT NOT NULL,
  keywords_json TEXT NOT NULL,
  list_id TEXT NOT NULL,
  body_preview TEXT NOT NULL,
  body_cached INTEGER NOT NULL DEFAULT 0,
  body_text TEXT NOT NULL DEFAULT '',
  last_seen_at TEXT NOT NULL,
  UNIQUE(account_id, mailbox_path, uid)
);

sync_state (
  account_id TEXT NOT NULL,
  mailbox_path TEXT NOT NULL,
  uidvalidity TEXT NOT NULL DEFAULT '',
  uidnext TEXT NOT NULL DEFAULT '',
  last_sync_at TEXT NOT NULL,
  PRIMARY KEY(account_id, mailbox_path)
);
```

Adjust names to repo style if needed. Keep idempotent.

### Step 2 — Add index service functions

Implement functions such as:

```python
upsert_index_account(account)
upsert_index_mailbox(account_id, mailbox)
upsert_index_message(message)
list_index_messages(criteria)
get_index_message(message_id)
update_sync_state(...)
```

Keep these simple and tested.

### Step 3 — Add basic sync function

Implement:

```python
sync_mailbox(account, mailbox_path, limit=500) -> dict
```

For this phase:

1. Discover/select mailbox.
2. Search recent or all UIDs, but clamp limit.
3. Fetch headers/body preview for up to limit.
4. Upsert into `messages_index`.
5. Store flags/keywords.
6. Store `list_id` if present from headers:
   - `List-Id`
   - optionally `List-Unsubscribe`
7. Update `sync_state`.

Do not attempt full IMAP QRESYNC/CONDSTORE complexity yet. Make a simple safe sync.

### Step 4 — Add sync API

Add endpoint(s), for example:

```http
POST /mail/index/sync
GET /mail/index/messages
GET /mail/index/messages/{message_id}
```

`POST /mail/index/sync` request should allow:

- accountId
- mailbox
- limit

Return:

- accountId
- mailbox
- scanned
- indexed
- errors

### Step 5 — Query the index

`GET /mail/index/messages` should support enough query parameters or request criteria to filter by:

- accountId
- mailbox
- unread
- flagged
- tag/keyword
- listId
- sender
- limit

This does not need to replace `/summaries` yet. That happens later.

### Step 6 — Preserve existing jobs

Do not rewrite existing `jobs` storage. The mail index is additive.

## Required tests

Add tests for:

1. DB tables are created by `init_db`.
2. Upsert account/mailbox/message works.
3. Re-upserting the same message updates rather than duplicates.
4. `list_id` is extracted from headers.
5. Sync clamps limit.
6. Sync indexes messages from fake/monkeypatched IMAP.
7. Query index filters unread.
8. Query index filters flagged.
9. Query index filters list ID.
10. Existing tests pass.

## Backwards compatibility constraints

- Do not replace `/summaries` yet.
- Do not remove old DB tables.
- Do not break database reset; reset should clear index tables or explicitly preserve them. Prefer clearing them on full reset.
- Do not cache full bodies for every message by default.

## Manual validation commands

```bash
pytest -q tests/test_backend_mail_flow.py
pytest -q tests/test_web_contract.py
pytest -q
./scripts/check_repo_hygiene.sh
git diff --check
```

If you add new test files, run them explicitly too.

## Definition of done

- SQLite has an idempotent mail index schema.
- Basic mailbox sync indexes message metadata safely.
- Indexed messages can be queried.
- Full-body fetching remains controlled.
- `STATUS.md` records the change.

## Things explicitly not to do in this phase

- Do not implement the dashboard.
- Do not implement saved MailMate-like scopes yet.
- Do not perform destructive actions based on index.
- Do not require index for existing summary flow yet.

