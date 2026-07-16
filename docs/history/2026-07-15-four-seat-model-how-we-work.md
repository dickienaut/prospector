# Four seats and a record

*How a one-person project builds with AI agents without drowning in their mistakes.*

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
  Claude Chat
- **Build** — an agent with full access to the repository. It implements, runs the tests, opens a pull
  request, and **stops**. It never merges.
  Claude VSCode
- **QA** — a *separate* agent, in a different environment, that reviews cold. It pulls the branch **from the
  repository of record** (not from the local working folder), mounts it, runs the suite against real data,
  and delivers findings as their own pull request: a failing test that reproduces the bug, plus a proposed
  patch. It does not apply the fix. The implementer does — so every fix gets a second, independent read.
  Claude Science
- **The human** — the only seat that decides. Reads the findings, makes the judgment calls, clicks merge.
  The architect of the project.

And a fifth thing that isn't a seat: **git is the only coordination layer.** The agents never talk to each
other. Everything one seat needs from another arrives as a committed artifact.

## The rules that make it work

Very few, and each is enforced by a mechanism rather than by remembering:

1. **Nothing merges unless the full test suite passes** — branch protection, no bypass for anyone, including
   the owner. A gate the owner can skip is theater.
2. **Agents propose; the human disposes.** No agent has merge rights. This is policy where it could be
   capability — the restraint *is* the product.
3. **Go to the primary source.** Never reason from a summary of the code, a doc that describes the code, or
   another agent's account of the code. Open the artifact.
4. **Write down what you decided and why, when you decide it.** The *why* decays fastest and is worth the
   most later.
5. **A stated invariant that isn't enforced by a mechanism is just a comment.** If it matters, make the
   violation fail a test.

## Why it works

**Generate-and-check.** The seats are stochastic; the gates are deterministic. That asymmetry — finding is
hard and can be random, verifying is cheap and exact — is what lets you use an unreliable generator to
produce a reliable artifact. The non-determinism isn't eliminated, it's *located*: on one side of a membrane
nothing crosses unchecked. Evolution runs this algorithm. So do human engineering orgs, which produce bridges
out of people who are wrong all the time.

**Author ≠ reviewer, structurally.** Two instances of the same model in the same setup fail *together*. The
defense isn't a better prompt, it's a differently-positioned eye: a different environment, a different entry
path to the code, a different procedure. Independence has to be architectural or it isn't real.

**Stateless seats, durable record.** Because nobody remembers anything, everything must be re-derivable from
the artifact — which turns out to be the source of every nice property. Kill a thread mid-task and the next
one reconstructs from disk. No shared live state means no desync, which means the whole thing runs
asynchronously, from a phone, over a flaky connection. Failure is cheap and local: things break constantly
and nothing important goes with them.

**Culture that survives total turnover.** In a human org, culture lives in people and walks out the door with
them. Here nobody stays — every seat is new every session — so the culture had to be externalized: a written
constitution, a searchable bug register (what has bitten us, what rule was born from it), dated decision
records, published procedures the agents load like training. A fresh agent reads them and behaves like a
veteran. The turnover that should kill the culture instead proves it: every cold start is a test of whether
it really lives in the record. This is a functioning Ship of Theseus.

## What it costs

Real things, worth knowing before you copy it:

- **Constant writing.** An artifact-based culture *starves* if you stop feeding it. Undocumented decisions
  are the failure mode, not disagreement.
- **Overhead per change.** A QA finding is two pull requests, not one. A risky slice gets a written plan
  first. That friction is the price of the independent read, and it's worth it — but it is a price.
- **It needs checkable work.** The whole model rests on having a cheap deterministic checker. Where output
  can't be verified — taste, prose, strategy — the membrane doesn't exist and the seats are just assistants.
- **The human is the bottleneck, on purpose.** Judgment doesn't scale, and that's the point: it's the one
  plank never replaced.

---

*The short version: don't try to make the agents reliable. Assume they aren't, and build the thing that
catches them — then you can let them reach further than you'd otherwise dare. Bold generation, ruthless
checking. The boldness is safe **because** the checking is not optional.*
