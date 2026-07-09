"""§4a xcorr wired into the runner — the PRIMARY live lead-spawner (spec §9). Tests are OFFLINE: the
EdgarClient and PriceIngest fetches are injected over in-memory bodies; the socket guard fails any real
connection.

Three properties:
  - end-to-end it FIRES LIVE and PUSHES: the mf map resolves a sector pair to series ids, a planted
    price panel departs, and one tick spawns a real `lead.spawned` (shadow=false) that counts in
    active_nonshadow and — being a state change — pages (unlike a silent launch);
  - it runs clean on the seed and spawns nothing when the universe can't yield a resolvable pair;
  - a batch failure (the panel lacks the market column) is a SOFT fault (§9g) — recorded, the run
    continues, never a crash.

The universe→series_id bridge is THIS tick's mf map (the seed universe is never registered), so the
fires test seeds two sector rows there; SPY carries no series id (a UIT) and is only the β-strip market.
"""

import copy
import json
from pathlib import Path

import numpy as np
import pandas as pd

from prospector.config import load_config
from prospector.fold.fold import active_nonshadow, fold
from prospector.ingest.edgar import MF_TICKERS_URL, EdgarClient, EdgarError
from prospector.ingest.holdings import HoldingsIngest
from prospector.ingest.prices import PriceIngest, PriceIngestError
from prospector.primitives.atomic import write_atomic
from prospector.runner import RunnerDeps, run_tick
from prospector.runner.notify import NullNotifier
from prospector.sensors.xcorr import xcorr_lead_id
from prospector.store.envelope import SYSTEM_LEAD
from prospector.store.event_store import EventStore

CONFIG = Path("config") / "prospector.yaml"
NOW = "2026-07-06T22:30:00Z"

XLK_ROW = [1001, "S000000001", "C000000001", "XLK"]
XLU_ROW = [1002, "S000000002", "C000000002", "XLU"]
XLKxXLU = xcorr_lead_id(["S000000001", "S000000002"])

# §9e: dispersion now runs every tick. A valid SPDR holdings body lets its membership parse; this file's
# price fetch only serves the sector ETFs, so the constituent-price pulls miss and dispersion cleanly
# SKIPS (no fault, no shadow spawn) — leaving these xcorr assertions untouched.
_XLK_HOLDINGS = (Path(__file__).parent / "fixtures" / "holdings" / "XLK_2026-07-02.csv").read_bytes()


def _mf_bytes(rows):
    return json.dumps({"fields": ["cik", "seriesId", "classId", "symbol"], "data": rows}).encode()


def _edgar_fetch(mf_rows):
    body = _mf_bytes(mf_rows)

    def fetch(url, headers):
        if url == MF_TICKERS_URL:
            return body
        raise EdgarError(f"no fixture for {url}", status=404)  # submissions 404 -> no interference

    return fetch


class _Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def _edgar(layout, fetch):
    c = _Clock()
    return EdgarClient("Test/1.0 (test@example.com)", fetch=fetch, clock=c,
                       sleep=lambda s: setattr(c, "t", c.t + s),
                       persist=lambda name, body: write_atomic(layout.edgar_path(NOW[:10], name), body))


def _deps(layout, registry, edgar_fetch, price_fetch, *, cfg=None, notifier=None):
    base_cfg, base_hash = load_config(CONFIG)
    return RunnerDeps(
        layout=layout, registry=registry, event_store=EventStore(layout, registry),
        edgar_client=_edgar(layout, edgar_fetch),
        # api_token: the primary source is now tiingo (config), whose header builder reads a token; a
        # fake one keeps the offline panel building. sleep no-op: the panel pulls 12+ tickers.
        price_ingest=PriceIngest(layout, fetch=price_fetch, clock=lambda: NOW[:10],
                                 sleep=lambda _s: None, api_token="tiingo-test-token"),
        holdings_ingest=HoldingsIngest(layout, fetch=lambda u, h: _XLK_HOLDINGS, clock=lambda: NOW[:10]),
        notifier=notifier if notifier is not None else NullNotifier(),
        cfg=cfg if cfg is not None else base_cfg, cfg_hash=base_hash,
        now=NOW, run_id="run_test", monotonic=lambda: 0.0)


def _clean_body() -> bytes:
    # A minimal valid Tiingo EOD row (the primary source). close != adjClose is fine here; the sensor
    # reads adjClose. One row -> an unwarmed panel that spawns nothing (the seed-clean test).
    return json.dumps([{"date": "2024-01-01T00:00:00.000Z", "close": 200.0, "adjClose": 100.0,
                        "splitFactor": 1.0}]).encode()


def _planted_bodies(n=1030, shift_on=1000, seed=166, loading=3.5, base_sd=0.008) -> dict:
    """{ticker -> Tiingo EOD body} for SPY (market) + XLK/XLU sharing a residual factor from `shift_on`
    to the end, so the pair departs and the LATEST row (~30 days in) is near the z peak. Same construction
    as the sensor test's planted panel — reliably clears z_in at the last row. Synthetic: close==adjClose
    (no splits), which is all the sensor needs (it reads adjClose)."""
    rng = np.random.default_rng(seed)
    mkt = rng.normal(0, 0.01, n)
    common = rng.normal(0, base_sd, n)
    mask = np.zeros(n)
    mask[shift_on:] = 1.0
    series = {"SPY": mkt}
    for k, beta in (("XLK", 1.1), ("XLU", 0.9)):
        series[k] = beta * mkt + rng.normal(0, base_sd, n) + loading * common * mask
    # Consecutive calendar days as ISO8601 (the parser reads `date` -> UTC calendar date).
    dates = [d.strftime("%Y-%m-%dT00:00:00.000Z")
             for d in pd.date_range("2019-01-01", periods=n, freq="D")]
    out = {}
    for k, r in series.items():
        prices = (1 + pd.Series(r)).cumprod() * 100.0
        out[k] = json.dumps([{"date": d, "close": float(p), "adjClose": float(p), "splitFactor": 1.0}
                             for d, p in zip(dates, prices)]).encode()
    return out


# === end-to-end: fires live and pushes ==============================================================

def test_xcorr_fires_live_end_to_end_and_pushes(layout, registry):
    cfg, _ = load_config(CONFIG)
    cfg = copy.deepcopy(cfg)
    cfg["universe"]["sectors"] = ["XLK", "XLU"]   # a 2-sector universe -> exactly one pair
    cfg["universe"]["market"] = "SPY"
    bodies = _planted_bodies()

    def price_fetch(url, headers):
        for t, body in bodies.items():
            if t in url.upper():
                return body
        raise PriceIngestError(f"no body for {url}", status=404)

    notifier = NullNotifier()
    runlog = run_tick(_deps(layout, registry, _edgar_fetch([XLK_ROW, XLU_ROW]), price_fetch,
                            cfg=cfg, notifier=notifier))

    assert runlog.sensors["xcorr"] == "ran"
    # A real LIVE spawn landed on the pair's series-id-keyed lead.
    spawns = registry.events_for_lead(XLKxXLU, "lead.spawned")
    assert len(spawns) == 1
    payload = json.loads(spawns[0]["payload"])
    assert payload["spawner"] == "xcorr" and payload["shadow"] is False
    # It folds active + non-shadow -> counts toward the §8a ceiling; and a live spawn PAGES.
    state = fold(registry.events_for_lead(XLKxXLU))
    assert state["status"] == "active" and state["shadow"] is False
    assert active_nonshadow([state]) == [state]
    assert runlog.changed_leads.get(XLKxXLU) == ["status"]
    assert runlog.pushed is True and len(notifier.pushes) == 1


# === runs clean on the seed, spawns nothing =========================================================

def test_xcorr_runs_clean_and_spawns_nothing_on_seed(layout, registry):
    # Default universe, clean 1-row price bodies, mf map with only XLK -> no resolvable PAIR (needs two)
    # and an unwarmed 1-row panel -> xcorr runs but spawns nothing, and nothing pages.
    runlog = run_tick(_deps(layout, registry, _edgar_fetch([XLK_ROW]),
                            lambda url, headers: _clean_body()))
    assert runlog.sensors["xcorr"] == "ran"
    assert [l for l in registry.all_leads() if str(l).startswith("xcorr-")] == []
    assert registry.events_for_lead(SYSTEM_LEAD, "xcorr.departure") == []
    assert runlog.pushed is False


# === a batch failure (no market column) is a soft fault =============================================

def test_xcorr_missing_market_column_is_a_soft_fault(layout, registry):
    # SPY's price fetch 404s -> the panel has sectors but no market column -> xcorr.scan raises, and the
    # runner records it as a SOFT fault (§9g) and carries on (identity retries still run).
    def price_fetch(url, headers):
        if "SPY" in url.upper():
            raise PriceIngestError("no SPY body", status=404)
        return _clean_body()

    runlog = run_tick(_deps(layout, registry, _edgar_fetch([XLK_ROW]), price_fetch))

    assert runlog.sensors["xcorr"] == "fault"
    faults = [json.loads(f["payload"]) for f in registry.events_for_lead(SYSTEM_LEAD, "fault")]
    assert any(f["subsystem"] == "sensor.xcorr" for f in faults)
    assert runlog.sensors["identity_retries"] == "ran"   # the run continued past the fault
