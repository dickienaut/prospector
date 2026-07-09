# `prospector/runner/` — the M5 cadence driver (spec §9)

This package is the scheduled entrypoint: **one invocation = one tick**. Everything through M4 is a
pure function or a deferred pass waiting for a driver — this is that driver. It invokes the
deterministic sensors in the **CONTRACT run order**, on cadence, and renders their output. It adds
**no intelligence** (CONTRACT): all judgment lives in the sensors (as facts) and the human (as
verdicts). If a change here would make the runner *interpret* rather than *sequence*, it belongs in
a sensor or in the human's hands. **Built and live** (`pros run`).

Two invariants hold the whole package together. **Firewall (CONTRACT):** the runner touches only its
own store and its own notifier — never the detector's bucket or `portfolio.yaml`, never a trade, and
exposes **no run-now surface** (cron invokes it; scheduling is M7). **Statelessness (§9f):** it holds
nothing across ticks — every between-tick state (the launch-diff prior, each xcorr pair's Schmitt
state, the mandate prior) is recovered from the fossil record, so two cold runs over the same store
produce identical events.

## Modules

- **`runner.py`** — `run_tick(deps) -> RunLog`, the only public entry point. Executes the seven
  run-order steps (config-honesty-first → ingest → sensors §4a–§4d → identity retries → capture no-op
  → reactive snapshots → `state_changed`-pinned push) inside a `try/finally` so a fatal exception
  still writes the run-log and still pushes (the **dead-man**). Fault granularity is deliberate: a
  per-unit failure (one fund's 404, one basket's degenerate matrix) is a **soft `fault`** on `_system`
  and the tick continues; only an escaped exception is fatal. **The module docstring's state map
  (lines 15–21) is the authoritative WIRED-vs-SLOT list** — keep it current before this README.
  Currently SLOTs: **§4b dispersion + §9e shadow clock**, **§4d rebalance runner-wiring**, and the
  **§10 real email sender**. (The dispersion and rebalance *sensors* are built in `sensors/`; only
  their wiring **into the runner** is deferred — see ARCHITECTURE §9.)
- **`deps.py`** — `RunnerDeps`, the injected seam bundle for one tick: store handles, the EDGAR
  client (`persist` pre-wired to freeze-before-parse, §3), the price ingest, the notifier, the loaded
  config + its hash, the single `now`, and a `monotonic` clock (elapsed only — **never** a record
  time). `pros run` builds the live bundle; tests build a fixture one, so the whole tick runs offline
  under the network guard.
- **`notify.py`** — the notifier seam (§10). `Notifier` is the transport `Protocol`; `NullNotifier`
  is today's implementation — it records what *would* be sent and sends nothing, so the push-decision
  path is fully exercised offline. **The real SMTP/SES sender is DEFERRED** (build-order step 4). The
  runner *decides* what to send (pinned to `fold.state_changed`); the notifier is only transport.
- **`runlog.py`** — `RunLog` + `write_run_log`/`recent_runs`, the per-tick operational telemetry
  (§9g). One object per tick under `runs/{date}_{run_id}.json`, indexed in a `runs` table. It is
  **not an event on a lead** — it never folds into lead state, never drives a push, and is excluded
  from the statelessness property (run-logs differ by `run_id`/elapsed). The `runs` table is owned
  here (not in the frozen vendored `registry.py` DDL), mirroring the `resolution_queue`/`funds`
  precedent; the files are truth, the table is a disposable index.

## Important to know

- **The four subtle bits (§9, marked inline in `runner.py`):** (1) config-hash **before** any sensor
  — acting on an un-fossilized config change is a hindsight hole; (2) the mandate prior comes from the
  last **frozen** prospectus blob, never the registry `prospectus_accession` an intra-run identity
  pass may advance (§9c); (3) deferred passes are **called with** their sectors, never assume them
  (§9d); (4) the shadow clock surfaces readiness, **never** auto-promotes (§9e).
- **Push cadence is mechanical, not editorial:** `_compute_push` fires iff some lead's
  `{status, shadow, verdict}` changed, or any fault occurred. Ticks, silent corroborations
  (rebalance / `mandate.changed` / launch accretion), and queue mechanics produce no such delta and
  so do not push — this is the anti-slot-machine cadence, enforced in code.
- **The xcorr bridge:** universe tickers resolve to series-ids from **this tick's mf map**
  (`_universe_series_ids`), **not** the registry — the seed universe is never "launched" and so is
  never registered; reading the registry would leave xcorr permanently inert.

## See also

- Spec **§9/§9a–§9g** and §10 in `docs/prospector-v1-spec-rev14-2026-07-08.md`; `ARCHITECTURE.md`
  §2/§9. Decisions: `docs/decisions/2026-07-06-m5-runner-skeleton.md`, `-mandate-9c.md`,
  `-soi-corroboration-retry-9d.md`, `-soi-fetch.md`, `-prices-ingest-and-p1.md`,
  `2026-07-07-xcorr-live.md`, `2026-07-07-tiingo-price-source.md`, `2026-07-08-live-cadence-qa-fixes.md`.
