# QA finding — METHOD.md rule-3 consolidation (the reviewed_sha scar)

**Seat:** QA (cold read, repo of record) · **Reviewed against `main` @ `5cf0b62`**, 2026-07-17
**Class:** doc-drift / one-home violation · **Severity:** LOW (documentation coherence; no code or gate affected)
**Target file:** `METHOD.md` · **Deliverable:** `METHOD_rule3_consolidation.diff` (git apply --check CLEAN on pristine `main`)

## What the scar is

Rule 3's QA sub-clause graduated to *enforced* on 2026-07-16 (the `reviewed_sha` gate in
`deliver_qa_findings_pr`). METHOD.md records the graduation correctly in the per-seat ledger, but the fact
is scattered across the doc and cited nowhere — the doc fails **two of its own standards** at exactly this spot:

1. **"This doc can't become a second home for one rule"** (its own precedence note). The reviewed_sha
   mechanism is described in *two* places: the rule-3 ledger bullet ("QA — enforced") **and** a separate
   `**QA verification**` paragraph down in *Why it works*. Two homes, one rule.
2. **"Every durable claim is tied to something outside the narrative"** (the anchoring rule). The header
   anchors only "(rules 1, 2, 6)" to the verification record — but that record **already contains a
   `## Rule 3 (QA sub-clause) … · CONFIRMED (QA seat)` section** (verified: `docs/notes/2026-07-16-method-
   mechanisms-qa-verification.md`, 4610 B). So the enforced sub-clause has an anchor and the doc doesn't cite it.

The `**QA verification**` paragraph is also **malformed** — a bold run-in with no `##`/`**…**` heading break,
carrying trailing-whitespace lines — so it renders as an orphan mid-section.

## Ground truth checked (primary source, not memory)

- `docs/notes/2026-07-16-method-mechanisms-qa-verification.md` **exists on `main`** and its section list is
  Rule 1 / Rule 2 / **Rule 3 (QA sub-clause)** / Rule 6 / Rule 6-other-half — all `CONFIRMED`. The rule-3
  section names the shipped `deliver_qa_findings_pr` gate and `proof_reviewed_sha.py` (exit 0).
- `proof_reviewed_sha.py` is **not** in the prospector repo (it is QA tooling / a Claude Science artifact) —
  so the patch cites the **in-repo verification record**, never a path that doesn't exist.
- The shipped `prospector-branch-qa` skill still carries the required-`reviewed_sha` gate (raises on omit /
  non-40-hex / mismatch before any push). The ledger's "enforced" claim is accurate.

## What the patch does (and does NOT)

- **Header:** acknowledges the record also anchors the enforced QA sub-clause of rule 3; adds "the shipped
  skill" to the checked-against list.
- **Rule-3 ledger bullet:** makes it the *single home* — appends the citation (record + § + RED/GREEN +
  meta-controls). The mechanism is now defined once, there.
- **Why-it-works:** deletes the malformed orphan paragraph; re-homes its *insight* as a properly-formatted
  bullet next to "the record only saves you if it's anchored" — as a back-reference to rule 3, not a second
  description of the mechanism.
- **Does NOT promote rule 3 to the enforced tier.** That would over-claim: "enforced" means a gate a
  stochastic seat physically cannot cross, and that is true for the QA seat only. Rule 3 stays aspired with a
  per-seat ledger; the patch makes the seam *legible and cited*, which is the honest state. Full graduation
  (all seats) remains rule #5's next candidate — not this PR's job.

## Verification

- `git apply --check` **CLEAN** on a pristine `main` checkout; applies OK.
- Post-apply assertions pass: orphan heading count 0; single-home citation present; header cites rule 3;
  re-homed bullet present. Net: 15 insertions, 10 deletions, one file.

*Review-and-report only. No merge. The consolidation is one of three items the Code seat has queued behind the
now-merged PR #88; this covers the rule-3 half, which is QA's graduation to speak to.*
