"""Dashboard view-models — pure folds of the fossil record (spec §11).

Every function here shapes stored events/snapshots into what a panel renders. NO streamlit import, NO
writes, NO recompute or fetch: the dashboard reads the record the runner already wrote (CONTRACT §11 —
"read-only means read-only"). Keeping the shaping here (not in the Streamlit shell) makes it testable
without a browser and keeps the render layer thin.

The panels (spec §11 / rev13 §8b): ranked active leads · per-lead timeline (thaw-backward) · the
dispersion **shadow panel** (burn-in clock, honestly-empty until §4b is wired) · the manual-resolution
queue · registry health · the unknown-type panel (empty in v1, built anyway for v2 writers) · the fault
log · the **macro catalog** (`off-thesis-real`, read-only context — never a trade/tilt trigger, never a
regime-forming alert stream) · the **launch panel** (recorded launches, survey-only, never pushed) · the
**coverage / dormant-pile** map (the §10 blindness map, ranked) · the §8a ceiling tripwire · run
history / the weekly dead-man.
"""

from __future__ import annotations

import json
from collections import Counter
from typing import Iterable, Mapping

from prospector.fold.fold import active_nonshadow, fold
from prospector.store.envelope import SYSTEM_LEAD, parse_ts

# The dormant/coverage dispositions the corroboration pass records on `_system` (launch_corroboration.py).
# `match` is NOT here — it accretes onto a live lead, so it shows in that lead's timeline, not the pile.
DORMANT_DISPOSITIONS = ("holdings_unavailable", "sectors_unresolved", "no_dominant_sector",
                        "dormant_no_match")


def _payload(row: Mapping) -> dict:
    """Parse an event row's payload (canonical-JSON text from the registry, or an already-dict)."""
    raw = row["payload"]
    if isinstance(raw, Mapping):
        return dict(raw)
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _days_between(earlier: str | None, later: str | None) -> int | None:
    """Whole days from `earlier` to `later` (both ISO-8601 UTC), or None if either is missing/unparseable.
    Never raises — a malformed timestamp in the record must not blank the whole panel."""
    if not earlier or not later:
        return None
    try:
        return (parse_ts(later) - parse_ts(earlier)).days
    except Exception:
        return None


# --- the lead-state panels (folds of the event record) ------------------------------------------


def fold_all_leads(registry) -> list[dict]:
    """Fold every real lead (all leads but `_system`, which is infra — faults/queue/runs, never a lead).
    The single read the lead-state panels share, so the record is folded once per view."""
    return [fold(registry.events_for_lead(lead))
            for lead in registry.all_leads() if lead != SYSTEM_LEAD]


def rank_active_leads(states: Iterable[dict]) -> list[dict]:
    """The ranked active-leads panel: the LIVE leads (active, non-shadow — `active_nonshadow`, the same
    §8a/paging/digest filter), ranked recency × magnitude (newest spawn first, then larger |z|). This is
    where the wired xcorr (§4a) firings surface."""
    # N10: `off-thesis-real` is INERT — a real-but-macro/sector regime, deliberately set aside, whose home
    # is the read-only `macro_catalog` context panel (CLAUDE.md: never a trade/tilt trigger). It must NEVER
    # surface in the actionable "real evidence" list, or a viewer reads a macro lead as a live signal.
    # `active_nonshadow` keys on status+shadow only (verdict is display-only in the fold), so the verdict
    # is filtered here at the panel boundary — the lead stays visible in `macro_catalog`, just not here.
    live = [s for s in active_nonshadow(list(states)) if s.get("verdict") != "off-thesis-real"]
    return sorted(live, key=lambda s: ((s.get("spawned_at") or ""), abs(s.get("latest_z") or 0.0)),
                  reverse=True)


def shadow_panel(states: Iterable[dict], now: str, shadow_days: int) -> list[dict]:
    """The dispersion **shadow** panel + burn-in clock: active shadow leads (spawner dispersion), each
    with days-since-spawn vs `shadow_days` (DEFAULT 90) and whether burn-in is complete. Honestly-EMPTY
    until §4b/§9e is wired (dispersion needs the holdings/constituent-price vertical) — an empty list
    renders "dispersion: not yet wired", never a faked record. The clock only SURFACES readiness;
    promotion is a human config flip (`dispersion.paging`), never auto (§9e CONTRACT)."""
    out = []
    for s in states:
        if s.get("status") == "active" and s.get("shadow") and s.get("spawner") == "dispersion":
            elapsed = _days_between(s.get("spawned_at"), now)
            out.append({**s, "shadow_days_elapsed": elapsed, "shadow_days_target": int(shadow_days),
                        "burn_in_complete": elapsed is not None and elapsed >= int(shadow_days)})
    return out


def ceiling_status(states: Iterable[dict], ceiling: int) -> dict:
    """The §8a active-lead ceiling tripwire: the live (non-shadow) count vs the configured ceiling.
    `over` is a HUMAN-recalibration tripwire, never an auto-tune (standing-review CONTRACT) — the banner
    says 'tighten thresholds, or the regime changed', it does not move a threshold."""
    n = len(active_nonshadow(list(states)))
    over = n > int(ceiling)
    return {"count": n, "ceiling": int(ceiling), "over": over,
            "banner": (f"Over ceiling ({n}/{ceiling}): tighten thresholds, or the regime changed — "
                       "either way, review." if over else None)}


def macro_catalog(states: Iterable[dict]) -> list[dict]:
    """The read-only **macro catalog**: leads whose current verdict is `off-thesis-real` (real but
    off-thesis macro/sector regime). CONTRACT (CLAUDE.md): read-only context for human adjudication —
    NEVER a trade/tilt trigger, never piped anywhere as actionable, never a 'regime forming' alert
    stream. Rendering it is consultation; the correct action on a detected macro regime is none."""
    return [s for s in states if s.get("verdict") == "off-thesis-real"]


def unknown_type_summary(states: Iterable[dict]) -> dict:
    """The unknown-type panel — event types outside the v1 vocabulary, aggregated across all leads.
    Empty in v1 (built anyway, spec §11): it is exactly where a v2 writer's new type first surfaces,
    counted and referenced, never a crash."""
    counts: Counter = Counter()
    items: list[dict] = []
    for s in states:
        u = s.get("unknown_types") or {}
        for it in u.get("items", []):
            counts[it.get("type")] += 1
            items.append({"lead": s.get("lead"), **it})
    return {"counts": dict(counts), "items": items}


def registry_health(states: Iterable[dict]) -> dict:
    """Operational registry health: lead counts by disposition + a verdict histogram. Not decision-
    driving — a legibility panel."""
    states = list(states)
    live = active_nonshadow(states)
    shadow = [s for s in states if s.get("status") == "active" and s.get("shadow")]
    reverted = [s for s in states if s.get("status") == "reverted"]
    verdicts = Counter(s.get("verdict") for s in states)
    return {"total": len(states), "active_live": len(live), "active_shadow": len(shadow),
            "reverted": len(reverted), "verdicts": dict(verdicts)}


def capture_inventory_counts(states: Iterable[dict]) -> dict:
    """Per-lead discourse-capture count (§6 capture inventory, §8b) — how many captures each lead has
    accrued, from the fold's `capture_inventory`. A read-only legibility line (build note §3h: a tiny
    count-per-lead, not a new page); v1 never READS a capture, so this counts, never renders, content.
    Leads with zero captures are omitted (keep the line short)."""
    return {s.get("lead"): len(s.get("capture_inventory") or [])
            for s in states if (s.get("capture_inventory") or [])}


# --- the _system panels (faults, launches, coverage, run history) -------------------------------


def fault_log(registry, limit: int = 100) -> list[dict]:
    """The fault log — every `fault` event, most recent first. Carries the §10 `category` (operational |
    review-advisory, default operational for legacy faults) + `on_live_lead`, so the email and the
    dashboard render the two classes distinctly: an OPERATIONAL fault is 'something broke, go fix it' (it
    paged); a REVIEW-ADVISORY is a sensor correctly punting an unreliable extraction to a human (surfaced,
    not paged unless on a live-lead fund). Forensic record of everything that was flagged."""
    rows = registry.events_by_type("fault")
    out = []
    for r in rows:
        p = _payload(r)
        out.append({"ts": r["ts"], "lead": r["lead"], "subsystem": p.get("subsystem"),
                    "message": p.get("message"), "category": p.get("category", "operational"),
                    "on_live_lead": bool(p.get("on_live_lead", False))})
    out.sort(key=lambda e: e["ts"], reverse=True)
    return out[:limit]


def launch_panel(registry) -> list[dict]:
    """The read-only **launch panel**: recorded launch DETECTIONS of LISTED funds (`launch.unverified` on
    `_system`, WITH a ticker), most recent first. Survey-only, never pushed (spec §11) — a cluster of
    unmatched launches in a novel area is itself worth pulling up, not a stream that pages.

    Two deliberate omissions (both honest, neither hides data):
    - The fund **name is not surfaced** — the mf-tickers feed carries none (the launch sensor records
      `name_raw=None`), so it is structurally empty at the survey stage; the column returns when the deferred
      name-enrichment slice lands (see sensors/launch.py). A column of "—" would signal missing-data where
      the truth is not-yet-enriched.
    - **Unlisted detections** (a series the mf feed lists with an EMPTY symbol — a fund with no ticker) are
      filtered from this listed-launch table, but KEPT COUNTED as a coverage fact (`unlisted_launch_count`) —
      the append-only record keeps every detection; this is a view filter, never a silently-hidden blind spot."""
    out = []
    for r in registry.events_by_type("launch.unverified"):
        p = _payload(r)
        ticker = p.get("ticker")
        if not ticker:  # an unlisted series (empty mf symbol) — counted below, not a listed-launch survey row
            continue
        out.append({"ts": r["ts"], "ticker": ticker, "series_id": p.get("series_id"),
                    "detected_at": p.get("detected_at") or r["ts"]})
    out.sort(key=lambda e: e["ts"], reverse=True)
    return out


def unlisted_launch_count(registry) -> int:
    """The count of `launch.unverified` detections with NO ticker — a series the mf feed lists with an empty
    symbol (a fund the universe detected but can't yet resolve to a ticker). `launch_panel` filters these out
    of the listed-launch survey; this keeps them a VISIBLE coverage fact (never a silently-hidden blind spot).
    The append-only record keeps every detection regardless."""
    return sum(1 for r in registry.events_by_type("launch.unverified") if not _payload(r).get("ticker"))


def dormant_pile(registry) -> dict:
    """The **coverage / dormant-pile** map (the §10 blindness map, spec §11): the LATEST corroboration
    disposition per launched fund that landed dormant on `_system`, grouped by disposition and ranked by
    count. This is the honest coverage gap — which issuers/dispositions the intake can't yet resolve — and
    the roadmap for widening it (holdings parsers, SOI). `match` never appears (it accretes onto a live
    lead). Renders empty/sparse honestly (corroboration is bounded on the holdings-corroboration SLOT)."""
    rows = registry.events_by_type("launch")
    latest: dict[str, tuple] = {}  # series_id -> ((ts, event_id), payload) — keep the newest per fund
    for r in rows:
        if r["lead"] != SYSTEM_LEAD:
            continue  # a `match` is on the accreted lead, not the pile
        p = _payload(r)
        sid = p.get("series_id")
        if sid is None:
            continue
        key = (r["ts"], str(r["event_id"]))
        if sid not in latest or key > latest[sid][0]:
            latest[sid] = (key, p)
    groups: dict[str, list] = {}
    for sid, (_key, p) in latest.items():
        disp = p.get("corroboration", "unknown")
        groups.setdefault(disp, []).append(
            {"series_id": sid, "ticker": p.get("ticker"), "detected_at": p.get("detected_at"),
             "sectors": p.get("concentration_sectors")})
    counts = {d: len(v) for d, v in groups.items()}
    # Ranked: known dormant dispositions in their canonical order, then anything else by count desc.
    order = {d: i for i, d in enumerate(DORMANT_DISPOSITIONS)}
    ranked = sorted(counts, key=lambda d: (order.get(d, len(order)), -counts[d]))
    return {"by_disposition": groups, "counts": counts, "ranked": ranked,
            "total": sum(counts.values())}


def heartbeat(runs: Iterable[Mapping], now: str, floor_days: int = 7) -> dict:
    """The weekly dead-man (spec §10, CONTRACT): the most recent run and the silence since. `runs` is
    `recent_runs(registry)` (newest first). `ok` iff a run landed within `floor_days` — silence beyond
    the floor unambiguously means BROKEN (the cadence floor is the whole alert posture). Empty runs ->
    broken (nothing has ever run)."""
    runs = list(runs)
    if not runs:
        return {"ok": False, "last_run_ts": None, "silence_days": None, "floor_days": int(floor_days),
                "reason": "no runs recorded — the runner has never completed a tick"}
    last = runs[0]
    silence = _days_between(last["ts"], now)
    ok = silence is not None and silence <= int(floor_days)
    return {"ok": ok, "last_run_ts": last["ts"], "last_run_date": last["date"],
            "silence_days": silence, "floor_days": int(floor_days),
            "reason": None if ok else f"silence {silence}d > {floor_days}d floor — broken"}


def manual_queue(machine) -> list[dict]:
    """The manual-resolution queue (§2): tickers awaiting a human EDGAR verification. `machine` is a
    read-only ResolutionMachine (EDGAR/registry not touched). Each row: ticker, when it first failed,
    last attempt, attempt count, and the original detection time."""
    out = []
    for row in machine.manual_queue():
        out.append({"ticker": row["ticker"], "first_failed_at": row["first_failed_at"],
                    "last_attempt_at": row["last_attempt_at"], "attempts": row["attempts"],
                    "detected_at": row["detected_at"]})
    return out


def lead_timeline(registry, lead: str) -> list[dict]:
    """The per-lead event timeline (the thaw-backward forensic view): every event on a lead in
    (ts, event_id) order, each with a short payload summary. Read-only; the fold of these IS the lead."""
    out = []
    for r in registry.events_for_lead(lead):
        p = _payload(r)
        summary = p.get("display") or p.get("corroboration") or p.get("subsystem") or ""
        out.append({"ts": r["ts"], "type": r["type"], "event_id": r["event_id"],
                    "summary": str(summary)})
    return out
