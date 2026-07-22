"""F1 (post-#99 sweep) — a submissions-JSON shape drift must SURFACE, never masquerade as a not-yet.

The state-collapse bug (N8's unfixed remainder). `edgar.latest_soi` / `latest_prospectus` /
`prospectus_history` read `submissions["filings"]["recent"]` as parallel columnar lists. When that shape
is ABSENT (SEC versions the JSON; the columns move) the OLD code caught `(KeyError, TypeError)` and
returned a bare `None`/`[]` — indistinguishable from "this registrant has no filing of that family on
record". Two consequences, both here:

  1. `classify_soi_target`'s docstring PROMISES that "a swallowed exception — e.g. a submissions-shape
     change — becomes SOI_ERROR and surfaces, instead of masquerading as a not-yet." It did not: the
     KeyError was eaten one layer below its `except Exception` handler, so a drift returned
     SOI_NOT_YET (silent). This test makes that promise true.
  2. The mandate runner does `cur = latest_prospectus(subs); if cur is None: continue` — so a drift
     silently skips EVERY watched fund with zero fault (fleet-wide dormancy).

The fix (Design-ruled): the three helpers RAISE `SubmissionsShapeError` (an `EdgarError` subclass) on a
drifted shape, while a genuinely-absent filing stays the benign `None`/`[]`. The SOI path then surfaces
SOI_ERROR; the mandate path emits ONE operational fault with a drift-scoped `key="submissions_shape"`
(fleet-wide drift pages once, not once-per-fund). See docs/notes/post99_sweep_fixes.diff.

Authored RED against the swallow at main 6eccdabf; GREEN against the reference fix. Asserts BEHAVIOUR
(drift is distinguishable from absence AND surfaces), not the specific exception class or fault string.
"""
import pytest

from prospector.ingest import edgar
from prospector.ingest.edgar import (classify_soi_target, latest_prospectus, latest_soi,
                                      prospectus_history, SOI_ERROR, SOI_NOT_YET,
                                      SubmissionsShapeError, SubmissionsIncompleteError)

# A submissions dict whose FETCH SUCCEEDED (valid JSON, HTTP 200) but whose shape drifted — the
# columnar container is renamed. This is NOT a network error; the bytes are the problem.
DRIFTED = {"cik": 2110, "filings": {"recentFilings": {"form": ["485BPOS"], "filingDate": ["2026-01-02"],
                                                      "accessionNumber": ["x"], "primaryDocument": ["d.htm"]}}}
# A genuinely filing-less registrant: `recent` present, every column empty. Benign not-yet.
ABSENT = {"cik": 2110, "filings": {"recent": {"form": [], "filingDate": [],
                                              "accessionNumber": [], "primaryDocument": []}}}
# UNDETERMINED (the pagination third-state): `recent` is well-formed but carries NO prospectus-family
# filing, WHILE `filings.files[]` (the SEC older-pages pointer) is non-empty — the prospectus may live
# in a page we deliberately do not fetch (B2). Distinct from absence (no older pages → a true not-yet)
# AND from drift (an unreadable shape): "found nothing in the window I have, and there is more I did not
# look at." SEC honored the contract exactly; our request was too narrow.
UNDETERMINED = {"cik": 2110, "filings": {
    "recent": {"form": ["N-CSR"], "filingDate": ["2026-01-02"], "accessionNumber": ["x"],
               "primaryDocument": ["d.htm"]},
    "files": [{"name": "CIK0000002110-submissions-001.json", "filingCount": 900}]}}


class _DriftClient:
    """An EdgarClient whose submissions() succeeds but returns a shape-drifted dict."""
    def submissions(self, cik):
        return DRIFTED
    def filing_index(self, cik, accession):
        raise AssertionError("must not reach filing_index — latest_soi should surface the drift first")


def test_drift_and_absence_are_distinguishable_and_drift_surfaces():
    # ABSENCE stays benign (no filing of that family) — the helpers return the empty sentinels.
    assert latest_prospectus(ABSENT) is None
    assert prospectus_history(ABSENT) == []
    assert latest_soi(ABSENT) is None

    # DRIFT must be DISTINGUISHABLE from absence: it raises, rather than collapsing to the same None/[].
    # (Behaviour asserted: a raised EdgarError, not a specific subclass name — a fix that raises any
    # EdgarError-family error on the unreadable shape satisfies this.)
    for fn in (latest_prospectus, prospectus_history, latest_soi):
        with pytest.raises(edgar.EdgarError):
            fn(DRIFTED)


def test_soi_shape_drift_surfaces_as_error_not_not_yet():
    # The docstring's own named example: a submissions-shape change must become SOI_ERROR, not a silent
    # not-yet. On the unfixed tree this returns (None, SOI_NOT_YET).
    target, reason = classify_soi_target(2110, _DriftClient())
    assert target is None
    assert reason == SOI_ERROR
    assert reason != SOI_NOT_YET


def test_pagination_undetermined_is_a_third_state_distinct_from_absence_and_drift():
    # The pagination third-state (Design 2026-07-22): the F1 split, one condition further along. A
    # submissions dict with NO prospectus in `recent` but a non-empty `filings.files[]` is UNDETERMINED
    # — the prospectus may sit in an older page we don't paginate (B2) — not the benign absence the bare
    # `None` collapsed it into. It must RAISE, distinguishably.
    with pytest.raises(SubmissionsIncompleteError):
        latest_prospectus(UNDETERMINED)

    # The SAME `recent` with NO older pages (`files` empty) is genuine absence → stays the benign None.
    # This is the whole point: absence and undetermined differ ONLY in `files`, and must not collapse.
    no_pages = {"cik": 2110, "filings": {"recent": UNDETERMINED["filings"]["recent"], "files": []}}
    assert latest_prospectus(no_pages) is None

    # The three states are mutually distinguishable BY TYPE, and each is DIFFERENTLY actionable:
    #   absence      → None                       (a benign not-yet, silent)
    #   drift        → SubmissionsShapeError       (a broken read, OPERATIONAL — pages)
    #   undetermined → SubmissionsIncompleteError  (coverage incomplete, REVIEW-ADVISORY — surfaced)
    assert latest_prospectus(ABSENT) is None
    with pytest.raises(SubmissionsShapeError):
        latest_prospectus(DRIFTED)
    with pytest.raises(SubmissionsIncompleteError):
        latest_prospectus(UNDETERMINED)

    # Undetermined is NOT a shape drift: a sibling EdgarError, never a SubmissionsShapeError — so the
    # runner's `except SubmissionsShapeError` (operational page) cannot swallow it into the wrong
    # disposition. It IS an EdgarError, so existing `except EdgarError` sites still catch it.
    assert issubclass(SubmissionsIncompleteError, edgar.EdgarError)
    assert not issubclass(SubmissionsIncompleteError, SubmissionsShapeError)
