"""Verdict CLI + identity queue + store repair + the cadence runner (spec §8c/§9).

Every surface here is a read of the store except four writers: `pros verdict` (a new verdict
event — a changed mind supersedes via `superseded_by`, never an edit), `pros identity resolve`
(the §2 manual-resolution queue's human path — an EDGAR-verified registry entry plus its
`identity.resolved` and completing `launch` events; it records a human judgment, it computes
nothing), `pros store reindex` (rebuilds the index from the fossil record; it computes nothing
new, so it is repair, not run-now), and `pros run` (one §9 cadence tick — the heaviest writer,
but cron invokes it; it is NOT an on-demand recompute). (`pros backtest` also writes, but only
to its own separate `backtest/` store, never the live record.) Deliberately absent (CLAUDE.md,
no-run-now CONTRACT): no run-now command, no capture trigger, no recompute-on-demand of any
kind — the command tree itself is pinned by test.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import click

from prospector.config import load_config
from prospector.fold.fold import VERDICT_VOCAB, fold, verdict_head_id
from prospector.identity.resolution import ResolutionMachine, VerificationError
from prospector.ingest.edgar import EdgarClient
from prospector.store.envelope import SYSTEM_LEAD
from prospector.store.event_store import EventStore
from prospector.store.fund_registry import FundRegistry, IdentityError
from prospector.store.backup import (DEFAULT_MARKER, BackupError, backup_store,
                                     verify_restore)
from prospector.store.layout import StoreLayout
from prospector.store.registry import Registry
from prospector.store.reindex import rebuild_registry

_CONFIG_PATH = Path("config") / "prospector.yaml"


def _load_dotenv(path: Path = Path(".env")) -> None:
    """Populate os.environ from a repo-root .env (git-ignored) if present — a tiny zero-dependency
    reader so a `TIINGO_API_TOKEN` set in .env reaches `pros run` without a shell export. Skips
    blank/`#` lines, strips an optional `export ` and surrounding quotes, and uses setdefault so an
    already-exported value wins. No-op if .env is absent. This is the ONLY place a secret enters the
    process env; the token is never read into config (it rides the Authorization header, §prices)."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


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


@store_group.command("verify-restore")
@click.argument("backup_dir", type=click.Path(exists=True, file_okay=False))
def store_verify_restore(backup_dir):
    """Prove a backup RESTORES (a backup you've never restored from is a hope). Rebuilds a throwaway
    store from the backup's fossils and prints the counts to spot-check against the live store. A read
    of a backup dir — it writes nothing to the live store."""
    counts = verify_restore(Path(backup_dir))
    click.echo(f"restored from {backup_dir}: leads={counts['leads']} "
               f"events={counts['events_indexed']} snapshots={counts['snapshots_indexed']} "
               f"fund_objects={counts['fund_objects']} skipped={counts['skipped']}")
    click.echo("spot-check: compare these to the live store (`pros lead list` / `pros store reindex`)")


@store_group.command("lock-path")
@_store_option
def store_lock_path(store_path):
    """Print the single-writer lock file path (`<store.root>/run.lock`) — the path the runner and the deploy
    coordination both use, derived from config the runtime's way (never hardcoded). A pure read."""
    from prospector.store.run_lock import run_lock_path
    layout = _layout(store_path)
    click.echo(run_lock_path(layout.root))


@store_group.command("lock-run", context_settings=dict(ignore_unknown_options=True))
@_store_option
@click.argument("command", nargs=-1, type=click.UNPROCESSED, required=True)
def store_lock_run(store_path, command):
    """Acquire the single-writer lock, run COMMAND while holding it, release on exit (M7-04). The runtime's
    OWN flock (`prospector.store.run_lock`) — macOS-portable, since the shell `flock(1)` util does not exist
    on macOS — so `deploy.sh` takes the SAME lock the runner holds and never swaps code/deps under an
    in-flight tick. On contention: refuse with exit code 75 (EX_TEMPFAIL, 'a tick is in flight — retry');
    otherwise propagate COMMAND's own exit code.  Usage:  pros store lock-run -- <command> [args...]"""
    import subprocess

    from prospector.store.run_lock import RunLockHeld, acquire
    layout = _layout(store_path)
    try:
        lock = acquire(layout.root)
    except RunLockHeld as e:
        click.echo(f"REFUSED: {e}", err=True)
        raise SystemExit(75)  # EX_TEMPFAIL — a tick is in flight; the caller (deploy.sh) retries
    try:
        completed = subprocess.run(list(command))
    finally:
        lock.release()
    raise SystemExit(completed.returncode)


# -- backup (fossil-store durability — a READ of the store, never run-now) -----


@cli.command("backup")
@_store_option
def backup_cmd(store_path):
    """Mirror the append-only fossil store + a WAL-safe registry snapshot to the configured HDD
    targets (backup.targets), incrementally. Fail-loud (non-zero exit) on an unmounted/unblessed
    target. A READ of the store — never a write to it, never near execution (the firewall and the
    read-only posture hold; like `store reindex`, it computes nothing new, so it is not run-now)."""
    layout = _layout(store_path)
    if not layout.root.is_dir():
        raise click.ClickException(f"no store at {layout.root} — nothing to back up")
    cfg, _ = load_config(_CONFIG_PATH)
    bcfg = cfg.get("backup") or {}
    # M7-02: stamp each verified-success target with this UTC time so the runner can fold `backup.stale`
    # into the §8a heartbeat's health channel (decision 2026-07-14-backup-health-one-fault-channel.md).
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    try:
        report = backup_store(layout, bcfg.get("targets") or [],
                              marker=bcfg.get("marker") or DEFAULT_MARKER, now=now)
    except BackupError as e:
        raise click.ClickException(str(e))
    for r in report.targets:
        click.echo(f"{r.target}: copied={r.files_copied} skipped={r.files_skipped} "
                   f"bytes={r.bytes_copied} registry={'ok' if r.registry_backed_up else 'absent'}")
    for target, reason in report.failures:
        click.echo(f"FAULT {target}: {reason}", err=True)
    if report.failures:
        total = len(report.failures) + len(report.targets)
        raise click.ClickException(
            f"{len(report.failures)} of {total} backup target(s) FAILED — "
            "the record is NOT fully backed up")


# -- run (the M5 cadence entrypoint — NOT a run-now surface, spec §9) --------------

@cli.command("run")
@_store_option
@click.option("--heartbeat", "--weekly", "heartbeat", is_flag=True, default=False,
              help="Also send the §8a WEEKLY heartbeat/dead-man email this tick (the scheduler runs "
                   "`pros run --heartbeat` weekly; the dead-man's silence=broken guarantee arms at M7).")
def run(store_path, heartbeat):
    """Execute ONE cadence tick: config honesty -> ingest -> sensors -> identity retries ->
    snapshots -> push-on-state-change (spec §9). This is the scheduled ENTRYPOINT — cron/EventBridge
    invokes it (scheduling itself is milestone 7). It is NOT a run-now surface: one invocation is one
    tick, it records on cadence and pushes on state change, and there is deliberately no flag to
    recompute or capture on demand (CLAUDE.md, no-run-now CONTRACT). The runner adds no intelligence;
    it sequences the deterministic sensors and never touches a trade path (firewall CONTRACT).

    `--heartbeat` additionally fires the §8a weekly heartbeat email (fires regardless of activity — the
    dead-man). It rides the tick (not a separate read-only send) so a heartbeat email proves the WHOLE
    pipeline ran; M7's scheduler calls it weekly. Email is sent only when `email.smtp_host` is configured
    AND `PROSPECTOR_SMTP_PASSWORD` is set; otherwise the run proceeds with a NullNotifier (records intent,
    sends nothing) so an un-configured/offline local run still works."""
    import time
    from uuid import uuid4

    from prospector.ingest.capture import CaptureProvider
    from prospector.ingest.holdings import HoldingsIngest
    from prospector.ingest.prices import PriceIngest
    from prospector.primitives.atomic import write_atomic
    from prospector.runner import RunnerDeps, run_tick
    from prospector.runner.notify import NullNotifier, SmtpNotifier, smtp_config

    _load_dotenv()  # pick up TIINGO_API_TOKEN from a git-ignored .env before we read the env below
    layout = _layout(store_path)  # a writer: Registry() below creates the store if absent
    cfg, cfg_hash = load_config(_CONFIG_PATH)
    edgar_cfg = cfg.get("edgar") or {}
    user_agent = edgar_cfg.get("user_agent")
    if not user_agent:
        raise click.ClickException(
            "edgar.user_agent missing from config/prospector.yaml — SEC requires a declared "
            "User-Agent")
    # Tiingo secret from the env (never config). Fail FAST here if the live source needs it and it's
    # unset: the runner treats a per-ticker fetch failure as a SOFT fault, so a missing token would
    # silently empty the whole panel (12 tickers) rather than tell the operator what's wrong.
    source = (cfg.get("prices") or {}).get("primary", "yahoo")
    api_token = os.environ.get("TIINGO_API_TOKEN")
    if source == "tiingo" and not api_token:
        raise click.ClickException(
            "TIINGO_API_TOKEN unset but prices.primary is tiingo — set it in .env or the environment "
            "(it rides the Authorization header; never put a token in config).")
    # §10 email sender. The SMTP app-password is a SECRET — env-only (PROSPECTOR_SMTP_PASSWORD from the
    # git-ignored .env), exactly like the Tiingo token, never in config. Fail FAST if email is configured
    # (email.smtp_host set) but the password is unset: a silent no-send would defeat the dead-man. When
    # email is NOT configured, fall back to NullNotifier so an offline/local `pros run` still works.
    smtp = smtp_config(cfg)
    if smtp is not None:
        smtp_password = os.environ.get("PROSPECTOR_SMTP_PASSWORD")
        if not smtp_password:
            raise click.ClickException(
                "email.smtp_host is set but PROSPECTOR_SMTP_PASSWORD is unset — set the app-password in "
                ".env or the environment (it is a secret; never put it in config). Unset email.smtp_host "
                "to run without email.")
        notifier = SmtpNotifier(password=smtp_password, **smtp)
    else:
        notifier = NullNotifier()
        if heartbeat:  # asked for a heartbeat but nowhere to send it — say so, don't fail the tick
            click.echo("note: --heartbeat set but email.smtp_host is unconfigured — no email sent "
                       "(NullNotifier). Configure email.* + PROSPECTOR_SMTP_PASSWORD to enable.")
    # §6 M6 discourse capture. ANTHROPIC_API_KEY is a SECRET — env-only (from the git-ignored .env),
    # exactly like the Tiingo/SMTP secrets, never in config. Capture is ENABLED only when
    # capture.monthly_budget_usd is set (null = disabled — the shipped default). Fail FAST if capture is
    # enabled but the key is unset: a silent no-capture would quietly drop the one dataset that cannot be
    # backfilled. When capture is disabled, the provider stays None and the runner's capture phase no-ops.
    capture_cfg = cfg.get("capture") or {}
    capture_provider = None
    if capture_cfg.get("monthly_budget_usd") is not None:
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
        if not anthropic_key:
            raise click.ClickException(
                "capture.monthly_budget_usd is set (capture enabled) but ANTHROPIC_API_KEY is unset — set "
                "it in .env or the environment (it is a secret; never put it in config). Set "
                "capture.monthly_budget_usd: null to disable capture.")
        capture_provider = CaptureProvider(anthropic_key,
                                           model=str(capture_cfg.get("model", "claude-haiku-4-5")),
                                           edgar_user_agent=str(user_agent))  # SEC identity for sec.gov fetches
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    tick_date = now[:10]

    # M7-04/M7-06 SINGLE-WRITER LOCK — AFTER config validation (a misconfigured run fails fast and touches
    # nothing), BEFORE the registry opens or any fossil is written. A second tick (the scheduled fire OR a
    # manual `pros run` in another shell) refuses HERE and exits nonzero, writing no fossils and paging no
    # one (the legit tick is running; the duplicate is prevented noise). Held in a local for the whole tick
    # — released when `run` returns/unwinds (WriterLock.__del__) and, belt, on process death (flock), so a
    # crash or `kickstart -k` never leaves a stale lock. See prospector/store/run_lock.py.
    from prospector.store.run_lock import RunLockHeld, acquire as _acquire_writer_lock
    try:
        _writer_lock = _acquire_writer_lock(layout.root)
    except RunLockHeld as e:
        raise click.ClickException(str(e))

    registry = Registry(layout.registry_path())
    try:
        # persist wired so every EDGAR pull is frozen before parse (§3, §9a).
        edgar_client = EdgarClient(
            str(user_agent),
            max_per_sec=float(edgar_cfg.get("max_requests_per_sec", 8.0)),
            persist=lambda name, body: write_atomic(layout.edgar_path(tick_date, name), body))
        # §9a prices ingest: default httpx fetch; the clock pins frozen pulls to this tick's date.
        # Rate-limited + 429/403-backoff like EDGAR. Tiingo's token rides the Authorization header
        # (built inside PriceIngest via the _Secret holder) — never the URL, never config.
        price_ingest = PriceIngest(
            layout, clock=lambda: tick_date,
            max_per_sec=float((cfg.get("prices") or {}).get("max_requests_per_sec", 2.0)),
            api_token=api_token)
        # §4b/§9e holdings ingest: default httpx fetch (SSGA serves the daily files to a browser UA),
        # the clock pins frozen holdings pulls to this tick's date. Public files -> no token; the
        # dispersion pass pulls each resolvable basket's holdings + its constituent prices (Tiingo).
        holdings_ingest = HoldingsIngest(layout, clock=lambda: tick_date)
        deps = RunnerDeps(
            layout=layout, registry=registry, event_store=EventStore(layout, registry),
            edgar_client=edgar_client, price_ingest=price_ingest, holdings_ingest=holdings_ingest,
            notifier=notifier,
            cfg=cfg, cfg_hash=cfg_hash, now=now, run_id=uuid4().hex, monotonic=time.monotonic,
            heartbeat=heartbeat, capture_provider=capture_provider)
        runlog = run_tick(deps)
    finally:
        registry.close()
    click.echo(f"run {runlog.run_id} date={runlog.date} "
               f"config_changed={runlog.config_changed} pushed={runlog.pushed} "
               f"faults={len(runlog.faults)}")


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
    crisis_level = cfg["xcorr"]["stress"]["crisis_level"]
    stress_diag = runner_mod.stress_diagnostics(
        z, stress, from_date, to_date, crisis_level,
        cfg["xcorr"]["z_in"], target_pair=("XLK", "XLU"))
    stress_validation = runner_mod.stress_concept_validation(
        stress, from_date, to_date, crisis_level)
    ac0 = (stress_validation.get("acute_crises") or [{}])[0]
    crash_fals = runner_mod.crash_falsification(
        result, stress, crisis_level, bt["stress_window"]["from"], bt["stress_window"]["to"],
        ac0.get("onset"), ac0.get("gate_rises"), int(bt["crash_revert_weeks"]))

    sweep_results = []
    if sweep:
        pairs_leads = runner_mod._pairs_with_series(
            tickers, runner_mod.load_series_ids(bt["series_ids_path"]))
        grid = [tuple(g) for g in bt["sweep_grid"]]
        sweep_results = runner_mod.sweep(z, stress, pairs_leads, from_date, to_date, grid,
                                         crisis_level)

    launches = load_launches(bt["launches_path"])
    rep = report_mod.build_report(result, sweep_results, launches,
                                  cfg["sector_keywords"], cfg,
                                  beta_strip=beta_strip, stress_diag=stress_diag,
                                  stress_validation=stress_validation,
                                  crash_falsification=crash_fals)
    jpath, mpath = report_mod.write_report(result.run_root, rep)

    r = rep["recall"]
    p = rep["precision"]["summary"]
    f = rep["falsification"]
    click.echo(f"recall {r['target']}: {'FIRED' if r['fired'] else 'DID NOT FIRE'}")
    click.echo(f"precision: {p['n_structural']}/{p['n_firings']} structural "
               f"({p['structural_fraction']:.1%})")
    click.echo(f"falsification (rev5): (i) β-strip {'✓' if f.get('i_beta_strip_clean') else '✗'} · "
               f"(ii) gate-fires {'✓' if f.get('ii_gate_fires') and f.get('ii_not_whole_window') else '✗'} · "
               f"(iii) reversion "
               f"{'✓ all transient' if f.get('iii_all_transient') else 'FLAGS ' + str(f.get('iii_n_persistent')) + ' persistent'} "
               f"({f['new_leads_spawned_in_window']} crash spawns)")
    if rep["cross_stream_lag"]:
        click.echo(f"lag datum: {rep['cross_stream_lag']['lag_days']} days")
    click.echo(f"artifact: {mpath}")


# -- verdict (the human judgment write path) ---------------------------------------

@cli.command("verdict")
@click.argument("lead_id")
@click.argument("value", type=click.Choice(list(VERDICT_VOCAB)))
@click.option("-m", "--note", "note", default=None, help="Optional note on the verdict.")
@_store_option
def verdict(lead_id, value, note, store_path):
    """Append a verdict event; a changed mind supersedes the current one, never edits it.

    Four dispositions (guidance rev2 §8.4): yes (promoted, on-thesis); watch (on-thesis but
    UNPROVEN, still live); off-thesis-real (REAL but off-thesis macro/sector regime — catalogued
    as context, inert, no action ever); noise (not real, closed). off-thesis-real and watch are
    deliberately distinct — do not file a live candidate tech lead as macro.
    """
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
