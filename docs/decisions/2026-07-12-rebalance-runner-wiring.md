# Rebalance runner wiring — shadow-inclusive routing, seed-on-first-sight, same-tick to `_system`

*Decision record, 2026-07-12. Ratifies the three design calls made wiring the already-built rebalance
sensor (`sensors/rebalance.py`) into the M5 runner (`_run_rebalance`) — the last M4 sensor into the
runner. Governing: spec §4d (rebalance accretion), §9 (runner). Build note (corrected in the same
change): `docs/notes/2026-07-11-rebalance-runner-wiring.md`. Implemented in commit on branch
`rebalance-runner-wiring`.*

## Context

Rebalance is an **accretion** sensor: no Schmitt, no lead of its own. It diffs a watched fund's frozen
holdings today vs the prior pull and, on a **material** change (an identified-security add/drop, or a
weight move ≥ `rebalance.weight_delta_threshold`), accretes a `rebalance` onto every live lead whose
baskets include the fund (forward-hash `watching_leads`), else onto `_system`. The fold treats
`rebalance` as a **silent corroboration** — no `{status,shadow,verdict}` change — so `_compute_push` can
never page on it. That "accretion never pages" property is what makes the calls below safe by
construction. The sensor was complete; this was a **wiring** slice reusing the §9e frozen holdings.

## Decision 1 — the active-lead set INCLUDES shadow leads

The routing target is "every live lead whose baskets include the fund." That set is read from the
registry's **materialized fold** (CONTRACT §4d), filtered to active leads — and it **includes shadow
(burn-in) leads**. Implemented as `active_incl_shadow_lead_ids`, a **sibling** to the shipped
`active_nonshadow_lead_ids`: one source (the materialized snapshots), two filters differing on the one
`include_shadow` dimension.

**Why include shadow — and why the divergence from the non-shadow helper is correct, not a smell.** The
mandate/SOI paths exclude shadow because they can **page**, and a burn-in lead must not trip the alarm.
Rebalance pages nothing. So the reason to wall off shadow does not apply. And it matters concretely:
**right now every dispersion lead is shadow** (the 0/90 burn-in), so the non-shadow filter would sever
rebalance from the **entire dispersion side** — precisely the spawner whose unproven leads most want a
second, independent "this basket really is restructuring" signal. Including shadow adds evidence to the
burn-in record without ever paging — strictly more information when you go to promote a lead, and safe
because accretion can't create the risk the shadow wall protects against. The two filters exist because
their paths have different rules (one pages, one doesn't); the sibling `active_incl_shadow_lead_ids`
carries a load-bearing comment forbidding a "consistency" refactor back to the non-shadow helper.

**Guard:** a dedicated violation-test (`test_shadow_only_lead_receives_the_rebalance`) — a basket whose
**only** live lead is a shadow dispersion lead — fails if the set is ever narrowed to non-shadow, which
every other test would still pass.

## Decision 2 — seed silently on first sight; fault only a broken feed *(a build-note correction)*

A basket with **no prior frozen pull (first sight) SEEDS silently** — no event, no fault. An
**unparseable / broken** current feed **faults** that basket (operational; the run continues).

**Why.** A fault means something broke; a first-ever pull is the **expected initial state** of an
append-only record, not a malfunction. Faulting it would page ~11 baskets on the first rebalance tick —
the day-one nuisance-alarm the whole §10 layer exists to prevent (a "cried wolf" first run trains the
operator to ignore the alarm). It also matches what **launch** (seeds) and **mandate** (baselines)
already do on first sight — rebalance is the same diff shape, so it seeds and begins diffing on the
second observation. This **corrects the build note**, which originally said "no prior snapshot → faults
that basket"; the correction is recorded in the note, not silently rewritten (append-only honesty).

**The line held:** missing-because-first-time is silent; broken-or-unreadable is loud. Two
violation-tests, pointing in opposite directions: `test_first_sight_basket_seeds_silently` (the run stays
clean) and `test_broken_current_feed_faults_that_basket` (the fault path survives).

## Decision 3 — same-tick spawn+rebalance routes to `_system`; keep the §4d CONTRACT, no amendment

The active set is read from **materialized snapshots**, which are written in run-order **step 6**, *after*
the sensor phase. So a lead spawned **this tick** is not yet snapshotted when rebalance runs: a basket
that both **spawns a lead and rebalances on the same tick** routes that first rebalance to `_system` and
accretes onto the lead **from the next tick on** (self-correcting; the record still holds the rebalance).

We **keep** this and do **not** amend §4d. The cost of the CONTRACT's trade is bounded and self-healing:
one tick of corroboration on a **rare co-occurrence**, and the datum is filed under `_system`, not lost.
The cost of the alternative — re-folding here to see same-tick spawns — is **permanent**: it reintroduces
exactly the re-fold-divergence risk the §4d "materialized fold, never re-fold" discipline was written to
forbid, across the whole sensor phase, and every future reader would have to reason about whether a
sensor reads materialized state or a re-fold. A self-correcting, bounded imperfection is cheaper than
weakening a load-bearing invariant to erase it. Commented where it lives (in `_active_lead_ids` and
`_run_rebalance`) so it reads as a deliberate consequence, not a bug to "fix." If the co-occurrence ever
proves *not* rare, the revisit is a targeted **materialize-earlier** step, not a re-fold.

## Also decided (in passing)

- **No `rebalance.unattached` type.** The build note floated a distinct survey type for the no-live-lead
  case; the sensor already routes those to `_system` (record-don't-drop), so no new event type is added —
  a new type would be an out-of-scope sensor change.
- **Idempotency.** A re-run of the same tick does not double-emit: a basket whose `(series_id, as_of)`
  `rebalance` is already in the record is skipped (mirrors the N-series idempotency discipline).
- **Current holdings via pull-if-absent.** Rebalance reads today's frozen file (the §9e dispersion pass
  froze it earlier this tick) and pulls only if it is absent — no double-fetch in the common case, and no
  silent dependency on dispersion having run.

## Scope / what did NOT change

`sensors/rebalance.py`'s `diff_holdings` / `watching_leads` / `scan` are unchanged (the sensor was
built). `parse_nport_holdings` stays the labeled §3b stub. Holdings-intake coverage (per-issuer / NPORT-P)
is unchanged — this slice reuses the SPDR §9e vertical, and widening intake remains a separate,
rate-widening concern, not part of the wiring.
