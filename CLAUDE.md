# Project Prospector — repo constitution

This repo is **Project Prospector**, the offensive twin of the thesis smoke detector. It watches
the ETF universe for structural novelty and proposes **reading, never orders**.

The canonical spec is `docs/spec.md` (rev 15, stated in its header; earlier revs kept in
`docs/history/`). Read it before changing anything load-bearing. Rev12 folds the launch corroboration hook
(§4c) to **built** (the M4 capstone) and records its finding at deflated strength — the live lag is
bounded by holdings coverage, an **existence proof, not a rate** — plus the fixture-provenance honesty.
Primary-source review then sharpened it: the real SSGA daily file is **xlsx, not CSV**, and for an
**active fund carries no `Sector` column at all** (all "-"), so file-sector-derived concentration is
empty → real TEKX → `sectors_unresolved` (dormant), not a corroboration; the +593 was reachable only on
the synthetic fixture (see `docs/decisions/2026-07-04-real-holdings-xlsx-and-blank-sectors.md`). Rev11
folds the mandate-diff precision into
§4d/§7 (raw-HTML frozen per accession, section extracted on *read*; priority-match Strategies→Objective;
specified extraction-unreliable→`fault` conditions) and adds a **CONTRACT state-source invariant for the
§9 runner**: the mandate sensor's "prior" is its last *frozen* prospectus blob, never the registry
`prospectus_accession` (which an identity pass may advance intra-run). Rev10 recorded mandate-diff built.
Rev9 decomposed the rebalance sensor (§4d)
like the launch sensor: the **holdings-diff accretion core is self-contained** (its own PR) and
**`mandate.changed` is a deferred defined-next-slice** (needs new surface — EDGAR prospectus-*text*
fetch + `ingest/prospectus/` blob-per-accession storage + text diff). Rev9 also makes **CONTRACT**:
routing by **forward-hash** (reuse `xcorr_lead_id`/`dispersion_lead_id` verbatim — no series_ids in the
payload, the lead-id already encodes them) and **live-lead enumeration from the registry-materialized
fold** (no separate cache). Rev8 records the **proto-cluster / pseudo-ETF** concept as a v2 design note
(Appendix B — a deterministic, price-only route to *new-category* detection below the ETF corpus) and
folds in a **generous `dispersion.tick` payload** (§4b, CONTRACT). Rev7 (folded in) demoted the launch stream to
corroboration + consensus-clock (never a ceiling-counting lead-spawner) and split the launch sensor
into recording (built) + corroboration (gated on §4d holdings ingest). Rev6 folded the four-value
verdict vocabulary into §5/§8c, recorded the box-B crash-flag outcome (§4a/§5/§8b/§10), and added the
§4a multi-factor-β guard. It carries forward unchanged rev5's stress-gate freeze (absolute 0.85,
crisis-only) and the amended March-2020 falsification (test 5c → reversion criterion).

## Firewall
- Never add code that reads the detector's bucket or `portfolio.yaml`.
- Never add a code path that places, sizes, or recommends a trade.
- The only connection to the portfolio system is human and one-way (a lead graduates by hand).

## CONTRACT vs DEFAULT
Items marked CONTRACT in `docs/` specs change only via the design thread (chat with the owner),
never unilaterally in implementation. DEFAULTs are config in `config/prospector.yaml` — change freely.

Design-thread-authorized amendments to CONTRACT defaults are recorded under `docs/decisions/`:
- `docs/decisions/2026-07-02-stress-gate-recalibration.md` — the market-stress gate moved from an
  absolute 0.65 to an absolute 0.85 (crisis-only), after the β-strip was proven the primary
  market-factor defense. Baseline-relative was tested and rejected (a fragility gauge's intrinsic
  level is the signal). The stress gate's crisis_level is frozen; fix its aging by human
  recalibration, never a rolling percentile. (Test 5c amended by rev5; see below.)
- **Verdict vocabulary (CONTRACT §5/§8c) — four values, three live meanings** (ratified:
  `docs/decisions/2026-07-02-crash-flags-guidance-rev2.md` §8.4). `yes` · `watch` (on-thesis but
  UNPROVEN — live) · `off-thesis-real` (real but off-thesis macro/sector regime — catalogued as
  context, inert) · `noise` (the refined `no` — not real). `off-thesis-real` and `watch` are
  deliberately distinct: never file a live candidate tech lead as macro. `VERDICT_VOCAB` in
  `prospector/fold/fold.py` is the single source of truth. Rev6 §5/§8c now carry
  `none|yes|watch|off-thesis-real|noise` — the code-ahead-of-spec drift is closed. The macro-catalog
  forensic view + Streamlit panel remain milestone 5.
- **Generous dispersion payload (CONTRACT §4b, rev8)** — ratified:
  `docs/decisions/2026-07-03-dispersion-payload-generous.md`. The `dispersion.tick` payload carries
  **full constituent membership + each name's sub-cluster assignment + the correlation structure**
  (not just the scalar Q), so the deferred v2 **proto-cluster / pseudo-ETF** layer (Appendix B) can
  thaw backward over it — you cannot backfill a payload you did not capture. The proto-cluster layer
  itself is **v2, not built**: it is **price-only** (correlation one level down — never keyword/NLP
  mining), the canary is a **cluster, never a single name**, and it is **observation-only — the
  canary is never the trade** (watch the forming cluster, buy the diversified ETF when it packages;
  single-name granularity is where over-trading and concentration risk peak). Same firewall class as
  the reading-list wall. v1's only action is capturing the substrate richly; do not build the
  interpretation.
- **Rebalance routing + enumeration (CONTRACT §4d, rev9)** — ratified:
  `docs/decisions/2026-07-03-rebalance-accretion-and-routing.md`. Rebalance is an **accretion** sensor
  (no Schmitt, no lead of its own; `rebalance`/`mandate.changed` are silent corroborations). To find
  "every live lead whose baskets include a fund," **forward-hash** — reuse `xcorr_lead_id`/
  `dispersion_lead_id` verbatim and intersect with active leads; **never** add series_ids to a lead
  payload (the lead-id already encodes them — duplication invites drift). Read the active-lead set from
  the **registry-materialized fold** (the snapshots the fold writes), never by re-folding or a separate
  cache. `mandate.changed` is a deferred defined-next-slice (unblock: EDGAR prospectus-*text* fetch +
  `ingest/prospectus/` blob-per-accession storage); NPORT-P (`parse_nport_holdings`) stays the labeled
  §3b stub — do not fill it with survivor-biased data.
- **Mandate-diff: targeted section + a deliberate dependency (§4d, rev9→rev10)** — ratified:
  `docs/decisions/2026-07-03-mandate-diff-targeted-section.md`. A new prospectus → diff **only the
  principal-investment-strategy section** (never the whole filing — a full-text diff is a false-positive
  machine, the diff-trap), emit `mandate.changed` as a **silent corroboration** the human adjudicates
  cosmetic-vs-substantive; when extraction is unreliable, emit a `fault` (manual review), **never** a
  false change. Added **`beautifulsoup4` (pinned `==4.15.0`)** — a deliberate, reasoned dependency:
  infrastructure-not-intelligence (parsing malformed filing HTML, like numpy/SQLite/boto3), pinned
  because it parses external input. **Boundary (do not blur):** bs4 owns HTML **structure**, our code
  owns **meaning** (which section, did the text move), the **human** owns **significance** — the
  extraction/diff must never grow a "this change is meaningful" opinion. Routing reuses the rebalance
  forward-hash. Folds into **spec rev10**.
- **Launch corroboration: existence proof, not a rate (§4c, M4 capstone)** — ratified:
  `docs/decisions/2026-07-03-launch-corroboration-existence-proof.md`. A resolved launch's sectors are
  **derived from its first holdings** (ground truth, not prose); a **both-sides sector-set overlap**
  with a live lead's baskets **accretes** the launch onto that lead (NEVER spawns one — rev7, no ceiling
  slot), making the **signed** cross-stream lag measurable (negative = packaging beat structure, recorded
  honestly, never clamped). It is a **deferred** pass (holdings post days after launch; wiring it at
  resolution would find the empty set and never fire) — reaches back, preserving `detected_at` as T2.
  The backtest `keyword_match` + curated launch table **never enter the live path**. **Load-bearing
  finding, at full strength:** the live lag is **bounded by holdings coverage, not the hook** —
  `ingest/holdings.py` is SPDR-only, so outside that family the lag is **structurally unmeasurable**;
  the v1 live lag is an **existence proof, not yet a rate**, and `holdings-unavailable → dormant` is the
  **first-class majority case** (flag the blind spot, never guess). **Real-data finding (2026-07-04,
  `docs/decisions/2026-07-04-real-holdings-xlsx-and-blank-sectors.md`):** the real SSGA daily file is
  **xlsx** (now handled — pinned `openpyxl`) and for an **active fund carries no `Sector` column** —
  so file-sector-derived concentration is empty and a real launch resolves **`sectors_unresolved` →
  dormant** (a new first-class disposition; the +593 was reachable only on the synthetic fixture).
  **Anti-fitting (CONTRACT):** a dormant real outcome NEVER motivates lowering
  `corroboration.sector_min_weight`.
- **SOI-derived sector concentration — the EDGAR filing carries the GICS grouping; the ticker→GICS
  classifier is RETIRED (§4c resolver)** — ratified:
  `docs/decisions/2026-07-04-soi-derived-sector-concentration.md` (design:
  `docs/notes/2026-07-04-soi-derived-sector-concentration.md`). The prior bullet's "external ticker→GICS
  classifier" unblock was a **convergent-prior error**: the primary source already publishes the sector
  grouping. A fund's periodic EDGAR filing renders a **GICS-industry-grouped Schedule of Investments**
  (`SOFTWARE — 38.7%`, `ELECTRIC UTILITIES — 6.4%`); sector concentration is derived by parsing those
  industry headers and rolling **industry → GICS sector** through a **frozen `gics_industry_sector`
  table** (config, CONTRACT — re-freeze only on a GICS structure revision, never a knob). No per-ticker
  classifier, no third-party feed (a bought feed breaches the primary-source wall). This is the
  **resolver** of `sectors_unresolved`: when the first SOI lands, `sensors/soi.py` derives `{sector:
  weight}`, thresholds it with the frozen `sector_min_weight`, and routes via the shared
  `launch_corroboration.route_corroboration` (holdings + SOI feed **one** overlap/accrete/lag path), the
  deferred reach-back preserving `detected_at` as T2. **Extraction-unreliable → `fault`, never a wrong
  sector set** (fund block not isolable / unknown industry / reconcile miss); bs4 owns structure, our
  code owns which-industry-and-rollup, the human owns significance. **Primary-source findings:** the
  sector-bearing artifact is the **`NPORT-EX`** exhibit (multi-fund — fund-block isolation is mandatory);
  the **reconcile-to-`COMMON STOCKS`-total** check caught a mixed-case `SPECIALIZED REITs` the first regex
  dropped; on real TEKX the Jul-2025 SOI clears `{Financials, Industrials, IT, Utilities}` (Financials
  10.1% too — filed truth over the spec's 3-sector prose) → **+593 on real data**, and Jan-2026 stays
  **dormant** (Utilities 6.4% < floor). **Live EDGAR-SOI-fetch is DEFERRED to M5** (tied to `EdgarClient`;
  `SOI_FORMS`/`latest_soi`/`index.json` doc resolution) — **drop-and-freeze for tests, fetch-on-cadence
  for the runner; the two never conflate** (fixtures are never refreshed by fetch code). `parse_nport_
  holdings` stays the labeled §3b stub. Holdings-intake coverage (per-issuer / NPORT-P) remains secondary
  — do not widen ad hoc.

## Append-only
- Nothing under `events/` is ever edited or deleted. Corrections are new events.
- A changed mind is a new `verdict` event that supersedes via `superseded_by`, never an edit.
- Backtests write **only** under `backtest/` (separate store root + registry per run).

## Canonical documents — amended, never regenerated
The doc-process form of Append-only: never let the present silently rewrite the past. **Canonical
contract/reference documents are amended, never regenerated.** The build spec, this file (the constitution),
the package READMEs, and the founding document change by **surgical diff — altering only the clauses a
recorded decision changed — plus a changelog note of the delta and its decision-record.** All other text is
preserved verbatim. A **wholesale rewrite is forbidden**: regenerating such a document silently drifts
contract text no one decided to change, and the drift is invisible precisely because there is no diff to
check. A clause is **superseded in place with the change recorded** (changelog + decision trail + git), never
silently dropped — the document states the *current* contract, but *every* change is traceable.
- **Two document kinds, two rules.** The **state-of-project doc** is the partial exception: its stable
  conceptual body (**Parts I–IV**) follows the amend rule (carried forward, not rewritten), but its
  current-status rollup (**Part V**) is **re-synthesized each rev** — it is a snapshot of *now*, not a
  contract. (Rev 7 carried I–IV verbatim and rewrote Part V; the spec took amendments — correctly.)
- **The escape valve (so patchwork can't trap you).** A cleanup **rewrite is allowed only as an explicit
  consolidation rev**, and only with a **clause-by-clause diff proving no contract changed except the ones
  intended**, recorded in that rev's decision record. The forbidden thing was never *rewrite*; it is *rewrite
  unchecked* — make the check mandatory and the drift can't hide.
- **Scope.** Bound: the enumerated canonical set above (+ the state-of-project Parts I–IV). NOT bound (freely
  authored): working notes, build notes, QA findings, session logs — and the **decision records themselves**,
  which are append-only (a changed decision is a *new* record superseding, never an edit — the immutable trail
  this rule points to).
- **The check (build seat).** Before writing a canonical doc: diff against the prior version and confirm every
  changed clause traces to a decision record. Ratified with the design thread:
  `docs/decisions/2026-07-11-canonical-docs-amended-not-regenerated.md`. (This rule was itself added by
  surgical amendment — fittingly.)

## Doc naming — provenance in the filename
Every doc is **born with a leading ISO date** (`YYYY-MM-DD-…`) so versions are tellable apart at a glance — the
date orders it and never changes. This mostly formalizes existing practice (decision records are dated; the spec
and state doc carry date + rev). The rule is deliberately narrow in three ways:
- **Rev only where it versions.** A `-revN` suffix is added **only** where the doc is one of a versioned series
  (a decision revisited as rev 2+; and the superseded spec/state revs already fossilized in `history/`). A
  rev-bump of such a fossil series is a **new dated file, the prior moved to `history/`** — never a
  rename-in-place. Date is universal; a `-rev1` on a one-shot fossil (a QA finding that will only ever be rev 1)
  is just noise. **The *live* build spec and state-of-project doc are not in this class** — they are amended in
  place under stable names (next bullet); filing them as a dated series was a misclassification, corrected
  2026-07-17.
- **Stable-named exceptions — because they are amended in place.** `CLAUDE.md`, `INDEX.md`, `ARCHITECTURE.md`,
  the **build spec (`docs/spec.md`)**, the **state-of-project doc (`docs/state.md`)**, the package `README`s, and
  `LICENSE` keep fixed names: they are the always-current single instance, amended in place per
  amend-never-regenerate, their history in git + changelog — not re-fossilized as a dated series; the rev they
  carry lives in the **header** (a content claim, one home), never the filename. The distinction is principled,
  the same one that governs how each kind changes: **stable-named = amended-in-place single instance; dated =
  point-in-time or versioned.** The spec and state doc belong here *by their own rule*: amend-never-regenerate
  already governs them (surgical diff, everything else verbatim) — which **is** the amended-in-place contract, so
  filing them as a dated series was the misclassification corrected 2026-07-17
  (`docs/decisions/2026-07-17-rolling-docs-stable-named.md`).
- **Forward-only — the load-bearing clause.** This governs **new** files (born dated); **existing filenames are
  never bulk-renamed.** The reorg's insight was *relocate, never rename* — references point at filenames, so
  byte-identical names keep ~99% of them resolvable by search; a bulk rename would break exactly those and
  *multiply* the un-fixable fossil drift the reorg recorded as its one cost (a decision record is immutable — it
  cannot be edited to point at a renamed file). The escape valve mirrors amend-never-regenerate's: a **specific**
  legacy misnamed doc may be normalized as a deliberate, **reference-checked one-off** (grep its references, fix
  the fixable, document any fossil drift — the same shape as the reorg), **never a bulk rename.**
- Ratified with the design thread: `docs/decisions/2026-07-11-doc-naming-convention.md`; the live-spec/state
  reclassification (stable-named, amended in place — `docs/spec.md`, `docs/state.md`) added 2026-07-17,
  `docs/decisions/2026-07-17-rolling-docs-stable-named.md`.

## Vendored store provenance
The store/registry primitives in `prospector/primitives/` are ported from
`prophit_skunkworks/ltee_archive/` (snapshot dated 2026-03-29, vendored 2026-07-02) with the
trading ontology stripped and the schema inverted to envelope + JSON-payload.
- Keep the provenance headers.
- Do not re-introduce wide typed-metric columns to the events table.
- Do not import anything from the sibling repo's `models/` (capacity and opacity — forbidden).

## No LLM text as data (v1)
No model-generated prose is ever persisted as record content. Capture (v1 milestone 6) stores raw
search-result blocks and fetched page text only.

## No run-now surfaces
No commands, buttons, or endpoints that trigger recompute or capture on demand. Record on cadence;
push on state change. No dashboard autorefresh. (`pros store reindex` rebuilds the index from the
fossil record — it computes nothing new, so it is repair, not run-now.)

## Identity
Every fund keys on its SEC series ID (S######). A bare ticker is rejected at the write path.
Failed resolutions go to the retry-then-manual queue, never silently dropped. Tickers are
display-only attributes.

## Config honesty
On every run the config is hashed; a change emits `config.changed` with the diff **before** any
sensor runs.

## Alert posture
Hard cadence floor (weekly heartbeat), state-change-only push, read-only surfaces, no execution.
Silence beyond 7 days unambiguously means broken. No auto-tune of thresholds, ever — the
active-lead ceiling is a tripwire for human recalibration.

## Standing review items (human-ratified, never auto-tuned)
Some thresholds are reviewed on a cadence and moved only by deliberate human recalibration that
leaves a `config.changed` fossil — never by a self-updating rule:
- **Active-lead ceiling** (§8a) — a tripwire for human recalibration of sensor sensitivity.
- **Stress-gate aging monitor** (§4a) — the backtest reports the recent-window **calm-regime** p95
  (non-crisis days) and its headroom to the frozen absolute gate. If the margin compresses,
  re-freeze the level higher by hand. **Never** a rolling percentile / self-updating window — that
  reintroduces the baseline-relative failure the recalibration diagnosed.
- **Macro catalog** (`off-thesis-real` verdicts) — a read-only reference layer of real-but-off-thesis
  (macro/sector) classifications, consulted by the human when adjudicating elsewhere. **Read-only
  context, NEVER a trade/tilt trigger, never piped anywhere as actionable, and never a macro-regime
  alert stream / "regime forming" push / monitoring surface** (same class of rule as the reading-list
  wall). The cap-weighted core already absorbs sector regimes; the correct action on a detected macro
  regime is none. The sensor also never strips the macro regime out (no multi-factor β — it is
  entangled with real tech theses; stripping it would delete real signal). See
  `docs/decisions/2026-07-02-crash-flags-guidance-rev2.md` §8.

## Development
- **Always work on a new branch.** Never commit directly to `main`. At the start of any change,
  branch off `main` (`git switch -c <descriptive-name>`) and do the work there; graduate it to `main`
  by pull request. If a session begins on `main` with work to do, create the branch first.
- **Code never merges to `main`** — it opens the PR and stops. Code's job ends at pushed branch → green CI →
  open PR; the owner reviews, approves, and merges from the phone (the Mini holds no owner credential). This
  is now mechanism, not posture: Code acts under the machine account `claudeatalphalabsengineering`, which is
  not a code owner and cannot approve its own PR, and the `main` ruleset requires one code-owner approval
  covering the most recent push, no bypass — so no sequence of agent actions alone lands code on `main`. The
  residual posture is narrow and still binding: once the owner has approved, Code could click merge — it must
  not. CI-green is not correctness: green-on-synthetic, a test that passes for the wrong reason, a
  merge-introduced regression all clear CI — and the human review is where that class is caught. Ratified:
  `docs/decisions/2026-07-16-agent-identity-split-and-merge-gate.md` (supersedes
  `docs/decisions/2026-07-12-code-does-not-merge-human-reviews.md`, which recorded the posture-era rule).
- **Branch off a freshly-fetched `origin/main`, never off a sibling feature branch** —
  `git fetch origin && git switch -c <descriptive-name> origin/main`. When PRs merge quickly, a branch cut from
  a **stale local `main`** (or from another feature branch) carries a stale base, and a PR from it can
  **silently revert an already-merged change** — the diff shows the sibling's merged work as *deletions*.
  **Diff against `origin/main` before opening the PR**; that catch is the last guard. (Born from exactly that
  near-miss — see `docs/decisions/2026-07-11-branch-off-fresh-main.md`.)
- **Verify git/PR state before acting on it — `main` moves, and that is its default.** Code opens PRs; the
  **owner** merges them asynchronously (often from a phone), so *"is this PR open / is this branch merged /
  where is `origin/main`"* is never something Code knows — only something it last observed. Before amending or
  force-pushing a branch, check `gh pr view <n> --json state,mergedAt`: **never amend a merged branch** — the
  change is orphaned and **silently does not land**; put it on a fresh branch off `origin/main` instead. Before
  reporting a change as landed, verify against the remote (`git merge-base --is-ancestor <sha> origin/main`),
  never against local state or memory. The hazard is not the force-push (harmless) — it is **believing a fix
  landed when it did not**, the fail-silent class wearing a git hat. (Born from exactly that:
  `docs/notes/2026-07-19-verify-git-state-before-assuming.md`.)
- `uv sync` to set up; `uv run pytest` to test; `uv run pros --help` for the CLI.
- Tests are offline: a network guard fails any test that opens a real socket. Recorded fixtures
  live in `tests/fixtures/`.
- All record times are UTC.

## Fixture provenance
Every test fixture is either **recorded-real** — carrying a source-URL + retrieval-date header (a
sidecar for binary files like xlsx) — or **declared synthetic** in-band (a trailer or comment that says
so). No fixture silently stands in for a real filing. Fixtures were the one input class exempt from the
freeze-the-substrate discipline (§7 frozen ingest); the launch-corroboration slice is why they no longer
are — a labeled-synthetic SPDR-format holdings fixture carried a green the real filing had not yet
earned. Reading the real file broke two shared (convergent) priors the cross-thread review could not:
the real SSGA daily file is **xlsx, not CSV**, and for an **active fund carries no `Sector` column at
all** ("-"), so the derivation was proven against *imagined* messiness, not *filed* messiness (the split
assertion held, so nothing was wrong — the gap was invisible until someone read the real file). When a
fixture is synthetic, say so where a reader will see it; when it is real, say where it came from and
when. Primary-source verification is the specific antidote to convergent priors.

## Documentation (standing practice — document as we build)
- `ARCHITECTURE.md` (repo root) is the top-level map of what's built and why. **Keep it current**:
  when a milestone lands or a module's shape changes, update the module map (§2) and the built/deferred
  status (§9) in the same change. It is written for someone catching up — orient, don't just enumerate.
- Every load-bearing decision or CONTRACT amendment leaves a written trace in `docs/decisions/`
  (pointed to from this file), next to its `config.changed` fossil / commit.
- Code carries **spec-citing docstrings** (which `§` a module implements) and **inline comments on the
  subtle bits** — especially anything that encodes a CONTRACT, a deliberate non-obvious choice, or a
  "do not do X because Y." Comment the *why*, not the *what*. This density is the norm; match it.
