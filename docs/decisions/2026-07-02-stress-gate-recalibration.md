# Decision: stress-gate recalibration (2026-07-02)

**Status:** ratified from the design thread (per spec §5, a CONTRACT-default change). This note is
the amendment of record; the canonical spec rev 3 §4a (which describes the original absolute-0.65
form) is left intact as history. A `config.changed` event fires on the config edit, so the record
also carries the machine trace.

## What changed

The market-stress gate changed from **absolute level 0.65** to **absolute level 0.85** — a lift, not
a form change. The design thread's *first-choice* form was baseline-relative (a departure of
market-wide correlation from its own trailing norm); it was **tested across level/baseline windows
and rejected on evidence** (below). Config: `xcorr.stress_corr_threshold: 0.65` →
`xcorr.stress: {level_window: 21, crisis_level: 0.85}`.

## Why the gate's job is now narrow (the licensing result)

The milestone-3 β-strip diagnostic proved the market-factor strip removes the market factor cleanly
even in the March-2020 crash (residual mean pairwise correlation **−0.035**). So the **β-strip, not
the stress gate, is the primary market-factor defense.** That demotes the stress gate to a
secondary, **acute-crisis-only** job: catch the two things the strip cannot during an acute crisis —
(a) crash-onset β staleness (the trailing-252d β is estimated pre-crash, so residuals carry
uncorrected beta for a short onset window), and (b) liquidity fire-sale dislocations. The old 0.65
was miscalibrated for this narrow job: it gated **24.8% of days**, because sector ETFs sit at a calm
baseline ~0.5–0.65, and it suppressed the real XLK×XLU signal on 2023-01-25 (an ordinary
~78th-percentile day at level 0.667).

## Why absolute, not baseline-relative — the durable reason (the scale distinction)

Baseline-relative (departure-from-own-norm) is the correct frame for a **scale-free** statistic —
one with no intrinsically meaningful level, where "how far from normal" is the only interpretable
question. That is exactly the pair residual correlation (there is no universal "correct" residual
correlation for XLK×XLU, so only its *change* means anything — departure-z is right there, and the
sensor uses it).

Market-wide mean pairwise correlation is the **opposite kind of object: a fragility gauge with an
intrinsic scale.** A market at 0.95 average sector correlation is one where diversification has
collapsed and everything moves as one — a stressed market, full stop, whether or not it was 0.95
last month. The *level* carries the meaning. Normalizing by the trailing norm destroys exactly the
quantity that is the signal.

The empirical failure is precisely what applying a change-detector to a level-signal must produce,
and it was **uniform across every construction tested** (level windows 5/10/15 × baselines
63/126/252), which is the tell that it is structural, not a tuning miss:
- **Range compresses.** The gauge is smooth and mean-reverting, so its own trailing variance swamps
  even COVID's excursion — the whole departure-z distribution caps at ~2.5σ, so a principled
  "3σ crisis" threshold is unreachable.
- **Monotonicity with severity breaks.** A small wobble off a calm baseline out-z's a real crisis
  off an elevated one, so COVID is *never* a clean outlier — the largest departures land on
  non-crisis days (a Dec-2024 wobble, the Aug-2019 scare).

The absolute level, by contrast, preserves crisis severity ordering (COVID 0.95 > Aug-2019 0.88 >
2022 grind 0.82 > calm 0.69; calm p95 ~0.81) and cleanly isolates the acute crisis.

Two corroborations: (1) this is the **absorption-ratio / correlation-concentration family**
(Kritzman–Li) — systemic-risk practitioners use correlation-concentration as absolute levels or
percentiles, never trailing-normalized, for exactly this reason. (2) In the project's own
vocabulary, "correlations rush to one" is a high-endogeneity, self-exciting cascade — the
absolute-correlation gate is a crude reflexivity detector, and reflexive panic is the regime where
β-staleness and liquidity dislocations live. The level being the meaning is not a quirk of this
series; it is that the series measures the thing the gate exists to catch.

## Why 0.85 specifically (onset latency is the binding constraint)

The gate exists for one acute thing (crash-onset β staleness), which makes **onset latency
load-bearing**. That kills the alternatives:
- **0.90** (the brief's first number) rises ~10 trading days into the crash — it partly misses the
  onset window it was retained to cover.
- **0.80** gates the 2022 slow-bear grind — a *sustained* regime, not an acute crisis. Over-gating
  sustained-high stretches blinds the tool exactly when idiosyncratic departures are
  disproportionately the structural shifts we want surfaced. That is the whole reason for the
  crisis-only demotion.
- **0.85** matches the gate to its job: ~5-day onset latency, fires on COVID and the genuinely-acute
  Aug-2019 scare, sits just above calm p95 (0.81) with the 2022 grind (0.82) correctly below, gates
  only 2.7% of days.

**Principled, not fitted.** The choice was made on the *crisis side* (top ~2–3% of days = genuinely
extreme comovement; onset-latency for the β-staleness job), validated against the concept (fires on
recognized crises, quiet on ordinary calm days), and **frozen** — never lowered until a known signal
appears. The recall-independence check is the guardrail: XLK×XLU on 2023-01-25 (level 0.667) is
ungated at 0.80 / 0.85 / 0.90 alike, so the recall un-gating is a *consequence* of setting the gate
to its correct job, not the *objective* of the tuning.

## Observed (not targeted) result

With the gate at its correct job, the deterministic cross-stream lag **flipped from −58 days to
+593 days**: XLK×XLU now fires 2023-01-25, ~19.5 months *before* TEKX launched (2024-09-09). That is
the thesis — catch the structure while it is still forming, not once someone has wrapped it in a
ticker. It is an observation read *after* freezing, never a tuning target.

## Two named characteristics (recorded so no one is surprised)

1. **Onset latency (~5 trading days).** The level input is a 21d rolling correlation, so it lags a
   crash by a few days; a departure at the very leading edge slips through before the level rises —
   a bounded leading-edge leak. Losing paging in a crash week is free (§4a). The latency lever is
   the level window, not the threshold.
2. **Crisis-duration, not transient.** An absolute gate stays on for as long as correlation is
   extreme (correct for an acute crisis). The watch-item is a *prolonged* extreme-correlation regime
   that could over-suppress the idiosyncratic departures we want — none occurred in 2019–2024.

## Standing watch-item: aging (the one real weakness of an absolute level)

Absolute levels age. Over the 17-year horizon, secular ETF-driven co-movement could lift the calm
baseline toward 0.85. **Monitor:** the backtest reports the recent-window calm p95 and its headroom
to the gate each run (currently p95 0.668 → gate 0.85, headroom **0.18** — healthy). If the margin
compresses, **deliberately re-freeze the level higher (a human decision).**

**Hard rule:** do NOT solve aging with a rolling percentile or any self-updating window — that is
baseline-relative in disguise and reintroduces the exact failure diagnosed above (crisis days and
sustained regimes inflate the trailing percentile). The correct pattern is frozen-absolute + periodic
*human* recalibration: the machine surfaces the drift, the human moves the level — the same
machine-proposes-human-ratifies discipline as everything else in the system.

## OPEN — for the design thread: spec test 5c ("zero crash-window spawns")

The recalibration surfaces a CONTRACT tension. **Spec §10 test 5c asserts zero new leads spawned in
the March-2020 window.** That criterion was written when the stress gate was conceived as the crash
defense (gate everything during a crash → zero spawns). The β-strip proof reassigned the crash
defense to the β-strip and demoted the gate to acute-onset-only, so the recalibrated gate correctly
no longer over-suppresses — and the window now shows **10 spawns** (7 in the [onset, gate-rises)
β-staleness window, 1 pre-onset, 2 recovery-tail).

The β-strip is proven clean in-crash (−0.035), so departures that survive it during the crash are
**genuine idiosyncratic moves** (e.g. Financials×Utilities decoupling as rates collapsed), not beta
artifacts. Forcing them to zero would mean re-inflating the gate to the 24.8%-of-days over-gating we
just removed.

**Recommendation (not yet applied):** amend test 5c from *"zero crash-window spawns"* to
*"(i) the β-strip keeps residual mean correlation ≈0 through the crash (holds: −0.035), AND (ii) the
gate fires on the acute crisis (holds: COVID, onset lag 5d)."* Separately, weigh whether to shorten
the level window to shrink the ~5-day onset leak (trades onset speed for level noise). **Do NOT
re-tighten the crisis level to pass the old test — that undoes this ratified recalibration.**
