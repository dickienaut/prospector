# Project Prospector — v1 Build Specification (rev 9)

*2026-07-03, rev 9 — supersedes rev 8. Rev 9 decomposes the rebalance sensor (§4d) after the design thread resolved its scope, mirroring the launch decomposition (§4c): the **holdings-diff accretion core is self-contained** (reuses the built `ingest/holdings.py`) and ships as its own PR; **`mandate.changed` is deferred as its own defined next slice** because it needs new surface (EDGAR prospectus-*text* fetch + `ingest/prospectus/` storage + text diff). Also settled: **routing by forward-hash** (no payload change — the lead-id is the canonical encoding of a lead's series_ids), **live-lead enumeration from the registry-materialized fold** (no separate cache), **mandate text stored as a per-accession blob** (never in `FundEntry` — so `mandate.changed` can diff across versions), and **NPORT-P scoped to holdings-table-only** (deferred with §3b). No prior sensor/gate behavior changed. Written to be read cold by the implementer (Claude Code) in a **fresh repo**. Where this spec says DEFAULT, the value is config — change freely. Where it says CONTRACT, do not deviate without returning to the design thread.*

**Rev 9 changes (rebalance decomposition + routing/storage decisions):**
- **§4d split (like §4c):** holdings-diff accretion (self-contained, this PR) vs `mandate.changed` mandate-diff (own slice, named unblock = prospectus-text fetch + `ingest/prospectus/` storage). Rebalance is a pure **accretion** sensor — no Schmitt, no lead of its own; `rebalance`/`mandate.changed` are silent corroborations (no fold change).
- **Routing (CONTRACT — no payload change):** forward-hash the fund's memberships via the existing `xcorr_lead_id`/`dispersion_lead_id` functions and intersect with active leads. The lead-id already encodes the series_ids; duplicating them in the payload invites drift.
- **Live-lead enumeration (CONTRACT):** read the active set from the registry (the fold's materialized snapshots) — no re-fold-each, no separate lead-to-baskets cache.
- **Mandate storage (§7):** `ingest/prospectus/{series_id}/{accession}/`, frozen per accession, reference-only in the registry — append-only, so the diff across versions is possible.
- **NPORT-P (deferred §3b):** holdings-table-only extraction (proper XML, not full-schema, not regex); trigger is the daily filings-index check (event-driven), not a quarterly cron. Stub stays deliberately thin.

**Rev 8 changes (proto-cluster substrate):**
- **Appendix B (v2 design note): proto-clusters — modeling the substrate below the corpus.** ETFs are the corpus ceiling (only packaged/discussed theses); the constituent layer breaks it — an unpackaged, undiscussed thesis is visible as a *cluster of names co-moving across sector boundaries* (a pseudo-ETF). The canary is the **cluster, not the single name** (single names are the idiosyncratic noise baskets exist to escape). It is the earliest possible T0 for the cross-stream lag; the same scope / disposition / firewall discipline transfers wholesale (observation-only — the canary is never the trade). Worked example: the 2023 nuclear+AI cluster, before NUKZ existed.
- **§4b dispersion payload → generous (CONTRACT).** Full constituent membership + sub-cluster assignment + correlation structure, so the deferred proto-cluster layer can thaw backward. You cannot backfill a payload you didn't capture.
- **§0:** the proto-cluster layer added to the v2/deferred list.

**Rev 7 changes (launch model + ceiling resolution):**
- **Launches don't spawn ceiling-counting leads (CONTRACT).** A launch is *near-consensus by construction* (packaging happens at/after peak recognition — the Ben-David finding), so a launch matching no active lead is, by its own timing, *late* — a "missed the early signal" marker, not an actionable lead. Disposition: **corroborating launch accretes onto the matched lead** (and the cross-stream lag is measured *on that lead*); **non-corroborating launch is recorded dormant on `_system`**, surfaced only for deliberate survey, never pushed, no verdict, no ceiling slot. The §8a ceiling is therefore governed by the **two structural detectors only** (excess-correlation, dispersion). The parked "handful of new ETFs/day blows the ceiling" question **dissolves** — launches never consume slots.
- **Launch sensor decomposition (forced build order).** Recording (detection + two-phase `launch.unverified`→`launch`, `detected_at` preserved) is built and live-functional. Corroboration (holdings-derived concentration → sector-set overlap → accrete-or-record + the live lag test) is the **defined next slice, gated on §4d**, tested against live behavior — never a hook wired to fixtures. You cannot backfill a launch timestamp (capture must run first), but you can add corroboration later and thaw it backward.
- **Concentration from holdings, not prose (§4c).** Reuses §4d's holdings→sector logic; ground-truth over stated strategy (look-through-is-truth; HECO the standing proof). The keyword matcher stays where it belongs — the backtest's curated YAML.
- **Sequencing (§12): holdings ingest is the keystone** — build `ingest/holdings.py` first (it unblocks dispersion, rebalance, *and* launch corroboration), then dispersion (shadow), then rebalance.

**Rev 6 changes (spec ← code + box-B resolution):**
- **Verdict vocabulary → four values, three live meanings (CONTRACT).** `yes` (promoted, on-thesis) · `watch` (on-thesis, unproven — **untouched**) · `off-thesis-real` (real but off-thesis, e.g. macro/sector regime — catalogued, inert) · `noise` (the refined `no`). The overloaded `no` is retired. Critical guard: `off-thesis-real` must never absorb `watch` (a deferred real tech lead must not rot under a "macro" label). Enforced by construction — verdict never keys action; ceiling/paging key on `status`+`shadow`.
- **Box-B outcome recorded (§10.5c).** The re-armed falsifier flagged 7 of 10 crash spawns; the diagnostic ruled out stale-β (0/7 collapse under a faster β — the β-strip's **second** independent confirmation) and classified them a real 2020–2022 Financials/Materials/Real-estate regime → **Box B, Path 1: no sensor change, +593 signal untouched.** Persistent-but-classified is **not** a milestone-3 failure — the test *routed* correctly. `crash_revert_weeks` stays 8 (flags dispositioned by classification, not by re-windowing — avoids the anti-fitting trap).
- **Macro catalog (§8b, milestone 5).** A read-only forensic view over `off-thesis-real` verdicts; **not** an alert stream. Context for human consultation only.
- **Single-factor β stays; multi-factor is wrong here (§4a guard).** A macro regime is entangled with real tech signal (AI-power is both a tech linkage and rate-sensitive capex), so stripping it would amputate signal. §4a note (2)'s "add a second factor" now carries a guard.

**Rev 5 changes (post-recalibration test amendment):**
- **§10.5(c) amended — "zero crash-window spawns" retired, reversion criterion added.** The original criterion operationalized "the β-strip works" under the retired assumption that the stress gate suppresses the entire crash; the β-strip proof reassigned that job and demoted the gate to acute-onset-only, so the window now correctly shows spawns (M3: 10). "Zero" would require re-inflating to the 24.8%-over-gating the recalibration removed. The replacement keeps the falsifier's teeth: β-strip-clean is **necessary, not sufficient** (idiosyncratic ≠ structural — a crash produces transient idiosyncratic co-movement that is not a durable thesis), so the amended test requires crash-window spawns to be **transient — they revert** rather than persisting as durable leads. This is the criterion that keeps the test able to fail, and it must be **verified against the M3 output, not assumed**.
- **If (iii) fails, the recalibration is not repudiated** — a persistent crash spawn is informative (real crisis-coincident shift, or onset artifact); the principled fix is a faster β estimator (§4a note 1), never re-tightening the crisis level or shrinking the gate's level window.
- **§4a aging-monitor reference pinned.** The decision note cited calm p95 as both ~0.81 (all-days, near-crisis included → margin ~0.04) and ~0.668 (recent calm-regime → margin ~0.18). The monitor uses the **calm-regime** measure (≈0.18 margin, healthy); the note should be reconciled to that one definition.

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
- **Two deterministic lead-spawners** (the genuinely *early* signals): **inter-basket excess-correlation** and **intra-basket dispersion**.
- **The launch stream** as **corroboration + consensus-clock** — accretes onto an active lead on a holdings-derived sector match, records dormant on no-match; it **never spawns a standalone ceiling-counting lead** (§4c, §8a).
- **Rebalances** as accretion (holdings deltas) onto existing leads.
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
- The **proto-cluster / constituent-substrate layer** (v2 — Appendix B). v1 does **not** interpret constituent co-movement into pseudo-baskets; it only **banks the substrate** via the generous dispersion payload (§4b), so the v2 layer can thaw backward over it.

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
  - **Aging watch-item (CONTRACT — standing review).** Absolute levels age, and this is their one real weakness over a 17-year horizon: ETF/index-driven co-movement has plausibly raised the secular baseline, so calm correlation could drift up toward 0.85 and begin catching calm days. Headroom is monitored operationally each run — the backtest reports the p95 of market-wide correlation over **recent non-crisis days** and its margin to the 0.85 gate (implementation reports ≈0.18 margin on the recent-window calm-regime measure — healthy). One reconciliation to close: the decision note cites calm p95 as both ~0.81 (all-days, near-crisis included → margin ~0.04) *and* ~0.668 (recent calm-regime → margin ~0.18); the monitor uses the **calm-regime** measure (non-crisis days excluded, since aging is about the *calm* baseline approaching the gate), and the note should be pinned to that one definition so the margin is unambiguous. **Standing review** (same cadence as other recalibrations): recompute calm-regime p95 on a recent multi-year window; if the margin to the gate compresses, deliberately re-freeze the level higher. **CRITICAL — do NOT solve aging with a rolling percentile or any self-updating window:** that is baseline-relative in disguise and reintroduces the exact failure diagnosed above (crisis days and sustained regimes inflate the trailing percentile). The correct pattern is frozen-absolute + periodic *human* recalibration — machine surfaces the drift, the human moves the level — which is machine-proposes-human-ratifies, identical to the oracle-ceiling and vocabulary-review disciplines.
- **Failure-diagnosis note (code comment, for milestone-3):** if March-2020 fires broadly despite the strip, two distinct mechanisms are candidates — (1) stale trailing-252d βs leave uncorrected market exposure in residuals during a regime break → remedy: EWMA or shorter β window; (2) a single factor underexplains crisis comovement even when estimated perfectly → remedy: add a second factor. Know which one you are fixing. **Guard (box-B finding, §10.5c):** neither mechanism was the cause in practice — the β-strip is confirmed clean *twice* (aggregate placebo −0.035, and a faster-β diagnostic on the flagged pairs: 0/7 collapse). Persistent crash decouplings turned out to be a **real macro/sector regime, not β leakage**, so remedy (2) applies *only* to genuine residual β leakage (ruled out here) and must **never** be used to strip a real macro regime — that regime is entangled with real tech signal (AI-power is both a tech linkage and rate-sensitive capex), so a multi-factor β would **amputate signal**. Single-factor β-strip stays; real macro regimes are *catalogued* (§5 `off-thesis-real`), not *removed*. Any future multi-factor change is a v2 question with its own full re-validation, not a quiet tweak.
- Statistical caveat to encode as a comment, not solve: overlapping windows autocorrelate, so z-scores overstate significance — thresholds are empirical, set by backtest, never by Gaussian assumptions.
- **Provenance note (Appendix A):** this z-score-against-a-frozen-baseline *is* the OOD primitive — model normal, flag departure — at the right capacity for the data. The sibling stack's sliced-Wasserstein-over-neural-embeddings OOD detector is the *same idea at the wrong capacity* for 55 pairs (and reintroduces the black box the interpretability mandate forbids). The concept ports; the machinery does not. Do not reach for the fancy distance.
- At first deploy, emit `baseline.frozen` on `_system` with a snapshot reference of all pair baselines.

**4b. Dispersion (intra-basket fracture sensor).**
- Per basket: trailing 63d daily returns for weight-covering constituents → pairwise correlation matrix → spectral (or hierarchical) bipartition → cluster quality **Q = mean(within-cluster corr) − mean(between-cluster corr)**.
- Baseline: trailing 252d mean/std of Q per basket; departure z as above. Entry DEFAULT z ≥ 2.5 → spawn/activate `disp` lead, emit `dispersion.tick` with split membership in payload (which names went which way — the go-look content). Exit DEFAULT z ≤ 1.0 → `dispersion.reverted`. Weekly tick while active.
- **Shadow mode (CONTRACT — punch-list 4).** Dispersion ships **record-only** for its first live quarter (DEFAULT `dispersion.shadow_days: 90`): events written, leads spawned but marked `shadow: true` — excluded from paging, from the active-lead ceiling, and from the state-changes email section; visible in a dashboard shadow panel. Promotion to paging is a human decision after a calibration review, executed as a config flip (`dispersion.paging: true`) — which emits `config.changed`, so the record shows exactly when the sensor became live. Rationale: survivor-only calibration under-predicts live firing rates (bias points toward oracle-flooding), so even a successful PIT backtest earns only shadow, not paging.
- **Payload richness (CONTRACT — banks the substrate for the deferred proto-cluster layer, Appendix B).** The `dispersion.tick` payload must be *generous*, not merely the scalar Q: **full constituent membership with each name's sub-cluster assignment, the cluster centroids, and the constituent correlation structure** (at minimum the within- and cross-cluster correlation summaries; ideally the pairwise matrix or its top structure). Reason: the proto-cluster / pseudo-ETF layer (Appendix B) is a *deferred* v2 interpretation that must thaw backward over this history, and **you cannot backfill a payload you did not capture** (append-only forced-ordering, §5). Capture the substrate richly now even though nothing interprets it until v2 — a scalar-only tick would permanently blind the future layer to *which* names formed the proto-cluster and *how* they cohered.

**4c. Launch sensor — recording (M4, built) + corroboration (next slice, gated on §4d).** A launch is *near-consensus by construction* (packaging happens at/after peak recognition — the Ben-David finding), so the launch stream's jobs are **corroboration and consensus-clock, not early lead-spawning**; it never spawns a standalone, ceiling-counting lead (§8a). The sensor splits into two slices with a **forced** build order — you cannot backfill *when* a fund launched (an un-watched launch timestamp is gone forever), but you can add corroboration later and thaw it backward over a captured launch history:

- **Recording half (M4 — built, live-functional).** Detection (new-registration scan — `company_tickers_mf.json` snapshot diff → candidates) + **two-phase recording**: at detection emit `launch.unverified` onto `_system` with ticker-only payload and `detected_at`; this **never keys a lead**; identity resolution then runs (§2, retry-then-queue); on success emit the proper `launch` event on `_system` with `{series_id, ticker, name, detected_at, unverified_ref}`. **`concentration_industries` is empty at this stage** (the prospectus/holdings fill is deferred — see below). **All lag math uses `detected_at`, never resolution time** — a fund that takes nine days to resolve must not get a timestamp nine days late.

- **Corroboration half (next slice — gated on §4d holdings ingest).** Concentration is **derived from the launch's first holdings, not parsed from prospectus prose** — reusing §4d's holdings→sector logic, ground-truth over stated strategy (the look-through-is-truth principle; HECO is the standing proof a fund's stated identity can be categorically wrong). Corroboration is then a direct **sector-set overlap** between the launch's holdings-derived sectors and an active lead's baskets:
  - **Match** (overlaps an active `xcorr` or `disp` lead): **accrete** the `launch` event **onto that lead** — the high-value confirmation the structural lead was real, and what makes the **cross-stream lag measurable on a single lead** (departure T1, launch T2, lag = T2 − T1). No new lead; no ceiling slot.
  - **No match:** **record** the `launch` on `_system`, dormant — surfaced only in the read-only launch panel (§8b) for deliberate survey, **never pushed, no verdict demanded, no ceiling slot.** (The launch *log* is preserved intact as raw material for v2's auto-expansion and backward-corroboration — the new-node case is recorded even though v1 can't act on it.)

- **Honest boundary (CONTRACT — do not build a self-flattering test).** The backtest's +593-day lag came from curated `historical_launches.yaml` (concentration hand-filled), **not the live path** — the live pipeline sets `concentration_industries: []` until the deferred holdings-derived extraction exists. The corroboration hook and the **live** cross-stream lag therefore ship **with the corroboration slice, tested against live behavior** — never as a hook wired to fixtures whose only green test is a scenario that never occurs live. Recording (this slice) and (concentration + hook) (next slice) are **one design, jointly honest**: the hook is never built without its live input. The backtest keyword matcher (`keyword_match()` on `sector_keywords`) stays with the curated YAML; the live path uses holdings-derived sector overlap.

- **Named unblock (not an open-ended v-later):** holdings-derived concentration working against live filings, gated on §4d. When §4d lands, this slice is unblocked, not reopened for debate. The live cross-stream lag is a stated v1 deliverable — allowed to arrive in the next slice, not allowed to quietly disappear. **Semi-transparent active ETFs** disclose holdings less directly; for those, fall back to prospectus strategy text or tag concentration `unresolved` and let the hook simply **not fire** (honestly) rather than guess.

**4d. Rebalance sensor — holdings-diff accretion (self-contained slice) + mandate-diff (own slice).** A pure **accretion** sensor: no Schmitt trigger, no lead of its own; `rebalance`/`mandate.changed` are silent corroborations that accrete onto a lead's timeline and never change status or paging (no fold change). It splits, like the launch sensor (§4c), into a self-contained core and a part that needs new surface.

- **Holdings-diff accretion (self-contained — reuses the built `ingest/holdings.py`; ships as its own PR).** Daily: diff a watched fund's frozen holdings; a material change (DEFAULT: any add/drop, or weight delta ≥ 0.5%) → `rebalance` event **onto every live lead whose baskets include that fund**; if none, onto `_system` (recorded, not surfaced).
  - **Routing (CONTRACT — no payload change).** To find "every live lead whose baskets include this fund," **forward-hash**: the lead-id functions (`xcorr_lead_id`, `dispersion_lead_id`) are deterministic, so enumerate the fund's memberships (its pairs and its basket), hash each with **the existing functions verbatim** (so canonicalization matches by construction), and intersect with the active-lead set. **Do not** add `series_ids` to the `xcorr.departure`/`lead.spawned` payloads — the lead-id is already the canonical encoding of a lead's series_ids, and duplicating it in the payload invites drift (a bug class avoided by keeping one source of truth). Trivially cheap at the fixed v1 scale. (v2 revisit: if auto-expansion makes forward-hashing the universe expensive, introduce a maintained `series_id → active-lead` index built from the same functions — still not denormalized payload duplication.)
  - **Live-lead enumeration (CONTRACT).** Read the active-lead set from the **registry** (the fold's materialized state — the snapshots the fold already writes), not by re-folding every lead at run time, and **not** by building a separate lead-to-baskets cache (a redundant materialization that can drift from the fold; forward-hashing makes it unnecessary). Single source of truth: the fold, materialized in the registry.

- **Mandate-diff → `mandate.changed` (own slice — gated on new surface, deferred).** A new prospectus filing on a watched fund → diff its stated mandate vs the stored copy → `mandate.changed` on any change (**audit = detection** — the staleness check and the drift signal are one mechanism). **Deferred as its own defined next slice**, not folded into the holdings-diff PR, because it needs surface that does not exist: an EDGAR prospectus-**text** fetch (the client fetches only JSON metadata today) + mandate **storage** (§7 `ingest/prospectus/`) + a text diff. **Named unblock:** prospectus-text fetch + `ingest/prospectus/` storage working against live filings. Trigger is the daily filings-index check (§3, event-driven — a prospectus filing appears → diff), not a calendar job.

- **NPORT-P quarterly cross-check (deferred with §3b).** The quarterly authoritative holdings cross-check is gated on `parse_nport_holdings` (a deliberately thin §3b stub — do **not** fill it with survivor-biased data). When built: **extract the holdings table only** (targeted, via proper XML parsing of the holdings elements — not a full NPORT-schema object model you won't use, and not a fragile regex). The trigger is the same daily filings-index check (event-driven — a new NPORT-P appears → process), not a separate quarterly cron. Note: the holdings-diff accretion core above uses the **issuer daily holdings CSVs** (already built), not NPORT-P — so it is unblocked now.

---

## §5 — Lead model and event schema (CONTRACT)

**Envelope (frozen, five fields):**
```json
{ "ts": "2026-07-14T13:00:00Z", "lead": "<lead_id>", "type": "<string>", "payload": { }, "schema": 1 }
```

**Lead identity:** natural key from spawner + **series IDs** (never tickers), hashed short; human display kept separately (`display: "XLK×XLU"`). `_system` is reserved for infra/registry events.

**A lead is the fold over its event stream.** No mutable rows. Computed state: `{status: active|reverted, shadow: bool, verdict: none|yes|watch|off-thesis-real|noise, spawned_at, last_event, event_count, latest_z, capture_inventory}`. Snapshots to `snapshots/{lead_id}/{ts}.json`; fold is deterministic (same events → same state, property-tested). The fold is **vocabulary-agnostic** (a legacy `no` or a future v2 value still renders) — the four-value set is a write-path allow-list, not a fold gate.

**Store implementation (CONTRACT — lifted from the LTEE registry, schema inverted).** The store is a local **WAL-mode SQLite** registry (fast queryable index) backed by object storage (the durable append-only blobs), mirroring `ltee_archive/registry.py`. **Critical inversion:** Prophit uses *wide typed metric columns* (one column per metric) because its metric set is fixed; the Prospector must **not**, because its whole premise is unforeseen event types. So the events table is the **envelope** — `ts, lead, type, schema` as columns plus `payload` as a **JSON blob column** — indexed on `(lead, ts, type)`. This preserves the open-`type` contract at the storage layer: a new event type needs no migration and no new column. Every event write is atomic (temp → fsync → rename) with a SHA-256; the SQLite file is snapshotted via the `.backup` API before upload, never raw-copied while WAL-active.

**Verdict succession (lifted from `apex_history.superseded_by`).** Verdicts are append-only, but a re-adjudication links to the prior verdict via a `superseded_by` pointer, so the *evolution* of your judgment on a lead is itself queryable — not merely the latest state. A changed mind is a new `verdict` event that supersedes, never an edit.

**Verdict vocabulary (CONTRACT — four values, three live meanings).** The human's disposition of a lead. `VERDICT_VOCAB` (in `fold.py`) is the single source of truth the CLI and dashboards reference; the write path rejects anything outside it (including the retired `no`).

| Verdict | Meaning | Live? | Action |
|---|---|---|---|
| `yes` | promoted — real, on-thesis | live | enters the per-investment-thread pipeline (human) |
| `watch` | **on-thesis but unproven** — a candidate not yet cleared | **live, untouched** | stays under observation |
| `off-thesis-real` | **real but off-thesis** (macro/sector regime) | catalogued, **inert** | recorded as context; **no action ever** |
| `noise` | not real (the refined `no`) | dead | closed |

Two rules make this correct, both load-bearing:
- **Three live meanings must stay distinct.** `off-thesis-real` (real, permanently set aside — the cap-weighted core absorbs it) must **never** absorb `watch` (possibly-on-thesis, still live). Collapsing them would let a deferred real tech lead rot under a "macro" label. The retired binary `no` split into `noise` (dead) and `off-thesis-real` (catalogued); `watch` was **not** touched.
- **Context, never a trigger — enforced by construction, not just by rule.** Nothing keys on `verdict` to drive action: the active-lead ceiling and paging key on `status`+`shadow` (via `active_nonshadow`), and `off-thesis-real` never flips `status`. A test proves the disposition is inert.

**The `off-thesis-real` disposition and the macro catalog.** A real-but-off-thesis classification (e.g. the 2020–2022 Financials/Materials/Real-estate regime, §10.5c) is *catalogued as context, not discarded* — it is the reference frame a future tech signal is read against (a linkage forming *against* a hostile regime is stronger evidence than one riding it), a labeled negative set, recorded memory, and human-mediated context for the smoke detector (is a satellite drawdown a thesis break or a regime drawdown?). The catalog is a **read-only forensic view** (§8b, milestone 5) over `off-thesis-real` verdicts — **not an alert stream, never piped anywhere as actionable** (same class of rule as the reading-list wall). See §4a for why the corresponding sensor fix (multi-factor β) is *wrong*, not merely unnecessary.

**Adaptive snapshot policy (CONTRACT — resolves decisions-review open-Q C).** Adopt the LTEE three-tier density *shape* (`snapshot_policy.py`) but **invert the trigger**. Prophit knows when stress is coming because it *authored* the training curriculum, so its density keys on scheduled epoch boundaries (480–620, 1400–1600). The Prospector cannot know when a fracture is coming — that is the premise — so density must be **reactive**: dense while any lead is active (DEFAULT: snapshot active leads daily), sparse when the collection is quiet (DEFAULT: weekly floor), plus an immediate snapshot on any state change (the "apex" tier's reactive analog). Do **not** port the epoch-boundary triggers; they are meaningless without a training schedule.

**v1 recognized event types (all deterministic-written):**

| type | emitted by | payload core fields |
|---|---|---|
| `lead.spawned` | a structural spawner (`xcorr` or dispersion only — **not** launch) | spawner, signature, evidence ref, shadow |
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
  ingest/prospectus/{series_id}/{accession}/...   # frozen mandate text per filing accession (reference-only in the registry) — enables mandate.changed diff across versions
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
- **Oracle-load ceiling (punch-list 5, confirmed: DEFAULT `oracle.active_lead_ceiling: 8`).** Counts active, non-shadow leads. While breached, every email carries a banner: *"Over ceiling (N/8): tighten thresholds, or the regime changed — either way, review."* The ceiling cannot mechanically distinguish loose-thresholds from a genuinely interesting world; that judgment is the human's. **No auto-tune ever (CONTRACT)** — the ceiling is a tripwire for human recalibration, machine-proposes-human-ratifies applied to the system's own sensitivity. **The ceiling counts leads spawned by the two structural detectors only (`xcorr`, dispersion) — launches never independently consume a slot** (a corroborating launch accretes onto an existing lead; a non-corroborating launch is recorded dormant on `_system`, §4c). This is why a handful of new ETFs per day cannot blow the ceiling: launches are corroboration + clock, not lead-spawners.
- Rendering is deterministic templating of folds — no generated prose (honest by construction).

**8b. Streamlit dashboard.** Read-only, renders stored snapshots and event streams — **no recompute on view, no autorefresh, no run-now** (the discipline variable is computation cadence, not display richness; note the deliberate inversion from Prophit's autorefreshing cockpit, §1). Panels: active leads ranked (recency × z); per-lead event timeline (the thaw-backward view); **shadow panel** (dispersion burn-in); **manual-resolution queue**; universe registry health; capture inventory; unknown-type panel (empty in v1, built anyway); fault log; and (milestone 5) a **read-only macro catalog** — a forensic view over `off-thesis-real` verdicts (§5), for human consultation only, **not an alert stream and not a monitoring lane** (no push, no heartbeat action item); and a **read-only launch panel** — recorded launches (especially non-corroborating ones, §4c), for deliberate survey only, **never pushed** (same deliberate-consultation discipline as the macro catalog — a cluster of unmatched launches in a novel area is itself a signal worth pulling up, not a stream that pushes).
- **The query shapes are lifted directly from `ltee_archive/forensics.py`** (read-only pandas-over-SQLite, already designed there): `lineage_trajectory` → per-lead event timeline; `cross_lineage_at_epoch` → "all leads as of date T" (the thaw-backward view); `extinction_report` → reverted/dead-lead view; `global_apex_ranking` → lead ranking. Port the shapes; rename off the trading genre.

**8c. Verdict CLI.** `pros lead list`, `pros lead show <id>`, `pros verdict <id> yes|watch|off-thesis-real|noise [-m note]` → appends a `verdict` event (append-only; a changed mind is a new event that supersedes via `superseded_by`, never an edit). The retired `no` and unknown values are rejected; help text spells out why `off-thesis-real` and `watch` are distinct (do not file a live candidate tech lead as macro — §5). `pros identity resolve <ticker> --series-id S######` for the manual queue. **No capture-trigger command, no run-now command.**

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
   - **(c) Falsification — March 2020 (amended rev 5; original "zero spawns" retired).** The original criterion asserted zero crash-window spawns — which operationalized "the estimator works" under the now-retired assumption that the stress gate suppresses the entire crash. The β-strip proof reassigned the crash-factor defense to the β-strip and demoted the gate to acute-onset-only, so the gate correctly no longer over-suppresses and the window shows spawns (M3: 10 — 7 in the onset-latency β-staleness window, 1 pre-onset, 2 recovery-tail). "Zero" would require re-inflating to the 24.8%-of-days over-gating the recalibration removed (which re-buries the 2023 signal), so it is retired. **The replacement keeps the falsifier's teeth** — the test exists to catch *a crash manufacturing durable bad leads*, and β-strip-clean is **necessary, not sufficient**: the β-strip removes the common factor, but *idiosyncratic ≠ structural*. A crash produces genuine idiosyncratic co-movement (Financials×Utilities decoupling as rates collapse) that is **transient crisis phenomenon, not a durable thesis**, and only *persistence over time* separates the two. Amended criteria:
     - **(i) Estimator falsification (core, intent unchanged):** the β-strip keeps mean pairwise residual correlation ≈0 through the crash (M3: −0.035 vs raw 0.88). If this fails the estimator leaks and no gate rescues it — diagnose via the §4a mechanism note (stale β vs single-factor underexplanation).
     - **(ii) Gate does its demoted job:** the gate fires on the acute crisis (M3: COVID peak 0.947, ~5-day onset) and its suppression is confined to the acute-peak days (it does not gate the whole window).
     - **(iii) No durable false leads — the falsifiable core; VERIFY against M3, do not assume:** every crash-window spawn must be **transient — it reverts** (the Schmitt exit, §4a) within a bounded window rather than persisting and accreting as a durable lead. The onset-latency leak is "free" *precisely because* those spawns resolve when the crisis passes; a spawn that persists for months is not free. Checkable against the existing M3 backtest output (the replay produces reversions): assert every crash-window spawn reverts within `backtest.crash_revert_weeks` (DEFAULT 8); flag any that does not. A crash that manufactured a durable lead fails (iii) *even with a clean β-strip* — which is the teeth the test needs.
     - **Reporting:** emit the crash-window spawn list with per-spawn phase (pre-onset / onset / peak / recovery-tail) and reversion latency, so the leak is characterized, not hidden.
     - **If (iii) fails** (a crash spawn persists): this does **not** repudiate the recalibration, which stands on the scale distinction and onset-latency independently (§4a). It is informative — the persistent lead is either a genuine crisis-coincident structural shift worth examining, or a persistent onset artifact. Principled responses, in order: examine the lead (it may be real); if artifact, the fix is a **faster β estimator** (EWMA / shorter window, §4a note 1) to shrink the onset leak at its source — **not** re-tightening the crisis level (undoes the recalibration) and **not** shrinking the gate's level window (imports level-noise into the common case to fix a rare one, eating the 2.7%-of-days property).
     - **Outcome (settled 2026-07-02 — this is not a milestone-3 failure).** (iii) flagged **7 of 10** crash spawns as persistent (Financials-heavy, into July–August 2020). A read-only `beta_diagnostic.py` (never wired into the sensor, with a planted-artifact discriminator test so the conclusion can't rot) ruled out the stale-β artifact: **0 of 7 collapse under a faster β** (pre-specified EWMA hl=63d and 63d rolling β, max Δ 0.033) — the β-strip's **second independent confirmation.** Trajectory: multi-quarter persistence into 2021, partial 2022 re-firing, near-zero yield correlation → a real **2020–2022 Financials/Materials/Real-estate sector regime.** Classification: **Box B — real macro/sector, not artifact, not the tech thesis → Path 1: no sensor change, the +593 signal untouched.** The test **routed correctly** — it flagged a real thing for human classification, which dispositioned it `off-thesis-real` (§5). **Persistent-but-classified is an acceptable disposition, not a gate failure.** `crash_revert_weeks` **stays 8**: the flags were resolved by *classification*, not by relaxing the window (which would be curve-fitting the test to the result). Whether 8 weeks is the right "transient" threshold on a 17-year horizon is a separate, non-blocking principle question, decidable only on its own merits.
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
4. **Holdings ingest (`ingest/holdings.py`) is the keystone — built.** It unblocked **dispersion** (built, shadow-wired), and it unblocks the three remaining M4 slices, each its own PR at a clean seam: **(a) rebalance holdings-diff accretion** (self-contained — reuses holdings ingest; forward-hash routing with no payload change; active leads read from the registry-materialized fold, §4d); **(b) mandate-diff → `mandate.changed`** (its own slice — gated on new surface: EDGAR prospectus-*text* fetch + `ingest/prospectus/` storage + text diff, §4d/§7); **(c) launch corroboration hook** (holdings-derived concentration + the *live* cross-stream lag — the **capstone**, its own PR and the hardest review because it carries the honest-test boundary, §4c). The NPORT-P quarterly cross-check stays the deliberately thin §3b stub. Suggested order: **rebalance-accretion → mandate-diff → corroboration-capstone**, then the §9 runner.
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
  docs/                # this spec (rev 8), decisions review rev 2, founding document, Appendices A + B
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
- **Verdict vocabulary (CONTRACT):** four values, three live meanings — `yes` / `watch` (on-thesis unproven, untouched) / `off-thesis-real` (real but off-thesis, catalogued, inert) / `noise`. `off-thesis-real` must never absorb `watch`. `verdict` never keys action; ceiling/paging key on `status`+`shadow`.
- **Macro catalog is context, never a trigger:** the `off-thesis-real` view is read-only context for human consultation — never a trade/tilt trigger, never an alert stream, never piped anywhere as actionable. And **single-factor β stays** — no multi-factor β to strip a macro regime (it is entangled with real tech signal; stripping it amputates signal).

**config/prospector.yaml (initial keys, defaults per this spec):** universe lists; window lengths (63/252/21); z_in 2.5 / z_out 1.0 per sensor; `stress_gate.window_days: 21`, `stress_gate.absolute_level: 0.85` (FROZEN — absolute, not baseline-relative; see §4a), `stress_gate.aging_monitor` = recent-window calm-regime p95 vs gate, reported each run (see §4a; reconcile the note's 0.81-vs-0.668 to the calm-regime definition); `dispersion.weight_coverage: 0.90`; `dispersion.shadow_days: 90`; `dispersion.paging: false`; `identity.retry_days: 10`; `oracle.active_lead_ceiling: 8`; snapshot cadence (`active: daily`, `quiet: weekly`); capture K=5, M=2, `max_searches_per_week: 60`, `monthly_budget_usd: <user>`; `backtest.corroboration_window_months: 24`, `backtest.crash_revert_weeks: 8`; sector→keyword corroboration map; email address; schedule times.

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

## Appendix B — Proto-clusters: modeling the substrate below the corpus (v2 design note)

*Captured 2026-07-03 for build against the day it is earned. This is a **v2** extension, downstream of a calibrated dispersion sensor and the §3b data resolution. The only thing v1 does about it is **bank its substrate** — the generous `dispersion.tick` payload (§4b). Do not build the interpretation before dispersion exists and is calibrated.*

**The idea: reach below the corpus.** The whole tool is built on ETFs because a fund is a curated, pre-packaged thesis — but that is also its ceiling: it can only see theses someone has already *packaged*, or (in v2 discourse) is already *discussing*. The constituent layer breaks the ceiling. A thesis that no one has packaged and no one is loudly discussing is still visible **in the substrate** — as a set of names that have started moving together across the existing sector boundaries. Prospector would watch the raw material its own corpus is an abstraction over. The payoff is large: this is a **deterministic, price-only route to *new-category* detection** — the hardest problem, previously filed entirely under v2/discourse/NLP. Emergent co-movement needs no language model; it is correlation, one level down.

**The critical reframe: the canary is a cluster, not a single name.** A single stock moves for a thousand idiosyncratic reasons — earnings, management, litigation, rotation — the exact noise the basket architecture was built to escape, and extracting thesis-level signal from one name swims against the current of the whole design. The signal is a **cluster of names co-moving *across* existing sector boundaries** — a **proto-basket / pseudo-ETF**. The single names are the *members*; the coherent cross-boundary co-movement is the *signal*. Bimodality-not-outlier, one level down: one bird bolting is noise, a covey rising together is the thing. And it is strictly more powerful than "watch some names," because a proto-basket can be modeled exactly like an ETF — a membership, a centroid, a dispersion you watch evolve — **before the ETF exists.** That is "model the substrate before we have an ETF," made concrete: the emergent cluster is a provisional fund you construct yourself.

**Worked example (NUKZ).** In 2023 there was no nuclear-plus-AI ETF. The proto-cluster layer would have constructed a pseudo-ETF from the co-moving names (nuclear / utility / data-center-power constituents cohering *across* the Tech and Utilities boundaries) and tracked it. When a real fund like NUKZ later launches, you check whether your pseudo-ETF *anticipated* it — and the lag from "these names started co-moving" to "someone finally packaged it" is the purest **recognition-latency** measurement the system can produce. (This is the same shift the §4a excess-correlation sensor already sees at the *sector* level via XLK×XLU; the proto-cluster layer sees it at the *constituent* level — earlier, and with an explicit, self-constructed membership.)

**The earliest possible T0.** Proto-cluster formation is *earlier than discourse* — names co-move before the linkage is even articulated, let alone packaged. So this gives the cross-stream lag its earliest anchor, and it slots straight into the launch corroboration slice (§4c): a launch can corroborate a **proto-cluster lead**, not only an `xcorr` or `dispersion` one. The full stream ordering becomes: proto-cluster formation → discourse → rebalancing → launch.

**Already fossilized — the one v1 action.** The substrate accrues from the moment dispersion goes live, with zero new capture, *provided the dispersion payload is generous* (§4b, now CONTRACT: full constituent membership, sub-cluster assignment, correlation structure — not just the scalar Q). Capture-now-interpret-later, one more time: bank the rich substrate now even though nothing interprets it until v2, because you cannot backfill a payload you did not capture (append-only forced-ordering, §5). A scalar-only tick would permanently blind the future layer to *which* names formed the proto-cluster and *how* they cohered.

**The discipline transfers wholesale — the tell that this is an extension, not a new project.**
- **Scope (policy-network → rollout, again):** never all-pairs across the universe (~125,000 constituent pairs vs. 55 sector pairs — instant oracle death). The cheap basket-level dispersion (11 baskets) *aims* the expensive constituent analysis; you drop to single-name detail **only inside a basket the sensor already flagged.** The proto-cluster layer is the rollout that the dispersion policy-network prunes toward.
- **Disposition (box-B applies one level down):** an emergent cluster is *real co-movement*, but whether it is an on-thesis new category or an off-thesis macro regime is the box-B call — a rates shock coheres Financials, Materials, and Real Estate too, real but not a tech thesis. The same `yes / watch / off-thesis-real / noise` vocabulary (§5) applies to proto-cluster leads unchanged.
- **Firewall (observation-only — and this is where it matters *most*):** single-name granularity is where over-trading *and* concentration risk both peak. For a survivability-first, 17-year owner, the correct response to a forming pre-ETF thesis is to **watch it and buy the diversified ETF when it packages** — accepting a touch of "lateness" — **never** to take a concentrated single-name bet whose "early-access premium" is just concentration risk repriced. The canary tells you where to look and buys you conviction and readiness for the moment an instrument exists; **it is never itself the trade.** This is the design constraint that keeps the proto-cluster layer from quietly becoming the stock-picking engine the barbell exists to prevent. (The owner's standing "not buying individual names" is not a hedge — it is this constraint.)

**The honest caveat (why it is build-later, beyond just "downstream of dispersion").** Historical validation of this layer inherits the delisted-constituent problem that already defers dispersion-PIT (milestone 3b) — and it is *worse* here: the acquired winners are exactly the small companies bought *because* their thesis turned out real, so they vanish from the survivor set, **biasing any backtest against the very signals you most want to detect.** Live-forward watching is clean; backtesting this layer is not, and must not be trusted until that data question is solved. So the substrate accrues live from day one (via the payload), but the *interpretation and any historical claim* wait — on a calibrated dispersion sensor and on survivorship-clean constituent data.

**Status.** v2. Downstream of a calibrated dispersion sensor and the §3b data resolution. **Current-build action: the generous dispersion payload (§4b) only.** Rushing the interpretation before dispersion is even calibrated would be premature and would risk building on an uncalibrated pre-filter.

---

*End of rev 8. The decisions review (rev 2, 2026-07-01) remains the canonical "why" and is unchanged. This spec is the canonical "what to build." Milestone 3 is passed; milestone 4 (holdings ingest → dispersion → rebalance) is the live path, with the launch corroboration slice and the Appendix B proto-cluster layer defined and deferred. The gate discipline stands: at each layer where it can lose, it must be able to.*
