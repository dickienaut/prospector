"""Market-stress crisis gate (spec §4a CONTRACT), recalibrated 2026-07-02 to an ABSOLUTE level.

The gate signal is xcorr.stress_series — the mean, across all pairs, of the rolling `window`-day
RAW pairwise correlation (gross comovement). The gate fires when this LEVEL reaches crisis_level
(0.85). Departures on a gated day are recorded but do not spawn leads or page — losing paging in a
crash week is free. Absolute, not baseline-relative: market-wide correlation is a fragility gauge
whose intrinsic level IS the signal (see the decisions note). These tests pin: the level detects a
crash, an ordinary-elevated-but-calm regime does NOT trip the crisis level (the recalibration's
whole point), and the runner's concept-validation (acute fires / sustained open / calm quiet /
aging monitor)."""

import numpy as np
import pandas as pd

from prospector.backtest import runner
from prospector.sensors import xcorr

CRISIS_LEVEL = 0.85   # DEFAULT xcorr.stress.crisis_level (frozen)


def _panel_with_crash_window():
    """Independent noise everywhere, except a known crash window where a huge common shock is added
    to EVERY fund (so all pairwise correlations -> ~1, level well above the crisis level)."""
    n = 260
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    rng = np.random.default_rng(2026)
    funds = ["F1", "F2", "F3", "F4", "F5"]
    data = {f: rng.normal(0.0, 0.01, n).copy() for f in funds}
    crash = slice(150, 190)
    shock = rng.normal(0.0, 0.05, n)
    for f in funds:
        data[f][crash] = data[f][crash] + 6.0 * shock[crash]
    return pd.DataFrame(data, index=idx), idx, crash


def test_stress_series_is_one_value_per_date_indexed_like_the_input():
    raw, idx, _ = _panel_with_crash_window()
    s = xcorr.stress_series(raw, 21)
    assert isinstance(s, pd.Series)
    assert len(s) == len(raw)
    assert s.index.equals(idx)


def test_level_reaches_crisis_level_in_a_crash():
    raw, idx, crash = _panel_with_crash_window()
    s = xcorr.stress_series(raw, 21)
    # Once the 21d window has slid fully into the shock, every pairwise correlation is ~1.
    window_saturated = s.iloc[crash.start + 21:crash.stop]
    assert (window_saturated >= CRISIS_LEVEL).all()
    assert window_saturated.max() > 0.9


def test_ordinary_elevated_but_calm_regime_does_not_trip_the_crisis_level():
    """The recalibration's whole point: a moderately-elevated correlation regime (like the real
    sector baseline ~0.5-0.7, or the 2023-01-25 day at 0.69) must NOT gate at 0.85 — only genuine
    crises do. Build a persistently elevated-but-sub-crisis regime and assert it stays open."""
    n = 200
    idx = pd.date_range("2021-01-01", periods=n, freq="B")
    rng = np.random.default_rng(7)
    funds = ["F1", "F2", "F3", "F4", "F5"]
    # A shared factor lifts pairwise correlation into the ~0.65 band (like the real sector
    # baseline / the 2023-01-25 anchor at 0.69) without reaching 1: corr ≈ vc/(vc+vi) with
    # vc=0.013², vi=0.009² -> ~0.68.
    common = rng.normal(0.0, 0.013, n)
    data = {f: (common + rng.normal(0.0, 0.009, n)) for f in funds}
    s = xcorr.stress_series(pd.DataFrame(data, index=idx), 21).dropna()
    assert len(s) > 0
    assert 0.5 < s.median() < CRISIS_LEVEL   # genuinely an elevated regime (like ~0.65-0.7)...
    assert (s < CRISIS_LEVEL).all()          # ...yet never trips the crisis gate


def test_stress_stays_below_crisis_in_a_calm_segment():
    raw, idx, crash = _panel_with_crash_window()
    s = xcorr.stress_series(raw, 21)
    calm = s.iloc[40:crash.start - 21].dropna()
    assert len(calm) > 0
    assert (calm < CRISIS_LEVEL).all()


def test_concept_validation_acute_fires_sustained_open_calm_quiet_with_bounded_onset():
    """The runner's concept validation over a synthetic series with one acute crash and one
    sustained-but-sub-crisis regime: the acute one fires with a finite onset latency, the sustained
    one stays open, a calm anchor stays quiet, and the aging monitor reports a headroom."""
    # Build a long daily level series by hand (dates as a business-day index).
    idx = pd.date_range("2019-06-03", periods=900, freq="B")
    level = pd.Series(0.50, index=idx)                       # calm baseline
    # An acute crash: level ramps 0.50 -> 0.95 over ~5 days starting at a known onset, holds, decays.
    onset_pos = 180
    for k, v in enumerate([0.60, 0.70, 0.82, 0.90, 0.95, 0.95, 0.94, 0.92]):
        level.iloc[onset_pos + k] = v
    onset = idx[onset_pos].date().isoformat()
    # A sustained but sub-crisis regime later (0.78, below 0.85 -> must stay open).
    level.iloc[500:560] = 0.78
    sustained_from, sustained_to = idx[500].date().isoformat(), idx[559].date().isoformat()
    calm_date = idx[700].date().isoformat()                 # stays at 0.50

    # Point the runner's anchors at this synthetic series, then validate.
    orig_acute, orig_sust, orig_calm = (runner.ACUTE_CRISES, runner.SUSTAINED_REGIMES,
                                        runner.CALM_ANCHORS)
    try:
        runner.ACUTE_CRISES = [{"label": "synthetic crash", "from": onset,
                                "to": idx[onset_pos + 30].date().isoformat(), "onset": onset}]
        runner.SUSTAINED_REGIMES = [{"label": "synthetic grind", "from": sustained_from,
                                     "to": sustained_to}]
        runner.CALM_ANCHORS = [{"label": "calm", "date": calm_date}]
        v = runner.stress_concept_validation(level, idx[0].date().isoformat(),
                                             idx[-1].date().isoformat(), CRISIS_LEVEL)
    finally:
        runner.ACUTE_CRISES, runner.SUSTAINED_REGIMES, runner.CALM_ANCHORS = (
            orig_acute, orig_sust, orig_calm)

    assert v["all_acute_fire"] is True
    ac = v["acute_crises"][0]
    assert ac["fires"] and ac["onset_latency_trading_days"] is not None
    assert 0 <= ac["onset_latency_trading_days"] <= 8          # bounded leading-edge leak
    assert ac["gate_rises"] is not None
    assert v["all_sustained_open"] is True                     # 0.78 regime never gated at 0.85
    assert v["all_calm_quiet"] is True
    assert v["aging_monitor"]["headroom"] > 0                  # calm p95 sits below the gate


def test_runner_replay_gates_a_crash_day_and_records_a_stressed_departure():
    """End-to-end on the pure replay: a pair whose z crosses z_in on a gated (crisis-level) day is
    recorded as a stressed departure and does NOT spawn; the same z on an ungated day spawns."""
    idx = pd.date_range("2020-01-01", periods=6, freq="B")
    pair = ("XLK", "XLU")
    z = pd.DataFrame({pair: [0.0, 3.0, 0.0, 0.0, 3.0, 0.0]}, index=idx)
    z.columns = pd.MultiIndex.from_tuples(z.columns)
    stress = pd.Series([0.5, 0.90, 0.5, 0.5, 0.5, 0.5], index=idx)   # day 1 is a crisis day
    res = runner.replay(z, stress, [(pair, "xcorr-abc0000000")],
                        idx[0].date().isoformat(), idx[-1].date().isoformat(),
                        z_in=2.5, z_out=1.0, crisis_level=CRISIS_LEVEL)
    # Day 1 (z=3.0 but gated) -> recorded stressed, no spawn. Day 4 (z=3.0, ungated) -> spawns.
    assert len(res.stressed_departures) == 1
    assert res.stressed_departures[0]["date"] == idx[1].date().isoformat()
    assert len(res.firings) == 1
    assert res.firings[0].entered == idx[4].date().isoformat()


# -- rev5 §10.5c(iii): crash-window spawn reversion + phase -----------------------------------

def test_crash_falsification_phases_and_reversion():
    """A crash-window spawn is 'free' only if it reverts within crash_revert_weeks. The classifier
    labels each spawn's phase (pre-onset / onset / peak / recovery-tail) and flags any that persist."""
    crash_from, crash_to = "2020-02-15", "2020-04-30"
    onset, gate_rises = "2020-02-24", "2020-03-02"   # gate rises 5 trading days after the onset
    # A stress level that is >=0.85 only across the acute peak (Mar 02 .. Apr 10) -> gate_releases.
    idx = pd.bdate_range(crash_from, crash_to)
    level = pd.Series(0.55, index=idx)
    level.loc["2020-03-02":"2020-04-10"] = 0.92
    Firing = runner.Firing
    firings = [
        Firing(("XLF", "XLP"), "l1", "2020-02-18", "2020-03-10", 3.0),   # pre-onset, reverts 3wk
        Firing(("XLF", "XLU"), "l2", "2020-02-28", "2020-07-10", 3.0),   # onset, persists ~19wk
        Firing(("XLV", "XLY"), "l3", "2020-02-28", "2020-04-01", 3.0),   # onset, reverts ~4.4wk
        Firing(("XLB", "XLF"), "l4", "2020-04-16", None, 3.0),           # recovery-tail, still active
    ]
    res = runner.BacktestResult(crash_from, crash_to, 2.5, 1.0, firings, [], [])
    cf = runner.crash_falsification(res, level, CRISIS_LEVEL, crash_from, crash_to,
                                    onset, gate_rises, crash_revert_weeks=8)

    by_pair = {s["display"]: s for s in cf["spawns"]}
    assert by_pair["XLF×XLP"]["phase"] == "pre-onset"
    assert by_pair["XLF×XLU"]["phase"] == "onset"
    assert by_pair["XLV×XLY"]["phase"] == "onset"
    assert by_pair["XLB×XLF"]["phase"] == "recovery-tail"     # entered after gate_releases (Apr 10)
    # reversion flags: the ~19wk and the still-active one persist; the 3wk / 4.4wk revert.
    assert by_pair["XLF×XLP"]["reverted_within"] is True
    assert by_pair["XLV×XLY"]["reverted_within"] is True
    assert by_pair["XLF×XLU"]["reverted_within"] is False
    assert by_pair["XLB×XLF"]["reverted_within"] is False
    assert by_pair["XLB×XLF"]["revert_weeks"] is None         # None == still active == persistent
    assert cf["n_spawns"] == 4 and cf["n_persistent"] == 2
    assert cf["all_transient"] is False


def test_crash_falsification_all_transient_when_every_spawn_reverts_fast():
    crash_from, crash_to = "2020-02-15", "2020-04-30"
    idx = pd.bdate_range(crash_from, crash_to)
    level = pd.Series(0.55, index=idx)
    level.loc["2020-03-02":"2020-03-20"] = 0.92
    Firing = runner.Firing
    firings = [Firing(("XLK", "XLU"), "l1", "2020-02-25", "2020-03-10", 3.0)]  # reverts ~2wk
    res = runner.BacktestResult(crash_from, crash_to, 2.5, 1.0, firings, [], [])
    cf = runner.crash_falsification(res, level, CRISIS_LEVEL, crash_from, crash_to,
                                    "2020-02-24", "2020-03-02", crash_revert_weeks=8)
    assert cf["all_transient"] is True and cf["n_persistent"] == 0


# -- rev5 §4a: aging monitor pinned to the CALM-REGIME p95 (crisis days excluded) --------------

def test_aging_monitor_uses_calm_regime_p95_excluding_crisis_days():
    """The aging monitor must measure the CALM baseline, not the all-days distribution. A recent
    window with a crisis excursion must not let the crisis days inflate the p95 — crisis days
    (level >= crisis_level) are excluded, so the reported calm p95 stays near the calm baseline."""
    idx = pd.bdate_range("2022-01-01", periods=700)          # > 504 so 'recent' is the last 2y
    rng = np.random.default_rng(3)
    level = pd.Series(0.55 + 0.05 * rng.standard_normal(700), index=idx).clip(0.2, 0.83)
    level.iloc[-60:-40] = 0.95                                # a recent crisis excursion (gated)
    v = runner.stress_concept_validation(level, idx[0].date().isoformat(),
                                         idx[-1].date().isoformat(), CRISIS_LEVEL)
    ag = v["aging_monitor"]
    # Calm p95 excludes the 0.95 crisis days, so it stays near the calm baseline (well under gate),
    # and the crisis days are counted out of the calm-regime day count.
    assert ag["calm_p95"] < CRISIS_LEVEL
    assert ag["calm_p95"] < 0.85 and ag["headroom"] > 0
    assert ag["calm_regime_days"] < ag["recent_window_days"]   # crisis days were excluded
    # A naive all-days p95 over the same recent window WOULD be inflated by the 0.95 days.
    naive_p95 = float(level.iloc[-504:].quantile(0.95))
    assert naive_p95 > ag["calm_p95"]
