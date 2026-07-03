# Project Prospector — Architecture, Findings, and Current State

*Canonical state-of-the-project record, 2026-07-02. Captures what Prospector is, what has been built (milestones 1–3 plus the verdict-vocabulary layer, 272 tests green), what the build has empirically found, the discipline that governs it, and where it stands. Detailed by request. Companion to the founding document, the decisions review, and the v1 build spec (rev 5); this document synthesizes across all of them.*

---

# Part I — The Idea

## 1.1 The premise (the load-bearing constraint)

The owner is investing on a **17+ year horizon** and wants **exposure to emerging technologies**, in the belief that this is a time of great technological change and innovation. He treats his own **over-trading as the primary risk**. This premise is not background; it is the parameter that determines nearly every design choice. It is what dissolves the central intellectual trap (below), what makes the tool's empty competitive niche empty, and what draws the hard line between *noticing* a structural shift and *acting* on one.

## 1.2 The consensus trap

The problem Prospector is built around: **any system that scans the world and ranks investment theses by the quality of their argument is selecting on how thoroughly a thesis has been documented — and documentation is positively correlated with how completely the thesis is already priced.** The better-argued the case, the more it has been written about, the more it is reflected in the price. A web-scanning thesis-ranker is therefore a machine for discovering *what everyone already knows*. Argument quality is not mispricing; it is adversely selected against it.

## 1.3 The resolution: novelty, not quality

Two moves resolve the trap for this owner:

1. **The horizon dissolves it.** A 17-year owner does not need mispricing or alpha; he needs durable, real, secular shifts he can own for two decades. **"Consensus-but-true" is acceptable** — a shift can be widely recognized and still be worth holding for twenty years. This alone defuses the trap, because it stops the tool from pretending to measure a mispricing it cannot see.

2. **Change the target from quality to novelty.** Detect *change as it forms* — which is, by construction, *before* consensus rather than after. The governing slogan: **novelty earns a look; reality earns a position.**

**[PRINCIPLE] Novelty is not interest.** Novelty is a measurable departure from a baseline; interest is whatever excites the operator — confirmation bias wearing a more flattering name. The system detects the former and is actively suspicious of the latter. A tool that only ever surfaced the operator's pre-existing interests would be a confirmation-bias engine, the opposite of what this is for.

## 1.4 The instrument: an ETF is a pre-packaged thesis

The organizing idea. The universe of exchange-traded funds is a **maintained, curated ontology** handed over for free: each fund is a holdings list (the entities/nodes), a mandate (the explicit thesis), a rebalance schedule (a professional curator continuously updating that thesis), and an issuer with a commercial stake in drawing the boundary well. This converts a vague "scan the discourse" problem into a tractable "watch a structured universe of baskets" problem — and it cleanly separates two detection problems that no single statistic could: **new edges** between known entities live *inside* baskets (co-occurrence/correlation territory), while **new entities** show up as *new fund launches* (curated, named, rare — no flooding).

## 1.5 Three streams on a consensus curve — the lag is the measured object

Baskets emit signals at different points on the journey from frontier to consensus, and **the quantity Prospector actually wants to measure is the lag between them:**

| Stream | Position | Character | Status |
|---|---|---|---|
| **Discourse** | earliest, noisiest | a linkage beginning to be discussed | **v2** — captured raw in v1, not interpreted |
| **Rebalancing / holdings** | middle | a professional quietly acting on it | v1 (rebalance sensor) |
| **Launches** | near-consensus | a fund packaging it — a dated public timestamp | v1 (launch sensor) |

A compressing inter-stream lag is a thesis accelerating toward consensus. The **barbell dodge** keeps the tool early: watch a few *broad* baskets as a wide early-coverage sensor array, and *thematic launches* as the consensus clock. (This watch-structure is the owner's own portfolio barbell pointed outward.)

## 1.6 The wall, the throughput asymmetry, and the scarce oracle

**[PRINCIPLE] The output is a reading list, never an order.** Prospector proposes *up*; it never executes *down*. The human keeps the one thing never delegated — the commitment to act. One decisive part of this wall is **structural, not habitual**: a generated lead becomes a position only by clearing the *identical* per-investment-thread discipline as any existing holding (written thesis, defined break-triggers, drawdown-proof sizing) — **the pipeline is the wall**, with no shortcut for being interesting.

The real risk is not the universe being large; it is a **throughput asymmetry**: generation is cheap and unbounded, adjudication is slow, costly, and human. The scarce resource is the human oracle, so the system is tuned to surface *little*, and **over-firing is treated as the characteristic failure mode.** The design is AlphaGo's two-part shape: a cheap always-on pre-filter (policy network — dispersion, cheap statistics) that ranks the firehose by a proxy for realness, so the expensive scarce evaluation (rollout — the human, and in v2 the multi-agent discourse search) lands on the most-robust candidates first.

## 1.7 The three-project skunkworks and the firewall

Prospector is one of three walled projects, and its never-execute wall is what keeps the separation coherent:

| Project | Domain | Polarity | Verb allowed |
|---|---|---|---|
| **Prophit** | FX microstructure | offensive | execute (currently research-only) |
| **Smoke detector** (yin) | equity book | defensive | GO-LOOK / silence |
| **Prospector** (yang) | equity frontier | offensive | "read this" |

The only project with an execute verb lives in the domain maximally distant from the 17-year book (milliseconds vs. decades, currencies vs. equities) — impulse-migration management by domain distance. Prospector is **firewalled**: its own repository, its own S3 bucket and IAM credentials (unable to read the detector's bucket or `portfolio.yaml`, enforced at IAM), its own email channel (not the detector's Discord), its own schedule and dashboard. The **only** connection to the portfolio is human and one-way — a lead graduates by passing the per-thread pipeline by hand; no code path exists for it.

## 1.8 Intellectual lineage (prior art)

None of the components is novel, which is reassuring rather than discouraging — a wholly unprecedented idea here would more likely be wrong than brilliant. The launch-timing insight has a direct empirical anchor: **Ben-David, Franzoni, Kim & Moussawi, "Competition for Attention in the ETF Space," *Review of Financial Studies* (2023)** — specialized ETFs launch just after peak theme-excitement and underperform ~30% risk-adjusted over five years, driven by overvaluation at launch. Prospector uses as *instrumentation* precisely the phenomenon that paper documents as investor harm: the launch is a consensus clock. The people who *buy* the timestamp lose; Prospector only reads it. Broader lineage: category comovement beyond fundamentals (Barberis, Shleifer & Wurgler, 2005), correlation-network structure in markets (Mantegna, 1999), burst detection in streams (Kleinberg, 2002). The contribution, if any, is the **assembly** — three streams ordered on a consensus curve, the inter-stream lag as the measured quantity, on a fossil-record substrate that scores its own forecasts.

---

# Part II — Architecture & Implementation

## 2.1 v1 scope (what is in, what is deliberately out)

**In:** three deterministic lead-spawners (excess-correlation, dispersion, launch); one accretion stream (rebalances); raw-but-uninterpreted discourse capture; an append-only event store with leads-as-folds; a four-value verdict vocabulary; weekly heartbeat + immediate state-change push; read-only dashboard; verdict CLI; a fixed starter universe; identity pinned to SEC series IDs; backtest mode.

**Out (deliberately — not to be "helpfully" added):** any LLM interpretation (no scouts, tagging, tag-minting, generated narrative — the only API use is capture plumbing, and *no model-generated text is ever persisted as data*); universe auto-expansion; sub-industry resolution; any write path into the detector/portfolio or read of `portfolio.yaml`; any "run now" or recompute-on-view surface; any component of Prophit's `models/` machinery.

## 2.2 The fossil record (the store)

**[PRINCIPLE] On a 17-year horizon with sparse feedback, the archive is the intelligence.** The store is the heart, and it is a better-built version of the spec's prose because its disciplines were **vendored from the sibling repo's `ltee_archive/`** (the trading ontology stripped, the schema inverted).

- **Immutable, event-sourced.** Nothing is ever edited or deleted. Corrections are new events. This makes both the machine's signals and the human's verdicts permanently and honestly **scoreable**, and it makes the record **hindsight-resistant by construction** — dated events cannot be rewritten to make an outcome look inevitable.
- **Closed envelope, open type.** Every event is a frozen five-field envelope — `{ts, lead, type, payload, schema}` — where `type` is an open string and `payload` a JSON blob. A new event type needs no migration; unknown types are raw-rendered and counted (in v1 the deterministic writers can't produce unknowns, but the panel exists from day one for v2's writers to plug into).
- **A lead is the fold over its event stream.** No mutable lead rows; state (`status`, `shadow`, `verdict`, counts, latest z, capture inventory) is computed by a deterministic fold (same events → same state, property-tested). The fold is **vocabulary-agnostic and forward-compatible** — a legacy or future verdict value still renders — so the verdict allow-list is a write-path gate, not a fold gate.
- **WAL-mode SQLite index + object store.** A local WAL SQLite registry is the queryable index (the `registry.py` pattern); durable blobs live in object storage. Critically, the events table is the **envelope with a JSON payload column** indexed on `(lead, ts, type)` — *not* Prophit's wide typed-metric columns, because the premise is unforeseen event types.
- **Write discipline (vendored verbatim):** atomic temp→fsync→rename per event with SHA-256; the SQLite file is snapshotted via the `.backup` API before upload, never raw-copied while WAL-active (a corruption bug otherwise shipped and found the hard way); uploads are fire-and-forget and never crash the run.
- **Reactive snapshots.** Materialized folds are snapshotted *densely while a lead is active, sparsely when quiet, immediately on any state change* — the LTEE three-tier density shape with the trigger inverted from Prophit's scheduled (curriculum epochs) to reactive, because Prospector cannot know when a fracture is coming.
- **Verdict succession.** Verdicts are append-only; a re-adjudication supersedes the prior via a `superseded_by` pointer (the `apex_history` pattern), so the *evolution* of judgment on a lead is queryable, not just the latest state.

## 2.3 Identity (the HECO rule)

**[PRINCIPLE] Fund identity keys on the permanent SEC series ID, never the ticker.** This exists because of a real natural experiment found early: etfdatabase's blurb for ticker `HECO` described an ESG/eco fund, while the *live* HECO is the State Street Galaxy Hedged Digital Asset Ecosystem ETF (crypto, launched 2024-09-09) — a categorically wrong, currently-serving description. Anchoring a baseline on such a source would manufacture a screaming false-positive departure (measuring the data provider's error, not the world).

- Registry key is the SEC series ID (with CIK and class IDs); tickers are display-only attributes. **A bare ticker is rejected at the write path** — nothing downstream (lead, baseline, event) may anchor to a ticker. This is the unskippable verify step.
- Resolution flow: ticker → EDGAR series/class lookup → confirm a prospectus filing exists → write registry entry.
- **Failed-resolution path** (EDGAR indexing lags brand-new funds, disproportionately the weird ones — exactly the targets): a failure emits `resolution.failed` to `_system` (failures land *in* the record, never silent), auto-retries daily for N days (`identity.retry_days: 10`), then enters a manual queue surfaced in the dashboard and heartbeat. Nothing evaporates.
- **etfdb as draft, primary source as truth.** etfdb categories seed a *draft* grid and rough membership; the constituent funds' prospectuses and holdings (EDGAR) overwrite the draft ("a draft that decays into truth as you verify"). etfdb's *category assignments* are treated as wrong too, not just its blurbs, so every category diff is verified against EDGAR before any event is written.

## 2.4 The sensors (deterministic writers)

All follow one discipline: **record on cadence, push on state change**, with Schmitt-trigger entry/exit (no flapping). All thresholds are config; the deterministic writers own countable facts (they cannot fabricate; they emit only pre-defined types).

**Excess-correlation (the inter-basket edge sensor — the one validated in milestone 3).** For each of the 11 sector ETF pairs (55 total): strip market beta (per-fund β over trailing 252d vs SPY) to get residuals; compute rolling 63d residual correlation; Fisher-z transform; measure departure as a z-score from the pair's own trailing-252d baseline. Entry z ≥ 2.5 spawns/activates a lead; exit z ≤ 1.0 reverts it (never deletes). This catches two sectors moving together *beyond* what their shared market exposure explains — a new linkage forming.

**Dispersion (the intra-basket fracture sensor).** Per basket: 63d constituent correlation matrix → spectral/hierarchical bipartition → cluster quality **Q = mean(within-cluster corr) − mean(between-cluster corr)**, measured as a departure from its own 252d baseline. This catches a category under strain (constituents fracturing into sub-clusters — the signature of a taxonomy starting to mis-fit reality). Q is a *bimodality* statistic (a clean two-cluster split), not plain variance. **Ships in shadow mode** for its first live quarter (records and spawns but does not page, is excluded from the active-lead ceiling), because survivor-biased calibration under-predicts live firing rates; promotion to paging is a human config flip that leaves a `config.changed` fossil.

**Launch (the consensus timestamp).** Two-phase to protect lag integrity: at detection, emit `launch.unverified` to `_system` with a `detected_at` timestamp (this never keys a lead — the identity rule holds); after resolution, emit the proper `launch` with the series ID and a back-reference. **All lag math uses `detected_at`, never resolution time** — a fund that takes nine days to resolve must not get a timestamp nine days late, because that timestamp is the datum the cross-stream lag is measured against. A launch whose concentration industries overlap a live lead's baskets also lands on that lead (the corroboration hook).

**Rebalance (accretion + audit).** Diffs issuer holdings (daily) and NPORT-P (quarterly cross-check); a material change accretes onto every live lead touching that fund. A new prospectus filing whose mandate text differs from the stored copy emits `mandate.changed` — **audit = detection**: the staleness check and the drift signal are one mechanism reading one diff.

## 2.5 The stress gate (frozen, absolute 0.85, crisis-only)

A market-stress annotation protects the oracle during genuine crises. It computes the 21-day mean *raw* pairwise correlation across the 55 pairs; above **an absolute level of 0.85**, departures are still *recorded* (`market_stress: true`) but do not spawn leads, count as state changes, or page. Its design carries three settled, non-obvious decisions:

- **[DECISION] Absolute level, not baseline-relative.** Baseline-relative (departure-from-trailing-norm — the frame used for the pair sensor) was tested exhaustively (windows 5/10/15 × baselines 63/126/252) and *every* construction fails identically — the tell that the failure is structural. The durable reason: the pair residual correlation is a **scale-free** quantity (only its change is interpretable), whereas market-wide correlation is a **fragility gauge with an intrinsic scale** — a market at 0.95 average sector correlation is one where diversification has collapsed, i.e. stressed *whatever last month's level was*. **The level is the signal.** Normalizing by trailing variance destroys exactly the quantity you want (range compresses so COVID caps at ~2.5σ; crisis-ordering breaks). This is the absorption-ratio / correlation-concentration family (Kritzman–Li), used in systemic-risk practice as absolute levels, never trailing-normalized.
- **[DECISION] Level 0.85, because onset latency is the binding constraint.** The gate's demoted job is crisis-only — catching the two things the (proven-clean) β-strip cannot during acute crisis: crash-onset β-staleness and liquidity dislocations, both acute-onset. 0.85 gives ~5-day onset, fires on COVID and the acute Aug-2019 scare, sits just above calm-regime p95 (~0.67) with the 2022 grind correctly below, gates ~2.7% of days. 0.90 rises too slowly (~10 days); 0.80 catches the 2022 slow bear grind (a *sustained* regime deliberately left un-gated, because in sustained-high-correlation stretches the idiosyncratic departures are disproportionately the structural shifts most worth surfacing).
- **[DECISION] Aging watch-item.** Absolute levels age; ETF/index-driven co-movement may raise the calm baseline toward the gate. The backtest reports each run the p95 of correlation over *recent non-crisis days* and its margin to the gate (~0.18, healthy). If the margin compresses, the level is **deliberately re-frozen higher by a human** — *never* a rolling percentile, which would reintroduce the baseline-relative failure. Machine surfaces drift; human moves the level.

## 2.6 The verdict vocabulary (four values, three live meanings)

The missing verb: the human's adjudication, recorded as append-only events (a memory prosthesis, and the thing that makes the human scoreable). Just enriched from the original `yes/no/watch` because "no" was overloaded — it could not distinguish *junk* from *real-but-off-thesis*, and collapsing those threw information away.

| Verdict | Meaning | Live? | Action |
|---|---|---|---|
| `yes` | promoted — real, on-thesis | live | enters the per-thread pipeline (human) |
| `watch` | **on-thesis but unproven** — a candidate not yet cleared | **live, untouched** | stays under observation |
| `off-thesis-real` | **real but off-thesis** (macro/sector regime) — catalogued, inert | set aside | recorded as context; *no action ever* |
| `noise` | not real (the refined "no") | dead | closed |

**[PRINCIPLE] Three live meanings must stay distinct.** The critical implementation guard: `off-thesis-real` (real, permanently set aside — the cap-weighted core absorbs it) must never absorb `watch` (possibly-on-thesis, still live). Collapsing them would let a deferred real tech lead rot under a "macro" label. `VERDICT_VOCAB` in `fold.py` is the single source of truth; the CLI rejects the retired `no` and unknowns; the help text spells out why `off-thesis-real` and `watch` are distinct.

**Context, never a trigger — enforced by construction.** Nothing keys on `verdict` to drive action: the active-lead ceiling and paging key on `status`+`shadow` (via `active_nonshadow`), and `off-thesis-real` never flips status. So the discipline is structural, not merely a written rule — a test proves the disposition is inert. (This is the resolution of the box-B finding; see Part III.)

## 2.7 Outputs

- **Email — weekly heartbeat + immediate pushes.** The heartbeat fires *every week regardless of activity* (the dead-man's switch: the subject encodes state, so *silence beyond 7 days unambiguously means broken*, never calm). State changes and faults push same-day. Rendering is deterministic templating of folds — no generated prose, honest by construction. This cadence is deliberately anti-engagement: a tool built to reduce trading must not become a slot machine.
- **Dashboard — read-only Streamlit.** Renders stored snapshots and event streams; **no recompute on view, no autorefresh, no run-now** (the discipline variable is computation cadence, not display richness — the deliberate inversion of Prophit's autorefreshing live cockpit). Panels: ranked active leads, per-lead event timeline (thaw-backward), the dispersion shadow panel, the manual-resolution queue, registry health, capture inventory, the unknown-type panel, and the fault log. The `forensics.py` query shapes (`lineage_trajectory`, `cross_lineage_at_epoch`, `extinction_report`) port directly as these views.
- **CLI (`pros`).** Read-only lead inspection plus verdict entry (append-only; a changed mind is a new superseding event) and manual identity resolution. **No capture-trigger command, no run-now command.**

## 2.8 Discourse capture (v1: capture, not interpret)

v1 freezes raw discourse on cadence **without interpreting it** — deterministic-templated queries (no LLM authorship) targeted at structural hits, persisting only raw search-result blocks and fetched page text (any model prose from the plumbing is discarded). This preserves the cadence backbone so v2's retrospective interpretation has an archive to thaw backward through, without paying the expensive, fabrication-prone interpretation cost up front — *"late-arriving meaning is free"* applied to the discourse stream itself. A hard budget guard caps searches/spend and emits a `fault` on breach (never silently overrun, never silently skip).

## 2.9 What is deferred

- **Milestones 4–7:** the remaining sensors wired live (dispersion shadow, two-phase launch, rebalance) → outputs (email/dead-man/dashboard/CLI) → discourse capture + budget guard → infra-as-code deploy.
- **Milestone 3b (dispersion PIT calibration):** needs survivorship-clean point-in-time historical holdings (quarterly NPORT-P back to ~2019) and free price coverage for *delisted* constituents — genuinely gated on data availability. Dispersion ships shadow-mode meanwhile.
- **v2:** the discourse *interpretation* layer (multi-agent scouts under a falsifiable-artifact tag-minting protocol), universe auto-expansion along holdings-graph edges, sub-industry resolution, and the full discourse→structure lead-time (the earliest and most valuable signal).

---

# Part III — Findings

The empirical arc so far, in order. The through-line: **every step left a fossil, nothing was auto-tuned, and nothing was surfaced as an order.**

## 3.1 Milestone 3 — the instrument works (recall confirmed)

The first real validation replayed the excess-correlation sensor over six years (2019–2024) of actual EOD prices across all 55 sector pairs. Its narrow, cheap purpose: establish whether the instrument can see a *known* past structural shift form, before building four more subsystems on it.

- **Recall — confirmed.** The Tech–Utilities pair (XLK×XLU) departs its baseline on **2023-01-25 at z 2.52**, well before "AI needs power" was a market cliché. The sensor sees Tech and Utilities decouple from the broad market and re-couple to *each other* — the structural fingerprint of the data-center power build-out — while it was still forming.

## 3.2 The β-strip placebo — run before calibration, and it held

Before tuning any threshold, the build ran the test that could invalidate everything: does the market-beta strip actually remove the common factor, or do all sectors merely co-move in a crash (making every "signal" a crash artifact)?

- **Mean pairwise residual correlation collapses to ≈0 in every window, including the March-2020 crash (raw 0.88 → residual −0.035).** So the 54/55 pairs that cross threshold over six years are genuine idiosyncratic departures, not beta leakage, and firings do not cluster in stress windows. **This settled the key methodological fork:** the remaining work is gating and surfacing discipline, not the estimator. Running the null test *before* the calibration is the discipline the whole project turns on.

## 3.3 The stress-gate recalibration — an instructive miscalibration, fixed on principle

A placeholder stress gate at raw-correlation **0.65** was found to gate nearly a quarter of all days — because sector ETFs are structurally ~0.5–0.65 correlated even in calm times — and it *suppressed the real 2023 signal*, slipping XLK×XLU's first recorded firing to late 2024 and inverting the measured lead to **−58 days** (the tool appearing to *trail* the fund it should have anticipated).

- The fix (see §2.5): reassign the crash-defense job to the proven-clean β-strip, demote the gate to crisis-only, and re-specify it as an **absolute level 0.85** (the scale distinction). Recalibrated, the lead flips to **+593 days — ~19.5 months ahead** of TEKX's 2024-09 launch.
- **[PRINCIPLE] Observed, not targeted.** The recalibration was authorized because a *proof* (the β-strip diagnostic) redefined what the gate is *for* — not because tuning made the answer prettier. It is validated against the *concept* (fires on genuine crises, quiet on ordinary calm days), never against the single known case. The **recall-independence check** is the license: the 2023 signal (market-wide correlation 0.667 that day) stays ungated at 0.80/0.85/0.90 alike, so the choice cannot be a case-fit. The +593 result is a *readout*, not an objective.

## 3.4 Precision — honestly unmeasurable, honestly reported

Of 98 firings, only **2 auto-score as "structural"** — but this is a *floor artifact*, not a verdict. The cross-stream corroboration set holds only three verified fund launches (all 2024), so almost nothing that fired before mid-2024 *can* be corroborated yet; the two that do (XLI×XLRE, XLI×XLK, both bridging TEKX's infrastructure/data-center/technology cluster) are exactly the AI-power pairs.

- **[PRINCIPLE] The corroboration score is a witness, not a judge — never optimize it.** It bakes in "packaged = real," a lagging and incomplete proxy: a genuine shift the market never wraps in a fund would score as junk. The human verdict is ground truth; the auto-score is a hint, and the day it is optimized against is the day a consensus-chaser is quietly rebuilt inside the anti-consensus tool.
- **A caught bug, corrected against interest:** adversarial review found the corroboration matcher letting the 2-character token `ai` match *inside* `retail`/`entertainment`, inflating the structural count from a true 2 to a false 8. Short tokens now require a word boundary; the honest number is 2. The record is built so it cannot silently flatter itself.

## 3.5 The re-armed falsifier and the box-B finding

When the stress gate was recalibrated, the March-2020 falsification test (5c) had its premise overturned — "zero crash-window spawns" had operationalized "the β-strip works" under the retired assumption that the gate suppresses the whole crash. The test was **amended to keep its teeth**: β-strip-clean is *necessary but not sufficient* (idiosyncratic ≠ structural — a crash produces transient idiosyncratic co-movement that is not a durable thesis), so the amended criterion requires crash-window spawns to be **transient (they revert)** rather than persisting as durable leads — a criterion that can still *fail*, and must be *verified*, not assumed.

- **It flagged.** 7 of 10 crash-window spawns persisted (Financials-heavy — XLF×XLU, XLF×XLRE, XLF×XLP, XLB×XLF, XLI/XLB — into July–August 2020). **The test did not fail; it routed** — it flagged a real thing for human classification, exactly as a router to adjudication should.
- **The diagnostic — three boxes, not two.** A read-only `beta_diagnostic.py` (never wired into the sensor, with a planted-artifact discriminator test so the conclusion can't silently rot) decisively ruled out the stale-β **artifact** box: on the 7 pairs, residual correlation is essentially unchanged under a faster β (pre-specified EWMA hl=63d and 63d rolling β) — **0 of 7 collapse, max Δ 0.033.** This is the **β-strip's second independent confirmation, by a different mechanism.** Trajectory analysis showed multi-quarter persistence into 2021 with partial 2022 re-firing and near-zero yield correlation → a real **2020–2022 Financials/Materials/Real-estate sector regime.**
- **Box B: real macro/sector regime — not artifact, not the tech thesis.** Resolution is Path 1: **no sensor change, no EWMA swap, no milestone-3 re-run, the +593 signal untouched.**

## 3.6 The disposition advance — "off-thesis" is not "worthless"

The box-B finding forced a refinement that is arguably the most valuable conceptual output of the whole crash-flag episode: **"not a tech thesis" and "not valuable" are different claims**, and the initial "file and move on" quietly conflated them.

- **[PRINCIPLE] A macro regime is not common-mode noise to be stripped like market beta.** The entanglement argument: the AI-power build-out is *both* an emerging-tech linkage *and* rate-sensitive infrastructure capex, so regressing the macro regime out would **amputate real tech signal**. This is an independent, principled reason the **single-factor β-strip stays and a multi-factor β is wrong here** — not merely unnecessary, but actively destructive of signal. The regime flips from *discard* to **the reference frame a future tech signal is read against** (the excess-vs-common-factor logic one level up, done in human judgment).
- The value, located: a macro catalog serves as a **reference frame** (a tech linkage forming *against* a hostile regime is stronger evidence than one riding the tide), a **labeled negative set** (what real-but-macro looks like, so the next rates echo isn't mistaken for a tech linkage), **recorded memory** (a recurrence in 2027 surfaces the 2020 verdict), and **cross-twin context** (when the smoke detector must judge whether a NUKZ/XBI drawdown is a thesis break or a regime drawdown, the catalog distinguishes them — human-mediated, firewall intact).
- **The boundary — context, never a trigger.** The same 17-year premise that makes macro *off-thesis* also says *don't act on it* — a passive, **cap-weighted core already absorbs sector-regime shifts automatically**, so the correct action on a detected regime is *none*. The seductive overreach — "detect the next regime early and tilt ahead of it" — is the market-timing trap in a data-science coat, and a macro-regime *alert stream* would rebuild the cockpit the whole design refuses. This is now enforced by construction (§2.6) and stands as a hard line in `CLAUDE.md`.

---

# Part IV — The Operating Discipline

The cross-cutting rules and patterns that govern the whole system. These are not decoration; each was earned, usually by nearly making the opposite mistake.

## 4.1 The recurring meta-pattern

Nearly every design fork resolved the same way, and recognizing the shape is the single most useful lens on the project: **model normal and flag departure; let a cheap always-on signal aim the expensive triggered one; freeze the substrate and defer the interpretation; let the human ratify; and never let the present rewrite the past.** Prove-it-cheap, append-only, dispersion-aims-the-graph, envelope-and-open-type, capture-now-interpret-later, the deterministic core before the agentic layer — all the same shape.

## 4.2 The falsifier must be able to fail

The property that separates this from a curve-fit. A test that cannot lose is worthless. When the recalibration overturned test 5c's premise, the amended test was deliberately built to *keep its teeth* (reversion, verified not assumed) rather than replaced with two facts already known to pass. The falsifier then earned its keep by flagging box B on its first live crash. **[PRINCIPLE] Model normal / flag departure is only honest if the flag can catch you.**

## 4.3 Observed, not targeted — the anti-fitting discipline

The exciting result is the one to be most disciplined about not reaching for. The +593-day lead and the box-B classification were both *observed as consequences* of principled choices, never *targets*. Thresholds are set on the concept (crises vs calm; transient vs durable), then the interesting number is *read off*. Tuning a threshold until one labeled example lights up is curve-fitting to n=1 — and the recall-independence check exists precisely to prove a choice wasn't that.

## 4.4 Cite-or-fault, and correcting against interest

Load-bearing claims are verified at primary source, and the system is built so its own record cannot silently flatter it: the precision bug was corrected *downward* (8→2) against interest; box A was ruled out by a *planted-artifact-tested* discriminator so "not stale-β" can't rot; the β-strip is now confirmed *twice by two mechanisms* — the "two independent derivations" standard. When search or diagnostic corrects a prior claim, the correction is recorded, not buried.

## 4.5 Reconstructed path, never demonstrated cause

The permanent epistemic ceiling, honestly named. This is a read-only fossil record; unlike a controlled experiment (the Lenski LTEE analogy, where a frozen ancestor can be regrown and evolution re-run), history cannot be re-run. Prospector reconstructs the *path* a shift took; it can never *demonstrate the cause*. This is written into the metric on purpose, because a read-only record is dangerously good at letting hindsight draw an elegant inevitable line backward and mistake it for a law. Relatedly, the whole apparatus is still validated against essentially **one known shift** — success on one case *fails to refute*, it does not confirm; the real test is prospective and accumulates.

## 4.6 Context, never a trigger

The load-bearing wall, in its most general form. The tool *notices*; the human (and, for regime shifts, the cap-weighted core) *acts or absorbs*. No information the tool surfaces — not a lead, not a macro regime — is ever piped anywhere as actionable. The reading-list wall, the firewall between the twins, and the macro-catalog hard line are all instances of the same rule.

## 4.7 Capacity minimalism and interpretability

Prospector is deliberately capacity-*minimal* where its sibling Prophit is capacity-maximal — the domain inversion (a few hundred regime-relevant observations per decade vs. millions of ticks per day) inverts the bias-variance regime, so the modeling machinery (Mamba/SSM, neural SDEs, sliced-Wasserstein OOD) that is correct there is overfitting risk *and* forbidden opacity here. What crossed the domain gap from Prophit was the **record-keeping discipline, not the intelligence** — the LTEE archive plumbing, not any model. A z-score against a frozen baseline *is* the OOD primitive at the right capacity; the fancy distance is refused. On a 17-year horizon with sparse feedback, legibility and pre-registered falsifiers are what you survive on, because outcome-feedback arrives too slowly to correct you.

---

# Part V — Current State & Roadmap

## 5.1 Where the 17-year arc stands

Every step has left an auditable fossil, and each of the milestone-3 questions is answered:

- **Recall proven** — the instrument sees structure form (XLK×XLU, 2023-01-25, +593-day lead).
- **The measure is sound** — the β-strip is confirmed *twice*, by two independent mechanisms (the March-2020 aggregate placebo, and the faster-β diagnostic on the flagged pairs).
- **The gate is recalibrated on principle** — absolute 0.85, crisis-only, frozen, with an aging monitor and the explicit no-auto-tune rule.
- **The falsifier is re-armed with teeth** — and its first live flag was correctly *routed* and classified as real-off-thesis-macro, captured as context and acted on nowhere.
- **The verdict layer is correct before more surface builds on it** — four values, three live meanings, `off-thesis-real` structurally inert, `watch` preserved.

Nothing was auto-tuned; nothing was surfaced as an order. The core question the project set out to answer — *can secular structural change be detected as it forms, cheaply, from the topology of how markets and their packaging move, early enough to matter and honestly enough to know when it is wrong?* — has its first, affirmative, appropriately-humble data point.

## 5.2 Built vs. pending

**Built (milestones 1–3 + verdict layer, 272 tests, all offline):** the fossil record (envelope, WAL-SQLite index, deterministic fold, reactive snapshots, atomic writes, `.backup`-safe upload, `pros` CLI); the identity layer (EDGAR client, series-ID registry with the HECO rule, retry-then-manual resolution, two-phase launch); the excess-correlation sensor (β-strip → residuals → 63d correlation → Fisher-z → 252d-baseline departure z, Schmitt trigger); the frozen stress gate; the backtest runner and the full three-part milestone-3 acceptance gate; the read-only `beta_diagnostic.py`; the four-value verdict vocabulary with structural inertness.

**Pending:** milestones 4–7 (dispersion shadow-wired · two-phase launch live · rebalance → email/dead-man/dashboard/CLI → discourse capture + budget guard → infra-as-code); the milestone-5 macro-catalog (a forensic query over `off-thesis-real` verdicts + one read-only panel) and the formal spec rev 6 folding the verdict vocabulary into the spec's §5/§8c; milestone 3b (dispersion PIT calibration, gated on delisted-constituent data); and the entire v2 discourse-interpretation program.

## 5.3 Immediate next step

The path is clear to **milestone 4** (dispersion shadow-wired, two-phase launch, rebalance). Milestone 3b remains deferred on data availability, and dispersion ships shadow-mode until it is calibrated, so 3b is not a blocker. The verdict-disposition work that would naturally accompany milestone 5 (the macro catalog panel) is specified and ratified, awaiting its milestone.

---

*Closing note. The distinguishing property of this project is that it is engineered, in writing, before building, to be able to **lose** — falsifiable at every layer, with an immutable record that grades its own calls and metrics that refuse to flatter themselves. That is an unusual stance for anything built around markets, and it is the property that makes the whole thing either worth taking seriously or worth cleanly refuting. So far, at each layer where it could have lost, it has instead surfaced something true — including, tellingly, a real structural shift that was not the one being hunted, correctly recorded as context rather than acted upon. The tool notices; the human decides; the core absorbs; the record remembers. That division is the whole design.*
