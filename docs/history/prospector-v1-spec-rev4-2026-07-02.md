# Project Prospector — v1 Build Specification (rev 4)

*2026-07-02, rev 4 — supersedes rev 3. Rev 4 folds in the milestone-3 gate outcome and the stress-gate recalibration decided in the design thread: the market-stress gate (§4a) is frozen to an **absolute** crisis level of **0.85**, with the empirical finding that baseline-relative fails on this statistic recorded as its durable rationale, and an aging-drift watch-item attached. This is a CONTRACT-default change, authorized from the design thread. No other decision changed. Written to be read cold by the implementer (Claude Code) in a **fresh repo**. Where this spec says DEFAULT, the value is config — change freely. Where it says CONTRACT, do not deviate without returning to the design thread.*

**Rev 4 changes (milestone-3 outcome + stress-gate recalibration):**
- **§4a stress gate frozen — absolute level 0.85, crisis-only.** Milestone 3 proved the β-strip removes the market factor cleanly even in the March-2020 crash, which demotes the stress gate to a narrow crisis-only job (crash-onset β-staleness + liquidity dislocations). The gate form is **absolute, not baseline-relative** — baseline-relative was tested exhaustively (windows 5/10/15 × baselines 63/126/252) and fails structurally, because market-wide mean pairwise correlation is a fragility gauge with an intrinsic scale (the level *is* the signal), not a scale-free quantity. Level **0.85** chosen because onset latency is the binding constraint (~5-day onset; 0.90 too slow, 0.80 catches the 2022 sustained regime the demotion deliberately leaves open). Recall-independent (the real 2023 signal at market-corr 0.667 stays ungated at every candidate level). Config default changed from `stress_corr_threshold: 0.65`.
- **Aging watch-item added (§4a, standing review).** Absolute levels age; calm p95 ~0.81 vs gate 0.85 ≈ 0.04 headroom. Standing human recalibration if the margin compresses — explicitly **not** a rolling percentile (which would reintroduce the baseline-relative failure).
- **§0 premise updated** to the owner's own framing.
- Milestone 3 verdict recorded: recall confirmed (XLK×XLU forms 2023-01-25, z 2.52), β-strip clean (residual ≈0 incl. March-2020 0.88→−0.035), precision floor-limited-but-honest (2/98, corroboration set holds only three 2024 launches). The gate did its job — proved the instrument before four more milestones got built on it, and surfaced exactly one dial.

**Rev 3 changes (fold-in of the LTEE / Prophit code review):**
- **§1 vendoring made concrete.** The primitives to vendor are `ltee_archive/`'s *disciplines and query shapes* — atomic-write+SHA+sidecar, WAL-mode SQLite registry, metadata/blob split, safe-SQLite-backup, forensic trajectory queries — under the Prospector's envelope schema. The trading ontology and all `models/` machinery do not cross. Full map in **Appendix A**.
- **§5 / §7 store implementation specified.** Local WAL-mode SQLite registry (queryable index) + object store (durable blobs); events stored as the envelope with a JSON `payload` column indexed on `(lead, ts, type)` — deliberately **not** Prophit's wide typed-metric columns. Atomic tmp-then-rename + SHA per write; `.backup`-API snapshot before upload.
- **Verdict succession chain** lifted from `apex_history.superseded_by` (§5).
- **Adaptive snapshot policy resolved** (was decisions-review open-Q C): adopt LTEE's three-tier density *shape*, invert the trigger from scheduled (curriculum epochs) to **lead-reactive** (§5).
- **OOD confirmation** (§4a, Appendix A): the OOD *concept* is the shared heart of both twins; the sliced-Wasserstein *machinery* must not cross — the §4a z-score is the right-capacity form at 55-pair scale.
- **Horizon premise** stated explicitly in §0.
- New **Appendix A**: the LTEE archive port map.

---

## §0 — Purpose and v1 scope

**Premise (the governing constraint).** The owner is investing on a 17+ year horizon and wants exposure to emerging technologies, in the belief that this is a time of great technological change and innovation. That horizon is not background; it is the design's load-bearing parameter. It is what dissolves the consensus trap (the goal is durable real shifts ownable for two decades, not pre-consensus alpha), it is why the empty niche is empty (no institution shares the objective, no vendor sells to it), and — per the code review — it is why almost none of the sibling trading stack's *intelligence* transfers while all of its *record-keeping discipline* does. On a horizon this long with feedback this sparse, the archive is the intelligence. Every CONTRACT below serves patience over reaction.

Project Prospector is the offensive twin of the thesis smoke detector: it watches the ETF universe for structural novelty and proposes **reading, never orders**. v1 is the deterministic core.

**IN:**
- Three deterministic lead-spawners: **intra-basket dispersion**, **inter-basket excess-correlation**, **ETF launches**.
- One accretion stream: **rebalances** (holdings deltas) onto existing leads.
- **Discourse capture** (raw, frozen, uninterpreted) targeted at structural hits.
- Append-only event store (S3 blobs + local WAL SQLite index); leads as folds; weekly heartbeat email + immediate state-change pushes; read-only Streamlit; verdict CLI.
- Fixed starter universe; identity pinned to SEC series IDs, with an explicit failed-resolution path.
- Backtest mode: calibration, the known-shift recall test, the precision audit, the March-2020 falsification.
- **The deterministic half of the cross-stream lag:** T(structural departure) → T(corroborating launch) is computable from v1 events. The milestone-3 backtest produces the first datum free (historical XLK×XLU firing vs TEKX's 2024-09 launch). The discourse→structure lead time — the full velocity-toward-consensus — is **v2**; do not expect it from milestones 3–7.

**OUT (explicitly — do not helpfully add):**
- Any LLM interpretation: no scouts, no tagging, no tag-minting gate, no adversary, no generated narrative. The only API use is capture plumbing (§6), and **no model-generated text is ever persisted as data**.
- Universe auto-expansion (v2). Universe changes are manual config edits.
- Sub-industry grid (v1 is sector-level).
- Any write path into the detector, the portfolio dashboard, or portfolio.yaml. Any read of portfolio.yaml.
- Any "run now" button or on-demand recompute surface. Cadence is the discipline.
- Any component from the sibling repo's `models/` (Mamba/SSM, ESN, neural-SDE, PINN, FinGAN, PPO, QUBO, sliced-Wasserstein OOD). Capacity **and** opacity; wrong for this data scale and forbidden by the interpretability mandate. See Appendix A.

---

## §1 — Placement and firewall (CONTRACT)

- **Own repository** (`prospector`), separate from prophit_skunkworks. This is the strongest form of the firewall: no import path to detector or Prophit code exists at all.
- **Vendored primitives — concrete (from the LTEE archive; full map in Appendix A).** Copy from `prophit_skunkworks/ltee_archive/` into `prospector/primitives/` with provenance headers (source repo, file, commit hash, date). Vendor the **disciplines and query shapes, not the schema**:
  - (a) **Atomic-write + SHA-256 + sidecar** per record — the `archiver.save_checkpoint` pattern (write `.tmp`, fsync, rename; hash; write queryable sidecar). A torn write must be impossible.
  - (b) **WAL-mode SQLite registry** as the queryable metadata index, with blobs on object storage and *never* in the index — the `registry.py` pattern.
  - (c) **Safe-SQLite-backup** via the `.backup` API before any upload — never raw-copy a live WAL file — the `s3_uploader.safe_upload_sqlite` pattern (a bug you would otherwise ship and find the hard way).
  - (d) **Forensic read-only query shapes** — `forensics.py`'s trajectory / cross-sectional / extinction queries *are* the thaw-backward surface; port their shapes.
  - **Do not vendor** the trading ontology (`schemas.py` — calmar/pnl/drawdown metrics, curriculum phases, death reasons) or anything under `models/`. Duplication over coupling is accepted. (Judgment call, veto-able.)
- **Separate S3 bucket**, own IAM credentials scoped to that bucket only. The Prospector's credentials must be *unable* to read the detector's bucket or portfolio.yaml — enforced at IAM, not convention.
- Separate notification channel: **email**, not the detector's Discord webhook. Different channels keep yin and yang contexts deliberately separate.
- Own schedule, own config, own Streamlit app (separate port/deployment from the look-through dashboard). Note the deliberate inversion from the sibling repo: Prophit's dashboard uses `streamlit-autorefresh` (a live cockpit where staleness is the enemy); the Prospector forbids autorefresh (a patience instrument where a refreshing screen is a compulsive-checking surface). Same author, same library, opposite polarity — because the games have opposite relationships to time.
- Infra-as-code: a single bootstrap file in the repo (Terraform or an idempotent setup script) creating bucket, IAM, schedule, and instance/Lambda. No hand-configured state.
- The **only** connection to the portfolio system is human and one-way: a lead graduates by passing the per-investment-thread pipeline by hand. No code path exists for this in v1.

---

## §2 — Universe and identity

**Starter universe (DEFAULT, in config):**
- **Correlation grid:** the 11 Select Sector SPDRs — XLK, XLC, XLY, XLP, XLE, XLF, XLV, XLI, XLB, XLRE, XLU — 55 pairs.
- **Dispersion baskets:** the same 11 funds, constituents from issuer daily holdings files.
- **Launch watch:** all new US-listed ETFs (a handful per day).
- **Rebalance watch:** the 11 sector funds plus any fund that is the subject of a live lead.

Deliberate exclusion: the user's own holdings are **not** in the seed (novelty≠interest; firewall). Config-overridable; exclusion is the default.

**Identity resolution (CONTRACT — the HECO rule):**
- Registry key is the **SEC series ID** (S######), with CIK and class IDs attached. Tickers are display-only attributes.
- The registry write path **requires** series_id; schema validation rejects a bare ticker. Nothing downstream — no lead, no baseline — may anchor to a ticker.
- Resolution flow: ticker (from etfdb seed or launch scan) → EDGAR series/class lookup → confirm a prospectus filing exists → write registry entry.

**Failed-resolution path (CONTRACT — punch-list 3).** EDGAR's ticker→series mapping is messy, disproportionately for the brand-new and weird funds — exactly the targets. A failed resolution must never silently drop the fund:
- On failure: emit `resolution.failed` onto `_system` (failures land *in* the fossil record — countable, never silent).
- **Auto-retry daily for N days** (DEFAULT `identity.retry_days: 10`) — EDGAR series indexing lags new funds, so most failures self-heal.
- After N days unresolved: the ticker enters a **manual-resolution queue**, surfaced as a dashboard panel and a line in the heartbeat email. Human resolves via CLI (`pros identity resolve <ticker> --series-id S######`), which writes the registry entry and emits `identity.resolved` with `method: manual`.
- Integrity preserved (nothing keys on a bare ticker); blindness closed (nothing evaporates).

Registry entry: `{series_id, class_ids[], cik, ticker_current, name, issuer, category_draft, concentration_industries[], prospectus_accession, holdings_source, first_seen, verified_at}` — `category_draft` is etfdb's label, **never trusted**, steering only; `concentration_industries` comes from the prospectus and is truth. Registry objects are S3-versioned; every change also emits `registry.updated` to `_system`.

---

## §3 — Data ingestion

- **Prices:** daily EOD adjusted closes, free source (Stooq or Yahoo; pin one primary + one fallback, record source per row). Needed for: 11 sector ETFs + SPY (market factor) + sector constituents (bounded below). Persist raw pulls to S3 (`ingest/prices/...`) before computing anything — freeze the substrate.
- **Constituents:** issuer daily holdings files (SPDR publishes daily CSVs) as the live feed for membership and weights; quarterly public NPORT-P from EDGAR as the authoritative cross-check *and* as the point-in-time historical record (used by the dispersion backtest, §10).
- **Constituent scale bound (DEFAULT):** top holdings covering 90% of basket weight (`dispersion.weight_coverage: 0.90`).
- **EDGAR:** daily filings-index check for (a) NPORT-P on watched funds, (b) new fund registrations / 485 filings (launch sensor), (c) new prospectus filings on watched funds (audit path → `mandate.changed`).
- **etfdb:** periodic scrape of the category tree and fund list (DEFAULT weekly) for the draft grid and launch-scan seed. Store raw scrapes. Diffs are steering only; every diff is verified against EDGAR before any event is written (the diff trap: source-correcting-itself vs world-changing).

---

## §4 — Sensors (deterministic writers)

Discipline throughout: **record on cadence, push on state change.** Entry/exit thresholds are Schmitt triggers (no flapping). All thresholds are config; defaults are placeholders **calibrated by the milestone-3 backtest**.

**4a. Excess-correlation (inter-basket edge sensor).**
- Daily returns for the 11 sector ETFs and SPY. Market strip: per-fund β over trailing 252d vs SPY; residual `r_i − β_i·r_mkt`.
- Signal: rolling 63d residual correlation per pair, Fisher-z. Baseline: trailing 252d mean/std of the Fisher-z per pair. Departure z = (current − baseline mean)/baseline std.
- Entry DEFAULT z ≥ 2.5 → spawn/activate lead, emit `xcorr.departure`. Exit DEFAULT z ≤ 1.0 → `xcorr.reverted` (lead → reverted, never deleted). Weekly `xcorr.tick` while active (cadence record, no push).
- **Market-stress annotation (CONTRACT — frozen 2026-07-02).** Compute mean *raw* pairwise correlation across the 55 pairs over a 21-day window. If it exceeds the **absolute** crisis level **0.85**, departures are still **recorded** (`market_stress: true` in payload — append-only ethos, capture now interpret later) but they **do not spawn leads, do not count as state changes, do not page.** Stressed events without an existing lead go onto `_system`. When stress clears and a departure persists, it fires normally. A gate would delete information; the annotation protects the oracle and the lead registry while keeping the record whole. Losing paging during a crash-week is free — structural formation is a months-scale phenomenon.
  - **Form: absolute level, NOT baseline-relative (settled empirically, frozen).** Baseline-relative (departure-from-trailing-norm — the theoretically nicer instrument the design prefers elsewhere) was tested exhaustively on this statistic — window lengths 5/10/15 × baselines 63/126/252 — and *every* construction fails the same way, which is the tell that the failure is structural, not a tuning miss. The durable reason: the pair residual correlation (the §4a signal) is a **scale-free** quantity — it has no meaningful level, so only its *change* is interpretable, and departure-z is right. Market-wide mean pairwise correlation is the opposite kind of object — a **fragility gauge with an intrinsic scale**: a market at 0.95 average sector correlation is one where diversification has collapsed and everything moves as one, i.e. a stressed market *whatever last month's level was*. The **level is the signal.** Normalizing by trailing variance therefore destroys exactly the quantity you want: the range compresses (COVID's raw 0.95 is only ~2σ above its own smooth, mean-reverting norm, so the whole departure-z distribution caps at ~2.5σ) and crisis-ordering breaks (a small wobble off a calm baseline out-z's a real crisis off an elevated one — COVID stops being an outlier). Absolute level separates crises cleanly because *for this statistic, crisis severity is the absolute level*: COVID 0.95 > Aug-2019 scare 0.88 > 2022 grind 0.82 > calm p95 ~0.81. (This is the absorption-ratio / correlation-concentration family — Kritzman–Li — which systemic-risk practice uses as absolute levels or percentiles, never trailing-normalized, for exactly this reason.)
  - **Level: 0.85 (settled; onset latency is the binding constraint).** The gate's demoted job is crisis-only — catching the two things the (milestone-3-proven-clean) β-strip cannot during acute crisis: (a) crash-onset β-staleness (the trailing β estimated pre-crash leaks for a short leading-edge window — the observed Feb-18-2020 leak) and (b) liquidity fire-sale dislocations. Both are *acute-onset* phenomena, which makes onset latency load-bearing. 0.85 gives ~5-day onset (fast enough for the β-staleness window), fires on COVID and the genuinely-acute Aug-2019 scare, sits just above calm p95 (~0.81) with the 2022 grind (0.82) correctly *below*, and gates only ~2.7% of days. It beats the alternatives on the gate's actual purpose: **0.90** rises ~10 days into the crash (too slow for the onset window the gate exists to cover); **0.80** fires on the 2022 slow bear grind — a *sustained* regime, which the crisis-only demotion deliberately leaves un-gated, because in sustained-high-correlation stretches the idiosyncratic departures are disproportionately the structural shifts we most want surfaced, so over-gating those months blinds the tool exactly when it should watch.
  - **Not case-fit (recall-independence check).** The real 2023 XLK×XLU signal (market-wide correlation 0.667 that day) stays *ungated at every candidate level* — so this choice is made purely on the crisis side and cannot be tuning-to-the-known-case. Principled, not fitted, per §5.
  - **Aging watch-item (CONTRACT — standing review).** Absolute levels age, and this is their one real weakness over a 17-year horizon: ETF/index-driven co-movement has plausibly raised the secular baseline, so calm correlation could drift up toward 0.85 and begin catching calm days. Headroom is explicit and thin: calm p95 ~0.81 vs gate 0.85 ≈ 0.04. **Standing review** (same cadence as other recalibrations): recompute calm-regime p95 on a recent multi-year window; if the margin to the gate compresses, deliberately re-freeze the level higher. **CRITICAL — do NOT solve aging with a rolling percentile or any self-updating window:** that is baseline-relative in disguise and reintroduces the exact failure diagnosed above (crisis days and sustained regimes inflate the trailing percentile). The correct pattern is frozen-absolute + periodic *human* recalibration — machine surfaces the drift, the human moves the level — which is machine-proposes-human-ratifies, identical to the oracle-ceiling and vocabulary-review disciplines.
- **Failure-diagnosis note (code comment, for milestone-3):** if March-2020 fires broadly despite the strip, two distinct mechanisms are candidates — (1) stale trailing-252d βs leave uncorrected market exposure in residuals during a regime break → remedy: EWMA or shorter β window; (2) a single factor underexplains crisis comovement even when estimated perfectly → remedy: add a second factor. Know which one you are fixing.
- Statistical caveat to encode as a comment, not solve: overlapping windows autocorrelate, so z-scores overstate significance — thresholds are empirical, set by backtest, never by Gaussian assumptions.
- **Provenance note (Appendix A):** this z-score-against-a-frozen-baseline *is* the OOD primitive — model normal, flag departure — at the right capacity for the data. The sibling stack's sliced-Wasserstein-over-neural-embeddings OOD detector is the *same idea at the wrong capacity* for 55 pairs (and reintroduces the black box the interpretability mandate forbids). The concept ports; the machinery does not. Do not reach for the fancy distance.
- At first deploy, emit `baseline.frozen` on `_system` with a snapshot reference of all pair baselines.

**4b. Dispersion (intra-basket fracture sensor).**
- Per basket: trailing 63d daily returns for weight-covering constituents → pairwise correlation matrix → spectral (or hierarchical) bipartition → cluster quality **Q = mean(within-cluster corr) − mean(between-cluster corr)**.
- Baseline: trailing 252d mean/std of Q per basket; departure z as above. Entry DEFAULT z ≥ 2.5 → spawn/activate `disp` lead, emit `dispersion.tick` with split membership in payload (which names went which way — the go-look content). Exit DEFAULT z ≤ 1.0 → `dispersion.reverted`. Weekly tick while active.
- **Shadow mode (CONTRACT — punch-list 4).** Dispersion ships **record-only** for its first live quarter (DEFAULT `dispersion.shadow_days: 90`): events written, leads spawned but marked `shadow: true` — excluded from paging, from the active-lead ceiling, and from the state-changes email section; visible in a dashboard shadow panel. Promotion to paging is a human decision after a calibration review, executed as a config flip (`dispersion.paging: true`) — which emits `config.changed`, so the record shows exactly when the sensor became live. Rationale: survivor-only calibration under-predicts live firing rates (bias points toward oracle-flooding), so even a successful PIT backtest earns only shadow, not paging.

**4c. Launch sensor.**
- Daily: diff etfdb fund list (skim) ∪ EDGAR new-registration scan (truth).
- **Two-phase launch (CONTRACT — punch-list 3 + lag integrity).** At detection, emit `launch.unverified` onto `_system` with ticker-only payload and `detected_at` timestamp. This event **never keys a lead** (identity rule holds). Identity resolution then runs (§2, retry-then-queue). On success, emit the proper `launch` event with `{series_id, ticker, name, category_draft, concentration_industries, detected_at, unverified_ref}` and spawn the launch lead. **All lag math uses `detected_at`, never resolution time** — a fund that takes nine days to resolve must not get a launch timestamp nine days late, because the launch timestamp is the datum the cross-stream lag is measured against.
- A launch whose concentration industries overlap a live `xcorr` or `disp` lead's baskets also emits its `launch` event **onto that lead** — the cross-stream corroboration hook, and the raw material for the deterministic lag.

**4d. Rebalance sensor.**
- Daily: diff issuer holdings files for watched funds; quarterly: NPORT-P cross-check.
- Material change (DEFAULT: any add/drop, or weight delta ≥ 0.5%) → `rebalance` event onto every live lead whose baskets include that fund; if none, onto `_system` (recorded, not surfaced).
- New prospectus filing on a watched fund → diff stated mandate vs stored copy → `mandate.changed` on any change (audit = detection).

---

## §5 — Lead model and event schema (CONTRACT)

**Envelope (frozen, five fields):**
```json
{ "ts": "2026-07-14T13:00:00Z", "lead": "<lead_id>", "type": "<string>", "payload": { }, "schema": 1 }
```

**Lead identity:** natural key from spawner + **series IDs** (never tickers), hashed short; human display kept separately (`display: "XLK×XLU"`). `_system` is reserved for infra/registry events.

**A lead is the fold over its event stream.** No mutable rows. Computed state: `{status: active|reverted, shadow: bool, verdict: none|yes|no|watch, spawned_at, last_event, event_count, latest_z, capture_inventory}`. Snapshots to `snapshots/{lead_id}/{ts}.json`; fold is deterministic (same events → same state, property-tested).

**Store implementation (CONTRACT — lifted from the LTEE registry, schema inverted).** The store is a local **WAL-mode SQLite** registry (fast queryable index) backed by object storage (the durable append-only blobs), mirroring `ltee_archive/registry.py`. **Critical inversion:** Prophit uses *wide typed metric columns* (one column per metric) because its metric set is fixed; the Prospector must **not**, because its whole premise is unforeseen event types. So the events table is the **envelope** — `ts, lead, type, schema` as columns plus `payload` as a **JSON blob column** — indexed on `(lead, ts, type)`. This preserves the open-`type` contract at the storage layer: a new event type needs no migration and no new column. Every event write is atomic (temp → fsync → rename) with a SHA-256; the SQLite file is snapshotted via the `.backup` API before upload, never raw-copied while WAL-active.

**Verdict succession (lifted from `apex_history.superseded_by`).** Verdicts are append-only, but a re-adjudication links to the prior verdict via a `superseded_by` pointer, so the *evolution* of your judgment on a lead is itself queryable — not merely the latest state. A changed mind is a new `verdict` event that supersedes, never an edit.

**Adaptive snapshot policy (CONTRACT — resolves decisions-review open-Q C).** Adopt the LTEE three-tier density *shape* (`snapshot_policy.py`) but **invert the trigger**. Prophit knows when stress is coming because it *authored* the training curriculum, so its density keys on scheduled epoch boundaries (480–620, 1400–1600). The Prospector cannot know when a fracture is coming — that is the premise — so density must be **reactive**: dense while any lead is active (DEFAULT: snapshot active leads daily), sparse when the collection is quiet (DEFAULT: weekly floor), plus an immediate snapshot on any state change (the "apex" tier's reactive analog). Do **not** port the epoch-boundary triggers; they are meaningless without a training schedule.

**v1 recognized event types (all deterministic-written):**

| type | emitted by | payload core fields |
|---|---|---|
| `lead.spawned` | any spawner | spawner, signature, evidence ref, shadow |
| `xcorr.departure` / `xcorr.tick` / `xcorr.reverted` | 4a | pair (series_ids + display), fisher_z, z, windows, market_stress |
| `dispersion.tick` / `dispersion.reverted` | 4b | basket, Q, z, split membership, shadow |
| `launch.unverified` | 4c | ticker, name_raw, detected_at |
| `launch` | 4c | series_id, ticker, name, category_draft, concentration_industries, detected_at, unverified_ref |
| `rebalance` | 4d | series_id, adds, drops, weight_deltas |
| `mandate.changed` | 4d | series_id, diff summary, filing accessions |
| `capture.stored` | §6 | query_set, s3_prefix, result_counts |
| `verdict` | CLI | verdict, note, superseded_by |
| `registry.updated` / `identity.resolved` / `resolution.failed` | §2 | series_id or ticker, change summary, method |
| `baseline.frozen` / `config.changed` | runner | snapshot ref / config diff |
| `fault` | anywhere | subsystem, message |

**Unknown types:** the fold raw-renders anything unrecognized (visible, timestamped, uninterpreted) and counts it — the unknown-type panel exists from day one; it is the contract v2's LLM writers plug into. (The JSON-payload column is what makes this work with no migration.)

**Config honesty (CONTRACT):** on every run, hash the config; if changed, emit `config.changed` with the diff *before* any sensor runs — folds stay interpretable across threshold changes.

---

## §6 — Discourse capture (raw, frozen, uninterpreted)

- **Trigger:** a non-shadow lead entering `active`, then weekly per active lead (DEFAULT). Shadow leads do not trigger capture (they aren't yet trusted enough to spend on).
- **Query construction is deterministic templating — no LLM authorship.** From lead metadata: basket display names, top-N constituent names, concentration industries. K queries per capture (DEFAULT K=5).
- **Mechanics:** Anthropic Messages API `web_search` with a minimal fetch-only prompt, **persisting only the `web_search_tool_result` blocks verbatim** (model prose discarded, never written), or a plain search API — implementation choice; the contract is what gets stored, not the provider.
- **Stored:** `captures/{lead_id}/{ts}/query_{n}.json` — query, timestamp, provider, raw result blocks. Additionally `web_fetch` the top-M URLs per query (DEFAULT M=2) and store extracted page text — fetched text is the frozen substrate; snippets can be re-served differently later.
- Each capture emits one `capture.stored` event onto the lead.
- **Budget guard (CONTRACT):** hard caps — `capture.max_searches_per_week` (DEFAULT 60), `capture.monthly_budget_usd` (user sets). On breach: capture pauses + `fault` event. Never silently overrun; never silently skip.

---

## §7 — Store layout (S3, versioning ON, lifecycle to cheap tiers, no deletion)

```
s3://<prospector-bucket>/
  events/{lead_id}/{ts}_{type}_{uuid}.json      # append-only fossil record — live observations ONLY
  snapshots/{lead_id}/{ts}.json                 # materialized folds
  captures/{lead_id}/{ts}/...                   # raw discourse
  ingest/prices/{source}/{date}/...             # frozen substrate
  ingest/holdings/{series_id}/{date}/...
  ingest/etfdb/{date}/...
  registry/funds/{series_id}.json               # versioned
  baselines/{date}/...
  registry.sqlite                               # WAL SQLite index, backed up via .backup API (never raw-copied)
  backtest/...                                  # synthetic history — NEVER under events/  (CONTRACT)
```

**Implementation notes (from the LTEE archive — Appendix A):**
- The S3 tree is the **durable substrate**; a local **WAL-mode SQLite registry** (`registry.sqlite`, the `registry.py` pattern) is the **queryable index** the dashboard and CLI read. Re-listing S3 prefixes for every query is the wrong tool — the registry holds envelope rows + JSON payloads + file paths, never blob contents.
- **Write discipline:** atomic temp→fsync→rename for every event object; SHA-256 per object; the SQLite file is snapshotted with the `.backup` API before any upload (`s3_uploader.safe_upload_sqlite` — raw-copying a live WAL database corrupts it). Uploads are fire-and-forget and must never crash the run.
- **Nothing under `events/` is ever edited or deleted.** Corrections are new events. Backtests write only under `backtest/`.

---

## §8 — Outputs

**8a. Email (weekly heartbeat + immediate pushes) (punch-list 6, confirmed).**
- **Heartbeat:** weekly, fires regardless of activity. Subject `[PROS] heartbeat — N active, M shadow, no changes` (or counts). Body: scan stats; active-leads digest (one line each: display, age, latest z, events this week, verdict); shadow panel summary; manual-resolution queue if non-empty; faults. Receipts inline as event references.
- **Push:** immediate email on any state change (lead entered/reverted, promotion, mandate.changed) and on any `fault`. Subject `[PROS] state change: …` / `[PROS] FAULT: …`.
- **Dead-man property:** silence beyond 7 days unambiguously means *broken* — the weekly floor is the heartbeat; state changes arrive same-day. Right latency for a tool whose leads develop over months, and every email now means something (smaller impulse surface than a daily "OK").
- **Oracle-load ceiling (punch-list 5, confirmed: DEFAULT `oracle.active_lead_ceiling: 8`).** Counts active, non-shadow leads. While breached, every email carries a banner: *"Over ceiling (N/8): tighten thresholds, or the regime changed — either way, review."* The ceiling cannot mechanically distinguish loose-thresholds from a genuinely interesting world; that judgment is the human's. **No auto-tune ever (CONTRACT)** — the ceiling is a tripwire for human recalibration, machine-proposes-human-ratifies applied to the system's own sensitivity.
- Rendering is deterministic templating of folds — no generated prose (honest by construction).

**8b. Streamlit dashboard.** Read-only, renders stored snapshots and event streams — **no recompute on view, no autorefresh, no run-now** (the discipline variable is computation cadence, not display richness; note the deliberate inversion from Prophit's autorefreshing cockpit, §1). Panels: active leads ranked (recency × z); per-lead event timeline (the thaw-backward view); **shadow panel** (dispersion burn-in); **manual-resolution queue**; universe registry health; capture inventory; unknown-type panel (empty in v1, built anyway); fault log.
- **The query shapes are lifted directly from `ltee_archive/forensics.py`** (read-only pandas-over-SQLite, already designed there): `lineage_trajectory` → per-lead event timeline; `cross_lineage_at_epoch` → "all leads as of date T" (the thaw-backward view); `extinction_report` → reverted/dead-lead view; `global_apex_ranking` → lead ranking. Port the shapes; rename off the trading genre.

**8c. Verdict CLI.** `pros lead list`, `pros lead show <id>`, `pros verdict <id> yes|no|watch [-m note]` → appends a `verdict` event (append-only; a changed mind is a new event that supersedes via `superseded_by`, never an edit). `pros identity resolve <ticker> --series-id S######` for the manual queue. **No capture-trigger command, no run-now command.**

---

## §9 — Runner and ops

- Single scheduled entrypoint (cron on a small instance, or Lambda + EventBridge; contract: stateless between runs except the store).
- Daily run: config-hash check → ingest → sensors (4a–4d) → identity retries → capture for due leads → snapshots (reactive cadence, §5) → push emails if state changed. Weekly run adds: etfdb scrape + heartbeat email.
- Every run writes a run-log object; any exception emits `fault` and still attempts the push email (a fault email beats silence).
- All times UTC in the record; email renders local.

---

## §10 — Testing and acceptance

1. **HECO fixture (identity).** Ticker `HECO` resolves to the State Street Galaxy fund's series ID via EDGAR; `category_draft` (the stale ESG label, kept as fixture data) is stored but never used for baseline or lead identity.
2. **Resolution-failure fixture.** A ticker that fails EDGAR lookup → `resolution.failed` on `_system`, daily retries, manual queue after N days; a `launch.unverified` emitted at detection preserves `detected_at`, and the eventual `launch` back-references it. Assert lag math reads `detected_at`.
3. **Fold determinism.** Same event set (any arrival order, sorted by ts at fold) → identical state. Unknown types render, count, never crash. Shadow flags respected in ceiling/paging logic. Verdict-supersession chain resolves to the latest verdict while preserving history.
4. **Envelope validation.** Bare-ticker registry writes rejected; malformed events rejected at write. WAL SQLite backed up via `.backup` (not raw copy) in the upload path — assert the upload never opens the live WAL file directly.
5. **Milestone-3 acceptance gate (CONTRACT — punch-list 1+2 folded in):** `pros backtest --from 2019-01-01 --to 2024-12-31` over the 55-pair grid, writing under `backtest/` only. Three criteria, all reported in one artifact:
   - **(a) Recall.** The AI-power linkage (Tech×Utilities excess co-movement) fires, with the dated timeline reported.
   - **(b) Precision.** The **full firing list** over the window, every pair, every firing — not just the target. Each firing is auto-scored by **cross-stream corroboration**: structural if a verified launch (or material rebalance) whose concentration industries keyword-match *both* sides of the pair lands within W months after first firing (DEFAULT `backtest.corroboration_window_months: 24`; the sector→keyword map is a small static config table — crude, deterministic, reviewable). Docstring caveat, stated honestly: this bakes in "packaged = real," so a real-but-never-packaged firing scores as junk — acceptable because packageability is this system's own success criterion, but it is a bias, not a truth. **Threshold selection ties to precision:** choose z_in/z_out for an acceptable structural fraction, deliberately backed off from the recall-optimal setting (anti-overfit to the one known case).
   - **(c) Falsification — March 2020.** During the crash window, the sensor must not fire broadly: with the stress annotation active, assert **zero new leads spawned** in the window and that raw departures are captured with `market_stress: true`. If it fails, diagnose via the §4a mechanism note (stale β vs single-factor underexplanation) before touching thresholds.
   - **Bonus datum (free):** report T(first XLK×XLU firing) → T(TEKX launch, 2024-09) as the first deterministic cross-stream lag measurement.
6. **Dispersion PIT backtest (milestone 3b).** Reconstruct historical basket membership from quarterly NPORT-P filings (~2019 onward — quarterly resolution suffices for a 63d window). **Measure and report the delisted-constituent price-coverage fraction** from the free EOD source; if coverage is poor, fall back to live burn-in only, and say so. Either way, shadow mode (§4b) applies at go-live — the backtest earns calibration, not paging.
7. **Dead-man.** Kill a sensor in staging → push email with FAULT subject still sends.

---

## §11 — Cost envelope (v1)

- Compute: one t4g.nano-class instance or Lambda — single-digit $/mo.
- S3: negligible at v1 volumes; lifecycle to infrequent-access after 90d.
- Capture: the one recurring spend — bounded by §6 caps; dollars, not tens, per month at defaults. Buys the frozen backbone; zero oracle load; budget as insurance for v2's thaw-backward.
- Email: SES or existing SMTP — pennies. (Volume now lower still: weekly + event-driven.)

---

## §12 — Build order (suggested milestones)

1. Repo bootstrap (§13) + **study and vendor `ltee_archive/` per §1 / Appendix A** (envelope-shaped WAL registry, atomic-write, safe-backup, forensic query shapes) + envelope/store/fold with tests (§5, §7; tests 3–4). Do not re-solve the store from scratch — a tested implementation exists in the sibling repo; port its disciplines under the inverted (envelope + JSON payload) schema.
2. Identity resolution + registry + **failed-resolution path** + HECO and resolution-failure fixtures (§2; tests 1–2).
3. Price/holdings ingest + excess-corr sensor with stress annotation + **backtest mode + the full acceptance gate** (§3, §4a; test 5). **Calibrate thresholds here before anything goes live.**
   - **3b.** Dispersion PIT backtest attempt + coverage report (test 6).
4. Dispersion (shadow-wired) + launch (two-phase) + rebalance sensors (§4b–4d).
5. Email (heartbeat + push + ceiling banner) + dead-man + Streamlit (incl. shadow + resolution-queue panels, forensic query shapes) + CLI (§8; test 7).
6. Discourse capture + budget guard (§6).
7. Infra-as-code + deploy (§1, §9).

Milestone 3 is the heart. If the backtest can't see AI-power forming in Tech×Utilities residual correlation — or can only see it at thresholds that also page on 25 junk pairs — that is cheap, informative failure: bring it back to the design thread before building 4–7.

---

## §13 — Repo bootstrap

**Repo name:** `prospector` (new, separate repository — §1).

**Skeleton:**
```
prospector/
  prospector/
    primitives/        # vendored from prophit_skunkworks/ltee_archive/ (Appendix A):
                       #   WAL registry, atomic-write, safe-backup, forensic queries —
                       #   envelope-shaped (JSON payload), trading ontology stripped
    ingest/            # prices, holdings, edgar, etfdb
    sensors/           # xcorr, dispersion, launch, rebalance
    store/             # envelope schema, WAL registry, S3 sync
    fold/              # fold + adaptive-reactive snapshots
    outputs/           # email render, streamlit app
    cli/               # pros entrypoints
  config/prospector.yaml
  infra/               # bootstrap.tf or setup.sh — the only way the AWS side gets built
  tests/               # incl. fixtures: heco.json, resolution_failure.json
  docs/                # this spec (rev 3), decisions review rev 2, founding document, Appendix A
  CLAUDE.md
  README.md
```

**CLAUDE.md (repo constitution — write it in milestone 1, contents in brief):**
- This repo is **Project Prospector**, the offensive twin of the thesis smoke detector. It proposes reading, never orders. It is firewalled from the detector and the portfolio: never add code that reads the detector's bucket or portfolio.yaml, and never add a code path that places, sizes, or recommends a trade.
- **CONTRACT vs DEFAULT:** items marked CONTRACT in `docs/` specs change only via the design thread (chat), never unilaterally in implementation. DEFAULTs are config.
- **Append-only:** nothing under `events/` is ever edited or deleted. Corrections are new events. Backtests write only under `backtest/`.
- **Vendored store provenance:** the store/registry primitives are ported from `prophit_skunkworks/ltee_archive/` with the trading ontology stripped and the schema inverted to envelope + JSON-payload (Appendix A). Keep provenance headers; do not re-introduce wide typed-metric columns, and do not import anything from the sibling repo's `models/`.
- **No LLM text as data (v1):** no model-generated prose is persisted as record content. Capture stores raw search-result blocks and fetched page text only.
- **No run-now surfaces:** no commands, buttons, or endpoints that trigger recompute or capture on demand. Record on cadence; push on state change. No dashboard autorefresh.
- **Identity:** every fund keys on SEC series ID. A bare ticker is rejected at the write path. Failed resolutions go to the queue, never silently dropped.
- **Config honesty:** config changes emit `config.changed` before sensors run.
- Push-alert posture mirrors the detector's amended CLAUDE.md guardrails: hard cadence floor (weekly heartbeat), state-change-only push, read-only surfaces, no execution.
- **Standing review items (human-ratified, never auto-tuned):** the active-lead ceiling (§8a) and the stress-gate aging monitor (§4a — recompute calm-regime p95; re-freeze the absolute level higher if headroom to the calm baseline compresses; **never** a rolling percentile, which reintroduces the baseline-relative failure). Thresholds move only by deliberate human recalibration that leaves a `config.changed` fossil.

**config/prospector.yaml (initial keys, defaults per this spec):** universe lists; window lengths (63/252/21); z_in 2.5 / z_out 1.0 per sensor; `stress_gate.window_days: 21`, `stress_gate.absolute_level: 0.85` (FROZEN — absolute, not baseline-relative; see §4a), `stress_gate.calm_p95_reference: 0.81` (aging watch-item); `dispersion.weight_coverage: 0.90`; `dispersion.shadow_days: 90`; `dispersion.paging: false`; `identity.retry_days: 10`; `oracle.active_lead_ceiling: 8`; snapshot cadence (`active: daily`, `quiet: weekly`); capture K=5, M=2, `max_searches_per_week: 60`, `monthly_budget_usd: <user>`; `backtest.corroboration_window_months: 24`; sector→keyword corroboration map; email address; schedule times.

---

## Appendix A — LTEE archive port map (what to lift from the sibling repo)

Reviewed against `prophit_skunkworks/ltee_archive/` (`archiver.py`, `registry.py`, `snapshot_policy.py`, `forensics.py`, `schemas.py`, `s3_uploader.py`) and `models/supervisory/ood_detector.py`.

**Governing finding.** The sibling repo's transferable value is its **fossil-record plumbing, not its intelligence.** The modeling stack does not cross the domain gap: Prophit has millions of L3 tick events/day and reaches for maximal function-approximation capacity to exploit them; the Prospector has a few hundred regime-relevant observations *per decade*. That inverts the bias-variance regime — the same capacity that is correct there is overfitting risk here, and it reintroduces the opacity the whole yin/yang project forbids at the apex. What survives is the record-keeping and the disciplines that keep it honest, which are nearly universal.

| Sibling artifact | Port as | Rebuild / drop |
|---|---|---|
| `archiver.py` — atomic-write + SHA + sidecar | **verbatim discipline** | — |
| `registry.py` — WAL SQLite, metadata/blob split, forensic indexes | **structure + query shapes** | replace fixed metric columns with **envelope + JSON payload** |
| `s3_uploader.safe_upload_sqlite` — `.backup` before upload | **verbatim** (the WAL-backup lesson) | — |
| `forensics.py` — trajectory / cross-sectional / extinction queries | **query shapes** (they *are* thaw-backward) | rename off the trading genre |
| `apex_history.superseded_by` chain | **pattern** for verdict succession | — |
| `snapshot_policy.py` — three-tier adaptive density | **principle** (resolves open-Q C) | **invert trigger: scheduled → lead-reactive** |
| `schemas.py` — enums + metric dataclasses | — | **drop** (trading ontology: calmar/pnl/drawdown, curriculum phases, deaths) |
| `ood_detector.py` — sliced-Wasserstein gate | **concept only** — the shared heart of both twins (model normal, flag departure) | **drop machinery**; the §4a z-score is the right-capacity form |
| `models/` — Mamba/SSM, ESN, neural-SDE, PINN, FinGAN, PPO, QUBO | — | **do not cross** (capacity + opacity) |

**One-line vendoring summary.** Vendor `ltee_archive/`'s disciplines and query shapes under the Prospector's envelope schema; drop the trading ontology and every `models/` component; rebuild the snapshot trigger from scheduled to lead-reactive. What survives the domain gap is the fossil record and the rules for keeping it honest — which, on a 17-year horizon with sparse feedback, *is* the intelligence.

**Two free lessons worth keeping visible.** (1) The `.backup`-before-upload discipline is a corruption bug you would otherwise ship and find the hard way — keep it verbatim. (2) Prophit's `streamlit-autorefresh` cockpit is *correct there* and *forbidden here*: seeing the same author's same library used with opposite polarity is the cleanest statement of why machinery — even your own, even already-written — cannot thoughtlessly cross between the millisecond game and the decade game.

---

*End of rev 3. The decisions review (rev 2, 2026-07-01) remains the canonical "why" and is unchanged by this revision — the code review confirmed every decision and specified how to build it. This spec is the canonical "what to build." Milestone 3 is the gate; if it returns a no, that is the system working as designed.*
