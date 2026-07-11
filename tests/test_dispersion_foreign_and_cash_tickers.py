"""§9e constituent-symbol resolution — the acceptance gate for Claude Science's QA finding
(`docs/notes/dispersion_foreign_ticker_findings.md`), adjudicated in
`docs/decisions/2026-07-10-9e-constituent-symbol-resolution.md`.

THE BUG: `_run_dispersion` pulls each constituent's price BY THE SPDR FILE'S TICKER, then re-keys the
panel to CUSIP. The pull trusts the ticker to be a valid, unique, US-listed Tiingo symbol — but the
recorded-real TEKX file breaks that three ways inside the 0.90 cut:
  - `ENR` (Siemens Energy AG, EUR) is a FOREIGN local ticker that COLLIDES with NYSE:Energizer, so a
    bare pull returns a real-but-WRONG series, relabelled with Siemens' CUSIP (the malignant, silent case);
  - `-` (SSI money market) and `2670549D` (an ExxonMobil placeholder) 404-drop, overstating coverage.
This is *never-anchor-on-a-ticker* (HECO, §2/§5) one level down, at the constituent grain.

THESE ARE THE PRIMARY DELIVERABLE (design thread): they were written RED FIRST and watched fail against
the un-fixed branch FOR THE STATED BEHAVIORAL REASON — `ENR`/`-`/`2670549D` actually in the pulled-symbol
set, `coverage_actual` actually overstated (0.9149) — before the fix existed. A test that only ImportErrors
on a missing helper fails for the WRONG reason and proves nothing; so the pull-set and coverage tests are
BEHAVIORAL: they drive the real §9e dispersion pass (`_run_dispersion`) and observe what it hands the price
layer / what coverage it records. All OFFLINE: real TEKX xlsx + a stub price_ingest that records requested
symbols, no network, no EDGAR (the mf map is hand-built).

PROVENANCE (Science's discipline, preserved): these tests assert the MEMBERSHIP-BOUNDARY behavior — that
`ENR` is never handed to the bare-symbol pull — NOT the secondary, web-sourced claim that `ENR`=Energizer.
The finding is fix-agnostic and needs no live verification; the malignant case is precisely WHY exclusion
(not "let it 404") is the honest default: a colliding foreign ticker does not 404.
"""

import copy
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from prospector.config import load_config
from prospector.ingest.holdings import (HoldingsIngest, parse_spdr_holdings,
                                         weight_covering_members)
from prospector.runner.runner import _run_dispersion, _tiingo_symbol
from prospector.runner.runlog import RunLog

CONFIG = Path("config") / "prospector.yaml"
NOW = "2026-07-14T22:30:00Z"
REAL_TEKX = (Path(__file__).parent / "fixtures" / "holdings"
             / "holdings-daily-us-en-tekx.xlsx").read_bytes()

TEKX_SERIES = "S000087749"                       # TEKX's SEC series id (identity keys on this, §2/§5)
# The mf-tickers map _run_dispersion resolves the universe from — hand-built so TEKX resolves to its
# series id WITHOUT an EDGAR fetch (the map's only job here; see runner._universe_series_ids).
_TEKX_MF = {"fields": ["cik", "seriesId", "classId", "symbol"],
            "data": [["0000000001", TEKX_SERIES, "C000000001", "TEKX"]]}

# The three lines in TEKX's 0.90 cut that are NOT priceable by a bare US ticker (read from the fixture):
ENR_TICKER = "ENR"               # Siemens Energy AG, EUR — collides with NYSE:Energizer (the malignant case)
CASH_CUSIP = "924QSGII3"         # SSI US GOV MONEY MARKET CLASS — ticker `-`
PLACEHOLDER_TICKER = "2670549D"  # EXXONMOBIL HOLDINGS CORP — an internal placeholder, no tradable US ticker


class _Recorder:
    """A store stand-in: _run_dispersion only calls `store.append` (via the sensor / _emit_fault)."""

    def __init__(self):
        self.events = []

    def append(self, event):
        self.events.append(event)


def _tekx_cfg():
    cfg = copy.deepcopy(load_config(CONFIG)[0])
    cfg["universe"]["sectors"] = ["TEKX"]        # the only basket this driver resolves (via _TEKX_MF)
    return cfg


def _empty_frame(_symbol):
    return pd.DataFrame()                        # -> _build_constituent_panel drops it (a coverage gap)


def _nonempty_frame(symbol):
    """A minimal tidy price frame so `build_panel` succeeds and the sensor is REACHED (test 4 needs the
    membership the runner hands to `scan`). The values are irrelevant — `scan` is monkeypatched to capture
    the membership; the pipeline math never runs. Columns match PriceIngest.pull's tidy shape."""
    dates = pd.bdate_range("2024-01-02", periods=5)
    return pd.DataFrame({"date": dates, "ticker": symbol, "close_adj": 100.0, "source": "tiingo"})


def _drive_tekx_dispersion(layout, registry, price_frame_factory):
    """Run the REAL §9e dispersion pass over the recorded TEKX xlsx with a stub price_ingest that RECORDS
    every requested symbol. Returns (requested_symbols, runlog). The fix lives inside `_run_dispersion`
    (it filters the membership BEFORE the pull), so driving it is the only place the violation is
    observable — a unit test on a helper would miss it. Offline: real holdings + stub prices, no EDGAR."""
    requested: list[str] = []

    class _StubPrices:
        def pull(self, symbol, source, start, end):
            requested.append(symbol)
            return price_frame_factory(symbol)

    deps = SimpleNamespace(
        cfg=_tekx_cfg(), registry=registry,
        holdings_ingest=HoldingsIngest(layout, fetch=lambda u, h: REAL_TEKX, clock=lambda: NOW[:10]),
        price_ingest=_StubPrices())
    runlog = RunLog(run_id="t", ts=NOW, date=NOW[:10])
    _run_dispersion(deps, _Recorder(), NOW, [], runlog, _TEKX_MF)
    return requested, runlog


# === the ENR collision: a foreign ticker must never be handed to the bare-symbol pull =================

def test_foreign_listing_is_not_pulled_by_a_colliding_us_ticker(layout, registry):
    # Sanity: the fixture still carries the hazard — ENR (Siemens Energy, EUR) is in the 0.90 cut.
    members, _ = weight_covering_members(parse_spdr_holdings(REAL_TEKX, "TEKX"), 0.90)
    assert any(m["ticker"] == ENR_TICKER for m in members)

    requested, _ = _drive_tekx_dispersion(layout, registry, _empty_frame)

    # THE VIOLATION: on the un-fixed branch `ENR` IS in the requested set, so Tiingo would return
    # Energizer's real-but-WRONG series relabelled with Siemens' CUSIP (P1 silent corruption). After the
    # fix the foreign line is excluded at the membership boundary — never pulled by its colliding symbol.
    assert ENR_TICKER not in requested


# === cash / placeholder lines are not priceable equities (and overstate coverage if left in) ==========

def test_cash_and_placeholder_lines_are_excluded_from_the_price_universe(layout, registry):
    # Both the `-` money-market line and the `2670549D` placeholder are in the cut today ...
    members, _ = weight_covering_members(parse_spdr_holdings(REAL_TEKX, "TEKX"), 0.90)
    tickers = {m["ticker"] for m in members}
    assert "-" in tickers and PLACEHOLDER_TICKER in tickers

    requested, _ = _drive_tekx_dispersion(layout, registry, _empty_frame)

    # ... but neither is handed to the price pull. On the branch they ARE (only 404-dropped downstream,
    # which overstates coverage); after the fix they are excluded as an honest, reported gap.
    assert _tiingo_symbol("-") not in requested             # the SSI money-market cash line (ticker `-`)
    assert _tiingo_symbol(PLACEHOLDER_TICKER) not in requested   # the ExxonMobil placeholder code


# === coverage_actual reports the PRICED set, not the pre-pull top-90% sum =============================

def test_coverage_actual_reflects_the_priced_set(layout, registry, monkeypatch):
    # Capture the MembershipSnapshot the runner hands to the sensor (coverage_actual is not emitted, so
    # this is the only seam). The stub prices every requested name so the panel builds and scan is reached.
    captured = {}

    def _capture_scan(series_id, ticker, membership, *args, **kwargs):
        captured["membership"] = membership
        return {"edge": None, "z": None, "q": None, "as_of": None, "n_constituents": 0}

    monkeypatch.setattr("prospector.sensors.dispersion.scan", _capture_scan)
    _drive_tekx_dispersion(layout, registry, _nonempty_frame)

    membership = captured["membership"]
    # THE VIOLATION: on the branch coverage_actual == the pre-pull top-90% weight sum (0.9149) — it counts
    # ENR (6.17%) + the `-` money market (4.22%) + the `2670549D` placeholder (1.62%) as if priced. After
    # the fix it is the fraction ACTUALLY priced (≈0.7953): the excluded weight is a reported gap, so the
    # burn-in Q is trustworthy (you know what universe it was computed on).
    assert membership.coverage_actual < 0.90
    assert membership.coverage_actual == pytest.approx(0.7953, abs=2e-3)


# === structural: a ticker-keyed map must not collapse two non-unique tickers (Option 2) ===============

def test_member_map_does_not_collapse_duplicate_tickers():
    # The old `{ticker: identifier}` map collapsed two `-`-ticker cash lines to ONE key, silently dropping
    # a CUSIP (an asymmetric loss). `priceable_members` excludes BOTH `-` lines — a symmetric, reported
    # gap — so no CUSIP is silently lost. (Structural / RED-by-construction: a dict collapse is not
    # behaviorally observable because both `-` lines 404 either way; `build_panel`'s duplicate-CUSIP fault
    # is the further backstop for two priceable lines that somehow shared a real ticker.)
    from prospector.ingest.holdings import priceable_members

    members = [
        {"name": "CASH ONE", "ticker": "-", "identifier": "CUSIP0001", "weight": 0.03,
         "sector": "-", "local_currency": "USD"},
        {"name": "CASH TWO", "ticker": "-", "identifier": "CUSIP0002", "weight": 0.02,
         "sector": "-", "local_currency": "USD"},
        {"name": "APPLE INC", "ticker": "AAPL", "identifier": "037833100", "weight": 0.95,
         "sector": "-", "local_currency": "USD"},
    ]
    kept = {m["identifier"] for m in priceable_members(members)}
    assert kept == {"037833100"}          # both `-` CUSIPs excluded; neither collapses onto the other
