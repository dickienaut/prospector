"""§4b/§9e dispersion wired into the runner — the SECOND live spawner, in SHADOW (spec §9, rev2 build
note). Tests are OFFLINE: the EdgarClient / PriceIngest / HoldingsIngest fetches are injected over
in-memory bodies; the socket guard fails any real connection.

The acceptance gate (rev2 §5, "prove a spawner fires on REAL seed data, not merely that it's wired"):
  - it FIRES LIVE end-to-end on REAL holdings-derived membership (the XLK fixture goes through the real
    parse -> weight_covering -> membership path) + a constituent panel that genuinely departs -> one
    tick spawns a real `lead.spawned` (spawner=dispersion, shadow=true) that folds active-shadow, is
    EXCLUDED from active_nonshadow / the §8a ceiling, sets `pushed=False` (a shadow-only change is not
    page-worthy, §9e), and starts the burn-in clock (`spawned_at`); the tick carries the generous payload;
  - the PUSH-BOUNDARY violation (§9e): shadow does NOT page, but a non-shadow xcorr spawn on the SAME
    tick still does (pushed=True because of xcorr, never the shadow lead);
  - null-silent (a calm basket spawns nothing);
  - §9f state reconstruction from the record (an active shadow lead ticks, does not re-spawn; a reverted
    one can re-enter);
  - the per-basket soft-fault boundary (one basket's broken holdings feed faults THAT basket, not the run).

The membership comes through the REAL holdings path (parse_spdr_holdings on the recorded XLK fixture) —
a test feeding synthetic membership that could never occur live would prove nothing (the rule's own
failure mode). House convention: each test builds its own RunnerDeps (no shared helper module).
"""

import copy
import json
from pathlib import Path

import numpy as np
import pandas as pd

from prospector.config import load_config
from prospector.dashboard.views import ceiling_status
from prospector.fold.fold import active_nonshadow, fold
from prospector.ingest.edgar import MF_TICKERS_URL, EdgarClient, EdgarError
from prospector.ingest.holdings import HoldingsIngest, HoldingsIngestError
from prospector.ingest.prices import PriceIngest
from prospector.primitives.atomic import write_atomic
from prospector.runner import RunnerDeps, run_tick
from prospector.runner.notify import NullNotifier
from prospector.runner.runner import _build_constituent_panel
from prospector.sensors import dispersion
from prospector.sensors.dispersion import dispersion_lead_id
from prospector.sensors.xcorr import xcorr_lead_id
from prospector.store.envelope import SYSTEM_LEAD
from prospector.store.event_store import EventStore

CONFIG = Path("config") / "prospector.yaml"
NOW = "2026-07-14T22:30:00Z"

XLK_SERIES = "S000006415"                      # matches the XLK holdings fixture / identity seed
XLK_ROW = [1001, XLK_SERIES, "C000019213", "XLK"]
XLU_SERIES = "S000006420"
XLU_ROW = [1002, XLU_SERIES, "C000019220", "XLU"]
XLK_LEAD = dispersion_lead_id(XLK_SERIES)

_XLK_HOLDINGS = (Path(__file__).parent / "fixtures" / "holdings" / "XLK_2026-07-02.csv").read_bytes()

# The XLK fixture's weight-covering (0.90) constituents, in weight-desc order, with their CUSIPs (the
# panel keys) — and a two-block assignment used to plant a real correlation fracture.
XLK_CUSIPS = {"AAPL": "037833100", "MSFT": "594918104", "NVDA": "67066G104", "ADBE": "00724F101",
              "AVGO": "11135F101", "ORCL": "68389X105", "CRM": "79466L302", "AMD": "007903107"}
_BLOCK = {"AAPL": "A", "MSFT": "A", "NVDA": "A", "ADBE": "A",
          "AVGO": "B", "ORCL": "B", "CRM": "B", "AMD": "B"}


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


def _constituent_prices(fractured=True, n_days=400, split_at=330, seed=11):
    """{ticker -> price Series} for the 8 XLK constituents. fractured=True plants a late two-block
    fracture (Q departs hard — a fixed seed pins the realized departure at z~3.1, comfortably over the
    real z_in=2.5, deterministically); fractured=False keeps a single common-factor block (Q ~ 0).
    Mirrors the sensor test's construction, but keyed by the fixture's real tickers so the runner prices
    them and re-keys the panel to CUSIPs."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2022-01-03", periods=n_days)
    common = rng.normal(0, 0.010, n_days)
    fac = {"A": rng.normal(0, 0.016, n_days), "B": rng.normal(0, 0.016, n_days)}
    out = {}
    for t in XLK_CUSIPS:
        r = common + rng.normal(0, 0.002, n_days)
        if fractured:
            blk = np.zeros(n_days)
            blk[split_at:] = fac[_BLOCK[t]][split_at:]
            r = r + blk
        out[t] = (1 + pd.Series(r, index=dates)).cumprod() * 100.0
    return out


def _tiingo_body(series) -> bytes:
    return json.dumps([{"date": d.strftime("%Y-%m-%dT00:00:00.000Z"),
                        "close": float(p), "adjClose": float(p), "splitFactor": 1.0}
                       for d, p in series.items()]).encode()


def _short_body() -> bytes:
    # A 1-row Tiingo body for the sector-grid tickers (XLK/SPY): the sector panel builds but is unwarmed,
    # so xcorr runs and spawns nothing — it must not fault (a fault would push and mask the shadow test).
    return json.dumps([{"date": "2024-01-01T00:00:00.000Z", "close": 100.0, "adjClose": 100.0,
                        "splitFactor": 1.0}]).encode()


def _planted_z(prices, cfg) -> float:
    """The real departure z the planted constituent panel produces under dispersion's OWN windows —
    computed exactly as the sensor does, so the test can bracket z_in to a genuine fracture."""
    panel = pd.DataFrame({XLK_CUSIPS[t]: s for t, s in prices.items()})
    d = cfg["dispersion"]
    returns = dispersion.constituent_returns(panel)
    q = dispersion.dispersion_q_series(returns, int(d["window_days"]), int(d["min_constituents"]))
    z = dispersion.dispersion_z(q, int(d["baseline_days"])).dropna()
    return float(z.iloc[-1]) if len(z) else float("nan")


def _price_fetch(constituent_bodies, *, sector_bodies=None):
    """Route a Tiingo price URL to its body by the `/daily/{SYMBOL}/` path segment. Sector-grid tickers
    (XLK/SPY) get a short body (or a planted one); constituents get their fracture body; anything else
    404s (dropped, honest)."""
    sector = sector_bodies or {}

    def fetch(url, headers):
        up = url.upper()
        for t, body in sector.items():
            if f"/DAILY/{t}/" in up:
                return body
        for t, body in constituent_bodies.items():
            if f"/DAILY/{t}/" in up:
                return body
        return _short_body()  # any sector-grid ticker: a benign 1-row body -> xcorr runs clean, no spawn

    return fetch


def _deps(layout, registry, edgar_fetch, price_fetch, holdings_fetch, *, cfg, cfg_hash, notifier=None):
    return RunnerDeps(
        layout=layout, registry=registry, event_store=EventStore(layout, registry),
        edgar_client=_edgar(layout, edgar_fetch),
        price_ingest=PriceIngest(layout, fetch=price_fetch, clock=lambda: NOW[:10],
                                 sleep=lambda _s: None, api_token="tiingo-test-token"),
        holdings_ingest=HoldingsIngest(layout, fetch=holdings_fetch, clock=lambda: NOW[:10]),
        notifier=notifier if notifier is not None else NullNotifier(),
        cfg=cfg, cfg_hash=cfg_hash, now=NOW, run_id="run_test", monotonic=lambda: 0.0)


def _one_basket_cfg(prices):
    """The default (multi-sector) universe, but the mf map (below) resolves ONLY XLK to a series id, so
    XLK is the only dispersion basket AND xcorr has no resolvable pair to spawn (its grid is unwarmed
    1-row bodies anyway). z_in is bracketed to the planted fracture — asserted a REAL departure (clears
    the default z_in=2.5), then lowered so the driver enters."""
    base, base_hash = load_config(CONFIG)
    cfg = copy.deepcopy(base)
    z = _planted_z(prices, cfg)
    assert z >= 2.5, f"the planted constituent panel must genuinely depart (real z_in floor), got z={z}"
    cfg["dispersion"]["z_in"] = z * 0.9
    cfg["dispersion"]["z_out"] = 1.0
    return cfg, base_hash, z


# === fires live on REAL holdings membership: shadow spawn, excluded, no page, burn-in started ========

def test_dispersion_fires_live_on_real_holdings_membership_shadow_spawn(layout, registry):
    prices = _constituent_prices(fractured=True)
    cfg, cfg_hash, z = _one_basket_cfg(prices)
    bodies = {t: _tiingo_body(s) for t, s in prices.items()}
    notifier = NullNotifier()

    runlog = run_tick(_deps(layout, registry, _edgar_fetch([XLK_ROW]),
                            _price_fetch(bodies), lambda u, h: _XLK_HOLDINGS,
                            cfg=cfg, cfg_hash=cfg_hash, notifier=notifier))

    assert runlog.sensors["dispersion"] == "ran"
    # A real SHADOW spawn landed on the basket's series-id-keyed dispersion lead.
    spawns = registry.events_for_lead(XLK_LEAD, "lead.spawned")
    assert len(spawns) == 1
    spawn = json.loads(spawns[0]["payload"])
    assert spawn["spawner"] == "dispersion" and spawn["shadow"] is True
    assert spawn["series_id"] == XLK_SERIES and spawn.get("spawned_at")  # burn-in clock starts on wire

    # It folds active + SHADOW -> active_nonshadow EXCLUDES it (ceiling/corroboration wall, §4b) ...
    state = fold(registry.events_for_lead(XLK_LEAD))
    assert state["status"] == "active" and state["shadow"] is True
    assert active_nonshadow([state]) == []
    assert ceiling_status([state], ceiling=8)["count"] == 0  # consumes no §8a ceiling slot
    # ... and — §9e — a shadow-only change does NOT page (no non-shadow change, no fault).
    assert runlog.pushed is False and len(notifier.pushes) == 0
    assert XLK_LEAD in runlog.changed_leads  # but the change IS in the whole record (fossil stays honest)

    # The generous payload rode the tick (rev8 §4b CONTRACT: membership + sub-cluster + correlation).
    tick = json.loads(registry.events_for_lead(XLK_LEAD, "dispersion.tick")[0]["payload"])
    assert tick["q"] is not None and tick["z"] is not None and tick["z"] >= z * 0.9
    assert set(tick["split_membership"]) == set(XLK_CUSIPS.values())      # every CUSIP placed
    assert set(tick["split_membership"].values()) == {0, 1}              # a real two-block split
    assert len(tick["clusters"]) == 2
    assert tick["correlation"]["between_cluster"] is not None


# === push boundary (§9e): shadow does NOT page, a non-shadow xcorr spawn on the same tick DOES =======

def test_dispersion_shadow_never_pages_but_xcorr_does(layout, registry):
    # A 2-sector universe: xcorr spawns the XLK×XLU pair (LIVE, non-shadow) AND dispersion spawns shadow
    # baskets on the same tick. The push fires ONLY because of the non-shadow xcorr lead — the shadow
    # leads are excluded. (Do NOT flip the xcorr pushed=True assertion; that would be a surprised test
    # silently lowering a threshold — the exact failure §9e's rule names.)
    prices = _constituent_prices(fractured=True)
    base, base_hash = load_config(CONFIG)
    cfg = copy.deepcopy(base)
    cfg["universe"]["sectors"] = ["XLK", "XLU"]
    cfg["universe"]["market"] = "SPY"
    cfg["dispersion"]["z_in"] = _planted_z(prices, cfg) * 0.9
    cfg["dispersion"]["z_out"] = 1.0
    sector_bodies = _xcorr_planted_bodies()          # XLK/XLU share a residual factor -> the pair departs
    price_fetch = _price_fetch({t: _tiingo_body(s) for t, s in prices.items()},
                               sector_bodies=sector_bodies)
    notifier = NullNotifier()

    runlog = run_tick(_deps(layout, registry, _edgar_fetch([XLK_ROW, XLU_ROW]), price_fetch,
                            lambda u, h: _XLK_HOLDINGS, cfg=cfg, cfg_hash=base_hash, notifier=notifier))

    pair = xcorr_lead_id([XLK_SERIES, XLU_SERIES])
    xcorr_state = fold(registry.events_for_lead(pair))
    assert xcorr_state["status"] == "active" and xcorr_state["shadow"] is False   # LIVE spawn
    disp_state = fold(registry.events_for_lead(XLK_LEAD))
    assert disp_state["status"] == "active" and disp_state["shadow"] is True       # SHADOW spawn
    # The live (page-worthy) set is the xcorr lead ALONE; the shadow leads are filtered out.
    all_states = [fold(registry.events_for_lead(l)) for l in registry.all_leads() if l != SYSTEM_LEAD]
    assert [s["lead"] for s in active_nonshadow(all_states)] == [pair]
    assert runlog.pushed is True and len(notifier.pushes) == 1   # pages — because of xcorr, not shadow


# === null-silent: a calm basket spawns nothing ======================================================

def test_dispersion_calm_basket_spawns_nothing(layout, registry):
    prices = _constituent_prices(fractured=False)     # single common block -> Q ~ 0, no departure
    base, base_hash = load_config(CONFIG)
    cfg = copy.deepcopy(base)                          # default universe; mf resolves only XLK as a basket
    bodies = {t: _tiingo_body(s) for t, s in prices.items()}

    runlog = run_tick(_deps(layout, registry, _edgar_fetch([XLK_ROW]), _price_fetch(bodies),
                            lambda u, h: _XLK_HOLDINGS, cfg=cfg, cfg_hash=base_hash))

    assert runlog.sensors["dispersion"] == "ran"      # it RAN (drove the sensor) but ...
    assert [l for l in registry.all_leads() if str(l).startswith("disp-")] == []   # ... spawned nothing
    assert runlog.pushed is False


# === §9f: an active shadow lead TICKS, does not re-spawn (state from the record, not a recompute) ====

def test_dispersion_active_shadow_ticks_not_respawn(layout, registry):
    prices = _constituent_prices(fractured=True)
    cfg, cfg_hash, _ = _one_basket_cfg(prices)
    deps_args = (_edgar_fetch([XLK_ROW]), _price_fetch({t: _tiingo_body(s) for t, s in prices.items()}),
                 lambda u, h: _XLK_HOLDINGS)

    run_tick(_deps(layout, registry, *deps_args, cfg=cfg, cfg_hash=cfg_hash))
    run_tick(_deps(layout, registry, *deps_args, cfg=cfg, cfg_hash=cfg_hash))  # re-tick, same store

    # Exactly ONE spawn across both ticks (§9f: the record says the lead is active -> it ticks, never
    # re-spawns), and a fresh tick each run while active.
    assert len(registry.events_for_lead(XLK_LEAD, "lead.spawned")) == 1
    assert len(registry.events_for_lead(XLK_LEAD, "dispersion.tick")) == 2


# === §9f: a reverted lead can RE-ENTER on a fresh fracture (state comes from the record) =============

def test_dispersion_reverted_lead_can_re_enter(layout, registry):
    # Seed the record so the lead's last trigger event is `dispersion.reverted` (quiet). A fresh fracture
    # must then re-spawn — proving _dispersion_last_event_types reconstructs `quiet` from the record.
    store = EventStore(layout, registry)
    store.append({"ts": "2026-07-01T00:00:00Z", "lead": XLK_LEAD, "type": "lead.spawned",
                  "payload": {"spawner": "dispersion", "shadow": True, "series_id": XLK_SERIES,
                              "spawned_at": "2026-07-01T00:00:00Z"}, "schema": 1})
    store.append({"ts": "2026-07-02T00:00:00Z", "lead": XLK_LEAD, "type": "dispersion.reverted",
                  "payload": {"series_id": XLK_SERIES}, "schema": 1})

    prices = _constituent_prices(fractured=True)
    cfg, cfg_hash, _ = _one_basket_cfg(prices)
    run_tick(_deps(layout, registry, _edgar_fetch([XLK_ROW]),
                   _price_fetch({t: _tiingo_body(s) for t, s in prices.items()}),
                   lambda u, h: _XLK_HOLDINGS, cfg=cfg, cfg_hash=cfg_hash))

    # A SECOND spawn (the re-entry) — the reverted lead was quiet, so a fresh fracture spawns again.
    assert len(registry.events_for_lead(XLK_LEAD, "lead.spawned")) == 2
    assert fold(registry.events_for_lead(XLK_LEAD))["status"] == "active"


# === per-basket soft-fault boundary: one broken holdings feed faults THAT basket, not the run ========

def test_dispersion_per_basket_soft_fault_boundary(layout, registry):
    # Two baskets: XLU's holdings feed 404s (a broken feed for an expected basket -> a per-basket FAULT),
    # while XLK's holdings + fracturing prices still spawn. The run continues past the fault (§9g).
    prices = _constituent_prices(fractured=True)
    base, base_hash = load_config(CONFIG)
    cfg = copy.deepcopy(base)
    cfg["universe"]["sectors"] = ["XLK", "XLU"]
    cfg["universe"]["market"] = "SPY"
    cfg["dispersion"]["z_in"] = _planted_z(prices, cfg) * 0.9
    cfg["dispersion"]["z_out"] = 1.0

    def holdings_fetch(url, headers):
        if "xlu" in url.lower():
            raise HoldingsIngestError(f"GET {url} -> HTTP 404", status=404)  # the broken basket feed
        return _XLK_HOLDINGS

    runlog = run_tick(_deps(layout, registry, _edgar_fetch([XLK_ROW, XLU_ROW]),
                            _price_fetch({t: _tiingo_body(s) for t, s in prices.items()}),
                            holdings_fetch, cfg=cfg, cfg_hash=base_hash))

    # XLK spawned (the healthy basket) ...
    assert len(registry.events_for_lead(XLK_LEAD, "lead.spawned")) == 1
    # ... and XLU faulted THAT basket (a soft fault on _system, keyed to its dispersion lead) ...
    xlu_lead = dispersion_lead_id(XLU_SERIES)
    faults = [json.loads(f["payload"]) for f in registry.events_for_lead(SYSTEM_LEAD, "fault")]
    assert any(f["subsystem"] == "sensor.dispersion" and f.get("lead") == xlu_lead for f in faults)
    # ... but the run continued (the boundary held): the sensor 'ran' and identity retries ran.
    assert runlog.sensors["dispersion"] == "ran"
    assert runlog.sensors["identity_retries"] == "ran"


# === unit: the constituent panel is re-keyed ticker -> CUSIP (columns AND attrs['sources']) ==========

def test_constituent_panel_rekeys_ticker_to_identifier(layout):
    # The sensor CONTRACT: the panel keys on the stable CUSIP identifier, not the ticker. Prove the
    # re-key (before build_panel) makes BOTH the columns and attrs['sources'] identifier-keyed — a
    # post-hoc .rename() would leave attrs['sources'] ticker-keyed and a source lookup would miss.
    prices = _constituent_prices(fractured=True)
    bodies = {t: _tiingo_body(s) for t, s in prices.items()}
    ingest = PriceIngest(layout, fetch=_price_fetch(bodies), clock=lambda: NOW[:10],
                         sleep=lambda _s: None, api_token="tiingo-test-token")

    class _Deps:  # a thin stand-in — _build_constituent_panel only touches deps.price_ingest
        price_ingest = ingest

    pairs = list(XLK_CUSIPS.items())               # (ticker, cusip) pairs, membership order (§9e Option 2)
    panel = _build_constituent_panel(_Deps(), pairs, "tiingo", "2022-01-01", NOW[:10])

    assert list(panel.columns) == list(XLK_CUSIPS.values())          # columns are CUSIPs, not tickers
    assert set(panel.attrs["sources"]) == set(XLK_CUSIPS.values())   # the source map re-keyed too
    assert all(v == "tiingo" for v in panel.attrs["sources"].values())


# --- the xcorr planted panel (borrowed shape from test_runner_xcorr) --------------------------------

def _xcorr_planted_bodies(n=1030, shift_on=1000, seed=166, loading=3.5, base_sd=0.008) -> dict:
    """{ticker -> Tiingo body} for SPY + XLK/XLU sharing a residual factor from `shift_on` to the end, so
    the pair departs and the latest row clears xcorr z_in — the same construction the xcorr-live test uses."""
    rng = np.random.default_rng(seed)
    mkt = rng.normal(0, 0.01, n)
    common = rng.normal(0, base_sd, n)
    mask = np.zeros(n)
    mask[shift_on:] = 1.0
    series = {"SPY": mkt}
    for k, beta in (("XLK", 1.1), ("XLU", 0.9)):
        series[k] = beta * mkt + rng.normal(0, base_sd, n) + loading * common * mask
    dates = [d.strftime("%Y-%m-%dT00:00:00.000Z")
             for d in pd.date_range("2019-01-01", periods=n, freq="D")]
    out = {}
    for k, r in series.items():
        px = (1 + pd.Series(r)).cumprod() * 100.0
        out[k] = json.dumps([{"date": d, "close": float(p), "adjClose": float(p), "splitFactor": 1.0}
                             for d, p in zip(dates, px)]).encode()
    return out
