"""Regression: an INERT `off-thesis-real` lead must not surface in the ranked ACTIVE-leads panel (N10).

`rank_active_leads` is the top-of-page "Active leads — the real evidence" panel. It filters through
`active_nonshadow`, which keys on **status + shadow only, never verdict** (fold.fold: "Verdict is
DISPLAY-ONLY: nothing keys on it"). But `off-thesis-real` is the one verdict the system defines as
INERT — real-but-permanently-set-aside macro/sector context, with its own read-only `macro_catalog`
home and an explicit CLAUDE.md CONTRACT that it is "never a trade/tilt trigger." A `verdict` event
sets `state["verdict"]` without touching `state["status"]` (only a `.reverted` does), so a lead can be
simultaneously status=active, shadow=False, verdict=off-thesis-real — and it then appears in the
priority "real evidence" panel a viewer scans for live actionable signals. That is the
"misrepresent a state as a signal" risk the thesis-smoke-detector brief is built to avoid.

This is the INFERRED finding N10: it depends on the oracle emitting the off-thesis-real verdict without
a paired status change — which is exactly how the fold models a verdict (display-only). Style mirrors
tests/test_dashboard_views.py (the `_state` minimal folded-state dict).
"""

from prospector.dashboard import views


def _state(lead, *, status="active", shadow=False, spawner="xcorr", z=None, spawned_at=None,
           verdict="none"):
    return {"lead": lead, "status": status, "shadow": shadow, "spawner": spawner, "latest_z": z,
            "spawned_at": spawned_at, "verdict": verdict, "display": lead,
            "unknown_types": {"count": 0, "items": []}}


def test_off_thesis_real_lead_is_not_in_the_ranked_active_panel():
    # A live xcorr lead the oracle has verdicted off-thesis-real (real, but macro/off-thesis — INERT).
    # It is status=active + non-shadow, so today it leaks into the "real evidence" panel. It belongs in
    # the macro_catalog (read-only context), NOT in the actionable list. RED today.
    states = [
        _state("xcorr-live", z=3.1, spawned_at="2026-07-06T00:00:00Z"),                 # a genuine live lead
        _state("xcorr-offthesis", z=4.9, spawned_at="2026-07-07T00:00:00Z",
               verdict="off-thesis-real"),                                              # INERT — must not rank
    ]
    ranked_leads = [s["lead"] for s in views.rank_active_leads(states)]

    assert "xcorr-offthesis" not in ranked_leads, (
        "an off-thesis-real (INERT) lead surfaced in the ranked ACTIVE-leads panel — a viewer scanning "
        "the priority 'real evidence' list reads a permanently-set-aside macro lead as a live "
        "actionable signal (N10); it belongs only in macro_catalog")
    assert "xcorr-live" in ranked_leads  # the genuine live lead is unaffected


def test_off_thesis_real_lead_is_still_in_the_macro_catalog():
    # The off-thesis-real lead must not simply DISAPPEAR — it stays in its read-only home. Guards
    # against a fix that drops the lead everywhere instead of demoting it to the catalog.
    state = _state("xcorr-offthesis", z=4.9, spawned_at="2026-07-07T00:00:00Z",
                   verdict="off-thesis-real")
    catalog_leads = [s["lead"] for s in views.macro_catalog([state])]
    assert catalog_leads == ["xcorr-offthesis"], (
        "the off-thesis-real lead must remain in the read-only macro_catalog even once excluded from "
        "the active panel (N10)")
