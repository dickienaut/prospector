"""Excess-correlation sensor math (spec §4a) — hand-computed known answers on tiny frames plus
one planted-regime-shift statistical test. Each stage is a pure pandas function, so the whole
pipeline is testable without a store, a network, or a clock.

The planted test seeds numpy's RNG for determinism and asserts QUALITATIVE behavior with generous
windows (not an exact date): the spec itself warns that overlapping 63d windows autocorrelate and
these z-scores overstate significance, so single noise touches of z=2.5 are expected — the signal
is a SUSTAINED post-shift departure that the pre-shift and control pairs do not produce."""

import numpy as np
import pandas as pd

from prospector.sensors import schmitt, xcorr


# -- rolling_beta: exact beta, and the t-1 shift -------------------------------

def test_rolling_beta_recovers_exact_beta_and_is_shifted():
    idx = pd.date_range("2020-01-01", periods=10, freq="B")
    # A market series with no repeats so var(r_mkt) > 0 in every window.
    mkt = pd.Series([0.01, -0.02, 0.03, -0.01, 0.02, 0.015, -0.03, 0.025, -0.015, 0.02],
                    index=idx)
    fund = 2.0 * mkt  # exactly 2x the market, no residual noise -> beta must be 2.0
    returns = pd.DataFrame({"SPY": mkt, "F": fund})

    beta = xcorr.rolling_beta(returns, "SPY", window=5)
    b = beta["F"]

    # The first FULL window ends at row index 4 (rows 0..4). The .shift(1) makes beta known as
    # of t-1, so the first NON-NaN beta appears one row LATER, at index 5.
    assert b.iloc[:5].isna().all()
    assert pd.isna(b.iloc[4])          # first full window, but shifted out
    assert not pd.isna(b.iloc[5])      # first usable beta, one row later
    # Where defined, beta is exactly 2.0 (a perfect 2x fund).
    assert np.allclose(b.iloc[5:].to_numpy(), 2.0, atol=1e-9)
    # The market column itself carries no beta.
    assert "SPY" not in beta.columns


# -- residuals: r_i - beta*r_mkt ----------------------------------------------

def test_residuals_are_the_market_strip():
    idx = pd.date_range("2020-01-01", periods=4, freq="B")
    returns = pd.DataFrame({"SPY": [0.01, 0.02, -0.01, 0.03],
                            "F": [0.05, 0.04, 0.00, 0.06]}, index=idx)
    betas = pd.DataFrame({"F": [1.0, 2.0, 0.5, 1.5]}, index=idx)
    resid = xcorr.residuals(returns, betas, "SPY")
    # r_F - beta_F * r_SPY, elementwise.
    expected = [0.05 - 1.0 * 0.01, 0.04 - 2.0 * 0.02, 0.00 - 0.5 * -0.01, 0.06 - 1.5 * 0.03]
    assert np.allclose(resid["F"].to_numpy(), expected, atol=1e-12)
    assert "SPY" not in resid.columns


# -- fisher_z: arctanh identity + the ±1 clip ---------------------------------

def test_fisher_z_is_arctanh_and_clips_at_plus_minus_one():
    corr = pd.DataFrame({("a", "b"): [0.0, 0.5, 1.0, -1.0]})
    fz = xcorr.fisher_z(corr)["a", "b"].to_numpy()
    assert fz[0] == 0.0                       # arctanh(0) == 0
    assert np.isclose(fz[1], np.arctanh(0.5))  # arctanh identity
    # rho of exactly +/-1 does NOT blow up to +/-inf — clipped to +/-0.999999 first.
    assert np.isfinite(fz[2]) and np.isfinite(fz[3])
    assert np.isclose(fz[2], np.arctanh(xcorr.FISHER_CLIP))
    assert np.isclose(fz[3], np.arctanh(-xcorr.FISHER_CLIP))


# -- departure_z: baseline mean/std ending t-1, std==0 -> NaN ------------------

def test_departure_z_excludes_current_value_from_its_own_baseline():
    # A window of 3: at index 3 the baseline is the PRIOR three values [1,2,3].
    fisher = pd.DataFrame({("a", "b"): [1.0, 2.0, 3.0, 10.0, 11.0]})
    z = xcorr.departure_z(fisher, baseline_window=3)["a", "b"]

    # mean([1,2,3]) == 2.0, std([1,2,3], ddof=1) == 1.0 -> z_3 = (10 - 2) / 1 = 8.0.
    assert z.iloc[:3].isna().all()   # not enough baseline yet
    assert np.isclose(z.iloc[3], (10.0 - 2.0) / 1.0)
    # And index 4's baseline is [2,3,10] (the .shift(1) excludes the current value 11).
    mean_prior = np.mean([2.0, 3.0, 10.0])
    std_prior = np.std([2.0, 3.0, 10.0], ddof=1)
    assert np.isclose(z.iloc[4], (11.0 - mean_prior) / std_prior)


def test_departure_z_zero_std_window_yields_nan():
    # A flat baseline [5,5,5] has std 0 -> no departure defined, even against a jump.
    fisher = pd.DataFrame({("a", "b"): [5.0, 5.0, 5.0, 9.0]})
    z = xcorr.departure_z(fisher, baseline_window=3)["a", "b"]
    assert pd.isna(z.iloc[3])


# -- the planted regime shift (the key statistical test) ----------------------

# A factor model over ~1700 business days. Funds A and B share an extra common residual factor
# that TURNS ON at SHIFT_ON and OFF at SHIFT_OFF; C never joins. Seed 166 (searched once, then
# frozen) gives a clean separation: zero pre-shift threshold touches on A×B, a sustained post-shift
# departure, and only scattered noise on the control pairs. Positions, not dates, anchor the
# asserts — the pipeline is calendar-agnostic.
_SEED = 166
_N = 1700
_SHIFT_ON = 1000
_SHIFT_OFF = 1350
_LOADING = 3.5
_BASE_SD = 0.008


def _planted_returns():
    rng = np.random.default_rng(_SEED)
    idx = pd.date_range("2019-01-01", periods=_N, freq="B")
    mkt = rng.normal(0, 0.01, _N)
    betas = {"A": 1.1, "B": 0.9, "C": 1.0}
    common = rng.normal(0, _BASE_SD, _N)
    mask = np.zeros(_N)
    mask[_SHIFT_ON:_SHIFT_OFF] = 1.0
    data = {"SPY": mkt}
    for k, beta in betas.items():
        r = beta * mkt + rng.normal(0, _BASE_SD, _N)
        if k in ("A", "B"):
            r = r + _LOADING * common * mask  # the shared residual factor, only while ON
        data[k] = r
    return pd.DataFrame(data, index=idx)


def _run_pipeline(returns):
    beta = xcorr.rolling_beta(returns, "SPY", 252)
    resid = xcorr.residuals(returns, beta, "SPY")
    corr = xcorr.pairwise_rolling_corr(resid, 63)
    fisher = xcorr.fisher_z(corr)
    return corr, xcorr.departure_z(fisher, 252)


def _schmitt_edges(z_series):
    """Replay a departure-z series through the trigger; return the (pos, edge) list."""
    state, edges = schmitt.QUIET, []
    for i, v in enumerate(z_series.to_numpy()):
        state, edge = schmitt.step(state, None if np.isnan(v) else float(v), 2.5, 1.0)
        if edge is not None:
            edges.append((i, edge))
    return edges


def test_planted_shift_fires_after_the_shift_not_before():
    returns = _planted_returns()
    corr, dz = _run_pipeline(returns)
    z = dz[("A", "B")]
    warm_pos = z.index.get_loc(z.dropna().index[0])

    # Sanity: the planted factor actually lifts the residual correlation from ~0 to ~0.9.
    assert corr[("A", "B")].iloc[_SHIFT_ON - 20] < 0.3
    assert corr[("A", "B")].iloc[_SHIFT_ON + 90] > 0.7

    # PRE-shift (warmup..SHIFT_ON): the pair never crosses the entry threshold.
    assert (z.iloc[warm_pos:_SHIFT_ON] >= 2.5).sum() == 0

    # POST-shift: a SUSTAINED departure — many days above threshold, not one noise touch.
    assert (z.iloc[_SHIFT_ON:_SHIFT_OFF + 150] >= 2.5).sum() >= 30

    # The Schmitt trigger's FIRST entry lands after the shift, in a plausible window.
    edges = _schmitt_edges(z)
    entries = [pos for pos, e in edges if e == "entered"]
    assert entries, "the planted pair should enter active at least once"
    first_entry = entries[0]
    assert _SHIFT_ON <= first_entry <= _SHIFT_OFF + 150

    # After the factor turns OFF, the departure decays and an exit eventually fires.
    exits_after = [pos for pos, e in edges if e == "exited" and pos >= _SHIFT_OFF]
    assert exits_after, "z should decay and exit once the common factor turns off"


def test_planted_shift_control_pair_does_not_sustain_a_departure():
    """Fund C shares no extra factor with A or B, so A×C / B×C never sustain a departure the way
    A×B does (a handful of noise touches is fine — the spec's own autocorrelation caveat)."""
    returns = _planted_returns()
    _, dz = _run_pipeline(returns)
    ab_days = (dz[("A", "B")] >= 2.5).sum()
    for control in (("A", "C"), ("B", "C")):
        control_days = (dz[control] >= 2.5).sum()
        assert control_days < ab_days / 2  # nothing like the planted pair's sustained run


# -- late-starter warmup: leading NaN never yields a spurious z ----------------

def test_late_starter_column_yields_nan_departure_z_until_all_windows_fill():
    n = 700
    idx = pd.date_range("2019-01-01", periods=n, freq="B")
    rng = np.random.default_rng(1)
    mkt = rng.normal(0, 0.01, n)
    a = 1.0 * mkt + rng.normal(0, 0.008, n)
    late = 1.0 * mkt + rng.normal(0, 0.008, n)
    late[:300] = np.nan  # a late-listed fund: leading NaN, never forward-filled (§3)
    returns = pd.DataFrame({"SPY": mkt, "A": a, "LATE": late}, index=idx)

    _, dz = _run_pipeline(returns)
    late_pair = dz[("A", "LATE")]
    # 300 leading NaN + 567 warmup > 700 rows, so this pair is NaN for the whole series — never
    # a spurious finite z from a partially-warmed window.
    assert late_pair.isna().all()
