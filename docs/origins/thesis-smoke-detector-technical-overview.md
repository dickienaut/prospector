# The Thesis Smoke Detector — Technical Overview
### Theory and architecture, for someone who likes systems but doesn't need the code

**In one line:** A monitoring system that watches your investment theses for early signs of breaking — built on the principle that you can't *predict* a failure, but you can *instrument* the conditions that precede it, and built deliberately to make its owner act *less*, not more.

---

## The problem, stated precisely

Two opposite failures sink long-term investors. *Inattention*: you hold a position for a reason, the reason quietly stops being true, and you find out from the price. *Over-attention*: you watch everything, react to noise, and trade yourself to death. The first is a monitoring failure; the second is a discipline failure. Most market tools are built for the over-attentive and make it worse. This system targets the narrow path between the two: surface the few signals that genuinely matter, on a slow schedule, and stay silent otherwise.

The governing constraint is epistemic. In complex systems — markets, grids, supply chains — failure is *not forecastable in principle*: the trigger of a cascade is generic and interchangeable, while the real cause is an accumulated fragile state that builds invisibly during the calm. So the design goal is never prediction. It's **regime-reading**: watching how loaded the system is, and being told when a specific, pre-defined break-condition trips — so a decision gets made deliberately, in calm, rather than reactively or not at all.

## Design philosophy: an aircraft sensor suite

The mental model is a cockpit stall-warning system — not one instrument but several (angle-of-attack probe, airspeed, the stick shaker) watching different things, fused, and **escalating in intensity**: a quiet dial, a louder "look now," and finally a physical shaker you can't ignore. The aviation world paid in blood for four lessons this system borrows directly:

1. **Layered escalation.** Not every signal should be equally loud — constant loudness *is* noise, and noise is what retrains an investor into over-trading. Most sensors are quiet dials; very few ever escalate.
2. **Sensor disagreement is itself the signal.** The deadliest crashes came from trusting a *single* probe. The high-value information isn't any one gauge tripping — it's gauges that should move together *diverging*.
3. **Always keep the raw cross-check.** When an instrument shows the impossible, pilots fall back to raw attitude. Every sensor here has a primary source-of-record it can be checked against; a reading you can't verify is one you don't act on.
4. **The false-positive rate is a tuned parameter, not an afterthought.** An alarm that cries wolf gets ignored — which is worse than no alarm, because it still shows a green light. Sensors are tuned to trip *rarely and meaningfully*; a noisy sensor is treated as a bug to fix.

And the fifth, which aviation confirms rather than solves: **a sensor suite only covers the failure modes someone thought to instrument.** It cannot catch the unknown-unknown — so the airframe still has to survive what the sensors miss.

## The architecture

Data flows in one direction — **sensors → fusion → escalation → push notification** — and there is a hard rule at the end: the system has **no execution surface**. It writes to a review queue; it never places a trade. (A navigator advises the heading; it can never touch the controls, and the pilot can always override.) That single boundary collapses two risks at once — a confident AI hallucination *and* the owner's own over-trading impulse both die on the execution axis, because there's no wire for either to travel.

The sensors are organized into banks of increasing sophistication:

**Bank A — deterministic gauges.** Clean numbers, hard thresholds, no AI: credit spreads, market volatility, how far a holding has drifted from its intended weight, the correlation *between* holdings. Dumb, reliable, incapable of making things up. These are the airspeed indicator — the ground truth the cleverer layers get checked against.

**Bank B — agentic scouts.** For signals that can't be reduced to a number — "is the regulatory or funding environment for this industry turning?" — an AI agent goes and researches the question. The governing rule is that it is a **research assistant, not a judge**: it gathers and *cites*, it never decides. Each scout is held to a strict discipline:
- **Cite-or-fault.** Every claim must terminate in a primary-source citation. No source → the finding is rendered as a *sensor fault*, visually distinct, never as data.
- **Coverage reporting.** The scout reports what it checked *and what it couldn't verify* — a self-test, not a bare "all clear." Critically, finding nothing logs as "checked these sources, found nothing," never as "thesis healthy" (absence of evidence is not evidence of absence — the lesson of the Thanksgiving turkey, who had 1,000 days of reassuring data).
- **Source tiering.** Sources are ranked (primary / reputable / unranked / low-trust) so the scout's confidence is *weighted by source quality*, not merely by whether a link exists.
- **Sourcing-asymmetry detection.** This is the subtle one: the scout automatically checks whether the evidence *for* its conclusion is better-sourced than the evidence *against* it — and flags when "the signal that would move the thesis is the least-verified." That is **confirmation bias rendered as a structural output**: the system polices its own tendency to believe the comfortable answer.

**Bank C — multi-agent reconciliation.** This is the heart of the design, and it deserves the detail.

A single AI agent is a *confident but fallible narrator* — it can fabricate a fact and attach a plausible-looking citation to it. You cannot make one agent reliable. So instead of trusting one, the same question is sent to **several agents working independently**, and their reports are reconciled. The logic:

- **Agreement is the confidence signal.** Independent agents rarely invent the *same* falsehood. So a claim that several differently-built scouts surface independently is high-confidence — consensus acts as a **fabrication filter**.
- **Disagreement is the triage signal.** A claim only one agent surfaces is *either* a unique catch *or* a hallucination — and that ambiguity is exactly what gets escalated for human review. Divergence doesn't get discarded as noise; it's the pointer to where judgment is actually needed.
- **Independence is the entire game.** The agents must genuinely differ — different framings of the question, different research entry points. If you give them identical instructions, you get *correlated* errors: three agents making the same mistake and agreeing with each other, which produces **false consensus** — the worst possible outcome, because it wears the costume of corroboration. (Three pitot tubes in the same patch of iced-over air all read wrong together.)
- **The fusion is skeptical, not averaging.** A conventional ensemble would *blend* the agents' outputs into one confident answer. This one does the opposite. Blending "the thesis is softening" and "the underlying data is firm" into "medium confidence" *destroys* the signal; flagging the **contradiction** preserves it. The fusion layer's job is to surface disagreement, never to smooth it away.

**Bank D — the novelty layer (instrumented humility).** Every sensor above is *in-distribution*: it watches a known variable for a known threshold. This layer asks a different question — "is the world starting to behave in a way none of these sensors were built for?" It watches the *shape* of the data (variables that normally move independently suddenly moving together) and the *character* of the agent reports over time (new actors, new mechanisms, vocabulary that wasn't in prior runs), looking for **drift** rather than any specific breach. It's the closest you can mechanically get to a tripwire for the risk you didn't think to watch — and it's the one sensor explicitly *allowed to be vague*, because its job is to point at novelty, not to make a sourced claim.

## Escalation, and two kinds of alert

The fusion layer applies a gradient: a quiet context dial that never alerts → a quiet log → a "go look" that opens a review → a forced review. And it keeps two categories of alert strictly separate: **GO-LOOK** ("come exercise judgment on this") versus **DO-THIS** ("execute a rule you already committed to in calm — no discretion"). Confusing the two — forming a fresh opinion under stress where a pre-made rule already exists — is precisely the failure the gradient prevents.

## The recursion (the part systems people enjoy)

The system's whole purpose is to watch for *cascading failure* in a complex system. So it would be self-defeating for the system itself to be cascade-prone. It's therefore built with the same resilience principles it monitors for: **loose coupling** (the banks fail independently — if the AI scouts break, the deterministic gauges still fire), **modularity** (one bad sensor doesn't sink the panel), **graceful degradation** (capability falls gradually as pieces fail, not all at once), and **fail-loud defaults** (a broken sensor reports "FAULT — could not read," *never* a silent green light — the iced-over airspeed indicator, encoded). The thing whose job is to be trustworthy about failure cannot itself be allowed to fail silently.

## The honest limit

No sensor suite catches the risk nobody instrumented. So this is explicitly *not* the safety net — it's instrumentation bolted onto one. The real protection is structural: position sizing, cash buffers, never being a forced seller — the things that let you survive a shock you never saw. The detector makes the *known* risks cheaper to watch; the *structure* survives the unknown ones. Letting a panel full of green talk you out of those buffers is the single trap it exists to prevent.

## Why it's different

It's genuinely sophisticated research infrastructure with the usual incentives inverted. A quant's tooling exists to find signals and trade fast. This exists to surface *fewer*, better-verified, bias-checked signals on a deliberately slow cadence — for the express purpose of keeping its owner disciplined. Its highest function is to let you stop watching.

---

*A personal discipline tool for reasoning clearly about one's own holdings — not investment advice, and not a system that makes any trading decisions.*
