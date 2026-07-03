# Project Prospector — repo constitution

This repo is **Project Prospector**, the offensive twin of the thesis smoke detector. It watches
the ETF universe for structural novelty and proposes **reading, never orders**.

The canonical spec is `docs/prospector-v1-spec-rev5-2026-07-02.md` (rev5; earlier revs kept as
history). Read it before changing anything load-bearing. Rev5 froze the stress gate (absolute 0.85,
crisis-only) and amended the March-2020 falsification (test 5c) to the reversion criterion.

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
  `prospector/fold/fold.py` is the single source of truth. Spec rev5 §5/§8c (which still read
  `none|yes|no|watch`) fold to rev6 with milestone 5.

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
