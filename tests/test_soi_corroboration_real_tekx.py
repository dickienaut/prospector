"""GOLDEN — SOI-derived corroboration on the real TEKX filings (spec §4c resolver; design
docs/notes/2026-07-04-soi-derived-sector-concentration.md).

Assertion B of the split (the LAG, from real sectors through real code — the derivation itself is checked
independently in test_soi_parser.py, so a rollup bug and a lag bug cannot cancel to a flattering +593).
End-to-end through the sensor on the recorded-real NPORT-EX fixtures:

  - Jul-2025 SOI → Utilities rolls to 10.7% (three industries together), clears the frozen 0.10 floor
    alongside IT → overlaps the XLK×XLU lead → `match` → cross-stream lag = +593 days (detected_at
    2024-09-09 minus the structural spawn 2023-01-25), the existence proof now on REAL primary-source
    data (n=1 snapshot).
  - Jan-2026 SOI → Utilities is 6.4% (Electric only), BELOW the floor → misses XLK×XLU → dormant.

ANTI-FITTING (CONTRACT, the sharpest case): the answer turns on whether Utilities reads 10.7% or 6.4%.
`corroboration.sector_min_weight` is FROZEN; a dormant real snapshot NEVER motivates lowering it. This
golden records both outcomes honestly — it does not chase the pretty one. Offline (frozen fixtures)."""

from datetime import timedelta
from pathlib import Path

from prospector.config import load_config
from prospector.ingest.soi import SoiIngest
from prospector.sensors import soi as soi_sensor
from prospector.sensors.launch_corroboration import cross_stream_lag
from prospector.sensors.xcorr import xcorr_lead_id
from prospector.store.envelope import SYSTEM_LEAD

CFG, _ = load_config(str(Path(__file__).parent.parent / "config" / "prospector.yaml"))
FIX = Path(__file__).parent / "fixtures" / "soi"
JUL2025 = (FIX / "tekx_soi_2025-07-31.htm").read_bytes()
JAN2026 = (FIX / "tekx_soi_2026-01-31.htm").read_bytes()

XLK, XLU = "S000006415", "S000006416"
PAIR = xcorr_lead_id([XLK, XLU])                      # the live lead: {Information Technology, Utilities}
ACTIVE = {PAIR: frozenset({"Information Technology", "Utilities"})}
# TEKX launch, recorded dormant (sectors_unresolved) at detection; the SOI pass reaches back, T2 preserved
TEKX = {"series_id": "S000075521", "ticker": "TEKX", "detected_at": "2024-09-09T00:00:00Z",
        "unverified_ref": "u1"}
ANCHOR = "Transformative Tech Accelerators"
NOW = "2026-07-04T00:00:00Z"
STRUCTURAL_SPAWN = "2023-01-25T00:00:00Z"            # T1 — the xcorr lead's real birth


def test_jul2025_soi_resolves_the_launch_and_attaches_the_593_lag(layout):
    events = []
    res = soi_sensor.scan(TEKX, "0001410368-25-011151", ANCHOR, ACTIVE, SoiIngest(layout), CFG, NOW,
                          events.append, lambda *a, **k: None, fetch_body=lambda: JUL2025)
    assert res["action"] == "corroborated" and res["matched"] == [PAIR]
    # Pin the DERIVED set in-line (symmetry with the dormant golden): a rollup bug that inflates a spurious
    # 5th ≥10% sector would keep the subset-overlap green, so the golden must constrain membership itself.
    assert set(res["sectors"]) == {"Financials", "Industrials", "Information Technology", "Utilities"}
    (ev,) = events
    assert ev["lead"] == PAIR and ev["type"] == "launch" and ev["payload"]["corroboration"] == "match"
    assert set(ev["payload"]["concentration_sectors"]) == {
        "Financials", "Industrials", "Information Technology", "Utilities"}
    assert ev["payload"]["detected_at"] == "2024-09-09T00:00:00Z"   # T2 preserved (lag measures to detection)
    assert ev["payload"]["soi_as_of"] == "2025-07-31"               # the resolving filing, for provenance
    # The lag is COMPUTED from the two real timestamps (Assertion B); sectors are checked separately.
    lead_events = [{"type": "lead.spawned", "ts": STRUCTURAL_SPAWN, "payload": {"spawner": "xcorr"}}, *events]
    assert cross_stream_lag(lead_events) == timedelta(days=593)


def test_jan2026_soi_is_recorded_dormant_utilities_below_the_frozen_floor(layout):
    events = []
    res = soi_sensor.scan(TEKX, "0001410368-26-034129", ANCHOR, ACTIVE, SoiIngest(layout), CFG, NOW,
                          events.append, lambda *a, **k: None, fetch_body=lambda: JAN2026)
    assert res["action"] == "dormant_no_match"
    assert set(res["sectors"]) == {"Industrials", "Information Technology"}   # Utilities 6.4% < 0.10 -> out
    (ev,) = events
    assert ev["lead"] == SYSTEM_LEAD and ev["payload"]["corroboration"] == "dormant_no_match"
    # The floor stays 0.10 — the dormant as-of truth is recorded, never fitted away.
    assert CFG["corroboration"]["sector_min_weight"] == 0.10
