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


# 07 — Triage dashboard for email control

## Goal

Add a dashboard that turns indexed mail and saved scopes into a high-level control surface: what needs reply, what is flagged, what is deadline-related, what is list noise, and what can likely be bulk-handled.

This phase is mostly read-only.

## Current problem

A flat digest is not enough for thousands of emails. The user needs a triage dashboard with buckets and counts, then summaries per bucket.

## Files likely involved

- `backend/schemas.py`
- new service module, e.g. `backend/triage_service.py`
- new route module, e.g. `backend/routers_triage.py`
- `backend/app.py`
- `webapp/index.html`
- `webapp/app.js`
- `webapp/api.js`
- `webapp/styles.css` or equivalent
- rendered UI tests
- backend tests
- `STATUS.md`

Inspect actual UI structure before editing.

## Required implementation steps

### Step 1 — Define triage categories

Implement read-only categories computed from the local index:

1. `reply_needed_candidates`
   - messages with question marks, direct requests, “could you”, “please”, “confirm”, “let me know”, etc.
   - do not claim certainty; label as candidates.

2. `flagged`
   - messages with `\Flagged`.

3. `deadlines`
   - messages containing deadline-like dates or words: deadline, due, vence, vencimiento, submit, cierre, closes.

4. `mailing_lists`
   - messages with `List-Id`, list keywords, or known list tags such as `List_Fing`.

5. `stale_unread`
   - unread messages older than configurable threshold, e.g. 14 days.

6. `bulk_archive_candidates`
   - list messages that are read or stale and not flagged.

7. `recent_unread`
   - unread messages from recent threshold, e.g. 7 days.

Keep heuristics transparent. Do not overstate.

### Step 2 — Add backend dashboard endpoint

Add:

```http
GET /mail/triage/dashboard
```

Parameters:

- `scopeId` optional
- `limitPerBucket` optional, clamp 1–100
- `staleDays` optional, clamp 1–365

Response:

```json
{
  "scopeId": "unread_or_flagged_all",
  "generatedAt": "...",
  "totals": {
    "messages": 4271,
    "unread": 2915,
    "flagged": 138
  },
  "buckets": [
    {
      "id": "reply_needed_candidates",
      "label": "Reply-needed candidates",
      "count": 8,
      "messages": [...]
    }
  ]
}
```

### Step 3 — Add summary endpoint for dashboard bucket

Add:

```http
POST /mail/triage/buckets/{bucket_id}/summary
```

It should:

1. Recompute the bucket from index/scope.
2. Clamp message count.
3. Call existing summarizer.
4. Store job with criteria containing `triageBucketId`.

If this is too broad, add only backend service tests and defer UI summary integration.

### Step 4 — Add webapp dashboard UI

Add a dashboard surface that shows:

- scope selector;
- total counts;
- cards for each bucket;
- message samples;
- “Summarise bucket” button.

Keep UI simple and consistent with existing style. Do not redesign the entire app.

### Step 5 — Add source-message drill-down

For each bucket message sample, allow opening message detail if the backend has message text/preview. Reuse existing message detail patterns where possible.

## Required tests

Backend tests:

1. Dashboard endpoint returns totals.
2. Flagged bucket detects flagged messages.
3. Mailing-list bucket detects `List-Id` or `List_Fing`.
4. Stale unread bucket respects threshold.
5. Bucket limits are clamped.
6. Bucket summary creates a job.
7. Empty bucket summary avoids provider call.

UI/rendered tests, if UI changed:

1. Dashboard tab/surface loads.
2. Bucket cards render.
3. Empty dashboard state is explicit.
4. No horizontal overflow.
5. Existing rendered UI test still passes.

## Backwards compatibility constraints

- Do not remove existing Main/Log/Settings/Help surfaces.
- Do not make dashboard depend on a live IMAP connection.
- Dashboard reads from the local index.
- No destructive actions in this phase.

## Manual validation commands

```bash
pytest -q
python scripts/validate_rendered_ui.py
./scripts/check_repo_hygiene.sh
git diff --check
```

## Definition of done

- Backend exposes a read-only triage dashboard.
- Dashboard buckets are transparent and tested.
- UI shows useful categories without overclaiming.
- Existing flows still work.
- `STATUS.md` records the change.

## Things explicitly not to do in this phase

- Do not add real bulk archive/delete actions.
- Do not auto-apply suggested actions.
- Do not claim heuristic categories are certain.
- Do not require LLM classification for dashboard buckets.

