"""Two BK-MSG-01 mislabels in the edgar.py submissions/manifest family — right refusal, WRONG cause.

The state-collapse enumeration (`docs/decisions/2026-07-22-submissions-pagination-undetermined.md`, the
`edgar.py` single-sentinel signature — doctrine in `docs/bugs/README.md` §1) found two functions that
surfaced a real fault under a MISLEADING cause: the operator was correctly paged, but with a wrong
diagnosis (the BK-MSG-01 class).

  1. `resolve_soi_document` returned a bare `None` for BOTH a well-formed-but-no-unique-exhibit manifest
     (genuine ambiguity) AND a manifest whose SHAPE it could not read (a drift). `classify_soi_target`
     maps any `None` → `SOI_AMBIGUOUS`, so a BROKEN manifest read was labeled exhibit-ambiguity, never
     `SOI_ERROR`. Fix: a drift RAISES `FilingIndexShapeError` → `SOI_ERROR`; genuine ambiguity stays
     `None` → `SOI_AMBIGUOUS`.
  2. `confirm_prospectus` read `filings.recent` DIRECTLY (bypassing `_recent_columns`), so a
     submissions-shape drift on the resolution path raised a bare `KeyError` → caught upstream by
     `resolve_ticker` / `resolve_series` as `reason='http_error'` (a transport failure it was not). Fix:
     `confirm_prospectus` reads via `_recent_columns` (raises `SubmissionsShapeError`); the resolvers
     catch it → `reason='submissions_shape'`.

§8a (rev 18, broken vs. incomplete): a violated read contract is BROKEN → it surfaces with the
broken-read cause, distinct from a genuine judgment call (ambiguity) and from a transport failure
(http_error). Both fixes keep the DISPOSITION (it still faults + surfaces) and correct only the CAUSE.

Behaviour-asserting: the drift is DISTINGUISHABLE from its genuine counterpart and carries the honest
cause. Authored against `main` 589fd3f (spec rev 18).
"""
import json

import pytest

from prospector.ingest.edgar import (classify_soi_target, confirm_prospectus, resolve_series,
                                      resolve_soi_document, resolve_ticker, EdgarClient, EdgarError,
                                      FilingIndexShapeError, SubmissionsShapeError, ResolutionFailure,
                                      SOI_AMBIGUOUS, SOI_ERROR, MF_TICKERS_URL)


# --- Fix 1: an SOI manifest drift is SOI_ERROR, not the SOI_AMBIGUOUS mislabel ------------------------

def test_resolve_soi_document_raises_on_a_drifted_manifest_but_not_on_genuine_ambiguity():
    # A manifest whose shape we cannot read RAISES (a broken read)...
    for drifted in ({}, {"directory": {}}, {"directory": {"item": None}}, {"directory": "nope"}):
        with pytest.raises(FilingIndexShapeError):
            resolve_soi_document(drifted)
    # ...while a WELL-FORMED manifest with no unique sector-bearing exhibit stays None (genuine ambiguity):
    assert resolve_soi_document({"directory": {"item": [{"name": "abc-index.htm"}]}}) is None        # 0 valid
    assert resolve_soi_document({"directory": {"item": [{"name": "a.htm"}, {"name": "b.htm"}]}}) is None  # >1


class _SoiClient:
    """A fund WITH an SOI filing on record; `filing_index` returns whatever manifest the test supplies."""
    def __init__(self, index):
        self._index = index

    def submissions(self, cik):
        return {"filings": {"recent": {"form": ["NPORT-EX"], "filingDate": ["2026-06-30"],
                "accessionNumber": ["0001111111-26-000001"], "primaryDocument": ["primary_doc.xml"]}}}

    def filing_index(self, cik, accession):
        return self._index


def test_classify_soi_target_manifest_drift_is_error_genuine_ambiguity_is_ambiguous():
    # A DRIFTED manifest -> SOI_ERROR (the honest broken-read cause), NOT the exhibit-ambiguity mislabel.
    _, drift_reason = classify_soi_target(1, _SoiClient({"directoryXX": {}}))
    assert drift_reason == SOI_ERROR
    # A well-formed manifest with two exhibits -> SOI_AMBIGUOUS (genuine: the filing is there, the exhibit
    # is not uniquely resolvable). The two dispositions are now told apart.
    _, amb_reason = classify_soi_target(1, _SoiClient({"directory": {"item": [{"name": "a.htm"},
                                                                              {"name": "b.htm"}]}}))
    assert amb_reason == SOI_AMBIGUOUS
    assert drift_reason != amb_reason


# --- Fix 2: a submissions-shape drift on the resolution path is 'submissions_shape', not 'http_error' -

def test_confirm_prospectus_raises_submissions_shape_on_a_drift_not_a_bare_keyerror():
    # It now reads through `_recent_columns`, so a drift is the TYPED break (was a bare KeyError that the
    # resolvers caught and mislabeled 'http_error').
    with pytest.raises(SubmissionsShapeError):
        confirm_prospectus({"name": "T", "filings": {"recentXX": {}}}, 7)


def _client(fetch):
    return EdgarClient("test@example.com (test)", fetch=fetch, clock=lambda: 0.0, sleep=lambda _s: None)


_MF = {"fields": ["cik", "seriesId", "classId", "symbol"], "data": [[7, "S000000007", "C7", "TICK"]]}


def test_resolve_ticker_and_series_label_a_submissions_shape_drift_distinctly_from_http_error():
    # A DRIFTED submissions JSON on the resolution path -> reason='submissions_shape' (a broken read),
    # NOT the transport-level 'http_error' the generic except used to assign (BK-MSG-01).
    def drift_fetch(url, headers):
        if url == MF_TICKERS_URL:
            return json.dumps(_MF).encode()
        if "submissions" in url:
            return json.dumps({"name": "T", "filings": {"recentXX": {}}}).encode()  # drift: no `recent`
        raise EdgarError(f"no fixture for {url}", status=404)

    rt = resolve_ticker("TICK", _client(drift_fetch))
    assert isinstance(rt, ResolutionFailure) and rt.reason == "submissions_shape"
    rs = resolve_series("S000000007", "TICK", _client(drift_fetch))
    assert isinstance(rs, ResolutionFailure) and rs.reason == "submissions_shape"

    # A genuine transport failure of submissions() still -> 'http_error' (unchanged; the two are split).
    def http_fetch(url, headers):
        if url == MF_TICKERS_URL:
            return json.dumps(_MF).encode()
        raise EdgarError("edgar down", status=503)

    assert resolve_ticker("TICK", _client(http_fetch)).reason == "http_error"
    assert resolve_series("S000000007", "TICK", _client(http_fetch)).reason == "http_error"
