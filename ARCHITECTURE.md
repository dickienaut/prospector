# Prospector — Architecture

*A map of what's built and why. Read this to catch up; read `docs/prospector-v1-spec-rev14-2026-07-08.md`
for the canonical "what to build," `docs/project-prospector-state-of-project-rev5-2026-07-08.md` for
the status/roadmap source of truth, and `docs/decisions/` for the "why we changed our minds." Last
updated after the **M5 runner arc + going-live (N1–N10) hardening**: the runner is built and the
system is **live and firing** — a real `pros run` fired 5 xcorr leads on the SPDR grid — but it is
still **n=1 and unfalsified** (falsifiability is demonstrated; a rate and profitability are not).*

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

~7,400 lines of Python, 499 tests (offline). Packages under `prospector/`:

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
| `ingest/edgar.py` | EDGAR client (declared UA, rate-limited, freeze-the-substrate); §2 resolution keyed on ticker OR the detected series (I1); SOI-target resolution (§9b) | `EdgarClient` (`filing_index()`), `resolve_ticker()`, `resolve_series()`, `confirm_prospectus()`, `latest_soi()`, `resolve_soi_document()`, `resolve_soi_target()`, `latest_prospectus()`, `prospectus_history()` |
| `ingest/prices.py` | Price ingest (**Tiingo primary** → `adjClose`, since Yahoo's endpoint is bot-blocked by TLS fingerprint; yahoo/stooq registered for a data-honest flip-back), frozen pulls, panel builder; rate-limited + 429/403 backoff (`prices.max_requests_per_sec`); token via `Authorization` header behind a `_Secret` redaction holder (never the URL/fossil); P1 fail-closed guard verified against the NVDA 10:1 split | `PriceIngest`, `parse_tiingo()`, `build_panel()`, `guard_live_source()` |
| `ingest/holdings.py` | Holdings ingest (§4d keystone) — SPDR daily file (**xlsx**, real SSGA format) → 90%-weight membership, frozen | `HoldingsIngest`, `weight_covering_members()`, `parse_spdr_holdings()`, `parse_nport_holdings()` (labeled §3b stub), `MembershipSnapshot` |
| `ingest/prospectus.py` | Prospectus fetch/freeze + mandate extraction (§4d) — bs4 → text, strategy section, diff | `ProspectusIngest`, `extract_mandate()`, `diff_mandate()` |
| `ingest/soi.py` | SOI fetch-freeze (read side) + GICS-industry-grouped sector derivation (§4c resolver) — fund-block isolation → `INDUSTRY — N.N%` parse → industry→sector rollup (+ `gics_industry_alias` rendering variants) → reconcile-or-fault | `SoiIngest`, `extract_soi_sectors()`, `dominant_sectors()` |
| `identity/resolution.py` | Retry-then-manual resolution machine; two-phase-launch intake + completion | `ResolutionMachine`, `register_launch()`, `launch_lag()` |
| `sensors/xcorr.py` | The excess-correlation pipeline (β-strip → departure z) + the stress gate; **`scan()`** — the runner's LIVE per-tick driver (state from the record §9f, stress gate, spawn/tick/revert) | `daily_returns`→`departure_z`, `stress_series`, `scan()` |
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
| `runner/runner.py` | The M5 **cadence driver** (§9) — CONTRACT run-order, config-honesty-first, soft-fault granularity, reactive snapshot + `state_changed`-pinned push. WIRED: §9a sector-prices panel ingest (`_build_sector_panel`, P1 guard), **§4a xcorr — the PRIMARY live spawner** (`_run_xcorr`; universe→series_id from the mf map, §9f state, LIVE/paging/ceiling-counting), launch-recording (§4c), the §9d deferred SOI-corroboration retry, the §4d mandate-diff (§9c frozen-prior), **§4b dispersion — the 2nd live spawner, in SHADOW** (`_run_dispersion`, §9e; membership from the live SPDR feed, shadow-gated push). SLOT: rebalance (§4d holdings-diff) | `run_tick()` |
| `runner/deps.py` / `runner/notify.py` / `runner/runlog.py` | Injected seam bundle; the `Notifier` transport (`NullNotifier` until the M5 email slice); per-tick run-log (§9g, its own `runs` table, telemetry — never a lead event) | `RunnerDeps`, `NullNotifier`, `RunLog`, `write_run_log()` |
| `cli/main.py` | The `pros` CLI — read surfaces + verdict/identity/backtest + the `run` cadence entrypoint | `cli` |
| `dashboard/views.py` / `dashboard/app.py` | The §11 **read-only** Streamlit dashboard — pure, tested view-models (folds of the record) + a thin `st.*` render shell. No recompute/autorefresh/run-now. Streamlit is an OPTIONAL extra (`uv sync --extra dashboard`); `views` is streamlit-free | `rank_active_leads()`, `dormant_pile()`, `heartbeat()`, `main()` |

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
it yet. **I1**: the *detected* series id is threaded through `register_launch` → `resolve_series`, so
identity keys on the detected series, never a ticker re-derive (the HECO rule, at the launch path).

The **corroboration hook is built** (it was the M4 capstone, not a future slice):
`sensors/launch_corroboration.py` derives a launch's concentration sectors from its **first
holdings**, not from prospectus prose (ground truth over prose — the same look-through-is-truth logic
as the HECO rule), then a **both-sides sector-set overlap** with a live lead's baskets **accretes**
the launch onto that lead (never spawns one — no ceiling slot), making the **signed** cross-stream lag
measurable. Because the real SSGA daily file carries no `Sector` column for an active fund, the blank
case is resolved by the **SOI resolver** (`ingest/soi.py` + `sensors/soi.py`), which parses the fund's
GICS-industry-grouped Schedule of Investments and rolls industry→sector through a frozen table, then
routes through the same shared `route_corroboration` tail; extraction-unreliable → `fault`, never a
wrong sector set. See `docs/decisions/2026-07-03-launch-corroboration-existence-proof.md`,
`2026-07-04-soi-derived-sector-concentration.md`, and `2026-07-06-identity-integrity.md`.

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

**Built (committed, 499 tests green, all offline) — milestones 1–4 + the SOI resolver + the M5 runner (live):**
- Milestone 1 — vendored primitives, envelope store, WAL registry, fold engine, reactive snapshots,
  S3 sync, config honesty, reindex.
- Milestone 2 — EDGAR client, fund registry (HECO rule), failed-resolution machine.
- Milestone 3 — price ingest, the xcorr sensor + stress gate, the backtest runner + acceptance gate.
- Post-M3 design-thread work — the stress-gate recalibration (0.85 crisis-only), spec rev5's amended
  falsification (reversion criterion), the read-only crash-flags diagnostic (box B), and the
  verdict-disposition vocabulary lock-in.
- Milestone 4 (**sensors complete**) — spec **rev14** canonical; the **launch sensor** (recording,
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
- **The M5 runner — built and live** (`prospector/runner/`, `pros run`) — the §9 cadence driver in the
  CONTRACT run order (config-honesty-first → ingest → sensors → identity retries → capture no-op →
  reactive snapshots → `state_changed`-pinned push), **no intelligence**, stateless between ticks (§9f
  state recovered from the fossil record — no side cache), soft-fault-vs-fatal exception granularity, and
  a dead-man that still pushes on a fatal (snapshots + push run in `finally`). Wired onto it, in order:
  - **§9a sector-prices panel** (`_build_sector_panel`) + the **P1 guard** (`guard_live_source` fails a
    source *closed* unless its adjusted-close is verified — an unadjusted close silently corrupts every
    return across a split, the base of the sensor stack).
  - The **prices vertical — Tiingo is now primary** (CRSP split+dividend-adjusted `adjClose`, verified
    against the NVDA-2024 10:1 split; token via `TIINGO_API_TOKEN` env behind a `_Secret` redaction holder
    on the Authorization header — never the URL/fossil; source-specific throttle/backoff). **Yahoo was
    demoted** after it turned out to **bot-challenge non-browser clients on a TLS fingerprint** (not a
    rate-limit — Chrome 200s where httpx/curl 429); **Stooq is P1-guarded-closed**. See
    `2026-07-07-tiingo-price-source.md`, `-prices-throttle-backoff.md`, `2026-07-06-prices-ingest-and-p1.md`.
  - **§4a xcorr wired LIVE — the primary spawner** (`xcorr.scan`, `_run_xcorr`): a spawn is LIVE
    (`shadow=false`) → it **pages and counts toward the §8a ceiling** via `active_nonshadow`; the universe
    tickers→series-ids resolve from *this tick's mf map* (`_universe_series_ids`, NOT the registry — the
    seed universe is never registered, so reading the registry would leave xcorr inert); the stress gate
    freezes a crisis-day entry to a `_system` `xcorr.departure`, never a spawn. See `2026-07-07-xcorr-live.md`.
  - **§4b dispersion wired LIVE in SHADOW — the 2nd spawner** (`dispersion.scan`, `_run_dispersion`, §9e):
    per-basket membership from the **live SPDR holdings feed** (never the empty registry), a constituent
    price panel keyed by member **CUSIP** (the ticker↔CUSIP bridge is the SPDR file's own Ticker column —
    parse now keeps the ticker as a display-only lookup attribute; re-keyed to CUSIP before `build_panel`),
    P1-guarded like the sector panel. A spawn is `shadow=true` → it starts the 90-day burn-in and is
    **excluded from paging/ceiling/corroboration** (`active_nonshadow`) **and from the push trigger** —
    a §9e fix: `_compute_push` now gates on a *non-shadow* change, closing a latent §8a-vs-§4b collision
    dispersion was the first spawner to make live. Generous payload captured. **Constituent-symbol
    resolution (QA fix, `priceable_members`):** the pull now excludes FOREIGN (non-USD) and cash/placeholder
    lines at the membership boundary — a real SSGA file's `ENR` (Siemens Energy, EUR) collides with
    NYSE:Energizer, so a bare pull would silently return the wrong series (HECO one level down); excluded
    weight is a reported coverage gap and `coverage_actual` reflects the *priced* set. The **widened**
    SPDR→Tiingo symbol primary-source gate (dual-class + foreign/cash on real XLF/XLC/XLY) is pending the
    desktop live run. See `2026-07-09-dispersion-vertical-9e.md`, `2026-07-10-9e-constituent-symbol-resolution.md`.
  - **launch-recording** (§4c, §9f frozen mf prior); the **§9d deferred SOI-corroboration retry**
    (`_run_soi_corroboration` — folds `sectors_unresolved` launches, `resolve_soi_target` fetches, and
    `soi.scan` reaches back preserving `detected_at`=T2, bounded by `retry_horizon_days`); the **§4d
    mandate-diff** on cadence (`_run_mandate`, **§9c frozen-prior invariant** — diffs the last *frozen*
    prospectus blob, never the registry accession field an intra-run identity pass may advance); the
    **identity-integrity fixes** (I1 series-threading, B1/B2, `ambiguous_symbol` fault); **SOI-fetch**
    (§9b — `resolve_soi_target`, form-priority NPORT-EX, refuse-to-guess on ambiguity; a `gics_industry_alias`
    map keeps the 74-row canonical GICS table pure). See `2026-07-06-{m5-runner-skeleton,soi-fetch,mandate-9c,soi-corroboration-retry-9d,identity-integrity}.md`.
  - The **read-only Streamlit dashboard** (§11) — pure, tested view-models (`dashboard/views.py`,
    streamlit-free, no writes/recompute) + a thin `st.*` shell (`app.py`, an OPTIONAL extra
    `uv sync --extra dashboard`); read-only **enforced at the substrate** (`mode=ro`), no
    recompute/autorefresh/run-now; the firewall grep guards it. See `2026-07-07-dashboard-11.md`.
- **Live + hardened.** A real `pros run` fired **5 live xcorr leads** on the SPDR grid (XLU×XLV, XLRE×XLY,
  XLC×XLF, XLC×XLV, XLRE×XLV — the correlated structure collapses these into ~2–3 independent events, XLV
  recurring). The **N1–N10** going-live QA fix batch then closed the first wave of bugs — the read-only
  firewall (now `mode=ro` mechanism, not prose), tick idempotency (stable series-id dedup, moving-clock-
  proof), a duplicate-date correlation-fabrication guard, source-specific retry sets, the ambiguous-exhibit
  fault surfacing, dashboard honesty — **each landing with the violation-test that would have caught it.**
  See `docs/decisions/2026-07-08-live-cadence-qa-fixes.md`.

**Deferred (named, with reason):**
- **§9e follow-ons** — the dispersion spawner itself is **built and shadow-wired** (above), and the QA
  constituent-symbol fix (foreign/cash/placeholder exclusion, CUSIP-keyed pull, honest coverage) is **built**;
  what remains is the **live `pros run` on real SPDR data + the widened SPDR→Tiingo symbol primary-source
  gate** — confirm on real XLF/XLC/XLY that dual-class (BRK.B / GOOG·GOOGL / FOX·FOXA) AND foreign/cash lines
  are handled, and that a clean-looking colliding symbol like `ENR` does not silently return a US security's
  series (the synthetic fixtures don't carry either case, so a green suite does not verify the live mapping);
  **also confirm the live sector-grid firings — e.g. XLI — are computed on clean US-equity constituents.**
  **Foreign CUSIP/SEDOL→US-symbol resolution (Option 3) and surfacing large per-basket coverage gaps are
  deferred, named** (not-yet-live foreign scope; needs a primary-source mapping). Broader holdings-intake
  coverage (per-issuer / NPORT-P) remains a rate-widening, not an unblock. The **"prove a spawner fires on
  real seed data"** rule got its first post-xcorr test here. See `2026-07-09-dispersion-vertical-9e.md`,
  `2026-07-10-9e-constituent-symbol-resolution.md`, `docs/decisions/2026-07-03-dispersion-shadow-first.md`.
- **§10 — the email sender.** Weekly heartbeat/dead-man + state-change push, with **nuisance-alarm
  suppression** (push once on a *new* fault, then fall to the weekly heartbeat until it clears/changes) —
  the one place the architecture as-is would train the operator to ignore the alarm. Currently `NullNotifier`.
- **Rebalance runner wiring** — the accretion sensor (`sensors/rebalance.py`) is built, but its per-tick
  wiring is a SLOT; it can now reuse the **§9e holdings/constituent vertical** (built) for its holdings-diff.
- **Milestone 3b** — dispersion **PIT backtest** + the **NPORT-P parser** + delisted-price coverage —
  data-availability-gated (survivorship-clean historical holdings + delisted-constituent prices, *worse*
  for the proto-cluster layer, where winners vanish from the survivor set exactly when their thesis was
  real). `parse_nport_holdings` is a deliberately thin, labeled §3b stub, not an unfinished edge;
  dispersion runs shadow / live burn-in meanwhile.
- **Broader holdings-intake coverage** (secondary) — per-issuer holdings parsers / NPORT-P look-through;
  the SOI path already resolves the active-fund sector case, so this turns the live cross-stream lag from
  an *existence proof* into a *representative rate* rather than unblocking it. Intake was deliberately not
  widened inside the corroboration slice.
- **Milestone 6** — discourse capture + budget guard. **Milestone 7** — infra-as-code + **scheduled**
  deploy (where `pros run` stops being a manual invocation); M7 also owns the SOI-corroboration **cadence
  gate** (0 cost today — the dormant pile is empty) and the read-only-media **WAL-checkpoint**.
- **v2 (banked, not built)** — the **proto-cluster / pseudo-ETF** layer (spec Appendix B): price-only,
  observation-only new-category detection below the corpus (the canary is a *cluster*, never a single
  name, and never the trade — its substrate already accrues via the generous dispersion payload, so v1's
  only action is to keep capturing) and the discourse-interpretation program. See
  `docs/decisions/2026-07-03-dispersion-payload-generous.md`.

**The load-bearing honesty line:** everything under **Built** is *built and running*, not *validated*. The
firing is **n=1**, the false-discovery rate is **unmeasured**, and the edge question is unanswered — the
runner exists to convert existence proofs into *rates*, and that work has barely started. **Falsifiability
is demonstrated; profitability is not. "Live" is not "proven."**

---

## 10. Running it

```sh
uv sync                 # set up the environment
uv run pytest -q        # 499 tests, offline
uv run pros --help      # the CLI
uv run pros run         # one cadence tick (§9): ingest → sensors → snapshots → push-on-state-change
uv run pros backtest --from 2019-01-01 --to 2024-12-31 --sweep   # regenerate the acceptance gate

uv sync --extra dashboard                          # add the (optional) Streamlit dependency
uv run streamlit run prospector/dashboard/app.py   # the §11 read-only dashboard
```

The backtest reads price data frozen under `store/ingest/prices/` (gitignored). See
`docs/decisions/` for the reasoning behind every calibration, and `CLAUDE.md` for the repo
constitution and the current CONTRACT amendments.
