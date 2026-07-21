# The orphan sort — which CLAUDE.md contracts fold, which delete, which stay

*2026-07-20, build seat. The job Design assigned in response to the Build read: per orphaned CONTRACT
clause, **is it genuinely absent from `docs/spec.md` (→ fold) or just phrased differently there (→
duplicate, delete)?** That distinction needs the diff, which is why it is Code's. Run against
`docs/spec.md` **rev 16** and `CLAUDE.md` at `c8d2d42`.*

---

## 0. Onboard with the ruling, and why

**No new contract doc. Fold, don't create.** Agreed, and the argument is stronger than tidiness: the
spec's identity *is* "section-numbered CONTRACTs + defaults," so a second contract document would have
no principled boundary against it — and an unbounded boundary is a drift generator with no arbiter.
This repo has closed that defect twice already under different names (`M7-DASH-01`,
`PAGE-WORTHY-MIRROR`: one rule, two homes, prose asking them to stay in sync). A third contract home
would be the same bug with a bigger blast radius, because the two homes would both be *canonical*.

The sorting filter — **build contract → spec section; constitutional invariant → stays in CLAUDE.md** —
is the right cut, and it survived contact with the diff.

**One correction to the framing, earned by running it (§3): a two-way sort is not enough.** There is a
third outcome that neither "fold" nor "delete" covers, and treating it as either silently weakens a
contract. Details below.

---

## 1. The headline: the orphan list is nearly empty

I probed **36 contract-bearing clauses** from CLAUDE.md against `docs/spec.md`. Result:

| outcome | count |
|---|---|
| resolves in the spec (fold **not** needed) | **32** |
| genuinely absent, but **constitutional / process** (stays in CLAUDE.md by the filter) | **3** |
| genuinely absent **and** a build contract (→ a real fold) | **0** |
| resolves but the spec's version is **weaker** (→ amend, see §3) | **1** |

**There is essentially nothing to fold.** The spec already carries the contracts; CLAUDE.md's
CONTRACT-vs-DEFAULT section is, almost in its entirety, a **second home** — which is exactly C-2's
diagnosis, now measured rather than asserted. The consolidation's work is therefore **delete-and-point**,
not **fold-then-delete**, and that is a materially smaller and safer change than either seat expected.

---

## 2. I was wrong about `gics_industry_sector` — and the way I was wrong is the lesson

My Build read named it the one CONTRACT that resolves nowhere in the spec, and built a recommendation on
it. **That finding was wrong.** The contract resolves, at `docs/spec.md:37`:

> *"The **industry→sector rollup table is frozen reference data, not a tunable** — verified **74/74**
> against MSCI's 'GICS structure effective 2023-03-17,' re-frozen only on a GICS revision with a
> `config.changed` fossil… an unknown industry → `fault`, never a silent mis-roll."*

That is CLAUDE.md's clause, in the spec, stated more precisely than CLAUDE.md states it.

**What I actually did:** grepped the *config key name* (`gics_industry_sector`) — an implementation
identifier — and read its absence as the contract's absence. The identifier isn't in the spec because
the spec describes contracts, not config symbols. **I probed for the wrong kind of token and reported
the null as a finding.**

This is precisely the failure Design predicted in the same breath as assigning the job (*"or just
phrased differently there"*), and it is the same shape as the mandate arc's own lesson two days ago:
**verifying the artifact you can see is not verifying the claim you're making.** The correct probe is
the *contract's words*, and — as §5 records — no single probe is sufficient.

`gics_industry_sector` is therefore **category B: duplicate, delete from CLAUDE.md.**

---

## 3. The third outcome the two-way sort misses — "the spec has it, weaker"

Design named two fold candidates. **Both already resolve** — but not identically, and the difference
matters:

**(a) The mandate-prior invariant** — Design suggested folding it "into §8a." It is already in the spec,
verbatim and three times, at **§9c** (`spec.md:51`, `:233`, named at `:350`):

> *"the mandate sensor's 'prior' is the **last prospectus it has frozen**, not the registry's
> `prospectus_accession` field…"*

→ **Category B: duplicate, delete.** (The §8a attribution is also off — it is §9c/§4d. Noted not as a
gotcha but as the cleanest evidence for Design's own point that section attribution needs the diff.)

**(b) The NPORT-P stub rule** — Design suggested folding it "into §3b." The spec **has §3b and has the
rule**, at `spec.md:67`:

> *"**NPORT-P (deferred §3b):** … Stub stays deliberately thin."*

But CLAUDE.md says something the spec does **not**:

> *"NPORT-P stays the labeled §3b stub — **do not fill it with survivor-biased data**."*

The spec states the *rule*; CLAUDE.md states the *hazard*. `survivor-biased` appears once in the spec
(`:46`) and in an unrelated context. So:

- Treating it as **duplicate → delete** silently drops the reason the stub is thin, which is the whole
  scar. A future reader sees "deliberately thin," judges it over-cautious, and fills it — with exactly
  the survivor-biased data the clause exists to forbid.
- Treating it as **orphan → fold whole** duplicates a rule the spec already carries.

**Correct handling: fold the *delta*.** Amend `spec.md:67` to carry the hazard clause, then delete from
CLAUDE.md. That's a one-sentence surgical amendment, fully traced.

**Generalized — the sort has four outcomes, not two:**

| | clause in spec? | action |
|---|---|---|
| **A · orphan** | no | fold into its section, then delete from CLAUDE.md |
| **B · duplicate** | yes, equivalent | delete from CLAUDE.md, keep the pointer |
| **C · constitutional** | n/a — not a build contract | **stays** in CLAUDE.md |
| **D · partial** | yes, but **weaker** | fold the **delta** (amend the spec clause), then delete |

**D is the dangerous one**, because a two-way sort classifies it as B and the deletion looks clean. It is
the doc-level form of the same class as the mandate false-corroboration: *the difference between "this
resolves" and "this resolves completely" is invisible unless you compare the wording, not the topic.*

---

## 4. The sorted list

**Category C — constitutional / cross-cutting. STAYS in CLAUDE.md.** (Verified absent from the spec, and
absent *correctly* — these bind every seat regardless of what it is building.)

- The **doc-process rules**: amend-never-regenerate, doc naming / provenance-in-the-filename
  (`amended, never regenerated`, `leading ISO date` → 0 hits, and rightly so).
- The **development rules**: branch off fresh `origin/main`, Code opens the PR and stops, verify git/PR
  state before acting (`pull request`, `origin/main`, `code owner` → 0 hits).
- **Offline tests / the network guard** — a testing discipline, not a build contract. (Candidate for
  `METHOD.md` instead; flagged, not ruled.)
- The **Firewall** — all three clauses, whole and untouched, per Design's protected list. Note the
  firewall *is* substantially in the spec too (`detector` 13, `portfolio.yaml` 3), but this is the one
  place duplication is **correct**: it is the constitution's reason for existing.

**Category D — fold the delta, then delete.** (1)

- **NPORT-P stub hazard** → amend `spec.md:67` (§3b) with "never filled with survivor-biased data."

**Category B — duplicate, delete from CLAUDE.md, keep a pointer.** (32, incl. every one Design or I had
flagged as at-risk.) A representative sample with its spec anchor:

| CLAUDE.md clause | resolves at |
|---|---|
| GICS rollup table frozen, never a knob | `:37` **(my corrected finding)** |
| mandate prior = frozen blob, not the registry field | `:51`, `:233`, `:350` |
| anti-fitting: `sector_min_weight` never moves to rescue a snapshot | `:37`, `:45` |
| fixtures never refreshed by fetch; drop-and-freeze | `:39`, `:45` |
| vendored provenance · no `models/` import · no wide typed-metric columns | `:435` (near-verbatim), `:130`, `:144` |
| append-only; backtests write only under `backtest/` | `:321` (CONTRACT), `:327` |
| stress gate absolute; **never** a rolling percentile; standing review | `:200`, `:441` |
| verdict vocabulary (4 values) · proto-cluster wall · no-run-now · forward-hash · bs4 boundary | 3–15 hits each |

---

## 5. The orphan list as a drift audit of the spec — the result is a clean bill

Design asked for this framing: *"every clause that lives only in the constitution is a clause the spec
was supposed to carry and didn't."*

**Run, and the spec passes.** Zero build contracts live only in CLAUDE.md; one (§3b) is carried in
weaker form. For a document at rev 16 with a decision trail this long, that is a genuinely good result
and worth recording as such — the folds have been happening.

The audit's finding is therefore about **CLAUDE.md, not the spec**: the constitution accreted
*restatements* of contracts that were folded correctly all along. That reframes the consolidation
one more time — it is not repairing a gap, it is removing an echo.

---

## 6. What this does not establish

- **Completeness.** 36 probes, chosen by reading CLAUDE.md for contract-bearing language. A clause I
  didn't recognize as contract-bearing is not in this list. The count "32 of 36" is a property of my
  probe set, not of the document.
- **Probe validity.** §2 is a worked example of a probe that returned a true null and a false finding.
  Every category-B row above rests on a phrase match I read in context — but I read the spec's wording,
  not the whole section, for most of them. **Before any deletion, each row wants a second read against
  the spec section, not the grep hit.** That is the clause-by-clause check the consolidation owes anyway.
- **Category D's true size.** I found one by noticing a missing qualifier. There is no probe for "the
  spec's version is subtly weaker" — it requires reading both. **If D has siblings, this method will not
  have found them**, and that is the residual I'd most want QA's read to attack.

## 7. Recommended next step

The fold/delete itself is a **surgical amendment to two canonical documents** (`spec.md` → rev 17 for
the one §3b delta; `CLAUDE.md` → the consolidation rev). Per amend-never-regenerate that wants the list
above **ratified first**, then executed as a traced diff where every changed clause points at a decision
record. Ready to execute on approval; deliberately not done here, because a self-approved list driving a
canonical-doc rewrite is the exact loop the rule exists to break.
