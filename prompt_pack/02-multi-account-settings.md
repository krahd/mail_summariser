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


# 02 — Multi-account settings model

## Goal

Introduce a backwards-compatible multi-account settings model while preserving the existing single-account fields.

This phase should create the data structures and API compatibility layer needed for multiple IMAP accounts. It should not yet discover mailboxes or change summary behaviour across multiple accounts.

## Current problem

The backend settings schema currently has only one IMAP/SMTP account:

- `imapHost`
- `imapPort`
- `imapUseSSL`
- `imapPassword`
- `smtpHost`
- `smtpPort`
- `smtpUseSSL`
- `smtpPassword`
- `username`

This is not sufficient for a MailMate-like setup with several sources/accounts.

## Files likely involved

- `backend/config.py`
- `backend/schemas.py`
- `backend/db.py`
- `backend/routers_settings.py`
- `backend/mail_service.py`
- `webapp/api.js`
- settings UI files if needed
- macOS settings model if needed
- tests for settings
- `STATUS.md`

Inspect the repo before editing.

## Required implementation steps

### Step 1 — Add account schema

Add a new Pydantic model, for example:

```python
class MailAccountSettings(BaseModel):
    id: str
    displayName: str = ''
    enabled: bool = True
    imapHost: str = ''
    imapPort: int = 993
    imapUseSSL: bool = True
    username: str = ''
    imapPassword: str = ''
    smtpHost: str = ''
    smtpPort: int = 465
    smtpUseSSL: bool = True
    smtpPassword: str = ''
    recipientEmail: str = ''
```

Use the actual repo style.

### Step 2 — Add `mailAccounts` to app settings

Add `mailAccounts: list[MailAccountSettings]` or an equivalent list of dicts to `AppSettings`.

Default behaviour:

- If no `mailAccounts` setting exists, derive a single legacy account from the existing single-account settings.
- The derived account ID should be stable, e.g. `default`.
- The display name should be based on username or host.
- If the legacy IMAP host is empty, still create a disabled or incomplete default account only if that matches existing settings UX. Prefer minimal disruption.

### Step 3 — Preserve legacy single-account fields

Existing clients and tests may still read/write the old fields. Do not remove them.

Implement compatibility rules:

1. Reading settings returns both:
   - legacy fields;
   - new `mailAccounts`.
2. Writing legacy fields updates the legacy fields as before.
3. Writing `mailAccounts` stores the list.
4. If `mailAccounts` is absent, live mail service can continue using legacy fields.
5. If `mailAccounts` is present, later phases will use it.

Do not change summary behaviour yet.

### Step 4 — Mask account secrets

Secret masking must apply inside `mailAccounts[]`:

- `imapPassword`
- `smtpPassword`

Masked sentinel writes must not overwrite stored account passwords.

If the existing settings update logic has mask handling only for top-level secrets, extend it recursively or explicitly for account secrets.

### Step 5 — Validate account IDs

Account IDs must be:

- non-empty;
- stable strings;
- unique in the list.

Add validation or normalization. Keep it simple.

Suggested rules:

- strip whitespace;
- if missing, derive from username/host;
- reject duplicates with HTTP 400, or normalise only if existing settings routes already normalise user input.

Do not over-engineer.

## Required tests

Add or update tests for:

1. `/settings` includes `mailAccounts`.
2. With legacy settings only, `mailAccounts` contains a derived default account.
3. Updating `mailAccounts` persists the account list.
4. Reading settings masks account passwords.
5. Writing masked account password sentinels does not overwrite stored account passwords.
6. Duplicate account IDs are rejected or safely handled, depending on implementation.
7. Legacy settings fields still work.
8. Existing tests pass.

## Backwards compatibility constraints

- Existing webapp and macOS app must not break if they ignore `mailAccounts`.
- Existing environment variables must still initialise legacy fields.
- Existing live IMAP mode should keep working with the default legacy account.
- Do not require users to re-enter credentials after this phase.

## Manual validation commands

```bash
pytest -q tests/test_system_message_settings.py
pytest -q tests/test_web_contract.py
pytest -q tests/test_backend_mail_flow.py
pytest -q
./scripts/check_repo_hygiene.sh
git diff --check
```

Run rendered UI validation only if settings UI was changed:

```bash
python scripts/validate_rendered_ui.py
```

## Definition of done

- Settings can represent multiple accounts.
- Legacy settings remain compatible.
- Account secrets are masked and protected from masked-overwrite bugs.
- No summary behaviour changes yet.
- `STATUS.md` records the change.

## Things explicitly not to do in this phase

- Do not implement mailbox discovery.
- Do not query multiple accounts during summaries.
- Do not change the main UI dashboard.
- Do not add local indexing.
- Do not implement saved scopes.

