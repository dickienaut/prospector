# Submissions pagination — the undetermined third-state is a review-advisory (§8a, one level in)

**Date:** 2026-07-22
**Status:** ratified (design thread — Design ruled the disposition; the owner relayed). Build seat implemented.
**Touches:** `ingest/edgar.py` (`latest_prospectus`, new `SubmissionsIncompleteError`), `runner/runner.py`
(`_run_mandate`, `_advisory_reporter`); the §8a fault taxonomy (CONTRACT) as applied to the submissions read.
**Builds on:** `2026-07-19-capture-fetch-controlled-vs-uncontrolled.md` (the §8a controlled-vs-open-web split);
the N8 state-collapse rule; the F1 shape-drift split (`SUBMISSIONS-SHAPE-DRIFT`, PR #138).

## The finding

`latest_prospectus` walks `filings.recent` (the newest ~1000 filings) for a prospectus-family form. Finding
none, it returned a bare `None` — the benign "this fund has no prospectus on record." But `filings.files[]`, the
SEC pointer to older filing pages we deliberately do NOT paginate (B2), can be non-empty: the prospectus may sit
in a page we never read. That is a THIRD state — UNDETERMINED, not absent — that the single `None` sentinel fused
with a genuine not-yet. It is the F1 shape-drift split (`SubmissionsShapeError` vs benign `None`) one condition
further along: the same N8 state-collapse class, in the same function family.

The runner gates the mandate diff on `if cur is None: continue`, so undetermined silently skipped the fund — a
fund we watch went dark on a coverage gap, with zero faults (the fail-silent class, class 8).

## The ruling

**`latest_prospectus` raises `SubmissionsIncompleteError`** (a new `EdgarError` sibling of `SubmissionsShapeError`)
when no prospectus is in `recent` while `filings.files[]` is non-empty — mirroring `confirm_prospectus`'s
`older_filings_unread`, already the idiom on the resolution path. The runner routes it to a **REVIEW-ADVISORY**,
per-fund keyed.

### Why review-advisory, not operational — the §8a boundary, sharpened
The capture-fetch decision drew §8a on *source*: a controlled source (SEC/EDGAR) that fails is operational (it
pages); an open-web host that declines is a review-advisory. This case refines that principle **one level in** —
it is not about fetch success, but about **whether the contract was honored**:

- **Operational = something BROKE.** We had a right to expect success and the source did not honor it. F1's shape
  drift is operational: SEC versioned the JSON and our columnar read no longer matches — a broken ingestion layer
  that must page.
- **Review-advisory = something is INCOMPLETE and a human decides.** The submissions fetch **succeeded**; SEC
  honored the contract exactly. *Our request was too narrow* — we chose not to paginate (B2). Nothing broke;
  coverage is incomplete by design. Paging a coverage gap is cry-wolf (a healthy system, a self-imposed limit). A
  retry-disposition (come back next tick) is wrong too: we do not paginate, so next tick re-reads the same window
  and never resolves — it is a punt-to-human, not a not-yet.

### Stable per-fund suppression key
Unlike a per-prospectus extraction advisory (each new unparseable filing is genuinely new information), this
condition is **stable**: the same fund's prospectus stays paged-out until someone paginates. Left unkeyed it
re-emits identically every tick — inflating the heartbeat review count, and paging *every tick* once the fund
touches a live lead (the E1 volatile-message class). It carries a stable per-fund key
(`submissions_incomplete:{series_id}`) so it surfaces once and rides the heartbeat. (`_advisory_reporter` gained
an optional `key=`, backward-compatible — existing sensor advisories keep keying on their message.)

### Scope: `latest_prospectus` only
`prospectus_history` / `latest_soi` share the same latent collapse but are out of scope here: `latest_soi` raising
would route through `classify_soi_target` → `SOI_ERROR` → an operational page, contradicting this review-advisory
ruling (same condition, two surfaces = a defect). Their symmetry is carried to the enumeration follow-up.

### Not built: pagination-following
Fetching the `files[]` overflow pages, merging them, and rate-limiting them is a subsystem for a case that may
never fire. Named here as **deliberately not built** (as the deploy-lock decision named blue-green): the guard
converts a silence into a visible punt at the cost of one condition; following the pages is not on the roadmap.

## Reachability — measured, not guessed (B-M2)
`tools/corpus-check/pagination_reachability.py` asks the real guard over every frozen per-CIK submissions blob,
offline. On 2026-07-22: **0 fire across 30 watched CIKs** — a dormant tripwire, the correct shape. **But 17 of 30
(57%) already carry a non-empty `files[]`** — the pagination substrate is live across most of the fleet; only the
trigger (a prospectus aged past the readable window) is dormant. The guard watches a real, present surface.

## The signature (why this keeps happening)
`edgar.py`'s columnar submissions helpers each return a single sentinel, so every distinct failure mode lands in
the same hole. This is the **sixth** instance — N8's three-way (ambiguous/error/not-yet), F1 shape-drift, F5
prior-coverage, this pagination third-state, and two mislabels found by enumerating the family (SOI `index.json`
drift → `SOI_AMBIGUOUS`; `confirm_prospectus` drift → `http_error`). Doctrine line in `docs/bugs/README.md` §1
(class 8). The discipline: **when you touch one of these helpers, enumerate the states that map to its return and
split any two that are distinguishable AND differently actionable** — distinguishing is not always fixing (a split
may still route to one disposition), but it makes the choice visible.

## Follow-up (flagged, not done here)
- The two mislabels above (**BK-MSG-01 class**: right refusal, wrong cause — the operator is still paged, with a
  wrong diagnosis) batch into one enumeration-follow-up PR, categorically less urgent than a silence.
- Whether the spec §8a prose itself should be surgically sharpened to state the broke-vs-incomplete /
  contract-honored distinction is a CONTRACT-doc edit for Design to rule — not taken unilaterally here.
