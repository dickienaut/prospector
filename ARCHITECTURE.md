# Prospector — Architecture

*A map of what's built and why. Read this to catch up; read `docs/prospector-v1-spec-rev12-2026-07-03.md`
for the canonical "what to build," and `docs/decisions/` for the "why we changed our minds." Last
updated after the launch sensor's detection + two-phase recording slice (milestone 4).*

---

## 1. What Prospector is

Prospector is the **offensive twin of the thesis smoke detector**: it watches the ETF universe for
**structural novelty** and proposes **reading, never orders**. The owner invests on a **17+ year
horizon** in emerging technology, and that horizon is the load-bearing design parameter — on a
timescale this long with feedback this sparse, *the archive is the intelligence*. So v1 is a
deterministic, append-only **fossil record** with a few honest sensors, and **no LLM interpretation
anywhere in the data path**.

Three ideas carry the whole system:

1. **Append-only fossil record.** Nothing under `events/` is ever edited or deleted. Corrections are
   new events. A changed mind is a new event that supersedes the old one, never an edit. This is what
   lets the archive be trusted over decades.
2. **A lead *is* the fold over its event stream.** There are no mutable "lead" rows. A lead's state
   (active/reverted, verdict, latest z, …) is *computed* by folding its events in timestamp order.
   Same events → same state, always (property-tested).
3. **Machines write facts; humans judge.** Deterministic sensors append observations; a human appends
   verdicts. Nothing keys on a verdict to drive action — the tool notices, the person decides.

The firewall is absolute: no code path reads the detector's bucket or `portfolio.yaml`, and no code
path places, sizes, or recommends a trade.

---

## 2. Module map

~5,300 lines of Python, 380 tests (offline). Packages under `prospector/`:

| Package / module | Responsibility | Key entry points |
|---|---|---|
| `store/envelope.py` | The frozen 5-field event envelope + validation | `validate()`, `Envelope`, `canonical_json()` |
| `store/registry.py` | WAL-mode SQLite index over the store (envelope + JSON payload columns) | `Registry` |
| `store/event_store.py` | Append-only writer: atomic file + registry row; **no update/delete** | `EventStore.append()`, `read_lead()` |
| `store/layout.py` | The §7 path tree; structural backtest/live separation | `StoreLayout`, `backtest_run_root()` |
| `store/snapshots.py`→`fold/snapshots.py` | Reactive snapshot policy + writer (fail-loud on divergence) | `should_snapshot()`, `write_snapshot()` |
| `store/s3_sync.py` | Fire-and-forget S3 mirror; `.backup`-only registry upload | `S3Sync.sync()` |
| `store/reindex.py` | Rebuild the registry from the `events/`+`snapshots/` trees | `rebuild_registry()` |
| `store/fund_registry.py` | Series-ID-keyed fund entries; the HECO rule enforced at the write path | `FundRegistry.upsert()` |
| `primitives/atomic.py` | tmp→fsync→rename atomic write + SHA-256 (vendored, hardened) | `write_atomic()`, `write_json_atomic()` |
| `primitives/sqlite_backup.py` | Consistent WAL-safe SQLite snapshot (native `.backup`) | `backup_sqlite()` |
| `fold/fold.py` | The pure fold: state, verdict supersession, unknown-type handling | `fold()`, `active_nonshadow()`, `VERDICT_VOCAB` |
| `config.py` | Load YAML → (config, canonical hash); `config.changed` emission | `load_config()`, `check_config_honesty()` |
| `ingest/edgar.py` | EDGAR client (declared UA, rate-limited, freeze-the-substrate); §2 resolution keyed on ticker OR the detected series (I1); SOI-target resolution (§9b) | `EdgarClient` (`filing_index()`), `resolve_ticker()`, `resolve_series()`, `confirm_prospectus()`, `latest_soi()`, `resolve_soi_document()`, `resolve_soi_target()` |
| `ingest/prices.py` | Price ingest (Yahoo primary / Stooq fallback), frozen pulls, panel builder | `PriceIngest`, `build_panel()` |
| `ingest/holdings.py` | Holdings ingest (§4d keystone) — SPDR daily CSV → 90%-weight membership, frozen | `HoldingsIngest`, `weight_covering_members()` |
| `ingest/prospectus.py` | Prospectus fetch/freeze + mandate extraction (§4d) — bs4 → text, strategy section, diff | `ProspectusIngest`, `extract_mandate()`, `diff_mandate()` |
| `ingest/soi.py` | SOI fetch-freeze (read side) + GICS-industry-grouped sector derivation (§4c resolver) — fund-block isolation → `INDUSTRY — N.N%` parse → industry→sector rollup (+ `gics_industry_alias` rendering variants) → reconcile-or-fault | `SoiIngest`, `extract_soi_sectors()`, `dominant_sectors()` |
| `identity/resolution.py` | Retry-then-manual resolution machine; two-phase-launch intake + completion | `ResolutionMachine`, `register_launch()`, `launch_lag()` |
| `sensors/xcorr.py` | The excess-correlation pipeline (β-strip → departure z) + the stress gate | `daily_returns`→`departure_z`, `stress_series` |
| `sensors/dispersion.py` | Intra-basket fracture (§4b) — constituent corr → spectral bipartition → Q departure z; shadow-wired, generous payload | `dispersion_q_series`, `scan()` |
| `sensors/launch.py` | Launch sensor — new-registration detection (MF-map diff), the consensus clock | `new_registrations()`, `scan()` |
| `sensors/rebalance.py` | Rebalance accretion (§4d) — holdings-diff → `rebalance` onto live leads; forward-hash routing | `diff_holdings()`, `watching_leads()`, `scan()` |
| `sensors/mandate.py` | Mandate-diff accretion (§4d) — new prospectus → strategy-section diff → `mandate.changed` / `fault` | `scan()` |
| `sensors/launch_corroboration.py` | Launch corroboration (§4c) — holdings→sectors → overlap → accrete + signed lag; shared routing tail | `sector_concentration()`, `corroborate()`, `route_corroboration()`, `cross_stream_lag()` |
| `sensors/soi.py` | SOI corroboration (§4c resolver of `sectors_unresolved`) — SOI→sectors → threshold → shared route; fault-on-unreliable; deferred reach-back (T2 preserved) | `scan()` |
| `sensors/schmitt.py` | Shared hysteresis trigger (no flapping) | `step()`, `state_from_last_event_type()` |
| `backtest/runner.py` | Replays the sensor over history; concept validation; crash falsification | `run()`, `replay()`, `crash_falsification()` |
| `backtest/report.py` | The acceptance-gate artifact (recall/precision/falsification/lag) | `build_report()`, `render_markdown()` |
| `backtest/corroboration.py` | Cross-stream corroboration scoring (sector→keyword) | `score_all()` |
| `backtest/beta_diagnostic.py` | **Read-only** crash-flags diagnostic (never wired to the sensor) | `scoped_beta_slice()`, `two_clock_read()` |
| `runner/runner.py` | The M5 **cadence driver** (§9) — CONTRACT run-order, config-honesty-first, soft-fault granularity, reactive snapshot + `state_changed`-pinned push; launch-recording (§4c), the §9d deferred SOI-corroboration retry pass, and the §4d mandate-diff pass (§9c frozen-prior) wired; xcorr/dispersion/rebalance + §9e are spec-cited SLOTS | `run_tick()` |
| `runner/deps.py` / `runner/notify.py` / `runner/runlog.py` | Injected seam bundle; the `Notifier` transport (`NullNotifier` until the M5 email slice); per-tick run-log (§9g, its own `runs` table, telemetry — never a lead event) | `RunnerDeps`, `NullNotifier`, `RunLog`, `write_run_log()` |
| `cli/main.py` | The `pros` CLI — read surfaces + verdict/identity/backtest + the `run` cadence entrypoint | `cli` |

Vendoring note: `primitives/` and the registry structure are ported from the sibling repo's
`ltee_archive/` — *disciplines and query shapes only*, with the trading ontology stripped and the
schema inverted to envelope + JSON payload. Provenance headers are on each vendored file.

---

## 3. The data model (the spine)

Every observation is a **five-field envelope** (frozen — CONTRACT):

```json
{ "ts": "2026-07-14T13:00:00Z", "lead": "<lead_id>", "type": "<string>", "payload": { }, "schema": 1 }
```

- `type` is an **open vocabulary** — never an enum. An unforeseen event type is the whole premise;
  v2's writers plug into exactly this gap with no migration.
- `payload` is a JSON object. This is the critical inversion from the sibling repo: instead of wide
  typed metric columns, the registry stores the payload as a **JSON blob column**, indexed on
  `(lead, ts, type)`. New event types need no schema change.

**Write path** (`EventStore.append`): validate → write the JSON object atomically
(`tmp → fsync → rename`, SHA-256, directory fsync — a torn write is impossible) → insert a registry
row (path + sha + payload). There is **no update and no delete method** — append-only by construction.

**Read path** = fold. `fold(events)` sorts by `(ts, event_id)`, dedupes, and reduces to a state dict:

```
{ status, shadow, verdict, verdict_history, spawned_at, last_event, event_count, latest_z,
  stress_departures, capture_inventory, corroborations, unknown_types, faults, anomalies }
```

Unrecognized event types are counted and raw-rendered (never crash — the day-one unknown-type panel
contract). Verdict supersession follows a `superseded_by` chain; the current verdict is the chain
head, and a broken chain resolves deterministically with an `anomalies` entry rather than a crash.

**The S3/local layout** (`§7`):

```
events/{lead}/{ts}_{type}_{uuid}.json      append-only fossil record — live observations ONLY
snapshots/{lead}/{ts}.json                 materialized folds (reactive cadence)
ingest/prices|edgar|holdings/...           frozen raw substrate (pull-once-freeze)
ingest/prospectus/{series_id}/{accession}/ frozen prospectus HTML — blob per filing (mandate-diff)
registry/funds/{series_id}.json            versioned fund registry objects
registry.sqlite                            the WAL index — uploaded only via .backup snapshot
backtest/run_{stamp}/...                   synthetic history — NEVER under events/ (structural guard)
```

Durability disciplines vendored verbatim: atomic writes, SHA per object, and **never raw-copy a
live WAL database** — the registry is snapshotted with the native `.backup` API before any upload.

---

## 4. The sensor and the stress gate (`sensors/xcorr.py`)

The excess-correlation sensor is the milestone-3 heart. Each stage is a pure function over pandas:

```
prices ──daily_returns──▶ returns
       ──rolling_beta(252, shift t-1)──▶ per-fund β vs SPY
       ──residuals──▶ r_i − β_i·r_mkt          (the market strip)
       ──pairwise_rolling_corr(63)──▶ residual correlation per sector pair
       ──fisher_z──▶ variance-stabilised
       ──departure_z(252, baseline ends t-1)──▶ z = departure from the pair's own trailing norm
```

A pair spawns a lead when its departure z crosses the **Schmitt trigger** (entry z≥2.5, exit z≤1.0 —
hysteresis, no flapping). The **stress gate** (a separate market-wide signal) freezes spawning during
acute crises so a crash can't flood the oracle.

**The stress gate is the most important calibration story in the project** (see
`docs/decisions/2026-07-02-stress-gate-recalibration.md`). It was recalibrated from an absolute 0.65
to an absolute **0.85**, crisis-only, because the milestone-3 β-strip diagnostic *proved* the β-strip
is the primary market-factor defense (residual mean correlation −0.035 even in the March-2020 crash).
A **baseline-relative** form was tested exhaustively and rejected: market-wide correlation is a
**fragility gauge with an intrinsic scale** — 0.95 *is* a stressed market — so normalizing it away
destroys the signal. The level ages, so the backtest reports a calm-regime-p95 headroom monitor;
aging is fixed by human recalibration, **never** a rolling percentile.

---

## 5. The backtest and the acceptance gate (`backtest/`)

`pros backtest --from … --to … [--sweep]` replays the sensor over frozen prices into a **backtest-only
store** (own root + registry — synthetic history can never touch `events/`), and writes one
acceptance artifact with four sections (spec §10 test 5):

- **(a) Recall** — the XLK×XLU (Tech×Utilities) firing timeline. *Confirmed:* the AI-power linkage
  forms 2023-01-25; with the recalibrated gate it fires **~19 months before** the TEKX ETF launched
  (+593-day cross-stream lag).
- **(b) Precision** — the full 55-pair firing list, each auto-scored by cross-stream corroboration
  (sector→keyword match against a curated launch table). Floor-limited but honest.
- **(c) Falsification (March 2020)** — amended by rev5 into three criteria: (i) β-strip clean
  in-crash, (ii) the gate fires on the acute crisis but not the whole window, (iii) **every
  crash-window spawn must revert** within 8 weeks (no durable false leads). (iii) is the falsifiable
  core.
- **β-strip health** and **stress-gate diagnostics** run *before* any threshold tuning — the
  diagnosis that decides whether you're calibrating a sound measure or a broken one.

`beta_diagnostic.py` is a separate **read-only** tool (never imported by the sensor) that classified
the milestone-3 crash-window flags: a scoped faster-β slice ruled out a stale-β artifact (a *second*
independent β-strip confirmation), classifying them as a real 2020 macro/sector regime. See
`docs/decisions/2026-07-02-crash-flags-guidance-rev2.md`.

---

## 6. Identity (`ingest/edgar.py`, `identity/resolution.py`, `store/fund_registry.py`)

Every fund keys on its **SEC series ID** (`S######`) — the HECO rule, enforced at the fund-registry
write path (a bare ticker is rejected). Tickers are display-only. Resolution:
ticker → EDGAR series/class lookup → confirm a prospectus filing → registry entry. Failures never
drop silently: they emit `resolution.failed`, auto-retry daily for `retry_days`, then enter a
manual-resolution queue. The two-phase launch preserves the original `detected_at` so cross-stream
lag math is never skewed by a slow resolution.

The **launch sensor** (`sensors/launch.py`, milestone 4) is the consensus clock: it detects new
US-listed ETFs by diffing two frozen `company_tickers_mf.json` snapshots (a new `(symbol, seriesId)`
pair is a new registration), then records each two-phase via `ResolutionMachine.register_launch` —
`launch.unverified` (timestamp nailed *before* resolution, because a launch datum can't be
backfilled) → resolve → immediate `launch` on `_system`, or the retry queue if EDGAR hasn't indexed
it yet. This is the **capture** half; the **corroboration hook** that routes a launch onto
overlapping live leads (yielding the live cross-stream lag) is the *defined next slice* — it needs a
launch's concentration industries, which will be derived from its first holdings once §4d's holdings
ingest lands (ground truth over prose — the same look-through-is-truth logic as the HECO rule). See
`docs/decisions/2026-07-03-launch-sensor-capture-first.md`.

---

## 7. The `pros` CLI (`cli/main.py`)

Read-only except four writers (verdict, manual identity resolve, store reindex, and the `run`
cadence tick). **No run-now, no capture trigger, no recompute-on-demand** — cadence is the discipline;
`pros run` is a *cadence entrypoint* (one invocation = one tick, cron-invoked), not an on-demand
recompute (its only option is `--store`).

| command | what it does |
|---|---|
| `pros run` | Execute ONE cadence tick (§9): config honesty → ingest → sensors → identity retries → snapshots → push-on-state-change. The scheduled entrypoint (cron invokes it; scheduling is M7) |
| `pros lead list` / `lead show <id>` | Read-only lead views (folds of the record) |
| `pros verdict <id> <disposition> [-m note]` | Append a verdict (see below); a changed mind supersedes |
| `pros identity resolve <ticker> --series-id S######` | Manual resolution-queue path (EDGAR-verified) |
| `pros identity queue` | The manual-resolution queue |
| `pros store reindex` | Rebuild the index from the fossil record (repair, not run-now) |
| `pros backtest --from … --to …` | Calibration + the acceptance gate (writes only under `backtest/`) |

**Verdict vocabulary — four values, three live meanings** (`VERDICT_VOCAB`; guidance rev2 §8.4):
`yes` (promoted, on-thesis) · `watch` (on-thesis but *unproven*, live) · `off-thesis-real` (real but
off-thesis macro/sector regime — catalogued as context, inert) · `noise` (not real). `off-thesis-real`
and `watch` are deliberately distinct — never file a live candidate as macro. Verdict is display-only;
nothing keys on it to drive action, so "context, never a trigger" holds by construction.

---

## 8. Conventions & disciplines

- **CONTRACT vs DEFAULT.** Items marked CONTRACT in `docs/` change only via the design thread; DEFAULTs
  are config in `config/prospector.yaml`. Design-thread-authorized amendments live in `docs/decisions/`
  and are pointed to from `CLAUDE.md`.
- **Anti-fitting.** Thresholds are set on principle and frozen, then observed — never tuned until a
  known case appears. The stress-gate level and the crash-revert window were both chosen on the
  crisis/own-merits side, with recall-independence checks proving they aren't case-fit.
- **Tests are offline.** A conftest network guard fails any test that opens a real socket; recorded
  fixtures live in `tests/fixtures/`. The fold is property-tested (hypothesis) for order-invariance
  and determinism.
- **Config honesty.** Every run hashes the config; a change emits `config.changed` before any sensor
  runs, so folds stay interpretable across threshold changes.
- **Document as we build** (standing practice): this file and `docs/decisions/` are kept current as
  the system changes — every load-bearing decision leaves a written trace next to a `config.changed`
  or commit.

---

## 9. Status — built vs deferred

**Built (committed, 380 tests green):**
- Milestone 1 — vendored primitives, envelope store, WAL registry, fold engine, reactive snapshots,
  S3 sync, config honesty, reindex.
- Milestone 2 — EDGAR client, fund registry (HECO rule), failed-resolution machine.
- Milestone 3 — price ingest, the xcorr sensor + stress gate, the backtest runner + acceptance gate.
- Post-M3 design-thread work — the stress-gate recalibration (0.85 crisis-only), spec rev5's amended
  falsification (reversion criterion), the read-only crash-flags diagnostic (box B), and the
  verdict-disposition vocabulary lock-in.
- Milestone 4 (**sensors complete**) — spec **rev12** canonical; the **launch sensor** (recording,
  the consensus clock, `detected_at` preserved); **holdings ingest** (§4d keystone; now reads real
  SSGA **xlsx** — pinned `openpyxl`); the **dispersion sensor** (§4b, shadow-wired, generous payload);
  the **rebalance sensor** (§4d accretion, forward-hash routing); the **mandate-diff sensor** (§4d,
  targeted strategy-section diff, pinned `beautifulsoup4`); and the **launch corroboration hook** (§4c
  capstone) — holdings-derived sectors → both-sides overlap → accrete → the **signed** cross-stream lag.
  Findings, recorded at full/deflated strength: **the live lag is bounded by holdings coverage, not the
  hook** (existence proof, not a rate); and from **primary-source review** of the real TEKX file — the
  real SSGA daily file is **xlsx** and for an active fund **carries no `Sector` column** ("-"), so
  file-sector-derived concentration is empty and real TEKX resolves **`sectors_unresolved` → dormant**;
  the +593 was reachable only on the *synthetic* fixture. Fixtures are now recorded-real-with-provenance
  or declared-synthetic. See `docs/decisions/2026-07-04-real-holdings-xlsx-and-blank-sectors.md` and
  `…-existence-proof.md`.
- **SOI-derived sector concentration (§4c resolver of `sectors_unresolved`)** — the "ticker→GICS
  classifier" unblock above was a convergent-prior error: the primary source already publishes the
  grouping. `ingest/soi.py` + `sensors/soi.py` parse the fund's GICS-industry-grouped Schedule of
  Investments (`INDUSTRY — N.N%`), roll industry→sector through a **frozen `gics_industry_sector` table**,
  threshold with the frozen `sector_min_weight`, and route through the shared `route_corroboration` (the
  holdings and SOI sources now feed one overlap/accrete/lag path). Extraction-unreliable → `fault`, never
  a wrong sector set. **On real TEKX NPORT-EX the +593 now attaches on primary-source data** (Jul-2025
  clears {Financials, Industrials, IT, Utilities}); Jan-2026 stays dormant (Utilities 6.4% < floor,
  threshold frozen — anti-fitting). See `docs/decisions/2026-07-04-soi-derived-sector-concentration.md`.
- **Milestone 5 — the runner skeleton (the thin spine, build-order step 1)** — `prospector/runner/` +
  `pros run`: the §9 cadence driver. It sequences the deterministic sensors in the CONTRACT run order
  (config-honesty-first → ingest → sensors → identity retries → capture no-op → reactive snapshots →
  push), adds **no intelligence**, and is stateless between ticks (between-tick state recovered from the
  fossil record, §9f — no side cache). Proven end to end through **one** vertical, launch-recording
  (§4c: mf-tickers diff → `launch.scan` → identity retries), with the run-log (§9g), soft-fault-vs-fatal
  exception granularity, and the `fold.state_changed`-pinned push (§10) all landed and offline-tested
  (fixture clock, two-cold-runs determinism). The two Claude-Science runner-blockers are in: **H1**
  (holdings weight-units sanity) and **S2** (sub-second-lossless `ts_compact`). Spec:
  `docs/prospector-m5-runner-spec-2026-07-05.md`; build record + follow-on sequencing:
  `docs/decisions/2026-07-06-m5-runner-skeleton.md`.
- **Milestone 5 — SOI-fetch (build-order step 2)** — the fetch-on-cadence half of the SOI resolver, in
  the ingest layer: `SOI_FORMS` + `latest_soi(submissions)` (form-priority: NPORT-EX over N-CSR/N-CSRS,
  the reader's verified artifact) + `EdgarClient.filing_index()` + `resolve_soi_document()` (the
  non-primary exhibit, refuse-to-guess on ambiguity) composed into `resolve_soi_target()` — the
  coordinates the step-3 retry loop hands to `sensors/soi.scan`'s `fetch_body` seam. **H4** folded in: a
  `gics_industry_alias` config map registers the plain `REAL ESTATE INVESTMENT TRUSTS` header (DFIN's
  collapsed equity-REIT rendering → Real Estate), keeping the 74-row canonical table pure; the
  `_build_table` docstring's inaccurate aliasing claim is corrected. All offline (synthetic
  submissions/index fixtures; **drop-and-freeze for tests, fetch-on-cadence for the runner — never
  conflated**). See `docs/decisions/2026-07-06-soi-fetch.md`.

**Deferred:**
- Milestone 3b — dispersion **PIT backtest** + NPORT-P parser + delisted-price coverage measurement
  (waits on delisted-constituent price data; ships live burn-in only for now — see
  `docs/decisions/2026-07-03-dispersion-shadow-first.md`).
- **Holdings-intake coverage** (secondary) — per-issuer holdings parsers / NPORT-P look-through, which
  turns the live cross-stream lag from an *existence proof* into a *representative rate*. Intake was
  deliberately not widened inside the corroboration slice.
- Milestone 5 — the remaining build-order steps on top of the landed runner skeleton + SOI-fetch + §9d +
  §9c (above): **step 3 remainder** the dispersion shadow clock (§9e — pulls in `PriceIngest`, since
  dispersion consumes a price panel; those prices then also serve xcorr §4a); then the **read-only
  Streamlit** dashboard (§11, incl. the macro-catalog + launch + coverage panels — the current priority);
  **email** (§10 heartbeat/push/dead-man + the dormant-pile coverage report) follows as a nice-to-have.
  **xcorr (§4a) — the primary lead spawner — is the big step-4 slot**: it's when the runner starts
  spawning its main leads and the dormant pile fills; it pairs with the dashboard (firings + a surface to
  see them) as the "runner earns its keep" moment.
- **Milestone 5 — §4d mandate-diff on cadence + §9c frozen-prior (landed 2026-07-06)** — the runner runs
  the mandate-diff each tick (`_run_mandate`): for each registered fund, `latest_prospectus` (current) +
  the last **frozen** prospectus as the prior (`_last_frozen_prospectus` via `prospectus_history` +
  `has_frozen` — **never** the registry `prospectus_accession` field, which an intra-run identity pass may
  advance, §9c), then `mandate.scan` (freeze → diff strategy section → `mandate.changed` silent / `fault`).
  Real execution from day one (baseline, then diffs across cadences); self-sufficient (records on
  `_system` with no lead). Proven by the invariant gate (the diff uses the frozen prior, not the advanced
  field). See `docs/decisions/2026-07-06-mandate-9c.md`.
- **Milestone 5 — §9d deferred SOI-corroboration retry loop (landed 2026-07-06)** — the runner now drives
  the deferred SOI resolution each tick (`_run_soi_corroboration`): `pending_soi_resolution` folds the
  `sectors_unresolved` launches from the events (§9f, never a side table), `resolve_soi_target` (step 2)
  fetches each, and `sensors/soi.scan` reaches back preserving `detected_at` as **T2**. Bounded by
  `corroboration.retry_horizon_days` (365, DEFAULT); a not-yet (`resolve_soi_target` → None) stays
  `sectors_unresolved`, re-attempted; per-launch failures are soft faults. Live yield is bounded (input
  from the unwired holdings-corroboration SLOT; overlap from the xcorr/dispersion SLOTs; anchor =
  `entry.name`, needs a stable stem) — mechanism landed and tested (the three-property fires-not-called
  gate). See `docs/decisions/2026-07-06-soi-corroboration-retry-9d.md`.
- **Milestone 5 — identity-integrity fixes I1/B1/B2 (landed 2026-07-06)** — the runner-path prerequisites
  hardening the HECO reused-ticker guarantee before live cadence. **I1**: `sensors/launch.scan` threads
  the *detected* series id into `register_launch` → `resolve_series` (+ the `detected_series_id` retry-
  queue column), so identity keys on the detected series, never a `matches[0]` re-derive by ticker; plus
  the `ambiguous_symbol` fault in `resolve_ticker`. **B1** (owner-ratified scope): resolve-by-series fixes
  the identity half; the residual trust-wide `prospectus_accession` is deferred (needs filing-header parse
  — the mandate-diff gate — or a §2 `FundEntry` field). **B2**: `confirm_prospectus` flags
  `older_filings_unread` when `filings.files[]` pages exist, instead of a silent `no_prospectus`; full
  pagination deferred. See `docs/decisions/2026-07-06-identity-integrity.md`. (**H4** landed with step 2.)
- **v2 (banked, not built)** — the **proto-cluster / pseudo-ETF** layer (spec rev8 Appendix B): a
  price-only, observation-only re-read of dispersion history (the canary is a cluster, never a single
  name, and never the trade). v1's only action is the generous dispersion payload that banks its
  substrate (see `docs/decisions/2026-07-03-dispersion-payload-generous.md`).
- Milestone 6 — discourse capture + budget guard.
- Milestone 7 — infra-as-code + deploy.

---

## 10. Running it

```sh
uv sync                 # set up the environment
uv run pytest -q        # 367 tests, offline
uv run pros --help      # the CLI
uv run pros backtest --from 2019-01-01 --to 2024-12-31 --sweep   # regenerate the acceptance gate
```

The backtest reads price data frozen under `store/ingest/prices/` (gitignored). See
`docs/decisions/` for the reasoning behind every calibration, and `CLAUDE.md` for the repo
constitution and the current CONTRACT amendments.
