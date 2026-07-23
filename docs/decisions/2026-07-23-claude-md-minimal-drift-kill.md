# CLAUDE.md — a minimal drift-kill now; the full ratified consolidation deferred with a trigger

**Date:** 2026-07-23
**Status:** ratified (design thread — the owner chose minimal-now over the full consolidation; Design endorsed
and set the deferral trigger). Build seat executed.
**Touches:** `CLAUDE.md` (the constitution) — three drifted clauses corrected by **surgical amendment** under
amend-never-regenerate's *normal* path, NOT the escape-valve consolidation rev.
**Governing rule:** `docs/decisions/2026-07-11-canonical-docs-amended-not-regenerated.md` (amend the canonical
docs by surgical diff; a full rewrite is allowed only as an explicit consolidation rev with a clause-by-clause
diff proof). This change is **not** that rewrite — it is a targeted correction of clauses the code and existing
decision records already falsify.

## The finding

The constitution carried three claims that had gone false or stale against the shipped code:
- **A2 — a hard-coded spec rev that keeps drifting.** The opening pointer said "the canonical spec is
  `docs/spec.md` (**rev 15**, …)" plus a rev-walk narrative (Rev12→Rev5); the spec is now **rev 18**. This
  pointer has re-drifted repeatedly (measured ~four times) — the recurring cost of duplicating a version number
  the spec already carries in its own header, against CLAUDE.md's *own* rule ("the rev … lives in the header,
  one home").
- **A3 — `mandate.changed` called "deferred" while it is built and live.** Two clauses said `mandate.changed`
  is "a deferred defined-next-slice" — one inside the rev narrative, one in the §4d rebalance-routing bullet.
  The mandate-diff arc shipped (extract/diff on the frozen per-accession blob; the B1 series-scoped + block-
  isolation stack; `mandate.py` emits `mandate.changed` live). The doc even contradicted itself in-file ("Rev10
  recorded mandate-diff built").
- **A stale "DEFERRED to M5" for live SOI-fetch.** The M5 runner shipped; SOI-fetch is built.

A cold seat reading these today is told the sensor is deferred while it executes — the doc-drift class where
status prose outside a regenerated section rots (bug-archive class 9).

## The decision — minimal drift-kill now

Kill the false/stale claims; do **not** attempt the full ratified consolidation. Three surgical edits:

1. **C-1 · version-free spec pointer.** Replace the rev-15 pointer + the whole Rev12→Rev5 narrative with:
   *"The canonical spec is `docs/spec.md`; read its header for the current rev; earlier revs in
   `docs/history/`."* This kills A2 at the root (the pointer names no rev, so it cannot drift again) and, with
   it, the narrative's embedded A3 instance. **Protected-list check (done before deleting):** the narrative's
   five embedded CONTRACT claims each verified present in **spec rev 18** — the §9-runner
   mandate-prior-from-the-frozen-blob invariant (spec `:58/:87/:269`), forward-hash routing (`:100/:264`),
   `sectors_unresolved` (`:69-70`), the registrant-level `prospectus_accession` residual (`:60/:210`), and the
   frozen GICS industry→sector rollup (`:73`). So the deletion drops **no live contract**.
2. **The §4d bullet's `mandate.changed` clause** corrected from "a deferred defined-next-slice (unblock: …)" to
   its true built status. The surrounding CONTRACT (forward-hash routing, the NPORT-P §3b stub) left verbatim.
3. **"Live EDGAR-SOI-fetch is DEFERRED to M5"** → "built (the M5 runner)"; the still-true drop-and-freeze-vs-
   fetch-on-cadence principle kept.

**Left byte-identical (verified):** the **Firewall** clauses ("never read the detector's bucket / `portfolio.
yaml`"; "never place, size, or recommend a trade"; "the connection is human and one-way") — surfaced and
confirmed **live, not stale scar tissue** (the first is now mechanically enforced by the P-1 package-wide sweep,
#127; the others are capability-absence + architecture). No design call is triggered because minimal-now touches
none of them. Also verbatim: every still-true status line (`parse_nport_holdings` §3b stub, proto-cluster
v2-not-built, launch-corroboration existence-proof).

**Traceability:** the corrected claims trace to already-recorded decisions — mandate-diff built (the
`2026-07-03-mandate-diff-*` + `2026-07-21-mandate-*` records), the M5 runner built, and the reconciled note's
C-1 ruling; the version-free pointer restores CLAUDE.md's own header-is-the-one-home rule.

## Why minimal, not the full consolidation (Design's ruling)

The two halves differ on both urgency and risk. The **false claims are urgent and zero-risk** — a cold seat
misled today, cheap to fix — and C-1 already kills the recurring rev-drift at its root. The **restructure**
(the reconciled note's C-2 compression, 32-row deletions, structure moves, §3d additions) is **non-urgent and
real-risk**: its one safety mechanism — the protected-list check — cannot be mechanized, because the hazard is
exactly a scar clause smoothed away by the person surest it is unnecessary, and that failure is silent and
effectively permanent. Run at the tail of a long doc-PR it gets rubber-stamped. Bias toward protecting the
irreversible: worst case of minimal-now is a verbose doc missing the QA-seat rules for a while (visible,
recoverable); worst case of full-now is lost scar tissue no one notices.

## The deferred full consolidation — trigger + hard requirement (so it does not decay)

Deferred ratified work decays, and this has been deferred once already, so it gets a **concrete trigger, not
"later"**: its **own dedicated session**, the reconciled note
(`docs/notes/2026-07-21-claude-md-consolidation-reconciled.md`) open beside the diff — now unblocked, since the
pagination + §8a work has landed and the §3d additions list has stopped accreting under it. **Hard requirement
for that session:** ship the **§4 protected-list table as part of the PR** — every scar-tissue clause × its
single canonical home × verified-present — so the owner reviews **~14 rows, not ~300 lines**, and the
un-mechanizable attention problem mostly dissolves (Design's stated condition for doing it full-now). It also
runs the escape valve in full: a clause-by-clause diff proof in *its own* decision record, the §4 protected-list
check, and the §7.4 QA cold post-check (a re-plant of the firewall violation, which must go RED).
