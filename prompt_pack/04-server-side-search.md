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


# 04 — Server-side IMAP search and mailbox-scoped summaries

## Goal

Extend summary/search criteria so the backend can search selected accounts and selected mailboxes using IMAP server-side search instead of fetching all messages from `INBOX`.

This phase makes live summaries scalable enough to operate on thousands of messages.

## Current problem

Live search currently does roughly:

1. select `INBOX`;
2. `UID SEARCH ALL`;
3. fetch every matching full message body;
4. filter locally.

This is too slow and too broad for a large MailMate-like setup.

## Files likely involved

- `backend/schemas.py`
- `backend/mail_service.py`
- `backend/routers_summaries.py`
- `backend/summary_service.py`
- `webapp/api.js`
- tests for summary payloads
- tests for mail flow
- `STATUS.md`

Inspect current tests and API contract before editing.

## Required implementation steps

### Step 1 — Extend `SearchCriteria`

Add optional fields, while preserving existing fields:

```python
accountIds: list[str] = []
mailboxes: list[str] = []
unreadOnly: bool = False
readOnly: bool = False
flagged: bool | None = None
since: str = ''
before: str = ''
listId: str = ''
limit: int = 100
```

Use exact names only if they fit current style. Keep camelCase consistency.

Rules:

- Empty `accountIds` means legacy default account for now.
- Empty `mailboxes` means `INBOX` for now.
- `limit` must be clamped to a safe range, e.g. 1–500.
- Do not remove old fields: `keyword`, `rawSearch`, `sender`, `recipient`, `tag`, `replied`, `useAnd`.

### Step 2 — Add IMAP search query builder

Implement a helper such as:

```python
_build_imap_search_terms(criteria: SearchCriteria) -> list[str]
```

It should produce IMAP-compatible search terms for:

- `UNSEEN` for unread;
- `SEEN` for read;
- `FLAGGED` for flagged;
- `UNFLAGGED` if needed;
- `FROM`;
- `TO`;
- `SUBJECT`;
- `KEYWORD`;
- `SINCE`;
- `BEFORE`;
- `ALL` fallback.

Keep body keyword search conservative. IMAP `TEXT` can be expensive; either implement only when requested or document limitations.

### Step 3 — Select requested mailbox

Refactor `_imap_connection` or add a new helper so live search can select a mailbox path, not only `INBOX`.

Rules:

- default to `INBOX`;
- reject empty mailbox path;
- raise `MailServiceError` if selection fails;
- do not silently fall back to `INBOX` if another mailbox fails.

### Step 4 — Search accounts and mailboxes

Implement logic:

1. Resolve accounts:
   - if `mailAccounts` present and `accountIds` specified, use those accounts;
   - if not, use legacy account.
2. Resolve mailboxes:
   - if specified, use those mailbox paths;
   - otherwise use `INBOX`.
3. For each account/mailbox:
   - connect;
   - select mailbox;
   - run server-side search;
   - limit UIDs;
   - fetch envelope/headers/body preview as needed.
4. Return messages with stable IDs that encode account and mailbox context.

Important: message IDs must not collide across accounts/mailboxes. Use a composite ID format such as:

```text
account_id|mailbox_path|uid
```

or store separate metadata fields and keep ID encoded. Ensure existing actions can parse this later.

### Step 5 — Limit body fetching

Do not fetch full body for thousands of messages by default.

For this phase, fetch full body only for the limited result set. A later phase will separate envelope and body caching.

Clamp default limit to a safe number, e.g. 100.

### Step 6 — Maintain sample mailbox behaviour

Sample mailbox must still work with the existing criteria.

For sample messages:

- `accountIds` and `mailboxes` may be ignored or simulated.
- Add enough metadata only if tests require it.

## Required tests

Add tests for:

1. `SearchCriteria` accepts new fields.
2. `limit` is clamped.
3. live search selects requested mailbox.
4. live search uses `UNSEEN` when `unreadOnly=True`.
5. live search uses `FLAGGED` when `flagged=True`.
6. live search uses `KEYWORD <tag>` when tag is provided.
7. search over two mailboxes returns composite IDs without collisions.
8. failed mailbox selection returns HTTP 400.
9. sample mailbox still works.
10. existing fuzz tests pass.

Use monkeypatched IMAP/fake IMAP to assert called commands.

## Backwards compatibility constraints

- Existing `/summaries` requests without new fields must behave as before.
- Existing webapp quick filters must still work.
- Existing action routes may not yet understand composite IDs; do not apply real actions to composite IDs until phase 08.
- Do not create a database index yet.

## Manual validation commands

```bash
pytest -q tests/test_fuzz_summary_payloads.py
pytest -q tests/test_backend_mail_flow.py
pytest -q tests/test_web_contract.py
pytest -q
./scripts/check_repo_hygiene.sh
git diff --check
```

Run rendered UI validation if webapp request shape changes:

```bash
python scripts/validate_rendered_ui.py
```

## Definition of done

- Summary requests can target specific account IDs and mailbox paths.
- Live IMAP search uses server-side filtering.
- Fetching is limited.
- Composite IDs avoid collisions.
- Existing sample and legacy paths continue to work.
- `STATUS.md` records the change.

## Things explicitly not to do in this phase

- Do not implement local index.
- Do not implement saved MailMate-like scopes.
- Do not implement dashboard clusters.
- Do not implement bulk actions.
- Do not fetch entire mailboxes.

