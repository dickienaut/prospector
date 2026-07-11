# Generator v1 — Build Specification

*2026-07-01. Implements the decisions review (rev 2, 2026-07-01) and founding document. Written to be read cold by the implementer (Claude Code). The name "generator" is provisional (open question G); the package name is `generator` until renamed. Where this spec says DEFAULT, the value is config, not architecture — change freely. Where it says CONTRACT, do not deviate without returning to the design thread.*

---

## §0 — Purpose and v1 scope

The generator is the offensive twin of the thesis smoke detector: it watches the ETF universe for structural novelty and proposes **reading, never orders**. v1 is the deterministic core:

**IN:**
- Three deterministic lead-spawners: **intra-basket dispersion**, **inter-basket excess-correlation**, **ETF launches**.
- One accretion stream: **rebalances** (holdings deltas) onto existing leads.
- **Discourse capture** (raw, frozen, uninterpreted) targeted at structural hits.
- Append-only S3 event store; leads as folds; daily text email with dead-man's-switch; read-only Streamlit; verdict CLI.
- Fixed starter universe; identity pinned to SEC series IDs.
- Backtest mode for calibration and the known-shift acceptance test.

**OUT (explicitly — do not helpfully add):**
- Any LLM interpretation: no scouts, no tagging, no tag-minting gate, no adversary, no generated narrative. The only API use is capture plumbing (§6), and **no model-generated text is ever persisted as data**.
- Universe auto-expansion (v2). Universe changes are manual config edits.
- Sub-industry grid (v1 is sector-level).
- Any write path into the detector, the portfolio dashboard, or portfolio.yaml. Any read of portfolio.yaml.
- Any "run now" button or on-demand recompute surface. Cadence is the discipline.

---

## §1 — Placement and firewall (CONTRACT)

- Lives in `prophit_skunkworks` as a separate top-level package: `generator/`. It may import from a shared `primitives/` library (envelope schema, append-only store client, reconciliation enum) — extract these from detector code if not already shared. It must never import detector runtime modules or share runtime state.
- **Separate S3 bucket** (not a shared prefix), own IAM credentials scoped to that bucket only. The generator's credentials must be *unable* to read the detector's bucket or portfolio.yaml, enforced at IAM, not convention.
- Separate notification channel: **email**, not the detector's Discord webhook. Different channels keep yin and yang contexts separate on purpose.
- Own cron/schedule, own config file, own Streamlit app (separate port/deployment from the look-through dashboard).
- Infra-as-code: a single bootstrap file in the repo (Terraform or an idempotent setup script) creating bucket, IAM, schedule, and instance/Lambda. No hand-configured state.
- The **only** connection to the portfolio system is human and one-way: a lead graduates by passing the per-investment-thread pipeline by hand. No code path exists for this in v1.

---

## §2 — Universe and identity

**Starter universe (DEFAULT, in config):**
- **Correlation grid:** the 11 Select Sector SPDRs — XLK, XLC, XLY, XLP, XLE, XLF, XLV, XLI, XLB, XLRE, XLU — 55 pairs.
- **Dispersion baskets:** the same 11 funds, constituents from issuer daily holdings files.
- **Launch watch:** all new US-listed ETFs (global scan; it is a handful per day).
- **Rebalance watch:** the 11 sector funds plus any fund that is the subject of a live lead.

Note the deliberate exclusion: the user's own holdings (GRID, NUKZ, XBI, etc.) are **not** in the seed. The generator looks outward; seeding it with the book is the novelty≠interest trap and a firewall leak. (User may override in config; the default is exclusion.)

**Identity resolution (CONTRACT — the HECO rule):**
- Registry key is the **SEC series ID** (S######), with CIK and class IDs attached. Tickers are display-only attributes.
- The registry write path **requires** series_id; schema validation rejects a bare ticker. This is the unskippable verify step (open question B): nothing downstream — no lead, no event, no baseline — may anchor to a ticker.
- Resolution flow: ticker (from etfdb seed or launch scan) → EDGAR series/class lookup → confirm a prospectus filing exists → write registry entry.
- Registry entry: `{series_id, class_ids[], cik, ticker_current, name, issuer, category_draft, concentration_industries[], prospectus_accession, holdings_source, first_seen, verified_at}` — `category_draft` is etfdb's label and is **never** trusted, only steering; `concentration_industries` comes from the prospectus and is truth.
- Registry objects live in the bucket with S3 versioning on; every change also emits a `registry.updated` event to the `_system` lead so history is in the fossil record.

---

## §3 — Data ingestion

- **Prices:** daily EOD adjusted closes, free source (Stooq or Yahoo; implementation choice, but pin one primary + one fallback and record source per row). Needed for: 11 sector ETFs + SPY (market factor) + sector constituents (bounded below). Persist raw pulls to S3 (`ingest/prices/...`) before computing anything — freeze the substrate.
- **Constituents:** issuer daily holdings files (SPDR publishes daily CSVs; the repo already has an example of the format). Primary for membership and weights. Quarterly public NPORT-P from EDGAR is the authoritative cross-check — note honestly in code comments that public N-PORT is quarterly with lag; issuer dailies are the live feed.
- **Constituent scale bound (DEFAULT):** for dispersion, use top holdings covering 90% of basket weight (config `dispersion.weight_coverage: 0.90`) to bound the price universe to a few hundred tickers total.
- **EDGAR:** daily filings-index check for (a) NPORT-P on watched funds, (b) new fund registrations / 485 filings for the launch sensor, (c) new prospectus filings on watched funds (triggers the audit path → `mandate.changed`).
- **etfdb:** periodic scrape of the category tree and fund list (DEFAULT weekly) for the draft grid and launch-scan seed. Store raw scrapes (`ingest/etfdb/{date}/...`). Diffs of these scrapes are steering only; every diff is verified against EDGAR before any event is written (the diff trap: source-correcting-itself vs world-changing).

---

## §4 — Sensors (deterministic writers)

All sensors follow the detector's discipline: **record on cadence, push on state change.** Each sensor has entry and exit thresholds (Schmitt trigger — no flapping). All thresholds are config; defaults below are placeholders to be calibrated by backtest (§11).

**4a. Excess-correlation (inter-basket edge sensor).**
- Daily returns for the 11 sector ETFs and SPY.
- Market factor strip: for each fund, β over trailing 252d vs SPY; residual `r_i − β_i·r_mkt`.
- Signal: rolling 63d residual correlation per pair, Fisher-z transformed.
- Baseline: trailing 252d mean/std of the Fisher-z per pair. Departure z-score = (current − baseline mean)/baseline std.
- Entry DEFAULT z ≥ 2.5 → spawn/activate lead, emit `xcorr.departure`. Exit DEFAULT z ≤ 1.0 → emit `xcorr.reverted`, lead state → reverted (never deleted).
- While active: weekly `xcorr.tick` events (cadence record), no push.
- Known statistical caveat to encode as a comment, not solve: overlapping windows autocorrelate, so z-scores overstate significance — thresholds are empirical, set by backtest, not by Gaussian assumptions.
- At first deploy, emit `baseline.frozen` on `_system` with a snapshot reference of all pair baselines.

**4b. Dispersion (intra-basket fracture sensor).**
- Per basket: trailing 63d daily returns for weight-covering constituents → pairwise correlation matrix → spectral (or hierarchical) bipartition → cluster quality **Q = mean(within-cluster corr) − mean(between-cluster corr)**.
- Baseline: trailing 252d mean/std of Q per basket; departure z as above.
- Entry DEFAULT z ≥ 2.5 → spawn/activate `disp` lead, emit `dispersion.tick` with the split membership in payload (which names went which way — this is the go-look content). Exit DEFAULT z ≤ 1.0 → `dispersion.reverted`.
- Weekly tick while active. Q is the bimodality statistic per the review doc: a clean two-cluster split, not plain variance.

**4c. Launch sensor.**
- Daily: diff etfdb fund list (skim) ∪ EDGAR new-registration scan (truth) → each new ticker runs identity resolution (§2) → on verify, emit `launch` event and spawn a `launch` lead with `{series_id, ticker, name, category_draft, concentration_industries}`.
- A launch whose concentration industries overlap a live `xcorr` or `disp` lead's baskets also emits a `launch` event **onto that lead** — this is the cross-stream corroboration hook and the raw material for cross-stream lag measurement.

**4d. Rebalance sensor.**
- Daily: diff issuer holdings files for watched funds; quarterly: diff NPORT-P as cross-check.
- Material change (DEFAULT: any add/drop, or weight delta ≥ 0.5% of basket) → `rebalance` event onto every live lead whose baskets include that fund; if none, onto the `_system` lead (recorded, not surfaced).
- New prospectus filing on a watched fund → diff stated mandate text vs stored copy → any change emits `mandate.changed` (audit = detection).

---

## §5 — Lead model and event schema (CONTRACT)

**Envelope (frozen, five fields):**
```json
{ "ts": "2026-07-14T13:00:00Z", "lead": "<lead_id>", "type": "<string>", "payload": { }, "schema": 1 }
```

**Lead identity:** natural key from spawner + series IDs, hashed short for the key, display string kept human: e.g. key `xcorr:a1b2c3` with `display: "XLK×XLU"`. Series IDs, never tickers, inside the natural key material. `_system` is a reserved lead for infra/registry events.

**A lead is the fold over its event stream.** No mutable lead rows. Computed state: `{status: active|reverted, verdict: none|yes|no|watch, spawned_at, last_event, event_count, latest_z, capture_inventory}`. Snapshots (materialized folds) written to `snapshots/{lead_id}/{ts}.json` after each run; fold must be deterministic (same events → same state, property-tested).

**v1 recognized event types (all deterministic-written):**

| type | emitted by | payload core fields |
|---|---|---|
| `lead.spawned` | any spawner | spawner, signature, evidence ref |
| `xcorr.departure` / `xcorr.tick` / `xcorr.reverted` | 4a | pair (series_ids + display), fisher_z, z, windows |
| `dispersion.tick` / `dispersion.reverted` | 4b | basket, Q, z, split membership |
| `launch` | 4c | series_id, ticker, name, category_draft, concentration_industries |
| `rebalance` | 4d | series_id, adds, drops, weight_deltas |
| `mandate.changed` | 4d | series_id, diff summary, filing accessions |
| `capture.stored` | §6 | query_set, s3_prefix, result_counts |
| `verdict` | CLI | verdict, note |
| `registry.updated` / `identity.resolved` | §2 | series_id, change summary |
| `baseline.frozen` / `config.changed` | runner | snapshot ref / config diff |
| `fault` | anywhere | subsystem, message |

**Unknown types:** the fold must raw-render anything it doesn't recognize (visible, timestamped, uninterpreted) and count it — the unknown-type panel exists from day one even though v1 writers can't produce unknowns. This is the contract v2's LLM writers plug into.

**Config honesty:** on every run, hash the config; if changed since last run, emit `config.changed` with the diff before any sensor runs — so folds remain interpretable across threshold changes (an old tick under an old threshold means something different, and the record must say so).

---

## §6 — Discourse capture (raw, frozen, uninterpreted)

- **Trigger:** a lead entering `active` (xcorr or disp), then weekly per active lead while active (DEFAULT).
- **Query construction is deterministic templating — no LLM authorship.** From lead metadata: basket display names, top-N constituent names, concentration industries. E.g. for XLU×XLK: `"utilities data centers"`, `"power demand semiconductors"`, `"<top XLU name> <top XLK name>"`. K queries per capture (DEFAULT K=5).
- **Mechanics:** either the Anthropic Messages API `web_search` tool with a minimal fetch-only prompt, **persisting only the `web_search_tool_result` blocks verbatim** (any model prose is discarded, never written to the record), or a plain search API (e.g. Brave free tier) — implementation choice; the contract is *what gets stored*, not the provider.
- **Stored:** `captures/{lead_id}/{ts}/query_{n}.json` — query, timestamp, provider, raw result blocks (URLs, titles, snippets). Additionally `web_fetch` the top-M URLs per query (DEFAULT M=2) and store extracted page text — snippets can be re-served differently later; fetched text is the frozen substrate (§7 founding-doc freezing discipline).
- Each capture emits one `capture.stored` event onto the lead.
- **Budget guard (CONTRACT):** hard caps in config — `capture.max_searches_per_week` (DEFAULT 60), `capture.monthly_budget_usd` (DEFAULT set by user). On breach: capture pauses and a `fault` event is emitted. Never silently overrun; never silently skip.

---

## §7 — Store layout (S3, versioning ON, lifecycle to cheap tiers, no deletion)

```
s3://<generator-bucket>/
  events/{lead_id}/{ts}_{type}_{uuid}.json      # append-only fossil record
  snapshots/{lead_id}/{ts}.json                 # materialized folds
  captures/{lead_id}/{ts}/...                   # raw discourse
  ingest/prices/{source}/{date}/...             # frozen substrate
  ingest/holdings/{series_id}/{date}/...
  ingest/etfdb/{date}/...
  registry/funds/{series_id}.json               # versioned
  baselines/{date}/...                          # frozen baseline snapshots
  backtest/...                                  # synthetic history — NEVER under events/
```
The live `events/` tree contains only live observations. Backtests write exclusively under `backtest/` (CONTRACT — the fossil record must not contain synthetic history).

---

## §8 — Outputs

**8a. Daily email (the briefing).** Plain text. Fires **every day** regardless of activity — the dead-man's-switch: subject encodes state (`[GEN] OK — no changes` / `[GEN] 2 state changes` / `[GEN] FAULT`), so *no email* unambiguously means *broken*. Body: heartbeat line (baskets scanned, pairs computed, captures run); state-changes section; active-leads digest (one line each: display, age, latest z, events this week, verdict); faults. Receipts inline as event references (`[2026-07-14 xcorr.departure z=2.8]`). v1 rendering is deterministic templating of folds — no generated prose, which keeps the briefing honest by construction.

**8b. Streamlit dashboard.** Read-only, renders stored snapshots and event streams — **no recompute on view, no autorefresh, no run-now** (same constraint as the detector's page: the discipline variable is computation cadence, not display richness). Panels: active leads ranked (recency × z); per-lead event timeline (the thaw-backward view); universe registry health (verified vs draft-only); capture inventory; unknown-type panel (empty in v1, built anyway); fault log.

**8c. Verdict CLI.** `gen lead list`, `gen lead show <id>`, `gen verdict <id> yes|no|watch [-m note]` → appends a `verdict` event. Verdicts are append-only; a changed mind is a new verdict event, never an edit. No capture-trigger command, no run-now command.

---

## §9 — Runner and ops

- Single scheduled entrypoint (cron on a small instance, or Lambda + EventBridge — implementation choice; contract: stateless between runs except S3).
- Daily run order: config-hash check → price/holdings/EDGAR ingest → sensors (4a–4d) → capture for due leads → snapshots → email. Weekly adds the etfdb scrape.
- Every run writes a run-log object; any exception emits `fault` and still attempts the email (a fault email beats silence).
- All times UTC in the record; email renders local.

---

## §10 — Testing and acceptance

1. **HECO fixture (identity).** Ticker `HECO` must resolve to the State Street Galaxy fund's series ID via EDGAR; the test asserts `category_draft` (etfdb's stale ESG label, kept as fixture data) is stored but never used for baseline or lead identity. The bug that motivated the rule is the regression test for it.
2. **Fold determinism.** Property test: same event set (any order of arrival, sorted by ts at fold time) → identical state. Unknown-type events render, count, never crash.
3. **Envelope validation.** Bare-ticker registry writes rejected; malformed events rejected at write.
4. **The known-shift backtest (acceptance).** `gen backtest --from 2019-01-01 --to 2024-12-31 --pairs XLK-XLU,XLK-XLE` runs the excess-corr sensor over historical data (writes under `backtest/` only) and produces a dated would-have-fired timeline. Acceptance: the AI-power linkage (Tech×Utilities excess co-movement) is flagged, with the firing date reported against the known consensus timeline (thematic launches ~2024). This doubles as threshold calibration: pick z_in/z_out so this fires usefully early without paging weekly on noise, then note honestly (per the founding doc) that one known case *calibrates* and *fails-to-refute* — it does not validate.
5. **Dead-man.** Kill a sensor in staging → email still sends with FAULT subject.

---

## §11 — Cost envelope (v1)

- Compute: one t4g.nano-class instance or Lambda — single-digit $/mo.
- S3: negligible at v1 volumes; lifecycle rules move ingest/ to infrequent-access after 90d.
- Capture: the one recurring spend — bounded by §6 caps; at defaults (≲60 searches/wk + small fetches) this is dollars, not tens, per month. It buys the frozen backbone and adds zero oracle load; budget it as insurance for v2's thaw-backward.
- Email: SES or existing SMTP — pennies.

---

## §12 — Build order (suggested milestones)

1. Primitives extraction + envelope/store/fold with tests (§5, §7, test 2–3).
2. Identity resolution + registry + HECO fixture (§2, test 1).
3. Price/holdings ingest + excess-corr sensor + **backtest mode** (§3, 4a, test 4) — calibrate thresholds here before anything goes live.
4. Dispersion + launch + rebalance sensors (4b–4d).
5. Email + dead-man + Streamlit + verdict CLI (§8, test 5).
6. Discourse capture + budget guard (§6).
7. Infra-as-code + deploy (§1, §9).

Milestone 3 is the heart: if the backtest can't see AI-power forming in Tech×Utilities residual correlation, that is cheap, informative failure — bring it back to the design thread before building 4–7.
