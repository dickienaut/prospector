# Project Prospector — Architecture, Findings, and Current State (rev 5)

*Canonical state-of-the-project record — **rev 5, 2026-07-08** (rev 4 was 2026-07-04; earlier revs before). Captures what Prospector is, what has been built, what the build has empirically found, the discipline that governs it, and where it stands — with every claim in §5 sorted by **register** (built / queued / deferred-named / aspirational-v2), so the record neither overclaims nor underclaims. **As of rev 5 the system is live and firing:** milestones 1–4 + the SOI resolver + the **M5 runner** are built, a real `pros run` fired 5 live leads on the actual SPDR grid, and a wave of going-live bugs (N1–N10) has been found and fixed — **499 tests green.** Companion to the founding document, the decisions review, and the v1 build spec (**rev 14** — the canonical build instructions; this document is the orientation / status / roadmap synthesis over it). Detailed by request.*

**What changed since rev 4 (for the returning reader):** the whole **M5 runner arc landed, and the system went live.** The runner (`prospector/runner/`) is the §9 cadence driver — config-honesty → ingest → sensors → identity retries → snapshots → `state_changed`-pinned push, with soft-fault/dead-man discipline and no run-now surface. Wired onto it, in order: **SOI-fetch** (§9b — the deferred fetch finally gets its consumer, `resolve_soi_target`, with the anchor-stem + header-variant robustness); the **identity-integrity fixes** (I1 series-threading, B1/B2, `ambiguous_symbol` fault); the **§9d deferred SOI-corroboration retry** (fires on real sectors, reaches back with `detected_at`=T2, `fires-not-called` proven); the **§9c mandate frozen-prior invariant**; the **prices vertical** — **Tiingo is now the primary source** (CRSP split+dividend-adjusted close, verified against the NVDA-2024 split; Yahoo demoted after it turned out to bot-challenge non-browser clients on a TLS fingerprint, not a rate-limit; Stooq guarded-off) with source-specific throttle/backoff — and **xcorr wired LIVE** (§4a, the primary spawner: pages, counts toward the §8a ceiling). Then the **read-only dashboard** (§11). **First contact with reality:** a real `pros run` fired **5 live xcorr leads** on the SPDR grid (XLU×XLV, XLRE×XLY, XLC×XLF, XLC×XLV, XLRE×XLV — the correlated structure collapses 5 into ~2–3 independent events, XLV recurring). A QA pass (Claude Science) then found, and the build fixed, a wave of **going-live bugs (N1–N10)**: the read-only firewall was violated *by the viewer* (now OS-enforced `mode=ro`), the tick wasn't idempotent (now dedups on the stable series-id, moving-clock-proof), a duplicate-date row could fabricate a correlation observation (now guarded), the Tiingo retry set was mis-sized for a per-hour cap (now source-specific), and more — **each fix landing with the violation-test that would have caught it. 499 tests green.** **The honest status: the system is live and firing, but almost everything it claims is still *unfalsified* — the firing is n=1, the false-discovery rate is unmeasured; falsifiability is demonstrated, profitability is not.** §5 is fully refreshed to this state, in registers; the marching orders (§5.3) now begin at **§9e** (dispersion + the holdings/constituent-price vertical).

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

## 1.9 Reaching below the corpus (v2 direction)

The ETF corpus is the tool's power *and* its ceiling: a fund is a curated, pre-packaged thesis, but the tool can only see theses someone has already *packaged* (or, in v2, is *discussing*). The **proto-cluster / pseudo-ETF** direction reaches below that ceiling. A thesis no one has packaged and no one is loudly discussing is still visible **in the substrate** — as a *cluster of names co-moving across the existing sector boundaries*, a pseudo-ETF you construct yourself. This is a **deterministic, price-only route to *new-category* detection** — the hardest problem, otherwise filed under v2/discourse/NLP — because emergent co-movement needs no language model; it is correlation one level down. The critical reframe (and the answer to why the whole tool went basket-level to begin with): **the canary is the cluster, not the single name** — one stock is idiosyncratic noise, but a covey rising together is signal, and a proto-basket can be modeled like an ETF (membership, centroid, dispersion) *before the ETF exists*. It is the earliest possible T0 for the cross-stream lag (co-movement precedes even discourse), and the whole discipline transfers unchanged: cheap basket-dispersion aims the expensive constituent analysis (never all ~125k pairs), box-B disposition applies one level down, and the firewall matters *most* here — single-name granularity is where over-trading and concentration risk both peak, so the canary is watched and the *diversified ETF* is bought when it packages: **the canary is never the trade.** This is **v2**, downstream of a calibrated dispersion sensor and survivorship-clean data; the only thing the current build does about it is **bank the substrate** via the generous dispersion payload (§2.4). Full design note: spec Appendix B. Worked example: the 2023 nuclear+AI cluster, before NUKZ existed.

---

# Part II — Architecture & Implementation

## 2.1 v1 scope (what is in, what is deliberately out)

**In:** two deterministic lead-spawners (excess-correlation, dispersion); the launch stream as corroboration + consensus-clock (accretes on a holdings match, records dormant on no-match — never a standalone, ceiling-counting lead); one accretion stream (rebalances); raw-but-uninterpreted discourse capture; an append-only event store with leads-as-folds; a four-value verdict vocabulary; weekly heartbeat + immediate state-change push; read-only dashboard; verdict CLI; a fixed starter universe; identity pinned to SEC series IDs; backtest mode.

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

**Launch (consensus timestamp — recording + corroboration built; running live in the runner).** A launch is *near-consensus by construction*, so the launch stream is **corroboration + consensus-clock, not an early lead-spawner** — it never spawns a standalone, ceiling-counting lead (the two early spawners are excess-correlation and dispersion; the §8a ceiling is governed by them alone). The sensor splits, with a *forced* build order (you cannot backfill *when* a fund launched — an un-watched timestamp is gone forever). The **recording half is built**: detection + two-phase `launch.unverified`→`launch` on `_system` with `detected_at` nailed *before* resolution (all lag math uses `detected_at`, never resolution time). The **corroboration half is built** (and its blank-sector-active-fund case is resolved via the SOI path — §5): concentration is **derived from the launch's first holdings, not parsed from prospectus prose** (look-through-is-truth; HECO the proof a stated identity can lie), and corroboration is a direct sector-set overlap — **match → accrete onto the live lead** (making the cross-stream lag measurable on that lead), **no match → record dormant** for deliberate survey, no verdict, no ceiling slot. Honest boundary (CONTRACT): the backtest's +593 lag came from *curated fixtures*, so the corroboration hook and the *live* lag ship **with** that slice, tested against live behavior — never a hook wired to a fixture whose only green test never occurs live.

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

*(Current build status is the single-source responsibility of §5; this lists only what remains **genuinely deferred** as of rev 5 — the M5 runner, its sensors, and the SOI resolver are all built and live, see §5.)*
- **Milestone 5 remainder:** **§9e** — dispersion wired into the runner (shadow-mode + the 90-day burn-in clock), which pulls in the **holdings/constituent-price vertical** (where holdings-intake coverage is finally confronted as its own slice); and **§10** — the real email sender (weekly heartbeat/dead-man + state-change push, carrying the nuisance-alarm suppression criterion).
- **Milestones 6–7:** discourse capture + budget guard (M6) → infra-as-code + **scheduled** deploy (M7), where the runner stops being a manual `pros run`. Two items are explicitly deferred to M7: the SOI-corroboration **cadence gate** (0 cost today — the dormant pile is empty) and the runner-side **WAL-checkpoint** for serving the store from read-only *media*.
- **Milestone 3b (dispersion PIT calibration + NPORT-P parser):** needs survivorship-clean point-in-time historical holdings (quarterly NPORT-P back to ~2019) and free price coverage for *delisted* constituents — genuinely gated on data availability, and *worse* for the proto-cluster layer (§1.9), where the acquired winners vanish from the survivor set exactly when their thesis was real. Dispersion ships shadow-mode / live burn-in meanwhile; the NPORT-P parser is a deliberately thin stub, not an unfinished edge.
- **Broader holdings-intake coverage:** a real but **secondary** widening (per-issuer parsers / NPORT-P) — the SOI path already resolves the active-fund sector case; widening turns the live lag from existence-proof toward a representative rate.
- **v2 (aspirational, walled off — captured as ideas, not queued):** the proto-cluster / pseudo-ETF layer (§1.9; its substrate already accrues via the dispersion payload, so nothing to build now but keep capturing) and the discourse-interpretation program.
- **v2 — discourse interpretation:** the discourse *interpretation* layer (multi-agent scouts under a falsifiable-artifact tag-minting protocol), universe auto-expansion along holdings-graph edges, sub-industry resolution, and the full discourse→structure lead-time.
- **v2 — the proto-cluster / pseudo-ETF layer (§1.9, spec Appendix B):** constituent-level new-category detection below the corpus, observation-only. Its substrate is *already accruing* via the generous dispersion payload, so the only current-build action is to keep capturing; the interpretation waits on a calibrated dispersion sensor and survivorship-clean data.

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

Milestones 1–4 are complete, the **SOI resolver** is in, and — new since rev 4 — the **M5 runner is built and the system is live**: a real `pros run` fires the sensors on a cadence, pages on state change, and has produced its first real leads. Every step has left an auditable fossil. The milestone-3 questions are answered:

- **Recall proven** — the instrument sees structure form (XLK×XLU, 2023-01-25, +593-day lead).
- **The measure is sound** — the β-strip is confirmed *twice*, by two independent mechanisms (the March-2020 aggregate placebo, and the faster-β diagnostic on the flagged pairs).
- **The gate is recalibrated on principle** — absolute 0.85, crisis-only, frozen, with an aging monitor and the explicit no-auto-tune rule.
- **The falsifier is re-armed with teeth** — and its first live flag was correctly *routed* and classified as real-off-thesis-macro, captured as context and acted on nowhere.
- **The verdict layer is correct before more surface builds on it** — four values, three live meanings, `off-thesis-real` structurally inert, `watch` preserved.
- **The runner is live (M5).** The §9 cadence driver runs config-honesty → ingest → sensors → identity retries → snapshots → `state_changed` push, stateless between runs, soft-fault-per-unit with a dead-man that still pushes on a fatal, no run-now surface. SOI-fetch (§9b), the §9d corroboration-retry, the §9c mandate frozen-prior invariant, the Tiingo prices vertical, and **xcorr wired live and paging** are all on it. **499 tests green.** (Dispersion is built but not yet wired live — that's §9e, queued — so its 90-day burn-in clock hasn't started; the mandate frozen-prior and the corroboration retry-loop, formerly owned by the "not-yet-built" runner, are now built and running.)
- **First contact with reality — and it fired.** A real `pros run` on the live SPDR grid produced **5 live xcorr leads** (XLU×XLV, XLRE×XLY, XLC×XLF, XLC×XLV, XLRE×XLV). This is the crossing from a system *reasoned about* to a system *tested against the world* — and reality immediately corrected it (the Yahoo TLS-fingerprint bot-challenge that forced the Tiingo pivot, then the N1–N10 going-live bugs, all found and fixed). The existence proofs stand — recall (+593 on real sectors), and now the runner end-to-end on live data — but they remain **existence proofs, not rates**: the firing is n=1 (one tick, leads at the z 2.5–3.1 threshold, the correlated structure collapsing 5 into ~2–3 independent events with XLV recurring).

**The honest epistemic status.** The system is live and firing, but almost everything it claims is still *unfalsified*: the firing is n=1, the false-discovery rate is unmeasured, and the edge question is unanswered. What has been demonstrated is **falsifiability** — the system knows when it is wrong (it soft-faults, it flagged its own Yahoo block, it surfaced its own going-live bugs) — **not profitability.** Those are different properties, and only the first is shown. Nothing was auto-tuned; nothing was surfaced as an order. The core question the project set out to answer — *can secular structural change be detected as it forms, cheaply, from the topology of how markets and their packaging move, early enough to matter and honestly enough to know when it is wrong?* — now has its instrument **live and producing real data**; converting that data from an existence proof into a measured rate is the work the runner exists to enable, and it has barely begun.

## 5.2 Status by register — the single source of truth for what's built

**BUILT (499 tests, all offline) — milestones 1–5-runner:**
- *Foundation (M1–3 + verdict):* the fossil record (envelope store, WAL-SQLite index, deterministic fold, reactive snapshots, atomic writes, `.backup`-safe upload, `pros` CLI); the identity layer (EDGAR resolution, series-ID registry with the HECO rule, **series-threaded** launch, retry-then-manual queue, `ambiguous_symbol` fault); the excess-correlation sensor + frozen stress gate; the backtest runner + the full three-part M3 gate; the read-only `beta_diagnostic.py`; the four-value verdict vocabulary with structural inertness.
- *M4 sensors + the SOI resolver:* `ingest/holdings.py` (keystone — SPDR daily file → 90%-weight membership, freeze-before-parse, series-ID-keyed, **xlsx-capable**); `sensors/dispersion.py` (**built, shadow-designed — not yet wired live**; canonicalized bipartition, generous `dispersion.tick` payload, shared Schmitt); `sensors/rebalance.py` + `sensors/mandate.py` (accretion — holdings-diff and strategy-section-diff, pinned `beautifulsoup4`); `sensors/launch_corroboration.py` (the capstone — holdings-derived sectors → both-sides overlap → accrete + the signed cross-stream lag); `ingest/soi.py` + `sensors/soi.py` (the SOI resolver — GICS-industry rollup through a frozen 74/74-verified table; puts the +593 on real sectors).
- *M5 runner (new this arc):* `prospector/runner/` — the §9 cadence driver (CONTRACT run-order, soft-fault/dead-man, no run-now); **SOI-fetch** wired (§9b — `resolve_soi_target`, typed reasons, unique-stem anchor, header variants); the **§9d** deferred corroboration retry (reaches back, `detected_at`=T2); the **§9c** mandate frozen-prior invariant; the **prices vertical** (Tiingo primary, CRSP-adjusted, split-verified; source-specific throttle/backoff; **Tiingo key read from the environment, never committed** — CONTRACT; Yahoo/Stooq demoted); **xcorr wired live** (§4a — pages, ceiling-counting, universe series-ids from the mf-map); the **read-only dashboard** (§11 — OS-enforced `mode=ro`, priority = active leads / dormant pile / health).
- *Live + hardened:* a real `pros run` fired **5 live xcorr leads** on the SPDR grid. The QA fix batch (**N1–N10** + sweeps) closed the going-live bugs — the read-only firewall (now mechanism, not prose), tick idempotency (stable series-id dedup, moving-clock-proof), the fabrication guard, source-specific retry sets, the ambiguous-exhibit fault surfacing, dashboard honesty (inert `off-thesis-real` excluded from the active panel), config-load validation — **each with the violation-test that would have caught it.**

**QUEUED (named, next):**
- **§9e** — dispersion wired into the runner (shadow + the 90-day burn-in clock), which pulls in the **holdings/constituent-price vertical** (where holdings-intake coverage becomes its own slice, and the "prove a spawner fires on *real seed data*, not merely that it's wired" rule — learned from xcorr's near-inertness — gets its first test).
- **§10** — the real email sender (weekly heartbeat/dead-man + state-change push), carrying the **nuisance-alarm suppression** criterion (push once on a *new* fault, then fall to the heartbeat).
- The **doc pass** (this rev; the ARCHITECTURE.md / runner-docstring regeneration is the code-side half, owned by the build seat).

**DEFERRED (named, with reason):**
- **M6** (discourse capture + budget guard), then **M7** (infra-as-code + **scheduled** deploy — where the runner stops being a manual `pros run`). M7 also owns two named items surfaced this arc: the SOI-corroboration **cadence gate** (0 cost today — empty dormant pile) and the runner-side **WAL-checkpoint** for serving the store from read-only *media*.
- **Milestone 3b** (dispersion PIT calibration + the NPORT-P parser) — data-availability-gated (survivorship-clean historical holdings + delisted-constituent prices), and *worse* for the proto-cluster layer per §1.9. Dispersion runs shadow / live burn-in meanwhile.
- **Broader holdings-intake coverage** — a real but **secondary** widening (per-issuer parsers / NPORT-P); the SOI path already resolves the active-fund sector case, so this turns the live lag from existence-proof toward a representative rate rather than unblocking it.

**ASPIRATIONAL (v2, walled off — captured as ideas, not queued):**
- The **proto-cluster / pseudo-ETF** layer and the Prospector-as-product direction (§1.9; the merged idea doc) — its substrate already accrues via the generous dispersion payload, so there is nothing to build now but keep capturing.
- The **discourse-interpretation** program (v2).

**The load-bearing honesty line:** everything under BUILT is *built and running*, not *validated* — the false-discovery-rate and edge questions live in the gap between "the runner fires" and "the firings mean something," and closing that gap is prospective, on-cadence work that has barely started. "Live" is not "proven."

## 5.3 Next steps — prioritized marching orders

The M5 runner is built and firing; the system is live and hardened against the first wave of going-live bugs. What remains is the second spawner, the sender, and then scheduled deploy:

1. **§9e — dispersion + the holdings/constituent-price vertical.** Wire dispersion into the runner in **shadow** mode (silent, non-paging, excluded from the ceiling), which starts its 90-day burn-in clock — and which pulls in **constituent-price ingest** and confronts **holdings-intake coverage** as its own slice (its consumer is finally built, so the widening is no longer smuggled under "wire the clock"). The **"prove a spawner fires on real seed data, not merely that it's wired"** rule — learned when xcorr would have been permanently inert reading an empty registry — gets its first test here.
2. **§10 — the email sender.** Weekly heartbeat/dead-man + state-change push, with the **nuisance-alarm suppression built in** (push once on a *new* fault, then fall to the weekly heartbeat until it clears or changes) — the one place the architecture-as-is would otherwise train the operator to ignore the alarm, exactly the failure the Protector brief names.
3. **M6** (discourse capture + budget guard), then **M7** (infra-as-code + **scheduled** deploy — where the runner leaves manual `pros run` for a real cadence, and the deferred M7 items land).

**The through-line:** the runner exists to convert existence proofs into *rates*. Everything from here is about **running it, on cadence, long enough for the false-discovery rate to become a measured number** — the only thing that answers whether the edge is real or merely architectural coherence. **Immediate action:** land these two docs (rev 5 / rev 14), then §9e. Dispersion stays shadow-mode until its burn-in completes; 3b is not a blocker; the proto-cluster layer needs nothing now beyond the generous payload already shipping.

---

*Closing note. The distinguishing property of this project is that it is engineered, in writing, before building, to be able to **lose** — falsifiable at every layer, with an immutable record that grades its own calls and metrics that refuse to flatter themselves. That is an unusual stance for anything built around markets, and it is the property that makes the whole thing either worth taking seriously or worth cleanly refuting. So far, at each layer where it could have lost, it has instead surfaced something true — including, tellingly, a real structural shift that was not the one being hunted, correctly recorded as context rather than acted upon. The tool notices; the human decides; the core absorbs; the record remembers. That division is the whole design.*
