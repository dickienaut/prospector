"""SOI parser — GICS-industry-grouped sector derivation from the real EDGAR filing (spec §4c resolver;
design docs/2026-07-04-soi-derived-sector-concentration.md).

Assertion A of the split (the sector derivation is checked INDEPENDENTLY of the lag, in the golden
test): parse the two real recorded-real TEKX NPORT-EX filings and confirm the derived `{sector: weight}`
against filed reality, the multi-fund isolation, and the extraction-unreliable → fault discipline. All
offline (frozen fixtures). Synthetic HTML in this file is fabricated for the fault cases and labeled so
in-band."""

from pathlib import Path

from prospector.config import load_config
from prospector.ingest.soi import dominant_sectors, extract_soi_sectors

CFG, _ = load_config(str(Path(__file__).parent.parent / "config" / "prospector.yaml"))
FIX = Path(__file__).parent / "fixtures" / "soi"
JUL2025 = (FIX / "tekx_soi_2025-07-31.htm").read_bytes()
JAN2026 = (FIX / "tekx_soi_2026-01-31.htm").read_bytes()
TEKX = "Transformative Tech Accelerators"
FLOOR = CFG["corroboration"]["sector_min_weight"]  # 0.10, frozen


def _syn_soi(fund_caps, cs_pct, industries, *, total_label="TOTAL COMMON STOCKS 999"):
    """A minimal, obviously SYNTHETIC single-fund SOI (NOT a real filing) for the fault cases: one caps
    fund line, a titled SCHEDULE OF INVESTMENTS, a COMMON STOCKS — cs% header, then INDUSTRY — pct%
    headers, then the TOTAL COMMON STOCKS boundary. Structure mirrors the real DFIN render."""
    rows = "".join(f"<div>{name} — {pct}%</div><div>Some Holding Inc. 1,000 12,345</div>"
                   for name, pct in industries)
    return (f"<!-- SYNTHETIC SOI — fabricated for tests, NOT a real filing -->"
            f"<html><body><div>Table of Contents</div><div>{fund_caps}</div>"
            f"<div>SCHEDULE OF INVESTMENTS</div><div>January 31, 2026 (Unaudited)</div>"
            f"<div>COMMON STOCKS — {cs_pct}%</div>{rows}"
            f"<div>{total_label}</div><div>TOTAL INVESTMENTS — 100.0%</div></body></html>").encode()


# === Assertion A — the derivation produces the RIGHT sectors from the real filing ===============

def test_jul2025_real_soi_derives_four_dominant_sectors_and_reconciles():
    r = extract_soi_sectors(JUL2025, CFG, TEKX)
    assert r["reliable"] and r["as_of"] == "2025-07-31"
    # Filed truth (spec prose listed only 3 — Financials 10.1% ALSO clears; the file, not the prose):
    assert dominant_sectors(r["sectors"], FLOOR) == frozenset(
        {"Financials", "Industrials", "Information Technology", "Utilities"})
    # Reconciles to the "COMMON STOCKS — 99.2%" header.
    assert abs(sum(r["sectors"].values()) - 0.992) < 1e-9
    assert round(r["sectors"]["Information Technology"], 3) == 0.520


def test_jul2025_utilities_clears_only_because_three_industries_roll_up_together():
    # The whole granularity argument: Utilities = Electric 5.3 + Independent Power 2.4 + Multi-Utilities
    # 3.0 = 10.7%. No single industry clears 10%; the industry→sector rollup is what makes it present.
    r = extract_soi_sectors(JUL2025, CFG, TEKX)
    assert round(r["sectors"]["Utilities"], 3) == 0.107
    assert "Utilities" in dominant_sectors(r["sectors"], FLOOR)


def test_jan2026_real_soi_is_dormant_utilities_below_floor():
    r = extract_soi_sectors(JAN2026, CFG, TEKX)
    assert r["reliable"] and r["as_of"] == "2026-01-31"
    # Utilities 6.4% (Electric only) is BELOW the frozen 0.10 floor -> excluded. This is the as-of truth
    # that must stay dormant; the threshold is frozen and NEVER lowered to rescue it (anti-fitting).
    assert round(r["sectors"]["Utilities"], 3) == 0.064
    assert dominant_sectors(r["sectors"], FLOOR) == frozenset({"Industrials", "Information Technology"})
    assert abs(sum(r["sectors"].values()) - 0.996) < 1e-9


def test_multi_fund_isolation_selects_the_target_funds_block():
    # The same industry headers recur across the six funds; the anchor must isolate TEKX's block, not
    # blend it with DECO's. A different anchor yields a materially different derivation.
    tekx = extract_soi_sectors(JAN2026, CFG, TEKX)["sectors"]
    deco = extract_soi_sectors(JAN2026, CFG, "Digital Asset Ecosystem")["sectors"]
    assert round(tekx["Information Technology"], 3) == 0.519
    assert round(deco["Information Technology"], 3) == 0.615        # a different fund -> different numbers
    assert tekx != deco


# === Extraction-unreliable → fault, never a wrong sector set (the §4d discipline) ===============

def test_unknown_industry_flags_unreliable_never_mis_rolls():
    body = _syn_soi("SYNTHETIC TECH ETF", 60.0,
                    [("SOFTWARE", 50.0), ("MADE UP INDUSTRY", 10.0)])
    r = extract_soi_sectors(body, CFG, "Synthetic Tech")
    assert not r["reliable"] and r["sectors"] == {} and "unknown GICS industry" in r["reason"]


def test_reconcile_miss_flags_unreliable():
    # A dropped/misparsed industry: headers sum to 55% but the COMMON STOCKS header says 60% -> the
    # reconcile check (the one that caught SPECIALIZED REITs) faults instead of under-counting.
    body = _syn_soi("SYNTHETIC TECH ETF", 60.0,
                    [("SOFTWARE", 50.0), ("ELECTRIC UTILITIES", 5.0)])
    r = extract_soi_sectors(body, CFG, "Synthetic Tech")
    assert not r["reliable"] and "COMMON STOCKS header" in r["reason"]


def test_fund_not_found_and_no_common_stocks_block_flag_unreliable():
    assert not extract_soi_sectors(JAN2026, CFG, "No Such Fund")["reliable"]
    # State Street Bridgewater All Weather is a futures/derivatives fund — no COMMON STOCKS block, so the
    # parser faults rather than inventing sectors.
    allw = extract_soi_sectors(JAN2026, CFG, "Bridgewater All Weather")
    assert not allw["reliable"] and "COMMON STOCKS" in allw["reason"]


def test_parser_returns_only_structural_keys_never_a_significance_opinion():
    # Boundary: the parser owns WHICH sectors / at what weight — never whether that MEANS anything. Its
    # dict is exactly the structural contract; no "meaningful"/"significant"/"verdict" leaks in.
    r = extract_soi_sectors(JUL2025, CFG, TEKX)
    assert set(r) == {"sectors", "reliable", "reason", "as_of"}
