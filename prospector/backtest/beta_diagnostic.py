"""Crash-flags diagnostic — a SCOPED, READ-ONLY analysis, NOT part of the sensor.

Purpose (design thread, 2026-07-02): rev5 test 5c(iii) flagged 7 persistent March-2020 crash-window
spawns (Financials-heavy). This module runs the two cheap diagnostics that classify them into three
boxes — A stale-β artifact / B real macro-sector regime / C real secular shift — WITHOUT rebuilding
the estimator:

  §3a scoped_beta_slice: on JUST the flagged pairs, over the crash/persistence window, compare the
      residual correlation under the production 252d β vs a faster β (EWMA / shorter window). If it
      COLLAPSES under the faster β, the decoupling was a stale-β artifact (box A). If it is
      unchanged, the decoupling is genuinely idiosyncratic (box B/C).
  §3b two_clock_read: the departure-z trajectory across periods (β-window-roll clock) and vs the
      10Y-yield path (rates clock), to separate a real macro-cyclical regime (B) from a secular
      shift (C).

CRITICAL: this is a diagnostic slice, not an estimator swap. The sensor keeps its production 252d β
(prospector/sensors/xcorr.rolling_beta). Nothing here is imported by the sensor or runner sensor
paths. The milestone-3 outcome (box A ruled out — see docs/decisions/) means no EWMA swap is
warranted; a sensor-wide β change would move every residual including the +593-day recall signal and
would require a full milestone-3 re-validation (rev5 §5). Do not wire this in.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from prospector.sensors import xcorr
from prospector.store.layout import StoreLayout


def ewma_beta(rets: pd.DataFrame, market: str, halflife: int = 63) -> pd.DataFrame:
    """Per-fund EWMA β vs the market: ewm-cov / ewm-var, shifted t-1 (same lag discipline as the
    production rolling_beta). Halflife pre-specified on principle (the standard estimator for a
    regime break: half the weight in the last `halflife` days), never tuned to the flags."""
    m = rets[market]
    var = m.ewm(halflife=halflife, min_periods=halflife).var()
    out = {}
    for c in rets.columns:
        if c == market:
            continue
        cov = rets[c].ewm(halflife=halflife, min_periods=halflife).cov(m)
        out[c] = (cov / var).shift(1)
    return pd.DataFrame(out, index=rets.index)


def _residuals_under(rets: pd.DataFrame, betas: pd.DataFrame, market: str) -> pd.DataFrame:
    return pd.DataFrame({c: rets[c] - betas[c] * rets[market] for c in betas.columns},
                        index=rets.index)


def _pair_corr(resid: pd.DataFrame, a: str, b: str, window: int, lo: str, hi: str) -> float:
    return float(resid[a].rolling(window, min_periods=window).corr(resid[b]).loc[lo:hi].mean())


def scoped_beta_slice(panel: pd.DataFrame, market: str, pairs: list[tuple[str, str]],
                      lo: str, hi: str, corr_window: int = 63,
                      ewma_halflife: int = 63, short_window: int = 63) -> list[dict]:
    """§3a. Per pair, mean residual correlation over [lo, hi] under the production 252d β vs two
    PRE-SPECIFIED faster βs (EWMA half-life, and a short rolling window). `collapses` is True if
    production correlation is materially non-zero AND *either* faster β more than halves it — the
    signature of a stale-β artifact (it collapses under a sufficiently fast β). Unchanged under both
    faster βs => genuinely idiosyncratic (box B/C). OR, not AND: an artifact need only collapse under
    the fast enough one; a real decoupling collapses under neither."""
    rets = xcorr.daily_returns(panel)
    resid_prod = xcorr.residuals(rets, xcorr.rolling_beta(rets, market, 252), market)
    resid_ewma = _residuals_under(rets, ewma_beta(rets, market, ewma_halflife), market)
    resid_short = xcorr.residuals(rets, xcorr.rolling_beta(rets, market, short_window), market)

    rows = []
    for a, b in pairs:
        cp = _pair_corr(resid_prod, a, b, corr_window, lo, hi)
        ce = _pair_corr(resid_ewma, a, b, corr_window, lo, hi)
        cs = _pair_corr(resid_short, a, b, corr_window, lo, hi)
        material = abs(cp) > 0.1
        collapses = bool(material and (abs(ce) < 0.5 * abs(cp) or abs(cs) < 0.5 * abs(cp)))
        rows.append({
            "pair": [a, b], "display": xcorr.pair_display((a, b)),
            "prod_beta_corr": round(cp, 3),
            "ewma_beta_corr": round(ce, 3), "short_beta_corr": round(cs, 3),
            "max_delta": round(max(abs(ce - cp), abs(cs - cp)), 3),
            "collapses": collapses})
    return rows


def two_clock_read(panel: pd.DataFrame, market: str, pairs: list[tuple[str, str]],
                   yields: pd.Series, corr_window: int = 63) -> list[dict]:
    """§3b. Per pair: peak |departure z| by period (β-window-roll clock — a stale-β artifact fades
    as the 252d window rolls past the crash by ~early 2021) and the correlation of the residual
    correlation with the 10Y-yield path over 2020–2022 plus a 2022 re-fire flag (rates clock — a
    real rates-driven decoupling re-engages when rates spike in 2022)."""
    rets = xcorr.daily_returns(panel)
    resid = xcorr.residuals(rets, xcorr.rolling_beta(rets, market, 252), market)
    z = xcorr.departure_z(xcorr.fisher_z(xcorr.pairwise_rolling_corr(resid, corr_window)), 252)
    rows = []
    for a, b in pairs:
        s = z[tuple(sorted((a, b)))]
        peak = {p: round(float(s.loc[p].abs().max()), 2) for p in ("2020", "2021", "2022")}
        rc = resid[a].rolling(corr_window, min_periods=corr_window).corr(resid[b]).loc["2020":"2022"]
        y = yields.reindex(rc.index, method="ffill")
        rows.append({
            "pair": [a, b], "display": xcorr.pair_display((a, b)),
            "peak_abs_z": peak, "refires_2022": bool(peak["2022"] >= 2.5),
            "corr_with_yield": round(float(rc.corr(y)), 2)})
    return rows


def load_yield(layout: StoreLayout, source: str, date: str, name: str = "TNX") -> pd.Series:
    """Load a frozen yield pull (e.g. ^TNX saved as TNX.json). Index quotes read `quote.close`
    (an index has no adjusted close), unlike the fund price parser."""
    body = json.loads((layout.prices_path(source, date, f"{name}.json")).read_bytes())
    r = body["chart"]["result"][0]
    ts, close = r["timestamp"], r["indicators"]["quote"][0]["close"]
    idx = pd.to_datetime([pd.Timestamp(t, unit="s").normalize() for t in ts])
    return pd.Series(close, index=idx).dropna()
