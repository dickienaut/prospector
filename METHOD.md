# How we work — four seats and a record

*How a one-person project builds with AI agents without drowning in their mistakes. Written to be read by a cold seat that wants to know **why** the rules in `CLAUDE.md` exist.*

*Precedence, so this doc can't become a second home for one rule: **`CLAUDE.md` is operative, this is
explanatory.** If they ever disagree about what a seat must do, `CLAUDE.md` wins and this doc is the bug.*

*Ratified 2026-07-16 by all four seats. Its enforced-tier mechanism claims (rules 1, 2, 6) — and the
enforced QA sub-clause of rule 3 — are anchored to a dated verification record —
`docs/notes/2026-07-16-method-mechanisms-qa-verification.md` — checked against the live ruleset,
`CODEOWNERS`, the shipped skill, and watched write-probes, not against memory. Prior drafts: `docs/history/`.*

---

## The problem

An LLM is a fast, capable, occasionally-confidently-wrong collaborator. The obvious way to use one — one
chat, one agent, do everything — fails in a specific way: **the thing that wrote the code also wrote the
tests, and it believed the same wrong thing twice.** No amount of "please review your work" fixes that,
because the reviewer shares the author's priors. Ask it to check itself and it will cheerfully confirm its
own error.

So the design question isn't "how do I get better output." It's **where do I put the check, and how do I make
it un-skippable.**

## The seats

Four roles, deliberately separated. None of them remembers anything between sessions; every one of them
starts cold.

- **Design** — a plain chat thread. Architecture, tradeoffs, rulings. It has, at most, a **stale read-only
  snapshot** of the code: enough to check its own factual claims before making them, never enough to verify —
  it cannot run anything, cannot enumerate, and its snapshot ages from the moment it's taken. So every claim
  it makes from that snapshot carries an as-of, and a search hit is a lead, not a verdict. Its job is judgment
  and argument; verification is not its seat.
- **Build** — an agent with full access to the repository. It implements, runs the tests, opens a pull
  request, and **stops**. It never merges.
- **QA** — a *separate* agent, in a different environment, that reviews cold. It pulls the branch **from the
  repository of record** (not from the local working folder), mounts it, runs the suite against real data,
  and delivers findings as their own pull request: a failing test that reproduces the bug, plus a proposed
  patch. It does not apply the fix. The implementer does — so every fix gets a second, independent read.
- **The Human** — the architect, and the only seat that decides. Reads the findings, makes the judgment calls, clicks merge.

And a fifth thing that isn't a seat: **git is the only coordination layer.** The agents never talk to each
other. Everything one seat needs from another arrives as a committed artifact.

### The identity boundary

New as of 2026-07-16, and it is what turned rule #2 from a posture into a wall.

**The agents do not run as you.** They act under a machine account with push access to exactly one
repository and no administrative rights — so the account, not the token, is the outer bound on what any seat
can reach. Each seat's credential then carries only its own role's scope: **Build can modify CI config; QA
cannot** — because a seat that can edit the gate binding it is not bound by it.

**Be exact about that last wall's kind.** Build and QA are the *same* bot account, differing only in **token
scope** (Build's carries `workflow`, QA's does not — a QA push to `.github/workflows/` is refused). So "Build
can / QA cannot" is a **scope** wall on one identity, not an identity wall between two — calibrated for the
threat rule #6 is for (a seat exceeding its role, proven both ways: QA's workflow write is refused, Build's
succeeds) and no more. The only *identity* wall here is between the agents and **you** (rule #2); between the
agent seats it is scope. A `workflow` token leaking into the QA seat would cross it — which is why per-seat
accounts, or a GitHub App, are the named upgrade — but for a one-person setup that is a low-priority threat,
not a present hole.

**And your identity exists only on a device the agents don't run on.** Not "the agent must never approve as
me" — that is a note-to-self, and notes-to-self are the tier below. The credential simply isn't on that
machine. **You cannot misuse a credential that isn't there.** Absence is the mechanism.

This is also the piece without which the rest is impossible: a platform cannot require review *from a
different identity* when there is only one identity. Every restraint stays instructed until the split exists.

## The rules that make it work

**A rule is either enforced by a mechanism, or it lives in an agent's head.** The first kind survives a total
staff turnover every session. The second is only as durable as the last agent's memory — which is to say,
gone at the next cold start unless the record re-teaches it. By our own rule #5, a rule with no mechanism
behind it is just a comment. So here is the honest accounting of which is which.

**Rule numbers are stable IDs; the tiers are groupings.** Rules keep their number and **migrate between
tiers** as they earn mechanisms — which is why the enforced list below reads 1, 2, 6 and the aspired list
reads 3, 4, 5: rule #2 *migrated up* when it earned its mechanism, and rule #6 was *born* enforced. Non-
contiguous, and correct. That migration *is* rule #5's engine, made visible.

**Enforced — the membrane. A gate a stochastic seat physically cannot cross.**

1. **Nothing merges unless the full test suite passes** — branch protection, no bypass for anyone, including
   the owner. A gate the owner can skip is theater.

2. **Agents propose; the human disposes.** — *Graduated from aspired on 2026-07-16.* Agents run under a separate, non-admin machine identity that owns no path and cannot approve its own PR; CODEOWNERS makes the human the sole owner, and main requires one code-owner approval covering the most recent push. No sequence of agent actions lands code on the default branch.

6. **Each seat holds only the capability its role requires.** — Least privilege, enforced at the account and
   credential layer (see *The identity boundary*). It protects the two rules above rather than standing
   alone: it is why QA cannot rewrite the CI gate that binds it (#1), and why the human's approval cannot be
   borrowed by an agent (#2). Its discipline is maintenance, not configuration — the boundary is defined by
   what you *don't* add to the machine account later.

**Aspired — the discipline. True only while a seat chooses it; each is hope until it earns a mechanism.**

3. **Go to the primary source.** — Never reason from a summary of the code, a doc that describes the code, or
   another agent's account of the code. Open the artifact. — A mechanism binds a seat, not a rule, so this
   one's ledger is per-seat; it stays aspired because only one seat is bound:
   - **QA — enforced (2026-07-16).** Pulls the repo of record by script, never the local copy; a findings PR
     cannot be delivered unless its provenance stamp equals the exact commit QA fetched and tested — a
     mismatch fails the call before any push. A finding cannot name a commit QA never read. *(This is the
     single home for the mechanism. Anchored: `docs/notes/2026-07-16-method-mechanisms-qa-verification.md`,
     §"Rule 3 (QA sub-clause)" — CONFIRMED against the shipped `deliver_qa_findings_pr` gate, RED/GREEN with
     meta-controls.)*
   - **Code — discipline.** The strict-status ruleset pins the merge base to current `origin/main`, but that's
     branch freshness, not reading. Three scars, one miss — reasoning from an *account* of the artifact instead
     of the artifact itself: **fixture-provenance** (a labeled-synthetic SPDR holdings fixture carried a green the
     real filing had not earned); **M6-CAPTURE-DRIFT** (reasoned from a stale `README.md` line's account of
     `capture.py` rather than opening it — filed M6 "front-loaded to v2" while it was built at `4739b52`); and
     **#88 stale-status** (reported `main`'s state from a stale local checkout, never fetched — QA caught it
     against git). The recurrence is why the rule stays *aspired* for Code: nothing yet forces the read.
   - **Design — discipline, thinner than it looks.** It can check a claim against a stale snapshot, but nothing
     forces it. Its code-claims are caught downstream; its document-claims are not — an external briefing once
     asserted two capabilities as built that were only planned, and no seat was bound to catch it.
   - **The Human — judgment.**

4. **Write down what you decided and why, when you decide it.** The *why* decays fastest and is worth the
   most later. — *Mechanism (partial):* dated decision records and a bug register are required artifacts in
   the review flow, but nothing yet *fails* when a decision lands undocumented. This one is still mostly
   discipline — name it as such rather than pretend otherwise.

5. **A stated invariant that isn't enforced by a mechanism is just a comment.** If it matters, make the
   violation fail a test. — This is not a step beside the others; it is the **engine that moves rules up a
   tier.** Every time an aspired rule earns a mechanism, it graduates to enforced and the model gets more
   robust against turnover. The list of rules still living in the aspired tier is the roadmap. *(Rule #2's
   graduation on 2026-07-16 is this engine's first recorded run: an outside reader caught the mis-tiering, the
   implementer independently flagged it and declined to force it, the mechanism was built, three probes proved
   it bites, and the rule moved.)*

## Why it works

**Generate-and-check.** The seats are stochastic; the gates are deterministic. That asymmetry — finding is
hard and can be random, verifying is cheap and exact — is what lets you use an unreliable generator to
produce a reliable artifact. The non-determinism isn't eliminated, it's *located*: on one side of a membrane
nothing crosses unchecked. Evolution runs this algorithm. So do human engineering orgs, which produce bridges
out of people who are wrong all the time.

**Author ≠ reviewer, structurally.** Two instances of the same model in the same setup fail *together*. The
defense isn't a better prompt, it's a differently-positioned eye: a different environment, a different entry
path to the code, a different procedure. Independence has to be architectural or it isn't real.

**The reviewer is a generator too — so check it the same way.** The trap the whole model exists to beat — an
author trusting its own output — reappears one level up, in QA. A *finding* is QA's output, and a finding
whose reproducing test passes for the wrong reason (green because an import broke, not because the bug is
caught) is the founding failure wearing a lab coat: a test that passes for the wrong reason. So the finding
is put through the same asymmetry before it reaches the human: the reproducing test is run **RED against the
untouched code** (it must fail — the bug is real) and **GREEN against the proposed patch** (it must pass — the
fix resolves it), as a re-runnable script. And because a checker that always says "pass" is worthless, the
checker itself is tested against a fix that doesn't fix and a test that was never red — it has to be able to
say *no*. Right now that check is a pre-flight the QA seat runs; the graduation (aspired → enforced) is to
make it a CI gate on findings PRs. The membrane only counts once it can reject.

**Prove the gate bites.** That last line is the rule *every* gate here has to pass, not only the
finding-checker. A mechanism you have never watched *reject* something is — until you test it —
indistinguishable from one wired to always say yes; relying on it is faith, not engineering. So each gate is
made to reject on purpose before it's trusted: a test is run **red** against the unfixed code before it's
believed green, the CI gate is proven by a PR built to fail it, and rule #2's wall was put through three
probes — bot opens a green PR → blocked; human approves → mergeable; bot pushes one more commit → blocked
again. The third probe is the one that mattered: it is the only one that watched the wall reject the
*approve-then-swap* move — bless a benign diff, push different code behind it — the exact failure a wall you'd
only ever seen say "yes" would hide.

**Stateless seats, durable record.** Because nobody remembers anything, everything must be re-derivable from
the artifact — which turns out to be the source of every nice property. Kill a thread mid-task and the next
one reconstructs from disk. No shared live state means no desync, which means the whole thing runs
asynchronously, from a phone, over a flaky connection. Failure is cheap and local: things break constantly
and nothing important goes with them.

**...but the record only saves you if it's anchored outside itself.** A doc that *describes* the code drifts
from the code — and then rule #3 tells the next cold agent to distrust that doc and open the source, which
means an un-anchored record starts decaying the moment it's written. So the record obeys a discipline of its
own: **every durable claim is tied to something outside the narrative — a commit SHA, a failing test, a real
breakage — never to another summary.** An anchored record is the asset the whole model rests on; an
un-anchored one is a confident story that ages into a lie. (We have already been bitten once: a
state-of-project doc that lagged the code and would have misled anyone who trusted it over the source.)

**The reviewer's own record is anchored the same way.** That discipline has a mechanized instance in QA's own
delivery: a findings PR is the doc-drift class wearing a QA badge — a confident record naming a commit QA never
actually read, because the branch moved between review and delivery. Rule #3's QA sub-clause closes it by
*binding* the provenance stamp to the fetched commit and refusing to ship on a mismatch — the mechanism is
defined once, there. It covers QA's fetch-and-deliver path only; Build and Design reading source over a summary
stays discipline, since no mechanism forces comprehension.

**Culture that survives total turnover.** In a human org, culture lives in people and walks out the door with
them. Here nobody stays — every seat is new every session — so the culture had to be externalized: a written
constitution, a searchable bug register (what has bitten us, what rule was born from it), dated decision
records, published procedures the agents load like training. A fresh agent reads them and behaves like a
veteran. The turnover that should kill the culture instead proves it: every cold start is a test of whether
it really lives in the record. We have built a functional Ship of Theseus.

## What it costs

Real things, worth knowing before you copy it:

- **Constant writing.** An artifact-based culture *starves* if you stop feeding it. Undocumented decisions
  are the failure mode, not disagreement.

- **Overhead per change.** A QA finding is two pull requests, not one. A risky slice gets a written plan
  first. That friction is the price of the independent read, and it's worth it — but it is a price.

- **The human can no longer author.** Rule #2's mechanism binds its author too: you cannot approve your own
  pull request, and you are the only code owner, so any PR *you* open is unmergeable. In practice the agents
  become the only authors and you the only approver. That is the model stated as a wall rather than a
  preference — and it is a real constraint, not a footnote. Accept it knowingly, or don't build the wall.

- **It needs checkable work.** The whole model rests on having a cheap deterministic checker. Where output
  can't be verified — taste, prose, strategy — the membrane doesn't exist and the seats are just assistants.

- **The checker covers the artifact, not the belief the artifact encodes.** The gates ruthlessly verify that
  the code does what it is meant to. They say nothing about whether what it is meant to do is *right*. For
  most software that gap is fine — the artifact is the product. For work whose product is a *judgment* (does
  this strategy have an edge? is this the right model of the world?), correct code is necessary and nowhere
  near sufficient, and the only real check is slow, statistical, and lives outside the repo: out-of-sample
  time. "Green in backtest, wrong out of sample" is the same shape as "green on synthetic data, broken on
  real" — one level up, and this model gives it no coverage. Know where the membrane ends, so you don't
  mistake a passing suite for a validated belief.

- **The human is the bottleneck, on purpose.** Judgment doesn't scale, and that's the point: it's the one
  plank never replaced.

---

*The short version: don't try to make the agents reliable. Assume they aren't, and build the thing that
catches them — then you can let them reach further than you'd otherwise dare. Bold generation, ruthless
checking. The boldness is safe **because** the checking is not optional. And the checker is not exempt: check
it the same way, and know what it cannot check at all.*
