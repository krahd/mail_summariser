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


# 09 — Structured pre-summary analytics

## Goal

Improve summarisation by adding deterministic pre-analysis before LLM calls. The model should summarise structured evidence, not a raw flat list of email blobs.

This phase should make summaries more useful for email control without making the LLM responsible for all classification.

## Current problem

The prompt currently sends a flat numbered list of messages. For large mailboxes, this is weak. The app needs deterministic grouping and feature extraction first.

## Files likely involved

- `backend/summary_service.py`
- new module, e.g. `backend/mail_analysis_service.py`
- triage service
- saved scope service
- tests for summary service
- `STATUS.md`

Inspect existing prompt tests before editing.

## Required implementation steps

### Step 1 — Add message analysis function

Implement:

```python
analyze_messages_for_summary(messages: list[dict]) -> dict
```

It should return structured data:

```json
{
  "messageCount": 123,
  "senders": [...],
  "senderDomains": [...],
  "mailingLists": [...],
  "threads": [...],
  "deadlineCandidates": [...],
  "replyNeededCandidates": [...],
  "flaggedMessages": [...],
  "bulkCandidates": [...],
  "oldestDate": "...",
  "newestDate": "..."
}
```

Keep extraction deterministic and transparent.

### Step 2 — Thread/group related messages

Group by:

- normalized subject with `Re:`, `Fwd:`, `[list]` prefixes stripped;
- `Message-ID` / `References` if available in index;
- sender/list where subject grouping is insufficient.

If message headers are not available, subject grouping is enough.

### Step 3 — Extract features

Implement simple heuristics:

- deadline terms:
  - `deadline`, `due`, `submit`, `closes`, `vence`, `vencimiento`, `fecha límite`, `plazo`
- reply-needed terms:
  - `please`, `could you`, `can you`, `let me know`, `confirm`, `review`, `approve`, `podés`, `puedes`, `confirmar`
- finance terms:
  - invoice, payment, receipt, factura, pago, transferencia
- academic/admin terms:
  - committee, grant, call for papers, deadline, seminar, charla, defensa, convocatoria
- list/noise:
  - `List-Id`, `List-Unsubscribe`, `novedades`, `boletín`, repeated list sender

Do not overclaim. Use “candidate” wording.

### Step 4 — Change prompt construction

Modify `_build_prompt(...)` or add a new prompt builder so the provider receives:

1. Scope metadata if available.
2. Summary of deterministic analysis.
3. Grouped messages.
4. Selected raw excerpts only where needed.
5. The existing sentinel requirement.

Keep existing guardrails:

- do not invent facts;
- focus on deadlines, requests, blockers, likely responses;
- group related messages;
- include next-step cues.

### Step 5 — Keep fallback summary useful

Update deterministic fallback summary to use analysis:

- group by sender/list/thread;
- show counts;
- mark candidate deadlines/replies;
- avoid “Action: review...” repeated for every message.

### Step 6 — Add tests locking prompt behaviour

Tests should assert that:

- prompt includes analysis section;
- prompt includes grouped thread/list information;
- prompt includes sentinel instruction;
- prompt does not omit subject/from/date;
- fallback summary contains grouped information;
- empty summaries still skip provider.

## Required tests

Add/update tests for:

1. subject normalization.
2. deadline candidate extraction.
3. reply-needed candidate extraction.
4. mailing-list grouping.
5. grouped prompt includes analysis.
6. fallback summary uses grouped output.
7. provider sentinel behaviour still works.
8. no-message summary still avoids provider call.
9. existing summary-service provider tests pass.

## Backwards compatibility constraints

- `/summaries` response shape should not change unless optional metadata is added safely.
- Existing provider clients should not change.
- Existing system message settings should still apply.
- Do not require an LLM to compute basic triage buckets.

## Manual validation commands

```bash
pytest -q tests/test_summary_service_provider_library.py
pytest -q tests/test_fuzz_summary_payloads.py
pytest -q
./scripts/check_repo_hygiene.sh
git diff --check
```

## Definition of done

- Summaries are built from deterministic pre-analysis.
- Prompt is more structured.
- Fallback output is materially better.
- Existing provider/fallback semantics remain stable.
- `STATUS.md` records the change.

## Things explicitly not to do in this phase

- Do not add new providers.
- Do not make LLM classification required for dashboard.
- Do not change mail sync semantics.
- Do not add destructive actions.

