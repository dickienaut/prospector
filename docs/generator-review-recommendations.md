# Thesis Generator — External Read & Recommendations

*A summary of the assessment from the review-thread read of the generator decisions doc (dated 2026-06-29). Written to drop into the build thread. These are recommendations to evaluate, not decisions taken.*

---

## The one thing that governs everything

The generator is the detector's primitive pointed **outward** — same freezer, same drift measure, same fleet-reconciliation enum (CORROBORATED / CONTESTED / THIN) — but with one asymmetry that sets the whole risk profile: the detector is *structurally* safe (no verb for "acquire," closed-form rules written in calm), while the generator's job is to **produce new things to want** — exactly what the over-trading defense exists to contain. The doc names this correctly: its safety "cannot be inherited; it must be a held habit." Everything below is about (a) protecting the parts already sound and (b) converting as much of that *habit* back into *structure* as possible.

---

## What's strongest — protect it

- **ETF-as-ontology (the keystone).** Turning "scan discourse" into "watch a maintained universe of baskets" is a genuine architectural insight, not a convenience: it hands you nodes / mandate / curator / boundary for free, and it *dissolves* the new-node-floods-every-edge problem by separating new-**edge** detection (inside tracked baskets, home turf for a co-occurrence graph) from new-**node** detection (rare, curated launches).
- **Three streams, and the lag between them (the real core).** Discourse → rebalancing (N-PORT) → launch sit at different points on the consensus curve, and **the payload is the lag between them** — velocity *toward consensus*, early by construction. Strip everything else away and "measure how fast a linkage travels from discourse to package" is the defensible heart.

---

## The main fork (§14A): deterministic-only v1 — recommended

The §15 analysis is right that the tempting middle — build the expensive discourse stream, then run it *reactively* — is incoherent: you pay for the hard part and throw away its only advantage (being earliest). But the recommendation goes further than "deterministic-only is a respectable v1":

**Deterministic-only is the _disciplined_ v1, and the reason is the detector's own build order.**

The detector was built deterministic-first: Banks A / A′ (regime gauges, look-through — no LLM) **before** the agentic scouts (B), **before** reconciliation (C), **before** OOD (D). The generator has the identical layering:

- Rebalancing (N-PORT) + launch streams = the **A/A′ equivalent** — curated, high-precision, deterministic, low-fabrication.
- Discourse scouts = the **Bank-B equivalent** — agentic, LLM, high-fabrication.

The discourse stream is simultaneously the **noisiest** ("noisy, high-recall, speculative"), the **most expensive** (the only stream needing multi-agent LLM scouts), and the **most fabrication-prone** — which makes it the stream that most floods the one resource the design correctly names as the true bottleneck: the **slow human oracle**. For a v1 whose primary failure mode is overwhelming that oracle, starting with the two deterministic streams is not a compromise — it's the move that respects the throughput constraint the design *itself* identifies as the core risk (§4).

**Recommended sequencing:**

1. **v1 — deterministic-only.** Rebalancing + launch streams. Sit at the rebalancing/launch clock (late, but "consensus-but-true is fine for a 17-year owner"). Build the adjudication muscle on manageable volume. Prove the oracle can keep up.
2. **v2 — add discourse via cadence-capture** (the §15 insight: freeze raw discourse cheaply on cadence, defer the expensive multi-agent interpretation to triggered / thaw-backward moments) — *once the adjudication throughput is proven.*

The fork isn't cost-vs-interpretability; it's **build order** — and build order says deterministic core first, same as the detector.

*Natural fit with where the build already is: the SPDR family (TEKX, HECO, and the rest) gives a known, frozen-prospectus, series-ID-anchored, N-PORT-filing v1 substrate. The deterministic streams start there.*

---

## The structural safety-add: make the pipeline the wall

The detector earned its safety through *structure*; the generator asks you to hold a *habit* where the detector held a *wall*. A compelling generated lead is exactly the kind of thing that manufactures a want and then leans on the disciplined portfolio process. §12 gestures at the fix (the **detector's break-trigger**, not price, governs what you do with a surfaced thesis) but doesn't state the structural version:

**A generated lead must enter the _same_ pipeline as any other candidate — no shortcut.**

It can't become a position by being *interesting*. It has to earn a written thesis, defined break-triggers, and survive-a-50%-drawdown sizing — exactly like every existing holding (GRID, XBI, …). Make **the pipeline itself the wall.** That converts a chunk of the generator's safety from habitual back to structural: "the generator surfaced something exciting" and "I hold it" are separated by the identical discipline that governs everything else in the book.

→ Recommend writing this into **§1** (as the structural complement to the held habit) and the **decisions ledger**.

---

## The permanent limit — keep it named

§5's **"reconstructed path, never demonstrated cause"** is the crucial humility, correctly stated: the fossil record is read-only, so you can thaw backward and *observe* precursors but never *prove* a linkage was inevitable — unlike Lenski, who regrows a frozen ancestor and re-runs evolution forward. The append-only schema makes this a *property* rather than a disclaimer (you can't edit old verdicts → you're honestly scoreable), which is the right defense.

But it's a limit to **live with**, not solve. The interpretation layer (the fold) is where confirmation bias keeps trying to sneak in, and the only thing that holds it is *actually running* the scoring discipline — grading the `no`s that later sprouted `launch`es.

---

## Bottom line

Coherent design, single organizing principle — *split cheap-always-on from expensive-triggered, freeze the substrate, defer the interpretation, let the human ratify* — which is the same principle as the detector. One primitive, two faces.

- **The decision worth making now is Fork A → deterministic-only v1** (cadence-capture discourse as v2), for the same reason the detector was built in layers.
- **Add "same-pipeline-is-the-wall"** structural safety to §1 + the ledger.
- **Keep "reconstructed-path-not-demonstrated-cause" named** — and actually run the scoring.
- The rest of §14 is **parameters, not architecture** — set them as you build.
