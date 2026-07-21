"""§11 dashboard view-models — pure folds of the fossil record (no streamlit, no writes, no recompute).

These pin the SHAPING logic each panel renders: the ranked live-leads filter (xcorr firings surface,
shadow/reverted excluded), the honestly-empty dispersion shadow panel + its burn-in clock, the §8a
ceiling tripwire, the read-only macro catalog, the coverage/dormant-pile blindness map (a `match` never
appears — it accretes onto a lead), the launch survey, the fault log, and the weekly dead-man. Offline:
events are appended to a real registry; the socket guard fails any real connection."""

from prospector.dashboard import views
from prospector.store.envelope import SYSTEM_LEAD
from prospector.store.event_store import EventStore

NOW = "2026-07-07T00:00:00Z"


def _state(lead, *, status="active", shadow=False, spawner="xcorr", z=None, spawned_at=None,
           verdict="none", unknown=None):
    """A minimal folded-state dict (the fields the list-shaping views read)."""
    return {"lead": lead, "status": status, "shadow": shadow, "spawner": spawner, "latest_z": z,
            "spawned_at": spawned_at, "verdict": verdict, "display": lead,
            "unknown_types": unknown or {"count": 0, "items": []}}


# === ranked active leads: live only, recency × magnitude ============================================

def test_rank_active_leads_is_live_only_and_ranked():
    states = [
        _state("xcorr-new", z=3.1, spawned_at="2026-07-06T00:00:00Z"),
        _state("xcorr-old", z=9.9, spawned_at="2026-07-01T00:00:00Z"),
        _state("disp-shadow", shadow=True, spawner="dispersion", spawned_at="2026-07-06T00:00:00Z"),
        _state("xcorr-dead", status="reverted", spawned_at="2026-07-06T00:00:00Z"),
    ]
    ranked = views.rank_active_leads(states)
    # Shadow + reverted are excluded (the active_nonshadow oracle filter); newest spawn ranks first.
    assert [s["lead"] for s in ranked] == ["xcorr-new", "xcorr-old"]


# === dispersion shadow panel: honestly-empty until wired, clock when present ========================

def test_shadow_panel_is_empty_until_dispersion_is_wired():
    # No dispersion shadow lead exists yet (§4b is a SLOT) -> the panel renders empty, not faked.
    states = [_state("xcorr-1", spawned_at="2026-07-06T00:00:00Z")]
    assert views.shadow_panel(states, NOW, shadow_days=90) == []


def test_shadow_panel_reports_the_burn_in_clock():
    states = [_state("disp-1", shadow=True, spawner="dispersion", spawned_at="2026-04-01T00:00:00Z")]
    panel = views.shadow_panel(states, NOW, shadow_days=90)
    assert len(panel) == 1
    row = panel[0]
    assert row["shadow_days_target"] == 90
    assert row["shadow_days_elapsed"] == 97          # 2026-04-01 -> 2026-07-07
    assert row["burn_in_complete"] is True           # 97 >= 90 (readiness SURFACED, never auto-promoted)


# === §8a ceiling tripwire ===========================================================================

def test_ceiling_status_flags_over_the_ceiling():
    live = [_state(f"xcorr-{i}", spawned_at=NOW) for i in range(3)]
    assert views.ceiling_status(live, ceiling=8)["over"] is False
    over = views.ceiling_status(live, ceiling=2)
    assert over["over"] is True and "review" in over["banner"]


# === macro catalog: off-thesis-real only, read-only context =========================================

def test_macro_catalog_filters_off_thesis_real():
    states = [_state("a", verdict="off-thesis-real"), _state("b", verdict="watch"),
              _state("c", verdict="off-thesis-real")]
    assert sorted(s["lead"] for s in views.macro_catalog(states)) == ["a", "c"]


def test_registry_health_counts_dispositions():
    states = [_state("a"), _state("b", shadow=True, spawner="dispersion"),
              _state("c", status="reverted"), _state("d", verdict="noise")]
    h = views.registry_health(states)
    assert h == {"total": 4, "active_live": 2, "active_shadow": 1, "reverted": 1,
                 "verdicts": {"none": 3, "noise": 1}}


def test_unknown_type_summary_aggregates_across_leads():
    states = [_state("a", unknown={"count": 1, "items": [{"ts": NOW, "type": "cluster.formed",
                                                           "event_id": "e1"}]}),
              _state("b")]
    summ = views.unknown_type_summary(states)
    assert summ["counts"] == {"cluster.formed": 1} and summ["items"][0]["lead"] == "a"


# === the _system panels: over a real registry =======================================================

def _emit(layout, registry):
    store = EventStore(layout, registry)
    return store.append


def test_launch_panel_and_dormant_pile_over_the_record(layout, registry):
    emit = _emit(layout, registry)
    # Two raw detections (survey), two dormant dispositions on _system, and a MATCH on a live lead.
    emit({"ts": "2026-07-05T00:00:00Z", "lead": SYSTEM_LEAD, "type": "launch.unverified",
          "payload": {"ticker": "NEWX", "series_id": "S000000009", "detected_at": "2026-07-05T00:00:00Z"},
          "schema": 1})
    emit({"ts": "2026-07-06T00:00:00Z", "lead": SYSTEM_LEAD, "type": "launch.unverified",
          "payload": {"ticker": "NEWY", "series_id": "S000000010", "detected_at": "2026-07-06T00:00:00Z"},
          "schema": 1})
    # An UNLISTED detection — a series the mf feed lists with an empty symbol (no ticker). It must be
    # FILTERED from the survey table but KEPT COUNTED as a coverage fact.
    emit({"ts": "2026-07-06T00:00:00Z", "lead": SYSTEM_LEAD, "type": "launch.unverified",
          "payload": {"ticker": "", "series_id": "S000000BAD", "detected_at": "2026-07-06T00:00:00Z"},
          "schema": 1})
    emit({"ts": "2026-07-06T00:00:00Z", "lead": SYSTEM_LEAD, "type": "launch",
          "payload": {"series_id": "S000000009", "ticker": "NEWX",
                      "corroboration": "holdings_unavailable"}, "schema": 1})
    emit({"ts": "2026-07-06T00:00:00Z", "lead": SYSTEM_LEAD, "type": "launch",
          "payload": {"series_id": "S000000010", "ticker": "NEWY", "concentration_sectors": [],
                      "corroboration": "sectors_unresolved"}, "schema": 1})
    emit({"ts": "2026-07-06T00:00:00Z", "lead": "xcorr-abcdef0123", "type": "launch",
          "payload": {"series_id": "S000000011", "ticker": "NEWZ",
                      "corroboration": "match"}, "schema": 1})

    launches = views.launch_panel(registry)
    assert [l["ticker"] for l in launches] == ["NEWY", "NEWX"]  # most recent first; the blank-ticker one gone
    assert "S000000BAD" not in {l["series_id"] for l in launches}   # the unlisted series is NOT surveyed
    assert all("name" not in l for l in launches)                   # the structurally-empty name column is dropped
    assert set(launches[0]) == {"ts", "ticker", "series_id", "detected_at"}
    assert views.unlisted_launch_count(registry) == 1              # ... but KEPT COUNTED (coverage fact)

    pile = views.dormant_pile(registry)
    assert pile["total"] == 2                                   # the MATCH is excluded (on a lead)
    assert pile["counts"] == {"holdings_unavailable": 1, "sectors_unresolved": 1}
    # Ranked in the canonical disposition order (holdings_unavailable before sectors_unresolved).
    assert pile["ranked"] == ["holdings_unavailable", "sectors_unresolved"]


def test_dormant_pile_keeps_only_the_latest_disposition_per_fund(layout, registry):
    emit = _emit(layout, registry)
    # A fund first lands sectors_unresolved, then LATER resolves to dormant_no_match -> only the later
    # disposition counts (the §9d resolution supersedes; the pile is not double-counted).
    emit({"ts": "2026-07-05T00:00:00Z", "lead": SYSTEM_LEAD, "type": "launch",
          "payload": {"series_id": "S000000009", "corroboration": "sectors_unresolved"}, "schema": 1})
    emit({"ts": "2026-07-06T00:00:00Z", "lead": SYSTEM_LEAD, "type": "launch",
          "payload": {"series_id": "S000000009", "concentration_sectors": ["XLK"],
                      "corroboration": "dormant_no_match"}, "schema": 1})
    pile = views.dormant_pile(registry)
    assert pile["counts"] == {"dormant_no_match": 1}


def test_fault_log_is_recent_first(layout, registry):
    emit = _emit(layout, registry)
    emit({"ts": "2026-07-05T00:00:00Z", "lead": SYSTEM_LEAD, "type": "fault",
          "payload": {"subsystem": "ingest.mf_tickers", "message": "edgar down"}, "schema": 1})
    emit({"ts": "2026-07-06T00:00:00Z", "lead": SYSTEM_LEAD, "type": "fault",
          "payload": {"subsystem": "sensor.xcorr", "message": "no market column"}, "schema": 1})
    log = views.fault_log(registry)
    assert [f["subsystem"] for f in log] == ["sensor.xcorr", "ingest.mf_tickers"]


def test_fault_log_carries_the_category_and_live_lead_flag(layout, registry):
    # §10 taxonomy: fault_log distinguishes operational (something broke) from review-advisory (a sensor
    # correctly punted), + the live-lead flag — so the email/dashboard render the two classes distinctly.
    emit = _emit(layout, registry)
    emit({"ts": "2026-07-05T00:00:00Z", "lead": SYSTEM_LEAD, "type": "fault",
          "payload": {"subsystem": "ingest.prices", "message": "boom"}, "schema": 1})  # no category -> op
    emit({"ts": "2026-07-06T00:00:00Z", "lead": SYSTEM_LEAD, "type": "fault",
          "payload": {"subsystem": "mandate", "message": "unreliable — manual review",
                      "category": "review-advisory", "series_id": "S1"}, "schema": 1})
    emit({"ts": "2026-07-07T00:00:00Z", "lead": SYSTEM_LEAD, "type": "fault",
          "payload": {"subsystem": "mandate", "message": "held fund reworded", "series_id": "S2",
                      "category": "review-advisory", "on_live_lead": True}, "schema": 1})
    by_ts = {f["ts"]: f for f in views.fault_log(registry)}
    assert by_ts["2026-07-05T00:00:00Z"]["category"] == "operational"          # missing -> operational
    assert by_ts["2026-07-06T00:00:00Z"]["category"] == "review-advisory"
    assert by_ts["2026-07-06T00:00:00Z"]["on_live_lead"] is False
    assert by_ts["2026-07-07T00:00:00Z"]["on_live_lead"] is True


# === the weekly dead-man ============================================================================

def test_heartbeat_keys_on_last_heartbeat_sent_not_last_run():
    """M7-03: liveness keys on the last HEARTBEAT SENT, not the last run — the run that renders the email
    is a tautology (a run always just happened), so keying on `runs[0].ts` always read OK. `runs` now
    supplies only the informational last-run line."""
    runs = [{"ts": "2026-07-06T00:00:00Z", "date": "2026-07-06"}]     # a fresh run — must NOT alone read OK
    assert views.heartbeat(runs, NOW, last_heartbeat_sent=None)["ok"] is False    # never sent -> broken
    assert views.heartbeat(runs, NOW, "2026-07-05T00:00:00Z", floor_days=7)["ok"] is True   # 2d ago -> ok
    stale = views.heartbeat(runs, NOW, "2026-06-01T00:00:00Z", floor_days=7)      # > a month -> broken
    assert stale["ok"] is False and stale["catch_up"] is True and "broken" in stale["reason"]
    hb8 = views.heartbeat(runs, NOW, "2026-06-29T00:00:00Z", floor_days=7)        # NOW = 07-07 -> 8d ago
    assert hb8["ok"] is False and hb8["catch_up"] is True and hb8["silence_days"] == 8
    assert stale["last_run_date"] == "2026-07-06"                                 # last-run line from runs


def test_last_heartbeat_sent_newest_wins(layout, registry):
    store = EventStore(layout, registry)
    assert views.last_heartbeat_sent(registry) is None                           # never sent -> None
    for ts in ("2026-07-01T00:00:00Z", "2026-07-08T00:00:00Z", "2026-07-04T00:00:00Z"):
        store.append({"ts": ts, "lead": SYSTEM_LEAD, "type": "heartbeat.sent",
                      "payload": {"trigger": "cadence"}, "schema": 1})
    assert views.last_heartbeat_sent(registry) == "2026-07-08T00:00:00Z"          # newest ts wins


# === firewall ======================================================================================
# The dashboard's firewall guard moved to `tests/test_firewall.py`, which sweeps the WHOLE package
# (this one listed 2 files by hand, and a text scan would have false-positived on export.py's
# firewall docstring). One rule, one home.
