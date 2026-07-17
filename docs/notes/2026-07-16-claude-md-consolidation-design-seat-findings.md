# CLAUDE.md consolidation — Design-seat findings (2026-07-16)

*One of three independent reads (Design / Build / QA), to be reconciled into a consolidation rev. Read against
the 277-line `CLAUDE.md` as uploaded 2026-07-16. **Findings, not taste** — each entry names an observable
defect and its class, so the consolidation's clause-by-clause diff can be checked against the list rather than
against a better idea. Where I could not verify a claim from this seat, it says so.*

*The rule this operates under: a cleanup rewrite is permitted **only** as an explicit consolidation rev, with a
clause-by-clause diff proving no contract changed except the ones intended. **The forbidden thing was never
rewrite; it is rewrite unchecked.** This document is the thing that makes the check possible.*

---

## 0. The reframe, before the list

**Length is the wrong target.** 277 lines of constitution for a 45k-line repo with a nine-class bug taxonomy
and a 17-year horizon is not long. The feeling that it needs a rewrite is real, but it is diagnosing
**navigability and second homes**, not excess. Cutting for length would delete scar tissue (§4) and leave the
actual defects (§1) in place.

**The lens is the one already ratified for the bug archive: distilled-vs-raw, one home per thing.** CLAUDE.md
currently carries three different kinds of content — *what a seat must obey* (operative), *why it exists*
(explanatory), and *what the contract says* (the spec's history). That is the whole diagnosis. The split:

| kind | home |
|---|---|
| what a seat must obey | **`CLAUDE.md`** |
| why the rules exist / how the model works | **`METHOD.md`**, `docs/decisions/` |
| what the contract says | the spec |
| what has bitten us | `docs/bugs/` |

**Sequence:** mint `METHOD.md` first (its precedence line — operative vs explanatory — *is* the boundary that
makes this consolidation obvious, and it converts half the work from "delete this" to "move this"), and do the
consolidation **after** the rev15/rev8 fold, not during. Two canonical docs in motion at once means the fold's
drift audit is checking against rules that are themselves moving — and the fold may surface unrecorded
decisions that want to become CLAUDE.md rules anyway. **Fold → then consolidate, with the fold's findings in
hand.**

---

## 1. Observable defects (drifted / duplicated) — the real worklist

**C-1 · The opening spec-rev narrative is a second home for the spec's changelog, and it has already drifted.**
*Class: duplicated + drifted.* The opener names the canonical spec as **rev14**, then narrates rev12 → rev5 in
~20 lines. **Revs 13 and 14 are never narrated** — the summary stops two revs short of the pointer it opens
with. This is the same defect class closed twice this week (M7-DASH-01, PAGE-WORTHY-MIRROR): one rule, two
homes, prose asking them to stay in sync. It is also self-inflicting: every spec rev obligates a parallel edit
here, forever.
**Proposed:** CLAUDE.md keeps the **pointer only** — *"The canonical spec is `docs/…rev15….md`; earlier revs in
`docs/history/`. Read it before changing anything load-bearing."* The rev narrative belongs to the spec's own
changelog.
**Caution — this is where the check earns itself:** some of that narrative carries **CONTRACT text that may
not exist in the spec** (e.g. *"the mandate sensor's 'prior' is its last frozen prospectus blob, never the
registry `prospectus_accession`"*). Before a single line is deleted, each claim must be shown to resolve in
rev15. Anything that doesn't resolve is a **finding**, not a deletion. I cannot check this from the design
seat — it needs the spec diffed. Hand it to Build.

**C-2 · `## CONTRACT vs DEFAULT` is doing two jobs, and the second one is ~80 of the 277 lines.**
*Class: duplicated + mixed-register.* The rule itself is ~4 lines. The rest is decision-record summaries —
which **mix operative constraints with war stories**. Compare, from the same section:
- *Operative:* "a dormant real outcome NEVER motivates lowering `corroboration.sector_min_weight`."
- *Explanatory:* "the reconcile-to-`COMMON STOCKS`-total check caught a mixed-case `SPECIALIZED REITs` the
  first regex dropped."
The first is an instruction to a seat. The second is a war story that already lives, in full, in the record.
**Proposed:** each entry compresses to **the operative constraint (imperative, one or two lines) + the record
path**. The reasoning stays in the record. This is the INDEX/doctrine split applied to the constitution.
**Caution:** this section is where most of the scar tissue lives (§4). Compress by dropping the *narrative
around* the imperatives — **never** by dropping the imperatives. If a "never X" loses its "never," the
consolidation has failed regardless of how much cleaner it reads.

**C-3 · Three sections, one topic.** *Class: scattered.* `## Canonical documents — amended, never regenerated`
· `## Doc naming — provenance in the filename` · `## Documentation (standing practice)`. Not duplicated —
they're different rules — but a seat looking for "how do I handle a doc" reads three places.
**Proposed:** one `## The record` heading, three sub-rules. Structural only; no text changes. Diff shows moves,
not edits.

**C-4 · The Development merge clause is FALSE.** *Class: stale.* Already ruled; amendment + decision record in
flight. Noted here only so the consolidation doesn't collide with it. **It lands first, separately** — it is
blocking `METHOD.md` and has no dependency on any of this.

**C-5 · `## Identity` is about *fund* identity, and a second identity concept is arriving.**
*Class: naming collision.* The Development amendment will name the machine account. Two "identity" concepts,
one heading.
**Proposed:** rename the heading to `## Fund identity`. One word, costs nothing, and a heading rename inside a
doc is not a filename rename — the forward-only rule doesn't bind it.

**C-6 · No map.** *Class: structural — and this is what makes it "feel" like it needs a rewrite.* 277 lines, 16
sections, no orientation, no statement of what kind of rule lives where. A cold seat reads top-to-bottom and
cannot find "what applies to me."
**Proposed:** a five-line header. *What this is (rules a seat must obey) · why they exist → `METHOD.md` · what
the contract says → the spec · what has bitten us → `docs/bugs/` · CLAUDE.md is operative; where it and
METHOD.md disagree, this file wins.* Highest value per line in the whole exercise.

---

## 2. The bigger half — what's MISSING

*Deletion is the visible half of a consolidation and the less valuable one. CLAUDE.md is a **Prospector**
constitution that grew a **process** section; the process has since become a four-seat model with real
mechanisms, and the constitution never caught up. A cold Code seat reading CLAUDE.md today would not know:*

| **M-1** | **The QA seat exists.** Nothing in CLAUDE.md mentions QA, the `qa/*` findings-PR path, or **Option-2 composition** (QA proposes a RED test + reference patch; Code applies with an independent read; `xfail(strict)` handoff so the gate never goes red). A fresh Code seat receiving a findings PR would have to infer the protocol. |
| **M-2** | **The bug register and its maintenance gate.** *"A fix isn't done until its row is current."* That is a live, ratified, load-bearing rule — the thing that stops the register going false-open (which it did: the Tier-4 sweep found six rows stale). It lives in `docs/bugs/README.md`. It belongs in the constitution. |
| **M-3** | **"Every fix ships with the violation test that would have caught it."** Universal in practice, absent from the doc. The nearest thing present is "code carries spec-citing docstrings," which is a different rule. |
| **M-4** | **Prove the gate bites.** Newly named, operating unnamed for weeks (RED-first · the negative controls · the deliberately-red PR #39 · probe 3 · H3's mandatory negative test · `verify-restore` · the dead-man loop test · *"proven RED by disabling the refusal"* in the lock record). Operative form: **a gate that has never rejected is observationally identical to no gate.** |
| **M-5** | **Merge commits, not squash.** Ratified (squash rewrites the record; append-only). Not in the constitution. Now partly mechanism (`allowed_merge_methods`), which makes stating it cheap and checkable. |
| **M-6** | **The seat model itself.** CLAUDE.md mentions "the design thread (chat with the owner)" once, in passing, inside CONTRACT-vs-DEFAULT. `METHOD.md` explains the model; CLAUDE.md should carry the **operative subset** — who does what, and what each seat must not do. |

**The boundary to hold while adding these:** METHOD.md explains *why the model works*; CLAUDE.md says *what
this seat must do*. If CLAUDE.md restates METHOD.md's reasoning, the consolidation has re-created the exact
defect it's fixing.

---

## 3. The firewall — a per-clause enforcement ledger

**I suspected the firewall was prose-only and checked. I was wrong, and the residual is sharper than the
suspicion.** The three clauses have **three different enforcement levels**, and the doc states them as one:

| clause | enforcement | tier |
|---|---|---|
| "Never add code that reads the detector's bucket or `portfolio.yaml`" | separate S3 bucket + **IAM credentials that cannot read them** (per the state doc: *"enforced at IAM"*); separate repo = no import path exists at all | **mechanism** |
| "Never add a code path that places or sizes a trade" | capability absence — no broker credentials, no portfolio data reachable. A trade path would have nothing to act on | **mechanism-adjacent** (absence, same shape as removing the owner's gh credential) |
| "Never add a code path that **recommends** a trade" | **nothing.** The sender could render *"BUY XLK"* tomorrow and no gate would stop it | **prose** |

The third is the clause **closest to the actual risk** — the system is not going to place a trade; it is going
to talk the operator into one. It is also the hardest to mechanize (how do you test the absence of a
recommendation?), which is exactly why it has stayed prose.
**Proposed:** state the three clauses with their tiers, the way `METHOD.md` rule #3 carries a per-seat ledger.
Not to weaken the firewall — to stop it *claiming* uniform enforcement it doesn't have. An overclaimed wall is
the defect being fixed elsewhere in this same doc.
**This is the finding I'd most want Code and QA to check independently** — I'm reading the state doc's IAM
claim from a stale snapshot and have not seen the IAM policy.

---

## 4. Scar tissue — the protected list (do not touch without a named record)

*These are the doc's actual value. Each is a decision that cost something to learn, and **most read as clutter
to a confident eye** because the reason isn't visible in the text. The risk in a rewrite is never that you'd
change a rule on purpose — it's that you'd smooth away a clause whose scar you can't see, and you are the
person best positioned to be sure it's unnecessary. **The consolidation's diff must show each of these
surviving byte-identical, or with a named decision record.***

- The **Firewall** — all three bullets, whole.
- **No LLM text as data.** · **No run-now surfaces.**
- "Never a rolling percentile / self-updating window — that reintroduces the baseline-relative failure the
  recalibration diagnosed."
- "NPORT-P stays the labeled §3b stub — **do not fill it with survivor-biased data**."
- "Do not import anything from the sibling repo's `models/` (capacity and opacity — forbidden)."
- "Do not re-introduce wide typed-metric columns to the events table."
- "A dormant real outcome **NEVER** motivates lowering `corroboration.sector_min_weight`." *(anti-fitting)*
- "**Never** add series_ids to a lead payload — the lead-id already encodes them; duplication invites drift."
- "Diff **only** the principal-investment-strategy section — never the whole filing; a full-text diff is a
  false-positive machine."
- "bs4 owns HTML **structure**, our code owns **meaning**, the **human** owns **significance** — the
  extraction/diff must never grow a 'this change is meaningful' opinion."
- The proto-cluster wall: **price-only, never keyword/NLP mining · the canary is a cluster, never a single
  name · the canary is never the trade.**
- The macro catalog: "**NEVER** a trade/tilt trigger… never a macro-regime alert stream" — *and* "the sensor
  never strips the macro regime out (no multi-factor β — it is entangled with real tech theses; stripping it
  would delete real signal)." **Both directions.** This one is two scars in one clause and reads like
  hedging; it isn't.
- "**Fixtures are never refreshed by fetch code.**" · "No fixture silently stands in for a real filing."
- **Identity:** "a bare ticker is rejected at the write path… tickers are display-only attributes."

---

## 5. What I could not check from this seat

Named, per the rule-3 ledger — Design's document-claims are the ones no seat is bound to catch:

- **C-1's deletion safety** — whether every CONTRACT claim in the opening narrative resolves in rev15. Needs a
  diff. **Build.**
- **§3's IAM claim** — read from the state doc, not the policy. **Build or the owner.**
- **Whether the spec-rev narrative's attributions are factually right** ("rev12 folds §4c to built") — needs
  the spec's own changelog.
- **Completeness.** I searched; I cannot enumerate. If a rule exists that I didn't think to look for, this list
  doesn't have it. That's what Code's and QA's reads are for.

---

## 6. Predicted division of the three reads

*Stated up front so the reconciliation can notice if it doesn't happen — a convergence that was predicted is
weaker evidence than one that wasn't, and a **divergence** is the interesting signal.*

- **Design (this):** second homes, missing rules, register mixing, the protected list.
- **Build:** stale facts, broken references, rules that don't match the code, unrecorded behavior.
- **QA:** claims that can't be checked, rules with no mechanism, overclaims.

**If all three lists agree on everything, be suspicious** — three same-model seats agreeing is the
convergent-prior signature, not confirmation. The entries where one seat sees a defect and the others don't
are the ones worth the most reading.
