"""Rebalance sensor — holdings-diff accretion (spec §4d, milestone 4 · accretion core).

A rebalance is a professional curator quietly acting on a thesis (the middle stream of the consensus
curve, §1.5). This sensor watches the issuer's daily holdings for a change and *accretes* the fact
onto the live leads that already touch that fund — it is an **accretion sensor, not a spawner**: it
has no Schmitt trigger and no lead of its own, and the fold treats `rebalance` as a silent
corroboration (it lands on a lead's timeline and never changes status, shadow, or paging). It carries
no z; "material or not" is the whole decision.

DIFF: compare a watched fund's frozen holdings today vs its prior pull (both from the built
`ingest/holdings.py`, `load_frozen`). A material change (DEFAULT: any add/drop, or a weight delta ≥
`rebalance.weight_delta_threshold`) emits a `rebalance` event. The diff is over **identified
securities only** — rows carrying a CUSIP/ISIN — so a fund's daily cash/derivative wiggle (rows with
no identifier) can't spuriously fire; that is an honest read of "the holdings changed," not a guess.
(Add/drop of a tiny tail position is material per spec; if live tail-churn proves noisy, the fix is a
config weight-floor, a calibration knob, not a code change — never auto-tuned.)

ROUTING (CONTRACT §4d — forward-hash, no payload change): to find "every live lead whose baskets
include this fund," the lead-id already *is* the canonical encoding of a lead's series_ids, so we
recover the mapping by **forward-hashing**: enumerate the fund's memberships (its 10 sector pairs and
its own basket) and hash each with the existing `xcorr_lead_id` / `dispersion_lead_id` **verbatim**
(so canonicalization matches by construction), then intersect with the active-lead set. We do NOT add
series_ids to lead payloads — duplicating what the lead-id already encodes invites hash/payload drift,
a bug class avoided by never creating it. On a match the `rebalance` accretes onto each lead (making a
future cross-stream lag measurable there); with no match it is recorded on `_system` (kept, not
surfaced). Trivially cheap at the fixed 11-sector scale; a v2 auto-expanded universe would swap the
forward-hash for a maintained series_id→active-lead index built from the same functions — still not
payload duplication.

ENUMERATION (CONTRACT §4d): the active-lead set is read from the registry's **materialized fold** —
the snapshots the fold already writes — never by re-folding every lead at run time and never via a
separate lead-to-baskets cache (a redundant materialization that can drift from the fold; forward-
hashing inverts the lookup so no such cache is needed). Single source of truth: the fold, materialized
in the registry.

STATUS (these were three deferred defined-next-slices; one has since landed): `mandate.changed` — a
new prospectus filing whose mandate *text* differs — is now BUILT: its named unblock (an EDGAR
prospectus-text fetch + `ingest/prospectus/` blob-per-accession storage + a strategy-section text diff)
shipped as `ingest/prospectus.py` + `sensors/mandate.py`, wired live in the §9 runner's `_run_mandate`.
STILL DEFERRED here: this rebalance sensor's OWN runner wiring (the holdings-diff needs the holdings/
constituent vertical, a later slice), and the quarterly NPORT-P authoritative cross-check (gated on
`holdings.parse_nport_holdings`, the deliberately thin §3b stub). Both remaining slices are event-driven
off the runner's one daily filings-index check — never a calendar cron. See
`docs/decisions/2026-07-03-rebalance-accretion-and-routing.md` and spec rev9 §4d.
"""

from __future__ import annotations

import json
import math
from typing import Callable, Iterable

import pandas as pd

from prospector.sensors.dispersion import dispersion_lead_id
from prospector.sensors.xcorr import xcorr_lead_id
from prospector.store.envelope import SYSTEM_LEAD


def _round(w, nd: int = 8):
    """Round a weight for a stable SHA-256, mapping NaN/inf -> None. `canonical_json` uses
    allow_nan=False, so a bare NaN in the payload would be rejected at write time (mirrors
    dispersion._round)."""
    if w is None:
        return None
    wf = float(w)
    if math.isnan(wf) or math.isinf(wf):
        return None
    return round(wf, nd)


def _is_cash_or_derivative(row) -> bool:
    """A cash / money-market / derivative / currency line, NOT a real security position. SSGA stamps
    these with the `-` TICKER sentinel: a real file's money-market and currency lines DO carry a
    populated CUSIP-like `identifier` (924QSGII3, 999EURZ94), so keying the exclusion on an EMPTY
    identifier excludes nothing on live data — the ticker sentinel is the primary-source signal.
    `MONEY MARKET` in the name is defense-in-depth. This is the CASH/DERIVATIVE test ONLY — NOT the
    price-universe gate `holdings.priceable_members`, which ALSO drops FOREIGN equities whose genuine
    add/drop/reweight IS a rebalance signal; the diff keeps foreign constituents, drops only non-security
    lines."""
    _t = row.get("ticker", "")
    ticker = "" if pd.isna(_t) else str(_t).strip()   # S5: NaN -> "" ("unknown"), never the string "nan"
    if ticker == "-":                       # the SSGA cash/derivative sentinel (explicit dash only —
        return True                          # a MISSING/blank ticker column is "unknown", NOT cash:
    return "MONEY MARKET" in str(row.get("name", "")).upper()   # synthetic frames omit ticker entirely


def _identified(frame: pd.DataFrame) -> dict[str, dict]:
    """Map identifier -> {name, weight} over the frame's REAL SECURITY positions (a non-empty
    CUSIP/ISIN, excluding cash/derivative/currency lines — `_is_cash_or_derivative`). Their daily wiggle
    must never read as a rebalance. On a duplicate identifier the heavier row wins (defensive; SPDR files
    are one row per lot)."""
    out: dict[str, dict] = {}
    for _, row in frame.iterrows():
        _id = row.get("identifier", "")
        ident = "" if pd.isna(_id) else str(_id).strip()   # S5: NaN identifier -> "" -> excluded, never a
        if not ident or _is_cash_or_derivative(row):        # truthy "nan" key treated as a real security
            continue
        w = row.get("weight")
        prev = out.get(ident)
        if prev is None or (w is not None and prev["weight"] is not None and w > prev["weight"]):
            out[ident] = {"name": str(row.get("name", "")).strip(), "weight": w}
    return out


def diff_holdings(prior: pd.DataFrame, current: pd.DataFrame, threshold: float) -> dict:
    """Diff two holdings frames (columns include name/identifier/weight, e.g. from
    `holdings.load_frozen`) into `{adds, drops, weight_deltas, material}` over identified securities.

    - `adds`: identifiers in `current` but not `prior` (carrying current name/weight).
    - `drops`: identifiers in `prior` but not `current` (carrying prior name/weight).
    - `weight_deltas`: identifiers in both whose |current - prior| >= `threshold`.
    - `material`: any add, any drop, or any weight delta over threshold (spec §4d DEFAULT).

    Lists are sorted most-material first (weight/|delta| desc, then identifier) for a deterministic,
    reviewable payload."""
    p, c = _identified(prior), _identified(current)
    p_ids, c_ids = set(p), set(c)

    adds = [{"identifier": i, "name": c[i]["name"], "weight": _round(c[i]["weight"])}
            for i in (c_ids - p_ids)]
    drops = [{"identifier": i, "name": p[i]["name"], "weight": _round(p[i]["weight"])}
             for i in (p_ids - c_ids)]

    weight_deltas = []
    for i in (p_ids & c_ids):
        pw, cw = p[i]["weight"], c[i]["weight"]
        if pw is None or cw is None:
            continue
        delta = float(cw) - float(pw)
        if abs(delta) >= threshold:
            weight_deltas.append({"identifier": i, "name": c[i]["name"],
                                  "prior": _round(pw), "current": _round(cw), "delta": _round(delta)})

    adds.sort(key=lambda d: (-(d["weight"] or 0.0), d["identifier"]))
    drops.sort(key=lambda d: (-(d["weight"] or 0.0), d["identifier"]))
    weight_deltas.sort(key=lambda d: (-abs(d["delta"] or 0.0), d["identifier"]))

    return {"adds": adds, "drops": drops, "weight_deltas": weight_deltas,
            "material": bool(adds or drops or weight_deltas)}


def watching_leads(series_id: str, universe_series_ids: Iterable[str],
                   active_lead_ids: Iterable[str]) -> list[str]:
    """The live leads whose baskets include fund `series_id` — recovered by FORWARD-HASH (CONTRACT
    §4d, no payload change). Candidates are the fund's own dispersion lead plus every sector-pair
    xcorr lead it belongs to, hashed with the deterministic lead-id functions **verbatim**, then
    intersected with the active-lead set. Sorted for stability."""
    active = set(active_lead_ids)
    candidates = {dispersion_lead_id(series_id)}
    for g in universe_series_ids:
        if g != series_id:
            candidates.add(xcorr_lead_id([series_id, g]))  # xcorr_lead_id sorts internally
    return sorted(candidates & active)


def _active_lead_ids(registry, layout, *, include_shadow: bool) -> set[str]:
    """The active lead-id set, read from the registry's MATERIALIZED fold — the latest snapshot per
    lead (the snapshots the fold writes), never by re-folding and never via a separate cache (CONTRACT
    §4d). The snapshot file is the state dict (plus a `reason` key); a lead with no snapshot yet is
    skipped. In the live runner an active lead almost always has a snapshot (spawning is a state change,
    which snapshots reactively) — the ONE exception is a lead spawned THIS tick, whose snapshot is not
    written until run-order step 6 (AFTER the sensor phase). A basket that both spawns a lead and
    rebalances on the SAME tick therefore routes that first rebalance to `_system` and accretes onto the
    lead from the NEXT tick on (self-correcting, the record still holds the rebalance). That one-tick lag
    on a rare co-occurrence is the CONTRACT's deliberate trade — the alternative, re-folding here, is the
    exact drift-risk §4d forbids; see the runner's `_run_rebalance`. Excludes `_system` (infra, never a
    lead). `include_shadow` is the ONE dimension the two public filters differ on — one source, two
    filters (see the wrappers)."""
    out: set[str] = set()
    for lead in registry.all_leads():
        if lead == SYSTEM_LEAD:
            continue
        snap = registry.latest_snapshot(lead)
        if snap is None:
            continue
        state = json.loads((layout.root / snap["file_path"]).read_text(encoding="utf-8"))
        if state.get("status") != "active":
            continue
        if not include_shadow and state.get("shadow", False):
            continue
        out.add(lead)
    return out


def active_nonshadow_lead_ids(registry, layout) -> set[str]:
    """The active, NON-SHADOW lead-id set from the materialized fold (CONTRACT §4d). This is the filter
    for the PAGING paths (the mandate/SOI `on_live_lead` routing): a shadow lead in burn-in must be
    excluded from anything that can page. Its sibling `active_incl_shadow_lead_ids` is for the
    non-paging rebalance path — see there for why the two legitimately differ."""
    return _active_lead_ids(registry, layout, include_shadow=False)


def active_incl_shadow_lead_ids(registry, layout) -> set[str]:
    """The active lead-id set INCLUDING shadow (burn-in) leads, from the materialized fold (CONTRACT
    §4d). The sibling of `active_nonshadow_lead_ids`: the SAME single source (the materialized
    snapshots), differing on the ONE filter — this KEEPS shadow leads.

    Why that divergence is correct, NOT a smell to "fix" back to the non-shadow helper for consistency:
    rebalance ACCRETES and NEVER pages (the fold treats `rebalance` as a silent corroboration — no
    status/shadow/verdict change, so `_compute_push` can never fire on it). The whole reason shadow is
    walled off in the mandate/SOI paths is the PAGING boundary — a burn-in lead must not trip the alarm.
    Rebalance trips nothing; it appends corroborating context onto a lead's timeline. So — unlike those
    paging paths — rebalance SHOULD corroborate shadow dispersion leads while they burn in: right now
    EVERY dispersion lead is shadow, so the non-shadow filter would sever rebalance from the entire
    dispersion side exactly when a second, independent "this basket really is restructuring" signal is
    most wanted. Including shadow adds evidence to the burn-in record without ever paging — strictly more
    information when you go to promote a lead, and safe by construction. DO NOT collapse this back to the
    non-shadow helper: the two filters exist because their paths have different rules (one pages, one
    doesn't). Ratified: docs/decisions/2026-07-12-rebalance-runner-wiring.md."""
    return _active_lead_ids(registry, layout, include_shadow=True)


def scan(series_id: str, ticker: str, prior: pd.DataFrame, current: pd.DataFrame,
         universe_series_ids: Iterable[str], active_lead_ids: Iterable[str],
         cfg: dict, now: str, emit: Callable[[dict], object], as_of: str | None = None) -> dict:
    """One per-fund rebalance pass. Diff the fund's prior vs current frozen holdings; on a material
    change emit a `rebalance` event onto every live lead whose baskets include the fund (forward-hash
    routing) — or onto `_system` if none is live (recorded, not surfaced). `emit` is an
    EventStore.append-shaped callable (tests wire a recorder; the M5 runner the store). Returns a
    summary; emits nothing on an immaterial change."""
    threshold = float(cfg["rebalance"]["weight_delta_threshold"])
    diff = diff_holdings(prior, current, threshold)
    if not diff["material"]:
        return {"material": False, "targets": [], "emitted_to": [],
                "n_adds": 0, "n_drops": 0, "n_weight_deltas": 0}

    targets = watching_leads(series_id, universe_series_ids, active_lead_ids)
    leads = targets or [SYSTEM_LEAD]  # no live lead touches it -> recorded on _system, kept not surfaced
    payload = {"series_id": series_id, "ticker": ticker, "as_of": as_of,
               "adds": diff["adds"], "drops": diff["drops"], "weight_deltas": diff["weight_deltas"]}
    for lead in leads:
        emit({"ts": now, "lead": lead, "type": "rebalance", "payload": payload, "schema": 1})

    return {"material": True, "targets": targets, "emitted_to": leads,
            "n_adds": len(diff["adds"]), "n_drops": len(diff["drops"]),
            "n_weight_deltas": len(diff["weight_deltas"])}
