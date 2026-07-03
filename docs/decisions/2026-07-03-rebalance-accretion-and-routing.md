# Rebalance sensor: accretion core first, and how a fund finds its live leads

**Status:** design-thread guidance, ratified 2026-07-03; folded into spec **rev9 §4d** (Decisions 1
and 5 are CONTRACT there). Records the rebalance sensor's scope decomposition and the routing /
enumeration decisions, and names the deferred slices so they cannot become open-ended "v-laters." The
holdings-diff accretion core is built (`prospector/sensors/rebalance.py`); `mandate.changed` and the
NPORT-P cross-check are deferred with named unblocks.

## The decomposition — §4d splits like §4c

The rebalance sensor splits exactly as the launch sensor did (§4c): a **self-contained core** plus a
**half that needs new, loosely-coupled surface.** That recurrence is the seam discipline working, not
a coincidence — "completeness of §4d" is the wrong seam, the same way "complete per §4c" was wrong for
launch.

- **Holdings-diff accretion (built, this slice).** Diff a watched fund's frozen daily holdings
  (`ingest/holdings.py`, already built) vs its prior pull; a material change (DEFAULT: any add/drop, or
  a weight delta ≥ `rebalance.weight_delta_threshold` = 0.5%) accretes a `rebalance` event onto every
  live lead whose baskets include that fund, else onto `_system`. Self-contained: reuses holdings
  ingest, touches no CONTRACT-validated code.
- **`mandate.changed` (deferred — its own defined next slice).** A new prospectus filing whose mandate
  *text* differs from the stored copy. Deferred because it needs surface that does not exist: an EDGAR
  prospectus-**text** fetch (the client fetches only JSON metadata today) + mandate **storage** + a
  text diff. **Named unblock:** prospectus-text fetch + `ingest/prospectus/` storage working against
  live filings. Not built here.

Rebalance is a pure **accretion** sensor: no Schmitt trigger, no lead of its own. The fold already
treats `rebalance` (and `mandate.changed`) as a **silent corroboration** — it lands on a lead's
timeline and never changes `status`, `shadow`, or `verdict`, so it never pages. No fold or envelope
change was needed.

## Decision 1 (CONTRACT) — routing by forward-hash, no payload change

To accrete onto "every live lead whose baskets include this fund," we need `series_id → live leads`.
Dispersion leads carry `series_id` in their payload; **xcorr leads encode their series_ids only in the
(one-way) lead-id hash.** The resolution is **forward-hash**, not payload enrichment:

- The lead-id is already the **canonical encoding** of a lead's series_ids (`xcorr_lead_id` hashes the
  sorted pair; `dispersion_lead_id` hashes the basket). So recover the mapping by enumerating a fund's
  memberships — its 10 sector pairs and its own basket — and hashing each with the **existing functions
  reused verbatim** (so canonicalization matches by construction), then intersecting with the active-
  lead set.
- **Do not** add `series_ids` to the `xcorr.departure` / `lead.spawned` payloads. Duplicating what the
  lead-id already encodes creates a second source of truth that can drift from the hash — a bug class
  (what happens when payload and hash disagree?) avoided by never creating it.
- Trivially cheap at the fixed 11-sector scale. **v2 revisit:** if auto-expansion makes forward-hashing
  the whole universe expensive, build a maintained `series_id → active-lead` index *from the same
  functions* — still not denormalized payload duplication.

## Decision 5 (CONTRACT) — enumerate from the registry-materialized fold, no cache

The active-lead set is read from the **registry's materialized state — the snapshots the fold already
writes** (`Registry.all_leads()` + `Registry.latest_snapshot()` → the snapshot file's `status`/`shadow`).
**Not** by re-folding every lead at run time, and **not** via a separate lead-to-baskets cache (a
redundant materialization that can drift from the fold; forward-hashing inverts the lookup — fund →
candidate leads — so no such index is needed). Single source of truth stays the fold, materialized in
the registry. A corroboration (like a rebalance) does not change status/shadow, so the latest snapshot
stays authoritative between state-changing events.

*Runner-ordering note for §9 (M5+):* the pure router takes an `active_lead_ids` set, so the runner
supplies whatever active set it computes; `active_nonshadow_lead_ids(registry, layout)` is the
CONTRACT-default snapshot read. The runner must decide intra-run freshness (a lead spawned by
xcorr/dispersion *earlier in the same daily pass* is not yet in the previous snapshot) — a runner
concern, out of scope for this sensor slice.

## Decisions recorded for the deferred slices (not built now)

- **Decision 2 — mandate storage = blob per accession, never in `FundEntry`.**
  `ingest/prospectus/{series_id}/{accession}/`, frozen per accession, SHA'd, reference-only in the
  registry (§7, added in rev9). Decisive reason: `mandate.changed` is a **diff across accessions**, so
  every version must be kept immutably. Cramming `prospectus_text` into `FundEntry` and overwriting on
  re-filing is a *mutation* that destroys the prior version and breaks the very thing the sensor
  exists to detect. Blob-per-accession is append-only by construction.
- **Decision 3 — NPORT-P scope = holdings-table only.** Targeted extraction via proper XML parsing of
  the holdings elements — not a full NPORT-schema object model (capacity you won't use), not a fragile
  regex. Deferred with §3b; `holdings.parse_nport_holdings` stays a **deliberately thin stub** — do
  **not** fill it with survivor-biased data (Appendix B's caveat). The accretion core uses the issuer
  daily holdings CSVs, not NPORT-P, so it is unblocked now.
- **Decision 4 — quarterly trigger = the one daily runner, event-driven.** A quarterly NPORT-P (or a
  new prospectus) is detected by the daily filings-index check the day it posts and processed then
  (audit = detection, §3). No separate quarterly cron. The *processing* of each is gated on its slice
  (mandate-diff / §3b); the *trigger* is the single daily runner.

## Sequencing (rev9 §12)

rebalance-accretion *(built)* → **mandate-diff** *(next slice — the prospectus-text unblock)* → **launch
corroboration hook** *(the M4 capstone — its own PR, hardest review, brought back to the design thread
before its test goes green, because it carries the honest-test boundary)* → the §9 runner + M5 outputs.
