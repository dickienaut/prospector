# Project Prospector — Follow-up Review (live / on-cadence)

*Second QA-seat pass by Claude Science, 2026-07-07. Prospector now runs on a cadence: a
`pros run` tick that hits SEC EDGAR + a price API and decides push/heartbeat. This review (a) checks
what happened to the 12 findings from the first pass, and (b) reviews the newly-written code that has
never had fresh eyes — the `runner/`, the live-fetch paths (`prices.py` Tiingo/throttle, `soi.py`
live-fetch), and the `dashboard/`. Every BUG below was reproduced by running the code.*

Snapshot reviewed: `main` as of 2026-07-07 (~7,230 LOC package / 48 test files / ~7,480 test LOC),
persisted as `prospector-snapshot-live-2026-07-07.tar.gz`.

**Headline:** the high-severity findings from the first pass were fixed *properly* (real guards, not
string-match placebos), and the new decision records show the diff-plus-contract loop working — you
actioned P1, I1, B1, B2, H1, S2 by name and even adversarially re-checked my H4 claim and caught that
*I* was slightly wrong about which block the plain REIT header sits under. That's exactly the
cross-context check the three-tool workflow is for. The new code is well-architected (the runner's
soft-fault/dead-man discipline is genuinely good). But going live added three **confirmed BUGs**, one
of which breaks the project's single most load-bearing CONTRACT (read-only firewall), and surfaced a
design gap in the alert cadence that your own smoke-detector brief predicts.

---

## Part A — Status of the 12 prior findings against live code

| # | Finding | Status | Evidence in live code |
|---|---|---|---|
| **H1** | `_parse_weight` ÷100 with no guard (the silent xlsx-class bug) | **FIXED (verified)** | `holdings.py:171` now has a real runtime guard: `total_weight = sum(...)` checked against `_WEIGHT_SUM_MIN/_MAX` with an explicit "never a silent 100x" fault. Exactly the recommended fix. |
| **I1** | launch discards detected `series_id`, re-derives by ticker | **FIXED (verified)** | `register_launch(ticker, name_raw, detected_at, series_id=None)` now threads the detected series and *verifies* it via `resolve_series` instead of `matches[0]` re-derivation. The HECO reused-ticker guarantee is restored. |
| **S1** | fold order-dependent when a row lacks `event_id` | **FIXED** | fold now requires/handles `event_id` deterministically. |
| **S2** | `ts_compact` collapses sub-second instants | **FIXED** | compact form now carries sub-second precision. |
| **B3** | backtest market/SPY excluded only by seed contents | **FIXED** | explicit `!= market` guard now present in `runner.py`. |
| **B1** | prospectus "confirm exists" trust-wide not series-scoped | **PARTIAL (ratified)** | Identity half is now series-scoped (`resolve_series` keys cik+class on the *detected* series). The `prospectus_accession` residual is still registrant-level — but now **openly flagged** in `confirm_prospectus`'s docstring as a documented deferral, not a silent gap. |
| **B2** | only `filings.recent` read, pagination ignored | **PARTIAL (ratified)** | `confirm_prospectus` now returns a distinct `older_filings_unread` reason when `recent` has none but `filings.files[]` is non-empty. Actually *following* the pages is the named deferral. Correct handling of the boundary. |
| **P1** | Stooq Close assumed adjusted, no evidence | **FIXED (structurally)** | `guard_live_source` now **fails closed** on unverified Stooq; Tiingo added as a verified-adjusted source (adjClose confirmed against an NVDA-split test). Best possible resolution. |
| **H2** | SPDR source still `ext="csv"` | **open (cosmetic)** | still `ext="csv"`; harmless (parser sniffs zip magic), only mislabels the frozen fossil. |
| **H4** | plain `REAL ESTATE INVESTMENT TRUSTS` alias missing | **open (re-scoped)** | still absent from config. Your 07-06 SOI work adversarially re-checked my claim and found the plain header sits under CORPORATE BONDS in the real fixtures, so it's only *synthetically* reachable — correctly downgraded. Worth the one-line alias anyway as a cheap safeguard. |
| **S3** | `^…$` regex admits trailing `\n` | **open (low)** | `SERIES_ID_RE`/`_LEAD_RE` still `^…$`. Use `\Z` or `fullmatch`. |
| **report.py** | `acute_crises: []` → IndexError | **open (low)** | a guarded path was added above line 99, but the `[{}])[0]` default-on-missing-key still doesn't cover the empty-list case. |

Net: **5 fully fixed, 3 correctly resolved (P1 structurally, B1/B2 ratified-with-honest-residual), 4
low-severity survivors.** Nothing regressed. The fixes I could execute, I did — they're real.

---

## Part B — New code review (runner / live-fetch / dashboard)

Ten findings: **3 BUG, 2 ASSUMPTION, 5 SMELL.** All three BUGs reproduced by execution.

### Fix-first BUGs

#### N1 · BUG · `dashboard/app.py:61,64,65` · the read-only firewall is violated — the viewer opens the store READ-WRITE
The `# read-only` comment is false at the storage layer. Merely rendering the dashboard:
- `Registry(layout.registry_path())` → `PRAGMA journal_mode=WAL` + `executescript(_DDL)` + `commit()` (`registry.py:63-69`)
- `recent_runs(registry)` → `_ensure_table()` DDL + commit (`runlog.py:44-45`)
- `ResolutionMachine(registry, EventStore, None, None)` → DDL + commit (`resolution.py:97-98`)

So the "read-only §11 firewall" — the project's most load-bearing CONTRACT — **flips the runner's
store into WAL mode, creates `-wal`/`-shm` sidecars, issues CREATE-TABLE DDL, and takes a write lock
that can contend with the live cron runner.** And on a store the operator mounts read-only (the
natural way to *enforce* the firewall), `Registry()` raises `sqlite3.OperationalError: attempt to
write a readonly database` **before** the try/finally, so the page dies with an unhandled exception
and never renders. Verified locally: WAL PRAGMA + DDL + commit on a `chmod 0444` sqlite file raises
that exact error. The `test_dashboard_app.py` smoke uses a *writable* tmp store, so it exercises only
the happy path and can't catch this.
**Fix:** open the viewer's connection immutably —
`sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)` — and add a `readonly=True` Registry
constructor that skips the WAL PRAGMA, the DDL `executescript`, and every commit. This is also the
cheapest way to make the firewall *enforced by the OS*, not just asserted in prose.

#### N2 · BUG · `runner/runner.py` · the tick is NOT idempotent on the same store — a same-day re-run double-writes the append-only record
The runner's docstring claims *"two cold runs over the same store produce identical events."* It
doesn't. `_load_prior_mf_snapshot` selects the prior mf blob from dates **strictly `< today`**
(`d.name < current_date`), so a second `pros run` on the same UTC day sees the *same* prior,
re-detects the identical new `(symbol, series_id)`, and `register_launch` re-emits `launch.unverified`
+ `resolution.failed` with a fresh `uuid4` `event_id` — **nothing dedupes** (Phase one is documented
as "ALWAYS emit"). Reviewer reproduced it: `run_tick` twice on one store takes events 2→4; three runs
→ `launch.unverified ×3`, `resolution_queue.attempts=6`. This corrupts the fossil that launch-lag and
§9f enumeration read from, and re-issues N EDGAR submissions + 12 price fetches per re-run. The
"two cold runs" test dodges it by using **two separate fresh stores each run once** — it never
exercises the same-store re-tick the docstring actually claims.
**Trigger:** cron catch-up after a missed tick; an operator re-running after the soft-fault path
returned a RunLog (the fault path deliberately invites a manual retry); or two cron fires before UTC
midnight.
**Fix:** make the tick idempotent per `(date, logical unit)` — before emitting `launch.unverified`,
check the record for an existing one for that `(series_id, detected_at)`, or gate the launch/config
passes on "not already emitted this date" — and replace the test with a **same-store** double-run that
asserts event equality.

#### N3 · BUG · `ingest/prices.py:103-113,408` · `_tidy`/`build_panel` never dedup dates → non-unique index + a fabricated cross-observation
`build_panel` loudly rejects empty frames and duplicate *tickers*, but silently accepts duplicate
*dates*. Reproduced: a ticker body with two rows for one date yields a non-unique `DatetimeIndex`, and
the outer join broadcasts a co-listed ticker's single value onto **both** duplicate rows — a
fabricated cross-sectional correlation observation, the exact thing `prices.py`'s own §3 docstring
("a filled hole would fabricate a correlation observation") forbids. Every downstream return/xcorr on
that index is then corrupted (`pct_change` straddles the dup) or raises on reindex.
**Trigger:** any source body with two rows for the same calendar date for one ticker — a Tiingo/vendor
duplicate row, or an upstream-merged overlapping re-pull.
**Fix:** `frame = frame.drop_duplicates(subset=["date"], keep="last")` in `_tidy` (matches "latest
supersedes"), or `assert panel.index.is_unique` in `build_panel` so a dup faults as loudly as the
dup-ticker case already does.

### ASSUMPTIONS (input/network beliefs, unvalidated)

#### N4 · ASSUMPTION · `ingest/prices.py:83-85,349-360` · 429 backoff is sized for a per-SECOND cap but Tiingo's binding limit is per-HOUR
The `(1s, 2s)` exponential backoff was copied verbatim from `EdgarClient`, where SEC's limit is
per-second and a short sleep genuinely clears a 429. **Tiingo's cap is 50 requests/hour** (the config
comment says so). On an hourly-cap 429, sleeping 1s then 2s cannot reopen the window — all 3 attempts
fail within ~3s **and each retry spends another of the 50 hourly requests** (12 tickers × 3 = 36 extra
pulls), so the backoff *accelerates* budget exhaustion. 403 is also retried, so an expired token burns
36 useless requests too.
**Fix:** for a per-hour-capped source, honor `Retry-After` when present and don't retry 429 within
seconds (let the ticker soft-fault to the next tick); drop 403 from the retry set for Tiingo (an auth
403 never clears on retry).

#### N5 · ASSUMPTION · `dashboard/app.py:30,56` · config path hardcoded relative, no env override, no guard
`_CONFIG_PATH = Path("config") / "prospector.yaml"` with `load_config()` doing a bare `open()` and no
existence check. The **store** path is `PROSPECTOR_STORE`-overridable and gracefully warns if missing;
the config path is a bare relative literal resolved against CWD. A systemd unit, a container WORKDIR,
or launching from `prospector/dashboard/` makes it unresolvable and the page dies with an unhandled
`FileNotFoundError` instead of the graceful degrade the store path gets.
**Fix:** mirror the store — `Path(os.environ.get("PROSPECTOR_CONFIG", "config/prospector.yaml"))` and
guard with `if not path.is_file(): st.warning(...); return`.

### SMELLs (worth a look, not blocking)

- **N6 · `runner.py:201-224`** — the `_run_sensors` prologue (the `retry_days = int(...)` cast, the
  `ResolutionMachine`/`FundRegistry` construction, the `_build_sector_panel` call) runs **outside any
  per-unit soft-fault boundary**. A non-integer `identity.retry_days` in config, or a registry
  table-init failure, escapes to the single backstop and blinds the *entire* sensor+ingest phase —
  the opposite of the "one fund's 404 never blinds the others" granularity the design claims. Wrap the
  prologue in its own boundary, or validate `retry_days` at config-load. (INFERRED)
- **N7 · `prices.py:322-324,353-360` (mirrored `edgar.py`)** — retry covers **only 429/403**. A
  transient 5xx or a socket read-timeout (routine over 12+ SEC pulls/tick) hits the final `raise` on
  attempt 1, silently dropping that column/filing for the whole tick with no recovery. Add
  `{500,502,503,504}` and connection/timeout errors to the retry set.
- **N8 · `edgar.py:295-300` + `runner.py:519-520`** — `resolve_soi_target`'s bare `except Exception →
  None` makes a genuine **ambiguous-exhibit fault** (>1 candidate `.htm`, which the design says must
  surface for manual review) indistinguishable from a legitimate not-yet, and the runner silently
  `continue`s on every `None` — **no `_system` fault emitted**. So an ambiguous filing never surfaces
  and is silently re-fetched every tick until the 180-day horizon; the bare except also swallows real
  programming errors (a `KeyError` on a submissions-shape change) as not-yets. Your own 07-06 SOI doc
  flags this exact case as "observe it once" — right now you couldn't, because it's silent. Return a
  typed marker and emit an `ingest.soi` fault on ambiguity. (INFERRED)
- **N9 · `runner.py:497-524`** — the SOI corroboration pass has **no cadence gate**: it calls
  `submissions()` + `filing_index()` (2 SEC requests) for *every* unresolved launch on *every* tick
  for up to 180 days. SOIs post ~quarterly, so under a sub-daily cron that's 2N wasted SEC requests
  indefinitely. The docstring names weekly as the intended cadence (an M7 item) — gate on it before
  live cadence scales N.
- **N10 · `dashboard/views.py:65-71`** — an active lead carrying the **INERT `off-thesis-real`**
  verdict still surfaces in the top-of-page "Active leads — the real evidence" panel
  (`active_nonshadow` filters on status+shadow, never verdict; a verdict doesn't change status in the
  fold). A viewer scanning the priority panel can read an off-thesis macro lead as a live actionable
  signal — the "misrepresent a state as a signal" risk. Exclude or visually demote off-thesis-real
  from `rank_active_leads`. (INFERRED — depends on the oracle emitting the verdict without a paired
  `.reverted`.)

---

## Part C — Two things I'd raise beyond the line-level findings

### 1. The recurring-fault push is the nuisance-alarm failure your own brief predicts
`_compute_push` returns `bool(changed_leads) or bool(faults)` — **a fault always pushes, every tick,
with no dedup or suppression** (verified: no dedup/rate-limit/"same-as-last-tick" logic anywhere in
`runner/` or `store/`). Today this is inert because the real sender is deferred (step 4 uses
`NullNotifier`). But when the SMTP sender lands, a *persistent* fault — SEC unreachable for a week, one
malformed fund that faults every tick — will push on **every cadence tick**. That is precisely the
GPWS nuisance-alarm failure mode your thesis-smoke-detector brief §2.4 names: *the alarm that fires on
noise trains you to disable the alarm.* For a builder whose stated primary risk is over-monitoring,
this is the one design gap I'd close **with** the step-4 sender, not after: dedup a fault against the
prior tick's fault set, or escalate (push once on a new fault, then fall silent into the weekly
heartbeat until it clears or changes). The dead-man heartbeat already covers "silence ≠ healthy," so
you don't need every-tick fault pushes to stay safe.

### 2. The runner's docstrings now under-describe the runner (doc drift, inverted)
The `run_tick`/`_run_sensors` docstrings still say "thin spine … launch-recording WIRED; the rest are
SLOTS," but the code now wires **xcorr, SOI-corroboration, and mandate-diff** as well (they're real
`try/except` sensor calls, not slots). This is the *inverse* of the usual drift — the code outran its
own comments — but it's the same hazard your memory-prosthetic archive exists to prevent: a returning
reader (or a fresh implementer in the VSCode seat) who trusts the docstring will mis-model what runs
each tick. Same class as the `ARCHITECTURE.md` header, which still says "~5,300 lines, 470 tests, last
updated after the launch sensor (M4)" and cites rev12 — stale by a milestone and ~1,900 LOC. Cheap
fix, high leverage for the prosthetic: regenerate the runner docstrings and the ARCHITECTURE.md
"what's built" line from the actual wired set each time the runner grows.

*(One small note for the ledger, not a finding: `_load_prior_mf_snapshot` compares date-dir names
lexically — `d.name < current_date`. Correct as long as every dir is `YYYY-MM-DD`; it silently
mis-sorts the day any other naming sneaks in. A one-line `datetime.fromisoformat` parse would make the
ordering intent explicit.)*

---

## Part D — What this pass says about the project

The through-line from the first review holds and strengthened: **the codebase fails loud, and you
close silent failures fast once they're named.** Every high-severity finding from the first pass is
fixed or ratified with an honest residual, and the fixes are real (I ran them). The new runner is the
most correctness-critical code in the project and its core discipline — soft-fault granularity,
config-honesty-first, single-`now` threading, snapshots+push in `finally` — is sound.

The three new BUGs are all "going-live" defects — idempotency, dedup, and a firewall that was asserted
in prose but not enforced in code — and they cluster exactly where the first review predicted the risk
would move: the moment code stops being a pure function and starts *running* on real inputs on a
cadence. That's the right thing for this seat to have caught before the sender goes live. Fix N1 and N2
before the next real tick (the firewall breach and the fossil-corruption are the two that damage the
archive you're staking decades on); N3–N5 before you trust the price panel or ship the dashboard; the
SMELLs as you wire the remaining sensors.

And close the nuisance-push gap (Part C.1) as part of the step-4 sender. It's the one place where the
architecture, left as-is, would actively train you toward the behavior the whole system exists to
prevent.

---

### Appendix — review provenance
Three delegated reviewers (runner core; prices + live fetch; dashboard + identity) over the live
`main` snapshot, each grounded by execution against the real config/fixtures, plus my own read of
`runner.py` and re-verification of all three confirmed BUGs and the prior-findings status table.
Reviewers read the eight new decision records (2026-07-06/07) to check code against *intended*
contract, not just against itself. Findings labelled `confirmed` were reproduced; `inferred` are
reasoned from the code path but not executed end-to-end.
