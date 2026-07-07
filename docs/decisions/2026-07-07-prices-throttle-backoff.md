# PriceIngest gets a rate cap + 429/403 backoff — mirroring EdgarClient's fair-access discipline

*Decision record, 2026-07-07. Hardens `ingest/prices.py`'s live fetch after a real `pros run` failure.
DEFAULT-level (config `prices.max_requests_per_sec`), not a CONTRACT amendment — so it lives here + in
ARCHITECTURE.md, with no `CLAUDE.md` pointer.*

## What happened

The first live `pros run` after the M5 spawner arc landed produced **12 faults**, all identical:

```
ingest.prices :: {TICKER}: GET https://query1.finance.yahoo.com/v8/finance/chart/{TICKER}
                 ?period1=1709856000&period2=1783468800&interval=1d -> HTTP 429
```

— every sector ETF + SPY, i.e. the whole correlation panel. The runner itself behaved **correctly**:
each ticker soft-faulted (§9g), the run continued, `xcorr` skipped honestly (no panel to score), and
`pushed=True` (a fault always pages — the dead-man, §10). No logic bug. The failure was entirely in the
price *fetch*.

## Two root causes, two layers

1. **Environment (not fixed in code):** the machine's traffic was egressing through **Apple Private
   Relay**, so Yahoo saw a *shared* relay IP carrying many users' aggregate load — a far lower effective
   per-IP ceiling. This is what a mere 12-request burst doesn't explain but the diagnosis confirmed: a
   single *spaced* request still 429'd, and **both** `query1` and `query2` were blocked (IP-wide). The
   endpoint worked fine on 2026-07-02 (frozen bodies on disk prove it) — a cleaner relay exit that day.
   The fix for *today* is turning Private Relay off (owner action); the durable fix is moving scheduled
   fetching off the daily-driver laptop to a deploy target (an M7 concern).

2. **Code (fixed here):** `PriceIngest` fired all 12 requests **back-to-back with no rate limiter and no
   429/403 backoff**, and faulted the whole panel on the first 429. That fragility is independent of the
   relay — on a bigger universe, a busy day, or even its own IP, an un-throttled burst trips Yahoo's
   limit, and with no backoff a *transient* 429 nukes the run. `EdgarClient` had already solved this
   exact problem for SEC (`_throttle` + a `_get` backoff loop, `_RETRY_STATUSES = (429, 403)`,
   `_MAX_ATTEMPTS = 3`). The asymmetry — one ingest client polite, the other not — was the real defect.

## The change

`PriceIngest` now carries the **same** fair-access discipline as `EdgarClient`:

- A min-interval **throttle** (`_throttle`, verbatim from `EdgarClient`) spacing request starts
  `>= 1/max_per_sec` apart, driven by config `prices.max_requests_per_sec` (**DEFAULT 2** — Yahoo
  publishes no limit and 429s aggressively; over-/slow-pulling is cheap here, so we pick a polite cap).
- A **`_fetch_with_retry`** wrapper: 3 attempts, exponential backoff (1s, 2s) on 429/403, immediate raise
  on any other status. Wired into `pull` in place of the bare `self._fetch`.

**Naming:** the throttle clock/sleep are injected as `monotonic`/`sleep` (defaults
`time.monotonic`/`time.sleep`), deliberately **distinct** from the existing `clock` — which is the
ISO-date partitioner for frozen-pull paths, not a wall clock. The two roles must never conflate.

**Freeze-before-parse preserved (§3):** unlike `EdgarClient._get` (which persists *inside* the fetch),
the price freeze stays in `pull`, *after* `_fetch_with_retry` returns. So a fetch that never succeeds
raises and freezes **nothing** — fetch-fail stays distinct from parse-fail (a corrupt body still lands
on disk; a 429-exhausted fetch does not). A dedicated test pins this
(`test_pull_persistent_429_raises_after_capped_retries_and_freezes_nothing`).

Only one site does a live price `.pull()` — the runner's sector panel (`runner.py`), fed by the
`PriceIngest` built in `cli/main.py`'s `pros run` path — so that is the only construction wired to the
config rate. The other two `PriceIngest` sites (`cli/main.py` diagnostics, `backtest/runner.py`) call
`load_frozen` only (no network) and need no rate.

## Status & scope

- **DEFAULT, not CONTRACT.** `prices.max_requests_per_sec` is a config knob, freely tunable. This
  changes robustness, not any spec-load-bearing behavior.
- **What it does NOT fix:** a hard shared-IP block. Throttle + backoff stop us from *being* the trigger
  and recover a *transient* 429; they cannot out-wait an IP that is already in Yahoo's penalty box. That
  is why disabling Private Relay is the parallel, necessary step.
- **Named next lever (deferred, not built):** if 429s persist on the un-relayed IP, Yahoo's chart API
  increasingly wants a **session-cookie + crumb** handshake (fetch a consent cookie, read a crumb,
  include it). Bigger, Yahoo-specific — out of scope here.

## Tests

`tests/test_prices.py` gains a fair-access block mirroring `tests/test_edgar_client.py`: throttle spacing,
no-sleep-when-already-spaced, 429-then-succeeds (+ body frozen), persistent-429 caps at 3 and freezes
nothing, 404 raises immediately (no retry), and non-positive `max_per_sec` rejected at construction. The
existing runner `_deps` helpers inject a no-op `sleep` so the now-throttled multi-ticker panels don't
really block. Suite: 449 green.
