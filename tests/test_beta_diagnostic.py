"""Guards the crash-flags diagnostic's discriminator (prospector/backtest/beta_diagnostic.py). The
load-bearing claim is that a residual decoupling COLLAPSES under a faster β iff it was a stale-β
artifact. We plant both cases and assert the flag, so "box A ruled out" can never silently rot."""

import numpy as np
import pandas as pd

from prospector.backtest import beta_diagnostic as bd


def _window(idx, start_pos, length):
    return idx[start_pos].date().isoformat(), idx[start_pos + length].date().isoformat()


def test_scoped_slice_flags_a_planted_stale_beta_artifact():
    """Both funds' true β jumps at a break. The 252d production β stays stale for months, so its
    residuals carry uncorrected market beta and correlate spuriously; a faster β adapts and the
    correlation collapses -> collapses=True (box A)."""
    n = 820
    idx = pd.bdate_range("2017-06-01", periods=n)
    rng = np.random.default_rng(11)
    mkt = rng.normal(0, 0.01, n)
    beta = np.where(np.arange(n) < 550, 1.0, 3.0)          # a sharp β regime break at day 550
    a = beta * mkt + rng.normal(0, 0.002, n)               # tiny idiosyncratic noise
    b = beta * mkt + rng.normal(0, 0.002, n)
    panel = pd.DataFrame({"SPY": (1 + pd.Series(mkt)).cumprod().values,
                          "A": (1 + pd.Series(a)).cumprod().values,
                          "B": (1 + pd.Series(b)).cumprod().values}, index=idx)
    # A window >63d past the break: the short β has fully cleared the break across the whole 63d
    # correlation window, while the 252d production β is still stale (blends pre/post-break).
    lo, hi = _window(idx, 680, 80)
    rows = bd.scoped_beta_slice(panel, "SPY", [("A", "B")], lo, hi)
    r = rows[0]
    assert abs(r["prod_beta_corr"]) > 0.3                   # spuriously correlated under stale β
    assert r["collapses"] is True                           # ...and it collapses under a faster β


def test_scoped_slice_does_not_flag_a_genuine_residual_decoupling():
    """Stable β throughout, but a real shared idiosyncratic factor couples the two residuals. It is
    unchanged under a faster β -> collapses=False (box B/C — the actual March-2020 finding)."""
    n = 820
    idx = pd.bdate_range("2017-06-01", periods=n)
    rng = np.random.default_rng(12)
    mkt = rng.normal(0, 0.01, n)
    shared = rng.normal(0, 0.008, n)                        # a genuine common residual factor
    a = 1.0 * mkt + shared + rng.normal(0, 0.003, n)
    b = 1.0 * mkt + shared + rng.normal(0, 0.003, n)        # stable β, real residual coupling
    panel = pd.DataFrame({"SPY": (1 + pd.Series(mkt)).cumprod().values,
                          "A": (1 + pd.Series(a)).cumprod().values,
                          "B": (1 + pd.Series(b)).cumprod().values}, index=idx)
    lo, hi = _window(idx, 600, 90)
    rows = bd.scoped_beta_slice(panel, "SPY", [("A", "B")], lo, hi)
    r = rows[0]
    assert r["prod_beta_corr"] > 0.4                        # genuinely correlated residuals
    assert r["collapses"] is False                          # ...and a faster β does not change it
    assert r["max_delta"] < 0.15                            # essentially unchanged, like the 7 flags
