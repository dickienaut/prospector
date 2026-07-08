"""Regression (DESIGN, currently DEFERRED to M7): the SOI-corroboration pass has no cadence gate (N9).

`_run_soi_corroboration` calls `resolve_soi_target` (submissions() + filing_index() = up to 2 SEC
requests) for EVERY unresolved launch on EVERY tick, for up to the 180-day retry horizon. SOIs post
~quarterly, so under a sub-daily cron this is 2N wasted SEC requests per pending launch, indefinitely.
The pass's own docstring names weekly as the intended cadence ("schedule.weekly_day is M7") and calls
the throttle "an M7 scheduling concern, not a correctness one."

>>> IMPORTANT FRAMING <<<
This test encodes a DESIGN DECISION the author has explicitly DEFERRED, not a bug the author disputes.
It is written so the regression exists and is ready the moment the M7 cadence gate lands — but it is
marked `xfail(strict=True)` so it does NOT fail the suite today (an expected-fail that turns into an
unexpected-PASS, flagging the moment the gate is added so the marker can be removed). If you'd rather
treat N9 as active now, delete the xfail marker and it becomes a normal RED test. Either way it asserts
the behaviour a fix must produce: within one cadence period, a pending launch is resolved at most once.

Self-contained harness; counts SEC calls on a fake edgar client.
"""

import json
from pathlib import Path

import pytest

from prospector.runner.runlog import RunLog
from prospector.runner.runner import _run_soi_corroboration
from prospector.store.event_store import EventStore
from prospector.store.fund_registry import FundEntry, FundRegistry
from prospector.store.layout import StoreLayout

SID = "S000099999"
CIK = 5678
DET = "2026-07-08T00:00:00Z"


class _CountingEdgar:
    def __init__(self):
        self.calls = []

    def submissions(self, cik):
        self.calls.append("submissions")
        return {"filings": {"recent": {}}}  # no SOI yet -> a not-yet, stays pending across ticks

    def filing_index(self, cik, accession):
        self.calls.append("filing_index")
        return {"directory": {"item": []}}

    def filing_text(self, *a, **k):
        self.calls.append("filing_text")
        return b""


class _Deps:
    def __init__(self, layout, registry, store, edgar):
        self.layout = layout
        self.registry = registry
        self.event_store = store
        self.edgar_client = edgar
        self.cfg = {"corroboration": {"retry_horizon_days": 180}}


def _seed_pending(layout, registry):
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


@pytest.mark.xfail(reason="N9: SOI-corroboration cadence gate is a DEFERRED M7 item; this test is "
                          "ready for it and will XPASS (flagging removal of this marker) once the "
                          "gate lands", strict=True)
def test_soi_corroboration_does_not_refetch_within_one_cadence_period(layout, registry):
    # Two ticks on the SAME day (well within any weekly cadence period). A cadence-gated pass resolves
    # the pending launch at most ONCE per period; today it re-fetches on every tick (no gate), so the
    # SEC call count doubles. Asserts the gated behaviour (<= one resolve worth of calls across the
    # two same-period ticks).
    store, fr = _seed_pending(layout, registry)
    edgar = _CountingEdgar()
    deps = _Deps(layout, registry, store, edgar)

    day1a = "2026-07-10T02:00:00Z"
    day1b = "2026-07-10T14:00:00Z"  # same UTC day, same weekly period
    for now in (day1a, day1b):
        _run_soi_corroboration(deps, store, now, [], RunLog(run_id="r", ts=now, date=now[:10]), fr)

    # One pending launch, two same-period ticks: a gate means it is resolved once (<=1 submissions call
    # for this launch across the period). Ungated today -> 2.
    submissions_calls = edgar.calls.count("submissions")
    assert submissions_calls <= 1, (
        f"the SOI-corroboration pass issued {submissions_calls} submissions() calls for ONE pending "
        "launch across two same-period ticks — there is no cadence gate, so every tick re-fetches SEC "
        "for up to 180 days (N9). A weekly gate should resolve each pending launch at most once per "
        "period")
