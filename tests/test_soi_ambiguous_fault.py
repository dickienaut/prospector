"""Regression: an AMBIGUOUS SOI exhibit must surface a fault, not vanish as a silent not-yet (N8).

`resolve_soi_target` wraps its whole pipeline in `except Exception: return None` and ALSO returns None
when `resolve_soi_document` finds no unique exhibit. So two very different outcomes collapse into the
same None:

  * a genuine NOT-YET — the fund has no SOI filing indexed yet (re-attempt next cycle, silent);
  * a FAULT — the SOI filing exists but its exhibit is ambiguous (>1 candidate .htm), which the design
    (resolve_soi_document docstring, the 07-06 SOI decision doc) says must SURFACE for manual review.

The runner's `if target is None: continue` treats both as not-yet and emits NO `_system` fault. Result:
an ambiguous filing is silently re-fetched every tick until the 180-day horizon and NEVER surfaces —
"observe it once" is impossible because it's invisible. The bare `except Exception` also swallows real
programming errors (a KeyError on a submissions-shape change) as not-yets.

These assert the observable CONTRACT: a resolvable-but-ambiguous SOI emits a corroboration/ingest
fault this tick, while a genuine not-yet stays silent. The fix (return a typed marker distinguishing
ambiguous from not-yet, and emit a fault on ambiguity; narrow the bare except) can take any shape that
makes the two cases distinguishable. Self-contained harness.

Reproduction of the ambiguity itself is unit-verified against the real resolve_soi_document below; the
runner-level test proves the silent-not-yet consequence.
"""

import json
from pathlib import Path

import pytest

from prospector.ingest.edgar import resolve_soi_document
from prospector.runner.runlog import RunLog
from prospector.runner.runner import _run_soi_corroboration
from prospector.store.event_store import EventStore
from prospector.store.fund_registry import FundEntry, FundRegistry
from prospector.store.layout import StoreLayout

NOW = "2026-07-10T00:00:00Z"
DET = "2026-07-08T00:00:00Z"
SID = "S000099999"
CIK = 5678


def test_resolve_soi_document_returns_none_on_ambiguity_today():
    # Unit-level: prove the ambiguity really collapses to None (the caller then can't tell it from a
    # not-yet). This is a documentation-of-current-behaviour assertion, GREEN today, that pins the
    # premise of the runner-level test below. If a fix makes resolve_soi_document raise/return-typed on
    # ambiguity instead, update this together with the runner test.
    zero = resolve_soi_document({"directory": {"item": [{"name": "abc-index.htm"}]}})   # cover page only
    two = resolve_soi_document({"directory": {"item": [{"name": "a.htm"}, {"name": "b.htm"}]}})
    assert zero is None and two is None  # both None -> indistinguishable at the call site (the N8 root)


class _AmbiguousEdgar:
    """An edgar client whose fund HAS an SOI filing, but whose exhibit index is AMBIGUOUS (two .htm
    candidates) — the fault case. submissions() returns a real NPORT-EX; filing_index() returns two
    sector-bearing candidates so resolve_soi_document refuses to guess."""

    def submissions(self, cik):
        return {"filings": {"recent": {
            "form": ["NPORT-EX"], "filingDate": ["2026-06-30"],
            "accessionNumber": ["0001111111-26-000001"], "primaryDocument": ["primary_doc.xml"]}}}

    def filing_index(self, cik, accession):
        return {"directory": {"item": [{"name": "exhibit_a.htm"}, {"name": "exhibit_b.htm"}]}}

    def filing_text(self, *a, **k):  # never reached (target resolves to None today)
        return b""


class _NotYetEdgar:
    """A fund with NO SOI filing yet — the legitimate silent not-yet."""

    def submissions(self, cik):
        return {"filings": {"recent": {
            "form": ["485BPOS"], "filingDate": ["2026-06-30"],
            "accessionNumber": ["0001111111-26-000009"], "primaryDocument": ["docA.htm"]}}}

    def filing_index(self, cik, accession):
        return {"directory": {"item": []}}

    def filing_text(self, *a, **k):
        return b""


class _Deps:
    def __init__(self, layout, registry, store, edgar):
        self.layout = layout
        self.registry = registry
        self.event_store = store
        self.edgar_client = edgar
        self.cfg = {"corroboration": {"retry_horizon_days": 180}}


def _seed_pending_launch(layout, registry):
    store = EventStore(layout, registry)
    store.append({"ts": DET, "lead": "_system", "type": "launch",
                  "payload": {"series_id": SID, "ticker": "NEWX", "detected_at": DET,
                              "corroboration": "sectors_unresolved"}, "schema": 1})
    fr = FundRegistry(layout, registry, store)
    fr.upsert(FundEntry(series_id=SID, class_ids=["C000099999"], cik=CIK, ticker_current="NEWX",
                        name="New Fund ETF", issuer="Issuer", category_draft=None,
                        concentration_industries=[], prospectus_accession="",
                        holdings_source="", first_seen=DET, verified_at=DET))
    return store, fr


def _run(layout, registry, edgar):
    store, fr = _seed_pending_launch(layout, registry)
    faults = []
    _run_soi_corroboration(_Deps(layout, registry, store, edgar), store, NOW, faults,
                           RunLog(run_id="r", ts=NOW, date=NOW[:10]), fr)
    soi_faults = [f for f in faults
                  if "soi" in str(f.get("subsystem", "")) or "ingest" in str(f.get("subsystem", ""))]
    return faults, soi_faults


def test_ambiguous_soi_exhibit_emits_a_fault(layout, registry):
    # The SOI exists but the exhibit is ambiguous — the design says surface it for manual review. RED
    # today: resolve_soi_target returns None, the runner `continue`s, no fault is emitted, the
    # ambiguous filing is silently re-fetched forever.
    faults, soi_faults = _run(layout, registry, _AmbiguousEdgar())
    assert soi_faults, (
        "an ambiguous SOI exhibit produced NO fault — it is indistinguishable from a not-yet and is "
        "silently re-fetched every tick, so 'observe it once' is impossible; ambiguity must emit a "
        "soi/ingest fault for manual review (N8)")


def test_genuine_not_yet_stays_silent(layout, registry):
    # The complement, and the reason the fix must DISTINGUISH rather than fault-on-every-None: a fund
    # with no SOI filing yet is a legitimate not-yet — it must NOT emit a fault (that would be the
    # nuisance-alarm failure). GREEN today and must stay GREEN after the fix.
    faults, soi_faults = _run(layout, registry, _NotYetEdgar())
    assert not soi_faults, (
        f"a genuine not-yet (no SOI filing) emitted a fault ({soi_faults}) — only AMBIGUITY should "
        "fault; a not-yet stays silent and re-attempts (N8)")
