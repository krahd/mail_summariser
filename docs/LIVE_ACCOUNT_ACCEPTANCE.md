# Live-account acceptance

Mail Summariser's paid macOS distribution remains gated on a real-account acceptance run. The acceptance probe is intentionally read-only and does not save credentials into the application database.

## Safety properties

- The command refuses to run unless `MAIL_SUMMARISER_LIVE_ACCEPT=1` is set.
- Credentials are read from environment variables for this process only.
- `safeMode` is forced on and `dummyMode` is forced off.
- The probe checks IMAP and SMTP authentication, discovers mailboxes, then performs one bounded IMAP search/fetch.
- The maximum fetch limit is 20; the default is 5.
- It never calls message-action, move, tag, mark-read, send-mail, settings-save, or database-reset code.
- The evidence report excludes message subjects/bodies/senders, usernames, passwords, and account identities.

This is an acceptance probe, not a substitute for the normal application UI. A passing result establishes that a real account can authenticate and that Mail Summariser can discover and read a bounded sample without mailbox mutation.

## Run

Use a provider-specific app password or equivalent revocable credential where available. Do not commit credentials or put them in shell history. One safe pattern is to export them in a dedicated local shell session, run the probe, then unset them.

Required environment variables:

```text
MAIL_SUMMARISER_LIVE_ACCEPT=1
MAIL_SUMMARISER_IMAP_HOST=...
MAIL_SUMMARISER_IMAP_USERNAME=...
MAIL_SUMMARISER_IMAP_PASSWORD=...
MAIL_SUMMARISER_SMTP_HOST=...
```

Optional variables:

```text
MAIL_SUMMARISER_IMAP_PORT=993
MAIL_SUMMARISER_IMAP_USE_SSL=1
MAIL_SUMMARISER_SMTP_PORT=465
MAIL_SUMMARISER_SMTP_USE_SSL=1
MAIL_SUMMARISER_SMTP_PASSWORD=...   # defaults to the IMAP password
MAIL_SUMMARISER_LIVE_MAILBOX=INBOX
MAIL_SUMMARISER_LIVE_LIMIT=5        # hard-capped at 20
```

Then run:

```bash
backend/.venv/bin/python scripts/validate_live_account.py --json
```

A successful JSON result is deliberately sparse and is safe to retain as release evidence. A failure exits non-zero and prints a high-level error. The application already redacts credential material in mail-service failures, but the acceptance runner still avoids including provider error payloads in its evidence record.

## What this does not prove

This gate does not exercise mailbox mutations, undo, archive/move, tagging, or outbound summary delivery. Those remain separate acceptance checks after read-only real-account behavior has passed. It also does not itself build, sign, notarise, or publish the macOS application.
