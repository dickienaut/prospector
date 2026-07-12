# Technical briefing — fact-check, second pass (2026-07-12)

*Second-pass review of the **revised** briefing (`2026-07-12-prospector-technical-briefing.md`), which
folded in the five findings from the first pass (`2026-07-12-technical-briefing-factcheck.md`) plus a
parallel QA thread's corrections. Re-checked against the repository (`main`, 2026-07-12). Verdict: the
revision is accurate and appropriately hedged — send-ready modulo two precision tightenings and one
externally-checkable fact. Written to travel with the first-pass note into the final rewrite.*

---

## Verdict

**Close to send-ready.** All five first-pass findings are correctly resolved, the QA thread's new claims
check out against the primary source, and the honesty framing is strengthened (notably the "in-sample by
construction" disclosure). Two items remain — both *tightening*, not corrections — plus one public fact to
confirm.

---

## First-pass findings — all resolved correctly

| First-pass finding | Status in the revision |
|---|---|
| RMT/Marchenko–Pastur "cleaning" | ✅ Now a plain eigendecomposition; MP denoising explicitly "planned for a later calibrated layer." |
| Null-model "reshuffled/random-matrix" validation | ✅ Now "baselined detection; formal nulls planned … not yet implemented." |
| "+593 trading days" | ✅ Now "593 calendar days; ~407 trading days" (593 × 252/365 ≈ 408 — correct). |
| Falsifier "tested and held" | ✅ Now stated precisely: 7-of-10-persisted → pre-committed read-only diagnostic → "real but off-thesis," a routed classification, not a clean pass. |
| "partial correlation" / "execution impossible" | ✅ Both qualified (single-factor β-residualization; firewall enforced by a test). |

## QA-thread additions — verified against source

- **Q = "mean within-block minus mean between-block correlation," 252-day baseline** — exact: `sensors/dispersion.py` states `Q = mean(within-cluster corr) - mean(between-cluster corr)` and `dispersion_z(252)`. ✅
- **~98 firings, 2 corroborate, three 2024 funds** — matches spec rev14 ("2/98, corroboration set holds only three 2024 launches"). ✅
- **March-2020 residual 0.88 → ≈ −0.035** — matches spec rev14 / ARCHITECTURE §4. ✅
- **Ben-David, Franzoni, Kim & Moussawi, *Competition for Attention in the ETF Space*** — real paper, accurately characterized (specialized ETFs launch near peak hype and underperform), already cited in the repo's own idea notes. ✅
- **"in-sample by construction" disclosure** — accurate and a strong addition: the XLK×XLU case *was* the milestone acceptance gate's recall target. ✅
- **"11 baskets, 55 pairs"** — C(11,2) = 55. ✅ **"six active leads; two fractures (industrials z≈4.0, consumer staples fading)"** — matches state-of-project rev7 (XLI z≈4.0, XLP fading, 0/90 burn-in). ✅

---

## Two precision points still worth tightening

### 1. (worth fixing — it's the centerpiece claim) "a thematic fund packaging that relationship"

This is the load-bearing existence-proof sentence, so it is the one a quant will push on ("*which* fund, and
is it actually a tech–utilities fund?"). The fund is **TEKX**, a **transformational-technology** thematic ETF
(rebranded SPDR Galaxy → State Street Galaxy). Its SOI holdings are **~52% information technology, ~11%
utilities, ~14% industrials, ~10% financials** — so it *materially holds both* sectors, which is exactly what
the corroboration (a **both-sides sector-overlap** match) keys on. But it is **not a fund built around the
tech–utilities pairing**; it is a broad tech-thematic fund whose basket spans both. State the mechanism
plainly rather than imply intent:

> *Suggested:* "…a transformational-technology fund whose holdings span both sectors (~52% information
> technology, ~11% utilities) launched in September 2024."

Same fact, no soft spot for a skeptic to lever.

**Also (free, and externally checkable):** TEKX's **inception date is public** — a quant will confirm it in
seconds. The "September 2024" month, and therefore the 593-day / ~19-month figure, hinge on it. **Confirm the
exact inception date against the fund's official page before sending.**

### 2. (minor) "the dispersion layer's falsification is its current 90-day live burn-in"

The 90-day shadow burn-in is a **record-only calibration/observation** window before promotion — it carries
**no pre-committed reject condition**, so it is not strictly a falsifier. The dispersion layer's actual
falsification (its point-in-time backtest) is **deferred**. As written it slightly overclaims that dispersion
is *under a falsifier* when it is *under observation*.

> *Suggested:* "…the dispersion layer has not yet been falsification-tested — it is in a 90-day record-only
> shadow burn-in, and its point-in-time backtest is deferred."

---

## Bottom line

Honest, accurate, appropriately hedged. Fix #1 (the centerpiece existence-proof sentence), ideally #2, and
confirm TEKX's public inception date — then it is ready for the quant. Nothing else in the revision conflicts
with the primary source.
