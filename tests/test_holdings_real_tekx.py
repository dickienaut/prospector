"""Golden test — RECORDED-REAL SSGA holdings (the fixture-provenance discipline; see CLAUDE.md).

Closes the fixture-provenance gap for §4c. `holdings-daily-us-en-tekx.xlsx` is a real download
(provenance in the .source.txt sidecar). It proves the xlsx parse path on REAL data and RECORDS the
primary-source finding the synthetic CSV hid: SSGA serves the daily file as xlsx (not CSV), and an
ACTIVE fund's file leaves the Sector column "-" on every row — so file-sector-derived concentration is
EMPTY and real TEKX resolves to `sectors_unresolved` (dormant), not a corroboration. The +593 lag was
reachable only on the *synthetic* fixture's fabricated sectors; on the real book the first derivation
is dormant. **Anti-fitting (CONTRACT):** this outcome NEVER motivates lowering `sector_min_weight`."""

import io
from pathlib import Path

import openpyxl

from prospector.ingest.holdings import parse_spdr_holdings
from prospector.sensors.launch_corroboration import corroborate, sector_concentration
from prospector.sensors.xcorr import xcorr_lead_id
from prospector.store.envelope import SYSTEM_LEAD

FIX = Path(__file__).parent / "fixtures" / "holdings"
REAL_TEKX = (FIX / "holdings-daily-us-en-tekx.xlsx").read_bytes()


def test_real_tekx_file_is_xlsx_and_parses_without_fault():
    # The real SSGA daily file is xlsx (zip magic PK), not CSV — the ingest now reads it. Assert only
    # parses-without-fault + the holdings FRAME is non-empty (the parse works). No pre-asserted sectors.
    assert REAL_TEKX[:4] == b"PK\x03\x04"
    df = parse_spdr_holdings(REAL_TEKX, "TEKX")
    assert list(df.columns) == ["name", "ticker", "identifier", "weight", "sector"]
    assert len(df) >= 30                                 # ~35 real holdings — non-empty frame
    assert 0.99 <= df["weight"].sum() <= 1.02            # weights are fractions summing ~100%
    assert "NVIDIA CORP" in set(df["name"])              # a recognizable real constituent


def test_real_tekx_has_no_file_sectors_so_it_resolves_sectors_unresolved_dormant():
    # PRIMARY-SOURCE FINDING (recorded, not fitted): the active fund's file leaves Sector "-" on every
    # row, so the holdings-derived sector set is EMPTY. The both-sides gate is not "undetermined at ~8%
    # Utilities" — it is UNRESOLVABLE from this file (no sectors at all).
    df = parse_spdr_holdings(REAL_TEKX, "TEKX")
    assert set(df["sector"]) == {"-"}                    # SSGA discloses holdings, not GICS sectors
    assert sector_concentration(df, 0.10) == frozenset()  # -> empty (the honest outcome)

    # End-to-end: real TEKX against a live XLK×XLU lead -> sectors_unresolved, dormant, NO accretion.
    pair = xcorr_lead_id(["S000006415", "S000006416"])
    events = []
    res = corroborate({"series_id": "S000087749", "ticker": "TEKX",
                       "detected_at": "2024-09-09T00:00:00Z", "unverified_ref": "u1"},
                      df, {pair: frozenset({"Information Technology", "Utilities"})},
                      {"corroboration": {"sector_min_weight": 0.10}}, "2026-07-03T00:00:00Z",
                      events.append)
    assert res["action"] == "sectors_unresolved" and res["matched"] == []
    (ev,) = events
    assert ev["lead"] == SYSTEM_LEAD and ev["payload"]["corroboration"] == "sectors_unresolved"
    # ANTI-FITTING (CONTRACT): a dormant real outcome never motivates lowering sector_min_weight to
    # rescue the known case. The threshold is frozen; this test records the truth, it does not chase it.


def test_xlsx_parse_path_handles_populated_sectors_synthetic():
    # Prove the xlsx PARSE PATH on a DECLARED-SYNTHETIC xlsx WITH populated sectors — so xlsx support is
    # exercised on a sector-bearing file too, not only the sector-blank real one. Same SPDR shape.
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Fund Name:", "Synthetic Test ETF (fabricated, not a real filing)"])
    ws.append(["Ticker Symbol:", "SYN"])
    ws.append([])
    ws.append(["Name", "Ticker", "Identifier", "Weight", "Sector"])
    ws.append(["APPLE INC", "AAPL", "037833100", 60.0, "Information Technology"])
    ws.append(["NEXTERA ENERGY INC", "NEE", "65339F101", 40.0, "Utilities"])
    buf = io.BytesIO()
    wb.save(buf)
    df = parse_spdr_holdings(buf.getvalue(), "SYN")
    assert set(df["sector"]) == {"Information Technology", "Utilities"}
    assert sector_concentration(df, 0.10) == frozenset({"Information Technology", "Utilities"})
