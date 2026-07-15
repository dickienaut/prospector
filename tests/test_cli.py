"""Verdict CLI (spec §8c): read-only lead views over folds, the append-only verdict path with
auto supersession, and `store reindex` repair. The command tree is pinned — no run-now, no
capture trigger (CLAUDE.md CONTRACT) — and an empty or absent store never crashes a read."""

import json
import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from prospector.cli.main import _load_dotenv, cli
from prospector.fold.fold import active_nonshadow, fold
from prospector.store.event_store import EventStore
from prospector.store.registry import Registry

FIXED_NOW = "2026-07-02T09:00:00Z"


def _event(lead, ts, type_, payload):
    return {"ts": ts, "lead": lead, "type": type_, "payload": payload, "schema": 1}


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def spawned(layout, registry):
    """A store with one spawned lead (two events) and one _system event."""
    store = EventStore(layout, registry, clock=lambda: FIXED_NOW)
    store.append(_event("ld_cli", "2026-07-01T00:00:00Z", "lead.spawned",
                        {"spawner": "xcorr", "display": "XLK×XLU", "shadow": False}))
    store.append(_event("ld_cli", "2026-07-02T00:00:00Z", "xcorr.tick", {"z": 3.1}))
    store.append(_event("_system", "2026-07-03T00:00:00Z", "config.changed", {"diff": {}}))
    return store


# -- the pinned surface: no run-now, no capture trigger ------------------------------

def test_command_tree_is_exactly_the_contract_surface():
    # backtest is calibration over frozen history, writing only under backtest/ — not a
    # run-now surface (it never recomputes the live record). `run` is the M5 cadence entrypoint
    # (spec §9): one invocation = one tick, cron-invoked — NOT a recompute/capture-on-demand
    # surface. Still no capture trigger, no recompute-on-demand of the live store (CLAUDE.md,
    # no-run-now CONTRACT).
    # `backup` and `store verify-restore` are READS of the store (durability mirror + restore proof) —
    # they compute nothing new and write only to external targets / a throwaway scratch, so they are in
    # the same allowed class as `store reindex`, NOT run-now surfaces (CLAUDE.md no-run-now CONTRACT).
    assert set(cli.commands) == {"store", "lead", "verdict", "identity", "backtest", "run", "backup"}
    # `store lock-path` (a pure read — prints the run.lock path) and `store lock-run` (acquire the
    # single-writer lock, run a command under it — the M7-04 deploy coordinator) are store MAINTENANCE, not
    # run-now surfaces: neither recomputes the live record (the no-run-now CONTRACT holds, like reindex).
    assert set(cli.commands["store"].commands) == {"reindex", "verify-restore", "lock-path", "lock-run"}
    assert set(cli.commands["lead"].commands) == {"list", "show"}
    assert set(cli.commands["identity"].commands) == {"resolve", "queue"}
    # `pros run` is a cadence entrypoint, not a run-now surface: its only params are --store and the
    # §10 --heartbeat flag (which ONLY adds the weekly heartbeat email to the tick — it never
    # recomputes or captures on demand, so the no-run-now CONTRACT holds).
    assert {p.name for p in cli.commands["run"].params} == {"store_path", "heartbeat"}


# -- lead list ------------------------------------------------------------------------

def test_lead_list_shows_spawned_lead(runner, spawned, store_root):
    result = runner.invoke(cli, ["lead", "list", "--store", str(store_root)])
    assert result.exit_code == 0, result.output
    lines = [l for l in result.output.splitlines() if l]
    assert len(lines) == 1  # _system is infra, never a lead
    fields = lines[0].split("\t")
    assert fields == ["ld_cli", "XLK×XLU", "active", "-", "none", "3.1", "2"]


def test_lead_list_missing_store_neither_crashes_nor_creates(runner, tmp_path):
    absent = tmp_path / "nope"
    result = runner.invoke(cli, ["lead", "list", "--store", str(absent)])
    assert result.exit_code == 0, result.output
    assert not absent.exists()  # a read surface must not conjure a store


# -- lead show ------------------------------------------------------------------------

def test_lead_show_renders_timeline_and_folded_state(runner, spawned, store_root):
    result = runner.invoke(cli, ["lead", "show", "ld_cli", "--store", str(store_root)])
    assert result.exit_code == 0, result.output
    assert "lead.spawned" in result.output
    assert "xcorr.tick" in result.output
    assert "2026-07-01T00:00:00Z" in result.output
    # The folded state is the JSON tail, parseable as written; the pretty-printed dict
    # opens on its own line, unlike the one-line payload summaries above it.
    lines = result.output.splitlines()
    state = json.loads("\n".join(lines[lines.index("{"):]))
    assert state["status"] == "active"
    assert state["latest_z"] == 3.1
    assert state["event_count"] == 2


def test_lead_show_unknown_lead_fails(runner, spawned, store_root):
    result = runner.invoke(cli, ["lead", "show", "ld_ghost", "--store", str(store_root)])
    assert result.exit_code != 0
    assert "unknown lead" in result.output


# -- verdict: append-only with auto supersession ----------------------------------------

def test_verdict_appends_and_second_supersedes_first(runner, spawned, layout, store_root,
                                                     registry):
    first = runner.invoke(cli, ["verdict", "ld_cli", "watch", "-m", "keep reading",
                                "--store", str(store_root)])
    assert first.exit_code == 0, first.output
    first_id = first.output.strip()

    second = runner.invoke(cli, ["verdict", "ld_cli", "yes", "--store", str(store_root)])
    assert second.exit_code == 0, second.output
    second_id = second.output.strip()
    assert first_id != second_id

    state = fold(registry.events_for_lead("ld_cli"))
    assert state["verdict"] == "yes"
    assert state["anomalies"] == []  # the auto-filled chain is well-formed
    by_id = {v["event_id"]: v for v in state["verdict_history"]}
    assert by_id[first_id]["superseded_by"] is None
    assert by_id[first_id]["note"] == "keep reading"
    assert by_id[second_id]["superseded_by"] == first_id

    # The events are in the fossil record, not just the index.
    files = sorted((layout.events_root() / "ld_cli").glob("*_verdict_*.json"))
    assert {f.stem.rsplit("_", 1)[1] for f in files} == {first_id, second_id}


def test_third_verdict_supersedes_the_new_head(runner, spawned, store_root, registry):
    ids = []
    for value in ("watch", "noise", "yes"):
        result = runner.invoke(cli, ["verdict", "ld_cli", value,
                                     "--store", str(store_root)])
        assert result.exit_code == 0, result.output
        ids.append(result.output.strip())
    state = fold(registry.events_for_lead("ld_cli"))
    assert state["verdict"] == "yes"
    by_id = {v["event_id"]: v for v in state["verdict_history"]}
    assert by_id[ids[2]]["superseded_by"] == ids[1]
    assert by_id[ids[1]]["superseded_by"] == ids[0]


def test_verdict_accepts_the_four_dispositions_and_off_thesis_real_is_inert(
        runner, spawned, store_root, registry):
    # All four ratified dispositions write; off-thesis-real (a real-but-macro classification) is a
    # first-class value distinct from watch — the three-live-meanings split (guidance rev2 §8.4).
    for value in ("yes", "watch", "off-thesis-real", "noise"):
        r = runner.invoke(cli, ["verdict", "ld_cli", value, "--store", str(store_root)])
        assert r.exit_code == 0, r.output
    state = fold(registry.events_for_lead("ld_cli"))
    assert state["verdict"] == "noise"                     # last written is the chain head
    # off-thesis-real is DISPLAY-ONLY / inert: it never changes the lead's active/shadow mechanics.
    off = fold([e for e in registry.events_for_lead("ld_cli")
                if not (e["type"] == "verdict")] +
               [{"event_id": "vX", "ts": "2026-07-20T00:00:00Z", "type": "verdict",
                 "payload": {"verdict": "off-thesis-real", "note": None, "superseded_by": None}}])
    assert off["verdict"] == "off-thesis-real"
    assert off["status"] == "active"                       # a verdict never flips status
    assert active_nonshadow([off]) == [off]                # ...and never gates the ceiling


def test_verdict_rejects_unknown_lead_and_retired_or_unknown_value(runner, spawned, store_root,
                                                                   registry):
    result = runner.invoke(cli, ["verdict", "ld_ghost", "yes", "--store", str(store_root)])
    assert result.exit_code != 0
    assert registry.events_for_lead("ld_ghost") == []
    # `no` is retired -> `noise`; the Choice rejects it and an unknown value.
    for bad in ("no", "maybe"):
        result = runner.invoke(cli, ["verdict", "ld_cli", bad, "--store", str(store_root)])
        assert result.exit_code != 0
    assert registry.events_for_lead("ld_cli", type="verdict") == []


# -- store reindex ------------------------------------------------------------------------

def test_store_reindex_rebuilds_lost_registry(runner, spawned, layout, store_root, registry):
    registry.close()
    layout.registry_path().unlink()
    for suffix in ("-wal", "-shm"):
        p = Path(str(layout.registry_path()) + suffix)
        if p.exists():
            p.unlink()

    result = runner.invoke(cli, ["store", "reindex", "--store", str(store_root)])
    assert result.exit_code == 0, result.output
    assert "events_indexed=3" in result.output
    assert "snapshots_indexed=0" in result.output
    assert "skipped=0" in result.output

    listed = runner.invoke(cli, ["lead", "list", "--store", str(store_root)])
    assert listed.exit_code == 0, listed.output
    assert "ld_cli" in listed.output
    assert "active" in listed.output


# -- store root default resolution ---------------------------------------------------------

def test_default_store_root_comes_from_config(runner, spawned, store_root, tmp_path,
                                              monkeypatch):
    cwd = tmp_path / "elsewhere"
    (cwd / "config").mkdir(parents=True)
    (cwd / "config" / "prospector.yaml").write_text(
        f"store:\n  root: {json.dumps(str(store_root))}\n", encoding="utf-8")
    monkeypatch.chdir(cwd)
    result = runner.invoke(cli, ["lead", "list"])
    assert result.exit_code == 0, result.output
    assert "ld_cli" in result.output


def test_default_store_root_without_config_is_cwd_store(runner, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(cli, ["lead", "list"])
    assert result.exit_code == 0, result.output
    assert not (tmp_path / "store").exists()


# -- `pros run` Tiingo token wiring (§9a): fail fast, and load the .env -----------------------

def test_run_missing_tiingo_token_errors_before_any_fetch(runner, tmp_path, monkeypatch):
    # primary: tiingo but no TIINGO_API_TOKEN -> a ClickException at startup, BEFORE the store is
    # created or any fetch runs. Fail-fast because the runner treats a fetch fail as a soft fault, so a
    # missing token would otherwise silently empty the whole panel rather than tell the operator.
    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "config" / "prospector.yaml").write_text(
        'edgar:\n  user_agent: "Test/1.0 (t@e.com)"\nprices:\n  primary: tiingo\n', encoding="utf-8")
    monkeypatch.delenv("TIINGO_API_TOKEN", raising=False)
    monkeypatch.chdir(tmp_path)   # no .env here -> _load_dotenv is a no-op, token stays unset
    result = runner.invoke(cli, ["run", "--store", str(tmp_path / "store")])
    assert result.exit_code != 0
    assert "TIINGO_API_TOKEN unset" in result.output
    assert not (tmp_path / "store").exists()  # failed before creating the store


def test_run_email_configured_without_password_errors_before_any_fetch(runner, tmp_path, monkeypatch):
    # §10 fail-fast (mirrors the Tiingo one): email.smtp_host set but PROSPECTOR_SMTP_PASSWORD unset ->
    # a ClickException at startup, BEFORE the store is created — a silent no-send would defeat the dead-man.
    # prices.primary stays default (yahoo) so this is the email check firing, not the Tiingo one.
    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "config" / "prospector.yaml").write_text(
        'edgar:\n  user_agent: "Test/1.0 (t@e.com)"\n'
        'email:\n  smtp_host: smtp.example.com\n  to: me@e.com\n', encoding="utf-8")
    monkeypatch.delenv("PROSPECTOR_SMTP_PASSWORD", raising=False)
    monkeypatch.chdir(tmp_path)   # no .env here -> the password stays unset
    result = runner.invoke(cli, ["run", "--store", str(tmp_path / "store")])
    assert result.exit_code != 0
    assert "PROSPECTOR_SMTP_PASSWORD is unset" in result.output
    assert not (tmp_path / "store").exists()  # failed before creating the store


def test_load_dotenv_populates_env_with_setdefault_semantics(tmp_path, monkeypatch):
    # The piece that makes the owner's .env actually reach `pros run`: parse it into os.environ, but
    # NEVER override an already-exported value (setdefault) — an explicit export wins over the file.
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        '# comment\n\nexport TIINGO_API_TOKEN="tok_from_file"\nALREADY=from_file\n', encoding="utf-8")
    monkeypatch.delenv("TIINGO_API_TOKEN", raising=False)
    monkeypatch.setenv("ALREADY", "from_env")
    _load_dotenv()
    assert os.environ["TIINGO_API_TOKEN"] == "tok_from_file"  # `export ` + quotes stripped
    assert os.environ["ALREADY"] == "from_env"                # setdefault: the exported value wins


def test_load_dotenv_is_a_noop_when_absent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # no .env
    _load_dotenv()  # must not raise
