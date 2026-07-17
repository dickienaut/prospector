# `prospector/fold/` — the pure state engine (spec §5)

A lead **is** the fold over its event stream. Nothing about a lead's state is stored as a mutable row;
it is always recomputed deterministically from the append-only events. This is the heart of the
append-only design — the store keeps facts, the fold derives state — and it is **built**. The fold is
pure (rows in, state dict out): no I/O, no clock, no config, total order `(ts, event_id)`, duplicates
dropped by `event_id`. Two cold runs over the same store therefore produce identical leads (spec
test 3, property-tested).

## Modules

- **`fold.py`** — the pure fold engine. `fold(rows) -> state` replays an event stream into a lead's
  state dict; `state_changed(prev, new)` reports which of the push/ceiling trio `{status, shadow,
  verdict}` differ (§5, §8a); `verdict_head_id` finds the current verdict chain head a new verdict
  must supersede. Two exports are load-bearing:
  - **`VERDICT_VOCAB`** — the **single source of truth** for the four-value verdict vocabulary:
    `yes` · `watch` (on-thesis but UNPROVEN, live) · `off-thesis-real` (real but off-thesis
    macro/sector regime, catalogued as inert context) · `noise` (the refined `no`, not real).
    `none` is the no-verdict default, not a writable value. The CLI choice and future surfaces
    reference this tuple. Verdict is **display-only** — nothing keys on it to drive action, so
    "context, never a trigger" holds by construction.
  - **`active_nonshadow(states)`** — the single oracle-facing filter. The §8a active-lead **ceiling**,
    paging, and the email digest all call it, so **shadow leads are excluded from all three by
    construction** (§4b CONTRACT). A shadow lead is real and recorded but does not count against the
    ceiling and does not page.
- **`snapshots.py`** — the reactive snapshot **policy**: *when* to materialize a fold, not what it
  contains. `should_snapshot` is pure (clock injected): immediate on any state change (the reactive
  analog of Prophit's apex tier), dense while a lead is active (DEFAULT daily), a weekly floor
  otherwise. `write_snapshot` materializes to `snapshots/{lead}/{ts}.json` (idempotent,
  first-write-wins) and carries a **`SnapshotDivergenceError`** guard: a rewrite whose folded state
  differs means a backdated event or a nondeterministic fold broke an invariant — surfaced as a
  `fault` (audit = detection), never silently masked.

## Important to know

- **Open-vocabulary, total, crash-proof (§5):** recognized v1 types (`V1_TYPES`) fold into named
  fields; any `*.reverted` type folds as a revert (a future sensor's exit event works with no code
  change); everything else lands in `unknown_types` — counted, raw-referenced, never a crash. The
  fold does **not** reject verdicts outside `VERDICT_VOCAB` (append-only / forward-compat: a legacy
  `no` still renders). A broken verdict chain (dangling/fork/cycle) resolves deterministically to the
  latest head by `(ts, event_id)` and records an anomaly rather than raising.
- **Market stress (§4a CONTRACT):** a departure annotated `market_stress` is recorded (in the fossil
  record and the counts) but is **not** a state change — no activation, no `latest_z`. It protects the
  oracle without erasing the record.
- The snapshot policy is inverted from its vendored source (`ltee_archive/snapshot_policy.py`): the
  Prospector cannot know when a fracture is coming, so the trigger moved from scheduled epoch
  boundaries to **lead-reactive**. Keep the provenance header.

## See also

- Spec **§5** (and §8a/§8c, §4b) in `docs/spec.md`; `ARCHITECTURE.md`
  §2/§9. Decision: `docs/decisions/2026-07-02-crash-flags-guidance-rev2.md` (verdict vocabulary §8.4);
  shadow leads: `docs/decisions/2026-07-03-dispersion-shadow-first.md`.
