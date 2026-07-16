# Four seats and a record

*How a one-person project builds with AI agents without drowning in their mistakes. Written to be handed to
someone who might want to steal the pattern. It's a working model from one project, not a validated
methodology — but the ideas underneath it are older than the tools.*

*Rev. 2026-07-15 — proposed by the QA seat, not yet ratified by Design or Code. Changes from the first draft:
splits the rules into an enforced tier and an aspired tier, names the mechanism behind each aspired rule,
adds "check the reviewer too" to why it works, and marks two limits the model had been running on faith.*

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

- **Design** — a plain chat thread. Architecture, tradeoffs, rulings. It is *structurally blind to the code*:
  it sees only what gets pasted in. That's a feature — its job is judgment and argument, not verification.
- **Build** — an agent with full access to the repository. It implements, runs the tests, opens a pull
  request, and **stops**. It never merges.
- **QA** — a *separate* agent, in a different environment, that reviews cold. It pulls the branch **from the
  repository of record** (not from the local working folder), mounts it, runs the suite against real data,
  and delivers findings as their own pull request: a failing test that reproduces the bug, plus a proposed
  patch. It does not apply the fix. The implementer does — so every fix gets a second, independent read.
- **The human** — the only seat that decides. Reads the findings, makes the judgment calls, clicks merge.

And a fifth thing that isn't a seat: **git is the only coordination layer.** The agents never talk to each
other. Everything one seat needs from another arrives as a committed artifact.

## The rules that make it work

Here is the one real change from the first draft. It listed five rules as equals. They are not equal, and the
inequality *is* the model: **a rule is either enforced by a mechanism, or it lives in an agent's head.** The
first kind survives a total staff turnover every session. The second is only as durable as the last agent's
memory — which is to say, gone at the next cold start unless the record re-teaches it. By our own last rule,
a rule with no mechanism behind it is just a comment. So here is the honest accounting of which is which.

**Enforced — the membrane. A gate a stochastic seat physically cannot cross.**

1. **Nothing merges unless the full test suite passes** — branch protection, no bypass for anyone, including
   the owner. A gate the owner can skip is theater.
2. **Agents propose; the human disposes.** No agent has merge rights. This is policy where it could be
   capability — the restraint *is* the product.

**Aspired — the discipline. True only while a seat chooses it; each is hope until it earns a mechanism.**

3. **Go to the primary source.** Never reason from a summary of the code, a doc that describes the code, or
   another agent's account of the code. Open the artifact. — *Mechanism (partial, and weaker than it looks):*
   QA fetches the repo of record by script, and the delivery tool **always stamps a commit SHA onto the
   findings PR** — you cannot ship a PR with no provenance block. But that enforces the *presence* of a stamp,
   not its *truth*: the stamped SHA is the branch head resolved at delivery time, and nothing binds it to the
   commit QA actually fetched, read, and tested against. If the branch moves between review and delivery, the
   stamp will confidently name a commit QA never saw — the doc-drift failure class, wearing a QA badge. So the
   load-bearing half — *the stamp equals the reviewed commit* — is still discipline. The graduation is to
   thread the fetched `commit_sha` through delivery and **fail the call when it doesn't match** the stamped
   SHA; until then, treat rule #3 as aspired with a good tool, not enforced. (Choosing the code of record over
   the convenient local copy was always discipline; this note is about what the stamp does and does not prove.)
4. **Write down what you decided and why, when you decide it.** The *why* decays fastest and is worth the
   most later. — *Mechanism (partial):* dated decision records and a bug register are required artifacts in
   the review flow, but nothing yet *fails* when a decision lands undocumented. This one is still mostly
   discipline — name it as such rather than pretend otherwise.
5. **A stated invariant that isn't enforced by a mechanism is just a comment.** If it matters, make the
   violation fail a test. — This is not a step beside the others; it is the **engine that moves rules up a
   tier.** Every time an aspired rule earns a mechanism, it graduates to enforced and the model gets more
   robust against turnover. The list of rules still living in the aspired tier is the roadmap.

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

**Culture that survives total turnover.** In a human org, culture lives in people and walks out the door with
them. Here nobody stays — every seat is new every session — so the culture had to be externalized: a written
constitution, a searchable bug register (what has bitten us, what rule was born from it), dated decision
records, published procedures the agents load like training. A fresh agent reads them and behaves like a
veteran. The turnover that should kill the culture instead proves it: every cold start is a test of whether
it really lives in the record.

## What it costs

Real things, worth knowing before you copy it:

- **Constant writing.** An artifact-based culture *starves* if you stop feeding it. Undocumented decisions
  are the failure mode, not disagreement.
- **Overhead per change.** A QA finding is two pull requests, not one. A risky slice gets a written plan
  first. That friction is the price of the independent read, and it's worth it — but it is a price.
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
