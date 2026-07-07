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
    # blend it with DECO's. A different anchor yields a materially different derivation. DECO's anchor
    # carries "Galaxy" so it does NOT also match the sibling HEDGED fund (see the ambiguity test below).
    tekx = extract_soi_sectors(JAN2026, CFG, TEKX)["sectors"]
    deco = extract_soi_sectors(JAN2026, CFG, "Galaxy Digital Asset Ecosystem")["sectors"]
    assert round(tekx["Information Technology"], 3) == 0.519
    assert round(deco["Information Technology"], 3) == 0.615        # a different fund -> different numbers
    assert tekx != deco


def test_ambiguous_anchor_faults_never_guesses_by_document_order():
    # "Digital Asset Ecosystem" is a substring of BOTH the plain and the HEDGED sibling fund. Picking the
    # first by document order could isolate the WRONG fund with reliable:True — a wrong sector set, the
    # worst outcome. The parser must FAULT on an ambiguous anchor (extraction-unreliable → fault).
    r = extract_soi_sectors(JAN2026, CFG, "Digital Asset Ecosystem")
    assert not r["reliable"] and r["sectors"] == {} and "ambiguous" in r["reason"]


def test_missing_anchor_faults_rather_than_crashing():
    # A launch whose name never resolved could reach the pass with a None/empty anchor; that is a fault
    # for manual review, never an uncaught AttributeError that aborts the whole deferred pass.
    for bad in (None, "", "   "):
        r = extract_soi_sectors(JAN2026, CFG, bad)
        assert not r["reliable"] and r["sectors"] == {}


def test_wrapped_section_header_fund_is_isolable():
    # In the real 2025 filing the DECO/HECO headers render line-WRAPPED ("...SCHEDULE OF" / "INVESTMENTS")
    # rather than on one line; without wrap handling those funds are invisible to section detection. The
    # anchor must still isolate the wrapped fund's block (and reconcile), proving detection is robust.
    r = extract_soi_sectors(JUL2025, CFG, "Galaxy Digital Asset Ecosystem")
    assert r["reliable"] and r["as_of"] == "2025-07-31" and r["sectors"]


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


# === H4 — the plain-REIT alias (proves the gap: faults without it, rolls up with it) =============

def test_h4_plain_reit_header_faults_without_the_alias_and_rolls_up_with_it():
    # DFIN can render the equity-REIT industry GROUP as a single collapsed "REAL ESTATE INVESTMENT TRUSTS"
    # header instead of the specific sub-industries (Diversified/Specialized/… REITs). That header is NOT
    # itself a GICS industry, so the canonical 74-row table alone faults on it; the explicit
    # gics_industry_alias rolls it to Real Estate. (No real fixture exercises this — in both TEKX filings
    # the plain header appears only under CORPORATE BONDS & NOTES, a bond-issuer class the COMMON STOCKS
    # bracket excludes — so it is proven synthetically; see the SOI-fetch decision doc.)
    body = _syn_soi("SYNTHETIC REIT ETF", 60.0,
                    [("SOFTWARE", 50.0), ("REAL ESTATE INVESTMENT TRUSTS", 10.0)])

    # WITHOUT the alias: the plain header is an unknown industry -> fault, never a silent mis-roll.
    no_alias = {**CFG, "gics_industry_alias": {}}
    bare = extract_soi_sectors(body, no_alias, "Synthetic REIT")
    assert not bare["reliable"] and bare["sectors"] == {}
    assert "unknown GICS industry" in bare["reason"] and "REAL ESTATE INVESTMENT TRUSTS" in bare["reason"]

    # WITH the alias (the shipped config): rolls up to Real Estate and reconciles to COMMON STOCKS 60%.
    ok = extract_soi_sectors(body, CFG, "Synthetic REIT")
    assert ok["reliable"], ok["reason"]
    assert round(ok["sectors"]["Real Estate"], 3) == 0.10
    assert ok["sectors"]["Information Technology"] == 0.50
    assert abs(sum(ok["sectors"].values()) - 0.60) < 1e-9


def test_h4_alias_does_not_perturb_the_real_tekx_goldens():
    # The alias can only ADD a key; the two real TEKX derivations must be byte-for-byte unchanged (the
    # plain header never enters TEKX's COMMON STOCKS block). Anti-regression for the +593 / dormant goldens.
    no_alias = {**CFG, "gics_industry_alias": {}}
    for body in (JUL2025, JAN2026):
        assert extract_soi_sectors(body, CFG, TEKX) == extract_soi_sectors(body, no_alias, TEKX)


# === §9b robustness items — the section detector (regression) ====================================

def test_consolidated_header_detected_and_continuation_page_skipped():
    # Two §9b robustness items at once: the section detector must accept the "CONSOLIDATED SCHEDULE OF
    # INVESTMENTS" prefix AND skip a "(continued)" continuation page. The continuation repeats the SAME
    # caps fund title, so if it were treated as a fresh block the anchor would match TWO blocks and fault
    # as ambiguous — reliable:True therefore proves both the prefix match and the continuation skip.
    fund = "SYNTHETIC CONSOLIDATED ETF"
    body = (
        "<!-- SYNTHETIC SOI — fabricated for tests, NOT a real filing -->"
        "<html><body><div>Table of Contents</div>"
        f"<div>{fund}</div><div>CONSOLIDATED SCHEDULE OF INVESTMENTS</div>"
        "<div>January 31, 2026 (Unaudited)</div>"
        "<div>COMMON STOCKS — 60.0%</div>"
        "<div>SOFTWARE — 50.0%</div><div>Holding A 1,000 2,000</div>"
        "<div>ELECTRIC UTILITIES — 10.0%</div><div>Holding B 1,000 2,000</div>"
        "<div>TOTAL COMMON STOCKS 999</div><div>TOTAL INVESTMENTS — 100.0%</div>"
        # continuation page for the SAME fund — must be SKIPPED (next line is "(continued)"):
        f"<div>{fund}</div><div>CONSOLIDATED SCHEDULE OF INVESTMENTS</div><div>(continued)</div>"
        "<div>SOFTWARE — 50.0%</div><div>Holding C 1,000 2,000</div>"
        "</body></html>"
    ).encode()
    r = extract_soi_sectors(body, CFG, "Synthetic Consolidated")
    assert r["reliable"], r["reason"]
    assert dominant_sectors(r["sectors"], FLOOR) == frozenset({"Information Technology", "Utilities"})
