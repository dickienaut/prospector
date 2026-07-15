"""Launch corroboration hook — the live cross-stream lag (spec §4c, M4 capstone).

The honest-test boundary: both lag endpoints are real events through real code, and the launch's
sectors are DERIVED from real (messy) holdings, never supplied. The SPLIT assertion (design-thread
sign-off condition) is two separate tests — "the derivation produces the RIGHT sectors" and "the hook
produces the RIGHT lag from those sectors" — so a mapping bug and a hook bug can't cancel to a
flattering +593. Plus: signed lag (negative is honest data), both-sides overlap, and the
`holdings-unavailable → dormant` majority case (flagged, never guessed). Offline throughout."""

from datetime import timedelta
from pathlib import Path

from prospector.ingest.holdings import parse_spdr_holdings
from prospector.sensors.dispersion import dispersion_lead_id
from prospector.sensors.launch_corroboration import (corroborate, cross_stream_lag, lead_sectors,
                                                     overlaps, sector_concentration,
                                                     series_id_sectors)
from prospector.sensors.xcorr import xcorr_lead_id
from prospector.store.envelope import SYSTEM_LEAD

FIX = Path(__file__).parent / "fixtures" / "holdings"
TEKX_HOLDINGS = parse_spdr_holdings((FIX / "TEKX_2024-09-10.csv").read_bytes(), "TEKX")

CFG = {"corroboration": {"sector_min_weight": 0.10}}
# sector-SPDR series ids (from the EDGAR MF-map fixture)
SXLK, SXLU, SXLE, SXLV, SXLF = "S000006415", "S000006416", "S000006410", "S000006412", "S000006411"
# a live launch record — detected_at is a full ISO ts (the live shape), preserved as T2
TEKX = {"series_id": "S000087749", "ticker": "TEKX", "name": "SPDR Galaxy … ETF",
        "detected_at": "2024-09-09T00:00:00Z", "unverified_ref": "u1"}
DERIVED = ["Industrials", "Information Technology", "Utilities"]  # sorted, sub-threshold tail excluded


# === Assertion A — the derivation produces the RIGHT sectors (INDEPENDENT of the lag) ============

def test_derivation_produces_the_right_sectors_from_real_holdings():
    # Derived from the holdings' sector column, not supplied — the fixture carries no
    # concentration_industries. IT 45% + Utilities 30% + Industrials 15% clear the 10% floor;
    # Materials 5% and Health Care 3% are the tail and are correctly excluded.
    sectors = sector_concentration(TEKX_HOLDINGS, min_weight=0.10)
    assert sectors == frozenset({"Information Technology", "Utilities", "Industrials"})
    assert "Materials" not in sectors and "Health Care" not in sectors


def test_sector_concentration_threshold_and_empty_cases():
    # A higher floor drops Industrials (15%) but keeps IT (45%) and Utilities (30%).
    assert sector_concentration(TEKX_HOLDINGS, 0.20) == frozenset({"Information Technology", "Utilities"})
    assert sector_concentration(None, 0.10) == frozenset()


# === overlap: the both-sides rule (§10 test 5b) =================================================

def test_overlap_requires_every_side_of_the_lead():
    launch = frozenset({"Information Technology", "Utilities", "Industrials"})
    assert overlaps(launch, frozenset({"Information Technology", "Utilities"}))    # xcorr pair, both present
    assert overlaps(launch, frozenset({"Information Technology"}))                 # dispersion basket
    assert not overlaps(launch, frozenset({"Information Technology", "Energy"}))   # Energy absent -> fails
    assert not overlaps(launch, frozenset())                                       # empty lead never matches


# === lead_sectors: forward-hash the universe, recover each active lead's sectors =================

def test_lead_sectors_forward_hashes_active_leads_only():
    universe = [SXLK, SXLU, SXLE]
    s2sec = {SXLK: "Information Technology", SXLU: "Utilities", SXLE: "Energy"}
    pair_ku, disp_k = xcorr_lead_id([SXLK, SXLU]), dispersion_lead_id(SXLK)
    ls = lead_sectors(universe, s2sec, {pair_ku, disp_k, "xcorr-inactive"})
    assert ls == {pair_ku: frozenset({"Information Technology", "Utilities"}),
                  disp_k: frozenset({"Information Technology"})}   # inactive/absent leads excluded


def test_series_id_sectors_bridges_sector_map_through_the_universe():
    assert series_id_sectors({"XLK": "Information Technology", "XLU": "Utilities"},
                             {"XLK": SXLK, "XLU": SXLU}) == {SXLK: "Information Technology",
                                                            SXLU: "Utilities"}


# === Assertion B — the hook produces the RIGHT lag from those sectors ============================

def test_corroboration_accretes_onto_the_matched_lead():
    pair = xcorr_lead_id([SXLK, SXLU])
    events = []
    res = corroborate(TEKX, TEKX_HOLDINGS, {pair: frozenset({"Information Technology", "Utilities"})},
                      CFG, "2024-09-10T00:00:00Z", events.append)
    assert res["action"] == "corroborated" and res["matched"] == [pair]
    (ev,) = events
    assert ev["lead"] == pair and ev["type"] == "launch"
    assert ev["payload"]["detected_at"] == "2024-09-09T00:00:00Z"          # T2 preserved through the deferral
    assert ev["payload"]["concentration_sectors"] == DERIVED               # the derived sectors, attached
    assert ev["payload"]["corroboration"] == "match"


def test_the_hook_produces_the_593_lag_from_the_accreted_launch():
    # T1 = a real xcorr structural spawn at 2023-01-25; T2 = the corroborating launch's detected_at.
    # The +593 is COMPUTED from the two timestamps (not asserted into existence); it is independent of
    # the sector derivation (which is checked separately, Assertion A) — the split closes the boundary.
    pair = xcorr_lead_id([SXLK, SXLU])
    events = []
    corroborate(TEKX, TEKX_HOLDINGS, {pair: frozenset({"Information Technology", "Utilities"})},
                CFG, "2024-09-10T00:00:00Z", events.append)
    lead_events = [{"type": "lead.spawned", "ts": "2023-01-25T00:00:00Z",
                    "payload": {"spawner": "xcorr"}}, *events]
    assert cross_stream_lag(lead_events) == timedelta(days=593)


# === signed lag: negative is honest data (packaging beat structure) =============================

def test_cross_stream_lag_is_signed_and_negative_is_recorded_not_clamped():
    # A launch whose detection PRECEDES the (delayed) structural spawn -> negative lag, the
    # un-recalibrated-gate -58 category. Recorded honestly, never clamped to positive or discarded.
    lead_events = [{"type": "lead.spawned", "ts": "2024-11-06T00:00:00Z", "payload": {}},
                   {"type": "launch", "ts": "2024-09-10T00:00:00Z",
                    "payload": {"detected_at": "2024-09-09T00:00:00Z"}}]
    assert cross_stream_lag(lead_events) == timedelta(days=-58)


def test_cross_stream_lag_is_none_without_a_spawn_or_a_launch():
    launch_only = [{"type": "launch", "ts": "x", "payload": {"detected_at": "2024-09-09T00:00:00Z"}}]
    spawn_only = [{"type": "lead.spawned", "ts": "2023-01-25T00:00:00Z", "payload": {}}]
    assert cross_stream_lag(launch_only) is None and cross_stream_lag(spawn_only) is None


def test_cross_stream_lag_picks_the_earliest_spawn_chronologically_not_lexically():
    # lag-lexical-sort: T1 must be the CHRONOLOGICALLY-earliest spawn, symmetric with T2's `parse_ts`. A
    # bare string sort is LEXICAL — "…00.5Z" sorts BEFORE "…00Z" (the '.' 0x2E precedes 'Z' 0x5A), so a
    # lexical T1 would pick the LATER (00.5) spawn and shave 0.5 s off the signed lag. The two spawns here
    # are one second-fraction apart; the fix makes T1 the true-earliest 00:00:00Z.
    lead_events = [
        {"type": "lead.spawned", "ts": "2026-07-02T00:00:00.5Z", "payload": {}},  # later, but lexically first
        {"type": "lead.spawned", "ts": "2026-07-02T00:00:00Z", "payload": {}},     # the true earliest (T1)
        {"type": "launch", "ts": "2026-07-05T00:00:00Z",
         "payload": {"detected_at": "2026-07-03T00:00:00Z"}}]
    # detected(07-03) − earliest-spawn(07-02T00:00:00Z) = exactly 1 day; a lexical T1 (the .5 spawn) would
    # give 1 day − 0.5 s.
    assert cross_stream_lag(lead_events) == timedelta(days=1)


def test_sector_concentration_ignores_a_nan_sector_no_phantom_bucket():
    # S5: a pandas NaN sector cell stringifies to "nan" (truthy, not in _UNRESOLVED_SECTOR), which without
    # the guard accumulates a PHANTOM "nan" sector and can cross min_weight. The pd.isna guard routes it to
    # "" — the same honest unresolved path as a blank cell (never a "nan" bucket, never a silent match).
    import numpy as np
    import pandas as pd
    holdings = pd.DataFrame({"sector": ["Information Technology", np.nan], "weight": [0.60, 0.40]})
    result = sector_concentration(holdings, min_weight=0.30)
    assert "nan" not in result
    assert result == frozenset({"Information Technology"})   # the NaN 0.40 is ignored, not a phantom sector


# === both-sides negative, off-thesis dormant, and the holdings-unavailable majority case =========

def test_both_sides_negative_pair_misses_but_dispersion_basket_matches():
    pair_ke, disp_k = xcorr_lead_id([SXLK, SXLE]), dispersion_lead_id(SXLK)
    active = {pair_ke: frozenset({"Information Technology", "Energy"}),   # Energy absent from launch
              disp_k: frozenset({"Information Technology"})}
    events = []
    res = corroborate(TEKX, TEKX_HOLDINGS, active, CFG, "2024-09-10T00:00:00Z", events.append)
    assert res["matched"] == [disp_k]                                     # the pair fails both-sides
    assert [e["lead"] for e in events] == [disp_k]


def test_off_thesis_launch_is_recorded_dormant_with_its_derived_sectors():
    active = {xcorr_lead_id([SXLV, SXLF]): frozenset({"Health Care", "Financials"})}  # no overlap
    events = []
    res = corroborate(TEKX, TEKX_HOLDINGS, active, CFG, "2024-09-10T00:00:00Z", events.append)
    assert res["action"] == "dormant_no_match"
    (ev,) = events
    assert ev["lead"] == SYSTEM_LEAD and ev["payload"]["corroboration"] == "dormant_no_match"
    assert ev["payload"]["concentration_sectors"] == DERIVED              # first-class: derived + recorded


def test_holdings_unavailable_is_first_class_dormant_never_a_guess():
    # The MAJORITY case today: a non-SPDR launch has no live holdings intake. The hook records the
    # blind spot honestly (flagged, no sectors, no corroboration) rather than faking through it.
    active = {xcorr_lead_id([SXLK, SXLU]): frozenset({"Information Technology", "Utilities"})}
    events = []
    res = corroborate(TEKX, None, active, CFG, "2024-09-10T00:00:00Z", events.append)
    assert res["action"] == "holdings_unavailable" and res["matched"] == []
    (ev,) = events
    assert ev["lead"] == SYSTEM_LEAD
    assert ev["payload"]["concentration_sectors"] is None
    assert ev["payload"]["corroboration"] == "holdings_unavailable"
