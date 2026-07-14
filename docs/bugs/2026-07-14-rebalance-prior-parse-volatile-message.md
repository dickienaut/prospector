# rebalance-prior-parse-volatile-message — the E1 volatile-message alarm, re-appearing on a sibling path

*Bug record, 2026-07-14. Status: **fixed** (reference patch drafted, pending land). Class: §1.7
nuisance-alarm/GPWS. Branch `m6-discourse-capture` @ `4739b528bc`. The direct recurrence of E1
(2026-07-10) on a path the E1 fix did not touch.*

- **Symptom.** When a rebalance basket has a frozen **prior** holdings pull that cannot be parsed (a genuinely
  broken prior — corrupt/truncated freeze), the operational fault it raises **pages every tick** instead of
  paging once and riding the heartbeat. Reproduced: two ticks a day apart, each with an unparseable prior →
  two *different* `_fault_signature`s → the §10 suppression treats tick 2 as new. MEDIUM severity (needs a
  persistently-broken prior, rarer than E1's live-403 path, but the mechanism is identical).

- **Root cause.** In `_run_rebalance` (`prospector/runner/runner.py`) the **current-feed** parse fault passes a
  stable `key=f"{ticker}:{status}"` (correct — the E1 `key=` convention). Its **sibling 11 lines below**, the
  **prior-parse** fault, passes **no `key=`** — so `_fault_signature` falls back to the full message, which
  embeds `prior_dates[-1]` (the newest frozen date strictly before today). That date **advances** as pulls
  accumulate, so a persistently-unparseable prior renders a different message every tick → a different
  signature → pages daily. Verbatim: `XLK prior 2026-07-13: no holdings header …` vs `XLK prior 2026-07-14: …`.
  The E1 fix minted the `key=` convention but only applied it to the sites known at the time; this sibling
  shipped later (the rebalance runner-wiring) and re-introduced the exact gap.

- **Fix.** Give the prior-parse `_emit_fault` a stable `key=f"{ticker}:prior:{getattr(e,'status',None)}"`. The
  message **keeps** the moving prior date for forensics; only the *signature* keys on the stable
  `(ticker, prior, status)`. One-line change, the same shape as the E1 fix.

- **Regression test.** `tests/test_runner_rebalance_cash_and_prior.py::test_unparseable_prior_fault_signature_
  is_stable_across_ticks`. Runs two ticks a day apart (each with a frozen-but-unparseable prior; the newest
  prior date advances between them) and compares the **real** `_fault_signature` of the emitted faults.
  Asserts BEHAVIOUR: the signature is *stable* across ticks (so §10 suppresses the recurrence) — not any
  specific key string. RED on the branch (signatures differ on the moving date); GREEN after the patch.

- **Why the suite missed it.** No existing test exercises a *persisting* unparseable prior across more than one
  tick, so the moving-date-in-message never surfaced. Same shape as the E1 miss: the suppression path is only
  tested with a single tick or a stable message.

- **Rule born.** None new — this is why it matters. It is a live demonstration that the E1 rule (§8a
  `_emit_fault(key=…)` stable-key convention) is **not yet enforced in mechanism** (class §1.3 territory): a
  new `_emit_fault` site with a volatile message can silently reopen the class, and did. Candidate hardening
  for the design seat: a lint/guard that flags an `_emit_fault` call whose `message` contains a moving token
  (a date, a URL, an epoch) but passes no `key=` — turning the convention from prose into a mechanical check.

- **References.** `notes/m6_deep_review_findings_qa.md` (R4), `2026-07-10-email-volatile-fault-suppression.md`
  (E1 — the parent bug and the `key=` convention this path failed to inherit), `docs/decisions/2026-07-10-10-
  email-sender.md` (§8a CONTRACT). Sibling bugs by class: E1, E2, C.1, fault-taxonomy count-lie (§1.7).
