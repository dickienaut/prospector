"""Pure fold engine — a lead IS the fold over its event stream (spec §5, CONTRACT).

No mutable rows: lead state is a deterministic function of the event set. Total order is
(ts, event_id) — the registry's ORDER BY — so any arrival order and any re-delivery fold to
the identical state (spec test 3, property-tested). No I/O, no clock, no config: rows in,
state dict out.

Type handling is the day-one open-vocabulary contract (spec §5): recognized v1 types fold
into named state fields; any type ending '.reverted' folds as a revert (a future sensor's
exit event works without a code change); everything else lands in `unknown_types` — counted,
raw-referenced, never a crash. That gap is exactly where v2's writers plug in.

Market stress (spec §4a, CONTRACT): a departure annotated `market_stress` is recorded (it is
in the fossil record and the counts) but is not a state change — no activation, no latest_z.
The annotation protects the oracle and the lead registry while keeping the record whole.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping

# The spec §5 table. Recognition is a fold concern only — the store never checks types
# against a list (envelope.py keeps `type` an open vocabulary).
V1_TYPES = frozenset({
    "lead.spawned",
    "xcorr.departure", "xcorr.tick", "xcorr.reverted",
    "dispersion.tick", "dispersion.reverted",
    "launch.unverified", "launch", "rebalance", "mandate.changed",
    "capture.stored", "verdict",
    "registry.updated", "identity.resolved", "resolution.failed",
    "baseline.frozen", "config.changed", "fault",
})

_CORROBORATION_TYPES = frozenset({"launch", "rebalance", "mandate.changed"})

# The push/ceiling trio — the only fields that constitute a state change (spec §5, §8a).
_CHANGE_FIELDS = ("status", "shadow", "verdict")
_INITIAL_TRIO = {"status": None, "shadow": False, "verdict": "none"}


def _get(row, key, default=None):
    """Mapping access that tolerates plain dicts and sqlite3.Row (Row has no .get, and a
    missing key raises IndexError rather than KeyError)."""
    try:
        return row[key]
    except (KeyError, IndexError):
        return default


def _payload_dict(raw, state: dict, ts, event_id) -> Mapping:
    """Payload arrives as a dict (fresh writes) or canonical-JSON text (registry rows).
    Anything else is malformed; the fold is total, so it folds as {} plus an anomaly rather
    than crashing — the raw record still holds the bytes."""
    if isinstance(raw, Mapping):
        return raw
    if isinstance(raw, (str, bytes, bytearray)):
        try:
            parsed = json.loads(raw)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            return parsed
    state["anomalies"].append(
        {"kind": "payload_unparseable", "ts": ts, "event_id": event_id})
    return {}


def _sort_key(row):
    # str() coercion so a malformed row cannot make the sort (and thus the fold) raise.
    return (str(_get(row, "ts", "")), str(_get(row, "event_id", "")))


def fold(rows: Iterable[Mapping]) -> dict:
    """Fold an event stream into lead state (spec §5).

    Rows carry event_id/ts/type/payload (dict or canonical-JSON text), optionally
    lead/schema; sqlite3.Row from Registry.events_for_lead works directly. Duplicates by
    event_id are dropped — first occurrence in (ts, event_id) order wins — so re-ingestion
    is invisible to the fold.
    """
    state = {
        "lead": None,
        "display": None,
        "spawner": None,
        "status": None,
        "shadow": False,
        "verdict": "none",
        "verdict_history": [],
        "spawned_at": None,
        "last_event": None,
        "event_count": 0,
        "latest_z": None,
        "stress_departures": 0,
        "capture_inventory": [],
        "corroborations": [],
        "unknown_types": {"count": 0, "items": []},
        "faults": [],
        "anomalies": [],
    }
    verdicts: list[dict] = []
    seen: set = set()
    for row in sorted(rows, key=_sort_key):
        event_id = _get(row, "event_id")
        if event_id is not None:
            if event_id in seen:
                continue
            seen.add(event_id)
        ts = _get(row, "ts", "")
        type_ = _get(row, "type", "")
        if not isinstance(type_, str):
            type_ = str(type_)
        payload = _payload_dict(_get(row, "payload", {}), state, ts, event_id)
        if state["lead"] is None:
            state["lead"] = _get(row, "lead")
        state["event_count"] += 1
        state["last_event"] = {"ts": ts, "type": type_, "event_id": event_id}
        _apply(state, verdicts, ts, type_, event_id, payload)
    _resolve_verdict_chain(state, verdicts)
    return state


def _apply(state: dict, verdicts: list, ts, type_: str, event_id, payload: Mapping) -> None:
    if type_ == "lead.spawned":
        state["status"] = "active"
        state["spawner"] = payload.get("spawner")
        state["display"] = payload.get("display")
        state["shadow"] = bool(payload.get("shadow", False))
        state["spawned_at"] = payload.get("spawned_at", ts)
    elif type_ == "xcorr.departure":
        if payload.get("market_stress"):
            # §4a CONTRACT: recorded, not a state change — no activation, no latest_z.
            state["stress_departures"] += 1
        else:
            state["status"] = "active"
            if "z" in payload:
                state["latest_z"] = payload["z"]
    elif type_.endswith(".reverted"):
        state["status"] = "reverted"  # reverted, never deleted
    elif type_ in ("xcorr.tick", "dispersion.tick"):
        if "z" in payload and not payload.get("market_stress"):
            state["latest_z"] = payload["z"]
    elif type_ == "verdict":
        entry = {"ts": ts, "event_id": event_id,
                 "verdict": payload.get("verdict"),
                 "note": payload.get("note"),
                 "superseded_by": payload.get("superseded_by")}
        verdicts.append(entry)
        state["verdict_history"].append(dict(entry))
    elif type_ in _CORROBORATION_TYPES:
        state["corroborations"].append(
            {"ts": ts, "type": type_, "event_id": event_id})
    elif type_ == "capture.stored":
        state["capture_inventory"].append(
            {"ts": ts, "event_id": event_id,
             "query_set": payload.get("query_set"),
             "s3_prefix": payload.get("s3_prefix"),
             "result_counts": payload.get("result_counts")})
    elif type_ == "fault":
        state["faults"].append(
            {"ts": ts, "event_id": event_id,
             "subsystem": payload.get("subsystem"),
             "message": payload.get("message")})
    elif type_ in V1_TYPES:
        pass  # recognized, recorded (event_count/last_event), no further state effect
    else:
        state["unknown_types"]["count"] += 1
        state["unknown_types"]["items"].append(
            {"ts": ts, "type": type_, "event_id": event_id})


def verdict_head_id(state: dict) -> str | None:
    """The current chain head's event_id — what a NEW verdict's `superseded_by` must point at
    (spec §5/§8c: a changed mind supersedes the head, never edits); None when the lead has no
    verdicts. Re-runs the fold's own head resolution over verdict_history, so the CLI's
    auto-fill and the fold can never disagree about which verdict is being superseded."""
    scratch = {"verdict": "none", "anomalies": []}
    head = _resolve_verdict_chain(scratch, list(state.get("verdict_history") or []))
    return None if head is None else head["event_id"]


def _resolve_verdict_chain(state: dict, verdicts: list) -> dict | None:
    """Current verdict = the chain head: the verdict whose event_id no other verdict's
    `superseded_by` references (spec §5, lifted from apex_history). A broken chain —
    dangling pointer, fork, cycle — resolves deterministically to the latest head by
    (ts, event_id) and records an anomaly; the fold never crashes on bad links.
    Returns the head entry (None when there are no verdicts)."""
    if not verdicts:
        return None
    ids = {v["event_id"] for v in verdicts}
    referenced = set()
    for v in verdicts:
        target = v["superseded_by"]
        if target is None:
            continue
        try:
            known = target in ids and target != v["event_id"]
        except TypeError:  # unhashable pointer is malformed by definition
            known = False
        if known:
            referenced.add(target)
        else:
            state["anomalies"].append(
                {"kind": "verdict_dangling", "ts": v["ts"],
                 "event_id": v["event_id"], "superseded_by": target})
    heads = [v for v in verdicts if v["event_id"] not in referenced]
    if not heads:  # every verdict referenced: a cycle
        head = max(verdicts, key=_verdict_key)
        state["anomalies"].append(
            {"kind": "verdict_cycle", "resolved_to": head["event_id"]})
    elif len(heads) == 1:
        head = heads[0]
    else:
        head = max(heads, key=_verdict_key)
        state["anomalies"].append(
            {"kind": "verdict_fork",
             "heads": sorted((h["event_id"] for h in heads), key=str),
             "resolved_to": head["event_id"]})
    state["verdict"] = "none" if head["verdict"] is None else head["verdict"]
    return head


def _verdict_key(v: dict):
    return (str(v["ts"]), str(v["event_id"]))


def state_changed(prev: dict | None, new: dict) -> list[str]:
    """Which of {status, shadow, verdict} differ — the trio that drives push emails and
    reactive snapshots (spec §5, §8a). prev=None compares against the initial fold state,
    so a first fold reports whatever is non-initial."""
    base = _INITIAL_TRIO if prev is None else prev
    return [f for f in _CHANGE_FIELDS if base[f] != new[f]]


def active_nonshadow(states: Iterable[dict]) -> list[dict]:
    """The single oracle-facing filter: M5's active-lead ceiling, paging, and the email
    digest all call this, so shadow leads are excluded from all three by construction
    (spec §4b CONTRACT)."""
    return [s for s in states if s["status"] == "active" and not s["shadow"]]
