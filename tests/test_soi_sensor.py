"""SOI sensor — the deferred pass that resolves `sectors_unresolved` (spec §4c resolver).

Mirrors the mandate-sensor tests: the bytes arrive via a `fetch_body` seam (freeze-before-parse,
idempotent), extraction-unreliable emits a `fault` on `_system` and NO accretion, and a reliable overlap
accretes a `launch`/`match` onto the live lead. Offline; synthetic SOI HTML is fabricated in-band."""

from pathlib import Path

from prospector.config import load_config
from prospector.ingest.soi import SoiIngest
from prospector.sensors import soi as soi_sensor
from prospector.sensors.xcorr import xcorr_lead_id
from prospector.store.envelope import SYSTEM_LEAD

CFG, _ = load_config(str(Path(__file__).parent.parent / "config" / "prospector.yaml"))
XLK, XLU = "S000006415", "S000006416"
ACC = "0001410368-26-999999"
NOW = "2026-07-04T00:00:00Z"
# a launch recorded dormant (sectors_unresolved) at detection; this pass reaches back, detected_at as T2
LAUNCH = {"series_id": "S000087749", "ticker": "SYN", "detected_at": "2024-09-09T00:00:00Z",
          "unverified_ref": "u1"}


def _syn_soi(cs_pct, industries):
    rows = "".join(f"<div>{n} — {p}%</div><div>Holding Inc. 1,000 12,345</div>" for n, p in industries)
    return (f"<!-- SYNTHETIC SOI — fabricated for tests, NOT a real filing -->"
            f"<html><body><div>Table of Contents</div><div>SYNTHETIC TECH ETF</div>"
            f"<div>SCHEDULE OF INVESTMENTS</div><div>January 31, 2026 (Unaudited)</div>"
            f"<div>COMMON STOCKS — {cs_pct}%</div>{rows}"
            f"<div>TOTAL COMMON STOCKS 999</div><div>TOTAL INVESTMENTS — 100.0%</div></body></html>"
            ).encode()


def _advisory_to(events):
    """Mirror the runner's §10 fault-reporter: a review-advisory fault into `events` (where the old raw
    emit fault landed), so a test reads it there and proves scan routes the extraction-unreliable punt
    through report_advisory rather than a raw fault write. Inert when the advisory path isn't hit."""
    def report(subsystem, message, series_id, extra=None):
        events.append({"ts": NOW, "lead": SYSTEM_LEAD, "type": "fault",
                       "payload": {"subsystem": subsystem, "message": message, "series_id": series_id,
                                   "category": "review-advisory", **(extra or {})}})
    return report


def test_reliable_overlap_accretes_launch_match_onto_the_lead(layout):
    # IT 50% + Utilities 10% both clear -> overlaps the XLK×XLU pair -> match, detected_at preserved.
    pair = xcorr_lead_id([XLK, XLU])
    active = {pair: frozenset({"Information Technology", "Utilities"})}
    body = _syn_soi(60.0, [("SOFTWARE", 50.0), ("ELECTRIC UTILITIES", 10.0)])
    events = []
    res = soi_sensor.scan(LAUNCH, ACC, "Synthetic Tech", active, SoiIngest(layout), CFG, NOW,
                          events.append, _advisory_to(events), fetch_body=lambda: body)
    assert res["action"] == "corroborated" and res["matched"] == [pair]
    (ev,) = events
    assert ev["lead"] == pair and ev["type"] == "launch" and ev["payload"]["corroboration"] == "match"
    assert ev["payload"]["detected_at"] == "2024-09-09T00:00:00Z"   # T2 preserved through the deferral
    assert ev["payload"]["soi_accession"] == ACC and ev["payload"]["soi_as_of"] == "2026-01-31"


def test_freeze_is_idempotent_second_pass_reads_the_frozen_blob(layout):
    pair = xcorr_lead_id([XLK, XLU])
    active = {pair: frozenset({"Information Technology", "Utilities"})}
    body = _syn_soi(60.0, [("SOFTWARE", 50.0), ("ELECTRIC UTILITIES", 10.0)])
    soi = SoiIngest(layout)
    calls = {"n": 0}

    def fetch():
        calls["n"] += 1
        return body

    soi_sensor.scan(LAUNCH, ACC, "Synthetic Tech", active, soi, CFG, NOW, [].append, _advisory_to([]), fetch_body=fetch)
    assert soi.has_frozen(LAUNCH["series_id"], ACC) and calls["n"] == 1
    # second pass: blob on file -> no refetch (drop-and-freeze, extract-on-read)
    soi_sensor.scan(LAUNCH, ACC, "Synthetic Tech", active, soi, CFG, NOW, [].append, _advisory_to([]), fetch_body=fetch)
    assert calls["n"] == 1


def test_unreliable_extraction_faults_on_system_and_accretes_nothing(layout):
    pair = xcorr_lead_id([XLK, XLU])
    active = {pair: frozenset({"Information Technology", "Utilities"})}
    body = _syn_soi(60.0, [("SOFTWARE", 50.0), ("MADE UP INDUSTRY", 10.0)])   # unknown industry
    events = []
    res = soi_sensor.scan(LAUNCH, ACC, "Synthetic Tech", active, SoiIngest(layout), CFG, NOW,
                          events.append, _advisory_to(events), fetch_body=lambda: body)
    assert res["action"] == "flagged_unreliable"
    (ev,) = events
    assert ev["lead"] == SYSTEM_LEAD and ev["type"] == "fault"
    assert ev["payload"]["subsystem"] == "soi" and "manual review" in ev["payload"]["message"]
    # §10: a REVIEW-ADVISORY routed through report_advisory (not a raw emit fault), carrying its series_id.
    assert ev["payload"]["category"] == "review-advisory" and ev["payload"]["series_id"] == LAUNCH["series_id"]
    assert not any(e["type"] == "launch" for e in events)          # no sector claim, no accretion


def test_no_overlap_records_dormant_on_system(layout):
    pair = xcorr_lead_id([XLK, XLU])
    active = {pair: frozenset({"Information Technology", "Utilities"})}
    body = _syn_soi(60.0, [("SOFTWARE", 50.0), ("CAPITAL MARKETS", 10.0)])   # Financials, not Utilities
    events = []
    res = soi_sensor.scan(LAUNCH, ACC, "Synthetic Tech", active, SoiIngest(layout), CFG, NOW,
                          events.append, _advisory_to(events), fetch_body=lambda: body)
    assert res["action"] == "dormant_no_match"
    (ev,) = events
    assert ev["lead"] == SYSTEM_LEAD and ev["payload"]["corroboration"] == "dormant_no_match"


def test_reliable_but_no_dominant_sector_records_no_dominant_sector_on_system(layout):
    # A reliably-parsed but DIFFUSE book — seven sectors each below the 0.10 floor, none dominant. The
    # source owns the empty case (route_corroboration requires a non-empty set): recorded honestly as
    # `no_dominant_sector`, NOT mislabeled `dormant_no_match` (which means "had dominant sectors, none
    # overlapped") nor `sectors_unresolved` (the file DOES carry sectors). detected_at still preserved.
    pair = xcorr_lead_id([XLK, XLU])
    active = {pair: frozenset({"Information Technology", "Utilities"})}
    body = _syn_soi(60.0, [("SOFTWARE", 9.0), ("ELECTRIC UTILITIES", 9.0), ("CAPITAL MARKETS", 9.0),
                           ("METALS & MINING", 9.0), ("OIL, GAS & CONSUMABLE FUELS", 9.0),
                           ("AUTOMOBILES", 9.0), ("MACHINERY", 6.0)])
    events = []
    res = soi_sensor.scan(LAUNCH, ACC, "Synthetic Tech", active, SoiIngest(layout), CFG, NOW,
                          events.append, _advisory_to(events), fetch_body=lambda: body)
    assert res["action"] == "no_dominant_sector" and res["matched"] == []
    (ev,) = events
    assert ev["lead"] == SYSTEM_LEAD and ev["payload"]["corroboration"] == "no_dominant_sector"
    assert ev["payload"]["concentration_sectors"] == []
    assert ev["payload"]["detected_at"] == "2024-09-09T00:00:00Z"   # T2 still preserved


def test_no_blob_and_no_fetch_is_a_noop_never_a_guess(layout):
    # The M5 runner supplies fetch_body; until then a fund with no frozen SOI is simply not resolved yet
    # (no event) rather than guessed.
    events = []
    res = soi_sensor.scan(LAUNCH, ACC, "Synthetic Tech", {}, SoiIngest(layout), CFG, NOW, events.append, _advisory_to(events))
    assert res["action"] == "none" and events == []
