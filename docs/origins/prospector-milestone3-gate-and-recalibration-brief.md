# Prospector — Milestone 3 Gate Outcome & Stress-Gate Recalibration Brief

*From the design thread, 2026-07-02. Written for Claude Code to read cold. Records the milestone-3 acceptance outcome, the one authorized recalibration, and the guardrails for milestones 4–7. The recalibration below is a CONTRACT-default change — it is authorized here, from the design thread, per §5 of the spec.*

---

## Verdict

**Go — keep building.** The measure is sound and recall is real. The gate did its job: it proved the instrument works before four more milestones get built on it, and it surfaced exactly one dial to turn. A "no" would have been the process working; this is "yes, and here is the dial."

---

## What the gate confirmed

1. **Recall ✓.** XLK×XLU (Tech×Utilities) fires. The real AI-power / data-center-power linkage forms in residual correlation on **2023-01-25 at z 2.52** — well before it was a market cliché. The sensor sees Tech and Utilities decouple from the market and re-couple to *each other*, which is the structural signature we wanted it to catch.

2. **β-strip ✓ sound — the fork is settled.** The diagnostic run *before* any threshold tuning: mean pairwise residual correlation collapses to ≈0 in **every** window, including the March-2020 crash (raw 0.88 → residual −0.035). Firings do **not** cluster in stress windows (the busiest quarters, 2024 Q1 and 2023 Q3, are calm). Conclusion: the 54/55 pairs crossing the threshold at some point over six years are **genuine idiosyncratic departures, not β leakage.** The market-factor strip is the primary market-factor defense and it works. **The remaining work is gating and surfacing discipline, not the estimator.**

3. **Process integrity (worth recording as a standard).** Adversarial review caught the corroboration matcher letting the 2-char token `ai` match *inside* `retail` / `entertainment`, inflating structural precision from a true 2 to a false 8. It was corrected **down** and reported honestly. A process that finds a bug flattering its own numbers and fixes it against interest is the cite-or-fault standard operating on itself. Short tokens now require a word boundary. The precision numbers below are the corrected, honest ones.

---

## The headline finding: the stress gate ate the real 2023 signal

The sensor saw the 2023-01-25 signal (z 2.52), but raw market stress that day was **0.667** — an ordinary ~78th-percentile day, **not a crisis** — and the 0.65 stress gate suppressed it. So the first *recorded* firing slipped to **2024-11-06**, and the cross-stream lag reads **−58 days**.

**Why this is not a marginal miss — the gate setting inverts the tool's apparent value:**

- **At 0.65:** cross-stream lag = **−58 days**. The tool appears to fire *after* TEKX launched — late, trailing the packagers, useless.
- **Recalibrated so it does not eat the 2023 signal:** the same tool fires **~19 months *before* the ETF exists** — which is the entire thesis (catch the shift while it is still forming, not once someone has wrapped it in a ticker).

One CONTRACT default is the whole difference between "catches the shift a year and a half early" and "trails the ETF by two months." The recalibration is not cosmetic; it is the headline capability being hidden by a placeholder.

---

## The recalibration decision: make the stress gate baseline-relative

### Why the *form* must change (not just the level)

The β-strip result **changed what the stress gate is for.** Before the diagnostic, one could believe the stress gate was a primary defense against market-factor contamination. But the β-strip is now *proven* to remove the market factor cleanly even in the March-2020 crash — so **it**, not the stress gate, is the primary market-factor defense.

That demotes the stress gate to a narrow **secondary, crisis-only** job: catching the two things the β-strip cannot during a genuine crisis —

- **(a) crash-onset β staleness** — the trailing-252d β is estimated pre-crash, so for a short window at the onset the residual carries uncorrected beta (this is the observed Feb-18-2020 leading-edge leak);
- **(b) liquidity-driven dislocations** — fire-sale idiosyncratic moves that look idiosyncratic but are crisis artifacts, not structural.

Both are **acute-crisis phenomena**, not mildly-elevated-correlation phenomena. So the gate should fire **rarely — crises only** — and an ordinary 78th-percentile day like January 2023 should never trip it.

### The formulation (recommended)

**Baseline-relative:** gate on the **departure of market-wide raw correlation from its own trailing norm** (reuse the exact trailing-baseline machinery the residual sensor already has — mean/std of the market-wide correlation level over a trailing window, then a departure z), thresholded to fire only at **genuine-crisis** departure levels.

Rationale for baseline-relative over absolute:
- **Self-calibrates** against multi-year correlation-regime drift — an absolute 0.9 is a magic number that ages as the market's baseline correlation shifts.
- **Reuses existing machinery** — the residual sensor already computes trailing-baseline departures; this is the same operation on the market-wide correlation series.
- **Correct failure behavior** — it fires on acute spikes and correctly *ignores* slow correlation drift and sustained-high regimes. That matters because in a sustained-high-correlation regime, idiosyncratic departures are often the very structural shifts we want to surface; an absolute-0.9 gate would over-suppress those stretches.

**Acceptable simpler fallback:** absolute level lifted to ~**0.9** (reflecting that the structural calm baseline is ~0.5–0.65, so 0.65 was barely above normal). Works, but ages and over-suppresses sustained-high regimes. Prefer baseline-relative since the machinery already exists.

### CRITICAL guardrail — this is a *principled* recalibration, not a *fitted* one

Thresholds are **never auto-tuned.** The recalibration is authorized because the β-strip result gives a *principled* argument for the gate's correct job (crisis-only), **not** because it makes XLK×XLU surface.

- We are **NOT** lowering the threshold until the 2023 signal appears. That would be curve-fitting to a single labeled example (n=1 known shift over 55 pairs).
- The 2023 signal surfacing is a **consequence** of setting the gate to its correct job, not the **objective** of the tuning.
- **Validate the recalibrated gate against the concept, not the known case:** confirm it fires on genuine crises (March-2020 → yes) and stays quiet on ordinary elevated-but-calm days (January 2023 → yes). Do **not** validate by "does XLK×XLU now surface" — that is the curve-fit.
- Set it once, on principle, and **freeze it.** Do not keep adjusting until the numbers look good on the one example. "Tuning it better" must mean "more correctly specified" (baseline-relative, crisis-only), never "better fit to 2023."

---

## Precision — unmeasurable now, by construction (carry this into 4–7)

Precision scored **2 of 98** firings as structural at the default threshold — honest, but **floor-limited and currently unmeasurable**, and the reason matters:

- The corroboration set holds **three** EDGAR-verified launches, **all 2024** (TEKX and siblings). By construction, almost nothing that fired **before mid-2024 can be corroborated yet.** The two that do — XLI×XLRE and XLI×XLK, both bridging TEKX through infrastructure / data-center / technology — are exactly the AI-power cluster.
- **Therefore this backtest proved recall and measure soundness. It did not, and structurally *could* not, prove *surface* precision.**

**Implications for milestones 4–7:**

- The **surfacing gates** — active-lead ceiling, sustain-≥K-weeks, cross-stream corroboration — get set on **principle now** and **validated live later**, as launches accumulate. Do not expect this run to have settled them.
- **The deeper limit (name it and keep it named):** the "packaged = real" scorer makes auto-corroboration a **lagging, incomplete proxy** for structural reality — a genuine shift the market never wraps in a fund scores as *junk*; a fad that gets packaged scores as *real*. That is "reconstructed path, never demonstrated cause" showing up in the precision metric. So the **human verdict stays the ground-truth; the auto-score stays a hint.** **Never optimize the corroboration number — it is a witness, not a judge.**

---

## Next steps & sequencing

1. **Stress-gate recalibration** (design decision, authorized here). Implement baseline-relative (departure-from-trailing-norm on market-wide correlation), or the absolute-~0.9 fallback. Validate against the *concept* (fires on crises, quiet on calm), not the known case. Freeze it.
2. **Milestones 4–7** — remaining sensors (dispersion, launch, rebalance), then outputs (email + dead-man's-switch, read-only Streamlit, verdict CLI), then discourse capture + budget guard, then infra-as-code.
3. **Milestone 3b (dispersion PIT coverage) — deferred, clean next task, do not rush.** It genuinely needs NPORT-P parsing and delisted-constituent data (survivorship-clean point-in-time holdings). Rushing it buys an *uncalibrated* dispersion sensor, which is worse than none. Until it is calibrated, expect dispersion to ship on placeholder thresholds and plan a **live burn-in** (noisy at first).

**Universe note:** the v1 universe is deliberately small — 11 Select Sector SPDRs, 55 pairs, 3 corroborating launches. **Precision being floor-limited is a starting-point property, not a flaw.** As launches accumulate and (v2) universe auto-expansion adds nodes along the holdings graph, the corroboration set grows and surface precision becomes measurable over time. The small universe is where you *begin*, not where you *stay*.

---

## One-line summary for the commit / handoff

Milestone 3 passed: recall real (XLK×XLU forms 2023-01-25), β-strip proven clean (fork settled → work is gating not estimator), one authorized recalibration (stress gate → baseline-relative, crisis-only, principled not fitted), precision unmeasurable until launches accumulate (surfacing gates on principle, corroboration is a witness not a judge). 3b deferred on data availability. Proceed to recalibration, then 4–7.
