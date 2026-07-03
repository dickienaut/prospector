# Prospector — Resolving the 7 Persistent Crash-Window Flags (rev 2)

### Design-thread guidance, 2026-07-02 (ratified policy record)

*Responds to the milestone-3 rev5 outcome: acceptance test 5c(iii) flagged 7 of 10 March-2020
crash-window spawns as persistent (Financials-heavy — XLF×XLU, XLF×XLRE, XLF×XLP, XLB×XLF, XLI/XLB
pairs — persisting to July–August 2020). §0–§7 are the original diagnostic framework (the reasoning
that led here; the §3 evidence is recorded in `2026-07-02-crash-flags-diagnostic-outcome.md`). **§8
records the resolved outcome and the ratified disposition policy — it is the operative section.***

> **OUTCOME (settled 2026-07-02): Box B — real macro/sector regime, not artifact, not the tech
> thesis.** §3a decisively ruled out box A: on the 7 flagged pairs, residual correlation is
> essentially unchanged under a faster β (pre-specified EWMA hl=63d and 63d rolling β) — 0 of 7
> collapse, max Δ 0.033 — a **second independent confirmation of the β-strip.** §3b shows
> multi-quarter persistence into 2021 with partial 2022 re-firing and near-zero yield correlation — a
> real 2020–2022 Financials/Materials/Real-estate sector regime. Resolution is **Path 1: no sensor
> change, no EWMA swap, no milestone-3 re-run, the +593-day signal untouched.** Test 5c(iii) did not
> fail — it **routed** a real thing to human classification, exactly as designed. Built as read-only
> `beta_diagnostic.py`, never wired into the sensor, with a planted-artifact discriminator test so
> "box A ruled out" cannot silently rot.

## §0–§7 — the diagnostic framework (summary; the reasoning that led to §8)

- **§0 The test worked, not a sensor failure.** 5c(iii) exists to catch a crash manufacturing
  *durable* leads; it flagged candidates for a human instead of silently passing or suppressing them.
- **§1 The reframe (load-bearing).** The tool surfaces real structural change; relevance to the
  emerging-tech thesis is the *human's* filter, not the sensor's. "Precision" here is not "only fires
  on tech theses" — it is "fires on real structural change, and a human decides relevance."
- **§2 Three boxes, not two.** A stale-β artifact / B real macro-cyclical / C real secular shift. The
  owner's 17-year emerging-tech premise separates B from C in *disposition* (a rates-driven Financials
  decoupling is real-but-off-thesis).
- **§3 The cheap diagnostic.** 3a scoped EWMA/short-β slice on just the 7 pairs (collapse ⇒ A); 3b
  two-clock trajectory read (β-window-roll vs rates). Explicitly a diagnostic, not an estimator
  rebuild.
- **§4 The reversion-window question**, judged on its own merits (17-year "transient" = quarters), and
  the HARD RULE: never relax the window to make the flags pass.
- **§5 Guardrails if EWMA sensor-wide** — it is not "small"; it moves every residual including the
  +593 recall signal, requiring a full milestone-3 re-validation; pre-specify the half-life, observe.
- **§6/§7 Sequencing + the two spec-fold paths** — Path 1 (transient/macro, likely) vs Path 2 (clean
  material stale-β artifact). Report the box; the design thread folds the outcome in.

## §8 — Resolved outcome and ratified disposition policy (rev 2)

The diagnostic resolved to **Box B** (see the outcome banner). Path 1: **no sensor change.** What
follows is the ratified handling of the *finding* — how a "real but off-thesis" classification is
captured instead of discarded. A small, principled fold: one enriched verdict vocabulary, one
read-only catalog, one standing rule. It lands with **milestone 5** (verdict CLI + dashboard); the
verdict vocabulary is a CONTRACT item (spec §5/§8c), so it is ratified here before implementation.

### §8.1 — The principle the finding forced

The sensor surfaces real structural change; relevance to the emerging-tech thesis is the human's
filter (§1) — **and "off-thesis" is not "worthless."** "File and move on" conflated *not-a-tech-thesis*
with *not-valuable* and threw information away. A macro/sector regime is **not** common-mode noise to
be stripped like market beta. The **entanglement argument** is load-bearing: the AI-power buildout is
*both* an emerging-tech linkage *and* rate-sensitive infrastructure capex, so regressing the macro
regime out would **amputate real tech signal along with it.** This is an independent, principled
reason the **single-factor β-strip stays and a multi-factor β is wrong here** — not merely
unnecessary, but actively destructive of signal. The regime flips from *discard* to **the reference
frame a future tech signal is read against** — the excess-vs-common-factor logic one level up,
performed in human judgment rather than mechanically.

### §8.2 — The value, located precisely

- **Reference frame.** When a tech linkage fires later, the question is whether it forms *against* the
  prevailing macro regime or merely *rides* it — a decoupling that survives a hostile rate regime is
  stronger evidence than the tide coming in. The macro catalog is that backdrop.
- **Labeled negative set.** "This is what real-but-macro looks like in residual-correlation space"
  sharpens, by contrast, what a real *tech* signal looks like — guarding against mistaking the next
  rates echo for an emerging-tech linkage.
- **Recorded memory.** When a Financials/rates decoupling recurs (say 2027), the fold surfaces "you
  classified this in 2020, verdict: real-macro."
- **Cross-twin context (human-mediated, firewall intact).** The satellites are rate/regime-sensitive
  (nuclear capex, biotech). When the smoke detector later judges whether a NUKZ/XBI drawdown is a
  *thesis break* or a *regime drawdown*, this macro catalog is the context that distinguishes them.
  Read-only, human-mediated; no automated pipe.

### §8.3 — The boundary (the load-bearing discipline)

**[HARD RULE] Context, never a trigger.** The same 17-year emerging-tech premise that makes macro
*off-thesis* also says *do not act on it* — a passive core holds *through* regimes. The tell: the core
is **cap-weighted, so it already absorbs sector-regime shifts automatically.** The correct action on a
detected macro regime is **none** — noticing it (Prospector) and absorbing it (core) never touch. The
overreach — "detect the next regime early and tilt ahead of it" — is the **market-timing trap in a
data-science coat**, precisely what the architecture refuses.

**[HARD RULE] No macro-regime alert stream.** The value is realized **passively**, through richer
recording and human consultation — never a new signal that asks for attention. A regime *alert*
stream / "regime forming" push / monitoring dashboard rebuilds the cockpit and the checking compulsion
the design refuses. Do not build it.

### §8.4 — The fold (three live meanings, not two — the critical implementation note)

The enriched vocabulary has one failure mode that must be designed out. Splitting the overloaded
**"no"** risks a *second* collapse: mixing **off-thesis-but-real** (macro — context, inert) with
**on-thesis-but-unproven** (a candidate tech linkage not yet cleared) would let a deferred real tech
lead rot in a drawer labeled "macro." So the vocabulary preserves **three live meanings**, and
`watch` stays exactly what it was:

| Verdict | Meaning | State | Action |
|---|---|---|---|
| `yes` | promoted — a real, on-thesis lead worth the pipeline | live | enters the per-investment-thread pipeline (human) |
| `watch` | **on-thesis, unproven** — a candidate tech linkage not yet cleared | **live** | stays under observation; **must NOT absorb macro verdicts** |
| `off-thesis-real` *(new)* | **real, but off-thesis** (macro/sector regime) | catalogued, **inert** | recorded as context; no action ever; cap-weighted core absorbs it |
| `noise` *(the old "no")* | not real — artifact/spurious | dead | closed |

The old binary "no" splits into **`noise`** (not real — dead/closed) and **`off-thesis-real`** (real
but off-thesis — catalogued, consultable, inert). **`watch` is untouched.** `off-thesis-real` is *real
and permanently set aside* (the core absorbs it, no action ever); `watch` is *possibly-on-thesis and
still live*. Collapsing them is the failure mode the split exists to prevent.

**Implementation (milestone 5, all read-only, no new machinery):**
1. **Verdict vocabulary** (CONTRACT, §5/§8c): add `off-thesis-real` alongside `yes/watch`, with `no`
   refined to `noise`. Verdicts remain append-only events; a reclassification supersedes, never edits.
2. **Macro catalog:** a forensic query over verdict events filtered to `off-thesis-real` + **one**
   read-only Streamlit panel. Not an alert stream, not a monitoring lane, not a heartbeat action item.
3. **Human-mediated consultation only:** read the catalog when adjudicating elsewhere; no automated
   hand-off; firewall intact.
4. **Standing hard line** (into CLAUDE.md standing-review): the macro catalog is **read-only context,
   never a trade/tilt trigger, never piped anywhere as actionable** — same class of rule as the
   reading-list wall.

### §8.5 — What this does NOT authorize

- **No multi-factor β / no stripping the macro regime out of the sensor** (§8.1 entanglement — it
  would delete real tech signal). Single-factor β-strip stays; a v2 question with its own
  re-validation if ever revisited.
- **No sensor change of any kind** from this finding (Box B, Path 1). The +593 signal and the frozen
  0.85 stress gate are untouched.
- **No macro alerting / monitoring surface** (§8.3).

### §8.6 — Disposition for the implementer

Handling of the 7 flags changes from *"file as not-a-thesis, move on"* to: **classify as
`off-thesis-real`, a recorded, consultable outcome, not a discard.** Implement the §8.4 fold —
three live meanings, `watch` preserved. The classification itself (the 2020 Financials/Materials/
Real-estate regime) is the design thread's recorded verdict; no further estimator work is earned.

**Methodological note worth preserving:** Box A was ruled out by a **pre-specified,
planted-artifact-tested, read-only** discriminator (`beta_diagnostic.py`, never wired into the sensor,
with a synthetic-positive-control regression guard). That is the β-strip's *second independent
confirmation* by a *different mechanism* — the "two independent derivations" standard — and an
instance of the whole method working: a claim made falsifiable, tested against a positive control, and
left with a guard so it cannot silently rot.

---

*Implementation status (2026-07-02): the §8.4 verdict vocabulary is locked in — CLI + fold
`VERDICT_VOCAB`, four values, three live meanings, `no`→`noise`, tests pinning `off-thesis-real` as
inert. The macro-catalog forensic query + Streamlit panel and the formal spec rev6 fold (§5/§8c) land
with milestone 5.*
