"""Regression: build_panel must not accept duplicate dates (finding N3).

prices.py's own §3 contract (build_panel docstring): "missing rows stay missing; a filled hole would
fabricate a correlation observation." build_panel already faults LOUDLY on two guard-worthy inputs —
an empty tidy frame, and a duplicate TICKER. But it silently accepts a duplicate DATE within one
ticker's frame: _tidy drops NaN and sorts but never de-duplicates on date, so a source body with two
rows for the same calendar date yields a non-unique DatetimeIndex. On the outer join, a co-listed
ticker's single value for that date is broadcast onto BOTH duplicate rows — a fabricated
cross-sectional observation, exactly what the contract forbids — and every downstream returns/xcorr
computation on the non-unique index is corrupted (pct_change straddles the dup) or raises on reindex.

Trigger: a Tiingo/vendor duplicate row, or an upstream-merged overlapping re-pull. We build it through
the REAL parse_tiingo so the test tracks the actual ingest path, not a hand-built frame.
"""

import json

import pandas as pd
import pytest

from prospector.ingest.prices import build_panel, parse_tiingo


def _tiingo_body(rows):
    return json.dumps(rows).encode("utf-8")


# A well-formed single-date row helper (adjClose is the field parse_tiingo reads).
def _row(date, adj):
    return {"date": f"{date}T00:00:00.000Z", "close": adj * 2, "adjClose": adj, "splitFactor": 1.0}


def test_parse_tiingo_frame_has_unique_dates():
    # A duplicate-date body (two rows for 2024-01-02) must not survive into a tidy frame with a
    # non-unique date — the tidy frame is the unit build_panel trusts. RED today: _tidy keeps both.
    body = _tiingo_body([_row("2024-01-02", 10.0), _row("2024-01-02", 10.1), _row("2024-01-03", 11.0)])
    frame = parse_tiingo(body, "AAA")
    dupes = frame["date"].duplicated().sum()
    assert dupes == 0, (
        f"parse_tiingo/_tidy kept {dupes} duplicate-date row(s) for AAA — a non-unique date lets "
        "build_panel's outer join fabricate a cross-observation (N3)")


def test_build_panel_rejects_or_dedups_duplicate_dates():
    # The behavioural guarantee, fix-agnostic: after build_panel, the panel index is unique — whether
    # the fix dedups in _tidy (keep=last) or faults loudly in build_panel like the dup-ticker case.
    # A dup-date column joined against a clean co-listed ticker is the fabrication trigger.
    dup = parse_tiingo(_tiingo_body(
        [_row("2024-01-02", 10.0), _row("2024-01-02", 10.1), _row("2024-01-03", 11.0)]), "AAA")
    clean = parse_tiingo(_tiingo_body(
        [_row("2024-01-02", 50.0), _row("2024-01-03", 51.0)]), "BBB")

    try:
        panel = build_panel([dup, clean])
    except ValueError:
        # Faulting loudly on the duplicate (like the duplicate-ticker guard) is an acceptable fix.
        return

    assert panel.index.is_unique, (
        "build_panel produced a non-unique DatetimeIndex from a duplicate-date input — the outer "
        "join broadcasts BBB's single 2024-01-02 value onto both AAA rows, fabricating a "
        "cross-sectional correlation observation the §3 contract forbids (N3)")
    # If dedup was the chosen fix, the surviving BBB value must not have been duplicated either.
    assert (panel.index == pd.Timestamp("2024-01-02")).sum() == 1
