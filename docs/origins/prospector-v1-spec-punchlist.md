# Project Prospector — v1 Spec Review (Punch-List)

*Review of `generator-v1-spec-2026-07-01.md`, from a separate review thread. Recommendations to evaluate, not decisions taken. These are refinements to a spec that is already sound — fold the P1 items into the milestone-3 gate; the rest slot where noted.*

---

## What's already right — don't rework it

The spec faithfully implements the deterministic-only v1 and goes *further* than recommended on safety:

- **Firewall is structural, not habitual** (§1): separate S3 bucket, IAM-scoped credentials that *cannot* read the detector's bucket or `portfolio.yaml`, no code path for graduation (human-and-one-way). This is the "same-pipeline-is-the-wall" recommendation made real.
- **novelty≠interest trap handled** (§2): the user's own book (GRID/NUKZ/XBI) is *excluded* from the seed by default.
- **HECO rule as CONTRACT** (§2, test 1): series-ID anchoring, prospectus-as-truth, `category_draft` never trusted, the original bug as its regression test.
- **Config honesty** (§5): `config.changed` emitted before sensors so a fold stays interpretable when a threshold moved — "don't let the present rewrite the past," applied to settings.
- **Discourse-capture-for-v2** (§6): freeze raw discourse now (cheap, zero oracle load) so v2's thaw-backward has substrate. Correct sequencing.

The items below make it *usable*, not just *sound*.

---

## P1 — fold into the milestone-3 acceptance gate

### 1. The acceptance test measures recall; it must measure precision.

**What:** §10.4 confirms the AI-power linkage (Tech×Utilities excess co-movement) *fires*. That's recall. It says nothing about how many false positives fire alongside it.

**Why it's the whole game:** the entire rationale for a deterministic-only v1 is to not flood the scarce human oracle. A threshold tuned to light up Tech×Utilities might also page on 25 spurious pairs — an oracle-flooding machine that happens to catch the one you wanted. **Precision is the metric that decides whether v1 achieves its own design goal**, not a nice-to-have.

**Fix:** the backtest should report the **full firing list** over 2019–2024, not just whether the target fired. Acceptance criterion adds a noise-fraction judgment: of everything that fired, how much was plausibly structural (AI-power, maybe GLP-1, maybe reshoring) vs. junk? Tie the threshold choice to precision, not just "fires usefully early." Deliberately back off from the recall-optimal threshold to avoid overfitting to the one known case.

### 2. Add a March-2020 falsification test for the market-factor strip.

**What:** the 2019–2024 window includes the COVID crash. Add an explicit check: **the sensor must *not* fire broadly during March 2020.**

**Why:** if many pairs light up in the crash, that's not structural linkage — it's the β-strip failing to remove the market factor (everything correlated because the *market* moved, and a stale trailing-252d β leaves uncorrected market exposure in the residual). Same failure shape as a misspecified Hawkes kernel manufacturing spurious criticality. If Tech×Utilities "excess" correlation spikes in the crash, the market-factor removal (§4a) is inadequate and needs a better estimator (e.g. shorter/decaying β window, or a multi-factor strip) before any firing is trustworthy.

---

## P1 — data-integrity gap

### 3. The strict identity contract has no failed-resolution path — it silently blinds you to novel funds.

**What:** §2 requires `series_id`; schema validation rejects a bare ticker (correct for integrity). But EDGAR's ticker→series/class mapping is genuinely messy, and a meaningful fraction of tickers won't resolve cleanly — disproportionately the *brand-new and weird* funds, which are exactly the targets.

**Why:** as written, a failed resolution blocks the write, so that launch is **dropped** — the "unwritten means never-written" evaporation the append-only design exists to prevent, reappearing at the identity layer. The rule that protects integrity quietly creates a blind spot for the novelty you're prospecting for.

**Fix:** define the failure path explicitly — emit `resolution.failed` onto `_system` (failures land *in* the fossil record, countable, never silent) and surface a **manual-resolution queue** in the dashboard. Integrity preserved; blindness closed.

---

## P2 — slot where noted

### 4. Dispersion ships uncalibrated.

Milestone 3 backtests only the excess-corr sensor; dispersion (§4b) goes live in milestone 4 on placeholder thresholds. A dispersion backtest needs **point-in-time constituents** (today's XLK members applied to 2019 prices is survivorship look-ahead), which is harder. So either build the PIT-constituent backtest, or explicitly plan a **live burn-in** where dispersion's thresholds are tuned by observation — and expect it noisy at first. Right now it's the one sensor entering live with no calibration gate. *(Slots into milestone 4, or a new milestone 3b.)*

### 5. No oracle-load ceiling.

The thing v1 exists to protect — human adjudication throughput — isn't monitored with a target. Set one: an expected **active-lead ceiling**, where exceeding it means thresholds are too loose. Over-firing is the over-trading analog for this tool and deserves the same explicit guardrail. The §8a email digest already lists active leads; add "N is the ceiling; above it, tighten." *(Slots into §8a + config.)*

### 6. Daily email vs. the impulse-migration chamber.

The dead-man's-switch needs a heartbeat, but *daily* is a daily touchpoint, and a daily "OK — no changes" trains you either to ignore the channel (defeating the dead-man) or to check compulsively. Consider a **weekly heartbeat with state-changes pushed immediately** when they occur — breakage still detected within a week (fine for a tool whose leads develop over months), with far less daily surface. Worth a conscious daily-vs-weekly decision rather than defaulting to daily. *(Slots into §8a.)*

---

## Expectations flag (not a gap)

### 7. v1 lays the substrate for the cross-stream lag; it does not deliver it.

The **cross-stream lag** (discourse → rebalance → launch timing) — the "deep" payload the founding work centered on — is a **v2** capability. v1 delivers *departures and launches*, and only captures the lag's raw material (frozen discourse, the launch-onto-live-lead hook in §4c). Be explicit so milestones 3–7 aren't expected to produce the lag signal itself. v1's job is to prove the deterministic core sees structure form *at all*; the velocity-toward-consensus measurement comes after.

---

## Bottom line

Milestone 3 is the right heart, and "if the backtest can't see AI-power forming, bring it back before building 4–7" is exactly the prove-it-cheap discipline. Fold **items 1 and 2** (precision audit + March-2020 falsification) into that milestone-3 gate — they're what tell you whether the sensor is *usable*, not merely *sensitive* — and **item 3** (failed-resolution path) into milestone 2, since it's the identity layer. The rest are calibration and expectation-setting that slot in as you build.
