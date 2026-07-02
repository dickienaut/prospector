"""Market-stress annotation (spec §4a CONTRACT): the mean, across all pairs, of the rolling
`window`-day RAW pairwise correlation. Above stress_corr_threshold (DEFAULT 0.65) departures are
still recorded but do not spawn leads or page — losing paging in a crash week is free. Computed on
raw returns, not residuals: it measures gross comovement (everything moving together)."""

import numpy as np
import pandas as pd

from prospector.sensors import xcorr

STRESS_THRESHOLD = 0.65  # DEFAULT xcorr.stress_corr_threshold


def _panel_with_crash_window():
    """A raw-returns panel: independent noise everywhere, except a known crash window where a huge
    common shock is added to EVERY fund on those days (so all pairwise correlations -> ~1)."""
    n = 260
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    rng = np.random.default_rng(2026)
    funds = ["F1", "F2", "F3", "F4", "F5"]
    data = {f: rng.normal(0.0, 0.01, n).copy() for f in funds}

    crash = slice(150, 190)                      # the known crash window
    shock = rng.normal(0.0, 0.05, n)             # a single common shock series
    for f in funds:
        # The common shock dwarfs each fund's idiosyncratic noise on crash days -> corr ~ 1.
        data[f][crash] = data[f][crash] + 6.0 * shock[crash]

    return pd.DataFrame(data, index=idx), idx, crash


def test_stress_series_is_one_value_per_date_indexed_like_the_input():
    raw, idx, _ = _panel_with_crash_window()
    s = xcorr.stress_series(raw, 21)
    assert isinstance(s, pd.Series)
    assert len(s) == len(raw)
    assert s.index.equals(idx)


def test_stress_exceeds_threshold_across_the_crash_window():
    raw, idx, crash = _panel_with_crash_window()
    s = xcorr.stress_series(raw, 21)

    # The 21d window trails, so elevated stress covers a SUPERSET of the crash days: once the
    # window has slid fully into the shock, every pairwise correlation is ~1 -> mean well over
    # threshold. Check the tail of the crash window where the window is saturated.
    window_saturated = s.iloc[crash.start + 21:crash.stop]
    assert (window_saturated > STRESS_THRESHOLD).all()
    assert window_saturated.max() > 0.9


def test_stress_stays_below_threshold_in_a_calm_segment():
    raw, idx, crash = _panel_with_crash_window()
    s = xcorr.stress_series(raw, 21)

    # A calm segment built from independent returns, comfortably before the crash window's
    # trailing 21d window can reach back into it.
    calm = s.iloc[40:crash.start - 21].dropna()
    assert len(calm) > 0
    assert (calm < STRESS_THRESHOLD).all()
