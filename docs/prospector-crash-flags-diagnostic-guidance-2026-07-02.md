# Prospector — Resolving the 7 Persistent Crash-Window Flags

### Design-thread guidance for Claude Code, 2026-07-02

*Responds to the milestone-3 rev5 outcome: acceptance test 5c(iii) flagged 7 of 10 March-2020 crash-window spawns as persistent (Financials-heavy — XLF×XLU, XLF×XLRE, XLF×XLP, XLB×XLF, XLI/XLB pairs — persisting to July–August 2020). This is a **diagnostic plan and decision framework**, not yet a spec amendment. The spec fold follows once the diagnostic resolves which box the flags land in (§7). Nothing here changes the ratified stress-gate recalibration or any committed code.*

---

## §0 — Status: the test worked. This is not a sensor failure.

Rev5's test 5c(iii) exists to catch a crash manufacturing *durable* leads, and it did precisely its job: it caught candidates and **flagged them for a human instead of silently passing them or silently suppressing them.** The falsifier earned its keep on its first live crash. So the honest frame before any "fix": nothing is broken. A well-built test surfaced an ambiguity for adjudication, which is what it is for. Do not treat the 7 flags as a defect to be made to disappear — treat them as a question to be answered.

---

## §1 — The reframe (the load-bearing principle)

**[PRINCIPLE] The tool surfaces real structural change; relevance to the emerging-tech thesis is the *human's* filter, not the sensor's.**

The value the 7 flags demonstrate is not a bug and not even a near-miss: it is that the sensor surfaces *real things*, even when they are not the *particular* real things the owner is hunting. A crash-coincident Financials decoupling that turns out to be a genuine 2020 rates-to-zero regime shift is a **real structural event the sensor correctly saw** — and the correct disposition, given the owner's mandate (17+ year horizon, exposure to emerging technologies, in the belief this is a time of great technological change), is a human verdict of *"real — but macro, not a tech thesis,"* recorded in the fossil record, and move on.

This clarifies what "precision" even means for this tool. It is **not** "only fires on tech theses." It is "fires on real structural change, and a human decides relevance." Surfacing-real + human-filters-relevance is the design working as intended. A tool that only ever fired on the operator's pre-existing interests would be the novelty≠interest failure — a confirmation-bias engine. The Financials flag is evidence the sensor is *not* that.

---

## §2 — The three boxes (not two)

Claude Code's write-up framed the fork as real-vs-artifact. There are **three** candidate explanations, and the third box is probably where these land:

| Hypothesis | Discriminating signature (mostly in the M3 data already produced) | What it means for Prospector | Action if true |
|---|---|---|---|
| **A. Stale-β artifact** | residual corr reverts roughly as the trailing-252d β window rolls past the crash (~by early 2021); **collapses under a faster β** | the estimator has a real regime-break weakness — matters, it's the sensor everything sits on | fix at source: EWMA / shorter β, **sensor-wide and fully re-validated** (§5) |
| **B. Real macro-cyclical (rates)** | tracks the yield path; persists while rates sit at zero (through 2021) and **re-couples when rates spike (2022)**; does *not* collapse under faster β | genuine decoupling, but a *rates regime*, not an emerging-tech secular shift — **not the thing being hunted** | no estimator fix; human verdict files it *"real, not our target"*; proceed |
| **C. Real secular shift** | persists indefinitely; eventually corroborated by a launch / rebalance | a genuine lead of the kind the tool exists for | tool worked; human examines (but rates-driven Financials is almost certainly not this) |

**[PRINCIPLE] The owner's premise is the criterion that separates B from C in *disposition*.** A 17-year horizon aimed at emerging technology means a rates-to-zero NIM-collapse decoupling is *real-but-irrelevant* — a macro cycle that reverted when rates came back in 2022, not a secular technological realignment. So even in the "real" case, the correct outcome is a human *"no — real macro, not a tech thesis,"* recorded, and proceed. "Real" does not mean the tool struck gold; it means the tool correctly saw a real thing that isn't what it's for, and the human filter handled it as designed (§1).

Note that A and B/C are **not mutually exclusive** — a real rates decoupling can be *amplified* by stale-β leak. The diagnostic below is designed to weigh their relative contribution, not to force a single label.

---

## §3 — The cheap, decisive diagnostic (smaller than "build EWMA-β")

**Do not rebuild the estimator to find out which box.** Two reads, both cheap, settle it without touching the sensor:

**3a. Scoped EWMA-β slice.** Run EWMA-β (or a shorter-window β) on **just the 7 flagged pairs, over the crash window, as a diagnostic slice** — not a sensor swap, not a re-run of the universe. If their residual correlation **collapses** under the faster β → box A (stale-β artifact) is the dominant driver. If it **does not** → the decoupling is real (B or C). Seven pairs, one window, no gate re-validation.

**3b. Two-clock trajectory read (free — uses M3 output already produced through 2024).** Look at the actual reversion trajectory of the 7 flagged spawns against two clocks:
- **β-window-roll clock:** did they fade as the trailing-252d β absorbed post-crash data (i.e., revert ~by early 2021)? → points to A.
- **Rates clock:** did they track the yield path and **re-couple in 2022** when rates spiked? → points to B (real macro-cyclical).

3a + 3b together classify the box definitively. Timebox this; it is a diagnostic, explicitly **not** an estimator project.

---

## §4 — The reversion-window question (principled, and *separate* from the box)

A reframe the data already hints at, and it cuts toward "proceed": the 7 spawns persisted *to July–August 2020* — i.e., they **reverted in ~5 months.** On a 17-year-horizon instrument, a 5-month decoupling is **unambiguously transient** — roughly 0.2% of the holding period.

Which raises a fair, principled question *independent* of the artifact/real fork: **is 8 weeks even the right "transient" threshold?** The reversion window's job (test 5c(iii)) is to separate crisis phenomena from *durable* leads, and "durable" on this horizon means **years, not two months**; major crisis recoveries routinely take one-to-two quarters. So `crash_revert_weeks: 8` may simply be a round number set too tight, and **~13–26 weeks** might be the principled value.

**[HARD RULE — the exact trap this project keeps avoiding] Do NOT relax the window to make these 7 flags pass.** That is curve-fitting the *test* to the result — the twin of tuning the gate to surface the 2023 signal. Settle the window on its **own merits** (what counts as "transient" on a 17-year horizon?), *separately* from the box question, and only ever as a principled choice you would defend without knowing what the 7 flags did. Relaxing the window is **not** a substitute for knowing *why* they persist — §3 still has to run regardless of where the window lands.

---

## §5 — Guardrails if the diagnostic sends you toward EWMA sensor-wide

**[PRINCIPLE] Sensor-wide EWMA-β is not "small," and it is not a refinement.** Swapping the β estimator changes **every residual on every pair over the entire history** — including the XLK×XLU 2023 firing and the **+593-day lead that is the core recall validation.** Therefore:

- Adopting EWMA sensor-wide requires **re-running the full milestone-3 gate and re-confirming the 2023 signal survives** (recall, precision, and the March-2020 falsification). It is a milestone-3 **re-validation**, not a tweak. Worth doing *if* box A is real and material — but it must clear its own bar, and "fixing a rare crash edge-case at the cost of shifting the core signal" is a bad trade you want explicitly ruled out.
- **Same anti-fitting discipline as the gate:** pre-specify the EWMA half-life **on principle** (it is the standard estimator for regime breaks), then **observe** what happens to the 7 flags *and* the 2023 signal — never tune the half-life until XLF reverts. The half-life is chosen for its statistical rationale, and the flag behavior is a readout, not a target.

---

## §6 — Recommendation and sequencing

**Run the scoped 7-pair EWMA diagnostic (§3a) plus the existing-data two-clock trajectory read (§3b) — timeboxed, explicitly a diagnostic and not an estimator project — because it is cheap and it interrogates the sensor everything downstream is built on.**

Prior (to be confirmed by the data, not asserted): the flags are **transient on this timescale** (they reverted in ~5 months) and **at least partly** the estimator's known regime-break lag. If so:
1. Characterize it as a **named limitation** (draft text in §7), not a defect.
2. Consider re-setting `crash_revert_weeks` on principle (§4) — decided on its own merits, not to pass the 7.
3. **Proceed to milestones 4–7.** Hold sensor-wide EWMA-β as a **future robustness item**, not a milestone-3 blocker.

Only if the scoped EWMA (§3a) shows a **clean, large artifact collapse** does sensor-wide EWMA-β earn its full-re-validation slot *ahead of* 4–7.

**[HARD RULE] Do not let this become the milestone that never ships.** The core question milestone 3 asked — *does the instrument see structure form?* — is **answered: yes** (XLK×XLU, 2023-01-25, +593-day lead, recall-independent of the gate level). The 7 flags are a **characterized onset edge-case, not a repudiation.** Run the cheap diagnostic so you *know* what they are, write the answer down, and do not let a 5-month crash artifact hold the other four milestones hostage.

---

## §7 — What to report back, and the two spec-fold paths

Report to the design thread **which box the flags landed in** (A / B / C, with the §3a collapse result and the §3b trajectory reads). Then the spec fold takes one of two forms:

**Path 1 — transient / macro (likely).** Fold a **known-limitation note** into §4a of the spec, roughly:
> *Known limitation (excess-corr sensor): at crisis onset the trailing-252d β is stale for a period after a regime break, so a subset of pairs (observed 2020: Financials-heavy) produce multi-month residual-correlation decouplings. These revert within ~2 quarters and are filtered by (a) test 5c(iii)'s reversion window and (b) the human verdict, which files real-but-macro decouplings as "not a tech thesis." Sensor-wide EWMA-β is the source-level fix, held as a future robustness item pending a milestone-3 re-validation.*

Plus, if §4 is settled on its merits, a principled update to `backtest.crash_revert_weeks`.

**Path 2 — clean, material stale-β artifact.** Then sensor-wide EWMA-β earns a **properly re-validated estimator amendment**: pre-specified half-life, full milestone-3 re-run, the 2023 signal re-confirmed to survive, all recorded — a rev-N spec change, ahead of 4–7.

Either way: examining the flagged leads (real shift vs macro vs artifact) is the design-thread read; the β-estimator work is the candidate next pass **only** if the diagnostic says it's earned. Tell me the box and I'll fold the outcome in.
