"""Email rendering — deterministic templating of folds into (subject, body) (spec §8a, §10).

The sender is a **dumb templater**: this module turns a `context` dict (folds the runner gathered) into
the heartbeat / state-change / fault emails §8a specifies. It is a **pure function of the folds** — no
LLM, no generated prose (CLAUDE.md "no LLM text as data"): the same context renders the same bytes, so
the email is honest by construction and unit-testable with no socket/browser (same discipline as
`dashboard/export.py`). It reuses the SAME `dashboard/views.*` view-models the board-snapshot export and
the dashboard render — share shapes, never a second copy that can drift.

Boundary (build note 2026-07-10-10): this module renders; it never DECIDES to send. The push decision
(the shadow-push gate + the nuisance-alarm suppression) lives in the runner's `_compute_push`. `build_context`
gathers folds; `render_push` / `render_heartbeat` template them. Neither reads a threshold or re-runs a sensor.
"""

from __future__ import annotations

from typing import Iterable

from prospector.dashboard import views


# --- small render helpers (self-contained, mirroring export._fmt so this stays a standalone pure module) ---

def _fmt(v) -> str:
    """A value as compact display text: None -> em-dash, float -> 4 sig figs, else str."""
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.4g}"
    return str(v)


def _age(days: int | None) -> str:
    return "—" if days is None else f"{days}d"


# --- the context (the folds the renderers template — gathered once, in the runner) ----------------

def build_context(registry, states: Iterable[dict], runs, machine, cfg: dict, now: str, *,
                  faults: list, changed_leads: dict, trigger: str) -> dict:
    """Gather every fold the §8a email templates need, ONCE, into a plain dict. Pure over the stored
    record (calls only `views.*` — no fetch, no recompute, no write). `states` is `views.fold_all_leads`,
    `runs` is `recent_runs` (newest first), `machine` is the read-only ResolutionMachine (manual queue).
    `faults` is THIS tick's fault list (the push subject keys on it); `recent_faults` is the forensic log
    the body shows (so a persisting fault stays visible in the heartbeat even when suppressed from paging)."""
    states = list(states)
    ceiling = int((cfg.get("oracle") or {}).get("active_lead_ceiling", 8))
    shadow_days = int((cfg.get("dispersion") or {}).get("shadow_days", 90))

    ranked = views.rank_active_leads(states)
    active = [{"lead": s["lead"], "display": s.get("display"), "spawner": s.get("spawner"),
               "latest_z": s.get("latest_z"), "verdict": s.get("verdict"),
               "spawned_at": s.get("spawned_at"), "event_count": s.get("event_count"),
               "age_days": views._days_between(s.get("spawned_at"), now)} for s in ranked]
    shadow = views.shadow_panel(states, now, shadow_days)
    cs = views.ceiling_status(states, ceiling)
    hb = views.heartbeat(runs, now)
    queue = views.manual_queue(machine) if machine is not None else []
    health = views.registry_health(states)

    return {
        "now": now,
        "trigger": trigger,                       # "push" | "heartbeat" (which subject to build)
        "active": active,                         # ranked live (non-shadow, non-macro) leads, with age
        "shadow": shadow,                         # dispersion burn-in rows (elapsed/target/complete)
        "ceiling": cs,                            # {count, ceiling, over, banner}
        "heartbeat": hb,                          # the dead-man dict {ok, reason, last_run_date, ...}
        "queue": queue,                           # manual-resolution queue (rendered only when non-empty)
        "faults": list(faults or []),             # THIS tick's faults — the FAULT subject/emphasis
        "recent_faults": views.fault_log(registry, limit=20),  # forensic body section (persisting faults)
        "changed_leads": dict(changed_leads or {}),            # lead -> [changed {status,shadow,verdict}]
        "health": health,
    }


# --- the §10 fault taxonomy (operational vs review-advisory) --------------------------------------

def _partition_faults(faults: list) -> tuple[list, list]:
    """Split a fault list into (operational, review-advisory) by the §10 `category` — a missing category
    defaults to operational (the conservative default: an unrecognized fault is treated as breakage)."""
    op = [f for f in faults if f.get("category", "operational") != "review-advisory"]
    adv = [f for f in faults if f.get("category") == "review-advisory"]
    return op, adv


def _page_worthy(faults: list) -> list:
    """The faults that DRIVE a page (§10 alarm-posture taxonomy — mirrors runner._page_worthy_faults):
    operational faults + review-advisories on a live-lead fund. A non-live-lead advisory is surfaced but
    never paged, so it never sets a FAULT subject."""
    return [f for f in faults
            if f.get("category", "operational") != "review-advisory" or f.get("on_live_lead")]


# --- subjects (§8a) --------------------------------------------------------------------------------

def _changed_summary(changed_leads: dict) -> str:
    """A compact 'what changed this run' phrase for the state-change subject. One lead -> name it + its
    changed fields; several -> a count (the body carries the per-lead detail)."""
    if not changed_leads:
        return "state advanced"
    if len(changed_leads) == 1:
        lead, fields = next(iter(changed_leads.items()))
        fs = ", ".join(fields) if fields else "state"
        return f"{lead} ({fs})"
    return f"{len(changed_leads)} leads changed"


def _fault_summary(faults: list) -> str:
    """The FAULT subject tail: the distinct subsystem(s) that faulted this tick (bounded — the body
    carries messages)."""
    subs = []
    for f in faults:
        s = f.get("subsystem") or "unknown"
        if s not in subs:
            subs.append(s)
    if not subs:
        return "unknown"
    if len(subs) == 1:
        return subs[0]
    return f"{subs[0]} (+{len(subs) - 1} more)"


def heartbeat_subject(ctx: dict, prefix: str) -> str:
    """`[PROS] heartbeat — N active, M shadow, K changes` (§8a). The subject ENCODES state, so silence
    past the weekly floor is unambiguously *broken*, never 'calm' — the dead-man property."""
    n = ctx["ceiling"]["count"]
    m = len(ctx["shadow"])
    k = len(ctx["changed_leads"])
    changes = "no changes" if k == 0 else (f"{k} change" if k == 1 else f"{k} changes")
    return f"{prefix} heartbeat — {n} active, {m} shadow, {changes}"


def push_subject(ctx: dict, prefix: str) -> str:
    """The immediate-push subject (§8a). A PAGE-WORTHY fault (operational, or a review-advisory on a live
    lead — §10 taxonomy) outranks a state change when a tick carries both: `[PROS] FAULT: <subsystem>` else
    `[PROS] state change: <summary>`. A non-live-lead advisory never pages, so it never sets the subject."""
    pw = _page_worthy(ctx["faults"])
    if pw:
        return f"{prefix} FAULT: {_fault_summary(pw)}"
    return f"{prefix} state change: {_changed_summary(ctx['changed_leads'])}"


# --- body (§8a: scan stats · active digest one-line-each · shadow · queue if non-empty · faults · banner) ---

def _body(ctx: dict) -> str:
    lines: list[str] = []
    h, hb = ctx["health"], ctx["heartbeat"]

    # Scan stats — the one-glance state (also the dead-man's "is it alive" line). Faults and review-
    # advisories are counted DISTINCTLY (§10): "something broke, go fix it" and "the sensor correctly
    # punted, look eventually" are different signals — one number would lose that (a complete summary
    # is not a flat one). This is also the count-honesty fix: never '0 faults' beside faults that fired.
    op, adv = _partition_faults(ctx["faults"])
    lines.append(
        f"Scan {ctx['now']}: {h['active_live']} live · {h['active_shadow']} shadow · "
        f"{h['reverted']} reverted · {len(ctx['changed_leads'])} changed this run · "
        f"{len(op)} fault(s) · {len(adv)} for review this run.")
    hb_state = "OK" if hb["ok"] else f"BROKEN — {hb['reason']}"
    lines.append(f"Heartbeat: {hb_state} · last run {hb.get('last_run_date') or '—'}.")

    # The over-ceiling banner rides EVERY email while breached (the §8a tripwire; the human recalibrates).
    if ctx["ceiling"]["over"]:
        lines += ["", f"⚠ {ctx['ceiling']['banner']}"]

    # Active-leads digest — one line each (§8a): display · age · latest z · verdict.
    lines += ["", "Active leads (live):"]
    if ctx["active"]:
        for s in ctx["active"]:
            lines.append(
                f"  · {s.get('display') or s['lead']} — age {_age(s.get('age_days'))}, "
                f"z={_fmt(s.get('latest_z'))}, verdict={s.get('verdict')}, "
                f"events={s.get('event_count')}")
    else:
        lines.append("  (none — xcorr spawns a live lead on a sustained residual departure)")

    # Dispersion shadow / burn-in summary.
    lines += ["", "Dispersion shadow (burn-in):"]
    if ctx["shadow"]:
        for s in ctx["shadow"]:
            done = "complete" if s.get("burn_in_complete") else "running"
            lines.append(
                f"  · {s.get('display') or s['lead']} — z={_fmt(s.get('latest_z'))}, "
                f"{_age(s.get('shadow_days_elapsed'))}/{s.get('shadow_days_target')}d ({done})")
    else:
        lines.append("  (none)")

    # What changed this run (the push's core; empty on a quiet heartbeat).
    if ctx["changed_leads"]:
        lines += ["", "Changed this run:"]
        for lead, fields in ctx["changed_leads"].items():
            lines.append(f"  · {lead}: {', '.join(fields) if fields else 'state'}")

    # Manual-resolution queue — ONLY when non-empty (§8a).
    if ctx["queue"]:
        lines += ["", "Manual-resolution queue (resolve via `pros identity resolve <ticker> --series-id S######`):"]
        for q in ctx["queue"]:
            lines.append(f"  · {q['ticker']} — {q['attempts']} attempt(s), first failed {q['first_failed_at']}")

    # Faults + advisories — the forensic log, split by §10 category (persisting items stay visible here
    # even when suppressed/not-paged). OPERATIONAL: something broke (paged, then rides the heartbeat while
    # it persists). REVIEW-ADVISORIES: a sensor correctly punted an unreliable extraction to a human —
    # surfaced but not paged, EXCEPT one on a live-lead fund (marked; it paged).
    op_recent, adv_recent = _partition_faults(ctx["recent_faults"])
    lines += ["", "Faults (recent) — operational:"]
    if op_recent:
        for f in op_recent:
            lines.append(f"  · {f['ts']} · {f.get('subsystem')}: {f.get('message')}")
    else:
        lines.append("  (none)")

    lines += ["", "Manual review — advisories (recent, not paged unless on a live lead):"]
    if adv_recent:
        for f in adv_recent:
            flag = "  [LIVE-LEAD — paged]" if f.get("on_live_lead") else ""
            lines.append(f"  · {f['ts']} · {f.get('subsystem')}: {f.get('message')}{flag}")
    else:
        lines.append("  (none)")

    return "\n".join(lines)


def render_push(ctx: dict, prefix: str) -> tuple[str, str]:
    """A state-change / fault push (§8a) as (subject, body). Immediate — the runner already decided to send
    (a NON-shadow state change or a NEW/changed fault); this only templates it."""
    return push_subject(ctx, prefix), _body(ctx)


def render_heartbeat(ctx: dict, prefix: str) -> tuple[str, str]:
    """The weekly heartbeat / dead-man (§8a) as (subject, body). Fires regardless of activity — the arriving
    email IS the liveness proof; its subject encodes state so silence past the floor means broken. (The
    *cadence* that makes silence meaningful arms at M7, when the runner is scheduled — build note fork 2.)"""
    body = _body(ctx)
    note = ("\n\nWeekly heartbeat — silence beyond the 7-day floor means broken (§8a dead-man). "
            "Cadence arms once the runner is scheduled (M7).")
    return heartbeat_subject(ctx, prefix), body + note
