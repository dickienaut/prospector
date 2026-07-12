# Technical briefing — fact-check against the primary source (2026-07-12)

*A claim-by-claim review of the external technical briefing
(`prospector-technical-briefing-2026-07.md`, "As of July 2026") intended for a hedge-fund quant. Each
claim was checked against the repository (`main`, 2026-07-12) — the code, the spec (rev14), the
state-of-project doc (rev7), and the decision records. Purpose: catch anything oversold or numerically
wrong **before** it reaches a rigorous reader, and cite the primary source for each so the findings can be
merged with a parallel review. Severity = how likely a quant is to catch it and how much it would cost
credibility.*

---

## Verdict

The briefing's **honesty framework is accurate and is its greatest strength**: the Known / Thought /
Unknown split, "n = 1 / existence proof, not a rate," "false-discovery rate unmeasured," and flow-vs-
structure as the central adversarial question all match the primary source faithfully. Preserve that tone —
it is exactly what earns a quant's trust.

**However, three technical claims describe methods the system does not actually implement, one figure has
the wrong unit, and one falsifier claim is oversimplified.** These are the specifics a quant probes first;
if asked "show me the Marchenko–Pastur cleaning" or "show me the null-model test," the honest answer is
"not implemented / it's a future layer." Fix all five before sending.

---

## Numbers verified

| Claim in briefing | Verdict | Primary source |
|---|---|---|
| Departure **z-score = 2.52** at structural formation (XLK×XLU, 2023-01-25) | ✅ **Accurate** | spec rev14 (Milestone-3 verdict line); state-of-project rev7 |
| **+593** lead ahead of consensus | ⚠️ **Number real, unit wrong** — it is **calendar days (~19 months)**, *not* "trading days" | `launch_lag` returns a `timedelta` between dates (`identity/resolution.py`); TEKX holdings fixture dated **2024-09-10** vs formation **2023-01-25** ≈ 593 **calendar** days. Every spec/state doc phrases it "~19 months." 593 *trading* days ≈ 2.7 yr → would imply a mid-2025 launch (false). |
| "live, real detections; six active xcorr leads; a real dispersion fracture in shadow burn-in" | ✅ **Accurate** (actually **two** fractures — XLI at z≈4.0, XLP fading — both in 0/90 burn-in) | state-of-project rev7 ("Two live spawners, both producing real data") |
| Market-strip "validated against real data" (residual ≈ −0.035 in March 2020) | ✅ **Accurate** | spec rev14 (β-strip clean, 0.88 → −0.035); ARCHITECTURE §4 |

---

## Findings — ranked

### 1. (HIGH) "correlation matrix cleaned via random-matrix theory (Marchenko–Pastur)" — not implemented

The dispersion detector does a plain eigendecomposition (`np.linalg.eigh`): the leading eigenvector is the
common sector factor, and the **sign of the second eigenvector** splits the basket into two blocks
(`sensors/dispersion.py`, `spectral_bipartition`), tracked by a modularity-style score Q. There is **no
Marchenko–Pastur bulk threshold, no eigenvalue clipping, no denoising** anywhere in the code — "RMT /
Marchenko–Pastur" appears only in a **v2-deferred research-grounding note**, never in the sensor. The
sensor docstring explicitly says "do not reach for a spectral-clustering library or a fancy graph cut."

**Why it matters:** RMT/MP cleaning is a specific, checkable technique; a quant will look for it and it
won't be there.

**Suggested reword:** "eigendecomposition of the constituent correlation matrix — the second eigenvector's
sign partitions the basket into two sub-blocks, tracked by a modularity-style score Q. (RMT / Marchenko–
Pastur denoising is planned for the calibrated layer, not the current sensor.)"

### 2. (HIGH) "Null-model validation … reshuffled and random-matrix baselines" — not implemented

No permutation / reshuffle / surrogate / bootstrap / null-model code exists (`grep` clean across
`prospector/`). The backtest's four sections are **recall, precision, March-2020 falsification, and
β-strip / stress diagnostics** (`backtest/report.py`) — none is a reshuffled or random-matrix null model.
What the system *does* have is the **departure z-score** (a deviation from each pair's own trailing
correlation baseline) — a baseline comparison, but not a null-model permutation test. Null-model /
permutation significance is described in the **v2 proto-cluster idea notes** as "standard practice" the
future layer would adopt — i.e., planned, not built.

**Suggested reword (or drop the bullet):** "Detections are departure z-scores — deviations from each pair's
own trailing baseline, not raw correlation levels, so the threshold measures 'unusual for this pair,' not
'high.' Formal null-model / permutation significance against reshuffled and random-matrix baselines is a
planned validation step, not yet implemented."

### 3. (MEDIUM) "Pre-registered falsifiers … have been tested and held" — oversimplified

In the March-2020 stress test, **two of three criteria held cleanly** (the market-strip stayed clean
through the crash; the stress-gate fired only on the acute window). The third — *every crash-window
detection reverts within 8 weeks* — **fired: 7 of 10 crash-window detections persisted.** A pre-committed,
read-only diagnostic then classified those as a genuine **2020–2022 macro/sector regime** (and independently
ruled out a stale-β cause — the β-strip's second confirmation), so they were dispositioned "real but
off-thesis," leaving the +593 signal untouched (spec rev14 §10.5c, "Box B, Path 1").

That is a **routed classification, not a clean pass.** Stated precisely it is arguably *more* impressive
(the falsifier flagged a real phenomenon and the system adjudicated it correctly) — but "tested and held"
glosses the 7/10, and a quant who later sees it may feel the doc smoothed it over.

**Suggested reword:** state the outcome plainly — "In the March-2020 test, two criteria held; the third
(all crash-window detections revert within 8 weeks) fired — 7 of 10 persisted. A pre-committed read-only
diagnostic classified these as a real 2020–2022 macro/sector regime rather than a sensor artifact, so they
were dispositioned 'real but off-thesis.' The falsifier worked as intended (it flagged a real thing for
adjudication); this is a routed classification, not a clean pass."

### 4. (LOW–MEDIUM) "partial-correlation market-stripping" — imprecise

The implementation is **single-factor β-residualization**: regress each fund's returns on SPY, take the
residuals, correlate the residuals (`sensors/xcorr.py`). That equals partial correlation *with respect to
the single market factor* — **not** a full partial-correlation matrix controlling for all other assets.
Defensible shorthand, but a quant may expect more from the unqualified term.

**Suggested reword:** "single-factor market-beta residualization (partial correlation with respect to the
market factor)."

### 5. (LOW) "an architectural wall that makes an execution path impossible" — overstated

It is a firewall **discipline** — no code path reads the portfolio or places / sizes / recommends a trade —
enforced by convention plus a firewall test. Robust, but "impossible" overstates.

**Suggested reword:** "an architectural firewall (no code path reads the portfolio or places / sizes /
recommends a trade), enforced by a firewall test." Still strong, and accurate.

### Minor

- "community detection" is technically a **2-way spectral cut plus a Q metric** — fine as shorthand, but it
  is not Louvain / modularity-maximization if a reader asks.
- The sentence "flagged … 593 [days] ahead of consensus, at a z-score of 2.52" correctly pairs two facts
  from the *same* formation event (the departure crossed the z≈2.5 trigger at z 2.52 on 2023-01-25, which
  was ~593 calendar days before the TEKX launch) — so once "trading" → "calendar," the sentence is sound.

---

## What is accurate — do not touch

- The entire **Known / Thought / Unknown** structure and the honest-limits framing (n = 1, existence proof
  not a rate, FDR unmeasured, no forward out-of-sample validation, flow-vs-structure unresolved).
- **z = 2.52**, live/real detections, six active xcorr leads, a real dispersion fracture in shadow burn-in,
  the market-strip validated on real data.
- The launch-as-consensus-clock operationalization and the research-only / no-execution posture (modulo the
  "impossible" wording in finding 5).
- The proposed validation backtest (PIT reconstruction, survivorship controls, structure-vs-flow test) —
  consistent with the deferred §3b work.

---

## One-line summary for merging with the parallel review

Keep the honesty; fix five things: **(1) drop the Marchenko–Pastur/RMT "cleaning" claim, (2) drop or
rescope the null-model "reshuffled/random-matrix" claim, (3) "593 trading days" → "~593 calendar days
(~19 months)", (4) state the March-2020 falsifier as a routed classification (7/10 persisted → classified
real-off-thesis), not a clean pass, (5) qualify "partial correlation" and soften "makes execution
impossible."** Claims 1 and 2 are the priority — they describe techniques the code does not contain.
