# IMAP Test Plan

This project now supports two mail modes:

- `dummyMode=true`: the built-in test mailbox and in-memory outbox
- `dummyMode=false`: a real IMAP mailbox plus a real SMTP server

## Goal

Prove that search, summary, actions, undo, and delivery work end to end against an actual IMAP account in a controlled environment before pointing the app at a third-party mailbox.

## Evaluation: should we build our own IMAP server for tests?

Yes, but only as a constrained test double.

It is not reasonable to build a full IMAP server ourselves for production-grade interoperability. IMAP is too large and too subtle for that to be a good use of time here.

It is reasonable to build a minimal server for automated tests if the scope is narrow and explicit. The app only needs a small subset of the protocol:

- `LOGIN`
- `SELECT`
- `UID SEARCH`
- `UID FETCH`
- `UID STORE`
- `NOOP`
- `LOGOUT`

For SMTP we only need:

- `EHLO` / `HELO`
- `AUTH PLAIN` / `AUTH LOGIN`
- `MAIL FROM`
- `RCPT TO`
- `DATA`
- `NOOP`
- `QUIT`

That is the approach implemented in [`tests/support/fake_mail_server.py`](/Users/tom/devel/ml-llm/llm/Mail-Summariser/tests/support/fake_mail_server.py).

## Plan

1. Run automated backend integration tests against the local fake IMAP/SMTP account.
2. Run frontend contract checks for tab names, dummy-mode control, and log copy.
3. Run the backend HTTP smoke test against a fresh temporary database.
4. Run macOS Swift typecheck to ensure the desktop shell still compiles.
5. Optional external-provider follow-up:
   Use a disposable mailbox on a real provider with SSL-enabled IMAP/SMTP and repeat the same UI workflow manually.

## Coverage

The automated plan verifies:

- settings persistence, including masked passwords
- dummy mode toggling
- connection testing in dummy mode and real IMAP mode
- summary creation from dummy data and IMAP data
- `mark_read` mutating `\Seen`
- `tag_summarised` mutating IMAP keywords
- row-level undo for both actions
- email summary delivery over SMTP
- final vs undoable log state
- web copy for `Main`, `Log`, and dummy-mode controls

## Execute

Run:

```bash
./scripts/run_imap_test_plan.sh
```

## Manual external account checklist

After the controlled plan passes, use a disposable mailbox and verify:

1. Save real IMAP/SMTP settings with `Dummy Mode` off.
2. Click `Test Connection` from the top of Settings.
3. Create a summary from a known unread message.
4. Run `Mark Read`, confirm the message becomes read in the mailbox, then undo it.
5. Run `Tag Summarised`, confirm the keyword appears in the mailbox, then undo it.
6. Run `Email Summary` and confirm the digest arrives at the configured recipient.
7. Confirm the Log view shows `Undo` only where the action is actually reversible.
