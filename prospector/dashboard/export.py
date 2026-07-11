"""Board-snapshot export — the §8b one-button review artifact (spec §8b/§11).

A PURE serialization layer over the SAME tested view-models the dashboard renders (`dashboard/views.py`):
it produces one self-describing **markdown** board-snapshot the human reads and the review seat parses in
one pass, plus small CSV helpers for the sortable per-panel downloads. NO streamlit import, NO fetch, NO
recompute, NO sensor — unit-tested without a browser, exactly like `views.py`.

CONTRACT (design doc 2026-07-10-8b, §5):
- **Pure export of stored folds — no recompute on export** (the anti-slot-machine rule, extended): reads
  the record the runner already wrote and serializes it; click it a hundred times and get the same document
  but for the export timestamp. A download-all has nothing new to reward re-clicking.
- **Cannot drift from the screen** — it calls the same `views.*` view-models the panels render, never a
  re-query, so the report and the dashboard cannot disagree.
- **Firewall** — reads only this store's own record; never a portfolio / `portfolio.yaml` / trade path.
- **Bounded by the sensor universe** (stays reviewable for years): the active set is <= 55 xcorr pairs +
  <= 11 dispersion baskets, each tick-collapsed; dead/reverted leads accrete in the record forever but
  NEVER in this file — that is what keeps the report bounded as the system runs.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Iterable, Mapping

from prospector.dashboard import views
from prospector.store.layout import ts_compact

# The ONLY silent per-cadence refresh events (fold._apply: they update `latest_z` and nothing in the
# {status, shadow, verdict} trio). A run of these collapses to one line in a timeline; every other
# recognized event is state-relevant and rendered verbatim. Pinned to the fold vocabulary, per the doc.
_SILENT_TICKS = frozenset({"xcorr.tick", "dispersion.tick"})


# --- small render helpers ------------------------------------------------------------------------

def _payload(row: Mapping) -> dict:
    """An event row's payload as a dict (canonical-JSON text from the registry, or an already-dict).
    Mirrors views._payload so the export stays a self-contained pure module."""
    raw = row["payload"]
    if isinstance(raw, Mapping):
        return dict(raw)
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _fmt(v) -> str:
    """A cell value as display text: None -> em-dash, float -> compact, else str."""
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.4g}"
    return str(v)


def _cell(v) -> str:
    """A markdown-table cell: formatted, with pipes/newlines neutralized so a value can't break the row."""
    return _fmt(v).replace("|", "\\|").replace("\n", " ")


def _md_table(headers: list[str], rows: list[list]) -> str:
    """A list-of-rows as a GitHub-flavored markdown table (house style, cf. backtest/report.render_markdown).
    An empty body renders an explicit '(none)' so a section is never a silently-blank block."""
    if not rows:
        return "_(none)_"
    head = "| " + " | ".join(headers) + " |"
    sep = "|" + "|".join(["---"] * len(headers)) + "|"
    body = ["| " + " | ".join(_cell(c) for c in row) + " |" for row in rows]
    return "\n".join([head, sep, *body])


def rows_to_csv(rows: list[dict]) -> str:
    """A list-of-dicts (a panel's rows, exactly as `st.dataframe` renders them) as CSV text with a header
    row — the data for a sortable per-panel download. Column order = the first row's keys."""
    if not rows:
        return ""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()), extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


# --- filenames (self-describing, second-resolution, collision-free across panels) ----------------

def board_snapshot_filename(now: str) -> str:
    """`prospector-board_{YYYYMMDDThhmmssZ}.md` — self-describing + second-resolution."""
    return f"prospector-board_{ts_compact(now)}.md"


def panel_csv_filename(panel: str, now: str) -> str:
    """`{panel}_{YYYYMMDDThhmmssZ}.csv` — the panel name disambiguates same-second downloads across panels
    (the friction the built-in dataframe export, named by time alone, could not)."""
    return f"{panel}_{ts_compact(now)}.csv"


# --- the manifest (the self-describing header — 'what is this file', at the contents level) -------

def _manifest(store_path: str, now: str, runs: list, cs: dict, shadow_count: int, hb: dict) -> str:
    lines = ["# Prospector — board snapshot",
             "",
             "*Read-only fold of the fossil record — proposes reading, never orders. All times UTC.*",
             "",
             f"- **store**: `{store_path}`",
             f"- **exported (UTC)**: {now}"]
    if runs:
        latest = runs[0]
        # config_changed for the latest run = its config hash differs from the PRIOR run's (a config.changed
        # fossil would have been emitted). Derived from the two most-recent rows — no run-log file read.
        if len(runs) >= 2:
            changed = str(latest["config_hash"] != runs[1]["config_hash"]).lower()
        else:
            changed = "n/a (first run)"
        hash_short = (latest["config_hash"] or "—")[:12]
        lines.append(
            f"- **latest run**: `{latest['run_id']}` · {latest['date']} · pushed={bool(latest['pushed'])} · "
            f"faults={latest['fault_count']} · config_hash=`{hash_short}` · config_changed={changed}")
    else:
        lines.append("- **latest run**: — (no runs recorded — the runner has never completed a tick)")
    active_line = f"- **active (live) / ceiling**: {cs['count']} / {cs['ceiling']}"
    if cs["over"]:
        active_line += f" — ⚠ {cs['banner']}"
    lines.append(active_line)
    lines.append(f"- **shadow (dispersion burn-in)**: {shadow_count}")
    hb_state = "OK" if hb["ok"] else f"BROKEN — {hb['reason']}"
    lines.append(f"- **heartbeat**: {hb_state} · last run {hb.get('last_run_date') or '—'}")
    return "\n".join(lines)


# --- the tick-collapsed per-lead timeline --------------------------------------------------------

def _event_detail(typ: str, p: dict) -> str:
    """A compact human suffix for a state-relevant event (the report's per-event legibility)."""
    if typ == "lead.spawned":
        return f"{p.get('spawner') or ''} {p.get('display') or ''}".strip()
    if typ == "xcorr.departure":
        return "market-stress (recorded, no spawn)" if p.get("market_stress") else f"z={_fmt(p.get('z'))}"
    if typ.endswith(".reverted"):
        return "reverted"
    if typ == "verdict":
        return f"verdict={p.get('verdict')}"
    if typ in ("launch", "rebalance", "mandate.changed"):
        return str(p.get("corroboration") or p.get("summary") or typ)
    if typ == "fault":
        return f"{p.get('subsystem')}: {p.get('message')}"
    return str(p.get("display") or p.get("corroboration") or "")


def _timeline_lines(registry, lead: str) -> list[str]:
    """A lead's full event history as markdown bullet lines, in (ts, event_id) order — state-relevant events
    verbatim, but a run of consecutive silent `*.tick`s collapsed to one 'N ticks, first…last, latest z = X'
    line (X = the LAST tick's payload z, so a mid-timeline block is honest, not the final fold latest_z).
    This keeps timelines dense as histories lengthen (the tick stream is the bulk of a long-lived lead)."""
    lines: list[str] = []
    run: list[tuple] = []  # accumulating (ts, z) for consecutive silent ticks

    def flush() -> None:
        if not run:
            return
        n = len(run)
        first_ts, last_ts, last_z = run[0][0], run[-1][0], run[-1][1]
        span = first_ts if n == 1 else f"{first_ts}…{last_ts}"
        lines.append(f"- {n} tick{'' if n == 1 else 's'}, {span}, latest z = {_fmt(last_z)}")
        run.clear()

    for r in registry.events_for_lead(lead):
        typ = r["type"]
        if typ in _SILENT_TICKS:
            run.append((r["ts"], _payload(r).get("z")))
            continue
        flush()
        detail = _event_detail(typ, _payload(r))
        lines.append(f"- {r['ts']} · `{typ}`" + (f" · {detail}" if detail else ""))
    flush()
    return lines


# --- the board snapshot ---------------------------------------------------------------------------

def board_snapshot_markdown(registry, states: Iterable[dict], runs, machine, cfg: dict, now: str,
                            store_path: str) -> str:
    """The whole live board as one self-describing markdown document: a manifest header + the summary
    panels + the tick-collapsed timeline of every ACTIVE lead (non-shadow AND shadow — burn-in timelines
    are review material). Serializes the SAME `views.*` view-models the screen renders, so it cannot drift;
    reads only the stored record (no fetch, no recompute). `runs` is `recent_runs(registry)` (newest
    first); `machine` is the read-only ResolutionMachine (for the manual queue)."""
    states = list(states)
    runs = list(runs)
    ceiling = int((cfg.get("oracle") or {}).get("active_lead_ceiling", 8))
    shadow_days = int((cfg.get("dispersion") or {}).get("shadow_days", 90))

    cs = views.ceiling_status(states, ceiling)
    hb = views.heartbeat(runs, now)
    shadow = views.shadow_panel(states, now, shadow_days)

    parts: list[str] = [_manifest(store_path, now, runs, cs, len(shadow), hb), ""]

    # 1. Active leads (live, non-shadow) — the ranked firings.
    ranked = views.rank_active_leads(states)
    parts += ["## Active leads (live)",
              _md_table(["lead", "display", "spawner", "latest_z", "spawned_at", "verdict", "events"],
                        [[s["lead"], s.get("display"), s.get("spawner"), s.get("latest_z"),
                          s.get("spawned_at"), s.get("verdict"), s.get("event_count")] for s in ranked]),
              ""]

    # 2. Dispersion shadow / burn-in.
    parts += ["## Dispersion shadow (burn-in)",
              _md_table(["lead", "display", "z", "elapsed_days", "target_days", "burn_in_complete"],
                        [[s["lead"], s.get("display"), s.get("latest_z"), s["shadow_days_elapsed"],
                          s["shadow_days_target"], s["burn_in_complete"]] for s in shadow]),
              ""]

    # 3. Health — heartbeat (in the manifest) + the fault log.
    faults = views.fault_log(registry)
    parts += ["## Health · fault log",
              _md_table(["ts", "lead", "category", "subsystem", "message"],
                        [[f["ts"], f["lead"], f.get("category"), f.get("subsystem"), f.get("message")]
                         for f in faults]),
              ""]

    # 4. Run history.
    parts += ["## Run history",
              _md_table(["date", "run_id", "pushed", "faults", "config_hash"],
                        [[r["date"], r["run_id"], bool(r["pushed"]), r["fault_count"], r["config_hash"]]
                         for r in runs]),
              ""]

    # 5. Coverage / dormant pile + launches.
    pile = views.dormant_pile(registry)
    parts += ["## Coverage / dormant pile",
              _md_table(["disposition", "count"], [[d, pile["counts"][d]] for d in pile["ranked"]]),
              ""]
    launches = views.launch_panel(registry)
    parts += ["## Launches (survey)",
              _md_table(["ts", "ticker", "series_id", "detected_at"],
                        [[l["ts"], l.get("ticker"), l.get("series_id"), l.get("detected_at")]
                         for l in launches])]
    unlisted = views.unlisted_launch_count(registry)
    if unlisted:  # keep the no-ticker detections a VISIBLE coverage fact, not a silently-dropped blind spot
        parts.append(f"\n_{unlisted} unlisted (no-ticker) detection{'' if unlisted == 1 else 's'} kept in "
                     "the record, omitted from this listed-launch survey._")
    parts.append("")

    # 6. Manual-resolution queue — only when non-empty.
    queue = views.manual_queue(machine)
    if queue:
        parts += ["## Manual-resolution queue",
                  _md_table(["ticker", "first_failed_at", "last_attempt_at", "attempts", "detected_at"],
                            [[q["ticker"], q["first_failed_at"], q["last_attempt_at"], q["attempts"],
                              q["detected_at"]] for q in queue]),
                  ""]

    # 7. Registry health.
    h = views.registry_health(states)
    parts += ["## Registry health",
              "\n".join(f"- **{k}**: {v}" for k, v in h.items()),
              ""]

    # 8. Active-lead timelines — EVERY active lead (non-shadow AND shadow), tick-collapsed. Reverted
    #    leads are deliberately absent (that is the bound that keeps this file reviewable for years).
    active = sorted((s for s in states if s.get("status") == "active"),
                    key=lambda s: (s.get("spawned_at") or ""), reverse=True)
    parts.append("## Active-lead timelines")
    if not active:
        parts += ["_(no active leads)_", ""]
    for s in active:
        tag = "shadow" if s.get("shadow") else "live"
        parts.append(f"### {s['lead']} · {s.get('display') or '—'} · {tag}")
        parts += _timeline_lines(registry, s["lead"])
        parts.append("")

    return "\n".join(parts).rstrip() + "\n"
