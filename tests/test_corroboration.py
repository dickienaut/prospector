"""Cross-stream corroboration scoring (spec §10 test 5b). A backtest firing is auto-scored
`structural` if a verified launch whose concentration industries keyword-match BOTH sides of the
pair lands within W months (DEFAULT 24) after first firing. Uses the REAL committed launch table
and the REAL config sector->keyword map — both small, static, deterministic, reviewable by eye."""

from datetime import date
from pathlib import Path

import yaml

from prospector.backtest.corroboration import (add_months, keyword_match, load_launches,
                                               score_all, score_firing)

_REPO = Path(__file__).resolve().parent.parent
_LAUNCHES = load_launches(_REPO / "tests" / "fixtures" / "backtest" / "historical_launches.yaml")
_SKW = yaml.safe_load(open(_REPO / "config" / "prospector.yaml"))["sector_keywords"]


# -- keyword_match: bidirectional substring, either direction -----------------

def test_keyword_match_is_bidirectional_substring():
    # industry string CONTAINS a shorter keyword ('technology' contains 'tech').
    assert keyword_match(["technology"], ["tech"]) is True
    # keyword CONTAINS a shorter industry ('powerplant' contains 'power').
    assert keyword_match(["power"], ["powerplant"]) is True
    # exact phrase match works both sides.
    assert keyword_match(["artificial intelligence"], ["artificial intelligence"]) is True
    # case-insensitive.
    assert keyword_match(["ARTIFICIAL INTELLIGENCE"], ["artificial intelligence"]) is True


def test_keyword_match_no_false_match_between_disjoint_lists():
    assert keyword_match(["banking", "insurance"], ["power", "nuclear", "grid"]) is False
    assert keyword_match([], ["power"]) is False
    assert keyword_match(["power"], []) is False


# -- add_months: day clamped to the target month's length ---------------------

def test_add_months_clamps_to_month_length():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)  # non-leap Feb
    assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)  # leap Feb


def test_add_months_rolls_over_the_year():
    assert add_months(date(2023, 12, 15), 1) == date(2024, 1, 15)


def test_add_months_spans_two_years():
    assert add_months(date(2023, 10, 1), 24) == date(2025, 10, 1)
    assert add_months(date(2022, 9, 9), 24) == date(2024, 9, 9)


# -- score_firing: the known cross-stream datum (TEKX / XLK×XLU) ---------------

def test_xlk_xlu_scores_structural_with_tekx_in_window():
    # TEKX (detected 2024-09-09) bridges XLK keywords ('technology'/'ai') AND XLU keywords
    # ('power'/'utilities'/'electricity'); first_fired 2023-10-01 puts it well inside 24 months.
    result = score_firing(("XLK", "XLU"), "2023-10-01", _LAUNCHES, _SKW)
    assert result["structural"] is True
    tickers = [m["ticker"] for m in result["matches"]]
    assert "TEKX" in tickers


def test_xlk_xlu_not_structural_when_launch_predates_window():
    # first_fired 2019-01-01 -> window ends 2021-01-01; TEKX at 2024-09 is far outside 24 months.
    result = score_firing(("XLK", "XLU"), "2019-01-01", _LAUNCHES, _SKW)
    assert result["structural"] is False
    assert result["matches"] == []


def test_xlp_xlv_not_structural_no_keyword_bridge():
    # No launch in the table bridges XLP (staples/food) AND XLV (health) keyword lists.
    result = score_firing(("XLP", "XLV"), "2023-10-01", _LAUNCHES, _SKW)
    assert result["structural"] is False


# -- window edges (inclusive both ends) ---------------------------------------

def test_window_lower_edge_inclusive_detected_equals_first_fired():
    # A firing whose first_fired == the launch's detected_at (2024-09-09) is in window.
    result = score_firing(("XLK", "XLU"), "2024-09-09", _LAUNCHES, _SKW)
    assert result["structural"] is True


def test_window_upper_edge_inclusive_detected_equals_first_fired_plus_24mo():
    # first_fired + exactly 24 months == detected_at (2022-09-09 + 24mo == 2024-09-09): still in.
    result = score_firing(("XLK", "XLU"), "2022-09-09", _LAUNCHES, _SKW)
    assert result["structural"] is True


def test_window_one_day_past_upper_edge_is_out():
    # first_fired 2022-09-08 -> window ends 2024-09-08, one day before TEKX's 2024-09-09.
    result = score_firing(("XLK", "XLU"), "2022-09-08", _LAUNCHES, _SKW)
    assert result["structural"] is False


# -- score_all summary --------------------------------------------------------

def test_score_all_summary_counts():
    firings = [
        {"pair": ("XLK", "XLU"), "first_fired": "2023-10-01"},   # structural (TEKX)
        {"pair": ("XLP", "XLV"), "first_fired": "2023-10-01"},   # junk (no bridge)
    ]
    result = score_all(firings, _LAUNCHES, _SKW)
    assert result["summary"] == {"n_firings": 2, "n_structural": 1, "structural_fraction": 0.5}
    # Rows carry the pair, the firing date, and the per-firing verdict.
    assert result["rows"][0]["pair"] == ("XLK", "XLU")
    assert result["rows"][0]["structural"] is True
    assert result["rows"][1]["structural"] is False


def test_score_all_empty_firings_no_zero_division():
    result = score_all([], _LAUNCHES, _SKW)
    assert result["summary"] == {"n_firings": 0, "n_structural": 0, "structural_fraction": 0.0}
    assert result["rows"] == []
