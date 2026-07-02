"""Verdict CLI + identity queue + store repair (spec §8c).

Every surface here is a read of the store except three writers: `pros verdict` (a new verdict
event — a changed mind supersedes via `superseded_by`, never an edit), `pros identity resolve`
(the §2 manual-resolution queue's human path — an EDGAR-verified registry entry plus its
`identity.resolved` and completing `launch` events; it records a human judgment, it computes
nothing) and `pros store reindex` (rebuilds the index from the fossil record; it computes
nothing new, so it is repair, not run-now). Deliberately absent (CLAUDE.md, no-run-now
CONTRACT): no run-now command, no capture trigger, no recompute-on-demand of any kind — the
command tree itself is pinned by test.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import click

from prospector.config import load_config
from prospector.fold.fold import fold, verdict_head_id
from prospector.identity.resolution import ResolutionMachine, VerificationError
from prospector.ingest.edgar import EdgarClient
from prospector.store.envelope import SYSTEM_LEAD
from prospector.store.event_store import EventStore
from prospector.store.fund_registry import FundRegistry, IdentityError
from prospector.store.layout import StoreLayout
from prospector.store.registry import Registry
from prospector.store.reindex import rebuild_registry

_CONFIG_PATH = Path("config") / "prospector.yaml"

_store_option = click.option(
    "--store", "store_path", type=click.Path(), default=None,
    help="Store root (default: store.root from config/prospector.yaml, else ./store).")


def _store_root(store_path: str | None) -> Path:
    """--store wins; else `store.root` from config/prospector.yaml (cwd-relative, like the
    runner); else ./store."""
    if store_path:
        return Path(store_path)
    if _CONFIG_PATH.is_file():
        cfg, _ = load_config(_CONFIG_PATH)
        root = (cfg.get("store") or {}).get("root")
        if root:
            return Path(str(root))
    return Path("store")


def _layout(store_path: str | None) -> StoreLayout:
    try:
        return StoreLayout(_store_root(store_path))
    except ValueError as e:  # e.g. a live root under backtest/ — structural, not a crash
        raise click.ClickException(str(e))


def _open_registry(layout: StoreLayout) -> Registry:
    """For read surfaces: never conjure a store into existence just to look at it."""
    if not layout.registry_path().is_file():
        raise click.ClickException(
            f"no registry at {layout.registry_path()} — is --store right? "
            "(pros store reindex rebuilds it from an existing events/ tree)")
    return Registry(layout.registry_path())


def _cell(value) -> str:
    return "-" if value is None else str(value)


@click.group()
def cli():
    """Project Prospector — proposes reading, never orders."""


# -- store (repair only — never recompute) -------------------------------------

@cli.group("store")
def store_group():
    """Store maintenance."""


@store_group.command("reindex")
@_store_option
def store_reindex(store_path):
    """Rebuild registry.sqlite from the events/ and snapshots/ trees (repair, not run-now)."""
    layout = _layout(store_path)
    registry = Registry(layout.registry_path())
    try:
        counts = rebuild_registry(layout, registry)
    finally:
        registry.close()
    click.echo(f"events_indexed={counts['events_indexed']} "
               f"snapshots_indexed={counts['snapshots_indexed']} "
               f"skipped={counts['skipped']}")


# -- lead (read-only views) -----------------------------------------------------

@cli.group("lead")
def lead_group():
    """Read-only lead views (folds of the event record)."""


@lead_group.command("list")
@_store_option
def lead_list(store_path):
    """One line per lead: lead, display, status, shadow, verdict, latest_z, event_count."""
    layout = _layout(store_path)
    if not layout.registry_path().is_file():
        return  # an empty or absent store simply has nothing to list
    registry = Registry(layout.registry_path())
    try:
        leads = [l for l in registry.all_leads() if l != SYSTEM_LEAD]
        states = [fold(registry.events_for_lead(l)) for l in leads]
    finally:
        registry.close()
    for s in states:
        click.echo("\t".join((
            _cell(s["lead"]), _cell(s["display"]), _cell(s["status"]),
            "shadow" if s["shadow"] else "-", _cell(s["verdict"]),
            _cell(s["latest_z"]), str(s["event_count"]))))


@lead_group.command("show")
@click.argument("lead_id")
@_store_option
def lead_show(lead_id, store_path):
    """The full event timeline (ts, type, payload summary), then the folded state as JSON."""
    layout = _layout(store_path)
    registry = _open_registry(layout)
    try:
        rows = registry.events_for_lead(lead_id)
        if not rows:
            raise click.ClickException(f"unknown lead: {lead_id}")
        for r in rows:
            click.echo(f"{r['ts']}  {r['type']:<20}  {_payload_summary(r['payload'])}")
        state = fold(rows)
    finally:
        registry.close()
    click.echo(json.dumps(state, indent=2, sort_keys=True, default=str))


def _payload_summary(payload_json, width: int = 100) -> str:
    text = " ".join(str(payload_json).split())
    return text if len(text) <= width else text[: width - 1] + "…"


# -- identity (the manual-resolution queue, spec §2/§8c) --------------------------

def _default_client_factory() -> EdgarClient:
    """EdgarClient from config `edgar.user_agent` (SEC 403s undeclared UAs). Tests monkeypatch
    the module attribute `_client_factory` with a fixture-backed factory — an env-var-free
    seam, so CLI construction stays offline under the network guard."""
    cfg = {}
    if _CONFIG_PATH.is_file():
        cfg, _ = load_config(_CONFIG_PATH)
    edgar_cfg = cfg.get("edgar") or {}
    user_agent = edgar_cfg.get("user_agent")
    if not user_agent:
        raise click.ClickException(
            "edgar.user_agent missing from config/prospector.yaml — SEC requires a declared "
            "User-Agent")
    return EdgarClient(str(user_agent),
                       max_per_sec=float(edgar_cfg.get("max_requests_per_sec", 8.0)))


_client_factory = _default_client_factory


@cli.group("identity")
def identity_group():
    """Identity resolution — the retry-then-manual queue (spec §2)."""


@identity_group.command("resolve")
@click.argument("ticker")
@click.option("--series-id", "series_id", required=True,
              help="SEC series id (S######) the human verified for this ticker.")
@click.option("-m", "--note", "note", default=None, help="Optional note on the queue row.")
@_store_option
def identity_resolve(ticker, series_id, note, store_path):
    """Manually resolve a queued ticker to its series id (EDGAR-verified, no bypass)."""
    layout = _layout(store_path)
    registry = _open_registry(layout)
    try:
        event_store = EventStore(layout, registry)
        machine = ResolutionMachine(registry, event_store,
                                    FundRegistry(layout, registry, event_store),
                                    _client_factory())
        try:
            entry = machine.resolve_manual(ticker, series_id, note=note)
        except (IdentityError, VerificationError) as e:
            raise click.ClickException(str(e))
    finally:
        registry.close()
    click.echo(f"{entry.ticker_current} -> {entry.series_id} ({entry.issuer})")


@identity_group.command("queue")
@_store_option
def identity_queue(store_path):
    """The manual-resolution queue: one line per ticker awaiting a human (spec §2)."""
    layout = _layout(store_path)
    if not layout.registry_path().is_file():
        return  # an empty or absent store simply has nothing queued
    registry = Registry(layout.registry_path())
    try:
        # Read surface: EDGAR and the fund registry are never touched, so neither is built.
        machine = ResolutionMachine(registry, EventStore(layout, registry), None, None)
        rows = machine.manual_queue()
    finally:
        registry.close()
    for row in rows:
        click.echo("\t".join((
            row["ticker"], row["first_failed_at"], row["last_attempt_at"],
            str(row["attempts"]), _cell(row["detected_at"]))))


# -- backtest (calibration + the milestone-3 acceptance gate, spec §10 test 5) ------
# Writes ONLY under backtest/ (own store root + registry). Not a run-now surface: it replays
# frozen history for calibration, never recomputes the live record.

@cli.command("backtest")
@click.option("--from", "from_date", required=True, help="Window start (ISO date).")
@click.option("--to", "to_date", required=True, help="Window end (ISO date).")
@click.option("--sweep", is_flag=True, help="Also sweep the (z_in, z_out) grid from config.")
@_store_option
def backtest(from_date, to_date, sweep, store_path):
    """Replay the xcorr sensor over history; write the acceptance report under backtest/."""
    from prospector.backtest import report as report_mod
    from prospector.backtest import runner as runner_mod
    from prospector.backtest.corroboration import load_launches

    cfg, _ = load_config(_CONFIG_PATH)
    root = _store_root(store_path)
    bt = cfg["backtest"]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    result = runner_mod.run(
        root, bt["prices_source"], str(bt["prices_date"]), bt["series_ids_path"],
        cfg, from_date, to_date, stamp)

    # β-strip health + stress diagnostics: the diagnosis that comes BEFORE any threshold tuning
    # (§4a). Recompute the panel/z once and reuse for the sweep too.
    from prospector.ingest.prices import PriceIngest, build_panel
    import warnings
    market = cfg["universe"]["market"]
    tickers = list(cfg["universe"]["sectors"]) + [market]
    ing = PriceIngest(StoreLayout(root))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        panel = build_panel([ing.load_frozen(bt["prices_source"], str(bt["prices_date"]), t)
                             for t in tickers])
        z, stress = runner_mod.compute_z_and_stress(panel, market, cfg)
    beta_strip = runner_mod.beta_strip_health(panel, market, cfg, [
        ("calm 2019-H2", "2019-06-01", "2019-12-31"),
        ("March-2020 crash", "2020-02-20", "2020-04-30"),
        ("2022 rate shock", "2022-01-01", "2022-10-31"),
        ("full window", from_date, to_date)])
    stress_diag = runner_mod.stress_diagnostics(
        z, stress, from_date, to_date, cfg["xcorr"]["stress_corr_threshold"],
        cfg["xcorr"]["z_in"], target_pair=("XLK", "XLU"))

    sweep_results = []
    if sweep:
        pairs_leads = runner_mod._pairs_with_series(
            tickers, runner_mod.load_series_ids(bt["series_ids_path"]))
        grid = [tuple(g) for g in bt["sweep_grid"]]
        sweep_results = runner_mod.sweep(z, stress, pairs_leads, from_date, to_date, grid,
                                         cfg["xcorr"]["stress_corr_threshold"])

    launches = load_launches(bt["launches_path"])
    rep = report_mod.build_report(result, sweep_results, launches,
                                  cfg["sector_keywords"], cfg,
                                  beta_strip=beta_strip, stress_diag=stress_diag)
    jpath, mpath = report_mod.write_report(result.run_root, rep)

    r = rep["recall"]
    p = rep["precision"]["summary"]
    f = rep["falsification"]
    click.echo(f"recall {r['target']}: {'FIRED' if r['fired'] else 'DID NOT FIRE'}")
    click.echo(f"precision: {p['n_structural']}/{p['n_firings']} structural "
               f"({p['structural_fraction']:.1%})")
    click.echo(f"falsification (March 2020): {'PASS' if f['passed'] else 'FAIL'} "
               f"({f['new_leads_spawned_in_window']} spawns in window)")
    if rep["cross_stream_lag"]:
        click.echo(f"lag datum: {rep['cross_stream_lag']['lag_days']} days")
    click.echo(f"artifact: {mpath}")


# -- verdict (the human judgment write path) ---------------------------------------

@cli.command("verdict")
@click.argument("lead_id")
@click.argument("value", type=click.Choice(["yes", "no", "watch"]))
@click.option("-m", "--note", "note", default=None, help="Optional note on the verdict.")
@_store_option
def verdict(lead_id, value, note, store_path):
    """Append a verdict event; a changed mind supersedes the current one, never edits it."""
    layout = _layout(store_path)
    registry = _open_registry(layout)
    try:
        rows = registry.events_for_lead(lead_id)
        if not rows:  # a verdict attaches to an existing record — refuse a typo'd lead id
            raise click.ClickException(f"unknown lead: {lead_id}")
        head = verdict_head_id(fold(rows))
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        written = EventStore(layout, registry).append(
            {"ts": ts, "lead": lead_id, "type": "verdict",
             "payload": {"verdict": value, "note": note, "superseded_by": head},
             "schema": 1})
    finally:
        registry.close()
    click.echo(written.event_id)
