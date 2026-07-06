"""Holdings ingest — freeze the constituent substrate (spec §3, §4d). Tests are OFFLINE: the `fetch`
callable is injected and closes over a recorded fixture body, so no socket ever opens. The
load-bearing invariants mirror price ingest: freeze precedes parse (a corrupt body still lands on
disk), the membership frame is a pure function of the frozen bytes (load_frozen round-trips pull), a
missing row is a missing row, and the snapshot keys on the basket's series_id while constituents
carry name+identifier only."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from prospector.ingest.holdings import (HoldingsIngest, HoldingsIngestError, MEMBER_COLUMNS,
                                        parse_spdr_holdings, weight_covering_members)

FIXTURE = Path(__file__).parent / "fixtures" / "holdings" / "XLK_2026-07-02.csv"
XLK_SERIES = "S000006415"  # Technology Select Sector SPDR (matches the identity seed)


def _fixture_bytes() -> bytes:
    return FIXTURE.read_bytes()


def _fixed_clock(iso_date):
    return lambda: iso_date


# -- parse_spdr_holdings ------------------------------------------------------

def test_parse_builds_tidy_frame_sorted_by_weight():
    frame = parse_spdr_holdings(_fixture_bytes(), "XLK")
    assert list(frame.columns) == list(MEMBER_COLUMNS)
    # Weights are fractions (24.00% -> 0.24), sorted weight desc.
    assert frame["weight"].iloc[0] == pytest.approx(0.24)
    assert frame["name"].iloc[0] == "APPLE INC"
    assert frame["weight"].is_monotonic_decreasing
    # Every parsed weight is a fraction < 1 (percent divided by 100), none left as a raw percent.
    assert (frame["weight"] < 1.0).all()


def test_parse_keeps_cash_row_as_recorded():
    frame = parse_spdr_holdings(_fixture_bytes(), "XLK")
    cash = frame[frame["name"] == "CASH"]
    assert len(cash) == 1  # a holding is a holding — cash kept, never silently dropped (§3)
    assert cash["weight"].iloc[0] == pytest.approx(0.005)


def test_parse_skips_preamble_and_footer():
    # 11 holdings rows (10 equities + cash); the preamble and the disclaimer footer are skipped.
    frame = parse_spdr_holdings(_fixture_bytes(), "XLK")
    assert len(frame) == 11
    assert "prospectus" not in " ".join(frame["name"]).lower()


def test_parse_name_tiebreak_is_stable():
    # ADOBE and BROADCOM both 6.50% -> weight desc, then name asc: ADOBE before BROADCOM.
    frame = parse_spdr_holdings(_fixture_bytes(), "XLK")
    tied = frame[np.isclose(frame["weight"], 0.065)]["name"].to_list()
    assert tied == ["ADOBE INC", "BROADCOM INC"]


def test_parse_no_header_raises():
    with pytest.raises(HoldingsIngestError, match="no holdings header"):
        parse_spdr_holdings(b"just,some,preamble\nwith,no,holdings\n", "XLK")


def test_parse_header_but_no_rows_raises():
    body = b"Name,Ticker,Identifier,SEDOL,Weight,Sector\n\nfooter disclaimer\n"
    with pytest.raises(HoldingsIngestError, match="no holdings rows"):
        parse_spdr_holdings(body, "XLK")


def test_parse_faults_on_fraction_scaled_weights_never_mis_scales_silently():
    # H1: a file already expressed in FRACTIONS (0.60/0.40, not 60%/40%) would be ÷100'd to 0.006/0.004,
    # summing to ~0.01 — a silent 100x-small scale, invisible to coverage (scale-invariant) but fatal to
    # the ABSOLUTE sector_min_weight gate (§4c: every fund would resolve dormant). The weight-units sanity
    # check faults on the implausible sum instead of mis-scaling — the check that used to live only in the
    # test now lives in the parser. (A well-formed percent file sums to ~1.0 and passes; see the fixtures.)
    body = (b"Name,Ticker,Identifier,Weight,Sector\n"
            b"APPLE INC,AAPL,037833100,0.60,Information Technology\n"
            b"NEXTERA ENERGY INC,NEE,65339F101,0.40,Utilities\n")
    with pytest.raises(HoldingsIngestError, match="unit"):
        parse_spdr_holdings(body, "SYN")


# -- weight_covering_members --------------------------------------------------

def test_coverage_truncates_through_ninety_percent():
    frame = parse_spdr_holdings(_fixture_bytes(), "XLK")
    members, actual = weight_covering_members(frame, coverage=0.90)
    # cumsum (weight desc): AAPL 24, MSFT 45, NVDA 64, ADBE 70.5, AVGO 77, ORCL 82.5, CRM 87.5,
    # AMD 92.0 -> crosses 90 at AMD; 8 names, coverage_actual 0.92. CSCO/ACN/CASH excluded.
    assert [m["name"] for m in members] == [
        "APPLE INC", "MICROSOFT CORP", "NVIDIA CORP", "ADOBE INC", "BROADCOM INC",
        "ORACLE CORP", "SALESFORCE INC", "ADVANCED MICRO DEVICES INC"]
    assert actual == pytest.approx(0.92)
    assert actual >= 0.90  # coverage is always >= the target, never under


def test_coverage_actual_never_under_target_for_flat_book():
    # A perfectly flat 10x10% book: the invariant is coverage >= target (never under). The exact
    # member count sits on a float boundary (9x0.10 == 0.8999999999999999 < 0.90), so the cut may
    # take the 10th name — including one extra is safe (over-covers), dropping one would not be.
    frame = pd.DataFrame(
        {"name": [f"N{i}" for i in range(10)], "identifier": [f"ID{i}" for i in range(10)],
         "weight": [0.10] * 10, "sector": ["x"] * 10})
    members, actual = weight_covering_members(frame, coverage=0.90)
    assert len(members) >= 9  # 9 ideal, 10 on the float boundary — never fewer
    assert actual >= 0.90


def test_coverage_empty_frame():
    empty = pd.DataFrame(columns=list(MEMBER_COLUMNS))
    members, actual = weight_covering_members(empty, 0.90)
    assert members == [] and actual == 0.0


# -- HoldingsIngest: freeze BEFORE parse --------------------------------------

def test_pull_freezes_before_parse_then_round_trips(layout):
    body = _fixture_bytes()
    captured = {}

    def fetch(url, headers):
        captured["url"] = url
        captured["headers"] = headers
        return body

    ingest = HoldingsIngest(layout, fetch=fetch, clock=_fixed_clock("2026-07-02"))
    frame = ingest.pull(XLK_SERIES, "XLK")

    # Frozen under ingest/holdings/{series_id}/{date}/ — keyed on the SERIES ID, not the ticker.
    frozen = layout.holdings_path(XLK_SERIES, "2026-07-02", "XLK.csv")
    assert frozen.exists()
    assert frozen.read_bytes() == body  # byte-exact freeze (§3)
    # Fetched by ticker (the SPDR URL is a display attribute); freeze/key by series id.
    assert "xlk" in captured["url"].lower()
    assert "User-Agent" in captured["headers"]

    reloaded = ingest.load_frozen(XLK_SERIES, "2026-07-02", "XLK")
    pd.testing.assert_frame_equal(frame, reloaded)


def test_pull_freezes_even_when_body_is_corrupt(layout):
    corrupt = b"not,a,holdings,file\nwith,no,header,weight,column\n"
    ingest = HoldingsIngest(layout, fetch=lambda url, headers: corrupt,
                            clock=_fixed_clock("2026-07-02"))
    with pytest.raises(HoldingsIngestError):
        ingest.pull(XLK_SERIES, "XLK")
    frozen = layout.holdings_path(XLK_SERIES, "2026-07-02", "XLK.csv")
    assert frozen.exists()
    assert frozen.read_bytes() == corrupt  # the postmortem substrate survives the parse failure


def test_pull_unknown_source_raises(layout):
    ingest = HoldingsIngest(layout, fetch=lambda url, headers: b"", clock=_fixed_clock("2026-07-02"))
    with pytest.raises(HoldingsIngestError, match="unknown holdings source"):
        ingest.pull(XLK_SERIES, "XLK", source="edgar")


# -- membership snapshot ------------------------------------------------------

def test_membership_snapshot_keys_on_series_and_carries_constituents(layout):
    ingest = HoldingsIngest(layout, fetch=lambda url, headers: _fixture_bytes(),
                            clock=_fixed_clock("2026-07-02"))
    ingest.pull(XLK_SERIES, "XLK")
    snap = ingest.membership(XLK_SERIES, "XLK", "2026-07-02", coverage=0.90)

    assert snap.series_id == XLK_SERIES  # the basket keys on the series id (HECO rule)
    assert snap.coverage_actual == pytest.approx(0.92)
    assert snap.coverage_target == 0.90
    assert len(snap.members) == 8
    # Constituents carry name + issuer identifier only — never a series id, never a fund.
    top = snap.members[0]
    assert top["name"] == "APPLE INC" and top["identifier"] == "037833100"
    assert snap.identifiers()[0] == "037833100"
