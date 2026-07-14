"""§4d rebalance — REAL-DATA cash-line and prior-parse regressions (cold-read QA, 2026-07-14).

These two tests target the gap between the synthetic rebalance fixtures and a real SPDR file:

  R1 (cash lines carry CUSIPs). The diff's cash/derivative exclusion (`_identified`, sensors/
     rebalance.py) skips only rows whose identifier is EMPTY. Every existing fixture builds cash-free
     equity baskets (identifiers 111/222/333), so the guard is never stressed. But a real SSGA daily
     file stamps its money-market and currency lines with populated CUSIP-like identifiers (e.g. the
     recorded TEKX file: 'SSI US GOV MONEY MARKET CLASS' -> 924QSGII3 @ 4.22%). Those lines therefore
     ENTER the diff, and a benign day-over-day cash-sweep balance move >= the weight threshold accretes a
     spurious `rebalance` ('this basket is restructuring') onto every live lead — including shadow
     dispersion leads in their 90-day burn-in, whose corroboration record is exactly what a human weighs
     when promoting a lead to paging. A cash-wiggle alarm that fires on benign input is the GPWS §2.4
     cry-wolf pattern one layer down.

     BEHAVIOUR asserted (implementation-agnostic): a diffed basket whose ONLY change between prior and
     today is a cash/money-market line's weight moving past the threshold (every equity constituent
     unchanged) accretes NO `rebalance`. Any correct fix satisfies this — a cash/derivative name/sentinel
     exclusion, a money-market filter, whatever — the test does not care HOW cash is excluded, only that a
     pure-cash-sweep does not read as a restructuring. (Note: routing the diff through the price-universe
     gate `priceable_members` would ALSO drop foreign equities, whose genuine add/drop IS signal — so
     that particular fix is wrong; this test stays silent on the mechanism to avoid locking in the wrong
     one.)

  R4 (prior-parse fault embeds a moving date, no stable §10 key). The current-feed fault
     (runner.py ~913) passes a stable `key=f'{ticker}:{status}'` so §10 suppression keys on the stable
     (ticker, status) and a persisting feed failure pages once then rides the heartbeat. Its sibling 11
     lines below — the prior-parse fault (runner.py ~925) — passes NO key=, so `_fault_signature` falls
     back to the full message, which embeds `prior_dates[-1]` (the newest frozen date strictly before
     today). That date advances as pulls accumulate, so a persistently-unparseable PRIOR produces a
     different message every tick -> a different signature -> pages DAILY. Exactly the volatile-message
     nuisance-alarm the §10 key= mechanism was built to prevent, re-appearing on the sibling path.

     BEHAVIOUR asserted: two ticks a day apart, each with a frozen-but-unparseable prior, must produce
     the SAME suppression signature (so §10 suppresses the second page). The test reads the fault the
     runner actually emitted and compares the stored suppression key (or, absent a key, the message) via
     the real `_fault_signature` — it does not assert a specific key string, only that the signature is
     STABLE across ticks.

Both are authored RED against the m6 branch and GREEN against the reference fix. House style: this file
builds its own deps (no shared helper import); the small harness mirrors test_runner_rebalance.py.
"""

import json
import pytest
from pathlib import Path
from types import SimpleNamespace

from prospector.config import load_config
from prospector.fold.fold import fold
from prospector.fold.snapshots import write_snapshot
from prospector.ingest.holdings import HoldingsIngest, HoldingsIngestError
from prospector.primitives.atomic import write_atomic
from prospector.runner.runlog import RunLog
from prospector.runner.runner import _run_rebalance, _fault_signature
from prospector.sensors.dispersion import dispersion_lead_id
from prospector.store.event_store import EventStore

CONFIG = Path("config") / "prospector.yaml"
NOW = "2026-07-14T22:30:00Z"
TODAY = "2026-07-14"
PRIOR_DATE = "2026-07-13"
T_SEED = "2026-07-10T00:00:00Z"
S_XLK = "S000006415"


def _spdr_csv(rows):
    """A real-shaped SPDR daily CSV: preamble, Name/Weight header, holdings, footer. SYNTHETIC bytes,
    real parser. `rows` are (name, ticker, identifier, weight_pct, sector)."""
    lines = ["The Select Sector SPDR Trust", "Fund ticker: XLK", "As of 2026-07-14", "",
             "Name,Ticker,Identifier,Weight,Sector"]
    for name, tk, ident, w, sec in rows:
        lines.append(f"{name},{tk},{ident},{w},{sec}")
    lines += ["", "Holdings are subject to change."]
    return ("\n".join(lines) + "\n").encode("utf-8")


# A basket with two equity constituents AND a money-market cash line carrying a REAL CUSIP-shaped
# identifier — the shape a live SSGA file has (cf. the recorded TEKX 'SSI US GOV MONEY MARKET CLASS'
# @ CUSIP 924QSGII3). Weights stay inside the parser's [0.5,1.5] sum band.
#   PRIOR: cash line at 5.00%.  TODAY: the SAME equities, cash swept to 6.00% (a +1% cash-sweep move,
#   well past the 0.5% threshold), NVDA trimmed to keep the sum ~constant. No equity add/drop.
_MM = ("SSI US GOV MONEY MARKET CLASS", "-", "924QSGII3")
PRIOR_CASH = _spdr_csv([("Apple", "AAA", "111", "55.00", "Tech"),
                        ("Nvidia", "NVDA", "222", "40.00", "Tech"),
                        (_MM[0], _MM[1], _MM[2], "5.00", "Cash")])
# Equities IDENTICAL; ONLY the money-market line moves (+1%, past the 0.5% threshold). The parser's
# weight-sum band is [0.5,1.5] on the fraction sum, so a 100%->101% total (cash inflow, equities held) is
# valid — this isolates a pure cash sweep, the exact benign behaviour that must NOT read as a rebalance.
TODAY_CASH_SWEEP = _spdr_csv([("Apple", "AAA", "111", "55.00", "Tech"),
                              ("Nvidia", "NVDA", "222", "40.00", "Tech"),
                              (_MM[0], _MM[1], _MM[2], "6.00", "Cash")])   # ONLY the cash line moves

GARBAGE_BODY = b"not,a,holdings,file\njust,some,garbage,rows\n"  # no Name/Weight header -> parser raises


def _mf(rows):
    return {"fields": ["cik", "seriesId", "classId", "symbol"], "data": rows}


MF_XLK = _mf([[1001, S_XLK, "C000019213", "XLK"]])


def _holdings(layout, *, clock=TODAY):
    def _raise(url, headers):
        raise HoldingsIngestError("no fetch fixture (frozen file expected)", status=404)
    return HoldingsIngest(layout, fetch=_raise, clock=lambda: clock)


def _freeze(hi, series_id, date, ticker, body):
    write_atomic(hi.frozen_path(series_id, date, ticker), body)


def _deps(layout, registry, hi, cfg):
    return SimpleNamespace(cfg=cfg, registry=registry, layout=layout, holdings_ingest=hi)


def _seed_lead(store, layout, registry, lead, *, spawner, shadow):
    store.append({"ts": T_SEED, "lead": lead, "type": "lead.spawned",
                  "payload": {"spawner": spawner, "display": lead, "shadow": shadow}, "schema": 1})
    write_snapshot(layout, registry, lead, fold(registry.events_for_lead(lead)),
                   reason="seed", ts=T_SEED)


def _all_rebalance_leads(registry):
    return {lead for lead in registry.all_leads()
            for _ in registry.events_for_lead(lead, "rebalance")}


# ============================ R1 ============================

@pytest.mark.xfail(strict=True, reason="R1 RED-first: reproduces the cash-line CUSIP spurious rebalance on the m6 branch. xfail(strict) handoff — GREEN in the gate now, flips to XPASS when m6_review_fixes.diff lands; implementer removes this marker then.")
def test_pure_cash_sweep_does_not_accrete_a_rebalance(layout, registry):
    """R1 — RED on m6: the money-market line carries a CUSIP so `_identified` keeps it, and its +1%
    day-over-day sweep fires a material weight_delta -> a spurious `rebalance` accretes onto the live
    (shadow dispersion) lead. GREEN after the fix: a cash/derivative line's wiggle is excluded, so a
    basket whose only change is a cash sweep accretes NOTHING.
    """
    cfg, _ = load_config(CONFIG)
    hi = _holdings(layout)
    _freeze(hi, S_XLK, PRIOR_DATE, "XLK", PRIOR_CASH)
    _freeze(hi, S_XLK, TODAY, "XLK", TODAY_CASH_SWEEP)

    store = EventStore(layout, registry, clock=lambda: NOW)
    disp = dispersion_lead_id(S_XLK)               # a shadow burn-in lead — the corroboration victim
    _seed_lead(store, layout, registry, disp, spawner="dispersion", shadow=True)

    faults, runlog = [], RunLog(run_id="t", ts=NOW, date=TODAY)
    _run_rebalance(_deps(layout, registry, hi, cfg), store, NOW, faults, runlog, MF_XLK)

    # BEHAVIOUR: a benign cash-sweep is not a restructuring. No rebalance on ANY lead.
    assert _all_rebalance_leads(registry) == set(), (
        "a pure money-market cash-sweep accreted a spurious rebalance — the cash line "
        "(CUSIP 924QSGII3) entered the diff because the exclusion keys on an EMPTY identifier, "
        "but real SSGA cash lines carry CUSIPs")
    assert faults == []  # a benign cash wiggle is not a fault either


# ============================ R4 ============================

@pytest.mark.xfail(strict=True, reason="R4 RED-first: reproduces the prior-parse volatile-message daily re-page on the m6 branch. xfail(strict) handoff — GREEN in the gate now, flips to XPASS when m6_review_fixes.diff lands; implementer removes this marker then.")
def test_unparseable_prior_fault_signature_is_stable_across_ticks(layout, registry):
    """R4 — RED on m6: the prior-parse fault (runner.py ~925) passes no key=, so its signature is the
    message, which embeds the moving `prior_dates[-1]`. Two ticks a day apart -> two signatures -> it
    pages daily. GREEN after the fix: a stable key= makes the signature identical across ticks, so §10
    suppresses the recurrence. Asserts the signature is STABLE, not any specific key string.
    """
    cfg, _ = load_config(CONFIG)

    def one_tick(now, today, prior_date, extra_prior=None):
        # A fresh store per tick (independent runs); each has a frozen-but-UNPARSEABLE prior and a good
        # current, so the prior-parse fault path (not the current-feed path) fires.
        r = registry if now == NOW else None
        # Build an isolated store/registry for the SECOND tick so frozen_dates advances realistically.
        from prospector.store.registry import Registry
        from prospector.store.layout import StoreLayout
        root = layout.root if now == NOW else (layout.root.parent / f"store_{today}")
        lay = layout if now == NOW else StoreLayout(root)
        reg = registry if now == NOW else Registry(lay.registry_path())
        hi = _holdings(lay, clock=today)
        # current parses; prior is garbage. Add an OLDER good prior on tick 2 so prior_dates[-1] MOVES.
        _freeze(hi, S_XLK, today, "XLK", PRIOR_CASH)
        _freeze(hi, S_XLK, prior_date, "XLK", GARBAGE_BODY)     # the unparseable prior (newest < today)
        if extra_prior:
            _freeze(hi, S_XLK, extra_prior, "XLK", GARBAGE_BODY)  # an even-older prior (tick 2 only)
        store = EventStore(lay, reg, clock=lambda: now)
        faults, runlog = [], RunLog(run_id="t", ts=now, date=today)
        _run_rebalance(_deps(lay, reg, hi, cfg), store, now, faults, runlog, MF_XLK)
        prior_faults = [f for f in faults if f["subsystem"] == "sensor.rebalance" and "prior" in f["message"]]
        assert len(prior_faults) == 1, f"expected one prior-parse fault, got {prior_faults}"
        return prior_faults

    # Tick 1: prior_date = 2026-07-13. Tick 2 (a day later): prior_date = 2026-07-14, and 07-13 also
    # frozen-garbage -> prior_dates[-1] advances 07-13 -> 07-14, moving the message.
    t1 = one_tick(NOW, TODAY, PRIOR_DATE)
    t2 = one_tick("2026-07-15T22:30:00Z", "2026-07-15", "2026-07-14", extra_prior="2026-07-13")

    sig1 = _fault_signature(t1)
    sig2 = _fault_signature(t2)
    assert sig1 == sig2, (
        "the prior-parse fault signature changed across ticks -> §10 re-pages every tick "
        "(the message embeds the moving prior date and no stable key= is passed)")
