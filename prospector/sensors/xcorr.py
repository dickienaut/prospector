"""Excess-correlation sensor — the inter-basket edge detector (spec §4a).

The pipeline, each stage a pure function over pandas so the whole thing is testable without a
store, a network, or a clock:

    prices --returns--> daily returns
           --rolling_beta(252)--> per-fund beta vs the market (SPY), known as of t-1
           --residuals--> r_i - beta_i * r_mkt  (the market strip)
           --pairwise_rolling_corr(63)--> residual correlation per sector pair
           --fisher_z--> variance-stabilised correlation
           --departure_z(252)--> (z_t - baseline mean) / baseline std, baseline ending t-1

Entry/exit is the Schmitt trigger (sensors/schmitt.py), z_in 2.5 / z_out 1.0 (DEFAULT, config;
calibrated by the milestone-3 backtest). The market-stress annotation is a separate 21d raw
correlation series that gates spawning during crash weeks (§4a CONTRACT) without deleting the
observation.

Provenance note (spec Appendix A): this z-against-a-frozen-baseline IS the OOD primitive —
model normal, flag departure — at the right capacity for 55 pairs. The sibling stack's
sliced-Wasserstein-over-neural-embeddings OOD detector is the same idea at the wrong capacity
(and reintroduces the black box the interpretability mandate forbids). The concept ports; the
machinery does not. Do not reach for the fancy distance.
"""

from __future__ import annotations

import hashlib
from itertools import combinations

import numpy as np
import pandas as pd

# --- Failure-diagnosis note (spec §4a, for the milestone-3 backtest) ---------------------------
# If March-2020 fires broadly despite the market strip, two DISTINCT mechanisms are candidates;
# know which one you are fixing before touching thresholds:
#   (1) stale trailing-252d betas leave uncorrected market exposure in residuals during a regime
#       break -> remedy: EWMA or a shorter beta window.
#   (2) a single factor underexplains crisis comovement even when estimated perfectly
#       -> remedy: add a second factor.
# The stress annotation (stress_series) is the near-term guard; this note is the diagnosis path
# the acceptance report wires in if falsification (§10 test 5c) fails.

FISHER_CLIP = 0.999999  # guards arctanh at rho -> +/-1 (near-duplicate residual series)


def daily_returns(panel: pd.DataFrame) -> pd.DataFrame:
    """Simple daily returns. Simple vs log is irrelevant at daily scale; simple keeps the
    residual r_i - beta*r_mkt a plain linear combination."""
    return panel.pct_change()


def rolling_beta(returns: pd.DataFrame, market: str, window: int = 252) -> pd.DataFrame:
    """Per-fund rolling beta vs the market: cov(r_i, r_mkt) / var(r_mkt) over `window`, then
    shifted one day. The shift makes beta known as of t-1 [proposal: trailing window ending
    t-1], so day t's residual is stripped with information available before t — no
    self-contamination. Columns: every non-market fund. min_periods == window (a partial
    window yields NaN, never a half-estimated beta)."""
    mkt = returns[market]
    var_mkt = mkt.rolling(window, min_periods=window).var()
    betas = {}
    for col in returns.columns:
        if col == market:
            continue
        cov = returns[col].rolling(window, min_periods=window).cov(mkt)
        betas[col] = (cov / var_mkt).shift(1)
    return pd.DataFrame(betas, index=returns.index)


def residuals(returns: pd.DataFrame, betas: pd.DataFrame, market: str) -> pd.DataFrame:
    """Market strip: r_i - beta_i * r_mkt for every fund with a beta (the market column drops
    out). NaN wherever beta is not yet warmed."""
    mkt = returns[market]
    return pd.DataFrame({col: returns[col] - betas[col] * mkt for col in betas.columns},
                        index=returns.index)


def _pairs(columns) -> list[tuple[str, str]]:
    """All unordered pairs, each sorted so (a, b) has a < b — a stable canonical key."""
    return [tuple(sorted(p)) for p in combinations(sorted(columns), 2)]


def pairwise_rolling_corr(df: pd.DataFrame, window: int) -> pd.DataFrame:
    """Rolling Pearson correlation for every unordered column pair. Returned frame has a
    MultiIndex column (a, b) per pair (a < b). Used on residuals (corr_days=63) for the signal
    and on raw returns (stress_days=21) for the stress series. min_periods == window."""
    cols = {}
    for a, b in _pairs(df.columns):
        cols[(a, b)] = df[a].rolling(window, min_periods=window).corr(df[b])
    out = pd.DataFrame(cols, index=df.index)
    out.columns = pd.MultiIndex.from_tuples(out.columns)
    return out


def fisher_z(corr_df: pd.DataFrame) -> pd.DataFrame:
    """Fisher z-transform: arctanh(clip(rho, +/-0.999999)). The clip keeps arctanh finite when
    two residual series are near-identical (rho -> 1)."""
    clipped = corr_df.clip(-FISHER_CLIP, FISHER_CLIP)
    return pd.DataFrame(np.arctanh(clipped.to_numpy()),
                        index=corr_df.index, columns=corr_df.columns)


def departure_z(fisher_df: pd.DataFrame, baseline_window: int = 252) -> pd.DataFrame:
    """Departure z per pair: (fisher_z_t - baseline_mean) / baseline_std, where the baseline
    mean/std are the trailing `baseline_window` Fisher-z values ending at t-1 (the .shift(1)
    excludes the current value from its own baseline). std==0 -> NaN (no departure defined).

    STATISTICAL CAVEAT (spec §4a, encode-not-solve): the 63d correlation windows overlap
    heavily, so consecutive Fisher-z values autocorrelate and these z-scores OVERSTATE
    significance relative to an i.i.d. Gaussian. The thresholds are therefore EMPIRICAL — set by
    the backtest sweep (§10 test 5), never by a Gaussian tail probability. Do not read z=2.5 as
    "0.6% chance"; read it as "the level the backtest showed separates signal from junk."
    """
    mean = fisher_df.rolling(baseline_window, min_periods=baseline_window).mean().shift(1)
    std = fisher_df.rolling(baseline_window, min_periods=baseline_window).std().shift(1)
    z = (fisher_df - mean) / std.replace(0.0, np.nan)
    return z


def stress_series(raw_returns: pd.DataFrame, window: int = 21) -> pd.Series:
    """The market-stress gate signal (§4a CONTRACT): the mean, across all pairs, of the rolling
    `window`-day RAW (pre-strip) pairwise correlation — gross comovement, everything moving
    together. Computed on raw returns, not residuals: it measures the comovement the β-strip is
    designed to remove. The gate fires when this LEVEL reaches crisis_level; a gated day freezes
    the trigger and records a would-be entry as a stressed departure, never a spawn.

    WHY AN ABSOLUTE LEVEL (recalibrated 2026-07-02, design thread, milestone-3 gate). The β-strip
    is PROVEN to remove the market factor cleanly even in the March-2020 crash (residual mean corr
    -0.035), so the strip — not this gate — is the primary market-factor defense. That demotes this
    gate to a secondary, crisis-only job: catch the two things the strip cannot during an acute
    crisis — (a) crash-onset β staleness (the trailing-252d β is estimated pre-crash, so residuals
    carry uncorrected beta for a short onset window), and (b) liquidity fire-sale dislocations. The
    old absolute 0.65 was miscalibrated — it fired on 24.8% of days because sector ETFs are
    structurally correlated (calm baseline ~0.5-0.65). The recalibration LIFTS the level to 0.85
    (top ~2-3% of days = genuinely extreme comovement).

    A baseline-relative departure (the design thread's first-choice form) was TESTED AND REJECTED on
    evidence: the mean pairwise correlation is smooth and mean-reverting with high year-long
    variance, so even COVID's 0.95 is only ~2σ above its own trailing norm, the distribution caps
    at ~2.5σ, and — decisively — its largest departures land on NON-crisis days (a Dec-2024 wobble,
    the Aug-2019 scare), so no threshold cleanly isolates a crisis. For this statistic, crisis
    severity IS the absolute level; normalizing by trailing variance destroys the signal. See
    docs/decisions/2026-07-02-stress-gate-recalibration.md.

    TWO NAMED CHARACTERISTICS (not bugs — recorded so no one is surprised):
    - Onset latency: L is itself a `window`-day rolling correlation, so it lags a crash by a few
      days; a departure at the very leading edge (2020-02-18) slips through before L rises — a
      bounded leading-edge leak, and losing paging in a crash week is free (§4a). The latency lever
      is `window`, not the threshold. Characterized in the backtest (§10).
    - Crisis-duration, not transient: an absolute gate stays on for as long as correlation is
      extreme (the whole COVID window), which is correct for an acute crisis. The watch-item is a
      PROLONGED extreme-correlation regime that could over-suppress the idiosyncratic departures we
      want to see — none occurred in 2019-2024, and the absolute level's aging under regime drift is
      a design-thread revisit (a self-calibrating form would fix both, but none tested detects
      crises — the open problem the decisions note records)."""
    raw_corr = pairwise_rolling_corr(raw_returns, window)
    return raw_corr.mean(axis=1)


def xcorr_lead_id(series_ids: list[str]) -> str:
    """Lead id from the pair's SEC series IDs (never tickers — §2/§5 CONTRACT): a short hash of
    the sorted series ids, spawner-prefixed. Display (e.g. 'XLK×XLU') is kept separately."""
    key = "xcorr|" + "|".join(sorted(series_ids))
    return "xcorr-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:10]


def pair_display(pair: tuple[str, str]) -> str:
    """Human display for a pair, sorted for stability: ('XLU','XLK') -> 'XLK×XLU'."""
    a, b = sorted(pair)
    return f"{a}×{b}"
