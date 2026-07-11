# Thesis Smoke Detector â Design Brief

*Spec to seed the build thread. Companion to the investment thesis master (rev. 4) and the Systems Failure & Portfolio Resilience synthesis â read those for the "why"; this is the "what to build." Principles and architecture, not code.*

---

## 0. What this is, in one paragraph

A **monitoring system** that watches my portfolio's break-it triggers and the market's fragility gauges, and **pings me on a schedule when the holes in the cheese line up** â so the tracking lives in a system instead of my head. The governing analogy is an aircraft **sensor suite**: many instruments, each watching something different, fused into computed warnings that escalate in intensity (quiet dial â go-look â forced review). It is **avionics bolted onto an airframe** â it assists a pilot, it does not fly the plane. The structural resilience (no leverage, sizing for a 50% drawdown, the orthogonal reserve) is the airframe and remains the backstop; this is instrumentation that makes the *known* risks cheaper to watch. It cannot catch the unknown-unknown, and nothing in the design should ever let a wall of green lights say otherwise.

**The behavioral purpose is explicit:** I have ADHD; over-trading/tinkering is my single largest risk (thesis Â§1). This tool is built to be a *constructive outlet for the watching urge that displaces trading* â which only works if it stays disciplined (scheduled, push-not-pull, informs-review-not-trade). The day building or checking it migrates from "displaces trading" to "new high-frequency channel for the same impulse," the tool has become the thing it was built to prevent.

---

## 1. Core principles (non-negotiable)

1. **The agent is a research assistant / navigator â never a judge or pilot.** It surfaces sourced evidence it *believes* bears on a thesis; I adjudicate. It can be overridden by the pilot and **has no execution surface whatsoever** â it writes to a review queue, full stop. There is no wire from agent output to a trade. (This collapses both the hallucination risk and the catnip risk to zero on the execution axis: if the wire doesn't exist, neither risk can travel it.)
2. **Trust but verify â operationalized, not delegated.** This automates the *search* half of rule 14 and keeps the *verify* half exactly where it is (with me, at the primary source). Every agentic finding terminates in a primary-source citation. **No citation, no signal** â an unsourced finding renders as a *sensor fault*, visually distinct, never as authoritative data.
3. **Deterministic where the data is clean; agentic only where the signal is irreducibly qualitative.** Don't LLM-ify anything with a clean number â it adds a hallucination failure mode to a solved problem.
4. **Complements, never replaces, the structure.** The sensor suite covers anticipated failure modes only. The airframe (sizing, no leverage, the reserve) survives the un-instrumented ones. Greens never override structural margins.
5. **Push, not pull.** Silence is the default. The system pings me when a threshold trips; I do not go hunting for it. (A panel you *pull* becomes catnip â every open is a discretionary decision, the thing my wiring over-supplies.)
6. **Loosely coupled and gracefully degrading** â because the tool that watches for cascading failure must not itself be a normal-accident waiting to happen (see Â§5). Build it the way the systems doc says to build any resilient system.

---

## 2. The four aviation lessons as design requirements

The airframe world paid for these in blood; each maps to a build requirement.

1. **Layered escalation (the stall-warning gradient).** Indicators are passive (read on the checkpoint), warnings are active (interrupt me), the shaker is physical (grabs the controls). Three intensities for three levels of certainty-and-urgency. **Don't make every sensor equally loud** â constant loudness *is* noise. â The three-tier escalation (Â§4).
2. **Sensor disagreement is itself a signal.** The deadliest crashes (AF447, both MAX) came from trusting a *single* probe. â Redundancy/voting where it matters (Â§5 multi-agent), and a **fusion layer that surfaces disagreement rather than smoothing it into a confident blend** (Â§3). When gauges that should move together diverge, *that divergence is the alert.*
3. **The instrument can be wrong â always keep the raw cross-check.** Pilots fall back to pitch-and-power when the glass shows the impossible. â Every sensor has a **source-of-record** behind it to drop to when the reading looks wrong (rule 14 as architecture). A sensor you can't cross-check is one you shouldn't act on.
4. **Nuisance alarms get the whole system disabled.** Early GPWS cried wolf so often crews ignored it â the alarm that fires on noise trains you to disable the alarm. â **False-positive rate is a tuned design parameter, not an afterthought.** A sensor that trips on routine volatility is mis-calibrated and must be re-thresholded or removed. Tune for *few, meaningful* trips. (Corollary: false-positive *budget* scales with alert cost â the OOD layer can be twitchy because its alarms are cheap to dismiss; a DO-THIS must be conservative.)

A fifth, which aviation *confirms* rather than solves: **sensors only cover anticipated failure modes.** The stall suite said nothing about MCAS-driven-by-a-single-AoA-vane until two airframes went down. â The OOD layer (Â§6) is the partial, instrumented answer; the structure is the real backstop.

---

## 3. Architecture â the layers

A **mixture-of-experts topology with a *skeptical* fusion layer.** Standard MoE blends experts into a confident answer; this one must do the opposite â surface contradiction, refuse to average it away.

- **Bank A â Deterministic regime/fragility gauges.** Clean feeds, hard thresholds, no LLM. The dumb reliable instruments (airspeed indicator).
- **Bank Aâ² â Deterministic from the look-through.** Portfolio-structure sensors computed from `portfolio.yaml` + holdings files + prices. (The surprise: a big chunk of what felt "agentic" is actually deterministic because the look-through already ingests the holdings.)
- **Bank B â Agentic scouts (cite-or-fault).** Per-trigger qualitative search â structured evidence dossier with primary-source citations. Flags for review; never flips a state.
- **Bank C â Multi-agent reconciled.** For the highest-stakes / hardest-to-source signals: N *independent* scouts (varied framings and entry points), then reconcile â consensus = high confidence, **divergence = the triage signal** for deep human review.
- **Bank D â OOD / novelty meta-layer.** Watches the *other sensors' collective behavior and the agent reports themselves* for distributional drift. The instrumented humility layer (Â§6).

**Fusion / escalation layer (the stall-warning computer):** combines all banks, applies the three-tier escalation, and â its highest-value job â **surfaces disagreement** (e.g., a scout says "uranium softening" while a deterministic feed reads firm â the divergence is the alert, not something one channel silently wins). It is a disagreement-*detector*, not a confidence-*blender*. Pushes via Discord webhook (same pattern as the existing trading bot).

---

## 4. Escalation tiers and the two alert types

| Tier | Meaning | Behavior |
|---|---|---|
| **T0** | Context dial | Read on the checkpoint; never alerts |
| **T1** | Quiet log | Appears in the scheduled digest |
| **T2** | Go-look | Pings â opens a **thesis-gate review** (read the dossier, exercise judgment) |
| **T3** | Forced review / pre-committed action | The shaker |

**Two categorically different alerts â keep them visually and structurally distinct:**
- **GO-LOOK** (almost all sensors): "come reason about this," dossier attached. Judgment required.
- **DO-THIS** (the drawdown-band sensor only): execute the pre-committed Â§7 reserve-deployment tranche, **no discretion**. The rule I wrote in calm, fired by the machine.

The day "execute the rule I wrote in calm" gets confused with "go form a fresh opinion in a drawdown" is the day the panel reintroduces the discretion it was built to remove. Never merge these.

---

## 5. Building it *as* a loosely-coupled system (the recursion)

This tool is itself a complex system that must not cascade. Apply the week's resilience principles to its own construction:

- **Loose coupling:** the layers fail independently. If the agent scouts break, the deterministic gauges still fire, and vice versa.
- **Modularity (bulkheads):** each sensor is isolated. One bad scout doesn't sink the panel.
- **Fail-safe defaults:** a sensor that errors reports **"FAULT â could not read,"** never a silent green. (The airspeed-indicator-that-ices-over lesson, as code. A silently-failing indicator is worse than an absent one because it still draws a green light.)
- **Graceful degradation:** value falls *gradually* as components fail, not all at once. Lose the one scout, lose one sensor â not the panel.
- **No single point of failure**, because a monitor with an SPOF will fail exactly when the regime it watches for arrives.

**Multi-agent reconciliation (the redundant-probe architecture), design notes:**
- **Independence is the whole game.** Vary prompt framing *and* search entry points â identical prompts give *correlated* confabulations agreeing with each other (false consensus, the worst outcome, same as three pitot tubes in one iced-over airflow).
- **Surface disagreement; do not auto-resolve it.** No meta-agent votes and collapses the variance â the collapse is where the signal dies. Reconciliation *reports the agreement structure*; I adjudicate the variances.
- **Why it filters false-greens:** a single agent's confident fabrication sails through; a fabrication is unlikely to be *independently reproduced* by three differently-framed scouts. Consensus becomes a fabrication filter; divergence becomes the deep-dive queue.

---

## 6. Bank D â the OOD / novelty layer (the instrumented humility)

Every other sensor is **in-distribution**: it watches a *known* variable for a *known* breach ("did this anticipated thing happen"). The OOD layer asks the different question: **"is the world behaving *unlike the regime these sensors were built for*?"** It's the closest mechanical approximation to a sensor for "something I didn't think to watch" â a tripwire for *novelty itself*. Not a solution to the unknown-unknown (nothing is); a flinch when the world goes strange.

**Two implementations, mapping to the two banks:**
- **Quantitative OOD (over Bank A/Aâ²):** not "spreads widened past X" (that's the in-distribution sensor) but "the *relationships among* spreads, vol, correlation, yields no longer look like any recent regime." Candidate methods: Mahalanobis distance from a trailing covariance window; or crudely, "how many gauges are simultaneously in their tails." Correlation breakdown is the cleanest case â variables that normally move independently suddenly co-moving (or vice versa) = the covariance structure has gone OOD even if no single gauge breached. *This is the closest port of the trading-bot's OOD, lifted to macro features.*
- **Qualitative OOD (over Bank B/C â the more novel, arguably more valuable one):** a **separate agent** that reads across all current dossiers **and the stored history of past dossiers** and characterizes how the *character* of findings has changed â new actors, new mechanisms, vocabulary that wasn't in prior runs. "Repeated references to a thing that wasn't on any sensor's watchlist" is distributional drift in unstructured text, which is what LLMs are good at. **It is a candidate-generator for new sensors** â how the panel escapes ossifying around today's risks.

**Required infrastructure:** a **persistent store of past agentic reports.** No reference distribution, no drift detection. (Doubles as the audit trail and the run-log archive.)

**The separate-agent requirement:** the OOD agent must *not* be the agent that wrote the reports â it would share its own blind spots and be blind to exactly the novelty it missed. Independence again.

**Sentiment as one drift axis (with a sharp caveat):** tonal/sentiment shift is a legitimate drift dimension, but **do not wire "negative sentiment = danger"** â peak *positive* sentiment is the Minsky/turkey tell (euphoria = thinnest buffers). Track *extremes in either direction* and *rapid swings*; the *change* is the signal, the *level* if anything inverts. Sentiment feeds the novelty detector; it is not a directional sensor of its own.

**Two design rules for Bank D:**
- **Tiered high and quiet:** OOD is inherently false-positive-prone (novelty â  danger; most new things are benign), so it should *almost never* fire, and only ever as a **T2 go-look** â never a DO-THIS. Its loose false-positive budget is justified *because* its alarms are cheap to check.
- **The one sensor explicitly allowed to be vague:** every other sensor must cite-or-fault; the OOD detector's legitimate output is "something feels off, here's the drift I'm seeing." Held to a different standard *on purpose* â it points at novelty to investigate, it doesn't make a sourced claim.

---

## 7. Sensor spec

*Starting thresholds are to **tune** â several depend on what the feeds actually return, and each should be backtested against the last ~15â20 years before being trusted. Reflects the book post-**URNM flatten** (proceeds â reserve alongside GLDM): satellite sleeves now GRID / NUKZ / XBI / ROKT / UFO, plus the GLDM sliver and cash reserve.*

### Bank A â Regime / fragility gauges (deterministic)

| Sensor | Starting threshold (tune) | Source-of-record | Tier |
|---|---|---|---|
| HY credit spreads | tight: <300bp (complacency); widening: +100bp/month | FRED `BAMLH0A0HYM2` | tight T1 / widening T2 |
| VIX | low: <13 for 3+ wks; spike: >28 | FRED `VIXCLS` | low T1 / spike T2 |
| Margin debt | YoY >~20% and accelerating | FINRA (monthly, lagged) | T1 |
| CAPE | context only â never fires alone | Shiller / multpl.com | T0 |
| Real 10y yield | context (gold + repression regime) | FRED `DFII10` | T0 |
| **Cross-sleeve correlation** | rolling 60d pairwise corr among sleeves >~0.7 **or** +0.2/month vs baseline | computed from daily returns | T1 â T2 |
| Broad-market drawdown | â20 / â35 / â50% vs trailing ATH | index price | **T3 â DO-THIS (deploy ladder)** |

*Calibration priority:* **cross-sleeve correlation** (baseline-relative, not absolute â and the most thesis-relevant gauge: it directly measures whether my "diversified" sleeves are secretly converging into one AI bet â "correlations rush to 1" caught while it's still creeping) and **HY spreads** (percentile-of-trailing-window almost certainly beats a fixed bp level).

### Bank Aâ² â Deterministic from the look-through

| Sensor | Threshold (tune) | Source-of-record | Tier |
|---|---|---|---|
| **Satellite % of book** | > ~25% (recompute baseline post-URNM-flatten) | `portfolio.yaml` + prices | T2 â rebalance |
| XBI AI-discovery cohort weight | > baseline + ~50% relative | XBI holdings file (SSGA, daily) | T1 â T2 |
| NUKZ Cameco weight | > set ceiling (joint-cap now collapses to NUKZ-only post-flatten) | fund holdings file | T1 |
| Per-holding drift vs target | Â±5pp abs or Â±25% of target | `portfolio.yaml` + prices | T2 â rebalance |

*Note:* define the XBI cohort list once (RXRX/TEM/RLAY/ABSI/SDGR/EXAIâ¦), set today's weight as baseline, alert on *growth*. This cohort imports AI-complex correlation into XBI via its **multiples** (not its cash flows), so it's the contaminant that erodes XBI's diversification value â a watch-it-grow tripwire, not an alarm about today's small weight. **Natural cross-check:** this same erosion is measurable two independent ways â cohort *weight* (here) and XBI's return-*correlation* to the AI complex (Bank A). Agreement = high confidence; divergence (weight flat but correlation rising, or vice versa) = a deep-dive. (The redundant-probe architecture showing up on its own.)

### Bank B â Thesis triggers (agentic scouts, cite-or-fault)

| Holding | Break-it condition | Scout watches â source-of-record | Tier |
|---|---|---|---|
| XBI | NIH/NSF appropriations freeze | appropriations bills â Congress.gov, AAAS R&D tracker | T2 |
| GRID | transformer lead times normalizing / China flooding queues | mfr earnings (Hitachi, Eaton, GEV), WoodMac â trade press | T2 |
| NUKZ | SMR FOAK costs stuck; policy reverses; HALEU bottleneck | Natrium/Kairos disclosures, NRC, DOE HALEU â filings | T2 |
| ROKT | defense budget cuts | NDAA, DoD budget â Congress | T2 |
| UFO | RKLB/Neutron execution stumble; SpaceX post-lockup unwind (~Jun 2027) | RKLB IR, FAA launch logs, SPCX filings | T2 |
| (confirming) | hyperscaler PPA flow â thesis-*confirming*, logged not alarmed | deal announcements â company PR | T1 |

### Bank C â Load-bearing / whole-book (multi-agent reconciled)

| Sensor | Why multi-agent | Vary the framings | Source-of-record |
|---|---|---|---|
| **AI demand durability (the beam)** | the master break; a false-green here is the costliest in the system | (a) hyperscaler capex guidance, (b) AI revenue/monetization, (c) efficiency + demand-response *deferring* build | hyperscaler 10-Qs, earnings, interconnection-queue data |
| Uranium term price + contracting | term price not cleanly sourceable; triangulate (note: smaller role now that URNM is flattened â NUKZ retains Cameco/fuel exposure) | (a) term-price commentary, (b) contracting cycle, (c) supply (Kaz/Cameco) | UxC/TradeTech secondary, filings |

### Bank D â OOD / novelty (meta, across the others)

| Sensor | Output | Tier |
|---|---|---|
| Quantitative OOD | covariance-structure drift / N-gauges-in-tails / correlation breakdown | T2 |
| Qualitative OOD | drift in dossier character vs report history (new entities/mechanisms/vocab/tone) â generates candidate new sensors | T2 |

---

## 8. Flying-blind list (named, because the panel must not hide them)

- **Term uranium price** â paywalled (UxC/TradeTech). The "watch term, not spot" discipline is the single hardest thing to instrument cleanly; multi-agent triangulation is a workaround, not a feed. *(Eased somewhat by the URNM flatten â the spiciest, least-instrumentable position is gone; NUKZ's fuel exposure remains but is one input among many.)*
- **True transformer lead times** â no public index; earnings-call commentary only, inherently agentic and laggy.
- **SMR FOAK actual cost** â disclosed sporadically, not a series.
- **The unknown-unknown** â uninstrumented by definition. Bank D is a partial flinch, not a fix. **This is the line that keeps the structure, not the panel, as the backstop.**

---

## 9. Operating disciplines

- **Cadence: every-other-week scheduled runs (26/yr).** Honest note: thesis facts don't change on a two-week clock, so this *slightly degrades* signal-to-noise vs. monthly â the extra runs mostly resample unchanged states. It's chosen anyway because it's a *constructive outlet that displaces trading*; that's a good trade given the wiring, as long as the **thesis-gate threshold stays high regardless of run frequency** (running more often must not lower the bar for what trips a review).
- **On-demand run button â the pressure-release valve.** For *new information arriving* (Hormuz closes, a surprise CPI print), not for anxiety. Protects the schedule: the legitimate urge to look when the world moves gets satisfied without dissolving the default of silence.
- **Run-log every manual run with a one-line reason.** Not a restriction â a **tell**. Re-read in three months: reasons like "Strait of Hormuz closed" = working as designed; reasons like "wanted to check" = the rule-16 running-log test catching the tool turning into catnip. The log is how I audit my own discipline.
- **Hard authority boundary:** the agent layer has no execution surface; it writes to a review queue only. No order placement, no pre-staging.
- **Alert on *trigger conditions*, never raw price moves.** "NIH appropriations headline â XBI funding-freeze gate" sends me to a review; "uranium â4% today" is a price alert in a costume and retrains the over-trading it's meant to prevent.
- **Build order:** Banks A + Aâ² first â a complete, useful v1 with **zero hallucination risk** (whole fragility bank + four real thesis sensors, all deterministic) that gets the cron + Discord plumbing working end-to-end. *Then* add scouts one trigger at a time. *Then* Bank C reconciliation. *Then* Bank D. Don't build the co-pilot before the airspeed indicator reads true. (Also the discipline defense: an agentic system is tinker-bait squared â sequencing it last keeps the build itself from becoming the new impulse channel.)

---

## 10. The two roulette chambers (explicit watch-items)

Complexity and engrossment are **not** danger signs and won't be flagged as such. The two configurations that *are*:

1. **Authority creep** â agent output drifting toward execution with less of me in the loop. (The config where a confident hallucination becomes a trade.)
2. **Impulse migration** â the building/checking shifting from "displaces trading" to "new high-frequency channel for the same impulse"; the manual-run log filling with anxiety rather than information.

If either appears, it gets called plainly. Those are the chambers; complexity isn't one.

---

## 11. Division of labor for the build

- **Chat thread (in the investments project):** design and judgment â what to instrument, how to threshold, whether a gauge is noise, reviewing alerts when they fire. Project knowledge (thesis rev. 4, the synthesis docs, per-holding templates, this brief) carries automatically.
- **Claude Code (VS Code, on the existing look-through dashboard):** implementation â ingest, cross-checks, cron, Discord webhook, the report store. Bolt the trigger + fragility panel onto the holdings ingest; turn the snapshot into a monitor.

Judgment in one place, mechanical execution in another â the same separation as everywhere else in the system.

---

*Not financial advice â a build spec for my own monitoring tool, reflecting my own theses and risk rules. The sensors inform reviews; every decision and every trade remains mine and passes through my hand on the controls. The structure, not the panel, is the backstop.*
