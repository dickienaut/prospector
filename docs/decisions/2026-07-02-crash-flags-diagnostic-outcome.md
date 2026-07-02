# Diagnostic outcome: the 7 persistent crash-window flags are box B (real macro/sector)

**Status:** diagnostic report to the design thread (per the guidance doc
`prospector-crash-flags-diagnostic-guidance-2026-07-02.md` §7). Classifies the flags and recommends
the disposition; the spec fold itself is the design thread's. Nothing here changed the sensor or any
CONTRACT. Reproducible via `prospector/backtest/beta_diagnostic.py` (a read-only diagnostic, never
wired into the sensor) over the frozen 2026-07-02 price + `^TNX` pull.

## The finding

Rev5 test 5c(iii) flagged 7 of 10 March-2020 crash-window spawns as persistent (Financials-heavy).
The diagnostic classifies them **box B — real macro/sector regime, not an artifact, not the
emerging-tech thesis.**

**§3a — scoped EWMA/short-β slice (the decisive test). Box A (stale-β) ruled out.** On the 7 flagged
pairs, over the persistence window (2020-03..08), the residual correlation is **essentially unchanged
under a faster β** — EWMA half-life 63d and a 63d rolling β, both pre-specified on principle, not
tuned. Max Δ **−0.033**; **0 of 7 collapse.** A stale-β artifact would collapse under a faster β (the
discriminator is validated on a planted artifact in `tests/test_beta_diagnostic.py`); these do not.
So the decoupling is genuinely in the residuals.

| pair | prod-β corr | EWMA-β | short-β | Δmax | collapses |
|---|---:|---:|---:|---:|:---:|
| XLF×XLP | −0.138 | −0.149 | −0.158 | 0.021 | no |
| XLB×XLRE | 0.253 | 0.251 | 0.248 | 0.005 | no |
| XLF×XLRE | 0.290 | 0.273 | 0.263 | 0.027 | no |
| XLF×XLU | 0.004 | −0.029 | −0.047 | 0.050 | no |
| XLI×XLV | −0.208 | −0.208 | −0.210 | 0.002 | no |
| XLI×XLRE | 0.263 | 0.265 | 0.266 | 0.003 | no |
| XLB×XLF | 0.461 | 0.457 | 0.458 | 0.003 | no |

**This is the second independent confirmation of the β-strip** — first on the March-2020 aggregate
(residual mean corr −0.035), now on a faster-β stress test of the specific persistent pairs. It
resolves the guidance doc's EWMA question cleanly to **Path 1 (no sensor change), not Path 2**: there
is no artifact to fix, so no sensor-wide EWMA and no milestone-3 re-validation. The +593-day recall
signal is untouched.

**§3b — two-clock trajectory read.** The departures **persisted/recurred into 2021** (not a
β-window-roll fade — |z| stayed elevated, e.g. XLB×XLRE 3.62 in 2021) and **partially re-fired in
2022** (4 of 7 crossed 2.5 again in the rates-spike year). The residual-correlation↔10Y-yield
correlation is near zero (−0.16..+0.24), so it is **not a clean single-driver rates story** — but it
is unambiguously a **real, multi-quarter, Financials/Materials/Real-estate-heavy 2020–2022 sector
regime** (COVID → reopening → inflation/rates), not a two-week crash blip and not a secular
tech shift.

**Test 5c(iii) did not fail — it worked.** It is a router to human adjudication: it neither passed
nor suppressed the persistent spawns, it *flagged* them for classification, and the classification
came back "real, box B." The router fired correctly on its first live crash.

## Disposition: "not a tech thesis" ≠ "not valuable"

The earlier instinct ("file as not-a-thesis, move on") conflated two different claims. A macro/sector
regime is **off-thesis but not noise**, and the reason is the same reason it is valuable:

- **It cannot be stripped away like the market factor.** Market beta is pure common-mode — everything
  carries it, it holds no thesis, so the β-strip removes it mechanically and safely. A macro regime
  is **entangled with real theses**: the AI-power buildout is *both* an emerging-tech linkage *and*
  rate-sensitive infrastructure capex. Regress the rates regime out and you amputate real tech signal
  with it. So the single-factor β-strip **stays**; the regime is **catalogued, not removed.** (A
  multi-factor β is explicitly *not* warranted here — it would delete real signal; a v2 question with
  its own re-validation if ever, never a quiet tweak.)
- **The regime is the reference frame a future tech signal is read against.** When a tech linkage
  fires later, what matters is whether it forms *against* the prevailing macro regime or merely
  *rides* it — a decoupling that survives a hostile rate regime is stronger evidence than the tide
  coming in. This is the excess-vs-common-factor logic one level up: the market factor stripped
  mechanically, the macro regime stripped *in human judgment* against the recorded backdrop.
- **It is a labeled negative set** — "this is what real-but-macro looks like in residual-correlation
  space" — which sharpens what a real *tech* signal looks like by contrast, so the next rates echo is
  not mistaken for an emerging-tech linkage.
- **It is recorded memory** — when a Financials/rates decoupling recurs in 2027, the fold surfaces
  "you classified this in 2020, verdict: real-macro."
- **It is cross-twin context** (human-mediated, read-only, firewall intact) — the satellites are
  regime-sensitive, so when the thesis smoke detector later judges whether a NUKZ/XBI drawdown is a
  *thesis break* or a *regime drawdown*, this macro catalog is the context that distinguishes them.
  The owner is the integration point, consulting both records in judgment; no automated pipe.

## The boundary (from the premise, doing double duty)

The 17-year emerging-tech horizon says macro is off-thesis **and** the same horizon says *don't act
on it* — a passive, **cap-weighted** core already absorbs sector regime shifts automatically (as
sectors grow and shrink, the index reweights with no action). So the correct action on a detected
macro regime is **none**, and that is the structure working, not neglect. The Prospector *notices*
the regime; the core *absorbs* it; the two never touch. **Valuable-as-context, never
valuable-as-trigger** — "detect the macro regime early and tilt ahead of it" is the market-timing
trap in a data-science coat, the one thing the architecture exists to refuse.

## Recommended fold (design thread's to ratify — not implemented in this pass)

Small, almost all recording, no new action:

1. **Enrich the verdict vocabulary.** Today it is yes/no/watch, and "no" is overloaded — it cannot
   distinguish "junk/artifact" from "real, but off-thesis." Add a disposition
   **"real — off-thesis (macro/sector regime)"** distinct from "noise." That one addition stops the
   information being thrown away and makes the record honest about *why* something was set aside.
   (Touches the verdict values in spec §5/§8c and the fold/CLI — a CONTRACT change, hence a design
   thread rev-N, not a unilateral edit.)
2. **A read-only macro catalog.** Mechanically nothing new — a forensic query over verdict events
   filtered to that disposition, plus one Streamlit panel (M5). A labeled reference layer, **not** an
   alert stream, **not** a monitoring lane.
3. **Human-mediated consultation only.** Read the catalog when adjudicating elsewhere (a future tech
   signal's backdrop, or a satellite drawdown in the detector). No automated hand-off; the owner
   integrates in judgment. Firewall intact.
4. **Standing hard line:** the catalog is read-only context, **never** a trade/tilt trigger, never
   piped anywhere as actionable — same class of rule as the reading-list wall.

**Resist** (the natural overreach, a real risk): letting this grow into a macro-regime *alert*
stream, a "regime forming" push, or a monitoring dashboard. That reintroduces the cockpit and the
checking compulsion the whole design refuses, and is how a tech-frontier tool quietly becomes a
general macro-monitor. The value is realized *passively*, through richer recording and human
consultation, never through a new signal that asks for attention.

## On the reversion window (§4 of the guidance doc)

Keep **`crash_revert_weeks: 8`.** The diagnostic shows the flags are *real* multi-month regimes that
*should* be flagged for human classification — the router working. Widening the window to make them
"pass" as transient would let real structure slip through unflagged; the guidance §4 HARD RULE (do
not relax the window to make the flags pass) cuts toward keeping 8 once the box is known. Decided on
its own merits, not to fit the 7.

## Next

The box is reported. The spec fold (verdict-vocabulary disposition + read-only catalog + the
context-not-trigger rule; single-factor β retained) is the design thread's, per §7. No estimator
work, no M3 re-run. The path clears to milestones 4–7 (3b/dispersion PIT still deferred on data);
the verdict-vocabulary enrichment naturally lands with milestone 5 (verdict CLI + dashboard).
