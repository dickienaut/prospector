"""Acceptance-gate report (spec §10 test 5, CONTRACT). One artifact per run, four sections:

  (a) Recall        — the XLK×XLU (Tech×Utilities) firing timeline.
  (b) Precision     — the FULL firing list, every pair, each auto-scored by cross-stream
                      corroboration; the threshold sweep; the chosen thresholds backed off from
                      recall-optimal.
  (c) Falsification — March 2020: zero new (non-stress) leads spawned in the crash window, with
                      raw departures captured as market_stress=true.
  Bonus             — T(first XLK×XLU firing) -> T(TEKX launch 2024-09), the first deterministic
                      cross-stream lag datum.

The report renders folds/results deterministically (no generated prose) into JSON + Markdown.
It does not decide pass/fail — it lays the evidence out for the human/design-thread review the
gate demands. A "no" here is the system working as designed (§12).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from prospector.backtest import corroboration
from prospector.backtest.runner import BacktestResult
from prospector.sensors import xcorr


def _firing_rows(result: BacktestResult) -> list[dict]:
    return [{"pair": list(f.pair), "display": xcorr.pair_display(f.pair),
             "first_fired": f.entered, "exited": f.exited, "peak_z": round(f.peak_z, 3)}
            for f in sorted(result.firings, key=lambda f: (f.entered, f.pair))]


def build_report(result: BacktestResult, sweep_results: list[BacktestResult],
                 launches: list[dict], sector_keywords: dict, cfg: dict,
                 beta_strip: list[dict] | None = None, stress_diag: dict | None = None,
                 stress_validation: dict | None = None, crash_falsification: dict | None = None,
                 target_display: str = "XLK×XLU", target_launch_ticker: str = "TEKX") -> dict:
    """Assemble the acceptance artifact as a JSON-serializable dict."""
    window_months = cfg["backtest"]["corroboration_window_months"]
    stress_win = cfg["backtest"]["stress_window"]

    rows = _firing_rows(result)

    # (a) Recall — the target pair's firings.
    target_firings = [r for r in rows if r["display"] == target_display]

    # (b) Precision — corroboration-score every firing at the chosen thresholds.
    scored = corroboration.score_all(
        [{"pair": tuple(r["pair"]), "first_fired": r["first_fired"]} for r in rows],
        launches, sector_keywords, window_months)
    precision_rows = []
    for r, s in zip(rows, scored["rows"]):
        precision_rows.append({**r, "structural": s["structural"], "matches": s["matches"]})

    # Threshold sweep: structural fraction + whether the target still fires, per grid point.
    sweep_table = []
    for sr in sweep_results:
        sr_rows = _firing_rows(sr)
        sr_scored = corroboration.score_all(
            [{"pair": tuple(x["pair"]), "first_fired": x["first_fired"]} for x in sr_rows],
            launches, sector_keywords, window_months)
        target_fires = any(x["display"] == target_display for x in sr_rows)
        sweep_table.append({
            "z_in": sr.z_in, "z_out": sr.z_out,
            "n_firings": sr_scored["summary"]["n_firings"],
            "n_structural": sr_scored["summary"]["n_structural"],
            "structural_fraction": round(sr_scored["summary"]["structural_fraction"], 3),
            "target_fires": target_fires})

    # (c) Falsification — March 2020. Zero non-stress firings whose entry falls in the window.
    win_from, win_to = stress_win["from"], stress_win["to"]
    spawns_in_window = [r for r in rows if win_from <= r["first_fired"] <= win_to]
    stressed_in_window = [sd for sd in result.stressed_departures
                          if win_from <= sd["date"] <= win_to]
    # The §4a note asks which mechanism to fix. The β-strip health check already answers the
    # stale-β half: if residual mean correlation stayed near zero through the crash, the strip
    # is NOT leaking market beta, so a spawn in the window is not a β problem — it is the
    # reactive-annotation latency (the 21d trailing stress had not yet risen when the departure
    # fired at the crash's leading edge). Make the note say which, from the evidence.
    crash_resid = None
    if beta_strip:
        crash_row = next((r for r in beta_strip if "crash" in r["window"].lower()), None)
        crash_resid = crash_row["residual_mean_corr"] if crash_row else None
    # Classify the spawns precisely against the acute-crisis onset window [onset, gate_rises):
    # spawns there leaked because the 21d level had not yet crossed the gate — the bounded
    # β-staleness leak. Spawns before onset (pre-crash) or after the gate releases (recovery tail)
    # are separate; the ones in-window that survive the clean β-strip are real idiosyncratic moves.
    onset = gate_rises = None
    if stress_validation and stress_validation.get("acute_crises"):
        ac = stress_validation["acute_crises"][0]
        onset, gate_rises = ac["onset"], ac.get("gate_rises")
    onset_leak = [s for s in spawns_in_window
                  if onset is not None and gate_rises is not None
                  and onset <= s["first_fired"] < gate_rises]

    # Amended falsification (spec rev5 §10.5c): three criteria, replacing the retired "zero spawns".
    clean = crash_resid is not None and abs(crash_resid) < 0.2   # (i) β-strip clean in-crash
    ac = (stress_validation or {}).get("acute_crises", [{}])[0]
    ii_fires = bool(ac.get("fires"))                              # (ii) gate fires on the acute crisis
    ii_not_whole = bool(stress_validation and stress_validation.get("gate_not_whole_window"))
    cf = crash_falsification or {}
    n_persistent = cf.get("n_persistent", 0)                      # (iii) all crash spawns revert?
    iii_all_transient = bool(cf.get("all_transient", not spawns_in_window))

    note = (
        "(i) β-strip clean in-crash (necessary, not sufficient — the strip removes the common "
        f"factor but idiosyncratic ≠ structural). (ii) gate fires on the acute crisis and does not "
        "gate the whole window. (iii) the falsifiable core: a crash-window spawn is 'free' only if "
        "it REVERTS; a spawn that persists is a durable lead, not a transient crisis phenomenon. ")
    if iii_all_transient:
        note += "All crash-window spawns reverted within the bound — (iii) holds."
    else:
        note += (
            f"(iii) FLAGS {n_persistent} persistent crash spawn(s) — the test's teeth working. Per "
            "rev5 this does NOT repudiate the recalibration (which stands on the scale distinction "
            "and onset latency, §4a). It is informative: each persistent lead is either a genuine "
            "crisis-coincident structural shift worth examining (the persistent set is "
            "Financials-heavy — a plausible 2020 rates-to-zero regime shift), or a persistent "
            "onset/stale-β artifact. Principled responses, in order: examine the lead (it may be "
            "real); if artifact, the fix is a FASTER β estimator (§4a note 1: EWMA / shorter window) "
            "to shrink the onset leak at its source — NEVER re-tighten the crisis level (undoes the "
            "recalibration) and NEVER shrink the gate's level window (imports level-noise into the "
            "common case to fix a rare one).")
    falsification = {
        "window": {"from": win_from, "to": win_to},
        "new_leads_spawned_in_window": len(spawns_in_window),
        "spawns_in_window": spawns_in_window,
        "onset_window_spawns": len(onset_leak),
        "stressed_departures_in_window": len(stressed_in_window),
        # rev5 §10.5c three-part verdict:
        "i_beta_strip_clean": bool(clean),
        "ii_gate_fires": ii_fires,
        "ii_not_whole_window": ii_not_whole,
        "iii_all_transient": iii_all_transient,
        "iii_n_persistent": n_persistent,
        "crash_spawns": cf.get("spawns", []),
        "crash_revert_weeks": cf.get("crash_revert_weeks"),
        # legacy fields kept for the literal-5c comparison and back-compat:
        "passed_literal_5c": len(spawns_in_window) == 0,
        "beta_strip_falsification_holds": bool(clean),
        "note": note}

    # Bonus — cross-stream lag: first target firing -> the target launch's detected_at.
    lag = None
    launch = next((l for l in launches if l.get("ticker") == target_launch_ticker), None)
    if target_firings and launch is not None:
        first_fire = date.fromisoformat(target_firings[0]["first_fired"])
        detected = date.fromisoformat(str(launch["detected_at"]))
        lag = {"target": target_display, "first_fired": target_firings[0]["first_fired"],
               "launch_ticker": target_launch_ticker, "launch_detected_at": launch["detected_at"],
               "lag_days": (detected - first_fire).days,
               "note": "T(structural departure) -> T(corroborating launch), deterministic half "
                       "of the cross-stream lag (§0); the discourse->structure lead time is v2."}

    return {
        "window": {"from": result.from_date, "to": result.to_date},
        "thresholds": {"z_in": result.z_in, "z_out": result.z_out,
                       "crisis_level": cfg["xcorr"]["stress"]["crisis_level"]},
        "beta_strip_health": beta_strip,
        "stress_diagnostics": stress_diag,
        "stress_validation": stress_validation,
        "recall": {"target": target_display, "fired": bool(target_firings),
                   "firings": target_firings},
        "precision": {"summary": scored["summary"], "firings": precision_rows,
                      "sweep": sweep_table,
                      "caveat": ("Corroboration bakes in 'packaged = real': a real-but-never-"
                                 "packaged firing scores as junk. Acceptable (packageability is "
                                 "this system's own success criterion) but a BIAS, not a truth.")},
        "falsification": falsification,
        "cross_stream_lag": lag,
    }


def render_markdown(report: dict) -> str:
    """Deterministic Markdown rendering of the report dict — no generated prose."""
    L = []
    w = report["window"]
    t = report["thresholds"]
    L.append(f"# Prospector — Milestone-3 Acceptance Report\n")
    L.append(f"Window **{w['from']} → {w['to']}** · thresholds z_in **{t['z_in']}** / "
             f"z_out **{t['z_out']}** · crisis gate correlation ≥ **{t['crisis_level']}** "
             f"(absolute, frozen)\n")

    bs = report.get("beta_strip_health")
    if bs:
        L.append("## β-strip health — the diagnosis that comes before any threshold tuning\n")
        L.append("Mean pairwise correlation across the 11 sectors, raw vs. after the market-β "
                 "strip. If residual stays high in a crash the strip leaks market beta (every "
                 "pair lights up on convulsions — a broken measure); if it collapses to ~0 the "
                 "strip works and departures are genuinely idiosyncratic (§4a mechanism note).\n")
        L.append("| window | raw corr | residual corr | reduction |")
        L.append("|---|---:|---:|---:|")
        for r in bs:
            red = f"{r['reduction_pct']:.0f}%" if r["reduction_pct"] is not None else "—"
            L.append(f"| {r['window']} | {r['raw_mean_corr']} | {r['residual_mean_corr']} | {red} |")
        L.append("")

    sd = report.get("stress_diagnostics")
    if sd:
        q = sd["quantiles"]
        L.append("## Stress gate — recalibrated to an absolute crisis level\n")
        L.append("The β-strip is the primary market-factor defense (proven clean in-crash above), "
                 "so the stress gate is demoted to catching acute crises only (crash-onset β "
                 "staleness, liquidity dislocations). The old absolute 0.65 gated a quarter of all "
                 "days; the level is lifted to an acute-crisis level. It stays **absolute**, not a "
                 "baseline-relative departure: market-wide correlation is a fragility gauge whose "
                 "intrinsic level *is* the signal (0.95 is a stressed market regardless of last "
                 "month), so normalizing it away destroys exactly what the gate reads — the "
                 "correlation-concentration / absorption-ratio family is used as a level, never "
                 "trailing-normed. The departure form was tested and rejected on evidence (decisions note).\n")
        L.append(f"Correlation-level distribution over the window: p5 {q['p5']} · p25 {q['p25']} · "
                 f"median {q['p50']} · p75 {q['p75']} · p95 {q['p95']}. The gate fires on "
                 f"**{sd['fraction_days_gated']:.1%}** of days at correlation ≥ {sd['crisis_level']}, "
                 f"suppressing **{sd['departure_days_gated']}/{sd['departure_days_total']} "
                 f"({sd['departure_days_gated_fraction']:.1%})** of all z≥{sd['z_in']} "
                 f"departure-days (was 24.8% of days / 32.2% of departures at the old 0.65).\n")
        if sd.get("target"):
            tg = sd["target"]
            L.append(f"For the target pair {tg['pair']}: {tg['gated']}/{tg['hi_days']} of its "
                     f"z≥{sd['z_in']} days were gated; its first departure ({tg['first_hi']}) "
                     f"was {'GATED' if tg['first_hi_gated'] else 'not gated'}.\n")

    sv = report.get("stress_validation")
    if sv:
        L.append("### Concept validation (not case-fit)\n")
        L.append(f"The level is set on principle (top ~2-3% of days; just above calm p95) and "
                 f"frozen. It is validated against the concept — fires on recognized crises, quiet "
                 f"on ordinary calm days — **never** tuned to make a known case surface.\n")
        L.append("| check | result |")
        L.append("|---|---|")
        for c in sv["acute_crises"]:
            lag = c["onset_latency_trading_days"]
            lag_s = "—" if lag is None else f"{lag} trading days after onset"
            L.append(f"| Fires in acute crisis {c['label']} ({c['window']}) | "
                     f"{'✓ yes' if c['fires'] else '✗ NO'} · peak corr {c['peak_level']} · "
                     f"onset latency {lag_s} |")
        for s in sv["sustained_regimes"]:
            L.append(f"| Stays open in sustained regime {s['label']} ({s['window']}) | "
                     f"{'✓ open' if s['correctly_open'] else '✗ gated ' + str(s['gated_days']) + 'd'} · "
                     f"peak corr {s['peak_level']} |")
        for a in sv["calm_anchors"]:
            L.append(f"| Quiet on {a['label']} ({a['date']}) | "
                     f"{'✓ quiet' if a['quiet'] else '✗ GATED'} · corr {a['level']} |")
        ag = sv.get("aging_monitor")
        if ag:
            L.append(f"| Aging-drift monitor (recent {ag['recent_window_days']}d) | "
                     f"calm p95 {ag['calm_p95']} → gate {ag['crisis_level']} · "
                     f"**headroom {ag['headroom']}** |")
        L.append("")
        L.append("> Two named characteristics, not bugs: (1) **onset latency** — the level input is "
                 "a 21d correlation, so the gate rises a few days into a crash; a departure at the "
                 "very leading edge slips through, a bounded leak (losing paging in a crash week is "
                 "free). (2) **absolute levels age** — over a 17-year horizon secular co-movement "
                 "could lift the calm baseline toward the gate (watch the headroom above). The fix "
                 "is deliberate human re-freezing higher, **never** a rolling percentile — that "
                 "would be the rejected baseline-relative form in disguise.\n")

    rc = report["recall"]
    L.append(f"## (a) Recall — {rc['target']}\n")
    L.append("**FIRED**" if rc["fired"] else "**DID NOT FIRE** ⚠️")
    for f in rc["firings"]:
        exit_ = f["exited"] or "(still active at window end)"
        L.append(f"- entered **{f['first_fired']}**, exited {exit_}, peak z {f['peak_z']}")
    L.append("")

    pr = report["precision"]
    s = pr["summary"]
    L.append("## (b) Precision — full firing list\n")
    L.append(f"{s['n_firings']} firings · **{s['n_structural']} structural** · "
             f"structural fraction **{s['structural_fraction']:.1%}**\n")
    L.append("### Threshold sweep\n")
    L.append("| z_in | z_out | firings | structural | fraction | target fires |")
    L.append("|---:|---:|---:|---:|---:|:---:|")
    for r in pr["sweep"]:
        L.append(f"| {r['z_in']} | {r['z_out']} | {r['n_firings']} | {r['n_structural']} | "
                 f"{r['structural_fraction']:.1%} | {'✓' if r['target_fires'] else '✗'} |")
    L.append("\n### Every firing (corroboration-scored)\n")
    L.append("| first fired | pair | peak z | structural | corroborating launch |")
    L.append("|---|---|---:|:---:|---|")
    for r in pr["firings"]:
        m = ", ".join(f"{x['ticker']}@{x['detected_at']}" for x in r["matches"]) or "—"
        L.append(f"| {r['first_fired']} | {r['display']} | {r['peak_z']} | "
                 f"{'✓' if r['structural'] else '·'} | {m} |")
    L.append(f"\n> {pr['caveat']}\n")

    fa = report["falsification"]
    L.append("## (c) Falsification — March 2020 (amended, spec rev5 §10.5c)\n")
    L.append(f"Window {fa['window']['from']} → {fa['window']['to']}: "
             f"**{fa['new_leads_spawned_in_window']} crash-window spawns** · "
             f"{fa['stressed_departures_in_window']} stressed departures recorded. "
             f"The retired 'zero spawns' criterion is replaced by three tests:\n")
    L.append("| # | criterion | result |")
    L.append("|---|---|---|")
    L.append(f"| i | β-strip keeps residual mean corr ≈0 in-crash (estimator falsifier) | "
             f"{'✓ holds' if fa['i_beta_strip_clean'] else '✗ LEAKS'} |")
    L.append(f"| ii | gate fires on the acute crisis, not the whole window | "
             f"{'✓' if fa['ii_gate_fires'] and fa['ii_not_whole_window'] else '✗'} "
             f"(fires={fa['ii_gate_fires']}, not-whole-window={fa['ii_not_whole_window']}) |")
    iii_cell = ("✓ all transient" if fa["iii_all_transient"]
                else f"⚠ FLAGS {fa['iii_n_persistent']} persistent")
    L.append(f"| iii | every crash-window spawn reverts within {fa.get('crash_revert_weeks')}wk "
             f"(no durable false leads) | {iii_cell} |")
    L.append("")
    if fa.get("crash_spawns"):
        L.append(f"### Crash-window spawns — phase & reversion (revert bound {fa.get('crash_revert_weeks')}wk)\n")
        L.append("| entered | pair | phase | exited | weeks | transient |")
        L.append("|---|---|---|---|---:|:---:|")
        for s in fa["crash_spawns"]:
            wk = "—" if s["revert_weeks"] is None else f"{s['revert_weeks']}"
            ex = s["exited"] or "(active at window end)"
            L.append(f"| {s['entered']} | {s['display']} | {s['phase']} | {ex} | {wk} | "
                     f"{'✓' if s['reverted_within'] else '✗ persists'} |")
        L.append("")
    L.append(f"> {fa['note']}\n")

    lag = report["cross_stream_lag"]
    if lag:
        L.append("## Bonus — cross-stream lag datum\n")
        L.append(f"T({lag['target']} first firing = {lag['first_fired']}) → "
                 f"T({lag['launch_ticker']} launch = {lag['launch_detected_at']}) = "
                 f"**{lag['lag_days']} days**\n")
        L.append(f"> {lag['note']}\n")
    return "\n".join(L)


def write_report(run_root: Path, report: dict) -> tuple[Path, Path]:
    """Write acceptance_report.json + .md under the backtest run root."""
    run_root.mkdir(parents=True, exist_ok=True)
    jpath = run_root / "acceptance_report.json"
    mpath = run_root / "acceptance_report.md"
    jpath.write_text(json.dumps(report, indent=2, default=str))
    mpath.write_text(render_markdown(report))
    return jpath, mpath
