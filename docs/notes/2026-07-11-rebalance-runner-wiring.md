# Rebalance runner-wiring — build note (2026-07-11)

> **Status: BUILT 2026-07-12** — `runner/_run_rebalance` + `sensors/rebalance.active_incl_shadow_lead_ids`
> + `ingest/holdings.frozen_dates`, 11 offline tests (`tests/test_runner_rebalance.py`). Two forks
> ratified: shadow-inclusive active set, and seed-silently-on-first-pull (this note's §2/§4 corrected
> below). Decision record: `docs/decisions/2026-07-12-rebalance-runner-wiring.md`.

*Build note for Claude Code. Wires the already-built rebalance sensor (§4d) into the runner — the **last M4
sensor into the runner**, and the last slice before a build-complete v1 core. §9e already freezes each
basket's holdings every tick, so the diff has its inputs; this is a wiring slice, not new sensor logic.
Governing: spec §4d (rebalance accretion), §9 (runner). **Read `sensors/rebalance.py` first** — wire to the
interface it actually exposes; do not assume its signature.*

## 1. What this is

Rebalance is **accretion, not a spawner** (§4d / §0: "rebalances as accretion onto existing leads"). It diffs
a basket's holdings between the prior frozen snapshot and this tick's, and when the change is *material* (a
real reconstitution, not daily price drift), it **accretes a `rebalance` event onto the live lead(s) for that
basket** — corroborating evidence that a basket a sensor already flagged just changed its composition. It
**never spawns a lead**, never fetches (holdings are frozen by §9e), never touches execution.

## 2. Scope — the wiring

- **`_run_rebalance` at its slot in `_run_sensors`**, alongside `_run_xcorr` / `_run_dispersion` (the §9e
  wiring is the template). Per basket: read this tick's frozen holdings and the prior frozen snapshot (both
  under `ingest/holdings/{series_id}/{date}/`), call the sensor's diff, and if material, accrete onto the
  basket's live lead(s).
- **Find the live leads via the shared `watching_leads` forward-hash** — the same resolver the mandate/SOI
  advisory routing uses for `on_live_lead`. Do **not** re-derive "which leads are on this basket" a second
  way; reuse the one canonical resolver (single-source-of-truth — same reason `on_live_lead` used it).
- **Seed / fault per basket (§9g)** *(corrected 2026-07-12 — see note below)*: a basket with **no prior
  frozen pull (first sight) → SEEDS SILENTLY** (baseline it, no event, no fault — a cold start is the
  expected initial state of an append-only record, not a malfunction; the same first-sight baseline launch
  and mandate already do). **Unparseable / broken holdings → faults that basket, not the run** — honest,
  never a guessed diff. The two conditions are distinct: missing-because-first-time is silent;
  broken-or-unreadable is loud.

  > **Correction (2026-07-12).** This bullet originally read "a basket with no prior snapshot to diff
  > against, or unparseable holdings, **faults that basket**." That was wrong for the first-pull case:
  > faulting a normal cold start would page ~11 baskets on the first rebalance tick — the day-one
  > nuisance-alarm §10 exists to prevent. Corrected to seed-silently-on-first-pull, fault-only-a-broken-feed
  > (ratified `docs/decisions/2026-07-12-rebalance-runner-wiring.md`). Recorded, not silently rewritten.

## 3. The design calls (small — decide, then Code wires)

- **Materiality — rebalance vs daily drift.** Holdings weights drift *every* tick (prices move); the sensor
  must not accrete that noise. The robust primary signal is a **membership change** (a constituent entered or
  left) — discrete and unambiguous; a large **weight shift** past a threshold is the secondary signal. Confirm
  the built sensor already distinguishes these; the threshold is a **DEFAULT**
  (`rebalance.material_weight_shift`, etc.) — tuned so a routine reconstitution registers and daily drift does
  not.
- **Which leads accrete.** A basket can carry an xcorr lead *and* a dispersion shadow lead. Accrete onto
  **all** live leads for the basket, non-shadow and shadow alike — the rebalance event is accretion onto a
  lead (not a fault or spawn), so it doesn't page and there's no paging concern.
- **A material rebalance on a basket with NO live lead.** Per the capture-broadly discipline, **record it
  survey-style** (a `rebalance.unattached` fossil, like a launch-survey entry) rather than drop it — the fossil
  is cheap and a later firing on that basket can reference it. It accretes onto nothing; it just isn't lost.
  (If the built sensor already drops these, that's a defensible alternative — Lyle's call; lean is
  record-don't-drop, consistent with launches.)

## 4. Acceptance — tests attempt the violation

Against a seeded store with real-shaped holdings fixtures:
- **material rebalance accretes:** a basket with a live lead + a constituent add/drop → a `rebalance` event on
  that lead's timeline.
- **daily drift does NOT accrete:** the same basket with only sub-threshold weight drift → **no** rebalance
  event (the materiality threshold works — the violation-test is that noise is suppressed).
- **accretes onto all live leads:** a basket with both an xcorr and a shadow dispersion lead → the rebalance
  lands on **both**.
- **no-live-lead handling:** a material rebalance on a basket with no lead → recorded survey-style (or
  dropped, per the ruling), never accreted onto a random lead.
- **first-sight seeds silently (corrected):** a basket with no prior frozen pull → **seeds, no fault, no
  event** (run stays clean on the first rebalance tick); an **unparseable** current feed → **faults** that
  basket, the run continues. Two conditions, two violation-tests (they point in opposite directions).
- **never spawns:** confirm `_run_rebalance` emits no `lead.spawned` — accretion only.

Suite stays green plus these.

## 5. Sequence

Independent of everything queued; lands through the CI gate like any slice. It completes the M4 sensor set —
after it, the runner's sensor phase is whole, and the remaining v1 work is the M7 autonomy core (scheduling +
dead-man) and durability.
