# The Recursive Spine — one axiom, every layer

*Origins note, 2026-07-11. A retrospective — written looking **back** at the built system with fresh eyes,
not forward from a plan. It names a property that was always there but never stated: the project is
**self-similar**. One small discipline, applied at every scale, makes the whole thing fractal — and that is
not decoration. It is why it holds.*

---

## The axiom

Strip the project to one sentence and it is this: **preserve the primary record; never let an interpretation
overwrite it.** Everything else is that rule, wearing a different coat at a different altitude:

- the **event store** is append-only — a correction is a new event, a changed mind a new `verdict` that
  *supersedes*, never an edit;
- **decision records** are dated fossils, never rewritten — the newest is not "the truth," the whole sequence is;
- **canonical docs are amended, never regenerated** — "the doc-process form of Append-only";
- **filenames are forward-only** — new files born dated, existing names never changed ("never change the past");
- **primary-source verification** — the *filed* artifact outranks the inferred one; read the real filing, not
  your prior about it;
- **capture, don't interpret** — v1 stores the substrate richly and defers the meaning (the dispersion payload,
  the reading list, the proto-cluster wall);
- **observe, don't act** — a lead is *read*, never traded; the only path to the portfolio is human and one-way.

Append-only, primary-source, capture-not-interpret, observe-not-act — they look like separate rules. They are
one rule: **the record is sacred; the interpretation is deferred, reversible, and never allowed to silently
rewrite the record.** Apply a recursive principle consistently and self-similarity is what you get for free.

## Where it recurses

**Outward, across scales.** The same "never overwrite the past" governs a byte in the events table, a clause in
the constitution, and a character in a filename. The discipline does not change with altitude — only its coat.

**Inward, into itself — the rules contain themselves.** The amend-never-regenerate rule *was added by surgical
amendment*. The naming rule arrived *born dated*, obeying itself. The bug archive that tracks how rules are born
from bugs is *itself built on rules born from bugs*. Each rule is an instance of the thing it describes — the
cleanest sign that the axiom is real and not imposed.

**Downward, through the bugs — the same lesson, one grain finer each time.** "Never anchor on a ticker" (the
identity lesson) reappeared at the constituent grain (the ENR / Siemens-Energy collision). "Green on synthetic,
broken on real" surfaced a *third* time, each occurrence a layer deeper — holdings, then prices, then the alarm
layer itself. The defects are self-similar too; that is exactly why a **meta-bug register** (the pattern) beats
a flat log (the instances).

**Sideways, as mirror images.** Prospector *is* "the offensive twin of the thesis smoke detector" — the yin/yang
pair, each the inverse of the other: one hunts *emerging* structure, one watches *existing* theses for breakage.
And the v2 proto-cluster idea looks *one level below* the ETF corpus — for the correlation structure that will
*become* the structure v1 watches. The tool recurses into its own substrate.

**Forward, in time.** "You cannot backfill a payload you did not capture." The rich dispersion payload is
captured *now* so a future layer can "thaw backward over it." The present builds for a future self that will
re-read the fossil — the append-only record pointed the other way down the timeline.

## Why bounded recursion, not infinite regress

A system this self-referential could spiral — meta-work about meta-work, organizing the organization, naming the
naming. It doesn't, because the recursion is **governed** by hard stops that live outside the loop:

- the **active-lead ceiling** is a *tripwire for human recalibration*, not a self-tuning dial — "no auto-tune of
  thresholds, ever";
- **no run-now surfaces** — record on cadence, push on state-change; nothing recomputes on demand;
- the **firewall / observation-only walls** — the loop can watch forever but can never close into an action
  without a human hand.

So the spine is recursive but **terminating**: self-reference with a base case, a fractal with an outer
boundary. The discipline recurses all the way down; the *authority to act* never does — it stops at a person.

## Why it matters

Name it and two things follow. First, it is a **design test**: a new layer that would require overwriting the
record, acting on a reading, or trusting a prior over the source is not just wrong — it is *off-spine*, and the
smell is detectable before the code is. Second, it is **why the thing coheres** under a build cadence this fast:
you are not maintaining many rules, you are maintaining *one*, and checking that each layer is still an honest
instance of it. The recursion is the project's compression — and its conscience.
