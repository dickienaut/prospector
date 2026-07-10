# Prospector §10 — fault-suppression volatile-message fix: regression test + reference patch

**For:** the Claude Code (implementation) seat.
**Finding:** `email_nuisance_suppression_findings.md` (the §10 nuisance-alarm suppression is defeated by
volatile fault messages on the live Tiingo path). This package delivers the RED-first regression test and a
reference patch, in the established RED-against-`main` / GREEN-after-fix convention.

Everything below was reproduced end-to-end through the real code; the patch is verified `git apply`-clean
against a pristine `main` checkout and the full suite is green after it.

---

## Files

- **`test_runner_fault_suppression_volatile_message.py`** — the regression test (4 tests). Drop into `tests/`.
- **`prospector_fault_suppression_fix.diff`** — the reference patch (one file: `prospector/runner/runner.py`).
  `git apply prospector_fault_suppression_fix.diff` (or `patch -p1 < …`) from the repo root.
- **`email_nuisance_suppression_findings.md`** — the finding write-up (context; already delivered).

## The bug (one paragraph)

`_compute_push` suppresses a recurring fault by comparing this tick's `_fault_signature` —
`frozenset((subsystem, message))`, **message-exact** — to the prior run's. The `ingest.prices` HTTP fault
message embeds the fetch URL, and the Tiingo URL carries `?startDate=…&endDate=…` (Yahoo: `period1`/`period2`
epochs); both derive from the run date, so a **persistent identical failure** (a lapsed Tiingo sub → HTTP
403) renders a *different* message every tick → a different signature → it **pages every day** — the GPWS
"cried wolf" failure §10's suppression exists to prevent, on the live path (`prices.primary = tiingo`).

## What each test asserts

1. **`test_persistent_price_fault_suppresses_across_ticks`** (unit, over `_compute_push`) — the same lapsed-sub
   403 on two consecutive days must page once then suppress. **RED** today (moving dates read as a new fault).
2. **`test_a_changed_price_status_still_pages`** (unit, guard) — a 403→500 transition on the same ticker must
   ALWAYS page. **GREEN today and must stay GREEN** — it's the guard against an over-coarse fix that would
   swallow a genuinely changed fault.
3. **`test_persistent_price_fault_pages_once_over_real_ticks`** (integration, over the real `run_tick`) — three
   real ticks with a failing price fetch page once, not three times. **RED** today.
4. **`test_flapping_fault_does_not_page_on_every_recurrence`** (E2, secondary) — a fault that clears then
   returns pages on every recurrence. Marked **`xfail(strict=True)`** — it documents a deferred design choice
   (an "escalate-then-fall-silent over an N-day window" shape) and flips to a loud XPASS the moment that lands.
   Same pattern as the N9 cadence-gate test.

The test builds each fault dict via the **real `_emit_fault`** (never hand-rolled), and is **fix-agnostic**:
it passes the same stable key the fixed runner passes and falls back to the plain call on the pre-fix
signature, so it expresses intent against both.

**Why the existing coverage missed it:** `test_runner.py::test_compute_push_is_pinned_to_state_change_or_fault`
uses a hardcoded stable `"boom"` message; `test_runner_notify.py` drives the EDGAR `mf_tickers` fault whose
URL carries no dates. Neither exercises a price fault, whose URL moves — the same green-on-synthetic /
broken-on-real shape as the H1/H4 misses.

## The fix (reference patch — `prospector/runner/runner.py` only)

Separate the **suppression key** from the **display message**, so the fossil keeps the full URL for
forensics while suppression keys on the stable identity of "the same failure":

1. **`_emit_fault` gains an optional `key: str | None = None`.** When set it's stored on the fault dict (and
   the fossil payload); when `None` behavior is unchanged (the many stable-message faults are unaffected).
2. **`_fault_signature` prefers the key:** `(subsystem, key or message)`. A fault with no key still signatures
   on its message — fully backward-compatible.
3. **The two URL-bearing fault sites pass a stable key** `f"{ticker}:{status}"` (both `PriceIngestError` and
   `EdgarError` carry `.status`): the sector-panel pull (`_build_sector_panel`) and the per-basket dispersion
   pull (`_run_dispersion`). The message keeps the full URL; only the suppression key is stabilized.

Deliberately **not** coarsening the signature to subsystem-only — that would swallow a genuinely changed
fault (test 2 guards this). And this fix does **not** address E2 (flapping); that's the deferred window-based
design the xfail documents.

## Verification (reproduced, not asserted)

- New test file: **RED** against `main` (2 failed + 1 guard-pass + 1 xfail), **GREEN** after the patch
  (3 passed + 1 xfail).
- Full suite delta from the patch is exactly those 2 tests: unfixed `main` (with the new file) = **541 passed,
  2 failed, 1 skipped, 2 xfailed**; patched = **543 passed, 1 skipped, 2 xfailed**. Nothing else moved.
- `git apply --check` is clean against a pristine `main` checkout; the freshly-applied tree + the new test =
  **543 passed**.

*(Skip is `test_s3_sync.py` on the optional `moto` package; the 2 xfailed are the pre-existing N9 cadence gate
and this package's E2 flapping case.)*
