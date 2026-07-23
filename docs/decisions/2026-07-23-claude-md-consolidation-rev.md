# CLAUDE.md consolidation rev — the clause-by-clause diff proof + the §4 protected-list table

**Date:** 2026-07-23
**Status:** ratified (design thread — the reconciled edit-list is the spec; the owner reviews the diff against
it, then QA runs the §7.4 cold post-check). Build seat executed.
**Type:** an **explicit consolidation rev** under CLAUDE.md's amend-never-regenerate escape valve
(`docs/decisions/2026-07-11-canonical-docs-amended-not-regenerated.md`), which requires this record — the
clause-by-clause diff proving **no CONTRACT changed except the ones the ratified list intended**.
**Spec:** `docs/notes/2026-07-21-claude-md-consolidation-reconciled.md` (the reconciled edit-list). C-1 (the
version-free spec pointer) landed earlier in `2026-07-23-claude-md-minimal-drift-kill.md`; this rev is the rest.

## Volatile-at-cut re-verification (reconciled §7.2)
Re-checked at execution (three prior reads each caught these drifting): spec pointer = version-free (C-1 on
main); spec header = **rev 18**; suite = **721 passed / 4 skipped / 2 xfailed** (the reconciled §5 685-baseline
is stale); GitHub merge flags = `allow_squash_merge:false`, `allow_rebase_merge:false`, `allow_merge_commit:true`
(so the §3d "merge commits, never squash" is true as written).

## What changed, clause by clause (every change traces to the reconciled list or a decision/spec anchor)

- **C-2 · `## CONTRACT vs DEFAULT` compressed to an amendment index.** The ~90-line narrative reduced per entry
  to *operative constraint + `decisions/` record* — the rule applied: *drop the narrative around the imperative,
  never the imperative*. **Every "never" is retained** (grep-verified below). Two deletions inside it: the
  **NPORT-P survivor-bias echo** (deleted — P-2 co-located it in spec §3b, rev 17; now spec-homed), and the
  **stale "macro-catalog … remain milestone 5"** status line (a false status claim — M5 shipped; not a CONTRACT).
- **C-3 · the three doc-rule sections grouped under `## The record`** — `Append-only`, `Canonical documents —
  amended, never regenerated`, `Doc naming — provenance in the filename` (a move; their text is verbatim).
- **C-5 · `## Identity` → `## Fund identity`** (+ a one-line cross-ref that the machine-account identity is the
  seats/merge-gate, not this fund-key rule). Fund-key text verbatim.
- **C-6 · header map + section list** — the five-line map (*operative here · why → METHOD.md · contract → spec ·
  scars → docs/bugs · this file wins*) + a ToC of section names; **no "index of every NEVER"** (the recorded
  rejected alternative).
- **§3c · `## Enforcement tiers`** — the honest firewall ledger (mechanism / mechanism-adjacent / prose).
  **DEVIATION FROM THE RECONCILED NOTE, recorded as a finding:** the reconciled §3c cell said the detector-bucket
  is a "P-1 sweep term (in-repo)." That is **not what shipped.** `tests/test_firewall.py` enforces it via an
  **S3-client-confinement proxy** — an import-root sweep over `("boto3","botocore","s3transfer")`, only
  `store/s3_sync.py` may build an S3 client — with **named gaps** (a bare bucket-name string with no import; a
  not-yet-enumerated dependency) and the **real wall at IAM, outside CI**. The rev writes the shipped truth;
  writing "sweep term" would have shipped the drift the consolidation exists to kill.
- **§3d · the missing operative rules folded in** (imperative + anchor, no restated reasoning): `## The seats`
  (QA exists; `qa/*` PRs; Option-2 composition; the machine-account boundary), `## Verification` (ship the
  violation test · prove-the-gate-bites · verify the acted-on unit · the tick is the proof · the INDEX row ·
  corpus-check parser changes), and inside `## Development` the **merge-commits-never-squash** mechanism and
  **deploy-from-a-tag-by-mechanism**.

**No other section changed.** Firewall, Vendored store provenance, No-LLM-text, No-run-now, Config honesty,
Alert posture, Standing review items, Fixture provenance, Documentation — **carried verbatim** (diff shows them
unchanged).

## §4 protected-list table — every Design-§4 scar shown present in a canonical home (verified)

Source list: `docs/notes/2026-07-16-claude-md-consolidation-design-seat-findings.md` §4. Rule: each scar in a
canonical home (spec, CLAUDE.md points · or CLAUDE.md constitutional), the **Firewall the one both-homes
exception**. "Verified" = grepped present at execution.

| # | scar (short) | home | verified present |
|---|---|---|---|
| 1 | Firewall — all three bullets, whole | **CLAUDE.md + spec (deliberate exception)** | CLAUDE.md `## Firewall` byte-identical; firewall test green |
| 2 | No-LLM-text · No-run-now | CLAUDE.md constitutional | `## No LLM text as data`, `## No run-now surfaces` (verbatim) |
| 3 | Never a rolling percentile / self-updating window | CLAUDE.md constitutional | `## Standing review items` (verbatim); + a one-line index label in `## CONTRACT vs DEFAULT`; spec §4a |
| 4 | NPORT-P — never survivor-biased data | **spec §3b** (P-2) | deleted from CLAUDE.md; spec `docs/spec.md` §3b (rev 17). CLAUDE.md count 0 |
| 5 | No import from sibling `models/` | CLAUDE.md constitutional | `## Vendored store provenance` (verbatim); spec cross-states :471 (pre-existing) |
| 6 | No wide typed-metric columns | CLAUDE.md constitutional | `## Vendored store provenance` (verbatim); spec :135/:287/:471 (pre-existing) |
| 7 | Anti-fitting — dormant NEVER lowers `sector_min_weight` | **spec §4c** (:73/:81) | CLAUDE.md CONTRACT-index label (launch-corroboration) points; full text in spec |
| 8 | Never add series_ids to a lead payload | **spec §4d** (:100/:264) | CLAUDE.md CONTRACT-index label (rebalance) points; full text in spec |
| 9 | Diff strategy-section only, never the whole filing (diff-trap) | **spec §4d** (:93/:267) | CLAUDE.md CONTRACT-index label (mandate-diff) points; full text in spec |
| 10 | bs4 structure / code meaning / human significance | **spec §4d** (:94) | CLAUDE.md CONTRACT-index label (mandate-diff) points; full text in spec |
| 11 | Proto-cluster wall — price-only · cluster-not-name · never-the-trade | **spec §4b/App. B** | CLAUDE.md CONTRACT-index (dispersion payload) carries all three; spec verified verbatim (QA seat) |
| 12 | Macro catalog — both directions (never a trade trigger · never strip the regime) | CLAUDE.md constitutional | `## Standing review items` (verbatim, both directions); spec cross-states |
| 13 | Fixtures never refreshed by fetch · no fixture stands in for a real filing | CLAUDE.md constitutional | `## Fixture provenance` (verbatim) |
| 14 | Bare ticker rejected at the write path | CLAUDE.md constitutional | `## Fund identity` (verbatim) |

**No scar absent from both homes → the diff passes §4.** No scar was flagged stale (a stale scar would be a
second-branch design call, never an in-diff edit).

**Residual honestly stated (protect-the-irreversible bias):** #3, #5, #6, #12 are stated in a CLAUDE.md
constitutional section **and** cross-stated in the spec (pre-existing duplication Design's list marks
constitutional). This rev **kept the CLAUDE.md statements verbatim** rather than delete-with-pointer — biasing
toward not smoothing a scar over maximal single-homing. The scar is safe in every case (present verbatim); the
residual is a pre-existing cross-statement, not introduced here. If Design wants strict single-homing for these,
it is a follow-up ruling, not a loss.

## After this rev (the gate)
1. **Owner** reviews the diff against the reconciled list + this table (~14 rows), merges.
2. **QA §7.4 cold post-check** over the merged result: the protected-list sweep + a **re-plant of the firewall
   violation** — a `portfolio.yaml` read in `prospector/sensors/soi.py` — which must go **RED** (the sweep
   bites). Any finding → a follow-up.

---

## Correction (2026-07-23, post QA §7.4 post-check + Design cold read)

The §7.4 post-check (`docs/notes/2026-07-23-claude-md-consolidation-qa-post-check.md`) **PASSED** — the firewall
re-plant went RED, every scar was grep-present — with one doc-accuracy nit. A subsequent **Design cold read**
caught what a keyword-grep cannot: several §4-homed scars were *present* but had their **operative half**
compressed away in the CLAUDE.md index labels (the descriptive slogan kept, the imperative dropped). Verified
real against the true pre-consolidation original (`<#145-merge>^1:CLAUDE.md`), not paraphrased quotes. All fixed
in the follow-up (CLAUDE.md surgical amendment); this section corrects the record accordingly.

**§4-table row 13 split (QA's nit — the table's home annotation was inaccurate):**
- **13a — "fixtures are never refreshed by fetch code":** home = **spec** (`docs/spec.md` :75, :392, verbatim),
  additionally **mechanized** (fixture `.source.txt` sidecars carry it; `test_edgar_client.py:630` enforces it
  for the frozen `.htm`). It is **NOT** in CLAUDE.md — a correct Category-B deletion; the original table wrongly
  annotated its home as CLAUDE.md `## Fixture provenance`. Scar safe (present in a canonical home).
- **13b — "no fixture silently stands in for a real filing":** home = **CLAUDE.md** `## Fixture provenance`
  (verbatim). Unchanged.

**Operative-half restorations (CLAUDE.md index labels — before → after):** the labels below dropped the
imperative during compression; the full clause was safe in the spec (its home) in each case, but per C-2 the
label must carry the *imperative*, not the descriptive part. The follow-up restores them:
- **bs4 boundary (#10):** was *"bs4 owns structure / code owns meaning / human owns significance"* (slogan only)
  → now also **"the extraction/diff must never grow a 'this change is meaningful' opinion"** (spec home :94/:270).
- **proto-cluster wall (#11):** was *"price-only · cluster-never-single-name · never-the-trade"* → now
  **"price-only, never keyword/NLP mining · …"** (the spec frames it descriptively at App. B :513; the hard
  prohibition is now stated in CLAUDE.md, not implied by "price-only").
- **anti-fitting (#7):** was *"a dormant real outcome NEVER **lowers** sector_min_weight"* (reads as a fact about
  the action) → now *"NEVER **motivates lowering** … never an *argument* to move the threshold"* (forbids the
  reasoning, the original rule; spec home :73/:81).

**Also fixed in the follow-up:** the header precedence line (scoped — this file wins on *seat actions*, the spec
wins on *CONTRACT content*, a disagreement there is a bug in this file's index); the stress-gate index entry
de-duplicated (the "never a rolling percentile" aging rule now lives once, in `## Standing review items`); the
missing **B-M5** sensor-conduct rule ("mark what you cannot attribute — never suppress, never emit as clean")
added to `## Verification`; a Firewall → `## Enforcement tiers` pointer added. Firewall test green; full suite
unaffected. No scar was ever absent from a canonical home — the §4 pass held throughout; these are label/accuracy
corrections, not scar restorations from loss.
