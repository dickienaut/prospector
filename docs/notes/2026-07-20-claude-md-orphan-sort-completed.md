# The completed sort — E-category, the protected-list cross-check, and one correction back

*2026-07-20, build seat. Completes `2026-07-20-claude-md-orphan-sort-build-seat.md` with the two
additions Design ratified it subject to: the **E category** (operative rules that belong in CLAUDE.md
and are not there in any form) and the **network-guard reclassification**. Also does the cross-check
Design asked for — the scar-tissue protected list against my 36 probes — and reports **one verified
correction to Design's own list**.*

---

## 1. Accepted: the axis I was missing

Design is right, and the diagnosis is precise. I sorted on one question — *is this a build contract?* —
and treated "no" as implying "constitutional or METHOD.md." The missing axis is **operative vs
explanatory**:

> METHOD.md explains **why the model works**. CLAUDE.md says **what this seat must do**.

*"Tests are offline; a network guard fails any test that opens a real socket"* is **operative**: a seat
can violate it, and something enforces it. That is CLAUDE.md, not METHOD.md. I reached for METHOD.md
because I was sorting on "not a build contract" and METHOD.md was the nearest non-spec home — which is
sorting by elimination, not by the rule.

**Reclassified: the network guard is not a lone Category C clause.** It is one third of an operative
**testing-discipline cluster**, and the constitution carries none of the three cleanly today.

---

## 2. The protected-list cross-check — clean, with one probe correction

Design: *"every clause on that list must be accounted for by name in the final sort, and if any protected
clause isn't in Code's 36, that's the gap. Cross the two lists."*

**Done. All 14 protected clauses are accounted for; no gap.** One needed a second probe:

**"No fixture silently stands in for a real filing"** — my probe set covered *"fixtures are never
refreshed by fetch"* (spec `:39`) but not this one, and the phrase itself returns **0 in the spec**. It
resolves anyway, at `spec.md:47`, as the positive form of the same rule:

> *"Every test fixture is either **recorded-real** (with a source-URL + retrieval-date provenance header)
> or **declared synthetic** in-band."*

*Every fixture is one or the other* and *no fixture silently stands in* are the same rule stated
positively and negatively. **Category B** — accounted for, not a gap.

**Where the two lists overlap, and the tie-break that resolves it.** Eight protected clauses also resolve
in the spec, which under a naive reading makes them "B: delete from CLAUDE.md" — directly contradicting
"must survive the diff." The firewall precedent settles it, and it generalizes:

> **Resolving in the spec does not demote a constitutional invariant to a duplicate.** For clauses that
> bind *every seat regardless of what it is building* — the firewall, no-LLM-text-as-data, no-run-now —
> duplication is **correct**, and the constitution keeps them.

So the sort's B/C test is not "is it in the spec" but Design's original filter — *build contract, or
invariant every seat obeys?* Spec-presence is evidence, never the decider. Applying that, the protected
list lands: **firewall ×3, no-LLM-text, no-run-now, no-auto-tune → C (stay).** The rest — the stress-gate
mechanics, `sector_min_weight`, `series_ids`, the diff-trap, the bs4 boundary, proto-cluster, macro
catalog, fixture provenance, identity — are build contracts that resolve in the spec → **B**, with
NPORT-P the lone **D**.

---

## 3. Correction back to Design: M-5 is not mechanism, and squash is currently *enabled*

Design's M-5: *"Merge commits, not squash. Ratified… Now partly mechanism (`allowed_merge_methods`),
which makes stating it cheap and checkable."*

**Checked. It is not mechanism here, and the hole is open:**

```
repos/dickienaut/prospector
  allow_squash_merge: true    allow_merge_commit: true    allow_rebase_merge: true

ruleset "main protection" -> [pull_request, required_status_checks, non_fast_forward, deletion]
```

No merge-method restriction at either level. **A squash merge is one click away in the UI**, and a squash
rewrites the record — which append-only forbids. Practice has been correct (every merge in the log is a
merge commit), but practice is not the wall.

**This is the cheapest mechanism win available and it is smaller than the firewall sweep:** set
`allow_squash_merge:false` and `allow_rebase_merge:false`. One API call, converts a ratified-but-unenforced
rule into a wall, and — Design's own point — *makes stating it in the constitution cheap and checkable,*
which is only true once the setting matches the claim.

*(Same class as my firewall-ledger finding: a rule described as mechanism that the repo does not enforce.
Two of Design's enforcement claims have now failed verification; neither was wrong to believe, both were
worth checking.)*

---

## 4. Confirmation: M-2 is where Design said, and I mis-probed it

I first reported M-2's register-currency gate as absent everywhere. **Wrong — Design's placement was
exactly right.** `docs/bugs/README.md:284`:

> *"**A fix is not done until its `INDEX.md` row is current** — the same gate as 'a fix needs a guarding
> test.' A merged fix with a stale row is the class-9 drift this archive exists to stop."*

I probed `register row`; the document says `INDEX.md row`. That line also carries **M-3** ("a fix needs a
guarding test"), so both rules exist — **in a subordinate doc, not the constitution.** Design's framing
holds unchanged: *it lives in `docs/bugs/README.md`; it belongs in the constitution.*

### The method failure worth naming, because it is now a pattern, not an incident

This is my **second** probe-phrasing error in this exercise:

| | I probed | the document says | I reported |
|---|---|---|---|
| 1 | `gics_industry_sector` (a config key) | "industry→sector rollup table… not a tunable" | falsely absent |
| 2 | `register row` (my paraphrase) | "`INDEX.md` row" | falsely absent |

Both times the null was true and the **finding** was false, because I probed my own paraphrase instead of
the document's wording — and a null from a grep is only as good as the phrasing that produced it. Same
family as the mandate arc's central lesson, one level up: *the unit you measure has to be the unit the
claim is about.*

**Operative discipline, and I'd put it in the constitution's testing cluster:** a grep null is not
evidence of absence until at least two alternate phrasings — including the target document's own
vocabulary — have been tried. Every "absent" in the sort now rests on ≥2 probes; the two above are why.

---

## 5. Category E — the operative rules the constitution doesn't carry

Structurally invisible to the orphan sort, which starts from CLAUDE.md's text and asks *where does this
go* — never *what should be here that isn't*. Grouped as operative clusters, with what verification found
about each.

**E1 · Testing discipline** *(one cluster; the constitution carries none of it cleanly)*
- **Tests are offline; the network guard fails any test that opens a real socket.** ← reclassified from C.
  Present in CLAUDE.md's Development section as a passing line; belongs here as a rule. Enforced
  (`tests/conftest.py`).
- **Every fix ships with the violation test that would have caught it.** In `docs/bugs/README.md:284`,
  not the constitution.
- **A fix is not done until its `docs/bugs/INDEX.md` row is current.** Same line, same gap. (M-2/M-3.)
- **A fixture must be proven to reproduce the pre-fix failure.** Fixture *provenance* is a contract
  (spec `:47`); fixture *efficacy* is not stated anywhere. A trimmed excerpt that accidentally fixes the
  document is a fixture that tests nothing — this bit during the 7/19 slice.
- **A grep null is not absence until ≥2 phrasings have been tried.** From §4.

**E2 · Prove the gate bites** — *present in `METHOD.md`, operative form absent from CLAUDE.md.* Not
"missing" but mis-homed: METHOD.md explains why the discipline works; the constitution should carry
**"a gate that has never rejected is observationally identical to no gate."** (M-4.)

**E3 · Verification scope** — the 2026-07-18→20 arc, currently only in notes:
- **Verify against the unit that *acts*, not the unit you changed.** (Three nested misses in one arc.)
- **A fix verified only on the artifacts it targeted is verified on a biased sample** — and the frozen
  substrate makes the full replay nearly free (`tools/corpus-check/`).

**E4 · Seat model, operative subset** — the QA seat, the `qa/*` findings-PR path, Option-2 composition
(RED test + reference patch, `xfail(strict)` handoff). A four-seat constitution that never names QA is a
Prospector constitution wearing a four-seat coat. (M-1, M-6.)

**E5 · Record integrity** — **merge commits, not squash** (M-5; **and fix the setting first**, §3).

**E6 · Deploy** — **production deploys from a tag, by mechanism** (`ops/deploy.sh` refuses any non-tag,
takes the single-writer lock). And **the deploy is not the proof; the tick is** — an untested path that
looks clean because it never ran is a green earned for the wrong reason; record the null, name the retest
date.

**E7 · Honest attribution** — **mark what you cannot attribute; never present it as clean.** The third
option between suppressing (which re-inflates noise) and emitting silently (which writes a confident
falsehood into an append-only store). Same family as `sectors_unresolved` and `holdings-unavailable →
dormant`, for the case where the signal is real and only its *attribution* is uncertain.

---

## 6. State of the sort

| category | count | action |
|---|---|---|
| **A · orphan** | 0 | — |
| **B · duplicate** | ~31 | delete from CLAUDE.md, keep the pointer |
| **C · constitutional** | ~6 | stays (incl. the protected list's cross-cutting clauses) |
| **D · partial** | 1 known | fold the delta (§3b NPORT-P hazard), then delete |
| **E · missing** | 7 clusters | add to CLAUDE.md |

**Ratifiable subject to the QA pass**, which Design has scoped: re-read each B-row against its **full spec
section**, not the grep hit, hunting for further Category D. NPORT-P was found by noticing a missing
qualifier; the assumption should be that there are more. My §4 pattern sharpens the brief — QA should
also distrust any "absent" that rests on a single phrasing, mine included.

**Two mechanism changes to land before or alongside the rewrite**, both one-PR-sized and both making a
constitutional claim true rather than aspirational:

1. **Disable squash/rebase merge** (§3) — one API call.
2. **Package-wide firewall grep** replacing the 6-of-54-module allowlists (from the Build read) — ~5 lines.

Neither is a doc change, and the constitution reads more honestly after both.
