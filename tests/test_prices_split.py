"""P1 verification: Tiingo's `adjClose` is genuinely split-adjusted (spec §3, guard_live_source).

This is the proof that lets `prices.tiingo_adjusted_verified` flip true — the antidote to the
convergent-prior trap the repo keeps catching (assuming a source's `close` is adjusted without checking).
Unlike Stooq (an assumed-adjusted close with NOTHING to check it against), Tiingo ships the corporate-action
truth WITH the prices: the recorded-real NVDA EOD array across the 2024-06-10 10:1 split carries raw `close`,
`adjClose`, AND `splitFactor` in the same rows.

The test is FALSIFYING by construction (continuity alone is not — an unsplit stock is also continuous). Three
legs on the SAME fixture rows: (1) `adjClose` stays continuous across the ex-date; (2) the raw `close` in the
same body DOES break ~10x there — the leg that proves the parser selected the adjusted field, not raw close;
(3) `splitFactor`≈10 sits on the 2024-06-10 ex-date row. Fixture provenance: the `.source.txt` sidecar.
"""

import json
from pathlib import Path

import numpy as np

from prospector.ingest.prices import parse_tiingo

FIXTURE = Path(__file__).parent / "fixtures" / "prices" / "nvda_tiingo_2024-split.json"
EX_DATE = "2024-06-10"  # NVDA's 10:1 split — first day trading split-adjusted


def _max_abs_log_step(values) -> float:
    """The largest single-day |log(ratio)| — a scale-free 'biggest jump' (a 10:1 split is a ~10x DROP,
    so we test the ABSOLUTE step, never a directional jump)."""
    v = np.asarray(values, dtype="float64")
    return float(np.max(np.abs(np.diff(np.log(v)))))


def test_tiingo_adjclose_continuous_across_nvda_split():
    body = FIXTURE.read_bytes()
    rows = json.loads(body)
    dates = [str(r["date"])[:10] for r in rows]
    assert EX_DATE in dates, "fixture must span the 2024-06-10 ex-date"
    i = dates.index(EX_DATE)

    # Leg 1 — adjClose is CONTINUOUS across the split: parse via the real parser (which reads adjClose),
    # and assert no single-day step is anywhere near a 10x break (the largest real daily move here is ~5%).
    frame = parse_tiingo(body, "NVDA")
    assert _max_abs_log_step(frame["close_adj"]) < 0.5  # ~0.05 in fact; nowhere near log(10)=2.30

    # Leg 2 — the RAW close in the SAME body DOES break ~10x at the ex-date. This is the falsifying leg:
    # it proves parse_tiingo selected `adjClose`, not `close` (an unadjusted feed would fail leg 1 here).
    close = [float(r["close"]) for r in rows]
    step_across_split = abs(np.log(close[i] / close[i - 1]))  # 2024-06-07 -> 2024-06-10
    assert step_across_split > 1.0                            # ~2.30 (a 10x drop); assert MAGNITUDE, not sign
    # And adjClose across that very same boundary is calm — the split vanished from the adjusted series.
    adj = [float(r["adjClose"]) for r in rows]
    assert abs(np.log(adj[i] / adj[i - 1])) < 0.1

    # Leg 3 — splitFactor≈10 sits on the ex-date row specifically, and is ~1 everywhere else.
    assert rows[i]["splitFactor"] == 10.0
    assert all(r["splitFactor"] == 1.0 for j, r in enumerate(rows) if j != i)
