# The Thesis Smoke Detector — Decisions Review

*Companion to the generator review, dated 2026-06-29. This is a concept-freeze for the defensive twin: it records every choice the build settled, the reasoning that load-bears each one, what is built versus pending, and the forks still open. The key difference from the generator review — where those decisions are brainstorm-settled but unbuilt, **these have already survived contact with code and real data.** This is the record of what held under implementation; §11, the bug hunt, is the proof that the design met reality.*

---

## §0 — Naming the pair, and which is which

The generator review already proposed the polarity; this fixes the reasoning so you can ratify it.

- **Detector: the Smoke Detector.** Established, defensive, inward — it watches what you already hold and either says GO-LOOK or stays silent. Its best day is a quiet one.
- **Which is yin.** The detector is **yin**: the receptive, inward, still, conserving principle — it watches, it waits, it defends the committed structure, and it speaks only when something it already owns is moving. The generator is **yang**: active, outward, expanding — it ranges the frontier and produces new objects of attention. A defender that mostly stays silent and points *inward* is yin almost by definition; a generator that ranges *outward* and proposes is yang. (The pleasing seed-in-each: the detector carries a generative seed — a thesis weakening *opens* a question — and the generator carries a defensive seed — the wall. But the dominant reading is clean: detector = yin, generator = yang.)
- **Umbrella, if you want one: Janus** — one system, two faces, one looking inward at what you hold, one outward at what's forming.

The rest of this document uses *detector*.

---

## §1 — The spine that did not move

The conceptual foundations that held across the entire build, stated briefly because they are settled.

- **Defensive by construction.** The detector's output vocabulary is **GO-LOOK and silence**. It has no verb for "acquire." Its prescriptive parts (deploy-this-tranche, rebalance-to-target) are *closed-form* — rules written in advance, in calm, against your own committed structure; a thermostat cannot propose more than the rule contains. You cannot overtrade from a tool whose loudest statement is "look at what you own." This is the structural safety the generator has to fake with a habit.
- **It's hard not to be a turkey — so bound it, don't escape it.** The turkey's error was certainty built on a finite history that structurally couldn't see the tail. No cleverness removes that; every layer of the system is a turkey-hedge with the hedge made explicit. The goal is never to be a *bankrupt* turkey — to be **wrong survivably**. The dangerous state is the operator sure he is *not* the turkey.
- **The calm is the loading.** From the sandpile: the trigger is not the cause, the slope is. The instrument reads the *regime*, not the *event* — which is why every reading is a trajectory and the level is a footnote.
- **Drift is the unifying measure.** The detector measures a held thesis drifting toward break; the generator measures discourse drifting into the new. Same operation — distance from a frozen point — two corpora.
- **The two roulette chambers — the only things to flag.** *Authority creep* (agent output drifting toward execution) and *impulse migration* (checking the panel filling with anxiety not information). Complexity and engrossment are explicitly **not** flagged; they are the point.
- **The hard authority boundary: no execution surface.** The human keeps the one thing never delegated — the commitment to act. This is the BDI boundary (§7), drawn where it belongs.
- **Prove it cheap before committing resources.** The dominant decision heuristic, restated unprompted across the whole build, and the reason ρ(G) is deferred and D ships on the cheapest lens.

---

## §2 — The five-bank architecture

The structural decomposition that organized the whole build. Five banks, increasing capability and *decreasing* authority — the master-caution light has the highest priority and the lowest right to act.

| Bank | What it is | LLM? | Authority | Status |
|---|---|---|---|---|
| **A** | deterministic regime / fragility gauges (FRED, VIX, credit, absorption) | no | gauge → tier | built |
| **A′** | deterministic look-through on `portfolio.yaml` (concentration, sleeve %) | no | gauge → tier | built |
| **B** | agentic scouts — one airworthy pilot, cite-or-fault, six guards | yes | finding → tier | built |
| **C** | multi-agent reconciliation — N independent scouts, classify-not-merge | yes | confidence label → tier | built |
| **D** | OOD / novelty meta-layer — the master caution light | (lens) | **always GO-LOOK, never DO-THIS** | pending |

**Build order was A+A′ → B → C → D**, cheapest and most-deterministic first. D is the only bank left, and it can ship on a simple absorption-ratio lens without ρ(G) (see §8, §15).

---

## §3 — Manufactured independence and the reconciliation discipline (Bank C)

The deepest engineering decisions in the system, and the two that, if violated, silently destroy it.

- **Manufactured independence via varied seed *trajectories*, full shared source access.** Naïve temp>0 gives sampling variance, not independence → correlated confabulation → *false consensus*, which is worse than one scout because it wears the costume of corroboration. Independence is built from different entry angles with everyone able to see everything. **Never partition domains** — partitioning manufactures coverage-gap disagreement and is the first of the two fatal mistakes.
- **Reconciliation is classify + surface, never merge.** An LLM reconciler would be a *seventh confabulator* that launders disagreement into false consensus — the precise failure C exists to prevent. This is the second fatal mistake. The machine classifies agree/disagree (drives the tier) and surfaces the N views; the human is the claim-matcher of last resort, by design.
- **The four-state confidence label — structure, never a score.** CORROBORATED (all agree, disjoint sources) / CONCORDANT (all agree, shared sources) / CONTESTED (split) / THIN (agree, weak coverage). A four-state enum, never a 0–1 score, so no false precision. It **describes scout convergence, never claim truth** — "CORROBORATED" means independent paths agreed, not that the world will comply.
- **Source-disjointness is the corroborated-vs-concordant distinction.** Domain-level, per-direction, on conclusion-bearing findings. Three scouts agreeing from disjoint domains is the fabrication filter at full strength; three agreeing on one source is agreement that collapses if that source is wrong.
- **Strict escalation asymmetry.** Only CORROBORATED-away → T0 (full relax); CONCORDANT/THIN-away → T1 (quiet); every toward-read and every CONTESTED → T2/GO-LOOK. The only path to silence is independent corroboration of intactness — biased toward "stay a little alert," the safe error for a tool whose failure mode is false reassurance.
- **Quorum and faulting.** N=3 default; n=1 FAULTs loudly; fewer than two clean survivors FAULTs. Knobs `corroborated_requires_disjoint` and `corroborated_requires_unanimous`, both default-strict.
- **Two designs rejected, and why.** *Advisor-tool as independence* (a cheap model consulting a strong one) — rejected because it **couples reasoning**, correlated confabulation, the exact thing C prevents. *LLM reconciler* — rejected as the seventh confabulator. Both rejections share one instinct: independence cannot come from coupling, and disagreement must be surfaced, never averaged.

---

## §4 — The six guards and the source model (Bank B)

Each scout is one airworthy pilot before it is ever put in a fleet.

- **Cite-or-fault.** A finding without a citation is a fault, not a fact. Known = asserted; uncited = visibly faulted (never dropped, never guessed). This reappears on the generator side as fold-shows-its-events.
- **The six guards:** *cite-or-fault, coverage, tier, sourcing-asymmetry, numeric, motive.* They are advisory at the cross-scout layer (consensus among them never silently changes a tier).
- **Source tiers:** PRIMARY / REPUTABLE / UNRANKED / LOW_TRUST. The tier gates whether a scout may *vote*, not whether two scouts share evidence — a distinction that turned out to be load-bearing (§11, bug 1).
- **The motive axis:** against-interest / neutral / self-serving. **Promotional news ≠ de-risking** (an announcement without figures is not confirmation) and **policy-input ≠ supply-output** (a DOE dollar is intent; a delivered kilogram is fact) both live here.
- **Pilot and fleet.** B is the brick — the cheap routine path, a single airworthy scout. C is the N-unit aggregation. *You can't triangulate without separate observations*, and a fleet of one is not a fleet.

---

## §5 — The freezer: run store, PIT, append-only

The same primitive that runs through the whole system — *don't let the present rewrite the past* — appearing here as the detector's own memory.

| LTEE | Detector |
|---|---|
| frozen samples every 500 generations | the run store — persisted sweeps, never overwritten |
| daily transfer, identical medium | the scheduled sweep on a fixed cadence |
| fossil record locates *when* | re-derive any past run from its frozen inputs |
| Cit+ visible only in replay | the reconciler fix proved by replaying a real run |
| potentiation: silent prior state | sub-threshold checkpoint drift, invisible at the time |

- **The run store is a re-derivable freezer.** It is what proved both reconciler-bug fixes at **$0** — offline re-derivation on the actual triggering run, no re-seed needed. The archive is not support for the detector; in that moment the archive *was* the test.
- **PIT vintage data.** Timestamp by release date, not revision date — or the ghost-line lies and your distance measures your data vendor's revisions, not the world. This is the prerequisite gating ρ(G).
- **Append-only, with heartbeat suppression.** Corrections are appends; the store grows and is never pruned. A confirmed-working heartbeat-suppression layer keeps a quiet sweep from emitting noise.
- **Where it differs from the generator, and it matters.** The generator's fossil record is read-only *forever* — it can thaw backward and observe precursors but never re-run discourse, so it yields **reconstructed path, never demonstrated cause.** The detector is luckier: its computation is *deterministic given frozen inputs*, so a replay is genuinely causal — re-running the frozen sweep reproduces the result exactly, which is why a $0 re-derivation could *prove* a fix rather than merely suggest one. The detector can re-run its past; the generator can only read its own.

---

## §6 — The HUD: the anti-Bloomberg terminal

The indicator layer — specced this cycle, **in build now** — and the place the project comes to life. A trading terminal is loud all the time; this is the inverse instrument.

- **The governing inversion.** Spend salience on **change, not magnitude**. The dashboard looks *boring* by default, and boringness is the feature, because it is what makes the rare burst of salience trustworthy. If everything is colored, nothing is.
- **The three-register rule** (the spine of the spec). A sensor is always in one of three states, each with its own voice: **calm** (quiet grey, thin line) / **break** (loud red — go look now) / **fault** (loud but *distinct* — "I've gone blind here"). The casino failure (alarms always firing → "loud" means nothing) and the silent failure (a dead gauge looking calm) pull opposite ways; only three registers satisfy both. The casino rule keeps red rare; the fail-loud rule makes fault scream in a different voice than break.
- **Trajectory is the instrument; the number is the footnote.** The slope shows the loading; the level is nearly meaningless. The rare dashboard where the headline number is small and the little line is big.
- **Trust-encoded, cockpit-labeled.** Every row shows value *and* reliability as one object — confidence label, guards, tier, freshness. Freshness mandatory: a reading with no freshness is indistinguishable from a stale one.
- **Silence designed, not absent.** A positive heartbeat (`live · N/N · swept · next`) so that *no signal* unambiguously means *broken*, never *calm* — the dead-man's-switch.
- **The intelligence report: raw JSON → a legible finding.** A pure render transform (the data is already there — not blind, just raw). Sources grouped **by direction** with tier and motive, clickable; guards as labeled annunciators; the four-state label expandable to its disjointness reasoning; raw JSON kept one click down so the audit artifact survives.
- **The relational view.** A cross-sleeve correlation/graph — sleeves as nodes, edges that thicken and warm as correlation climbs toward the ceiling. The fleet's source-disjointness question at the portfolio scale: *is my diversification secretly one bet?* A list cannot show "XBI and ROKT moving in lockstep"; this can.
- **The frozen-ghost sparkline + horizon disagreement.** Every trajectory carries a faint frozen baseline; the gap is the drift, rendered. A drift glyph lights when fast and slow baselines disagree — the boiling-frog detector.
- **Read-only, no recompute.** No run-now, no autorefresh, no live fetch on load. There is nothing to *do* on the surface, only things to *see* — which is the over-trading defense drawn at the render layer.

---

## §7 — The human in the loop

- **The BDI inversion.** You sit at the top of an auditable belief–desire–intention network. Scouts are belief units; Bank C is belief *reconciliation* (the hard part classical BDI hand-waves); tiers are a stripped-down desire/intention layer. Standard BDI fails through *opacity*; this is the **auditable** BDI — beliefs guilty-until-grounded, intentions proposed-*up* rather than executed-*down*. The live risk: a BDI network is built to *relieve* its top layer of load, which is the authority-creep chamber — so the top layer must stay a deliberator who mostly decides "no."
- **The only two legitimate sell triggers.** A *broken thesis* or *drift past intended size* — **never price**. Encoded everywhere: the detector can flag a break or a size-drift; it has no concept of "it went down, sell."
- **Sizing is the primary risk control.** Positions sized so a 50%+ drawdown cannot force a sale. The ORA exit was a *sizing-system* decision (single-name ran to ~2× intended weight), not a thesis call — the system working as designed.
- **The roulette chambers as self-monitoring.** The two named failure modes are the only things to watch for, and they are about the *operator's relationship to the tool*, not the tool's complexity.

---

## §8 — ρ(G): the deferred criticality gauge

A panel-level context gauge, deferred behind its prerequisite, with the design socket already cut.

- **What it is.** The endogenous branching ratio — distance-from-criticality. It reads *kindling, not fire*: ρ → 1 means self-exciting feedback dominates, the system primed for one spark to cascade. Trajectory-not-level; ρ *creeping toward 1* is the loading. It's the fire-danger rating, not the lightning forecast.
- **The socket.** A uniform `GaugeReading` (value, trajectory, threshold + side, frozen baselines, freshness, optional quality note). ρ(G) drops in as *just another row* — and so does any future gauge. If adding it ever needs HUD surgery, the socket was cut wrong.
- **Why deferred, not the socket.** It needs the **PIT vintage layer** (its history must be computed on point-in-time data or the ghost lies), and the kernel fit is still open. It is the frozen skunkworks experiment.
- **The literature check (done, this cycle).** The gauge is a real decade-plus econophysics vein (Filimonov–Sornette branching ratio; Hardiman–Bercot–Bouchaud near-critical reading; Hardiman–Bouchaud moment estimator). The field's hardest finding is the validation of your own design: the estimate is *brutally sensitive* to kernel, background-rate, and window, and a mis-specified fit **manufactures false criticality** — which is exactly the §6 fit-quality annunciator, made non-optional ("a gauge that doesn't know its own number is fault-adjacent"). The level is untrustworthy in absolute terms; the *trajectory* and *cross-estimator agreement* are the trustworthy reads — the fleet-of-distances, forced on you by the estimator's fragility. Directional loading (does it catch a melt-up, not just a crash?) is real via quadratic Hawkes (the Zumbach/return-sign extension). And the unsettled causality — does ρ *lead* or merely *persist* near 1 — is precisely why D's placement is right: context, lowest authority, always GO-LOOK, never a trigger. You designed for the field's actual epistemic state without having read it.

---

## §9 — The thesis (rev.6) and the findings in the wild

The portfolio the detector watches, and the real discoveries that shaped its triggers — the detector's analog of the generator's HECO/TEKX lessons.

- **HALEU as common-mode — promoted to a first-class break-trigger.** Almost every advanced reactor needs the same enriched fuel, so HALEU is the one input *every* NUKZ holding shares — the place ETF diversification cannot protect, a load-bearing beam inside one sleeve. Common-mode failures need their own trigger; sleeve diversification doesn't touch them.
- **The breakthrough desert.** NIH/NSF cuts land now but feed clinical catalysts on an 8–12-year lag, so the damage is invisible in today's pipeline and surfaces later as a thinning of shots-on-goal. "The calm is the loading," applied to research funding. Held loosely on timing; partially offsettable except early-stage VC is *also* at decade lows.
- **Centrus cyclicality.** The HALEU linchpin sits in a sub-sector that ran −96% from its 2007 peak through a 2014 bankruptcy — an argument *for* the diversified wrapper and for promotional-news ≠ de-risking, not against the thesis.
- **Common-mode risk, generalized.** When reviewing any sleeve, ask not "are the names diversified?" but **"do they share a single upstream dependency?"**
- **The fleet concentration map.** Three drivers, not five bets: AI-power → GRID + NUKZ (correlated confirmation); US appropriations → XBI + ROKT (the two all-independent sleeves, same intact-now/future-funding-dependent shape); space → UFO (alone). Effective-bets < position-count — the thing the relational HUD view exists to render.
- **ORA exited; ACTUAL-vs-TARGET drift managed by deposits.** Convergence to target via direction-of-deposits to the core, not force-selling satellites — tax-free inside the Roth, and consistent with "never sell on price."

---

## §10 — Infrastructure and cost

- **Scheduled CLI / cron sweep** on a fixed cadence — the unbiased backbone.
- **Discord webhook for state-change push**, carved out in `CLAUDE.md` under four explicit guardrails: a hard cadence floor, push only on state-change, read-only/no-execution, and the two roulette chambers named as standing review items.
- **S3 append-only run store**; lifecycle rules age old runs into cheap storage without deletion — the fossil record gets cheaper, never pressured to prune.
- **Streamlit dashboard**, read-only: look-through aggregation, the run-store renderer, and the indicator HUD (in build).
- **`portfolio.yaml` is the single source of truth**; the read-only constraint is non-negotiable across all tooling.
- **API:** Messages API `web_search` server tool (metered), scouts dispatched in batch (~50% cost), reconciled.
- **The dead-man's-switch.** An unwatched scheduler drifts until the alerts silently stop, and *no alert looks identical to a quiet day* — the turkey problem in the infra layer. The heartbeat must fire even on a quiet sweep so that *silence* unambiguously means *broken*, never *calm*.
- **Repo:** `src/monitor/` (`scouts.py`, `sensors.py`, `types.py`, `feeds.py`, `run.py`, `views.py`, `cohorts.py`, `lookthrough.py`), `config/monitor.yaml` with the `group:` label, `CLAUDE.md`, `ReportStore`. Infra-as-code in the repo, not a hand-configured server.

---

## §11 — The bug hunt, in the wild

The most concrete validation the system has — the place the abstract design met real data and taught something. Two reconciler bugs, **both inflating CORROBORATED by discarding information before the independence check.**

1. **`_conclusion_domains` tier-filtered before the disjoint test.** It dropped sub-tier evidence before comparing scouts, so two scouts both leaning on the same UNRANKED source (`thebreakthrough.org`, on NUKZ) read as *more* independent than two sharing a wire — exactly backwards. Fix: assess independence over *all* grounded evidence; the tier gates the vote, not the comparison. Dropping the now-dead `_tier` helper and unused `spec` param was the tell the boundary had landed correctly.
2. **An abstaining scout was dropped**, letting a 2-of-3 reach the top label. Fix: CORROBORATED requires unanimity; an abstention caps at CONCORDANT.

**Verification, deterministic and $0:** two regression tests, each failing pre-fix; 215 pass; offline re-derivation on the *real* triggering run flips NUKZ and ROKT from CORROBORATED to CONCORDANT and *nothing else*, both staying T2 — so no alert behavior moved, only the label's honesty. Committed `03daeb7`.

The shared instinct: **count everything before you decide it's independent**, and both fixes can only ever *tighten* CORROBORATED, never manufacture it. The meta-lesson is the one worth carrying: a trusted tool goes *invisible from working well*, and the way you find out whether it still measures what you think is to **perturb it from an angle you don't normally use** (the coupling test) — corrupt an input, run the assay you've been skipping, compare two things you'd assume identical, and see if it breaks the way it should. That is how both bugs hid, and how they surfaced.

What the runs themselves found: nothing tripped a *new* break; every fleet confirmed an already-in-thread risk (Neutron slip, SpaceX lockup, HALEU, early-biotech freeze, FY27 defense cliff), with away-evidence stronger on fundamentals. The system behaved correctly and *quietly* — which is the success state for a defensive instrument.

---

## §12 — Decisions ledger (for fast review)

| # | Decision | Choice | Why it held |
|---|---|---|---|
| 1 | Signal philosophy | alert on a TRIGGER condition, never on raw price | price is the laggiest, most-priced-in number; breaks and size-drift are the only real signals |
| 2 | Push vs pull | push on state-change via webhook, hard cadence floor | a tool you must check becomes an anxiety object; state-change push can't reward compulsion |
| 3 | Independence | varied seed trajectories, full shared access | partitioning domains manufactures coverage-gap disagreement |
| 4 | Reconciliation | classify + surface, never LLM-merge | an LLM reconciler is a 7th confabulator that launders disagreement |
| 5 | Confidence | four-state enum, not a 0–1 score | describes scout convergence, not claim truth; no false precision |
| 6 | Disjointness | domain-level, per-direction, conclusion-bearing | corroboration from disjoint sources is the fabrication filter at full strength |
| 7 | Escalation | only CORROBORATED-away → T0; everything else stays alert | the only safe error for a false-reassurance failure mode is "stay a little alert" |
| 8 | Quorum | N=3; n=1 FAULTs; <2 survivors FAULTs | a fleet of one is not a fleet; faults must be loud |
| 9 | Guards | six, advisory at the cross-scout layer | guard consensus must never silently move a tier |
| 10 | Storage | append-only run store, re-derivable | proved the reconciler fix at $0; hindsight-resistant by construction |
| 11 | Data vintage | point-in-time (release date, not revision) | otherwise distance measures vendor revisions, not the world |
| 12 | HUD salience | boring by default; three registers (calm/break/fault) | satisfies the casino rule and the fail-loud rule at once |
| 13 | HUD reading | trajectory primary, number a footnote | the slope is the loading; the level is nearly meaningless |
| 14 | HUD surface | read-only, no recompute | nothing to *do*, only to *see* — over-trading defense at the render layer |
| 15 | ρ(G) | build the socket, defer the feed behind PIT | prove-it-cheap; uniform gauge interface costs nothing until the data is honest |

---

## §13 — What's built, what's pending

| Component | State |
|---|---|
| Deterministic sensor pipe (A/A′), Mag-7 concentration gauge | **built**, 14 tests, verified on a real 12,485-row holdings export |
| Bank B scouts — cite-or-fault, six guards, source tiers | **built** |
| Bank C fleet reconciliation — including both bug fixes | **built**, 215 tests, committed `03daeb7` |
| Run store, heartbeat suppression, Discord webhook under guardrails | **built** |
| Indicator HUD / read-only run-store page | **in build** (Claude Code, now) |
| Bank D — OOD / master-caution | **pending** — can ship on an absorption-ratio lens (§15) |
| ρ(G) / Hawkes criticality | **deferred** behind the PIT layer; fit open |

---

## §14 — Open questions, for your review

**A. Phase D's lens and its authority (the main one).** Can D ship on a simple absorption-ratio lens — PIT-clean, free, no ρ(G) — and what is D *allowed to say*? (My way through is §15.)

**B. The PIT vintage layer.** ρ(G) and any honest frozen-ghost baseline both need it; it is the shared prerequisite, currently unbuilt.

**C. Snapshot cadence for the append-only run store** — the performance mitigation as the store grows. A real parameter, unset.

**D. Guard-review cadence** — how often you re-ratify the six guards and their thresholds before they ossify, the detector-side analog of the generator's vocabulary review.

**E. The relational view's correlation method** — raw vs residual (stripping the common market factor), and which windows. Same residual-vs-total instinct as the generator's excess-co-movement.

**F. The frozen-ghost horizons** — which baselines (thesis-write, login, fixed anchor) and the fast/slow pair that drives the frog glyph.

**G. Naming** — confirm yin = detector / yang = generator and the Janus umbrella.

---

## §15 — An insight on how to approach the open fork

Phase D (fork A) looks like a "which OOD method" question. It isn't. It collapses to a sharper one: **what is D permitted to *say*?**

D is the purest expression of the salience budget — the one light allowed to override the calm, the master caution. Its whole danger is authority creep: the temptation to let the cleverest layer also be the most *trusted* one. So the decision that load-bears D is not its statistic but its **vocabulary**: D must remain GO-LOOK-shaped forever — *highest priority, lowest authority, always "look at the thing I wasn't built to instrument," never "do this."* Fix that and the method almost doesn't matter.

Which is exactly why D can ship on the **cheapest possible lens** — the absorption ratio, PIT-clean and free — *because its job is to nominate a look, not to be precise.* Prove-it-cheap, one more time: ship D on absorption-ratio now; ρ(G) is a later module that plugs the same socket (§8). You do not need the expensive gauge to stand up the master caution; you need the *honest* one, and the cheap one is honest enough to nominate.

And here is the insight that ties the whole pair together. **D is unsupervised by construction** — you cannot label "the thing you didn't instrument for," so you can only model normal and flag departure. That is *the same primitive as the generator's novelty layer*, pointed the other way: D models the structure of your own book and flags departure inward; the generator models the discourse frontier and flags departure outward. The master caution light and the Prospector are **one OOD engine with two muzzles** — model normal, flag departure, let the human decide. Build D and you have built half the generator already; build it with the wrong authority and you have built the casino. The fork resolves the way every fork in both projects resolved: cheap always-on capture, expensive interpretation deferred, the human ratifying, and the present never permitted to rewrite the past.

---

*Throughline: the detector is the disciplined twin — same drift measure, same freezer, same reconciliation logic as the generator, opposite polarity, with a wall built into its vocabulary where the generator must hold a habit. The build's work was mostly to discover, decision by decision, that the right answer was almost always to make silence trustworthy, to count everything before trusting agreement, and to refuse to let the present rewrite the past. It watches; it never acts. Its best day is the day it says nothing, truthfully.*
