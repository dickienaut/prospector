"""The §11 read-only Streamlit dashboard — the render shell (spec §11 / rev13 §8b).

CONTRACT (§11, hard): read-only, **no recompute on view, no autorefresh, no run-now**. This shell only
renders folds of the record the runner already wrote — it never triggers a sensor, a fetch, or a
computation, and there is deliberately no refresh timer and no button that runs anything. The discipline
variable is computation cadence, not display richness (the deliberate inversion of an autorefreshing
cockpit): a surface that only renders stored runs cannot reward compulsive checking. All shaping lives in
`views` (pure, tested); this file is just `st.*` over those view-models. Firewall: never reads the
portfolio config or any trade path — only this store's own record.

Launch:  uv sync --extra dashboard  &&  PROSPECTOR_STORE=./store streamlit run prospector/dashboard/app.py
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

from prospector.config import load_config
from prospector.dashboard import views
from prospector.identity.resolution import ResolutionMachine
from prospector.runner.runlog import recent_runs
from prospector.store.event_store import EventStore
from prospector.store.layout import StoreLayout
from prospector.store.registry import Registry

_CONFIG_PATH = Path("config") / "prospector.yaml"
_STORE_PATH = os.environ.get("PROSPECTOR_STORE", "./store")


def _now() -> str:
    """A DISPLAY 'now' for the silence/burn-in math only — this is a viewer, not the runner, so this
    wall-clock read is never a record time (all record times are the runner's `now`)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _rows_to_table(rows: list[dict]) -> list[dict]:
    return rows  # st.dataframe/table take a list-of-dicts directly


def main() -> None:
    st.set_page_config(page_title="Prospector — reading, never orders", layout="wide")
    st.title("Project Prospector")
    st.caption("Read-only forensic surface — folds of the fossil record. No recompute, no autorefresh, "
               "no run-now (§11 CONTRACT). It proposes reading, never orders. All times UTC.")

    layout = StoreLayout(Path(_STORE_PATH))
    if not layout.registry_path().is_file():
        st.warning(f"No store at `{_STORE_PATH}` yet — run a tick (`pros run`) first, or set "
                   "`PROSPECTOR_STORE`.")
        return

    cfg, _ = load_config(_CONFIG_PATH)
    ceiling = int((cfg.get("oracle") or {}).get("active_lead_ceiling", 8))
    shadow_days = int((cfg.get("dispersion") or {}).get("shadow_days", 90))
    now = _now()

    registry = Registry(layout.registry_path())
    try:
        states = views.fold_all_leads(registry)
        runs = recent_runs(registry)
        machine = ResolutionMachine(registry, EventStore(layout, registry), None, None)  # read-only
        queue = views.manual_queue(machine)
        launches = views.launch_panel(registry)
        pile = views.dormant_pile(registry)
        faults = views.fault_log(registry)

        # --- the dead-man + the ceiling, up top (the alert posture) -------------------------------
        hb = views.heartbeat(runs, now, floor_days=7)
        cs = views.ceiling_status(states, ceiling)
        c1, c2, c3 = st.columns(3)
        c1.metric("Heartbeat", "OK" if hb["ok"] else "BROKEN",
                  delta=(None if hb["ok"] else hb["reason"]), delta_color="off")
        c2.metric("Active leads (live)", f"{cs['count']} / {cs['ceiling']}")
        c3.metric("Last run", hb.get("last_run_date") or "—")
        if not hb["ok"]:
            st.error(f"Dead-man: {hb['reason']}. Silence beyond the weekly floor unambiguously means "
                     "broken (§10).")
        if cs["over"]:
            st.warning(cs["banner"])

        # === AT A GLANCE — the three that serve watching the evidence accumulate ==================
        # Lead with active leads (the real firings) · the dormant pile (where we're blind) · health
        # (is it running / what broke). Everything else is a click deeper (collapsed expanders below).
        # This is the reciprocal-of-a-cockpit priority — evidence + blindness + is-it-alive first; the
        # dashboard's purpose is watching the evidence accumulate, so that is what leads.

        # --- 1. ranked active leads (the wired xcorr firings surface here) --------------------------
        st.header("Active leads")
        st.caption("Live (non-shadow) leads, ranked recency × |z| — the wired xcorr (§4a) firings.")
        ranked = views.rank_active_leads(states)
        if ranked:
            st.dataframe(_rows_to_table([
                {"lead": s["lead"], "display": s.get("display"), "spawner": s.get("spawner"),
                 "latest_z": s.get("latest_z"), "spawned_at": s.get("spawned_at"),
                 "verdict": s.get("verdict"), "events": s.get("event_count")} for s in ranked]),
                width="stretch", hide_index=True)
        else:
            st.info("No live leads yet — xcorr (§4a) spawns them on a sustained residual departure.")

        # --- 2. coverage / dormant pile (where intake is blind — the §10 map) -----------------------
        st.header("Coverage / dormant pile")
        st.caption("The §10 blindness map — where intake can't yet resolve a launch (the roadmap for "
                   "widening holdings/SOI coverage). Ranked by disposition.")
        if pile["total"]:
            st.dataframe(_rows_to_table(
                [{"disposition": d, "count": pile["counts"][d]} for d in pile["ranked"]]),
                width="stretch", hide_index=True)
        else:
            st.info("Empty — no dormant launches recorded yet (corroboration is bounded on the "
                    "holdings-corroboration SLOT).")

        # --- 3. health: the fault log (is it running / what broke) ----------------------------------
        st.header("Health · fault log")
        st.caption("The heartbeat + last-run are up top; this is what broke. A fault always paged (§10).")
        st.dataframe(_rows_to_table(faults) if faults else [{"—": "no faults"}],
                     width="stretch", hide_index=True)

        # === A CLICK DEEPER — the rest of the §11 panels, collapsed by default =====================
        with st.expander("Dispersion shadow (burn-in)"):
            shadow = views.shadow_panel(states, now, shadow_days)
            if shadow:
                st.dataframe(_rows_to_table([
                    {"lead": s["lead"], "display": s.get("display"), "z": s.get("latest_z"),
                     "elapsed_days": s["shadow_days_elapsed"], "target_days": s["shadow_days_target"],
                     "burn_in_complete": s["burn_in_complete"]} for s in shadow]),
                    width="stretch", hide_index=True)
                st.caption("Readiness is surfaced, never auto-promoted — shadow→paging is a human "
                           "config flip that leaves a config.changed fossil (§9e CONTRACT).")
            else:
                st.info("Dispersion is not yet wired (§4b needs the holdings/constituent-price "
                        "vertical). This panel fills once it ships shadow, starting the 90-day clock.")

        with st.expander("Launches (survey)"):
            st.caption("Recorded launch detections — survey-only, never pushed (§11).")
            st.dataframe(_rows_to_table(launches) if launches else [{"—": "no launches recorded"}],
                         width="stretch", hide_index=True)

        with st.expander("Macro catalog"):
            st.caption("Real-but-off-thesis (`off-thesis-real`) verdicts — read-only context for human "
                       "adjudication. NEVER a trade/tilt trigger, never an alert stream (CLAUDE.md).")
            macro = views.macro_catalog(states)
            st.dataframe(_rows_to_table([{"lead": s["lead"], "display": s.get("display"),
                                          "spawned_at": s.get("spawned_at")} for s in macro])
                         if macro else [{"—": "no off-thesis-real verdicts"}],
                         width="stretch", hide_index=True)

        with st.expander("Manual-resolution queue"):
            st.caption("Tickers awaiting a human EDGAR verification (§2). Resolve with "
                       "`pros identity resolve <ticker> --series-id S######`.")
            st.dataframe(_rows_to_table(queue) if queue else [{"—": "queue empty"}],
                         width="stretch", hide_index=True)

        with st.expander("Run history"):
            st.dataframe(_rows_to_table([
                {"date": r["date"], "run_id": r["run_id"], "pushed": bool(r["pushed"]),
                 "faults": r["fault_count"], "config_hash": r["config_hash"]} for r in runs])
                if runs else [{"—": "no runs recorded"}], width="stretch", hide_index=True)

        with st.expander("Registry health + unknown-type panel"):
            st.write(views.registry_health(states))
            st.caption("Unknown-type panel (empty in v1, built for v2 writers):")
            st.write(views.unknown_type_summary(states)["counts"] or "— none —")

        with st.expander("Per-lead timeline (thaw-backward)"):
            lead_ids = [s["lead"] for s in states]
            if lead_ids:
                chosen = st.selectbox("Lead", lead_ids)
                st.dataframe(_rows_to_table(views.lead_timeline(registry, chosen)),
                             width="stretch", hide_index=True)
            else:
                st.info("No leads yet.")
    finally:
        registry.close()


# `streamlit run` executes this file as `__main__`; the guard also keeps the module importable (a
# smoke test / the firewall grep) without kicking off a render outside a Streamlit runtime.
if __name__ == "__main__":
    main()
