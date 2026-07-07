"""Price ingest — freeze the substrate (spec §3). Tests are OFFLINE: the `fetch` callable is
injected and closes over synthetic bodies, so no socket ever opens. The load-bearing invariants:
freeze precedes parse (a corrupt body still lands on disk), the tidy frame is a pure function of
the frozen bytes (load_frozen round-trips pull), and missing rows stay missing (no forward-fill,
outer join keeps a late-lister's leading NaN)."""

import json
import math

import numpy as np
import pandas as pd
import pytest

from prospector.ingest.prices import (CALENDAR_PER_TRADING_DAY, PriceIngest, PriceIngestError,
                                      build_panel, guard_live_source, parse_stooq, parse_yahoo,
                                      required_pull_start, warmup_days)

WINDOWS_CFG = {"windows": {"corr_days": 63, "baseline_days": 252, "stress_days": 21}}


def _yahoo_body(timestamps, adjcloses, error=None) -> bytes:
    """A synthetic Yahoo v8 chart body: chart.result[0].timestamp x indicators.adjclose."""
    if error is not None:
        return json.dumps({"chart": {"result": None, "error": error}}).encode("utf-8")
    return json.dumps({"chart": {"result": [{
        "timestamp": timestamps,
        "indicators": {"adjclose": [{"adjclose": adjcloses}]},
    }], "error": None}}).encode("utf-8")


# UTC-midnight epochs for three consecutive days.
_D1 = 1704067200  # 2024-01-01T00:00:00Z
_D2 = 1704153600  # 2024-01-02T00:00:00Z
_D3 = 1704240000  # 2024-01-03T00:00:00Z


# -- parse_yahoo --------------------------------------------------------------

def test_parse_yahoo_builds_the_tidy_frame():
    frame = parse_yahoo(_yahoo_body([_D1, _D2, _D3], [100.0, 101.5, 102.25]), "XLK")
    assert list(frame.columns) == ["date", "ticker", "close_adj", "source"]
    assert (frame["ticker"] == "XLK").all()
    assert (frame["source"] == "yahoo").all()
    assert frame["close_adj"].to_list() == [100.0, 101.5, 102.25]
    # Timestamps become UTC dates.
    assert list(frame["date"].dt.date.astype(str)) == ["2024-01-01", "2024-01-02", "2024-01-03"]
    assert pd.api.types.is_float_dtype(frame["close_adj"])


def test_parse_yahoo_null_adjclose_drops_the_row_not_fills_it():
    frame = parse_yahoo(_yahoo_body([_D1, _D2, _D3], [100.0, None, 102.25]), "XLK")
    # The null row is DROPPED, never forward-filled (§3: a missing price is a missing row).
    assert frame["close_adj"].to_list() == [100.0, 102.25]
    assert list(frame["date"].dt.date.astype(str)) == ["2024-01-01", "2024-01-03"]


def test_parse_yahoo_error_payload_raises():
    with pytest.raises(PriceIngestError, match="yahoo error"):
        parse_yahoo(_yahoo_body(None, None, error={"code": "Not Found"}), "XLK")


def test_parse_yahoo_unparseable_body_raises():
    with pytest.raises(PriceIngestError, match="unparseable yahoo"):
        parse_yahoo(b"{not json", "XLK")


# -- parse_stooq --------------------------------------------------------------

def test_parse_stooq_uses_close_as_close_adj():
    csv = (b"Date,Open,High,Low,Close,Volume\n"
           b"2024-01-01,10,11,9,10.5,1000\n"
           b"2024-01-02,10.5,12,10,11.25,2000\n")
    frame = parse_stooq(csv, "XLU")
    assert list(frame.columns) == ["date", "ticker", "close_adj", "source"]
    assert (frame["source"] == "stooq").all()
    assert (frame["ticker"] == "XLU").all()
    # Close (not Open/High/Low) is the adjusted close.
    assert frame["close_adj"].to_list() == [10.5, 11.25]
    assert list(frame["date"].dt.date.astype(str)) == ["2024-01-01", "2024-01-02"]


# -- pull(): freeze BEFORE parse ----------------------------------------------

def _fixed_clock(iso_date):
    return lambda: iso_date


def test_pull_freezes_before_parse_then_round_trips(layout):
    body = _yahoo_body([_D1, _D2], [100.0, 101.0])
    captured = {}

    def fetch(url, headers):
        captured["url"] = url
        captured["headers"] = headers
        return body

    ingest = PriceIngest(layout, fetch=fetch, clock=_fixed_clock("2026-07-02"))
    frame = ingest.pull("XLK", "yahoo", "2024-01-01", "2024-01-02")

    frozen = layout.prices_path("yahoo", "2026-07-02", "XLK.json")
    assert frozen.exists()
    # Byte-exact freeze of the raw body (§3: the frame is a pure function of these bytes).
    assert frozen.read_bytes() == body
    # A browser-ish UA rides on the request (Yahoo blocks bare library UAs).
    assert "User-Agent" in captured["headers"]

    # load_frozen re-parses the frozen file to a frame equal to what pull() returned.
    reloaded = ingest.load_frozen("yahoo", "2026-07-02", "XLK")
    pd.testing.assert_frame_equal(frame, reloaded)


def test_pull_freezes_even_when_the_body_is_corrupt(layout):
    """FREEZE-BEFORE-PARSE proof: a corrupt body raises on parse, but the frozen file still
    exists on disk with the exact corrupt bytes (the postmortem substrate, §3)."""
    corrupt = b"{ this is not valid yahoo json"

    ingest = PriceIngest(layout, fetch=lambda url, headers: corrupt,
                         clock=_fixed_clock("2026-07-02"))
    with pytest.raises(PriceIngestError):
        ingest.pull("XLK", "yahoo", "2024-01-01", "2024-01-02")

    frozen = layout.prices_path("yahoo", "2026-07-02", "XLK.json")
    assert frozen.exists()
    assert frozen.read_bytes() == corrupt


def test_pull_unknown_source_raises(layout):
    ingest = PriceIngest(layout, fetch=lambda url, headers: b"", clock=_fixed_clock("2026-07-02"))
    with pytest.raises(PriceIngestError, match="unknown price source"):
        ingest.pull("XLK", "bloomberg", "2024-01-01", "2024-01-02")


# -- build_panel: outer join, no forward-fill ---------------------------------

def test_build_panel_outer_join_keeps_late_starter_leading_nan():
    early = parse_yahoo(_yahoo_body([_D1, _D2, _D3], [100.0, 101.0, 102.0]), "XLK")
    # A late-starting ticker: first date is _D2, so _D1 has no observation for it.
    late = parse_yahoo(_yahoo_body([_D2, _D3], [50.0, 51.0]), "XLC")

    panel = build_panel([early, late])
    assert list(panel.columns) == ["XLK", "XLC"]
    assert len(panel) == 3  # union of dates (outer join)
    # The late-lister keeps its leading NaN — NEVER forward-filled (§3, XLC-2018-06 case).
    assert math.isnan(panel["XLC"].iloc[0])
    assert panel["XLC"].isna().sum() == 1
    assert panel["XLC"].dropna().to_list() == [50.0, 51.0]
    # The early column is complete.
    assert panel["XLK"].isna().sum() == 0


def test_build_panel_records_source_per_column():
    yh = parse_yahoo(_yahoo_body([_D1, _D2], [100.0, 101.0]), "XLK")
    st = parse_stooq(b"Date,Open,High,Low,Close,Volume\n2024-01-01,1,1,1,9.0,1\n", "XLU")
    panel = build_panel([yh, st])
    assert panel.attrs["sources"] == {"XLK": "yahoo", "XLU": "stooq"}


def test_build_panel_empty_input_raises():
    with pytest.raises(ValueError, match="at least one tidy frame"):
        build_panel([])


def test_build_panel_empty_frame_raises():
    empty = parse_yahoo(_yahoo_body([], []), "XLK")
    good = parse_yahoo(_yahoo_body([_D1], [100.0]), "XLU")
    with pytest.raises(ValueError, match="empty tidy frame"):
        build_panel([good, empty])


def test_build_panel_duplicate_ticker_raises():
    a = parse_yahoo(_yahoo_body([_D1], [100.0]), "XLK")
    b = parse_yahoo(_yahoo_body([_D2], [101.0]), "XLK")
    with pytest.raises(ValueError, match="duplicate ticker"):
        build_panel([a, b])


# -- P1 guard: Stooq fails closed as a live source until verified --------------

def test_guard_live_source_allows_yahoo():
    # Yahoo reads `adjclose` (genuinely adjusted) — never gated.
    guard_live_source("yahoo", {"prices": {"primary": "yahoo"}})  # no raise


def test_guard_live_source_refuses_unverified_stooq():
    # parse_stooq only ASSUMES `Close` is adjusted; unverified Stooq must never go live (P1).
    with pytest.raises(PriceIngestError, match="P1"):
        guard_live_source("stooq", {"prices": {"stooq_adjusted_verified": False}})


def test_guard_live_source_refuses_stooq_when_flag_absent():
    # Absent flag is treated as false — fail closed, not open (the safe default for a return base).
    with pytest.raises(PriceIngestError, match="P1"):
        guard_live_source("stooq", {})


def test_guard_live_source_allows_verified_stooq():
    # Once a recorded-real split fixture proves adjustment and the flag is flipped, Stooq is allowed.
    guard_live_source("stooq", {"prices": {"stooq_adjusted_verified": True}})  # no raise


# -- warmup arithmetic --------------------------------------------------------

def test_warmup_days_is_567_for_default_windows():
    # baseline_days (beta) + corr_days (residual corr) + baseline_days (z baseline).
    assert warmup_days(WINDOWS_CFG) == 252 + 63 + 252 == 567


def test_required_pull_start_subtracts_ceil_of_warmup_times_calendar_factor():
    # ceil(567 * 1.5) = ceil(850.5) = 851 calendar days before 2019-01-01.
    days = math.ceil(warmup_days(WINDOWS_CFG) * CALENDAR_PER_TRADING_DAY)
    assert days == 851
    # 2019-01-01 minus 851 days is 2016-09-02 (deterministic, no exchange calendar).
    assert required_pull_start("2019-01-01", WINDOWS_CFG) == "2016-09-02"
