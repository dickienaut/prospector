# email-volatile-fault-suppression — nuisance-alarm suppression defeated by volatile fault messages

*Bug record, 2026-07-10 (catalogued 2026-07-11). Status: **fixed** (E1); a lower-severity sibling **E2** is
deferred by design (xfail). Class: §1.1 green-on-synthetic/broken-on-real · §1.4 test-passes-for-wrong-reason ·
§1.7 nuisance-alarm/GPWS · §1.8 fails-silently. This is the **worked example** for the archive's record format.*

- **Symptom.** On the live-primary price path (`prices.primary = tiingo`), a *persistent identical* failure —
  e.g. a lapsed Tiingo subscription returning HTTP 403 every day — **pages every single tick** instead of
  paging once and falling silent to the weekly heartbeat. It silently reopens the exact GPWS "cried-wolf" gap
  the §10 sender was built to close (smoke-detector brief §2.4). HIGH severity — reproduced end-to-end through
  the real code, no network.

- **Root cause.** `_compute_push` (`runner.py`) suppresses a recurring fault by comparing this tick's
  `_fault_signature` — a **message-exact** `frozenset((subsystem, message))` — to the prior run's. That is
  correct *only if a persisting fault renders the same message every tick.* It does not: the live price fault
  message embeds the fetch URL (`f"GET {url} -> HTTP {resp.status_code}"`), and the Tiingo URL carries
  `?startDate=…&endDate=…` — **both dates move every tick** (Yahoo: `period1`/`period2` epochs). Same failure →
  different message → different signature → treated as NEW/CHANGED → pages. The suppression *logic* is sound;
  its *comparand* is wrong for the messages the live code actually emits.

- **Fix.** **Separate the suppression key from the display message** (Option 1 of the finding). `_emit_fault`
  gains an optional `key=` (defaulting to the message — backward-compatible for stable-message faults);
  `_fault_signature` keys on `(subsystem, key or message)`; the two URL-bearing sites pass
  `key=f"{ticker}:{status}"`. The message **keeps the full URL** for the fossil/forensics; only the *signature*
  keys on the stable part. **Rejected:** normalizing/stripping tokens inside `_fault_signature` (regex
  whack-a-mole — a new volatile token silently reopens the gap) and coarsening the signature to subsystem-only
  (would swallow a genuinely *changed* fault — the one thing "never swallow a changed fault" forbids).

- **Regression test.** `tests/test_runner_fault_suppression_volatile_message.py`, driving the **real** fault
  path (real `_tiingo_url`, real error text, real `_compute_push`), not a synthetic stub:
  - `test_persistent_price_fault_suppresses_across_ticks` — same 403 two consecutive dates → **no page** on
    tick 2. RED before the fix (moving dates made it page).
  - `test_a_changed_price_status_still_pages` — 403→500 on the same ticker must still page (guards against an
    over-coarse fix). GREEN and must stay GREEN.
  - `test_a_different_failing_ticker_still_pages` · `test_persistent_price_fault_pages_once_over_real_ticks`.

- **Rule born.** The **`_emit_fault(key=…)` stable-key convention** (a fault's suppression identity ≠ its
  display message) and the **§8a alarm-posture CONTRACT** (page once on a new/changed fault, then ride the
  heartbeat; operational faults page, manual-review advisories are counted+surfaced but don't page except on a
  live-lead fund). → `docs/decisions/2026-07-10-10-email-sender.md`. *This is the archive's whole point: the
  bug didn't just get a patch — it minted a rule that now guards the class.*

- **E2 (deferred sibling).** `_compute_push` compares only to the *immediately-prior* run, so a **flapping**
  fault (present→clears→returns) pages on every return even with a stable key. Lower severity (an intermittent
  fault is arguably worth seeing). Deferred to an "escalate-then-fall-silent over an N-day window" shape; pinned
  by `::test_flapping_fault_does_not_page_on_every_recurrence` marked `xfail(strict=True)` — it flips to a loud
  XPASS the moment the window logic lands.

- **References.** `notes/email_nuisance_suppression_findings.md` (the full finding + evidence),
  `notes/PROSPECTOR_FAULT_SUPPRESSION_README.md` (the RED-first test package), `docs/decisions/2026-07-10-10-email-sender.md`
  (the ratified fix + §8a CONTRACT), smoke-detector brief §2.4 (the GPWS failure this class imports). Sibling
  bugs by class: H1, H4, P1, 9e-ENR (§1.1); C.1, E2, fault-taxonomy (§1.7).
