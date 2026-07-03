# Project Prospector — repo constitution

This repo is **Project Prospector**, the offensive twin of the thesis smoke detector. It watches
the ETF universe for structural novelty and proposes **reading, never orders**.

The canonical spec is `docs/prospector-v1-spec-rev9-2026-07-03.md` (rev9; earlier revs kept as
history). Read it before changing anything load-bearing. Rev9 decomposes the rebalance sensor (§4d)
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

## Append-only
- Nothing under `events/` is ever edited or deleted. Corrections are new events.
- A changed mind is a new `verdict` event that supersedes via `superseded_by`, never an edit.
- Backtests write **only** under `backtest/` (separate store root + registry per run).

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
- `uv sync` to set up; `uv run pytest` to test; `uv run pros --help` for the CLI.
- Tests are offline: a network guard fails any test that opens a real socket. Recorded fixtures
  live in `tests/fixtures/`.
- All record times are UTC.

## Documentation (standing practice — document as we build)
- `ARCHITECTURE.md` (repo root) is the top-level map of what's built and why. **Keep it current**:
  when a milestone lands or a module's shape changes, update the module map (§2) and the built/deferred
  status (§9) in the same change. It is written for someone catching up — orient, don't just enumerate.
- Every load-bearing decision or CONTRACT amendment leaves a written trace in `docs/decisions/`
  (pointed to from this file), next to its `config.changed` fossil / commit.
- Code carries **spec-citing docstrings** (which `§` a module implements) and **inline comments on the
  subtle bits** — especially anything that encodes a CONTRACT, a deliberate non-obvious choice, or a
  "do not do X because Y." Comment the *why*, not the *what*. This density is the norm; match it.
