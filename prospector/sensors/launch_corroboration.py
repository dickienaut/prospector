"""Launch corroboration hook — the live cross-stream lag (spec §4c, milestone 4 capstone).

When a launch's holdings-derived sectors overlap a live lead's baskets, the `launch` accretes onto
that lead, and the **cross-stream lag** (T(structural departure) → T(launch)) becomes measurable
there — the first moment "detect emerging shifts early" becomes a *number*.

THE HONEST BOUNDARY (CONTRACT §4c). The backtest's +593-day lag came from a CURATED launch table
(concentration hand-filled) matched with `keyword_match` on industry strings — a green that never
occurs live. That path stays in the backtest and never crosses here. The live hook derives
concentration from the launch's **first holdings** (look-through-is-truth; HECO the proof a stated
identity can lie) and does a **direct sector-set overlap**. Both lag endpoints must be real events
through real code — T1 a real structural spawn, T2 a real launch whose concentration was *derived*,
not supplied.

WHAT THE CAPSTONE TELLS US — the binding constraint is HOLDINGS COVERAGE, not the hook. `ingest/
holdings.py` parses the SPDR family only (the SSGA daily xlsx), so for a launch outside that family the
lag is *structurally unmeasurable*, not merely absent — `holdings_unavailable → dormant`, the honest
MAJORITY case today
(the launch-side twin of `fault`-on-unreliable-extraction; the dormant pile is the map of what the
tool can't yet see). The measured lag is therefore an EXISTENCE PROOF, not yet a rate. Widening
intake (per-issuer parsers / NPORT-P) is the named next slice — not here.

TIMING (deferred, not fired at launch time). A fund's first holdings post DAYS after it lists, but
`detected_at` is nailed at detection. Wiring corroboration into launch resolution would find the
empty sector set and silently never fire. So `corroborate` is a DEFERRED, re-attempted pass: the
launch is recorded dormant at detection (built), and when its first holdings land this runs and
reaches back, preserving the original `detected_at` as T2. It is *called with* holdings; it never
assumes they exist. The M5 runner owns the retry scheduling (built): its §9d pass re-attempts each
`sectors_unresolved` launch within the retry horizon — wired live for the SOI-source resolver
(`sensors/soi.py`); the holdings-source `corroborate` retry awaits the holdings/constituent vertical.

A corroborating launch ACCRETES onto the existing lead — it NEVER spawns one (rev7: launches aren't
lead-spawners; no ceiling slot). The lag is SIGNED: negative (packaging beat structure) is honest
data, never clamped or discarded.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Callable, Iterable, Mapping

import pandas as pd

from prospector.identity.resolution import launch_lag
from prospector.sensors.dispersion import dispersion_lead_id
from prospector.sensors.xcorr import xcorr_lead_id
from prospector.store.envelope import SYSTEM_LEAD, parse_ts


# --- Piece 1: holdings-derived concentration (the fragile part, isolated) -----------------------

# SSGA's "not disclosed" markers in the daily file's Sector column. VERIFIED against the real TEKX
# file (2026-07-03): an ACTIVE/thematic fund discloses holdings but leaves Sector "-" on every row, so
# these are unresolved, NOT a sector — treating "-" as a sector would forge a phantom {"-"} bucket.
_UNRESOLVED_SECTOR = frozenset({"", "-"})


def sector_concentration(holdings: pd.DataFrame | None, min_weight: float) -> frozenset[str]:
    """A fund's dominant sectors, DERIVED from its holdings' `sector` field (ground truth, not prose).
    Aggregate by weight; a sector is 'present' iff it holds ≥ `min_weight` of total fund weight. An
    unresolved sector ("" or SSGA's "-") is ignored — so a fund whose file carries NO sectors (every
    active thematic ETF, per primary-source review) yields the **empty set**, which the caller reads
    as `sectors_unresolved` (dormant), never a phantom match. This decides *which* sectors the fund is
    in, never whether that means anything (the overlap + the human do that)."""
    if holdings is None or holdings.empty:
        return frozenset()
    by_sector: dict[str, float] = {}
    for _, row in holdings.iterrows():
        sec = str(row.get("sector", "")).strip()
        w = row.get("weight")
        if sec in _UNRESOLVED_SECTOR or w is None:
            continue
        by_sector[sec] = by_sector.get(sec, 0.0) + float(w)
    return frozenset(sec for sec, w in by_sector.items() if w >= min_weight)


def series_id_sectors(sector_map: Mapping[str, str],
                      ticker_to_series_id: Mapping[str, str]) -> dict[str, str]:
    """`series_id → GICS sector name`, from the config `sector_map` (ticker → sector) bridged through
    the universe's ticker↔series_id. Leads key on series_id; the launch's holdings carry GICS names;
    this is the bridge. The map is stable data (a fund's legal sector designation)."""
    out: dict[str, str] = {}
    for ticker, sector in sector_map.items():
        sid = ticker_to_series_id.get(ticker)
        if sid:
            out[sid] = sector
    return out


# --- Piece 2: overlap + routing + signed lag ----------------------------------------------------

def lead_sectors(universe_series_ids: Iterable[str], series_id_to_sector: Mapping[str, str],
                 active_lead_ids: Iterable[str]) -> dict[str, frozenset[str]]:
    """`active lead_id → its sector set`, recovered by FORWARD-HASH (the §4d routing CONTRACT — the
    lead-id already encodes its series_ids, so hash the universe with the existing lead-id functions
    verbatim and intersect with the active set; no payload duplication). A dispersion lead → the one
    basket's sector; an xcorr lead → the pair's two sectors."""
    active = set(active_lead_ids)
    sids = list(universe_series_ids)
    out: dict[str, frozenset[str]] = {}
    for sid in sids:
        lid = dispersion_lead_id(sid)
        if lid in active and sid in series_id_to_sector:
            out[lid] = frozenset({series_id_to_sector[sid]})
    for i in range(len(sids)):
        for j in range(i + 1, len(sids)):
            a, b = sids[i], sids[j]
            lid = xcorr_lead_id([a, b])
            if lid in active and a in series_id_to_sector and b in series_id_to_sector:
                out[lid] = frozenset({series_id_to_sector[a], series_id_to_sector[b]})
    return out


def overlaps(launch_sectors: frozenset[str], lead_sector_set: frozenset[str]) -> bool:
    """The BOTH-SIDES rule (§10 test 5b): the launch's sectors must intersect EVERY side of the lead
    — both sectors of an xcorr pair, or the one sector of a dispersion basket. Plain set logic, the
    live replacement for the backtest keyword matcher (which stays with the curated YAML)."""
    if not lead_sector_set:
        return False
    return lead_sector_set <= launch_sectors


def corroborate(launch: Mapping, holdings: pd.DataFrame | None,
                active_lead_sectors: Mapping[str, frozenset[str]],
                cfg: dict, now: str, emit: Callable[[dict], object]) -> dict:
    """The DEFERRED corroboration pass — call it when the launch's first holdings land (NOT at
    resolution; see the module docstring on timing). `launch` is the launch record ({series_id,
    ticker, name?, detected_at, unverified_ref?}); `holdings` is its first-holdings frame or None
    (None = fetch/parse failed — a non-SPDR issuer today); `active_lead_sectors` is the
    `lead_sectors(...)` map. Outcomes:
      - holdings None -> `holdings_unavailable`, recorded dormant on `_system` (the honest coverage
        gap, the majority case — never a guess);
      - overlap -> the `launch` ACCRETES onto every matched lead (detected_at preserved as T2, the
        derived sectors attached), NEVER spawning a lead (rev7);
      - no overlap -> recorded dormant on `_system` with its derived sectors (first-class, surveyable).
    Returns a summary."""
    base = {"series_id": launch["series_id"], "ticker": launch.get("ticker"),
            "detected_at": launch["detected_at"], "unverified_ref": launch.get("unverified_ref")}

    if holdings is None:
        emit({"ts": now, "lead": SYSTEM_LEAD, "type": "launch",
              "payload": {**base, "concentration_sectors": None,
                          "corroboration": "holdings_unavailable"}, "schema": 1})
        return {"action": "holdings_unavailable", "sectors": None, "matched": []}

    sectors = sector_concentration(holdings, float(cfg["corroboration"]["sector_min_weight"]))

    if not sectors:
        # Holdings parsed, but the file carries no resolvable GICS sectors (SSGA leaves Sector "-" for
        # active funds — the primary-source reality). We cannot compute an overlap, so we FLAG rather
        # than guess: `sectors_unresolved`, dormant on _system (the launch-side twin of
        # holdings_unavailable, one level in). This is the DAILY-XLSX blind spot; the SOI sensor
        # (ingest/soi.py + sensors/soi.py) is its RESOLVER — when the first industry-grouped Schedule
        # of Investments lands it derives the sectors from the filing and re-runs this routing via
        # `route_corroboration` below, reaching back with detected_at preserved as T2.
        emit({"ts": now, "lead": SYSTEM_LEAD, "type": "launch",
              "payload": {**base, "concentration_sectors": [], "corroboration": "sectors_unresolved"},
              "schema": 1})
        return {"action": "sectors_unresolved", "sectors": [], "matched": []}

    return route_corroboration(base, sectors, active_lead_sectors, now, emit)


def route_corroboration(base: Mapping, sectors: frozenset[str],
                        active_lead_sectors: Mapping[str, frozenset[str]],
                        now: str, emit: Callable[[dict], object]) -> dict:
    """The shared routing tail: given a launch's DERIVED dominant sectors (already thresholded), overlap
    them against every active lead and either ACCRETE the launch onto each match or record it dormant.

    Extracted from `corroborate` so the two concentration *sources* — the holdings `sector` column and
    the SOI industry-header derivation (sensors/soi.py) — feed ONE overlap/emit path. The emitted event
    is identical either way (`type: "launch"`, `corroboration: "match"`, `detected_at` in `base`
    preserved as T2), so `cross_stream_lag` consumes it unchanged regardless of which source resolved
    the sectors. `base` is the launch identity dict ({series_id, ticker, detected_at, unverified_ref});
    `sectors` is NON-EMPTY (the empty/unavailable dispositions belong to the source, which knows whether
    the emptiness is "no file" vs "file has no sectors")."""
    matched = sorted(lid for lid, ls in active_lead_sectors.items() if overlaps(sectors, ls))

    if not matched:
        emit({"ts": now, "lead": SYSTEM_LEAD, "type": "launch",
              "payload": {**base, "concentration_sectors": sorted(sectors),
                          "corroboration": "dormant_no_match"}, "schema": 1})
        return {"action": "dormant_no_match", "sectors": sorted(sectors), "matched": []}

    for lid in matched:
        emit({"ts": now, "lead": lid, "type": "launch",
              "payload": {**base, "concentration_sectors": sorted(sectors),
                          "corroboration": "match"}, "schema": 1})
    return {"action": "corroborated", "sectors": sorted(sectors), "matched": matched}


def pending_soi_resolution(launch_events: Iterable[Mapping], now: str,
                           retry_horizon_days: float) -> list[dict]:
    """The §9d work-list: the launches still awaiting SOI sector resolution, FOLDED from the launch
    events — never a side 'pending' table (§9f: between-tick state is the fossil record, the same
    single-source enumeration as active leads). Each element is a `launch` event as a Mapping with
    `ts`, `event_id`, and `payload`.

    A launch's disposition is `payload['corroboration']`, and the append-only record supersedes: group
    every `launch` event by `series_id`, keep the LATEST by `(ts, event_id)`, and a launch is still
    pending iff that latest disposition is `sectors_unresolved`. So once §9d resolves one — a `match`
    on a lead, or a `dormant_no_match` / `no_dominant_sector` on `_system` (all later `ts`) — it drops
    off the work-list and is never re-fetched. A launch whose detection has aged past
    `retry_horizon_days` also drops off (dormant-terminal, surfaced by the coverage report, not
    re-fetched forever). Returns the pending launch payloads (the record `sensors/soi.scan` consumes)."""
    latest: dict[str, tuple[tuple, dict]] = {}
    for e in launch_events:
        payload = e["payload"]
        sid = payload.get("series_id")
        if sid is None:
            continue
        key = (e["ts"], e.get("event_id", ""))
        if sid not in latest or key > latest[sid][0]:
            latest[sid] = (key, payload)
    horizon = timedelta(days=retry_horizon_days)
    now_dt = parse_ts(now)
    pending: list[dict] = []
    for _key, payload in latest.values():
        if payload.get("corroboration") != "sectors_unresolved":
            continue
        detected_at = payload.get("detected_at")
        if detected_at and now_dt - parse_ts(detected_at) > horizon:
            continue  # aged past the horizon -> dormant-terminal (surfaced, never re-fetched)
        pending.append(dict(payload))
    return pending


def cross_stream_lag(lead_events: Iterable[Mapping]) -> timedelta | None:
    """The SIGNED cross-stream lag on a lead: T2 − T1, where T1 is the lead's earliest structural
    spawn (`lead.spawned` — the xcorr/dispersion birth) and T2 is the earliest corroborating launch's
    `detected_at`. Positive = structure preceded packaging (the lead was early); NEGATIVE = packaging
    beat structure — recorded honestly, NEVER clamped or discarded (the un-recalibrated-gate −58
    category is real data). None when the lead has no structural spawn or no corroborating launch
    (undefined, not fabricated). Reuses `launch_lag`, which reads ONLY `detected_at` (lag integrity)."""
    events = list(lead_events)
    spawns = sorted(e["ts"] for e in events if e.get("type") == "lead.spawned")
    launches = [e["payload"] for e in events
                if e.get("type") == "launch" and isinstance(e.get("payload"), Mapping)
                and e["payload"].get("detected_at")]
    if not spawns or not launches:
        return None
    earliest_launch = min(launches, key=lambda p: parse_ts(p["detected_at"]))
    return launch_lag(spawns[0], earliest_launch)  # T2 − T1, signed
