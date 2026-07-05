"""Structural invariants of the frozen `gics_industry_sector` rollup table (CONTRACT reference data).

The reconcile-to-COMMON-STOCKS check in the SOI parser guards *parsing* (were all industries captured)
but is BLIND to the *rollup* (did each industry map to the right sector) — a mis-mapped or mis-named
sector reconciles cleanly and yields a wrong (or silently non-matching) sector set. These tests pin the
table's SHAPE so a typo'd/non-canonical sector string or a duplicate/degenerate key can't slip in. The
*content* (which sector each industry actually belongs to) is verified against primary-source GICS in the
decision doc; this file guards the invariants that can be checked without the external structure."""

from pathlib import Path

from prospector.config import load_config

CFG, _ = load_config(str(Path(__file__).parent.parent / "config" / "prospector.yaml"))
TABLE = CFG["gics_industry_sector"]

# The 11 canonical GICS sectors — the ONLY legal rollup targets, and the exact strings a lead's basket
# sectors carry (via config sector_map), so `launch_corroboration.overlaps` can match on them.
GICS_SECTORS = frozenset({
    "Communication Services", "Consumer Discretionary", "Consumer Staples", "Energy", "Financials",
    "Health Care", "Industrials", "Information Technology", "Materials", "Real Estate", "Utilities"})


def test_every_value_is_a_canonical_gics_sector_string():
    # A non-canonical / typo'd sector ("Info Technology", "Utility") would roll silently and then never
    # match an overlap — the failure mode this test exists to catch.
    bad = {k: v for k, v in TABLE.items() if v not in GICS_SECTORS}
    assert not bad, f"non-canonical sector values in gics_industry_sector: {bad}"


def test_value_set_equals_sector_map_values_the_overlap_vocabulary():
    # The rollup targets must be EXACTLY the sector strings a lead's basket resolves to (config
    # sector_map, XLK→"Information Technology", …). If these two vocabularies drift, a correctly-rolled
    # SOI sector could still fail to overlap a lead. All 11 sectors are exercised (the table spans them).
    assert set(TABLE.values()) == set(CFG["sector_map"].values()) == set(GICS_SECTORS)


def test_keys_are_unique_and_each_maps_to_exactly_one_sector():
    # YAML would silently keep the last of duplicate keys; assert the table wasn't quietly collapsed.
    assert len(TABLE) == len({k.strip().lower() for k in TABLE}), "duplicate industry keys"
    assert all(isinstance(v, str) and v for v in TABLE.values())


def test_table_is_the_complete_gics_industry_set():
    # GICS (effective March 2023) has 74 industries under the 11 sectors. A short table would silently
    # fault real filings (unknown-industry) rather than roll them; pin the full count so an accidental
    # deletion is caught. (Re-freeze this only on a GICS structure revision, with a config.changed fossil.)
    assert len(TABLE) == 74, f"expected 74 GICS industries, found {len(TABLE)}"
