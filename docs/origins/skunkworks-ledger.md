# Skunkworks Ledger

*The freezer for experiments. One place to keep everything straight; one door out to production. This is a template — adopt and edit like the thread template.*

---

## Why a ledger, not a log

A log records what happened. A **freezer** preserves *replayable states* — so the past can be re-run, not just remembered. This matters for one reason that governs everything below: **the thing you most want to catch won't look like anything when it's forming.** A structural shift, a thesis drifting, the silent change that potentiates a later breakthrough — none of it is legible at the moment it occurs. You can only see it by thawing an earlier state and measuring the distance. **Drift is invisible without a baseline to compare against, and the archive *is* that baseline.** A log can't do this; a freezer can. (Same primitive as the run store that re-derived the reconciler fix at $0 — point-in-time states you can replay.)

The firewall is the other half: a skunkworks is defined by what it's *walled off from*. Experiments live here so they can be half-built and wrong without leaking into the committed system that watches real money. **Commingling is the danger.** Nothing crosses the wall without clearing the gate (below).

---

## The four disciplines (from the Lenski LTEE)

1. **Freeze states, not events.** When you start or kill an experiment, archive enough to *re-run* it — config + inputs + actual output — not just a sentence about it. The one-line note is the label on the tube; the frozen state is what makes the label worth keeping. A thawed dead experiment can answer a question you didn't think to ask at time of death.

2. **Freeze on cadence, not on interest.** Freeze at **birth** and at **death** (and at major forks), *mechanically*, regardless of whether the experiment felt worth it. The whole lesson of the LTEE's Cit⁺ event is that the potentiating changes were **boring at the time** — the mutations that made the breakthrough possible looked like nothing for 30,000 generations. If you only archive the experiments that feel promising, you've already decided what's interesting, and you'll have thrown away the boring ancestor you'll later wish you could thaw. Resist the urge to curate.

3. **Track ancestry — the graveyard is a phylogeny, not a list.** Experiments descend from other experiments, and most of all *from the conclusions of dead ones.* Each entry names its parent. New discoveries build on earlier successes **and** failures; the dead end you killed is often the potentiating mutation for the experiment three months out. Structure the ledger so you can read the lineage, not just scan a list.

4. **The graveyard is the most valuable section.** Failed experiments show you the map in a way success doesn't. Every death gets two fields: a **cause of death** (why it died) and a **potentiating note** (what door it left ajar). The second is the one people skip and the one that compounds — not "what did this prove" but "what did this teach that something later might need."

---

## The one door: the graduation gate

The wall only works if there's exactly **one door** and you know where it is. An experiment may not touch production — the committed portfolio, the live monitor, anything load-bearing — until it clears the gate. The failure mode of a skunkworks isn't bad experiments (those are the point); it's a fun prototype graduating into production *because it was interesting*, without ever clearing the bar the boring committed things had to clear.

**Graduation gate (a research tool must prove all three):**
- **Survived contact with real data** — not just synthetic fixtures or a compelling argument.
- **Failure modes are understood** — I can explain how it breaks, not just that it works. (Comprehension is a gate, not a phase.)
- **It didn't just confirm what I already believed** — it told me something I'd have bet against, or it survived a real attempt to disconfirm it.

Nothing graduates on charm. If it can't clear the gate, it stays an experiment — which is a fine thing to be.

---

## Per-experiment entry (the schema)

```
SKW-### · {name}
Status:        active | frozen (paused, may thaw) | graduated | killed
Born:          {date} — forked from {parent SKW-### / conclusion of X / external spark}
Question:      {the hypothesis in one line — and what would prove or kill it}
Frozen state:  {pointer to archived config + inputs + output, re-runnable — path/commit}
Log:           {dated entries — what changed / what was learned}
Cause of death:{one line, on kill}
Potentiating:  {what door it left ajar — what a later experiment might need.
                ALWAYS filled on death; optionally on graduation/freeze}
Graduated to:  {where it went + what gate evidence cleared it, if graduated}
```

Minimal on purpose. The discipline is in the *habit* (freeze on cadence, always write the cause of death and the potentiating note), not in a baroque schema.

---

## Worked examples

**SKW-000 · Advisor-tool as scout independence** — `killed (2026-06-26)`
- Born: during Bank C design — testing whether the API's advisor mode (cheap model consults a stronger one mid-task) could manufacture scout independence cheaply.
- Cause of death: it *couples* the two models' reasoning → correlated confabulation, the exact false-consensus failure Bank C exists to prevent. Independence cannot come from shared-model consultation.
- **Potentiating:** independence has to come from *varied entry angles with full shared source access*, not from coupling — which became `missions(n)` (seed-trajectory independence) in the production reconciler. *A dead idea that defined the shape of the surviving one* — the cleanest proof of why the graveyard is the valuable section.

**SKW-001 · Thesis Generator (the yang)** — `active`
- Born: 2026-06-28 — forked from the OOD / master-caution insight (distance-from-normal), pointed *outward* at sector discourse instead of inward at the book.
- Question: can an *unsupervised* novelty detector over sector discourse surface real structural shifts early enough to research — without drowning in consensus or mistaking hype for signal? Killed if it only ever surfaces what's already priced and known.
- Frozen state: *pending — first prototype not built.*
- Log: 2026-06-28 — scoped. Target Dow sector sub-indexes (indexes, not single names — stays in the own-the-industry lane). Two-stage: wide novelty scan (recall-optimized) → human deep-dive (precision). Output is a **reading list, never an order ticket** (the firewall the defender holds with a wall, this holds with a habit). Reframe locked: rank by *how real/durable the shift is*, not *how good the trade is* — argument-quality, never opportunity-quality.

**SKW-002 · ρ(G) / Hawkes criticality (branching ratio as reflexivity gauge)** — `frozen`
- Born: forked from the microstructure Hawkes work → macro-timescale port.
- Question: does the endogenous branching ratio ρ(G) *lead* the level gauges (absorption ratio, vol) into a regime break — i.e., is it forward-looking by construction? **Disproof acceptable** — the hypothesis is stated to be killed if false.
- Frozen state: `rho-G-hawkes-criticality-subsystem-design-theory.md` ([HYPOTHESIS]-tagged theory capture).
- Thaw condition: blocked on the PIT vintage-data layer (its real prerequisite). Thaw when that exists.
- **Potentiating (partial, while still frozen):** the *capacity-inversion* lesson — excess model capacity breeds overfitters on scarce macro data — already graduated into the lean-interpretable design stance for the whole monitor. *Even frozen, it potentiated something that shipped.*

Note the phylogeny already visible across three entries: a killed idea (000) defined a production design; a frozen idea (002) potentiated a shipped philosophy; a new idea (001) descends from an insight that was itself the outward-pointed twin of a defensive layer. None of these are isolated — that's the point of tracking ancestry.

---

## The same freezer, pointed elsewhere

The freezer is one primitive with more than one target — recognize it rather than rebuilding it three times:

- **Thesis-drift detection (the generator's hard problem).** To catch a sector's thesis drifting, you need frozen snapshots of what that sector's discourse *normally* looked like — novelty is departure-from-normal, and "normal" is a frozen baseline. The archive isn't support for the detector; the archive is the detector.
- **Your own portfolio theses.** The master thesis is *already* a frozen lineage — rev.2 → rev.6, each a dated snapshot. That's a phylogeny of your own thinking, and it's why you can see how the HALEU view evolved rather than just asserting the current one. Keep bumping revisions rather than overwriting, for the same reason Lenski freezes every 500 generations.

The unifying instinct, the same one that runs through the PIT data layer and the re-derivable run store: **don't let the present rewrite the past.** The past has to be replayable in the information environment it actually occurred in, or you manufacture hindsight. Lenski freezes *E. coli* for the same reason you timestamp by release date. The Skunkworks Ledger is that instinct pointed at your own experiments — so future-you inherits not just the conclusions but the actual states that produced them, and can ask better questions than you knew to ask.

---

*Adopt, renumber, and edit freely — this is the seed, not the law. The one rule worth keeping rigid: freeze on cadence, write the cause of death and the potentiating note every time, and let nothing through the door that hasn't cleared the gate.*
