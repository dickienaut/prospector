# Live-cadence QA fixes (N1–N10 + cheap sweeps)

*Decision record, 2026-07-08. Implements Claude Science's 2026-07-07 follow-up review via the design
thread's ordered plan (`docs/2026-07-07-live-cadence-qa-fixes.md`; evidence:
`docs/prospector_followup_review_2026-07-07.md`). Science shipped 10 regression-test files (behaviour-
asserting, fix-agnostic) + a verified reference patch; this arc implements the fixes, treating that patch
as a blueprint, not a prescription. Governing frame: convert each prose invariant to mechanism, and land
the test that ATTEMPTS the violation.*

**Governing rule for how-far-past-minimal (design-thread, this session):** does the extra scope close a
gap on something LIVE, or build for a case that isn't live yet? Live → close now; not-live → defer, named.

## What was fixed

- **N1 · dashboard read-only firewall** — `Registry(readonly=True)` opens `mode=ro` and skips the WAL
  PRAGMA/DDL/commit; `runlog._ensure_table` and `ResolutionMachine.__init__` skip their DDL when readonly;
  `app.py` opens read-only. **`mode=ro`, not `immutable=1`** — deliberately: `mode=ro` is WAL-readable, so
  the live viewer sees the runner's latest un-checkpointed writes; `immutable=1` would silently miss them
  (a stale viewer). Proven by a **freshness test** (`test_registry.py`): a `mode=ro` Registry re-queried
  after another connection commits a WAL write sees it. *Deferred (not-live):* serving a WAL store from
  read-only **media** also needs a checkpoint-out-of-WAL step — documented here; the runner-side
  `wal_checkpoint(TRUNCATE)` waits for M7/deploy (never touch the live write path for a not-live case).

- **N2 · non-idempotent tick** — the ALWAYS-emit launch path is now idempotent per **fund identity**.
  **Strengthened past the reference patch (correctness):** the patch keyed dedup on `(ticker,
  detected_at)`, but `register_launch(detected_at=now)` moves `now` run-to-run, so it only dedups under a
  fixed clock (the test's) — a real same-day cron catch-up / operator re-run hours later still
  double-writes. We add `series_id` to the `launch.unverified` payload and key the dedup on it (the stable
  HECO identity); ticker is the fallback for a ticker-only caller. A **moving-clock test** proves it where
  `(ticker, detected_at)` would fail. Scope stays the launch/two-phase path (config-honesty + xcorr spawns
  are already state-change-gated). *Note:* xcorr **ticks** are a separate per-cadence stream that
  legitimately accrues per run — out of N2 scope per the ratified plan; if strict tick idempotency is ever
  wanted, that's a separate follow-up.

- **N3 · fabricated cross-observation** — `_tidy` dedupes dates (`keep="last"`, append-only re-pull) AND
  `build_panel` raises loudly on a non-unique index (backstop for any frame not built through `_tidy`).

- **N4 + N7 · retry set corrected for a per-hour source, transient/transport covered** — prices
  `_RETRY_STATUSES = (429, 500, 502, 503, 504)` (drop 403 — auth never clears); `_Source.hourly_cap` (tiingo
  only) makes a 429 **fail fast** (a sub-second backoff can't reopen an hourly 50/hr window); a
  transport/timeout error (status None) is retried like a 5xx. **Mirrored into `edgar.py`** (Full-doc-intent
  — submissions/SOI are fetched every tick with the identical gap): add 5xx to its retry set + an
  `httpx.HTTPError`→status-None catch + status-None retry (keep SEC's per-second 429/403).

- **N8 · silent ambiguous-exhibit** — `classify_soi_target` returns `(target, reason)` ∈
  {resolved, not_yet, ambiguous, error}; `resolve_soi_target` is a thin wrapper. The runner emits a
  `soi.corroboration.{ambiguous,error}` fault (surface once for manual review) while a genuine not-yet
  stays silent; a swallowed exception now surfaces as `error` instead of masquerading as a not-yet.

- **N5 · config path** — `PROSPECTOR_CONFIG` env-override + existence-guard `st.warning`, mirroring the
  store path. **N10 · inert off-thesis-real** — `rank_active_leads` filters `verdict == "off-thesis-real"`
  at the panel boundary (it stays in `macro_catalog`).

- **N6 · prologue fault boundary** — `retry_days = int(...)` wrapped: a bad value is a scoped
  `config.identity.retry_days` fault + default fallback, so the sensor phase still runs (launch recording
  unaffected).

- **Tier-4 sweeps** — H2 SPDR fossil ext `csv`→`xlsx` (parse content-detects, so harmless); S3
  `SERIES_ID_RE`/`CLASS_ID_RE`/`_LEAD_RE` use `\Z` not `$` (reject a trailing newline); report.py
  `acute_crises` empty-list guard (`or [{}]`, not a get-default); `_load_prior_mf_snapshot` parses the date
  (`date.fromisoformat`) rather than lexical-compare; the stale `run_tick`/`_run_sensors` "thin spine …
  launch only" docstrings corrected to the wired xcorr/mandate/SOI set. **H4** (plain-REIT alias) was
  already handled by the existing `gics_industry_alias` entry + `test_soi_config.py`.

## Deferred / separate (named)

- **N9** SOI cadence gate → M7 (0 cost today; its test stays `xfail(strict=True)` — flips to a loud XPASS
  when the M7 gate lands).
- **N1 runner checkpoint-truncate** → M7/deploy (documented precondition only).
- **C.1** recurring-fault push (nuisance-alarm) → a §10 acceptance criterion for the sender (push once on a
  *new* fault, then heartbeat) — no code today (NullNotifier). Verified inert: `pros run` with faults=0
  pushed=False.
- **C.2 full doc pass** (ARCHITECTURE §2/§9 + spec §5 + three-register cleanup) → separate pass; only the
  immediately-misleading inline docstrings were corrected here.

## Verification

Full suite **499 passed, 1 xfailed** (the 10 QA files + extra violation-tests for the beyond-diff parts:
prices/edgar transport-timeout retry, the `build_panel` backstop, the moving-clock N2, the N1 freshness).
End-to-end: `pros run` twice the same day → faults=0, prices flow through Tiingo (retry-set change didn't
regress the live path), launch idempotency holds (no double-write), and a `mode=ro` viewer reads the store
and sees the freshest run. The reference patch (`tests/reference_fixes_all_N1-N10.diff`) is a superseded
scratch artifact, left untracked.
