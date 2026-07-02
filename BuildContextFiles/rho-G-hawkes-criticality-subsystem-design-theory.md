# ρ(G) / Hawkes Criticality Subsystem — Design Theory & Future Build Spec

**Project:** Thesis Smoke Detector → Criticality Subsystem (Bank A gauge + Bank D fusion input)
**Document type:** Design-ahead capture. Theory to be proven or disproven via point-in-time backtest. **Not yet built.**
**Phase:** 5+ — *after* B/C/D integration. This is deliberately sequenced behind the working core (per `CLAUDE.md`: "do not build ahead of need; prefer a working Phase 1 over a half-built Phase 5").
**Status:** Living document. Append as the design matures. Nothing here is committed until the PIT data layer exists and the validation backtest has run.

---

## 0. How to read this

This subsystem adds one idea to the detector: a **branching-ratio gauge, ρ(G)**, that measures how much of current market activity is the system *reacting to itself* (endogenous) versus *to outside news* (exogenous). It is the quantitative form of the theme the whole thesis circles — reflexivity (Soros), endogeneity (Filimonov–Sornette), approach to self-organized criticality (Bak), "the calm is the loading." It feeds the **master caution light (Bank D / OOD)** as the *temporal* criticality lens, paired with the absorption ratio as the *contemporaneous* lens.

**Epistemic frame.** Three kinds of claim live here, and they must not be confused:

- **[PRINCIPLE]** — follows from the system's own logic; high confidence; would only change if the design philosophy changed.
- **[DECISION]** — a deliberate engineering choice with a stated tradeoff; revisable, but the rationale is the point.
- **[HYPOTHESIS]** — an empirical claim the PIT backtest must *establish*; currently unproven; **do not hardcode the version you'd like.**

The load-bearing hypothesis of the entire subsystem: *that ρ(G) carries useful information about fragility before it shows up in level gauges.* Everything else is scaffolding around testing that. If the backtest disproves it, the subsystem is a coincident confirmer at best — still mildly useful, but not the early-warning lens this document hopes for. **That outcome is acceptable and must be reportable.** The smoke alarm earns its keep even at "51% effective," and a gauge that is merely coincident-and-legible still guards against the real failure mode (not noticing). Predictive is the bonus; legible is the floor.

---

## 1. What ρ(G) is, and why it earns a slot

**The scalar.** A Hawkes process splits every event into two possible origins: *exogenous* (an outside shock) or *endogenous* (triggered by a prior event rippling forward through a decaying self-excitation kernel). The **branching ratio n** is the average number of direct offspring each event spawns through that self-excitation:

| n | Meaning |
|---|---|
| 0 | Pure Poisson — every event a bolt from the blue, no internal feedback |
| 0.5 | Half of all activity is the system reacting to itself |
| → 1 | Each event spawns ~one offspring — cascades barely die out; the system rings like a bell from a faint tap (critical) |
| ≥ 1 | Non-stationary — each event more than replaces itself; the cascade runs away |

So n is a dial from inert → critical → explosive, reading exactly *how much of what's happening is the system reacting to itself versus to the world.*

**[PRINCIPLE] Why it's a gauge we don't otherwise have.** n can climb while the surface looks calm — price steady, vol low, spreads tight — because the *fraction of activity that's endogenous* is rising underneath. Every other fragility gauge reads a **level** (VIX is high, spreads are wide) and so tells you the fire has *started*; it is coincident. ρ(G) reads the **coupling that determines whether a spark becomes a fire** — how dry the kindling is *before* ignition. That is what makes it forward-looking by construction, and why it earns the master-caution-light's most important input slot.

**The matrix.** Generalize to N processes that excite themselves *and each other*. **G** is the N×N branching matrix; **G_ij** = expected events in process *i* triggered by one event in process *j*. The **diagonal is self-excitation** (a node's own momentum); the **off-diagonal is contagion** (cross-node spillover). The system's criticality scalar is **ρ(G), the spectral radius** (largest absolute eigenvalue). Stationarity requires **ρ(G) < 1**; as ρ(G) → 1 the *coupled* system nears criticality — and crucially it can get there through the **off-diagonal alone**, i.e. the system becomes critical through *contagion wiring* even if no single node is individually hot. That is the load-bearing-beam / correlations-to-1 risk, measured **dynamically** (who triggers whom, through time) rather than **contemporaneously** (who moves with whom, now).

**[PRINCIPLE — the load-bearing caveat] ρ(G) is never a number; it is a number plus its kernel assumption, and the two travel together always.** The branching-ratio estimate is *extremely* sensitive to the assumed decay-kernel shape. Hardiman–Bercot–Bouchaud (2013) fit markets with a **power-law** kernel and found **n ≈ 1, perpetually near-critical**; exponential kernels on the same data give materially **lower, calmer** readings. Same market, opposite criticality verdict — entirely from the memory-shape assumption. (Power-law fat tails load weight onto distant-past events as endogenous causes, inflating n; exponential kernels forget faster, attributing more to the exogenous baseline.) This is the §12 power-law epistemics with real teeth, because it changes the number you'd act on.

The discipline that falls out — **rule 14 turned on your own gauge:**
- **[DECISION]** Choose the **exponential / sum-of-exponentials** form deliberately. It's the *conservative* estimator (less prone to crying "critical") and it reuses the decay machinery already in the microstructure stack.
- **[PRINCIPLE]** Trust the **trajectory, not the level.** "ρ(G) has climbed for six weeks under a *fixed* kernel" is robust; "ρ(G) = 0.85" in isolation is nearly meaningless without its assumption stapled on. **Watch the derivative; distrust the absolute value.**
- **[DECISION]** **Archive the kernel form with every reading** (the Lenski-Ledger / validation-gate requirement — now you see *why* it's load-bearing, not bureaucratic).

---

## 2. The capacity-inversion principle (why most of the source stack does NOT port)

This subsystem is ported from a microstructure trading architecture (Mamba-SSM perception, ESN, neural-SDE, PINN, PPO policy, learned Hawkes kernels). **[PRINCIPLE] The principles transfer; the machinery mostly does not.**

**Why.** Microstructure gives millions of events/day; macro gives perhaps a few hundred regime-relevant observations *per decade* — and only a handful of genuine regime transitions (2000, 2008, 2011, 2020, 2022). This **inverts the bias-variance regime.** In microstructure the danger is an underpowered model; in macro the danger is an **overpowered** one that memorizes a handful of historical regimes and OOD-fails on the first genuinely new one. *"Excess capacity breeds overfitters."*

This is the **same conclusion as thesis §12** (the regime model that was a brilliant historian and slept through 2008; "don't build a detector for the last war") — arrived at **independently** from the microstructure capacity analysis. **Two independent derivations converging on the same answer is the strongest signal it's true**, and it *validates the smoke detector's entire lean-interpretable design.*

**Consequence for the port:**
- **Transfers (high value):** ρ(G) as a reflexivity gauge (the jewel); the capacity-inversion principle itself; the point-in-time data discipline (§3); the decay-kernel / sum-of-exponentials idea.
- **Transfers as method, deprioritize:** strong-prior + KL-anchor HMM construction; no-gradient multiplicative gate; offline-discover → warm-start → online-refine.
- **Should NOT cross (machinery):** the Mamba perception backbone, ESN, neural-SDE, PINN — capacity *and* opacity (they reintroduce the black box the detector exists to avoid). The PPO/execution layer is dead on arrival by design — **no execution surface.**

**[PRINCIPLE] At the apex, interpretability is a hard requirement, not a preference.** The master caution light's whole job is to tell you *legibly* where to look. So the fusion and every gauge feeding it stay rule-based and readable. The microstructure stack's best lesson for the macro tool is *"be less like the microstructure stack."*

> Note on indicator selection: the source indicators were chosen for **functional coverage** (filling structural gaps in a perception stack), *not* reverse-engineered from past crashes. This is the robust provenance — functional coverage generalizes to unseen regimes; curve-fit-to-history does not. There is no crisis-selection bias baked into the architecture.

---

## 3. PREREQUISITE — the point-in-time (vintage) data layer

**[PRINCIPLE] This is the long pole. Nothing in this subsystem can be validated without it, and it does not yet exist in the repo (`feeds.py` pulls current data).** Build it once, well; every backtest in the whole system benefits.

**Why it's worse for a fragility detector than for an ordinary backtest.** Macro revisions are **not random with respect to the signal** — they correlate with it. Initial estimates are systematically too optimistic near turning points and revised *down* as bad news fills in. Canonical case: **Q4 2008 real GDP first printed ≈ −3.8% annualized, later revised to ≈ −8%** — it more than doubled in the *worse* direction, after the fact. Validate a detector on revised data and it "sees" 2008 collapse with a clarity **no one had in real time**, concentrated exactly at the crisis you're trying to prove it catches. **The detector's own validation becomes the silently-broken green light** — the turkey, one level up. **The OOD lead-time backtest is meaningless, or worse, on non-vintage data.**

**[PRINCIPLE] The goal is not "don't cheat." It is: make the backtest's information environment identical to the live one.** Live, the detector *only ever* sees first-print, unrevised, noisy data (future revisions don't exist yet — live is automatically look-ahead-free). So **calibrate and score on the first-release vintage**, or every backtest trains on clean numbers and deploys on dirty ones — a train-clean/deploy-dirty mismatch that makes it *underperform its backtest live, exactly when it matters.*

**Two distinct look-aheads, two different fixes:**
1. **Revision look-ahead** — using the revised value instead of the as-first-reported value. (Which vintage of the number.)
2. **Release-timing look-ahead** — using a data point before it was published. A December GDP reading isn't knowable in December; the advance estimate lands late January. **Timestamp every macro event by its release date, not its reference date.**

**Sources.** ALFRED (St. Louis Fed) — FRED's vintage twin, serves any series "as of" a historical date. Philadelphia Fed **Real-Time Data Set for Macroeconomists** (Croushore–Stark) — purpose-built quarterly vintages, the academic standard.

**[DECISION] The engineering guard — the macro analog of the Δt / session-boundary corruption check:**
- The only accessor is **`get(series, reference_date, as_of_date)`**, returning the value *as known on `as_of_date`*. Every backtest query passes `as_of = the simulation's current clock`.
- The invariant: **FAULT any observation whose release_date > the query's as_of** — loud, like a physically-impossible price jump. This makes look-ahead *structurally hard to commit*, not something you must remember to avoid.
- **Store two timestamps on every point** (reference date, release date), never one.
- **Use published seasonally-adjusted vintages; do not roll your own SA** — re-estimated seasonal factors silently rewrite *past* SA values, reintroducing look-ahead.

**[PRINCIPLE] Triage — the boundary is favorable, and it maps onto the sensor banks.** **Market-priced gauges are point-in-time clean for free** (a VIX close, a credit spread, a Treasury yield, a price are not revised). So most of **Bank A is PIT-safe with no vintage store at all.** The revision problem concentrates in **estimated real-activity series** — GDP, payrolls, industrial production, retail sales, personal income. Survey diffusion indexes (ISM, PMIs) and CPI are essentially not revised. *(Verify per series, but that's the shape.)*

**[PRINCIPLE — architecture-changing] The agentic scouts cannot be cleanly backtested at all.** A scout is a web search; run one "as of October 2008" *today* and it returns 2010–2025 hindsight (retrospectives, post-mortems, revised narratives), not what was knowable then. **The web has no vintage** — there is no ALFRED for "what the internet said on date T." Therefore:

> **The deterministic banks are historically validatable (on PIT data); the agentic banks are forward-validatable only.** You prove the gauges' lead time against 2008/2020/2022; you can *only* earn confidence in the scouts by running them live, going forward, scored as real events unfold.

This reinforces deterministic-first from a new direction (it's not just lower hallucination risk — it's *the only part you can validate against the past*), and it shares a root cause with why the **qualitative OOD layer can't be seeded**: the narrative layer has no vintage, period.

**Two honest limits.** (1) PIT fixes the *data*, not the hindsight in your *choice of what to monitor* — selection bias lives one level up and is handled by leaning on priors and a small indicator set, not by vintaging. (2) PIT makes the backtest *honest*, not the detector *omniscient* — a genuinely novel mechanism still won't show up. PIT buys a *truthful lead-time estimate*; structure stays the backstop.

---

## 4. Event taxonomy — the foundation both forks share

A Hawkes process is undefined until you say *what counts as an event* and *when it's timestamped*. Timestamp is settled by §3 (release date; close for market events). Four remaining decisions, two of them deep.

**[DECISION 1] Dimension N — what the processes are.** ~6 **asset-class nodes**: equities, duration/rates, credit, FX, commodities, gold. Then the **diagonal of G is each class's self-excitation** and the **off-diagonal is literally the cross-asset contagion graph.** Two constraints make this right: N² off-diagonal entries from a scarce sample means **sample count caps N** (capacity discipline — ~6 over ~20yr of daily data is fittable; 20 nodes is not); and **define these nodes over the same asset-class decomposition the rest of the detector uses**, so ρ(G)'s off-diagonal and the existing cross-sleeve-correlation gauge are measuring the *same coupling through two lenses* and are directly comparable.

**[DECISION 2] Signed / downside-tracked.** Downside moves cluster and propagate through different machinery than melt-ups (leverage effect, margin spirals, forced deleveraging — the fire-sale channel). An unsigned process averages crash-contagion together with melt-up momentum and blurs the exact asymmetry that matters. **Track downside-event excitation as its own thing.** (Cost: ~2× the events. Worth it — the tool is for cascading *failure*.)

**[DECISION 3 — deep trap #1] Thresholding.** Events are moves beyond **k·σ**, normalized so the threshold means the same thing across regimes. But the obvious normalization — *trailing conditional vol* — contains a self-defeating mechanism: **Hawkes self-excitation and volatility clustering are the same phenomenon.** Normalizing by fast conditional vol **partially conditions out the very clustering ρ(G) is supposed to measure** — you can deflate n by absorbing endogeneity into the normalization, reading calm because you defined the calm in. (A fixed absolute threshold preserves clustering but becomes meaningless across regimes.) There is no free lunch; you're choosing *what to attribute the clustering to.* **[DECISION]** Use a **deliberately sluggish ~1-year trailing normalization** — slow enough to stay comparable across the decade, slow enough not to chase and absorb short-horizon clustering — **and sensitivity-test it** (if ρ(G)'s trajectory flips character between 6- and 18-month windows, that fragility must be known before trusting the gauge).

**[DECISION 4 — deep trap #2] Granularity / debounce.** "|r| > kσ on a given day" makes a five-day selloff into **five back-to-back events** → enormous spurious self-excitation → inflated n. Is that real cascade structure or a binning artifact? Both, partly — which is the problem. **[DECISION]** Define events at the **onset of a threshold-exceedance episode** with a **refractory period** (a multi-day move = one event with a magnitude, not N events). This is the "suppress flicker, preserve high-intensity bursts" declustering from the microstructure Hawkes filter — one of the cleanest wholesale transfers in the whole port. Start with a short refractory window; **watch whether n is being driven by consecutive-day runs** and lengthen if so.

**[PRINCIPLE — the deepest issue: baseline-vs-excitation identifiability].** Rising event intensity has two explanations the model must split: the **exogenous baseline μ rose** (more outside shocks) *or* the **self-excitation n rose** (more endogenous cascading). These are **partially confounded**, and the split depends on how much flexibility μ is given. Constant μ → all clustering attributed to endogeneity → high n (possibly overstated). Time-varying μ(t) → the baseline "explains away" clustering as exogenous-arrival drift → deflated n. So the branching ratio depends on **both** the kernel shape (§1) **and** the baseline's flexibility — two hand-made choices, both moving the number. **[DECISION]** Keep **μ rigid — constant, or piecewise-constant refit per regime, never continuously time-varying.** A wiggly μ(t) is more capacity (bad) *and* muddies the exact quantity you care about. Attribute clustering to endogeneity (the thing you're measuring), accept this can overstate n under genuine baseline drift, and handle drift by **regime-conditioning the refit** — which is also why ρ(G) must be fit regime-conditioned, not as a single static matrix. *Regime-conditioning protects the identifiability of n itself, not just ρ(G)'s level.*

**[PRINCIPLE] The events pay off before any Hawkes fit runs.** Raw **event-rate, downside-event-rate, and consecutive-day clustering** are themselves clean deterministic Bank-A gauges (PIT-safe market data, fully readable). So the event layer feeds the panel *immediately* — a readable gauge on step one, the reflexivity gauge on step four. Fits deterministic-first, comprehend-as-you-build.

**[PRINCIPLE] Overfitting guardrail on k.** Do **not** grid-search the threshold (or debounce, or vol window) to make crisis dates light up — that fits the past, not a sensor. Pick a principled **k ≈ 2–2.5σ**, fix it, verify **robustness** to it. If ρ(G) only signals at k = 2.31, you've rebuilt the war you already won. The threshold is exactly the knob the optimization itch wants to tune.

**v1 taxonomy (concrete):** ~6 asset-class processes aligned to the sleeves; signed / downside-tracked; events at onset of a > ~2σ move normalized by a sluggish ~1yr trailing vol, few-day refractory debounce; timestamped at close; constant-μ fit, refit per regime; threshold fixed and sensitivity-tested, never tuned to crises. **Return-events only to start** (PIT-clean, stands up the machinery); data-surprise events (§5) as the planned upgrade.

---

## 5. Data-surprise events — the exogenous anchor

**[PRINCIPLE] Purpose first.** Return-only events force the model to infer exo-vs-endo from arrival-time clustering alone (the §4 confounding). **A data surprise is exogenous by definition** (outside information arriving against consensus), so a surprise stream *pins the exogenous channel* and makes the endogenous self-excitation estimate trustworthy. Data-surprise events are not a v2 nicety — **they are the eventual fix for the identifiability problem return-only events can't solve.** Design goal: supply an *unambiguously-exogenous, correctly-ordered, magnitude-comparable* arrival stream.

**Wrinkle 1 — vintaged consensus.** Surprise = actual − consensus, and **both terms must be as-known-before-release.** The actual is first-print (§3 handles it). The new trap: **consensus numbers themselves get revised/backfilled** — many calendar vendors display the *current* or *final* consensus, so pulling "the consensus for that release" today may not return what the screen showed that morning. Source hierarchy, cleanest first:

- **Market-derived surprises are PIT-free by construction — START HERE.** For Fed decisions, read the surprise from **fed funds futures**: implied probability *before* the meeting vs. the outcome (Kuttner 2001). No survey vendor, no backfill, no vintage problem — the futures price *is* the timestamped pre-release expectation. *(Distinction that matters for the anchor: the futures-implied **prior** is the clean exogenous input; the **post-decision jump** is the endogenous response being modeled — don't confuse them, or the answer is baked in.)*
- **Survey-based surprises (payrolls, CPI, ISM) need genuinely vintaged consensus.** Bloomberg ECO survey medians are gold-standard (timestamped, preserved) but paywalled. Pragmatic: the **Citi Economic Surprise Index** already computes standardized, relevance-weighted, decayed surprises vs. survey median — usable as **benchmark** (does your stream track it?) and possibly as a feed. For any vendor, the integrity question is non-negotiable and **per-source**: does it preserve the pre-release consensus or backfill it? If unconfirmable, unusable for backtesting.
- The consensus has its **own as-of** (the survey *closes* a day or two before release). Store it; the vintage guard should respect it.

**Wrinkle 2 — normalization, and the deep trap is VALENCE not magnitude.** Mechanical part: standardize by the **trailing** σ of past surprises for that series (z = (actual − consensus)/σ_surprise; trailing-only or it's look-ahead); event = |z| > k, k fixed. The hard part: **the same surprise has opposite valence in different regimes** — a hot payrolls print is "good news → risk-on" normally, but "good news → bad news → risk-off" in a good-news-is-bad regime (exactly 2022–23). **[PRINCIPLE] Do not hardcode a valence map** — it embeds a regime assumption that *inverts* in the conditions a fragility detector most needs to read right. **Sign by raw economic direction** (or use unsigned shock-magnitude) and **let G learn the regime-dependent propagation.** Whether a hot CPI print triggers an equity-downside cascade *is* the off-diagonal being estimated — you want to **discover** the 2022 sign-flip, not bake in a 2017 valence that hides it. Hardcoding would convert a potential discovery into a blind spot.

**Wrinkle 3 — intraday ordering: need ORDERING, not true spacing.** Surprises carry intraday timestamps (8:30am data, 2pm FOMC); return events are on 4pm closes. **[DECISION] Resist going to intraday resolution** — it reintroduces microstructure-timescale machinery into a weekly-cadence tool and violates clock-matching. **Stay daily, but preserve within-day order**: surprise at `t = day + release_hour/24`, close at `t = day + 16/24`, so a morning surprise correctly *precedes* the same-day close. Costs nothing, and **cross-excitation direction (surprise → response, not response → surprise) depends entirely on it.** Ordering yes; sub-day spacing no.

**Two mechanical wrinkles inside this:**
- **Keep the return-event definition independent of surprises.** A return event is a > kσ move, identical on release and non-release days. Define it *by* the surprise and you've baked in the cross-excitation you're trying to estimate. Let the model *discover* that release days carry more surprise-triggered events.
- **Bundle co-released series into one composite event.** The employment report is payrolls + unemployment + wages at one 8:30am timestamp; identical-timestamp events are degenerate for Hawkes (no orderable sequence) and treating each as its own process blows the capacity budget. Aggregate to a single "employment-report surprise" with one magnitude.

**Staging:** start fed-funds-futures monetary surprises (cleanest, no vintage problem); stand up surprise → return cross-excitation on those; add survey-based macro surprises *only once vintaged-consensus sourcing is genuinely solved* — a contaminated consensus poisons the exact anchor the surprises exist to provide.

---

## 6. Fitting G and extracting ρ(G) — *[OPEN — not yet deep-designed]*

Sketch only; this is the next design session. The source-stack methodology is **offline-discover → warm-start → online-refine**: discover G's topology offline from history (e.g. NPHC / cumulant matching), use it to warm-start learnable kernels, then refine online via arrival-time likelihood. **[DECISION carried from §1/§4]** exponential / sum-of-exponentials kernel; rigid μ, regime-conditioned; archive {ρ(G) trajectory, kernel form, calibration method, regime context} with every reading. **Open questions to resolve here:** estimator choice and its small-sample behavior; how regime-conditioning interacts with the fit (how regimes are bounded); how online-refinement avoids slowly fitting away the signal (the boiling-frog risk applied to the estimator itself); confidence/stability bands on ρ(G) so a noisy estimate doesn't masquerade as a trajectory.

---

## 7. The OOD fusion — ρ(G) + absorption ratio (Bank D)

**[PRINCIPLE] Do not blend the two into one fragility score.** They are fooled by **different** artifacts, so they **cross-check** each other — and blending throws that away. The absorption ratio (Kritzman–Li 2010 — fraction of total variance in the top few eigenvectors) spikes in a **benign melt-up** (everything rising on one factor — high correlation concentration, zero fragility); ρ(G) inflates from a **kernel/debounce artifact**. But a melt-up that fools AR won't inflate ρ(G), and an artifact that inflates ρ(G) won't move AR. **Agreement is a fabrication filter; disagreement is the GO-LOOK.** This is the aviation sensor-disagreement lesson and the Bank-C reconciliation principle, applied a third time — now to the two quantitative criticality gauges.

**The joint state — a 2×2 in (AR, ρ(G)) space:**

| | **ρ(G) low** (no cascade) | **ρ(G) high** (self-exciting) |
|---|---|---|
| **AR low** (decoupled) | Calm — genuinely quiet | **Early / localized contagion** — a node ringing before the system couples. *Highest lead; ρ(G) out front.* |
| **AR high** (coupled) | **Coupled-but-quiet** — crowded into one factor. *Ambiguous: loaded-pre-crisis OR benign melt-up → go-look to disambiguate.* | **Confirmed critical** — coupled *and* cascading. *Most certain, least lead.* |

The off-diagonal cells are the payoff, asymmetrically: **ρ(G)-high / AR-low** is the early-warning divergence (temporal cascade before cross-sectional compression) — potentially the highest-lead signal. **AR-high / ρ(G)-low** is the ambiguous divergence (eerily-calm-crowded-trade *or* benign melt-up) — which is *why* it's a GO-LOOK, not a verdict: it routes you to the level gauges to disambiguate. **Both-high** is most certain but least useful (by the time both confirm, you're coincident).

**[HYPOTHESIS — the lifecycle ordering. DO NOT HARDCODE.]** The cells *suggest* a sequence: **ρ(G) rises first → AR compresses → both max (correlations → 1).** If that ordering holds, ρ(G) is the **leading** lens and AR the **confirming** lens, and "ρ(G) climbing while AR is calm" is the single most valuable early signal. **But the ordering is probably crisis-type-dependent** — 2020 (liquidity shock) may spike both near-simultaneously; 2007–08 (slow credit unwind) may show a long ρ(G)-leads runway; 2022 (inflation regime) may order differently again. **The PIT crisis backtest must establish the lead-lag — whether it exists, how large, and whether it's stable across crisis types.** If stable → trust ρ(G)-leading as the early trigger. If crisis-dependent → treat the two as **coincident cross-confirmation** with the divergence cells as go-look, *not* as a directional lead. **Do not assume the ordering you'd like.**

**[DECISION] Mechanics:**
- **Fuse trajectories, not levels** — and this falls out for free: Kritzman–Li's actual signal is the *standardized shift* in AR (ΔAR vs. its own trailing distribution), and ρ(G)'s trustworthy quantity is its *derivative under a fixed kernel*. Both reduce to **standardized criticality-velocity**, directly commensurable.
- The OOD layer **monitors the joint (ΔAR, Δρ(G), lead-lag) as a small feature vector** whose historical shape it knows — **Mahalanobis distance from the seeded baseline** (the "correlations correlating" machinery). The fusion *is* the OOD layer doing its job on these two features. The caution light fires when the *joint relationship* goes historically unfamiliar — both spiking together far from baseline, OR diverging in a way the history doesn't contain.
- **The off-diagonal of G routes the GO-LOOK.** When ρ(G) rises, G_ij identifies *where* the self-excitation concentrates → "ρ(G) climbing, led by the **credit** node, AR still calm → check credit spreads (Bank A) and run the credit/rate scouts (Bank B)." The fusion's output is a **targeted pointer into the rest of the panel**, not a standalone judgment. ρ(G) localizes; AR confirms breadth.

**[PRINCIPLE] Caveats so the fusion isn't its own false-green:**
- **Validate the ordering on PIT crises before trusting ρ(G)-leads-AR** (the whole reason the vintage layer comes first).
- **Both share the non-stationarity trap, squared.** If *both* baselines are trailing, a slow fragility normalizes in both at once — the boiling frog with two thermometers both recalibrating to the warming water. **At least one reference for each must be a fixed historical anchor** (the seeded crises as permanent reference points).
- **Divergence needs persistence, not a print.** Both signals are noisy; a one-day divergence is noise. Escalate only on a **sustained** divergence (multi-week ρ(G)-leads-AR gap). Watch the trajectory of the divergence, not its instantaneous value.
- **Keep the fusion rule-based and legible — do not learn it.** Capacity-inversion at the apex: a learned (AR, ρ(G), context) → score map reintroduces opacity into the one component that most requires interpretability. Two standardized scalars, a 2×2, a persistence-gated divergence flag, a Mahalanobis-on-the-pair — **simple by design, because the caution light cannot be a black box.**

---

## 8. Integration into the existing architecture

**[PRINCIPLE] It slots into the seam already built — no new output plumbing.** Every sensor emits a `SensorReading`; ρ(G), the absorption ratio, and the event-derived gauges each become a **new sensor type via `register_sensor_type`**, rendering through the HUD / store / Discord unchanged. The architecture already accepts them.

**[PRINCIPLE] Bank D does NOT need ρ(G) to ship.** The absorption ratio runs on **market-priced data (PIT-clean for free)** — no vintage store required. So **build D now on the simple interpretable lens** (absorption ratio / top eigenvalue), get the master-caution-light working end-to-end, and add ρ(G) as the **second** criticality lens to the *same* fusion later. ρ(G) is the temporal complement to the contemporaneous AR.

**The dependency chain (and why ρ(G) is correctly Phase 5+):**

```
PIT vintage store  →  event taxonomy (return events)  →  Hawkes fit  →  ρ(G) sensor
                                                                              ↓
                                       folds into the already-built Bank D fusion
                                       (which shipped earlier on the AR lens alone)
```

ρ(G)'s real prerequisite is the PIT layer, which doesn't exist yet and benefits *every* backtest. None of this blocks finishing B/C/D. **Build order: finish B/C/D → build the PIT layer → event taxonomy → Hawkes/ρ(G) → fold into D.**

**Related later-additive signal — TDA *[OPEN]*.** Persistent homology on the *gauge-panel trajectory* (not the microstructure price-size cloud) is a studied crash early-warning method (Gidea–Katz 2018 — persistence-landscape norms spike before 2000/2008). It captures **nonlinear, higher-order shape** the eigenvalue/AR methods are blind to by construction — genuinely *additive*, not redundant. But interpretable covariance methods dominate for v1 (simpler, readable — which matters for a caution light), and the existing TDA implementation makes experimenting cheap later. **Sequence: interpretable covariance core first; TDA as a scoped optional second signal much later.**

---

## 9. Validation gates — what would prove or disprove this

**[PRINCIPLE] The single artifact that licenses trusting any of this:** replay **2008 / 2020 / 2022 on point-in-time data**, run the gauges, and **score on LEAD TIME** — does ρ(G) (and the fusion) fire *early enough to be useful*, or only *coincident with the crash*? This is the same question that mattered for the Nasdaq regime backtest, which was a brilliant historian that slept through 2008 in real time. **The gauge is a forecaster only if it catches the shift before the break; otherwise it's a very well-read historian.**

Specific things the backtest must establish (not assume):
1. **Does ρ(G) carry pre-level information at all?** (The load-bearing hypothesis. If no → subsystem is coincident-confirmer, still mildly useful, report honestly.)
2. **The ρ(G)↔AR lead-lag** — exists? how large? stable across crisis types? (§7 hypothesis. Determines whether the fusion treats ρ(G) as leading or as coincident cross-confirmation.)
3. **Kernel-sensitivity of the verdict** — does the *trajectory* (not level) survive a reasonable change of kernel? (If the signal flips with the kernel, it's an artifact.)
4. **Threshold/window robustness** — does the signal survive k ∈ [2, 2.5]σ and vol-window ∈ [6, 18]mo *without* being tuned to crises? (§4 guardrail.)
5. **False-positive behavior in benign regimes** — how often does it cry wolf in calm/melt-up periods, and is that rate tolerable given the convex payoff? (The smoke-alarm asymmetry: false alarms are cheap, the missed 3am fire is not — but the rate still has to be *livable*.)

**Kill / downgrade criteria.** If (1) fails on PIT data, ρ(G) does not get the early-warning slot — it becomes at most a coincident corroborator of AR, and the honest move is to say so rather than dress it up. If (3) fails, the gauge is not trustworthy at any authority. **None of these failures sink the broader detector** — they just bound what this one subsystem is allowed to claim. That boundedness *is* the discipline.

---

## 10. One-line summary

ρ(G) is a single interpretable scalar that reads how self-exciting the market is — the kindling's dryness before ignition — and it earns the master-caution-light's most important slot **if and only if** a point-in-time backtest shows it leads the level gauges. It is built on a vintage data layer that doesn't exist yet, fed by an event taxonomy whose every knob is a place a plausible design silently corrupts the signal, fused with the absorption ratio so the two cross-check each other's artifacts, and kept rule-based because the apex cannot be a black box. **Theory to be proven or disproven — and acceptable either way.**

---

*End of capture. Sequenced behind B/C/D. Next deep-design session: §6 (fitting G). This document becomes the Claude Code handoff once the PIT layer is scheduled and the code state is current.*
