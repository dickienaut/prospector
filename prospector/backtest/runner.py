"""Backtest runner — replays the xcorr sensor over history to calibrate thresholds and produce
the milestone-3 acceptance artifact (spec §10 test 5, the CONTRACT gate).

Writes ONLY under backtest/ (spec §7, CONTRACT): each run gets its own store root
(backtest/run_{stamp}/) with its own registry.sqlite, so synthetic history can never touch the
live events/ tree. The guard is structural (StoreLayout kind='backtest'), not conditional.

The replay is a faithful pass of the real sensor logic over frozen prices:
  panel -> z-panel (xcorr pipeline) + stress series -> per-pair Schmitt replay -> events.
Stress gating (§4a CONTRACT): on a stressed day the trigger is frozen (no spawn, no state
change); a would-be entry is recorded as a stressed departure onto _system with
market_stress=true. When stress clears and the departure persists, it fires normally.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from prospector.sensors import schmitt, xcorr
from prospector.store.event_store import EventStore
from prospector.store.layout import StoreLayout, backtest_run_root
from prospector.store.registry import Registry


def load_series_ids(path) -> dict[str, str]:
    """ticker -> SEC series id, from the reviewed backtest identity seed. Leads key on these
    series ids, never the tickers (§2/§5 CONTRACT)."""
    doc = yaml.safe_load(open(path))
    return {t: row["series_id"] for t, row in doc["funds"].items()}


@dataclass
class Firing:
    """One pair's entry into active over the window."""
    pair: tuple[str, str]
    lead_id: str
    entered: str          # ISO date
    exited: str | None    # ISO date, or None if still active at window end
    peak_z: float


@dataclass
class BacktestResult:
    from_date: str
    to_date: str
    z_in: float
    z_out: float
    firings: list[Firing]
    stressed_departures: list[dict]   # {pair, date, z} recorded during stress
    stress_days: list[str]            # dates where stress > threshold, within the window
    run_root: Path | None = field(default=None)


def _pairs_with_series(tickers, series_ids) -> list[tuple[tuple[str, str], str]]:
    """Every sector pair (excluding the market) with its series-ID-derived lead id."""
    from itertools import combinations
    sectors = [t for t in tickers if t in series_ids]
    out = []
    for a, b in combinations(sorted(sectors), 2):
        lead = xcorr.xcorr_lead_id([series_ids[a], series_ids[b]])
        out.append(((a, b), lead))
    return out


# Validation anchors for the recalibrated crisis gate — CHECKS it is held to, never targets it is
# tuned toward. The gate's demoted job is ACUTE crises only (crash-onset β staleness, liquidity
# dislocations), so:
#   - ACUTE_CRISES: the gate MUST fire (correlation genuinely spikes to extreme).
#   - SUSTAINED_REGIMES: the gate MUST NOT fire — a slow grind is a sustained regime where
#     idiosyncratic departures are disproportionately the structural shifts we want surfaced;
#     over-gating those months blinds the tool exactly when it should watch (why 0.85 not 0.80).
#   - CALM_ANCHORS: ordinary elevated-but-calm days stay quiet.
# 2020-02-24 is the crash proper (first large COVID down-day) used to measure onset latency.
ACUTE_CRISES = [
    {"label": "COVID crash", "from": "2020-02-24", "to": "2020-04-30", "onset": "2020-02-24"},
]
SUSTAINED_REGIMES = [
    {"label": "2022 bear grind", "from": "2022-05-01", "to": "2022-10-31"},
]
CALM_ANCHORS = [{"label": "XLK×XLU real signal", "date": "2023-01-25"}]


def compute_z_and_stress(panel: pd.DataFrame, market: str, cfg: dict):
    """The pure pipeline: panel -> (departure z per pair, stress level). Computed once; the
    threshold sweep reuses it (only the Schmitt replay changes per grid point). `stress` is the
    absolute market-wide correlation LEVEL (xcorr.stress_series) — the crisis gate fires when it
    reaches crisis_level. Absolute, not baseline-relative: correlation-concentration is a fragility
    gauge whose intrinsic level IS the signal (see the decisions note)."""
    w = cfg["windows"]
    s = cfg["xcorr"]["stress"]
    rets = xcorr.daily_returns(panel)
    betas = xcorr.rolling_beta(rets, market, w["baseline_days"])
    resid = xcorr.residuals(rets, betas, market)
    corr = xcorr.pairwise_rolling_corr(resid, w["corr_days"])
    z = xcorr.departure_z(xcorr.fisher_z(corr), w["baseline_days"])
    stress = xcorr.stress_series(rets, s["level_window"])
    return z, stress


def replay(z: pd.DataFrame, stress: pd.Series, pairs_leads, from_date: str, to_date: str,
           z_in: float, z_out: float, crisis_level: float) -> BacktestResult:
    """Replay the Schmitt trigger per pair over [from_date, to_date], honoring the crisis gate.
    `stress` is the absolute market-wide correlation level (xcorr.stress_series); the gate fires
    when it reaches crisis_level. Pure over the precomputed z/stress — no store writes (that is
    `run`'s job)."""
    window = z.loc[from_date:to_date]
    dates = window.index
    stressed_mask = stress.reindex(dates) >= crisis_level
    stress_days = [d.date().isoformat() for d in dates[stressed_mask.fillna(False)]]

    firings: list[Firing] = []
    stressed_departures: list[dict] = []

    for pair, lead_id in pairs_leads:
        if pair not in z.columns:
            continue
        state = schmitt.QUIET
        entered = None
        peak = float("-inf")
        for d in dates:
            zv = window.at[d, pair]
            if pd.isna(zv):
                continue
            if bool(stressed_mask.get(d, False)):
                # Stressed day: trigger frozen. A would-be entry is recorded, not acted on.
                if state == schmitt.QUIET and zv >= z_in:
                    stressed_departures.append(
                        {"pair": pair, "date": d.date().isoformat(), "z": float(zv)})
                continue
            new_state, edge = schmitt.step(state, float(zv), z_in, z_out)
            if edge == "entered":
                entered = d.date().isoformat()
                peak = float(zv)
            elif state == schmitt.ACTIVE:
                peak = max(peak, float(zv))
            if edge == "exited" and entered is not None:
                firings.append(Firing(pair, lead_id, entered, d.date().isoformat(), peak))
                entered, peak = None, float("-inf")
            state = new_state
        if entered is not None:  # still active at window end
            firings.append(Firing(pair, lead_id, entered, None, peak))

    return BacktestResult(from_date, to_date, z_in, z_out, firings,
                          stressed_departures, stress_days)


def beta_strip_health(panel: pd.DataFrame, market: str, cfg: dict,
                      windows: list[tuple[str, str, str]]) -> list[dict]:
    """The §4a diagnosis, run BEFORE any threshold sweep: how much does the market-β strip
    reduce mean pairwise correlation, per named window? If residual correlation stays high
    during stress, the strip leaks market beta and every pair lights up on market convulsions
    (mechanism 1: stale/underpowered β) — a broken measure no threshold can fix. If residual
    collapses to ~0 even in a crash, the strip works and the departures are genuinely
    idiosyncratic — then the remaining work is gating/surfacing, not the estimator. Measuring
    this is higher-leverage than the threshold back-off: it says whether you are calibrating a
    sound measure or a broken one."""
    from itertools import combinations
    sectors = [c for c in panel.columns if c != market]
    rets = xcorr.daily_returns(panel)
    betas = xcorr.rolling_beta(rets, market, cfg["windows"]["baseline_days"])
    resid = xcorr.residuals(rets, betas, market)

    def mean_pair_corr(df, a, b):
        sub = df[sectors].loc[a:b]
        c = sub.corr()
        vals = [c.loc[x, y] for x, y in combinations(sectors, 2)]
        return float(np.nanmean(vals))

    out = []
    for label, a, b in windows:
        raw = mean_pair_corr(rets, a, b)
        res = mean_pair_corr(resid, a, b)
        out.append({"window": label, "from": a, "to": b,
                    "raw_mean_corr": round(raw, 3), "residual_mean_corr": round(res, 3),
                    "reduction_pct": round((raw - res) / raw * 100, 1) if raw else None})
    return out


def run(store_root: Path, prices_source: str, prices_date: str, series_ids_path,
        cfg: dict, from_date: str, to_date: str, run_stamp: str,
        z_in: float | None = None, z_out: float | None = None) -> BacktestResult:
    """Full backtest: load frozen prices, compute the z-panel, replay, and write the events
    into a backtest-only store. Returns the BacktestResult (report.py renders the artifact)."""
    from prospector.ingest.prices import PriceIngest, build_panel

    z_in = cfg["xcorr"]["z_in"] if z_in is None else z_in
    z_out = cfg["xcorr"]["z_out"] if z_out is None else z_out
    crisis_level = cfg["xcorr"]["stress"]["crisis_level"]
    market = cfg["universe"]["market"]
    tickers = list(cfg["universe"]["sectors"]) + [market]
    series_ids = load_series_ids(series_ids_path)

    live_layout = StoreLayout(store_root)
    ing = PriceIngest(live_layout)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        panel = build_panel([ing.load_frozen(prices_source, prices_date, t) for t in tickers])
        z, stress = compute_z_and_stress(panel, market, cfg)

    pairs_leads = _pairs_with_series(tickers, series_ids)
    result = replay(z, stress, pairs_leads, from_date, to_date, z_in, z_out, crisis_level)

    # Persist the firing events into a backtest-only store (own root + registry; §7 CONTRACT).
    run_root = backtest_run_root(store_root, run_stamp)
    bt_layout = StoreLayout(run_root, kind="backtest")
    bt_registry = Registry(bt_layout.registry_path())
    store = EventStore(bt_layout, bt_registry)
    try:
        for f in result.firings:
            spawn_ts = f.entered + "T00:00:00Z"
            store.append({"ts": spawn_ts, "lead": f.lead_id, "type": "lead.spawned",
                          "payload": {"spawner": "xcorr", "display": xcorr.pair_display(f.pair),
                                      # display tickers, not series ids — the lead_id itself is
                                      # the series-ID key (xcorr_lead_id); this is for the eye
                                      "display_pair": list(f.pair), "shadow": False},
                          "schema": 1})
            store.append({"ts": spawn_ts, "lead": f.lead_id, "type": "xcorr.departure",
                          "payload": {"display": xcorr.pair_display(f.pair), "z": f.peak_z,
                                      "market_stress": False}, "schema": 1})
            if f.exited is not None:
                store.append({"ts": f.exited + "T00:00:00Z", "lead": f.lead_id,
                              "type": "xcorr.reverted",
                              "payload": {"display": xcorr.pair_display(f.pair)}, "schema": 1})
        for sd in result.stressed_departures:
            store.append({"ts": sd["date"] + "T00:00:00Z", "lead": "_system",
                          "type": "xcorr.departure",
                          "payload": {"display": xcorr.pair_display(sd["pair"]),
                                      "z": sd["z"], "market_stress": True}, "schema": 1})
    finally:
        bt_registry.close()

    result.run_root = run_root
    return result


def sweep(z: pd.DataFrame, stress: pd.Series, pairs_leads, from_date: str, to_date: str,
          grid: list[tuple[float, float]], crisis_level: float) -> list[BacktestResult]:
    """Replay across a (z_in, z_out) grid — the z-panel is fixed, only the trigger moves.
    Feeds the report's threshold-selection section (§10 test 5b: back off from recall-optimal)."""
    return [replay(z, stress, pairs_leads, from_date, to_date, zi, zo, crisis_level)
            for zi, zo in grid]


def stress_diagnostics(z: pd.DataFrame, stress: pd.Series, from_date: str, to_date: str,
                       crisis_level: float, z_in: float,
                       target_pair: tuple[str, str] | None = None) -> dict:
    """How aggressively the crisis gate gates over the window: the stress-level distribution, the
    fraction of days gated, and — the load-bearing stat — how many z>=z_in departures (all pairs,
    and the target pair) were suppressed. `stress` is the absolute market-wide correlation level;
    the gate fires at crisis_level. The recalibration's whole point is that lifting the level from
    0.65 to 0.85 (crisis-only) suppresses far fewer genuine departures than the old gate."""
    win_z = z.loc[from_date:to_date]
    win_stress = stress.reindex(win_z.index)
    gated_mask = win_stress >= crisis_level

    quantiles = {f"p{int(q*100)}": round(float(win_stress.quantile(q)), 3)
                 for q in (0.05, 0.25, 0.5, 0.75, 0.95)}

    # Count z>=z_in departure-days and how many coincided with a stressed (gated) day.
    total_hi = gated_hi = 0
    for pair in win_z.columns:
        hi_days = win_z.index[win_z[pair] >= z_in]
        total_hi += len(hi_days)
        gated_hi += int(gated_mask.reindex(hi_days).fillna(False).sum())

    target = None
    if target_pair is not None and tuple(sorted(target_pair)) in [tuple(c) for c in win_z.columns]:
        tp = tuple(sorted(target_pair))
        hi_days = win_z.index[win_z[tp] >= z_in]
        gated = int(gated_mask.reindex(hi_days).fillna(False).sum())
        target = {"pair": list(tp), "hi_days": len(hi_days), "gated": gated,
                  "first_hi": hi_days[0].date().isoformat() if len(hi_days) else None,
                  "first_hi_gated": bool(gated_mask.reindex(hi_days).fillna(False).iloc[0])
                  if len(hi_days) else None}

    return {
        "crisis_level": crisis_level,
        "quantiles": quantiles,
        "fraction_days_gated": round(float(gated_mask.fillna(False).mean()), 3),
        "z_in": z_in,
        "departure_days_total": total_hi,
        "departure_days_gated": gated_hi,
        "departure_days_gated_fraction": round(gated_hi / total_hi, 3) if total_hi else 0.0,
        "target": target,
    }


def stress_concept_validation(stress: pd.Series, from_date: str, to_date: str,
                              crisis_level: float) -> dict:
    """Validate the recalibrated gate against the CONCEPT, not any known case: it must FIRE during
    recognized market crises and stay QUIET on ordinary elevated-but-calm days. Also characterize
    the onset latency (the bounded leading-edge leak) and — the aging-drift monitor — the margin
    between the recent calm-regime p95 and the frozen crisis_level. These are checks the gate is
    held to; the XLK×XLU lag is only ever read afterward, never targeted."""
    win = stress.loc[from_date:to_date].dropna()

    crises = []
    for c in ACUTE_CRISES:
        seg = stress.loc[c["from"]:c["to"]]
        gated = seg[seg >= crisis_level]
        # onset latency: trading days from the crash proper to the first gate fire at/after it
        after = stress.loc[c["onset"]:c["to"]]
        fired = after[after >= crisis_level]
        onset_lag = gate_rises = None
        if len(fired):
            first_fire = fired.index[0]
            onset_lag = int(after.index.get_loc(first_fire))  # 0 == fires on the onset day
            gate_rises = first_fire.date().isoformat()
        crises.append({
            "label": c["label"], "window": f"{c['from']}..{c['to']}",
            "fires": bool(len(gated)), "gated_days": int(len(gated)),
            "peak_level": round(float(seg.max()), 3) if len(seg) else None,
            "onset": c["onset"], "onset_latency_trading_days": onset_lag,
            "gate_rises": gate_rises})

    sustained = []
    for s in SUSTAINED_REGIMES:
        seg = stress.loc[s["from"]:s["to"]]
        gated_days = int((seg >= crisis_level).sum())
        sustained.append({"label": s["label"], "window": f"{s['from']}..{s['to']}",
                          "peak_level": round(float(seg.max()), 3) if len(seg) else None,
                          "gated_days": gated_days, "correctly_open": gated_days == 0})

    calm = []
    for a in CALM_ANCHORS:
        v = stress.get(pd.Timestamp(a["date"]))
        if v is None or (isinstance(v, float) and np.isnan(v)):
            v = float(stress.reindex([pd.Timestamp(a["date"])], method="ffill").iloc[0])
        calm.append({"label": a["label"], "date": a["date"], "level": round(float(v), 3),
                     "quiet": bool(v < crisis_level)})

    # Aging-drift monitor: absolute levels age. Report the recent calm-regime p95 and its headroom
    # to the frozen gate. If secular co-movement lifts the baseline and this margin compresses, the
    # gate is deliberately RE-FROZEN higher by a human — never via a rolling percentile (that would
    # be baseline-relative in disguise, the rejected form). "Recent" = the last ~2y of the window.
    recent = win.iloc[-504:] if len(win) >= 504 else win
    calm_p95 = float(recent.quantile(0.95))
    aging = {"recent_window_days": len(recent), "calm_p95": round(calm_p95, 3),
             "crisis_level": crisis_level, "headroom": round(crisis_level - calm_p95, 3)}

    return {
        "crisis_level": crisis_level,
        "fraction_days_gated": round(float((win >= crisis_level).mean()), 3),
        "acute_crises": crises,
        "sustained_regimes": sustained,
        "calm_anchors": calm,
        "aging_monitor": aging,
        "all_acute_fire": all(c["fires"] for c in crises),
        "all_sustained_open": all(s["correctly_open"] for s in sustained),
        "all_calm_quiet": all(a["quiet"] for a in calm),
    }
