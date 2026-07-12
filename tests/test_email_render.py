"""§10 email rendering — the PURE templating of folds into (subject, body) (spec §8a). Offline: no
smtplib, no socket, no store; render is a pure function of the context dict (the no-LLM CONTRACT — same
context, same bytes). `build_context` is exercised once over a real registry to prove it gathers the same
`views.*` folds the dashboard/board-snapshot render (no drift from the screen)."""

from prospector.dashboard import views
from prospector.runner import email_render
from prospector.store.envelope import SYSTEM_LEAD
from prospector.store.event_store import EventStore

PREFIX = "[PROS]"


def _ctx(**over) -> dict:
    """A minimal render context with the keys `email_render._body` reads — overridden per test."""
    ctx = {
        "now": "2026-07-10T00:00:00Z",
        "trigger": "run",
        "active": [],
        "shadow": [],
        "ceiling": {"count": 0, "ceiling": 8, "over": False, "banner": None},
        "heartbeat": {"ok": True, "reason": None, "last_run_date": "2026-07-10"},
        "queue": [],
        "faults": [],
        "recent_faults": [],
        "changed_leads": {},
        "health": {"total": 0, "active_live": 0, "active_shadow": 0, "reverted": 0, "verdicts": {}},
    }
    ctx.update(over)
    return ctx


# === subjects (§8a) ================================================================================

def test_heartbeat_subject_encodes_state():
    ctx = _ctx(ceiling={"count": 3, "ceiling": 8, "over": False, "banner": None},
               shadow=[{"lead": "d1"}, {"lead": "d2"}])
    assert email_render.heartbeat_subject(ctx, PREFIX) == "[PROS] heartbeat — 3 active, 2 shadow, no changes"
    # A change count is encoded so silence past the floor is unambiguously *broken*, never 'calm'.
    assert "1 change" in email_render.heartbeat_subject(_ctx(changed_leads={"ld_x": ["status"]}), PREFIX)


def test_push_subject_fault_outranks_state_change():
    both = _ctx(changed_leads={"ld_x": ["status"]},
                faults=[{"subsystem": "ingest.prices", "message": "XLK empty"}])
    assert email_render.push_subject(both, PREFIX) == "[PROS] FAULT: ingest.prices"  # FAULT wins
    change = _ctx(changed_leads={"ld_x": ["status"]})
    s = email_render.push_subject(change, PREFIX)
    assert s.startswith("[PROS] state change:") and "ld_x" in s
    multi = _ctx(faults=[{"subsystem": "a", "message": "1"}, {"subsystem": "b", "message": "2"}])
    assert email_render.push_subject(multi, PREFIX) == "[PROS] FAULT: a (+1 more)"


# === body (§8a: scan · active one-line-each · shadow · queue-if-nonempty · faults · banner) =========

def test_body_carries_the_required_sections():
    ctx = _ctx(
        ceiling={"count": 9, "ceiling": 8, "over": True,
                 "banner": "Over ceiling (9/8): tighten thresholds, or the regime changed — either way, "
                           "review."},
        active=[{"lead": "ld_x", "display": "XLK×XLU", "spawner": "xcorr", "latest_z": 3.2,
                 "verdict": "watch", "spawned_at": "2026-07-01T00:00:00Z", "event_count": 7,
                 "age_days": 9}],
        shadow=[{"lead": "d1", "display": "XLI split", "latest_z": 4.1, "shadow_days_elapsed": 10,
                 "shadow_days_target": 90, "burn_in_complete": False}],
        recent_faults=[{"ts": "2026-07-10T00:00:00Z", "subsystem": "ingest.prices",
                        "message": "XLK empty"}],
        health={"total": 3, "active_live": 1, "active_shadow": 1, "reverted": 1, "verdicts": {}},
        changed_leads={"ld_x": ["status"]})
    _, body = email_render.render_push(ctx, PREFIX)
    assert "Scan 2026-07-10T00:00:00Z:" in body                     # scan stats line
    assert "XLK×XLU — age 9d, z=3.2, verdict=watch" in body         # active digest, one line each
    assert "Over ceiling (9/8)" in body                             # the tripwire banner while breached
    assert "XLI split — z=4.1, 10d/90d (running)" in body           # shadow burn-in summary
    assert "ingest.prices: XLK empty" in body                       # faults (forensic) section
    assert "ld_x: status" in body                                   # what changed this run


def test_manual_queue_section_only_when_nonempty():
    assert "Manual-resolution queue" not in email_render.render_push(_ctx(), PREFIX)[1]
    ctx = _ctx(queue=[{"ticker": "NEWX", "attempts": 2, "first_failed_at": "2026-07-01T00:00:00Z"}])
    body = email_render.render_push(ctx, PREFIX)[1]
    assert "Manual-resolution queue" in body and "NEWX" in body


def test_empty_active_and_faults_render_honestly_not_blank():
    body = email_render.render_push(_ctx(), PREFIX)[1]
    assert "Active leads (live):" in body and "(none" in body
    assert "Faults (recent) — operational:" in body and "Manual review — advisories" in body


# === the §10 fault taxonomy in the render (operational vs review-advisory, split distinctly) ========

def _f(subsystem, message, category, *, on_live_lead=False) -> dict:
    return {"ts": "2026-07-10T00:00:00Z", "subsystem": subsystem, "message": message,
            "category": category, "on_live_lead": on_live_lead}


def test_faults_and_advisories_render_distinctly_with_a_split_count():
    ctx = _ctx(
        faults=[_f("ingest.prices", "boom", "operational"),
                _f("mandate", "unreliable — manual review", "review-advisory"),
                _f("mandate", "held fund reworded", "review-advisory", on_live_lead=True)],
        recent_faults=[_f("ingest.prices", "boom", "operational"),
                       _f("mandate", "unreliable — manual review", "review-advisory"),
                       _f("mandate", "held fund reworded", "review-advisory", on_live_lead=True)])
    subj, body = email_render.render_push(ctx, PREFIX)
    # The split count — 1 operational fault, 2 for review (never a single flat number).
    assert "1 fault(s) · 2 for review this run" in body
    # Distinct sections; the operational fault under Faults, the advisories under Manual review.
    assert "Faults (recent) — operational:" in body and "ingest.prices: boom" in body
    assert "Manual review — advisories" in body and "unreliable — manual review" in body
    # The live-lead advisory is flagged (it paged); a page-worthy fault sets the FAULT subject.
    assert "held fund reworded  [LIVE-LEAD — paged]" in body
    assert subj.startswith("[PROS] FAULT:")


def test_a_non_live_advisory_alone_does_not_set_a_fault_subject():
    # Only non-live advisories this tick: none page-worthy, so a co-occurring state change owns the subject.
    ctx = _ctx(changed_leads={"ld_x": ["status"]},
               faults=[_f("mandate", "unreliable — manual review", "review-advisory")])
    assert email_render.push_subject(ctx, PREFIX).startswith("[PROS] state change:")


# === determinism / no-LLM ==========================================================================

def test_render_is_deterministic_same_context_same_bytes():
    ctx = _ctx(active=[{"lead": "ld_x", "display": "XLK×XLU", "spawner": "xcorr", "latest_z": 3.2,
                        "verdict": "watch", "spawned_at": "2026-07-01T00:00:00Z", "event_count": 7,
                        "age_days": 9}])
    assert email_render.render_push(ctx, PREFIX) == email_render.render_push(ctx, PREFIX)
    assert email_render.render_heartbeat(ctx, PREFIX) == email_render.render_heartbeat(ctx, PREFIX)


def test_heartbeat_body_states_the_deadman_and_the_m7_caveat():
    subj, body = email_render.render_heartbeat(_ctx(), PREFIX)
    assert subj.startswith("[PROS] heartbeat —")
    assert "silence beyond the 7-day floor means broken" in body
    assert "arms once the runner is scheduled (M7)" in body     # do not claim a live dead-man pre-M7


def test_heartbeat_health_ok_when_clean_and_degraded_on_operational_fault():
    """§8a/§10 summary-honesty: a received heartbeat says Health: OK only when nothing broke this cycle; an
    operational fault flips it to DEGRADED (never a bare 'OK' beside a fault in the same body). A review-
    advisory is a correct punt, not breakage, so it stays OK. Liveness (silence dead-man) is the separate axis."""
    _, clean = email_render.render_heartbeat(_ctx(), PREFIX)
    assert "Health: OK ·" in clean and "DEGRADED" not in clean

    _, degraded = email_render.render_heartbeat(
        _ctx(faults=[_f("ingest.prices", "XLK empty", "operational")]), PREFIX)
    assert "Health: DEGRADED — 1 fault(s) this run" in degraded

    _, punt = email_render.render_heartbeat(
        _ctx(faults=[_f("mandate", "extraction unreliable — manual review", "review-advisory")]), PREFIX)
    assert "Health: OK ·" in punt


# === build_context over a real registry (gathers views.* folds — cannot drift from the screen) =====

def test_build_context_gathers_the_view_model_folds(layout, registry):
    store = EventStore(layout, registry)
    store.append({"ts": "2026-07-06T00:00:00Z", "lead": "ld_x", "type": "lead.spawned",
                  "payload": {"spawner": "xcorr", "display": "XLK×XLU", "shadow": False}, "schema": 1})
    store.append({"ts": "2026-07-06T00:00:01Z", "lead": "ld_x", "type": "xcorr.departure",
                  "payload": {"display": "XLK×XLU", "z": 3.2, "market_stress": False}, "schema": 1})
    store.append({"ts": "2026-07-06T00:00:02Z", "lead": SYSTEM_LEAD, "type": "fault",
                  "payload": {"subsystem": "ingest.prices", "message": "XLK empty"}, "schema": 1})

    states = views.fold_all_leads(registry)
    ctx = email_render.build_context(
        registry, states, [], None, {}, "2026-07-10T00:00:00Z",
        faults=[{"subsystem": "ingest.prices", "message": "XLK empty"}],
        changed_leads={"ld_x": ["status"]}, trigger="run")

    assert ctx["ceiling"]["count"] == 1
    assert ctx["active"] and ctx["active"][0]["lead"] == "ld_x"
    assert ctx["active"][0]["age_days"] == 4                       # 2026-07-06 -> 2026-07-10
    assert any(f["subsystem"] == "ingest.prices" for f in ctx["recent_faults"])
    # And it renders end-to-end over the gathered folds.
    _, body = email_render.render_push(ctx, PREFIX)
    assert "XLK×XLU" in body and "ingest.prices: XLK empty" in body
