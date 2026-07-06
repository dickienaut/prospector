# M5 runner skeleton: the thin spine, and how it grows

**Status:** build-decision, 2026-07-06. Implements the M5 spec
(`docs/prospector-m5-runner-spec-2026-07-05.md`) **§9 build-order step 1 — the runner skeleton**. Not a
new CONTRACT: it *implements* the existing §9/§9a/§9f/§9g/§10 CONTRACTs. This record captures the scope
decision (the **thin spine**), two implementation deviations from the approved plan (both made to match
the codebase's own precedent), the invariants under test, and the follow-on sequencing — including one
refinement the design thread made *because* this slice moved a review finding into the wired path.

Everything through M4 was a pure function or a deferred pass **waiting for a driver**. This slice is that
driver's spine: `prospector/runner/` + `pros run`. After it, Prospector runs on a cadence — records
launches, decides push/heartbeat mechanically — while adding **no intelligence** (the load-bearing §9
CONTRACT: the runner sequences deterministic sensors and renders their output; it never decides).

## The scope decision — thin spine, not a full tick

The owner's call (from three framings offered) was the **thin spine**: get the run order and the
invariants right *before* wiring anything new, proven end to end through **one** real vertical, with every
other sensor and all genuinely-new logic as **explicit, spec-cited SLOTS**. This is the same seam
discipline the rest of the build already runs on (`2026-07-03-launch-sensor-capture-first.md`,
`…-rebalance-accretion-and-routing.md`): ship the self-contained core, name the deferred half so it can't
become an open-ended "v-later."

**Wired end to end (the proof-of-shape): launch-recording (§4c).** mf-tickers ingest → `launch.scan`
(new-registration diff) → `ResolutionMachine` two-phase intake → identity retries. It was chosen as the
one vertical deliberately: it is the only path that exercises the **§9f between-tick-state-from-the-
fossil-record** invariant (the launch diff's prior comes from the last frozen `ingest/edgar/` mf blob,
not a side cache), and it lands its events on `_system` — so it also proves the runner correctly stays
**silent** on a launch (§10: a launch never pages).

**SLOTS (spec-cited, commented in `runner/runner.py`, filled in later steps):** §4a xcorr, §4b
dispersion, §4d rebalance/mandate (sensors); §9b SOI live-fetch, §9d deferred corroboration/SOI retry
(deferred passes); §9c mandate frozen-prior and §9e shadow clock (invariants noted at their slots); the
real §10 email sender (`NullNotifier` stands in — it records the intended push, sends nothing).

## What the runner does, in order (§9 CONTRACT run-order)

`run_tick(deps)` executes one tick — one invocation = one tick, cron-invoked, **no run-now surface**:

1. **Config honesty FIRST** — hash the config; if it moved, emit `config.changed` (with the diff)
   **before any sensor** (a fold is uninterpretable across an unrecorded threshold move). If this step
   fails, sensors are skipped (never act on an unchecked config) but snapshots + push still run.
2. **Ingest** (§9a) — thin spine drives only mf-tickers; freeze-before-parse via the `EdgarClient`
   `persist` seam (wired to `layout.edgar_path`).
3. **Sensors §4a→§4b→§4c→§4d** — the order is load-bearing (a test pins it); launch WIRED, the rest SLOTS.
4. **Identity retries** — drain the retry-then-manual queue; nothing evaporates.
5. **Capture** — no-op until M6 (the slot exists so M6 plugs in without reshaping the run order).
6. **Snapshots** — re-fold every real lead; materialize on the reactive cadence (`should_snapshot`).
7. **Push if state changed** (§10) — pinned to `fold.state_changed`; through the notifier seam.

A single `now` is captured once and threaded, so all events in a tick share one timestamp (determinism +
snapshot coherence). The runner holds nothing across ticks (statelessness CONTRACT §9): all carry-over
state is recovered from the durable record.

## Exception granularity (§9g) — a crashed run is legible, not silent

Each step is a **soft-fault** boundary: a per-unit failure emits a `fault` on `_system` (subsystem named),
skips that unit, and continues — one fund's 404 never blinds the others. A backstop catch turns any
escaped exception into a fault too. **In every case the run still attempts the push and still writes the
run-log** — a fault email beats silence (the weekly dead-man). A snapshot divergence is downgraded to a
soft fault via `write_snapshot`'s `fault_sink` (the built seam), not a run-abort.

## Two deviations from the approved plan (both toward the codebase's own precedent)

The plan is a guess made before reading the local conventions; where the two disagreed, the conventions
won. Recorded here so the divergence from the plan file is auditable.

1. **The run-log index (`runs` table) lives in `runner/runlog.py`, not `registry.py`.** The plan said add
   it to `registry.py`. But `registry.py` is **vendored and its DDL is frozen** (CLAUDE.md: keep the
   provenance, don't re-shape the ported schema), and the codebase already established the pattern for a
   module's own working index — `resolution_queue` is owned by `resolution.py` and `funds` by
   `fund_registry.py`, each created on the shared connection **precisely to avoid touching the vendored
   file**. The run-log is exactly that kind of module-owned, index-over-the-files telemetry (the
   `runs/{date}_{run_id}.json` files are the truth; `pros store reindex` does not rebuild the table, like
   the other working tables). Following the precedent over the plan was the correct call.
2. **No `# noqa` markers.** The plan's code sketch carried `# noqa: BLE001` on the broad `except` blocks.
   The repo has **no linter and no `noqa` anywhere**; the house idiom for a deliberate broad except is a
   plain why-comment (see `edgar.py`'s "Broad excepts are deliberate"). Introducing `noqa` would be
   cargo-culting a suppression for a tool that does not exist, so the markers were dropped and the
   why-comments kept.

## What is under test — the invariants, not the happy path

`tests/test_runner.py` (offline, fixture-clock; the conftest network guard fails any real socket). Every
CONTRACT the skeleton implements has a test:

- **config-honesty-before-sensors** — `config.changed` is appended *before* the first sensor event
  (an append-order spy, since both share `now`).
- **launch recorded but silent** — a new registration emits `launch.unverified`; the notifier is **not**
  pushed (a graceful resolution failure is not a fault, and a launch never pages).
- **first run seeds** — no prior frozen mf blob → seed (freeze today's map, flag nothing) rather than
  flag the whole universe.
- **ingest failure is a soft fault that continues AND pushes** — the run does not abort, and a fault
  forces the push (dead-man).
- **run-log written + indexed + NOT a lead event** — never appears in the event record or as a lead.
- **two cold runs → identical events** — the statelessness property (state IS the store).
- **push pinned to `state_changed`** — a real lead's status change snapshots and pushes; `_compute_push`
  unit-pins the `changed ∨ fault` rule.
- **firewall + no-run-now guards** — the runner reads no portfolio config; `pros run`'s only option is
  `--store`.

Result: **380 tests green** (was 370; the +10 here, on top of the two runner-blockers H1/S2 that landed
with the spec). A live `pros run` was **not** exercised (it builds a real `EdgarClient` and would call
SEC) — the offline fixture-clock drives the whole tick without touching the network, which is the point.

## The four subtle bits — and the discipline for the three still dormant

The spec names four places the runner can go quietly wrong; all four are commented where they live. Of
the four, **only #1 (config-hash-before-sensors) is exercised now** — the other three sit at slots the
skeleton hasn't wired, so they get their teeth only when those slots land (steps 2–3). (Separately, the
soft-fault-continues path is fully tested now, but it is a §9g property, not one of the four numbered
bits.) The discipline for the dormant three:

- **#2 mandate prior from the FROZEN blob, not the registry `prospectus_accession`** (§9c) — an identity
  pass earlier in the same run may advance that field; the diff must source its prior from the frozen
  prospectus blob store.
- **#3 a deferred pass is CALLED WITH its sectors, never assumes them** (§9d) — wiring it at launch
  resolution finds the empty set (holdings post days later) and **silently never fires**.
- **#4 shadow clock surfaces readiness, never auto-promotes** (§9e) — wired when dispersion lands; the
  runner tracks the burn-in clock and surfaces it, but the shadow→paging flip stays a human config change
  that leaves a `config.changed` fossil.

**The test lands WITH the slot wiring, never after** — and for #3 the test must prove the pass *actually
fires* on late-arriving sectors, not merely that it is *called*: an "it's called" test would pass against
the exact ∅-and-never-fires bug §9d exists to prevent.

## Follow-on sequencing (refined — because this slice moved I1 into the spine)

The QA review's runner-path fixes were, yesterday, "before the identity/HECO path is leaned on hard."
Wiring launch-recording end to end changed that for one of them:

- **I1 now lives in the wired launch path.** `register_launch` re-derives identity by ticker rather than
  threading the *detected* series_id, which defeats the HECO reused-ticker guarantee. It is still latent
  (it only bites on a ticker-reuse transition in a **live** run, and the skeleton is offline-tested), so
  it does not block the commit — but it must land **before the runner ever runs live cadence**, not after
  step 2.
- **H4 lands WITH step 2, not after it.** H4 is a real latent gap — the SOI parser has no alias for the
  plain `REAL ESTATE INVESTMENT TRUSTS` header (only the specific sub-industry REIT headers roll up). A
  **correction to the original framing, made by verifying against the code** (this doc's claims were
  adversarially checked before commit): the plain header does **not** currently fault the two TEKX
  NPORT-EX fixtures — they parse `reliable=True`, because in them it is a parent/group line the industry
  regex (`_HEADER_RE`) never matches (the Real-Estate weight comes from the specific REIT sub-industries
  that *are* in the table). The gap bites only where the plain header appears as a *weighted industry
  line* — the real IG-Credit equity blocks the Claude-Science review cited. Step 2 widens the live input
  beyond the two TEKX fixtures to exactly such filings, so H4 (the missing alias **+ a fixture that
  exercises the faulting equity-block path**) should land with step 2, before those filings reach the
  parser. (Also surfaced in verification: `ingest/soi.py`'s docstring claims the plain header "still rolls
  up instead of faulting" via aliasing — that stated *mechanism* is inaccurate; fold the docstring fix
  into step 2.)

**Order:** this skeleton (committed) → **step 2 (SOI-fetch) with H4 folded in** → **I1/B1/B2 before live
cadence** → step 3 (deferred retry §9d + mandate frozen-prior §9c + shadow clock §9e) → step 4 (email +
dormant-pile coverage report) → step 5 (Streamlit).

## What shipped (2026-07-06)

- `prospector/runner/runner.py` — `run_tick` (the driver, the CONTRACT run-order, soft-fault granularity,
  reactive snapshot + `state_changed`-pinned push) + `_CountingStore` (tallies event types for the
  run-log) + `_load_prior_mf_snapshot` (§9f) + `_compute_push` (§10).
- `prospector/runner/deps.py` — `RunnerDeps`, the injected seam bundle (offline-testable).
- `prospector/runner/notify.py` — the `Notifier` protocol + `NullNotifier` (records intent, sends nothing).
- `prospector/runner/runlog.py` — `RunLog` + `write_run_log`/`recent_runs`, owning the `runs` table.
- `prospector/store/layout.py` — `runs_path` / `runs_root` (+ the tree-diagram line).
- `prospector/cli/main.py` — the `pros run` cadence entrypoint (thin; only `--store`).
- Tests: `tests/test_runner.py` (the invariants above); `tests/test_cli.py` (command-tree pin + `run`'s
  option surface).
- `ARCHITECTURE.md` — module map (the `runner/` rows), the CLI table, and the built/deferred status.

**Not built (deferred, named — the SLOTS above):** SOI live-fetch (§9b, step 2); the deferred
corroboration/SOI retry loop (§9d) + mandate frozen-prior (§9c) + shadow clock (§9e) (step 3); email
heartbeat/push + the dormant-pile coverage report (§10, step 4); the read-only Streamlit (§11, step 5).
The runner-path integrity fixes (I1/B1/B2, H4) are sequenced above.
