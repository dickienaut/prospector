"""Dispersion pure pipeline (spec §4b): the bipartition, cluster quality Q, and the Q departure-z.
Offline, deterministic — no store, no clock, no network. The reuse of xcorr.departure_z is asserted
directly (dispersion delegates the (Q_t - baseline)/std machinery, no fork)."""

import numpy as np
import pandas as pd
import pytest

from prospector.sensors import dispersion, xcorr

# An explicit two-block correlation matrix: {x1,x2} cohere, {y1,y2} cohere, cross-block loose.
BLOCK_CORR = pd.DataFrame(
    [[1.0, 0.9, 0.1, 0.1],
     [0.9, 1.0, 0.1, 0.1],
     [0.1, 0.1, 1.0, 0.8],
     [0.1, 0.1, 0.8, 1.0]],
    index=["x1", "x2", "y1", "y2"], columns=["x1", "x2", "y1", "y2"])


def _two_regime_panel(n_days=340, split_at=270, seed=0):
    """A constituent PRICE panel with a late fracture. Pre-split all six names load on one common
    factor only (a single block: within ~ between, Q~0). Post-split they keep the common factor AND
    each half picks up its own block factor, so within-block correlation rises above between-block
    (Q > 0). The retained common factor gives a clean leading eigenvector (uniform), so the SECOND
    eigenvector is the A-vs-B contrast that sign-splits the two blocks cleanly — avoiding the
    equal-eigenvalue degeneracy of two fully-independent blocks."""
    rng = np.random.default_rng(seed)
    ids = ["A1", "A2", "A3", "B1", "B2", "B3"]
    dates = pd.bdate_range("2023-01-02", periods=n_days)
    common = rng.normal(0, 0.010, n_days)
    fac = {"A": rng.normal(0, 0.012, n_days), "B": rng.normal(0, 0.012, n_days)}
    data = {}
    for cid in ids:
        idio = rng.normal(0, 0.002, n_days)
        r = common + idio                              # pre-split: common only
        block = np.zeros(n_days)
        block[split_at:] = fac[cid[0]][split_at:]      # post-split: add the block factor
        data[cid] = r + block
    returns = pd.DataFrame(data, index=dates)
    prices = (1 + returns).cumprod() * 100.0   # sensor recovers returns via pct_change
    return ids, prices


def test_spectral_bipartition_recovers_the_two_blocks():
    labels = dispersion.spectral_bipartition(BLOCK_CORR)
    assert labels["x1"] == labels["x2"]          # the x-block is one cluster
    assert labels["y1"] == labels["y2"]          # the y-block is the other
    assert labels["x1"] != labels["y1"]          # and they are distinct
    assert labels["x1"] == 0                     # canonical: top-weighted (col 0) -> cluster 0


def test_spectral_bipartition_is_deterministic():
    # Eigenvector sign is arbitrary from eigh; the canonicalization must make labels reproducible
    # (a stable SHA-256 of the payload depends on it).
    assert dispersion.spectral_bipartition(BLOCK_CORR) == dispersion.spectral_bipartition(BLOCK_CORR)


def test_cluster_quality_is_within_minus_between():
    labels = dispersion.spectral_bipartition(BLOCK_CORR)
    # within means: {x:0.9, y:0.8} -> 0.85; between: mean of four 0.1 cross pairs -> 0.1; Q = 0.75.
    assert dispersion.cluster_quality(BLOCK_CORR, labels) == pytest.approx(0.75, abs=1e-9)


def test_cluster_quality_degenerate_split_is_nan():
    # A one-block labelling (no between pairs) -> Q undefined.
    labels = {"x1": 0, "x2": 0, "y1": 0, "y2": 0}
    assert np.isnan(dispersion.cluster_quality(BLOCK_CORR, labels))


def test_corr_matrix_at_drops_underwarmed_constituents():
    dates = pd.bdate_range("2023-01-02", periods=80)
    rng = np.random.default_rng(1)
    full = rng.normal(0, 0.01, 80)
    late = np.concatenate([np.full(50, np.nan), rng.normal(0, 0.01, 30)])  # lists late
    returns = pd.DataFrame({"A": full, "B": full * 0.9 + rng.normal(0, 0.003, 80),
                            "C": late}, index=dates)
    corr = dispersion.corr_matrix_at(returns, dates[-1], window=63)
    # C has only 30 of the last 63 observations -> dropped from that day's matrix (§3, no fill).
    assert list(corr.columns) == ["A", "B"]


def test_dispersion_z_delegates_to_departure_z():
    rng = np.random.default_rng(2)
    q = pd.Series(np.linspace(0.1, 0.6, 300) + rng.normal(0, 0.01, 300),
                  index=pd.bdate_range("2022-01-03", periods=300))
    z = dispersion.dispersion_z(q, baseline_window=252)
    expected = xcorr.departure_z(q.to_frame(name="Q"), 252)["Q"]
    pd.testing.assert_series_equal(z, expected)
    assert not np.isnan(z.iloc[-1])  # warmed at the tail


def test_dispersion_q_series_nan_before_warmup_finite_after():
    _ids, prices = _two_regime_panel()
    returns = dispersion.constituent_returns(prices)
    q = dispersion.dispersion_q_series(returns, window=63, min_constituents=4)
    assert np.isnan(q.iloc[0])          # no window yet
    assert not np.isnan(q.iloc[-1])     # a warmed two-block regime -> finite Q
    assert q.iloc[-1] > 0.2             # the late fracture shows as elevated Q


def test_dispersion_lead_id_keys_on_series_id():
    lid = dispersion.dispersion_lead_id("S000006415")
    assert lid.startswith("disp-") and len(lid) == len("disp-") + 10
    assert lid == dispersion.dispersion_lead_id("S000006415")       # stable
    assert lid != dispersion.dispersion_lead_id("S000006416")       # series-id-derived
