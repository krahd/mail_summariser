# Synthetic demo acceptance checkpoint

6 October 2026. Draft implementation only; final reset-race recheck pending.

The green runtime checkpoint below predates the final reset/detail-race correction. That correction invalidates both selected-detail request generations immediately when reset is confirmed, and includes held success/error regressions for review and triage plus failed-reset recovery. The expanded browser acceptance and settled mobile screenshots must pass on the new code head; this document does not attribute the older run to later runtime changes.

## Reproducible source and evidence

Runtime/code head: `f67dbe5c9524e47c25579b8b93b368add2e02937`.

- [Ordinary CI 37509282224](https://github.com/krahd/mail_summariser/actions/runs/37509282224): passed. Python 3.11/3.12 tests, hygiene, existing rendered UI regression and Linux/macOS/Windows startup jobs completed successfully.
- [Synthetic Chromium CI 37509282239](https://github.com/krahd/mail_summariser/actions/runs/37509282239): passed. Nineteen synthetic API tests with outbound transport/provider/SMTP traps and fifteen real-browser scenario groups.
- [Small evidence artifact 11434495213](https://github.com/krahd/mail_summariser/actions/runs/37509282239/artifacts/11434495213): four PNGs, mobile geometry and summary JSON. Retained by CI for seven days. The JSON records source head `f67dbe5c9524e47c25579b8b93b368add2e02937` and GitHub's test merge checkout `675a63314f96af3c8bf3980de81a8d6c7a32ff1a`.
- Local full regression: 205 passed, one expected skip. Five original mocked client-state checks passed at this checkpoint; the reset-race correction expands this to nine. These are distinct from browser evidence.

This report initially accompanied a documentation-only publication. Subsequent runtime changes require their own workflow result; no later runtime change inherits this acceptance automatically.

## Covered browser scenarios

1. Failed initial dashboard loading remains an error; visible Reload recovers.
2. Synthetic first-run isolation, pre-indexed messages and ignoring a stored external backend target.
3. Evidence inspection, triage candidate summary, local excerpts and source-message reading.
4. Per-message preview cancellation without mutation.
5. Safe-mode simulation of selected actions.
6. Apply, duplicate-click suppression, grouped undo and index recovery.
7. Real one-shot index faults after completed apply/undo, failed rebuild and successful non-destructive retry. History is preserved; completed mutations are not repeated.
8. Completed mutation with failed view refresh retains a truthful warning.
9. Cancelling an in-flight preview prevents late reopening.
10. Cancelling a digest preserves the existing review.
11. Out-of-order digest responses cannot replace the newer selection.
12. Failed summary preserves the old result; explicit retry recovers.
13. Action error recovery and navigation invalidate pending confirmation.
14. Cancelled and confirmed reset paths restore safe onboarding.
15. Mobile layout, scrolling, summary generation and reachable cancellation controls.

The browser recorded no external requests. Its synthetic backend trapped outbound network/provider/SMTP calls. Tests used visible controls, not force-clicks or hidden legacy actions. Strict mobile geometry measured 390px viewport and 390px document width.

## Review repairs

All three initial independent findings were repaired: the validator now uses visible scoped actions; completed mutations report projection/index failure separately with a visible non-destructive rebuild; failed view loading cannot be overwritten by a green ready state. Browser testing then found two additional mobile issues, corrected by wrapping header status text and keeping the narrow-screen footer in document flow so it cannot cover Cancel.

The author inspected the retained desktop and mobile images. The mobile source-message table remains compact, with truncated sender/date columns; the selected message below and every action preview show full evidence. Broader responsive/accessibility refinement is still appropriate before a public product release.

## Boundaries

This is a synthetic workflow checkpoint, not live-account or commercial acceptance. Real-account authorisation and provider compatibility, sustained daily use, live privacy/security review, cross-browser/platform accessibility, native packaging/distribution, demand/pricing and support remain gates. No real mail, credentials, outbound messages, OAuth grants, provider transmission, release, deployment, billing, App Store or TestFlight work was performed.
