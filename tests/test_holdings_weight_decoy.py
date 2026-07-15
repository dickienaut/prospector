"""H3-DECOY — the prefix header matcher must not silently read a decoy 'weight*' column.

Cold-read finding (2026-07-15, against branch tier4-sweep @ e0739956): PR #67's H3 fix changed
holdings._col to locate a header column by PREFIX (startswith) so a known issuer variant like
"Weight (%)" resolves. But _col is FIRST-MATCH-WINS, so a decoy column whose name merely STARTS with
"weight" — e.g. "Weighted Average Life", a standard column on SPDR fixed-income ETF holdings files —
placed before the real "Weight" column is read AS the weight, silently, with NO fault. That is exactly
the loud->silent severity inversion the sweep's own build-note ground-rule 4 names as its one design
line: the mandatory-negative test only covers a FULLY-alien header, not a prefix-decoy collision.

Latent, not live: the real TEKX equity-ETF fixture has "Weight" as its only weight-prefixed column, so
the current substrate never triggers it. It would bite the moment the universe extends to bond funds.

These tests assert BEHAVIOUR (a decoy 'weight*' column must not be silently used as the weight; an
ambiguous header must fault loud), not a specific implementation. FIXED (the apply PR): `_col` now prefers
an EXACT match over a prefix, so a real "Weight" column wins over a "Weighted Average Life" decoy; and
`_weight_prefix_count` faults loud when >1 columns start with "weight" and none is exactly "Weight". The
QA->implementer handoff is complete — the RED-first `xfail(strict)` marker is removed and these are now
passing regression guards.
"""

import pytest

from prospector.ingest.holdings import parse_spdr_holdings, HoldingsIngestError


# a real-shaped SPDR fixed-income header: a decoy "Weighted Average Life" column precedes the real
# "Weight" column. The two carry DIFFERENT numbers so the source column is unambiguous in the result.
_DECOY_BODY = (b"Name,Weighted Average Life,Weight,Sector\n"
               b"ACME CORP,55,60,Financials\n"
               b"BETA CORP,45,40,Financials\n")


def test_decoy_weight_prefixed_column_is_not_silently_used():
    # A correct parser either reads the REAL Weight column (0.60/0.40) or faults loud on the ambiguity.
    # It must NOT silently return the decoy column's 0.55/0.45.
    try:
        df = parse_spdr_holdings(_DECOY_BODY, "DECOYX")
    except HoldingsIngestError:
        return  # faulting loud on the ambiguous header is an acceptable (safe) resolution
    weights = [round(w, 4) for w in df["weight"]]
    assert weights != [0.55, 0.45], (
        f"silently read the decoy 'Weighted Average Life' column as the weight: {weights}")


def test_unambiguous_weight_header_still_parses():
    # Guard against over-correction: a single real "Weight" column (no decoy) must still parse cleanly,
    # and the known "Weight (%)" issuer variant the H3 fix was built to accept must keep working.
    body = b"Name,Weight,Sector\nACME CORP,60,Financials\nBETA CORP,40,Financials\n"
    df = parse_spdr_holdings(body, "OKX")
    assert [round(w, 4) for w in df["weight"]] == [0.60, 0.40]
    variant = b"Name,Weight (%),Ticker,Identifier,Sector\nACME,50,AC,037833100,Tech\nBETA,50,BC,594918104,Tech\n"
    df2 = parse_spdr_holdings(variant, "VARX")
    assert [round(w, 4) for w in df2["weight"]] == [0.50, 0.50]


def test_two_weight_prefixed_columns_with_no_exact_weight_faults_loud():
    # H3-DECOY, the genuinely-ambiguous case: two "weight*" columns and NO exact "Weight" — the parser
    # cannot know which is the holding weight, so it must fault LOUD, never guess one silently (`_col`'s
    # exact-preference can't disambiguate here; `_weight_prefix_count` catches it).
    body = (b"Name,Weighted Average Life,Weight (%),Sector\n"
            b"ACME CORP,55,60,Financials\n"
            b"BETA CORP,45,40,Financials\n")
    with pytest.raises(HoldingsIngestError, match="ambiguous holdings header"):
        parse_spdr_holdings(body, "AMBIGX")
