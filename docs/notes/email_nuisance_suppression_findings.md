# §10 email sender — the nuisance-alarm suppression is defeated by volatile fault messages, on the live Tiingo path

**Reviewed:** `main` as of 2026-07-10 (rev6 — §10 sender built, merged, and fired), fresh-eyes QA read.
**Seat:** Claude Science (QA) → for the Claude Code (implementation) seat.
**Severity:** **HIGH** — it silently reopens the exact gap §10 was built to close, on the live-primary
(`prices.primary = tiingo`) path, for the exact failure mode rev6 names (“closes the paid-Tiingo-sub
lapse-risk”). Reproduced end-to-end through the real code; not inferred.

---

## TL;DR

`_compute_push` (runner.py) suppresses a recurring fault by comparing this tick's **`_fault_signature`**
to the immediately-prior run's. The signature is **message-exact**: `frozenset((subsystem, message))`.
That is correct *only if a persisting fault produces the same message every tick*. It does not. The
live-primary price path builds its fault message from the **fetch URL**, and the Tiingo URL carries
`?startDate=…&endDate=…` — **both dates move every tick**. So a persistent identical failure (e.g. a
lapsed Tiingo subscription → HTTP 403) produces a *different* message every day → a *different* signature
→ `_compute_push` treats it as NEW/CHANGED → **it pages every single day.** That is the GPWS
“pull-up that cried wolf” failure the smoke-detector brief §2.4 names, and it is precisely the case the
sender slice was written to prevent.

The suppression *logic* is sound; its *comparand* is wrong for the messages the live code actually emits.

---

## Evidence (reproduced end-to-end through the real code, no network)

Driving the **real** `prices._tiingo_url`, the **real** error text from `prices.py:344`
(`f"GET {url} -> HTTP {resp.status_code}"`), the **real** fault-message wrapper from `runner.py:439`
(`f"{t}: {e}"`), and the **real** `_fault_signature` / `_compute_push`, for two consecutive daily ticks
with an *identical persistent* 403:

```
Tick 1 fault message:
  NVDA: GET https://api.tiingo.com/tiingo/daily/NVDA/prices?startDate=2024-03-11&endDate=2026-07-10&format=json -> HTTP 403
Tick 2 fault message (SAME failure, next day):
  NVDA: GET https://api.tiingo.com/tiingo/daily/NVDA/prices?startDate=2024-03-12&endDate=2026-07-11&format=json -> HTTP 403

signatures equal?  False
=> _compute_push treats tick 2 as a NEW/CHANGED fault: True    # pushes every day
```

`prices.primary` is **`tiingo`** in the shipped config, so this is the live path, not a hypothetical one.
`end = now[:10]` and `start = required_pull_start(now[:10], cfg)` in `_build_sector_panel` (runner.py:428–429)
both derive from the run date, so the moving dates are structural, not incidental.

### Blast radius — which faults are volatile (defeat suppression) vs stable (suppress correctly)

**Volatile → pages every tick (bug):**
- **`ingest.prices` HTTP errors** — `prices.py:342, 344, 383` embed `GET {url} …`; the Tiingo URL carries
  `startDate`/`endDate`, the Yahoo URL carries `period1`/`period2` **epochs** (`_yahoo_url`, prices.py:202)
  — both move every tick. This is the **live sector-panel pull** (`_build_sector_panel`) and the
  **dispersion constituent pull** (`_build_constituent_panel`), i.e. the paths that fault on a
  lapsed/expired key, a Tiingo outage, or an entitlement change.
- Any fault whose message wraps an exception (`f"…: {e}"`) whose text carries a per-tick token (a URL, a
  timestamp, a row count, a rate-limit reset). `edgar.py` submissions faults (`detail=f"…: {e}"`) are in
  the same class where the underlying error carries a URL.

**Stable → suppresses correctly (works as designed):**
- `ingest.prices` empty-frame: `f"{t}: empty price frame (no rows)"` — stable.
- P1 guard: parameterized on `source`+`flag` only — stable.
- `TIINGO_API_TOKEN unset — refusing tiingo fetch` — stable.
- SOI-corroboration reason faults (`soi.corroboration.{reason}`, runner.py:796) — series_id/cik/reason,
  all stable across ticks — stable.

So the mechanism is half-working: the stable-message faults suppress; the URL-bearing faults on the live
price path don't. The most operationally-likely persistent fault (a dead price key) is in the broken half.

### Why the existing test didn't catch it

`tests/test_runner.py:321–329` tests `_compute_push` with a **hardcoded stable message**
(`boom = [{"subsystem": "ingest.mf_tickers", "message": "boom"}]`): `_compute_push({}, boom, boom) is False`
passes because `"boom" == "boom"`. The test proves the *logic* is correct **given a stable message** — it
never exercises a real fault message with volatile content, so the gap is invisible to the suite. This is
the same shape as the H1/H4 misses: green against a synthetic fixture, wrong against real data.

---

## A second, lower-severity finding while here (E2 — flapping fault)

`_compute_push` compares only to the **immediately-prior** run. A fault that *flaps* (present → clears →
returns) pages on **every** return, even with a perfectly stable message, because each return compares
against a prior tick where it was absent:

```
t1 new fault            -> pushes (True)
t2 fault clears         -> no push (False), rides the heartbeat
t3 SAME fault returns   -> pushes again (True)   # prior tick had no fault
```

An intermittently-failing source (a flaky 5xx, a network timeout that clears and recurs) therefore pages
on each recurrence. This is **less severe** than E1 — a genuinely intermittent fault is arguably worth
seeing — but it is not the "push once, then fall to the heartbeat while it persists" cadence the docstring
describes, and a noisy flapping source can still train the operator to ignore the alarm. The
"escalate-then-fall-silent over a window" shape (rather than a one-tick-back comparison) would cover both
E1 and E2; a one-tick memory covers neither cleanly.

---

## Suggested handling (a design decision — options, not a prescription)

The tension is real and worth stating: the **fossil message should keep the full URL** (forensics — you
want to see exactly what failed), but the **suppression key should be stable** across ticks for "the same
failure." So the fix is to *separate the suppression key from the display message*, not to strip the URL
from the message. Options, roughly in order of how clean they are:

1. **Give a fault a stable `key` (or `signature`) field at emit time, and signature on that.** For the
   HTTP faults the natural key is `(subsystem, status_code)` — `PriceIngestError`/`EdgarError` already
   carry `status`. `_emit_fault` would accept an optional `key=` (defaulting to the message, preserving
   today's behavior for stable-message faults), and the price/edgar sites pass `key=f"{subsystem}:{status}"`
   or similar. The message keeps the full URL for the fossil; the *signature* keys on the stable part.
   This is additive and localized.
2. **Normalize the message inside `_fault_signature`** (strip URLs / ISO dates / epochs before hashing).
   Works, but it's regex whack-a-mole — a new volatile token in a new subsystem silently reopens the gap.
   I'd avoid this: it's the fragile version of option 1.
3. **Escalate-then-fall-silent over a window** (covers E2 too): suppress if the same key fired within the
   last *N* days (not just the immediately-prior run), so a flapping fault suppresses across the window and
   a persistent one pages once then rides the heartbeat. Combine with option 1's stable key.

I would **not** coarsen the signature to subsystem-only — that would swallow a genuinely *changed* fault
in the same subsystem, which is the one thing the build note's "never swallow a changed fault" line
correctly forbids.

---

## Test target (RED against current `main`, GREEN after a fix — the house convention)

A `test_runner_fault_suppression_volatile_message.py` that drives the **real** fault path (no network),
matching the existing `_compute_push` unit-test style but with a *real* message rather than `"boom"`:

- **`test_persistent_price_fault_suppresses_across_ticks`** — build the ingest.prices fault message the way
  the runner does, for two consecutive dates (real `_tiingo_url` + real `f"{t}: {e}"`); assert
  `_compute_push` returns **False** on the second tick (same failure, same key). RED today (the moving
  dates make it True). Fix-agnostic: satisfied by any of the options above.
- **`test_changed_price_fault_still_pages`** — a 403 → 500 transition on the same ticker must still page
  (guards against an over-coarse fix that swallows a real change). GREEN today and must stay GREEN.
- **`test_flapping_fault_does_not_page_on_every_recurrence`** (E2) — present/clear/present with a stable
  message; assert the return does not page within the window. RED today. Mark `xfail(strict=True)` if E2 is
  deferred as a design choice, so it flips to XPASS the moment the window logic lands (same pattern as the
  N9 cadence-gate test).

I can draft these as runnable RED tests plus a reference patch (option 1 + option 3) against `main`, the
same RED/GREEN + reference-fix shape as the N1–N10 set — say the word and I'll produce them.

---

## Note for the record

This is the third time the project's characteristic pattern has surfaced — code that reads correctly,
passes its tests, and breaks on the real substrate — and the first time it's on the alarm layer itself.
The suppression design is genuinely good (the shadow-push gate, the "never swallow a changed fault" line,
the fossil-as-comparand discipline are all right); it was validated against a stable synthetic message and
shipped before meeting a real persistent fault. The live Tiingo path is where it will meet one first.
