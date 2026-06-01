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


# 03 — IMAP mailbox discovery

## Goal

Add backend support to discover selectable IMAP mailboxes/folders/labels per configured account.

This phase should expose discovered mailboxes through API endpoints. It should not yet change the summary endpoint to search arbitrary mailboxes unless that is a minimal internal dependency for tests.

## Current problem

The app currently hardcodes `INBOX` in IMAP connection logic. It has no way to list folders/labels such as archive folders, account-specific folders, Gmail labels, or list-related folders.

MailMate smart mailboxes are not directly exposed via IMAP, but underlying IMAP folders and flags/keywords are discoverable and needed for later saved scopes.

## Files likely involved

- `backend/mail_service.py`
- `backend/schemas.py`
- new route module, e.g. `backend/routers_mailboxes.py`
- `backend/app.py`
- `backend/router_context.py` if needed
- settings/account tests
- fake mail server tests if present
- `webapp/api.js` if API contract tests require it
- `STATUS.md`

Inspect the existing route organisation before editing.

## Required implementation steps

### Step 1 — Add mailbox data model

Add a response model similar to:

```python
class MailboxInfo(BaseModel):
    accountId: str
    path: str
    delimiter: str | None = None
    selectable: bool = True
    flags: list[str] = []
    displayName: str = ''
```

Use repo conventions.

### Step 2 — Parse IMAP LIST responses robustly

Implement a function in mail service such as:

```python
discover_mailboxes_for_account(account: dict) -> list[dict]
```

It should:

1. Connect to the account’s IMAP server.
2. Login if username is configured.
3. Run `LIST "" "*"` or equivalent.
4. Parse returned flags, delimiter, and mailbox name.
5. Mark mailboxes with `\Noselect` as `selectable=False`.
6. Decode quoted mailbox names.
7. Avoid crashing on unusual LIST response formats.
8. Return an empty list only when the server genuinely returns no mailboxes.
9. Raise `MailServiceError` on connection/authentication failure.

Keep parsing small and tested.

### Step 3 — Add fake-mail support

If the fake mail server/environment has mailboxes, expose them. If it does not, extend it minimally so tests can simulate:

- `INBOX`
- `Archive`
- `Lists/Fing`
- `Deleted Messages`
- `Junk`

Do not turn fake-mail into a full IMAP server unless already designed that way.

### Step 4 — Add API endpoint

Add an endpoint such as:

```http
GET /mail/accounts/{account_id}/mailboxes
```

It should:

1. Load merged settings.
2. Resolve the account by ID.
3. Reject unknown account with 404.
4. Return mailbox list.
5. Mask/redact sensitive errors.
6. Use sample-mailbox behaviour when `dummyMode` is true:
   - return a small predictable list, or
   - clearly report that sample mailbox has only sample folders.

Prefer predictable sample result:

```json
[
  {"accountId":"sample","path":"INBOX","selectable":true},
  {"accountId":"sample","path":"Lists/Fing","selectable":true}
]
```

### Step 5 — Add optional endpoint for all accounts

If straightforward, add:

```http
GET /mail/mailboxes
```

This returns mailboxes for all enabled accounts. If one account fails, prefer returning per-account error entries rather than failing the entire response. Keep this endpoint read-only.

If this makes scope too large, skip it and document as next step.

## Required tests

Add tests for:

1. Successful mailbox discovery for fake/simulated IMAP.
2. `\Noselect` mailbox is marked `selectable=False`.
3. Unknown account returns 404.
4. Bad credentials return a redacted error.
5. `dummyMode` returns deterministic sample mailbox list.
6. Existing settings tests pass.
7. Existing summary tests pass.

## Backwards compatibility constraints

- Do not change `/summaries` request shape in this phase.
- Do not remove hardcoded `INBOX` summary behaviour yet, unless tests require extracting selection into a helper.
- Existing webapp can ignore the new endpoint.
- Existing macOS app can ignore the new endpoint.

## Manual validation commands

```bash
pytest -q tests/test_backend_mail_flow.py
pytest -q tests/test_web_contract.py
pytest -q
./scripts/check_repo_hygiene.sh
git diff --check
```

## Definition of done

- Backend can list IMAP mailboxes for a configured account.
- API exposes mailbox discovery.
- Bad credentials and parse oddities are handled safely.
- `STATUS.md` records the change.

## Things explicitly not to do in this phase

- Do not implement saved scopes.
- Do not add a mailbox picker UI unless trivial and explicitly requested.
- Do not implement local index.
- Do not search multiple mailboxes in summaries yet.
- Do not implement MailMate smart mailbox recreation yet.

