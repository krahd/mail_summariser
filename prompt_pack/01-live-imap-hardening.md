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


# 01 — Live IMAP hardening before architecture changes

## Goal

Make the current single-account live IMAP/SMTP implementation safer and more predictable before adding multi-account and mailbox-discovery features.

This phase must not add multi-account support yet. It prepares the existing code so later phases can extend it without carrying unsafe behaviour.

## Current problem

The current live mail path can silently continue after authentication errors. It also tends to hide partial failures in IMAP and SMTP actions. For a real mailbox workflow, failed login and failed connection must fail loudly, while individual per-message action failures should be reported rather than silently ignored.

## Files likely involved

- `backend/mail_service.py`
- `backend/routers_settings.py`
- `backend/routers_summaries.py`
- `backend/schemas.py`
- `tests/test_backend_mail_flow.py`
- `tests/test_fuzz_summary_payloads.py`
- any existing fake-mail tests
- `STATUS.md`

Inspect the actual repo before editing. Use existing test naming and style.

## Required implementation steps

### Step 1 — Add explicit auth failure behaviour

In `backend/mail_service.py`, update `_imap_connection(...)` so that:

1. If `username` is non-empty, `imap.login(...)` must be attempted.
2. If login fails, raise `MailServiceError` with a redacted, user-safe message.
3. Do not continue to `select`.
4. Do not silently pass.
5. Logout should still be attempted in cleanup when possible.

Expected behaviour:

```text
bad IMAP login -> summary request returns HTTP 400
bad IMAP login -> test mail connection reports IMAP error
```

### Step 2 — Make mailbox selection failure explicit

Currently the implementation selects `INBOX`. Keep `INBOX` for this phase, but check the result of `select`.

If `select('INBOX')` fails:

- raise `MailServiceError('Could not select mailbox INBOX: ...')`, redacted;
- do not return an empty result as if the mailbox had no mail.

### Step 3 — Make SMTP login failure explicit when sending

In `send_summary_email(...)`:

1. If SMTP username and password are configured, `smtp.login(...)` must be attempted.
2. If login fails, raise `MailServiceError`.
3. Do not silently continue to `send_message`.

Do not change SMTP send semantics beyond this.

### Step 4 — Report per-message IMAP action failures

For marking read/unread and adding/removing keyword flags:

1. Keep best-effort per-message behaviour.
2. Track failed message IDs.
3. Return or log failure details where existing API shapes allow it.
4. Do not break existing API contracts unless tests are updated deliberately and compatibility is preserved.

If the current action route expects a specific payload, preserve it and add optional fields such as `failed_message_ids`.

### Step 5 — Redact sensitive values

Add a small helper if none exists in mail service:

- redact configured username only if it looks like a secret? Usually username is fine.
- always redact password values.
- avoid including raw server challenge strings if they contain supplied password.
- do not expose `imapPassword`, `smtpPassword`, OpenAI keys, Anthropic keys.

Prefer conservative messages:

```text
IMAP authentication failed
SMTP authentication failed
Could not connect to IMAP server: <safe reason>
```

## Required tests

Add or update tests for:

1. IMAP login failure causes summary creation to fail with HTTP 400.
2. IMAP login failure does not return an empty summary.
3. IMAP `select('INBOX')` failure causes HTTP 400.
4. SMTP login failure causes send-summary action to fail.
5. Password text is not present in returned error details.
6. Existing sample mailbox tests still pass.
7. Existing fake-mail tests still pass.

Use existing fake IMAP/fake SMTP patterns if present. If not present, monkeypatch `imaplib.IMAP4_SSL`, `imaplib.IMAP4`, `smtplib.SMTP_SSL`, and/or `smtplib.SMTP`.

## Backwards compatibility constraints

- Do not remove `dummyMode`.
- Do not change default settings.
- Do not add multi-account settings yet.
- Do not change the UI yet.
- Do not change `SearchCriteria` yet.
- Do not change the database schema yet unless absolutely necessary.

## Manual validation commands

```bash
pytest -q tests/test_backend_mail_flow.py
pytest -q tests/test_fuzz_summary_payloads.py
pytest -q
./scripts/check_repo_hygiene.sh
git diff --check
```

## Definition of done

- Bad IMAP credentials fail loudly.
- Bad SMTP credentials fail loudly.
- Failed mailbox selection fails loudly.
- Secrets are not leaked.
- Existing tests pass.
- `STATUS.md` records the change.

## Things explicitly not to do in this phase

- Do not implement multiple accounts.
- Do not add mailbox discovery.
- Do not add a local mail index.
- Do not redesign the UI.
- Do not add MailMate saved scopes yet.

