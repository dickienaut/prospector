# Bench Note — Crowding Detection (the consensus clock, pointed inward)

*From the design thread, 2026-07-02. Written to drop into the skunkworks bench. This is a design brief for a **Protector-side sensor bank** (not a new organ) that vendors Prospector primitives. Nothing here is built. It records the shape settled across several turns of stress-testing, so the bench can prototype and gate it before anything graduates.*

---

## What it is, and the hole it fills

Prospector's launch/lag machinery watches *new* theses approaching consensus. Pointed **inward**, the same idea watches *held* theses arriving there. It is the **success-side exit complement** to the existing break-triggers.

The break-triggers catch a thesis **dying** — fundamentals deteriorate, exit because the thesis is *wrong*. Nothing currently catches a thesis **succeeding into crowding** — the theme was *right*, it worked, capital flooded in, and the scarcity-window edge that was actually owned is gone even though the thesis was correct. For an investor whose satellites are explicitly *scarcity-window trades with a shelf life* (§3, Perez installation→deployment), this is the harder exit, and it is the one **December 1 has no instrument for.** The monthly review reads thesis-health; the bands read size-drift; but "this sleeve succeeded and the window closed, trim it back toward core" has no sensor. This is that instrument.

It adds a legitimate **third exit trigger** to the existing two (broken thesis; size-drift): *scarcity window closed via crowding.*

---

## The load-bearing discipline: structure, never price

Three states must be told apart:

1. thesis **dying** → break-trigger (already covered);
2. thesis **succeeding-into-crowding** → *trim* (the new thing);
3. thesis **succeeding-and-still-early** → *hold* (the state we want to protect).

**The trap: price is up in both (2) and (3).** A crowded theme and a still-early theme both show green. So any trigger that keys on price appreciation silently degenerates into "sell when it's gone up a lot" — which is exactly the price-based market-timing the whole system forbids. Therefore:

> **Every signal keys on crowding *structure* — flow, fund count, launch share, holdings overlap, correlation bloc — and never on price.** Keep it structural and the discipline holds by construction; let price leak in anywhere and it becomes a profit-taking trigger wearing a crowding costume.

This is the never-sell-on-price wall, applied to a new exit reason.

---

## Distinct from the existing break-triggers (not redundant)

The GRID break-trigger (transformer lead times normalizing) is **fundamental-scarcity ending** — the supply side catching up. Crowding is **market-scarcity ending** — everyone piling into the theme. These come apart: lead times can still be long (physical bottleneck intact) while the market has fully crowded the trade (valuation compressed, ten copycat funds launched). One sensor watches the *physical* bottleneck; the crowding sensor watches the *ownership* bottleneck. It catches an edge-erosion the fundamental triggers miss entirely.

---

## The sensor stack (ranked by measurability)

**Spine — fund flow (direction + acceleration).** Continuous, bidirectional, and the *true decision variable* — it measures capital movement directly, where launch-rate is a lumpy one-bit proxy for it. Bidirectionality is the key property: launch-rate sees a window *open* (funds launch when a theme heats up) but is nearly blind to one *closing* (dead ETFs linger for years before delisting). Flow sees both, symmetrically:

- inflow **accelerating** → room to run, capital still arriving → *still early-to-mid, hold*;
- inflow **decelerating / plateauing** → marginal buyer drying up → *window closing — the trim signal*;
- sustained **outflow** → capital leaving → *late, confirmed by the door*.

Flow is what finally separates "successful-and-still-early" from "crowded-and-done," the distinction price alone cannot make (both green): green price + accelerating inflow = still climbing; green price + decelerating inflow = top of the crowding curve.

**Corroborator — copycat-launch-rate.** Deterministic, EDGAR-verifiable (cite-or-fault clean), reuses Prospector's launch primitive directly. New funds launching *into your existing themes* (the fifth, sixth, tenth nuclear/grid/space ETF) is the industry certifying the theme is now marketable — consensus arriving. The *first* fund was early entry; the packaging *wave* is the crowding. Honest limit: coarse, discrete, one-directional, and **late by construction** — the industry launches the eighth nuclear ETF *because* it already sees the demand, so the launch wave confirms crowding that already happened. Fine for an annual trim; useless for timing.

**Level — accumulated fund count.** Crude crowding *stock* (fifteen funds is more mainstream than two). Guards the flow/launch-rate *velocity* against a spike off a tiny base.

**v2 co-signals (earlier but noisier — the layer that could partly cure the lateness):**
- *Valuation-percentile* — the theme's aggregate multiple at a rich percentile of its own history means forward return is compressed. This *precedes* the launch wave (funds launch *because* the theme got expensive and popular), so it's a leading indicator — but harder to assemble cleanly for a basket.
- *Within-theme residual correlation* — when a theme crowds, its names trade as a *bloc* on flows rather than fundamentals, so within-theme correlation rises. Reuses the xcorr engine directly, but interpretation is ambiguous (rising correlation could be crowding *or* a shared fundamental driver), so lower confidence.

These are the v2 layer *on top of* the v1 spine, not the starting point — deterministic-first discipline holds.

---

## The flow arithmetic (how to isolate net-flow from AUM)

AUM moves for two reasons; only one is the signal. Market return moves **NAV per share**; creations/redemptions move **shares outstanding**. Separator: *market moves NAV, flow moves shares.* Isolate flow by watching shares.

**Shares-based form (use this for ETFs):**
```
NetFlow_t = (S_t − S_{t−1}) × NAV_t
```
change in shares outstanding, valued at NAV. Positive = in, negative = out.

**Return-based form (equivalent, if you only have AUM + total return):**
```
NetFlow_t = A_t − A_{t−1}·(1 + R_t)
```
These are algebraically identical: `(1 + R_t) = NAV_t/NAV_{t−1}`, so `A_{t−1}(1+R_t) = NAV_t·S_{t−1}`, and `A_t − NAV_t·S_{t−1} = NAV_t(S_t − S_{t−1})`. The two data paths agreeing is the check that price is stripped correctly.

**Why shares-based, and why it's v1-able:** shares outstanding and NAV are *both issuer-published daily*, so net flow is computable from primary data — **no paid fund-flows product required.** (This reranks an earlier assessment that had flow gated behind paid data; the shares-outstanding decomposition promotes it to the deterministic, cite-or-fault-clean spine.) It also handles distributions for free — a distribution drops NAV but not shares, so it reads ~zero flow; the return form would misread that NAV drop as an outflow unless fed total-return NAV.

**Three edges:** compute at the finest interval (daily ΔShares × daily NAV) and sum to the period — a single monthly ΔShares × month-end NAV values a whole month's creations at one price and drifts; use **NAV, not market price** (ETF premium/discount noise); distributions are free in the shares form, adjusted only in the return form.

**Then normalize into the decision variable — one confound stripped per step (β-strip logic, one level up):**
1. **Strip fund size** → organic growth rate = `NetFlow_t / A_{t−1}`. Separates intensity from size ($100M is a flood for a $200M fund, noise for a $50B one).
2. **Aggregate to theme** → sum fund flows across the theme seed, divide by theme AUM → theme organic growth rate.
3. **Strip the market tide** → subtract the all-ETF organic growth rate. "Nuclear is taking a *rising share* of flows" is signal; "nuclear inflows rose but every theme's did" is risk-on froth, removed.

**The quantity that drives the trim is the trajectory, not the level:** *direction* (in/out — the bidirectional read), *level* (fill rate), and above all *acceleration* (the change in flow) — decelerating-but-still-positive inflow is the earliest honest "window maturing" read and inflects *before* flow crosses into outflow.

The same **double normalization** applies to launch-rate: the theme's *share* of total ETF launches, measured against its *own trailing share* — dividing by total launches strips the "everything is launching" market-froth confound; comparing to the theme's own history strips the theme-size confound.

---

## The theme seed (what counts as "your theme")

**Holdings-derived, CUSIP-keyed — HECO applied to classification.** A theme is defined *extensionally* by a reference seed of CUSIPs, never by fund names (a "Global Clean Energy" fund might be 60% solar or 20% solar — only the holdings tell you which; classifying by name is the exact mistake Prospector rejects when it refuses a bare ticker).

Build the seed from the look-through of the **thematic sleeve** — nuclear = NUKZ + URNM constituents, space = UFO + ROKT, grid = GRID — **not** the index funds (the S&P holding contains half the market and would make every theme seed uselessly broad). The index funds are *exposure* ground truth; the thematic ETFs are *theme-definition* ground truth. Use the right one for the seed and it stays sharp.

**Membership test for a new launch F:** the fraction of F's *weight* that sits in the theme seed (weight-fraction, not mere presence — that's what separates "this fund *is* about nuclear" from "this fund *has some* nuclear"). Data-timing wrinkle, immaterial for an annual signal: F's holdings lag its launch by the N-PORT gap (weeks–months); classifying off the prospectus mandate at launch is the deferred discourse-interpretation layer, so holdings-with-a-lag is the clean v1 path.

**Hand-expansion deferred.** Start with the pure holdings-derived seed; only add adjacent pure-play names if a real gap shows up in practice. Let the need prove itself before taking on any curation surface at all.

---

## The lateness principle (why late is fine here)

**Any signal read from public information is necessarily late — the information becoming public *is* the lateness.** The fund manager launching the eighth nuclear ETF and the retail investor reading about it see the same fact at the same structural moment: after the move that made it visible. There is no vantage in observable data that gets you there early, because "early" means before the thing is observable.

This is survivable *because it is the exit signal, not the entry.* Early entry into these themes was a **conviction** call on non-public signal (nuclear before the fund renaissance, space before the IPO wave) — that had to be early or the thesis was lost. Late *exit* costs only a slow give-back of edge. The asymmetry: being late to the entry would have been fatal; being late to the exit is a tolerable cost. The honest tool is one that knows which end it's on. Flow's *acceleration* (second derivative) partly cures the lateness — it inflects before flow itself turns — but the tool's job is **robust and honest about its lateness**, not early.

---

## Safety posture

- **Annual cadence.** Feeds the December-1 trim decision, not a fast trigger.
- **A question, not a call.** Emits *"Nuclear has crossed novel→crowded on the flow + launch-rate signal; review whether the scarcity window is closing"* — weighed against the fundamental break-triggers and everything else. It raises the item; the human makes the call.
- **Lens, not trigger.** Same posture as the regime model: a read on *what inning*, never an auto-trigger. No fast wire to execution, so it structurally cannot manufacture over-trading.
- **Price-blind by construction** (see the wall above).

---

## Acceptance test (milestone-3 style, against known cases)

**Known case: solar / TAN (§12).** Solar deployment broke records while the manufacturer ETF collapsed ~80% as the theme commoditized and crowded. Backtest the stack — flow reversal, launch wave, accumulated fund count — against that episode: **did the signals flag the window closing *before* the collapse?**

**Be as honest as the Prospector gate was.** That gate cheerfully surfaced that the stress threshold had *eaten* the real signal. This backtest must surface the true lead/lag: if, even on the known case, the signals only fired *at* the collapse rather than before it, write that down plainly — the value is "confirm the window has closed, trim over the following year," not "warn before the peak." Confirm-not-lead is still genuinely useful for a slow trim and useless for timing; either result is the honest, correct description.

**Adversarial second case: the 2007 uranium blow-off** (nuclear-hype round one). Good precisely *because* uranium is owned now — if the signal fires on 2007 uranium, does it also fire on *today's* nuclear, and is that a true crowding read or a false alarm? Build the backtest to answer that against a case understood from the inside.

**Anti-curve-fitting (transfers exactly from the stress-gate recalibration):** define crowding *conceptually* (a theme has transitioned from novel-with-first-mover-edge to mainstream-and-marketable-to-retail), pick thresholds that capture *that concept*, and use solar and uranium as a **consequence-check** — "does setting it to the concept happen to fire on solar before the collapse?" — **never** as the objective tuned toward. Thresholds are never auto-tuned. With only two known cases, fitting to them is overfitting to n=2. Set it on principle, freeze it, validate live as launches and flows accumulate.

---

## Build order

- **v1 (deterministic, cite-or-fault clean, reuses existing primitives):** flow spine (net-flow from issuer-published shares outstanding × NAV, price-stripped, theme-aggregated, market-normalized, trajectory-focused) + copycat-launch-rate corroborator (reuses Prospector's launch primitive) + accumulated fund count. Theme seed from the thematic-sleeve look-through.
- **v2 (earlier but noisier, needs interpretation):** valuation-percentile (leading) and within-theme residual correlation (reuses xcorr).
- **Precision is validated live, not at build.** Like Prospector's, the corroboration material (crowding episodes) is thin; the thresholds get set on principle now and proven as episodes accumulate.

---

## One-line summary for the bench

A Protector-side, price-blind, annual **crowding sensor** — the success-side exit complement to the break-triggers — with **fund flow (from shares-outstanding × NAV) as the v1 spine**, launch-rate and fund-count as corroborators, a holdings-derived theme seed from the thematic sleeve, and solar/TAN as the honest milestone-3-style gate. Feeds December 1 as a *question*, never a trigger. Necessarily late, which is fine because it's the *exit* end.
