# mail_summariser prompt pack

Use `00-master-plan.md` as the persistent orchestration context, then feed exactly one numbered phase prompt at a time.

Recommended use:

1. Start a fresh coding session.
2. Provide `00-master-plan.md`.
3. Provide the current phase file, e.g. `01-live-imap-hardening.md`.
4. Tell the model: “Implement only this phase. Stop after tests and STATUS.md update.”
5. Run/inspect tests.
6. Commit.
7. Continue with the next phase.

Do not ask a simple model to implement all phases at once.
