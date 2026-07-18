# Handoff to the v2 Design thread — from the v1 Design seat

*Written 2026-07-17, the day v1 went live and self-running. **Its purpose is not to summarize the record** —
the record is in the repo and you must read it there (rule #3; and a summary of the artifact is the thing this
project spent a month learning not to trust). **Its purpose is to tell you what the record won't**: which
claims are load-bearing, what was tried and rejected, where the honest gaps are, and what your own seat's
failure mode is.*

***Read this once, then don't cite it.*** *It is a lead, not a verdict. Every factual claim below is from a
frozen project-knowledge snapshot (2026-07-17) plus what was pasted into a chat window. Ground anything
load-bearing against live `main` before you build on it.*

---

## 1. The one thing to hold before anything else

**v1 is build-complete, deployed, and self-running as of 2026-07-17 — and it has proven nothing.**

What finished is the **instrument**. The false-discovery rate — the number the entire project exists to
produce — is **unmeasured**. The measurement started with the first unattended tick on 2026-07-17 and is
measured in **years**, not slices. Everything before that date was construction.

So the first sentence of your seat's job: **the temptation to build more instrument is the project's named
risk, and v2 is its largest vector.** The burn-in is calendar-bound and cannot be accelerated, so *using* that
wait to design v2 is legitimate. The failure mode is subtler: **v2 becomes interesting enough that v1's answer
quietly stops mattering.** If you find yourself designing something that would make the FDR question moot
rather than answerable, stop.

## 2. Opening this thread crosses a wall — do it deliberately

The state doc files proto-clusters and discourse-interpretation as **ASPIRATIONAL — "v2, walled off —
captured, not queued."** That wall is deliberate, and rev8 carries an explicit guard at exactly the point of
temptation: *"a re-synthesis is exactly when an item like this drifts into a plan, and it must not."*

**Designing v2 moves it from aspirational to queued.** That is a real register transition and it must be a
**recorded decision**, not something that happens because someone opened a thread. Write the record. If the
answer to *"what does this enable"* is "a cleaner version of itself," you have your answer.

## 3. Reading order (do this before you have opinions)

1. **`METHOD.md`** — how the four seats work and *why*. Read the **rule-3 per-seat ledger** twice; §7 below is
   about your entry in it.
2. **`CLAUDE.md`** — the operative constitution. Its weirdest clauses are its most valuable: each is a scar
   whose reason is invisible in its text.
3. **`docs/spec.md`** (rev15+) — the CONTRACT. Not a description of the code; the thing that constrains it.
4. **`docs/state.md`** (rev8+) — orientation/status. §5.2 is the status register.
5. **`deferred/2026-07-11-v2-research-grounding-flow-vs-structure.md`** — **the single most important document
   for your thread.** Everything in §5 below is compressed from it; read the original.
6. **`docs/bugs/README.md`** (doctrine, classes 1–9) then **`INDEX.md`** (the register). The nine classes are
   *generic* failure patterns of AI-built software — none of them is about ETFs. Read them as your own
   pre-mortem.
7. **`docs/decisions/`** — the case law. Enumerate it; don't sample it.

## 4. Where v1 honestly stands (verify, don't trust this)

- **Both spawners live.** Excess-correlation (§4a) pages — 7 live leads as of 2026-07-17. Dispersion (§4b/§9e)
  runs in **shadow burn-in** — XLF split z=2.523 at 3/90, XLI split z=4.667 at 7/90. Fractures turn over; each
  spawn carries its own clock. Promotion from shadow to paging is a **human act** (`config.changed`), gated on
  90 days.
- **§10 sender honest from both directions** — a persistent fault pages once then rides the heartbeat (stable
  suppression key); low-value advisories are counted-and-surfaced, not paged.
- **M7 autonomy core live** — launchd, prod on a worktree pinned at a release tag, single-writer lock, weak
  dead-man (heartbeat + a self-owned calendar backstop; no external dependency, by a 20-year-durability call).
- **M6 capture: BUILT, ships disabled, ZERO captures.** See §6 — this is your biggest design constraint.
- **~634 tests.** Docs ≈ code by line count, which is correct: the seats are stateless, so **the record is the
  runtime**.

**The M3 result, stated the way it must be stated:** XLK×XLU fired at z=2.52 roughly **407 trading days**
before the TEKX launch consensus. That is **one instance** — an existence proof of the mechanism, **not a
rate**, and **in-sample by construction** on the headline. The March-2020 falsifier came back as a *routed
classification* (2/3 held, 7/10 persisted → a pre-committed diagnostic said "real but off-thesis"), which reads
**stronger** than a clean pass, not weaker. The corroboration base rate is a **2/98 floor**.

## 5. What's banked for v2 (compressed — read the original)

- **The enemy is REFLEXIVE FLOW mimicking structure, not noise.** Flow can produce a correlation break that
  looks exactly like a structural one. Distinguishing them is v2's core research problem.
- **The project is well-aimed against it:** liquid large-caps (hard to move with flow) + the lead fires
  **before a vehicle exists** (so there is no flow yet to mimic anything).
- **The distinctive angle: launch-as-consensus-clock.** An ETF launch is a dated, public marker of when
  consensus arrived. That gives you a *labelled* event to measure lead time against — the thing most novelty
  research lacks.
- **The testable thing: a historical-launch backtest.** PIT throughout; survivorship including **delisted**
  funds; the discriminator is **structure-persists vs flow-reverts**; measured as excess-vs-benchmark.
  Publishable either way — a null result on a pre-registered design is a result.
- **Prior art the design rests on:** Ben-David / Franzoni / Kim / Moussawi, *"Competition for Attention in the
  ETF Space."* Also: *Ponzi Funds* (arXiv:2405.12768), and the Dumb-Money literature.

## 6. v2's two halves have OPPOSITE data situations — this is the design constraint

| half | substrate | status |
|---|---|---|
| **Proto-clusters / pseudo-ETFs (§1.9)** | **Real and accruing** — the generous dispersion payload has been banking it since July; XLI/XLF/XLB/XLP fractures are live data | Something to design **against** |
| **Discourse interpretation** | **ZERO captures.** Capture is built and disabled; the armed byte-compare hasn't run | Nothing to design against |

**So the honest first question for your thread is not "what is v2" — it is "which half has anything to design
against."** One does. The other is waiting on a gate that hasn't opened.

**And designing an interpretation layer against zero captures is designing against imagination — which is
precisely this seat's named failure mode (§7), and the one thing no downstream seat is bound to catch.**

**The cheap fix, if it hasn't happened: arm capture.** Two config lines (`ANTHROPIC_API_KEY`,
`capture.monthly_budget_usd`) plus **one supervised manual run** to watch whether `query_drift` fires (see
`2026-07-14-query-drift-byte-exact.md` — the ruling is an **ordered gate**, not a menu). Blast radius is
bounded three ways: the stable suppression key means a cry-wolf pages once then rides the heartbeat; the budget
is a hard cap with a loud fault; and **capture is write-only — nothing in v1 reads it.** Arm early and the
substrate accrues *while* you design.

## 7. Your seat's failure mode — the most important section here

`METHOD.md`'s rule-3 ledger, verbatim in spirit: ***Design — discipline, thinner than it looks. It can check a
claim against a stale snapshot, but nothing forces it. Its code-claims are caught downstream; its
document-claims are not.***

That entry is not modesty. It is a finding, and it has fired repeatedly:

- **A technical briefing described Marchenko-Pastur cleaning and null-model validation as BUILT.** Both are
  **PLANNED AND NOT BUILT.** The actual dispersion method is **eigendecomposition + second-eigenvector sign
  split + Q-score baseline tracking**. The error was caught by a fact-check, not by a gate. **If you write that
  MP/RMT is built, you have repeated it.**
- **Two dangling citations in one week** — a decision record cited before it existed; a findings doc cited in a
  handoff while it sat outside the repo. Both this seat's.
- **A build note's own two sections contradicted each other** on a fold's don't-fold list, in the note
  commissioning a drift audit.

**Your countermeasures, in order:**
1. **Search the code and the record before asserting.** You have `project_knowledge_search` over a repo
   snapshot — code *and* `docs/`. Use it. **A search hit is a lead, not a verdict**; confirm before ruling.
2. **The snapshot freezes at sync time and goes stale.** Every claim carries an **as-of**. **Ask the owner to
   re-sync** — it takes him ~30 seconds and he will forget; a memory note exists for this.
3. **You cannot enumerate, diff, or see commits/branches/PRs.** So: never claim completeness. The fold's
   worklist, the register's completeness, any "everything traces" claim — those belong to the build seat by
   rule, because they require diffing.
4. **Flag what you structurally can't check, then let Code ground it.** That composition produced this seat's
   one genuinely useful code finding (PAGE-WORTHY-MIRROR): found it, flagged the one thing it couldn't verify
   (is there an agreement test?), Code resolved it against a SHA newer than the snapshot.

## 8. The walls that bind v2 (non-negotiable; each is a scar)

- **The never-execute firewall.** Note the honest tiering — *reads the detector's bucket / `portfolio.yaml`* is
  **IAM-enforced**; *places or sizes a trade* is **capability-absence** (no broker credentials, no reachable
  portfolio); ***recommends* a trade is PROSE — nothing stops it.** That third clause is the one closest to the
  real risk: the system was never going to place a trade, it was going to **talk the operator into one**. v2's
  interpretation layer is exactly where that pressure will appear.
- **No LLM text as data.** Capture freezes **raw `web_search_tool_result` blocks** and our deterministically
  templated query. No model prose enters the record. v2's interpretation layer is where this wall gets tested
  hardest — the moment model output becomes *data*, the non-determinism crosses the membrane and there is no
  fixed thing left to check against.
- **Proto-clusters are PRICE-ONLY.** Never keyword/NLP mining. **The canary is a cluster, never a single
  name. The canary is never the trade.**
- **The macro catalog is NEVER a trade/tilt trigger** — and the sensor **never strips the macro regime out**
  (no multi-factor β; it's entangled with real tech theses, and stripping it would delete real signal). Both
  directions. It reads like hedging; it is two scars.
- **Append-only fossil store. No run-now surfaces. CONTRACT vs DEFAULT.**

## 9. What I'd actually do first

1. **Don't design yet.** Read §3's list. Cold.
2. **Write the wall-crossing record** (§2) — it makes the transition a decision.
3. **Arm capture** (§6) if it isn't armed — the substrate accrues while you think, and it dissolves the
   interpretation half's blocker for free.
4. **Then answer one question**: which half has data. Design that one. Let the other wait until it has
   something real to be designed against.

**The line to carry, unchanged from v1:** this thing is *engineered, in writing, before building, to be able to
**lose*** — falsifiable at every layer, an immutable record that grades its own calls, metrics that refuse to
flatter themselves. Whatever v2 becomes, it has to be able to lose too. If a design can't be wrong, it isn't
finished.
