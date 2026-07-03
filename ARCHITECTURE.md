# Prospector — Architecture

*A map of what's built and why. Read this to catch up; read `docs/prospector-v1-spec-rev6-2026-07-02.md`
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

~3,700 lines of Python, 277 tests (offline). Packages under `prospector/`:

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
| `ingest/edgar.py` | EDGAR client (declared UA, rate-limited, freeze-the-substrate) | `EdgarClient`, `resolve_ticker()` |
| `ingest/prices.py` | Price ingest (Yahoo primary / Stooq fallback), frozen pulls, panel builder | `PriceIngest`, `build_panel()` |
| `identity/resolution.py` | Retry-then-manual resolution machine; two-phase-launch intake + completion | `ResolutionMachine`, `register_launch()`, `launch_lag()` |
| `sensors/xcorr.py` | The excess-correlation pipeline (β-strip → departure z) + the stress gate | `daily_returns`→`departure_z`, `stress_series` |
| `sensors/launch.py` | Launch sensor — new-registration detection (MF-map diff), the consensus clock | `new_registrations()`, `scan()` |
| `sensors/schmitt.py` | Shared hysteresis trigger (no flapping) | `step()`, `state_from_last_event_type()` |
| `backtest/runner.py` | Replays the sensor over history; concept validation; crash falsification | `run()`, `replay()`, `crash_falsification()` |
| `backtest/report.py` | The acceptance-gate artifact (recall/precision/falsification/lag) | `build_report()`, `render_markdown()` |
| `backtest/corroboration.py` | Cross-stream corroboration scoring (sector→keyword) | `score_all()` |
| `backtest/beta_diagnostic.py` | **Read-only** crash-flags diagnostic (never wired to the sensor) | `scoped_beta_slice()`, `two_clock_read()` |
| `cli/main.py` | The `pros` CLI — read surfaces + verdict/identity/backtest | `cli` |

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

Read-only except three writers (verdict, manual identity resolve, store reindex). **No run-now, no
capture trigger, no recompute-on-demand** — cadence is the discipline.

| command | what it does |
|---|---|
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

**Built (committed, 277 tests green):**
- Milestone 1 — vendored primitives, envelope store, WAL registry, fold engine, reactive snapshots,
  S3 sync, config honesty, reindex.
- Milestone 2 — EDGAR client, fund registry (HECO rule), failed-resolution machine.
- Milestone 3 — price ingest, the xcorr sensor + stress gate, the backtest runner + acceptance gate.
- Post-M3 design-thread work — the stress-gate recalibration (0.85 crisis-only), spec rev5's amended
  falsification (reversion criterion), the read-only crash-flags diagnostic (box B), and the
  verdict-disposition vocabulary lock-in.
- Milestone 4 (in progress) — spec rev6 landed as canonical; the **launch sensor**: new-registration
  detection (MF-map diff) + two-phase recording (the consensus clock, `detected_at` preserved).

**Deferred:**
- Milestone 3b — dispersion PIT backtest (waits on delisted-constituent price data).
- Milestone 4 (remaining) — dispersion (shadow-wired) and rebalance sensors; the launch
  **corroboration hook** + holdings-derived concentration — the *defined next slice*, unblocked by
  §4d holdings ingest (see `docs/decisions/2026-07-03-launch-sensor-capture-first.md`), which yields
  the live cross-stream lag.
- Milestone 5 — email (heartbeat + push + dead-man), read-only Streamlit dashboard (incl. the macro
  catalog panel), verdict CLI polish. *(Spec **rev6** — the verdict-vocabulary fold into §5/§8c and the
  box-B record — landed ahead of M5; it is now the canonical spec.)*
- Milestone 6 — discourse capture + budget guard.
- Milestone 7 — infra-as-code + deploy.

---

## 10. Running it

```sh
uv sync                 # set up the environment
uv run pytest -q        # 277 tests, offline
uv run pros --help      # the CLI
uv run pros backtest --from 2019-01-01 --to 2024-12-31 --sweep   # regenerate the acceptance gate
```

The backtest reads price data frozen under `store/ingest/prices/` (gitignored). See
`docs/decisions/` for the reasoning behind every calibration, and `CLAUDE.md` for the repo
constitution and the current CONTRACT amendments.
